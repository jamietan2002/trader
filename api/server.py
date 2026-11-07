"""REST API & Web Dashboard Server for the Swing Trading AI Platform.

Exposes:
- `GET /`: Full 7-tab Interactive Quantitative Dashboard
- `GET /api/health`: System health & trading mode status
- `GET /api/dashboard-state`: Complete aggregated state for all 7 dashboard tabs
- `GET /api/account`: Paper account summary, open positions, orders, and ledger
- `GET /api/strategies`: Versioned strategy registry and experiment history
- `POST /api/backtest`: Run a deterministic backtest for any registered strategy
- `POST /api/research/scan`: Trigger the Autonomous Market Research Agent
- `POST /api/workflow/daily`: Trigger the Daily Pre-Market / Execution / Post-Close workflow
- `POST /api/workflow/weekly`: Trigger the Weekly AI Strategy Discovery & Walk-Forward workflow
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from dashboard.ui_template import DASHBOARD_HTML
from infrastructure.configuration.settings import Settings, get_settings
from infrastructure.database.db import DatabaseManager
from infrastructure.logging.logger import get_logger
from infrastructure.scheduler.orchestrator import AutonomousWorkflowOrchestrator

logger = get_logger("api.server")


class PlatformApplication:
    """Application controller shared across REST endpoints, CLI, and Streamlit."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.db = DatabaseManager(self.settings.sqlite_path)
        self.orchestrator = AutonomousWorkflowOrchestrator(self.settings, self.db)

    def get_dashboard_state(self) -> Dict[str, Any]:
        return {
            "settings": self.settings.sanitized_dict(),
            "account": self.orchestrator.paper_engine.get_account_summary(),
            "positions": self.orchestrator.paper_engine.get_open_positions(),
            "orders": self.orchestrator.paper_engine.get_orders(limit=50),
            "trade_ledger": self.orchestrator.paper_engine.get_trade_ledger(limit=100),
            "snapshots": self.orchestrator.paper_engine.get_portfolio_snapshots(),
            "strategies": [s.to_dict() for s in self.orchestrator.registry.list_strategies()],
            "experiments": self.orchestrator.registry.list_experiments(),
            "research_reports": self.orchestrator.research_agent.get_latest_reports(limit=15),
            "proposals": self.orchestrator.analyst_agent.list_proposals(limit=15),
            "risk_alerts": self.orchestrator.risk_agent.get_recent_alerts(limit=30),
            "jobs": self.orchestrator.get_job_history(limit=30),
        }

    def run_backtest_endpoint(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        strategy_id = str(payload.get("strategy_id", "strat_momentum_trend"))
        version = int(payload.get("version", 1))
        start_date = str(payload.get("start_date", "2023-03-01"))
        end_date = str(payload.get("end_date", "2025-06-30"))

        strat = self.orchestrator.registry.get_strategy(strategy_id, version)
        if strat is None:
            strats = self.orchestrator.registry.list_strategies(strategy_id=strategy_id)
            if not strats:
                raise KeyError(f"Strategy {strategy_id} not found")
            strat = strats[0]

        res = self.orchestrator.backtest_engine.run_backtest(
            strategy=strat,
            start_date=start_date,
            end_date=end_date,
            experiment_type="ON_DEMAND",
        )
        return res.to_dict()


def create_http_handler(app: PlatformApplication) -> type[BaseHTTPRequestHandler]:
    class RequestHandler(BaseHTTPRequestHandler):
        def _send_json(self, status_code: int, data: Any) -> None:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status_code: int, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw) if raw else {}

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path in ("/", "/dashboard"):
                    self._send_html(200, DASHBOARD_HTML)
                elif path == "/api/health":
                    self._send_json(
                        200,
                        {
                            "status": "ok",
                            "trading_mode": app.settings.trading_mode,
                            "market_timezone": app.settings.market_timezone,
                            "operator_timezone": app.settings.operator_timezone,
                        },
                    )
                elif path == "/api/dashboard-state":
                    self._send_json(200, app.get_dashboard_state())
                elif path == "/api/account":
                    self._send_json(
                        200,
                        {
                            "summary": app.orchestrator.paper_engine.get_account_summary(),
                            "positions": app.orchestrator.paper_engine.get_open_positions(),
                            "orders": app.orchestrator.paper_engine.get_orders(limit=50),
                            "ledger": app.orchestrator.paper_engine.get_trade_ledger(limit=100),
                        },
                    )
                elif path == "/api/strategies":
                    self._send_json(
                        200,
                        {
                            "strategies": [
                                s.to_dict() for s in app.orchestrator.registry.list_strategies()
                            ],
                            "experiments": app.orchestrator.registry.list_experiments(),
                        },
                    )
                else:
                    self._send_json(404, {"error": f"Endpoint {path} not found"})
            except Exception as exc:
                logger.error(f"GET {path} failed: {exc}")
                self._send_json(500, {"error": str(exc)})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                payload = self._read_json_body()
                if path == "/api/backtest":
                    self._send_json(200, app.run_backtest_endpoint(payload))
                elif path == "/api/research/scan":
                    as_of = str(payload.get("as_of_date", "2025-06-27"))
                    res = app.orchestrator.research_agent.run_market_scan(as_of_date=as_of)
                    self._send_json(200, res)
                elif path == "/api/workflow/daily":
                    dt = str(payload.get("trading_date", "2025-06-27"))
                    force = bool(payload.get("force", True))
                    res = app.orchestrator.run_daily_workflow(trading_date=dt, force=force)
                    self._send_json(200, res)
                elif path == "/api/workflow/weekly":
                    dt = str(payload.get("week_ending_date", "2025-06-27"))
                    fam = payload.get("preferred_family")
                    force = bool(payload.get("force", True))
                    res = app.orchestrator.run_weekly_workflow(
                        week_ending_date=dt, preferred_family=fam, force=force
                    )
                    self._send_json(200, res)
                else:
                    self._send_json(404, {"error": f"Endpoint {path} not found"})
            except Exception as exc:
                logger.error(f"POST {path} failed: {exc}")
                self._send_json(500, {"error": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return RequestHandler


def run_server(host: Optional[str] = None, port: Optional[int] = None, bootstrap: bool = True) -> None:
    """Start the HTTP API and Dashboard server."""
    settings = get_settings()
    app = PlatformApplication(settings)
    if bootstrap and not app.orchestrator.registry.list_strategies():
        logger.info("Bootstrapping initial historical dataset, 3 baseline strategies, and paper sessions...")
        app.orchestrator.bootstrap_baseline_system()
        from core.market_data.models import USTradingCalendar
        for session_dt in USTradingCalendar.get_trading_days("2025-05-01", "2025-05-20"):
            app.orchestrator.run_daily_workflow(session_dt)

    bind_host = host or settings.api_host
    bind_port = port or settings.api_port
    server = ThreadingHTTPServer((bind_host, bind_port), create_http_handler(app))
    logger.info(f"Swing Trading AI Dashboard & API running at http://{bind_host}:{bind_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.server_close()

