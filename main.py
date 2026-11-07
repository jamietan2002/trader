"""Main CLI and Application Entrypoint for the Swing Trading AI Platform.

Commands:
- `python3 main.py bootstrap`: Ingest US equity data, run 3 baseline strategies through
  In-Sample / Validation / Out-of-Sample / Walk-Forward / Stress-Testing, and evaluate promotion.
- `python3 main.py daily --date 2025-06-27`: Run the autonomous daily workflow (Pre-Market Research,
  Paper Trading Execution, Post-Close Reconciliation & Performance Analysis).
- `python3 main.py weekly --date 2025-06-27`: Run the autonomous weekly AI Strategy Discovery,
  Backtesting, and Walk-Forward Validation loop.
- `python3 main.py demo`: Run a complete end-to-end lifecycle demonstration and print a full summary.
- `python3 main.py serve`: Launch the REST API & Interactive 7-Tab Web Dashboard on http://127.0.0.1:8080.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from api.server import PlatformApplication, run_server
from core.strategies.registry import StrategyFamily
from infrastructure.configuration.settings import get_settings


def cmd_bootstrap(app: PlatformApplication) -> None:
    res = app.orchestrator.bootstrap_baseline_system()
    print(json.dumps(res, indent=2))


def cmd_daily(app: PlatformApplication, trading_date: str, force: bool) -> None:
    res = app.orchestrator.run_daily_workflow(trading_date=trading_date, force=force)
    print(json.dumps(res, indent=2))


def cmd_weekly(app: PlatformApplication, week_date: str, family: str | None, force: bool) -> None:
    res = app.orchestrator.run_weekly_workflow(
        week_ending_date=week_date, preferred_family=family, force=force
    )
    print(json.dumps(res, indent=2))


def cmd_demo(app: PlatformApplication) -> None:
    print("=" * 88)
    print("SWING TRADING AI PLATFORM — END-TO-END SYSTEMATIC RESEARCH & PAPER TRADING RUN")
    print("=" * 88)
    boot = app.orchestrator.bootstrap_baseline_system()
    ing = boot["ingestion"]
    print(
        f"\n[1] Market Data Ingested ({ing['provider']}): "
        f"{ing['tickers_ingested']} US equities, {ing['bars_ingested']} daily bars, "
        f"{ing['earnings_ingested']} earnings events, dataset={ing['dataset_version']}"
    )

    print("\n[2] Three Baseline Strategies Backtested & Validated vs SPY:")
    for b in boot["baseline_evaluations"]:
        m = b["metrics"]
        print(
            f"  - {b['strategy_id']} v{b['version']} [{b['status']}]: "
            f"Return={m['total_return_pct']:+.2f}% (vs SPY {m['benchmark_return_pct']:+.2f}%), "
            f"Sharpe={m['sharpe_ratio']:.2f}, Sortino={m['sortino_ratio']:.2f}, "
            f"PF={m['profit_factor']:.2f}, MaxDD=-{m['max_drawdown_pct']:.2f}%, Trades={m['trade_count']}"
        )

    print("\n[3] Running Autonomous Daily Workflows (Pre-Market -> Paper Execution -> Post-Close):")
    from core.market_data.models import USTradingCalendar
    paper_dates = USTradingCalendar.get_trading_days("2025-05-01", "2025-05-20")
    for dt in paper_dates:
        daily_out = app.orchestrator.run_daily_workflow(trading_date=dt, force=True)
        exec_sum = daily_out["market_execution"]["summary"]
        acc_sum = exec_sum["account_summary"]
        entries_n = len(exec_sum["entries_executed"])
        exits_n = len(exec_sum["exits_executed"])
        if entries_n > 0 or exits_n > 0 or dt == paper_dates[-1]:
            print(
                f"  - Session {dt}: Entries={entries_n}, Exits={exits_n} | "
                f"Equity=${acc_sum['total_equity']:,.2f} ({acc_sum['total_return_pct']:+.2f}%), "
                f"Cash=${acc_sum['cash_balance']:,.2f}, OpenPositions={acc_sum['open_positions_count']}, "
                f"DD=-{acc_sum['current_drawdown_pct']:.2f}%"
            )

    print("\n[4] Running Weekly AI Strategy Discovery & Walk-Forward Validation Loop:")
    weekly_mr = app.orchestrator.run_weekly_workflow(
        week_ending_date="2025-06-27",
        preferred_family=StrategyFamily.MEAN_REVERSION.value,
        force=True,
    )
    w_sum = weekly_mr["summary"]
    print(
        f"  - Discovered Candidate: {w_sum['candidate_strategy_id']} v{w_sum['candidate_version']} "
        f"({w_sum['strategy_family']}) -> Status={w_sum['new_status']}"
    )
    print(f"    Decision: {w_sum['decision_summary']}")

    weekly_evolve = app.orchestrator.run_weekly_workflow(
        week_ending_date="2025-06-27",
        preferred_family=None,
        force=True,
    )
    we_sum = weekly_evolve["summary"]
    print(
        f"  - Analyst-Driven Evolution: {we_sum['candidate_strategy_id']} v{we_sum['candidate_version']} "
        f"({we_sum['strategy_family']}) -> Status={we_sum['new_status']}"
    )
    print(f"    Decision: {we_sum['decision_summary']}")

    acc = app.orchestrator.paper_engine.get_account_summary()
    print("\n[5] Reconciled $100,000 Paper Account State:")
    print(json.dumps(acc, indent=2))
    print("=" * 88)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Swing Trading AI Research & Paper-Trading Platform")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("bootstrap", help="Ingest market data and evaluate the 3 baseline strategies")
    sub.add_parser("demo", help="Run full end-to-end demonstration workflow")

    p_daily = sub.add_parser("daily", help="Run daily pre-market, paper execution, and post-close workflow")
    p_daily.add_argument("--date", default="2025-06-27", help="Trading session date (YYYY-MM-DD)")
    p_daily.add_argument("--force", action="store_true", help="Force re-run even if idempotent key exists")

    p_weekly = sub.add_parser("weekly", help="Run weekly strategy discovery & validation workflow")
    p_weekly.add_argument("--date", default="2025-06-27", help="Week ending date (YYYY-MM-DD)")
    p_weekly.add_argument("--family", default=None, help="Optional StrategyFamily override")
    p_weekly.add_argument("--force", action="store_true", help="Force re-run")

    p_serve = sub.add_parser("serve", help="Start REST API and 7-tab Web Dashboard server")
    p_serve.add_argument("--host", default=None, help="Bind host (default 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=None, help="Bind port (default 8080)")

    p_ide_ctx = sub.add_parser(
        "ide-context",
        help="Run deterministic daily ingestion/execution and output compact JSON context for the IDE AI Agent",
    )
    p_ide_ctx.add_argument("--date", default=None, help="Optional trading date override (YYYY-MM-DD)")
    p_ide_ctx.add_argument("--skip-daily", action="store_true", help="Skip running daily workflow first")

    p_ide_apply = sub.add_parser(
        "ide-apply",
        help="Apply IDE AI Agent qualitative research updates and run multi-candidate strategy tournament",
    )
    p_ide_apply.add_argument("--json", default=None, help="Inline JSON payload string")
    p_ide_apply.add_argument("--file", default=None, help="Path to JSON payload file")
    p_ide_apply.add_argument("--date", default=None, help="Optional trading date override")

    args = parser.parse_args(argv)
    settings = get_settings()
    app = PlatformApplication(settings)

    if args.command == "bootstrap":
        cmd_bootstrap(app)
    elif args.command == "daily":
        cmd_daily(app, args.date, args.force)
    elif args.command == "weekly":
        cmd_weekly(app, args.date, args.family, args.force)
    elif args.command == "ide-context":
        res = app.orchestrator.export_ide_ai_context(
            trading_date=args.date, run_daily_first=not args.skip_daily
        )
        print(json.dumps(res, indent=2))
    elif args.command == "ide-apply":
        if args.file:
            with open(args.file, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        elif args.json:
            payload = json.loads(args.json)
        else:
            payload = json.load(sys.stdin)
        res = app.orchestrator.apply_ide_ai_cycle(payload=payload, session_date=args.date)
        print(json.dumps(res, indent=2))
    elif args.command == "serve":
        run_server(host=args.host, port=args.port, bootstrap=True)
    else:
        cmd_demo(app)
    return 0


if __name__ == "__main__":
    sys.exit(main())

