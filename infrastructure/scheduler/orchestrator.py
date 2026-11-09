"""Autonomous Operating Workflow & Idempotent Job Orchestrator.

Implements:
1. Daily Pre-Market Job (`daily_pre_market`):
   - Update market data
   - Run Market Research Agent scan
   - Produce ranked research report
2. Daily Market Hours Job (`daily_market_execution`):
   - Evaluate entry and exit signals across active `PAPER_TRADING` strategies
   - Run `PortfolioRiskManager` checks
   - Submit & simulate paper orders with duplicate prevention
3. Daily Post-Close Job (`daily_post_close`):
   - Reconcile paper account state & mark-to-market snapshot
   - Run `PerformanceAnalystAgent` session review
   - Generate daily report and experiment proposals
4. Weekly Strategy Research & Validation Loop (`weekly_research_and_validation`):
   - Review strategy performance & analyst proposals
   - Generate new strategy hypotheses via `StrategyDiscoveryAgent`
   - Run In-Sample / Validation / Out-of-Sample / Walk-Forward / Stress-Test pipeline
   - Evaluate & promote/reject via `StrategyEvaluationAgent`
5. Idempotency & Recovery:
   - Every job run is keyed by `idempotency_key` in `job_executions`.
   - Completed jobs are not re-executed unless `force=True`.
   - Failed jobs record error state and can be cleanly retried/recovered.
   - Respects US market holidays (`USTradingCalendar`) and `America/New_York` / `Asia/Singapore` timezones.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from agents.market_researcher.agent import MarketResearchAgent
from agents.performance_analyst.agent import PerformanceAnalystAgent
from agents.risk_manager.agent import RiskManagerAgent
from agents.strategy_architect.agent import StrategyDiscoveryAgent
from agents.strategy_evaluator.agent import StrategyEvaluationAgent
from core.backtesting.engine import BacktestEngine
from core.execution.paper_broker import LiveTradingCopilotEngine, PaperTradingEngine
from core.market_data.models import USTradingCalendar
from core.market_data.providers import MarketDataService
from core.risk.manager import PortfolioRiskManager
from core.strategies.registry import (
    StrategyConfig,
    StrategyRegistry,
    StrategyStatus,
    get_baseline_strategies,
)
from infrastructure.configuration.settings import Settings
from infrastructure.database.db import DatabaseManager, utc_now_iso
from infrastructure.logging.logger import get_logger

logger = get_logger("infrastructure.scheduler")


class AutonomousWorkflowOrchestrator:
    """Persistent, idempotent workflow orchestrator for the Swing Trading AI Platform."""

    def __init__(
        self,
        settings: Settings,
        db: DatabaseManager,
        market_data: Optional[MarketDataService] = None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.market_data = market_data or MarketDataService(settings, db)
        self.registry = StrategyRegistry(db)
        self.risk_manager = PortfolioRiskManager(settings.risk, db=db)
        self.backtest_engine = BacktestEngine(settings, self.market_data)
        self.paper_engine = PaperTradingEngine(
            settings, db, self.market_data, risk_manager=self.risk_manager
        )
        self.live_copilot = LiveTradingCopilotEngine(
            settings, db, self.market_data, risk_manager=self.risk_manager, registry=self.registry
        )

        self.research_agent = MarketResearchAgent(settings, db, self.market_data)
        self.discovery_agent = StrategyDiscoveryAgent(settings, self.registry)
        self.evaluator_agent = StrategyEvaluationAgent(settings, self.registry)
        self.analyst_agent = PerformanceAnalystAgent(
            settings, db, self.paper_engine, self.registry
        )
        self.risk_agent = RiskManagerAgent(
            settings, db, self.risk_manager, self.paper_engine
        )

    def run_idempotent_job(
        self,
        job_name: str,
        idempotency_key: str,
        fn: Callable[[], Dict[str, Any]],
        max_retries: int = 2,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Execute a workflow job with idempotency, retry handling, and persistent state."""
        existing = self.db.fetch_one(
            "SELECT * FROM job_executions WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        if existing is not None and existing["status"] == "COMPLETED" and not force:
            return {
                "job_run_id": existing["job_run_id"],
                "job_name": job_name,
                "idempotency_key": idempotency_key,
                "status": "SKIPPED_IDEMPOTENT",
                "summary": json.loads(existing["summary_json"]) if existing["summary_json"] else {},
            }

        job_run_id = (
            existing["job_run_id"]
            if existing is not None
            else f"job_{uuid.uuid4().hex[:12]}"
        )
        started_at = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO job_executions (
                job_run_id, job_name, idempotency_key, status, started_at, completed_at, summary_json, error_message
            ) VALUES (?, ?, ?, 'RUNNING', ?, NULL, NULL, NULL)
            ON CONFLICT(idempotency_key) DO UPDATE SET
                status='RUNNING',
                started_at=excluded.started_at,
                error_message=NULL
            """,
            (job_run_id, job_name, idempotency_key, started_at),
        )

        last_err: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                summary = fn()
                completed_at = utc_now_iso()
                self.db.execute(
                    """
                    UPDATE job_executions
                    SET status = 'COMPLETED', completed_at = ?, summary_json = ?, error_message = NULL
                    WHERE idempotency_key = ?
                    """,
                    (completed_at, json.dumps(summary), idempotency_key),
                )
                return {
                    "job_run_id": job_run_id,
                    "job_name": job_name,
                    "idempotency_key": idempotency_key,
                    "status": "COMPLETED",
                    "summary": summary,
                }
            except Exception as exc:
                last_err = exc
                logger.warning(f"Job {job_name} ({idempotency_key}) attempt {attempt} failed: {exc}")
                if attempt < max_retries:
                    time.sleep(0.1 * attempt)

        err_msg = str(last_err)
        self.db.execute(
            """
            UPDATE job_executions
            SET status = 'FAILED', completed_at = ?, error_message = ?
            WHERE idempotency_key = ?
            """,
            (utc_now_iso(), err_msg, idempotency_key),
        )
        raise RuntimeError(f"Job {job_name} failed after {max_retries} attempts: {err_msg}")

    def bootstrap_baseline_system(
        self,
        start_date: str = "2023-01-03",
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Seed market data, register the 3 baseline strategies, backtest & validate them, and run initial paper trading."""
        # 1. Ingest historical US equity data
        ingest_summary = self.market_data.ingest_universe_and_history(
            start_date=start_date, end_date=end_date
        )
        dataset_version = ingest_summary["dataset_version"]

        # 2. Register and evaluate the three baseline strategies
        baselines = get_baseline_strategies()
        strategy_results: List[Dict[str, Any]] = []

        for strat in baselines:
            existing = self.registry.get_strategy(strat.strategy_id, strat.version)
            if existing is None:
                strat = self.registry.register_strategy(strat)
            else:
                strat = existing

            self.registry.update_status(
                strat.strategy_id,
                strat.version,
                StrategyStatus.BACKTESTING,
                reason="Running In-Sample / Validation / Out-of-Sample pipeline",
                dataset_version=dataset_version,
            )

            pipeline = self.backtest_engine.run_in_sample_validation_oos_pipeline(strat)
            full_bt = pipeline["full_period"]

            self.registry.update_status(
                strat.strategy_id,
                strat.version,
                StrategyStatus.VALIDATION,
                reason="Evaluating strategy promotion criteria",
                backtest_summary=full_bt["metrics"],
                dataset_version=dataset_version,
            )

            eval_report = self.evaluator_agent.evaluate_pipeline_results(
                strategy=strat,
                pipeline_results=pipeline,
                dataset_version=dataset_version,
                auto_transition=True,
            )

            self.registry.record_experiment(
                experiment_id=full_bt["experiment_id"],
                strategy_id=strat.strategy_id,
                version=strat.version,
                experiment_type="FULL_PIPELINE",
                dataset_version=dataset_version,
                start_date=full_bt["start_date"],
                end_date=full_bt["end_date"],
                parameters={"entry_rules": strat.entry_rules, "exit_rules": strat.exit_rules},
                metrics=full_bt["metrics"],
                equity_curve=full_bt["equity_curve"],
                trades=full_bt["trades"],
                evaluation_report=eval_report.to_dict(),
                passed_promotion=eval_report.promoted,
            )

            strategy_results.append(
                {
                    "strategy_id": strat.strategy_id,
                    "version": strat.version,
                    "promoted": eval_report.promoted,
                    "status": eval_report.new_status,
                    "metrics": full_bt["metrics"],
                    "decision_summary": eval_report.decision_summary,
                }
            )

        return {
            "ingestion": ingest_summary,
            "baseline_evaluations": strategy_results,
        }

    def run_daily_workflow(
        self,
        trading_date: str,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Execute the full Daily Autonomous Workflow (Pre-Market -> Market Hours -> Post-Close)."""
        dt = date.fromisoformat(trading_date)
        if not USTradingCalendar.is_trading_day(dt):
            return {
                "trading_date": trading_date,
                "status": "MARKET_HOLIDAY_OR_WEEKEND",
                "message": f"{trading_date} is not a NYSE/NASDAQ trading session.",
            }

        if hasattr(self.market_data, "ensure_latest_market_data"):
            self.market_data.ensure_latest_market_data(target_date=trading_date)

        # 1. Pre-Market: Market Research Scan
        pre_market_res = self.run_idempotent_job(
            job_name="daily_pre_market",
            idempotency_key=f"daily_pre_market:{trading_date}",
            fn=lambda: self.research_agent.run_market_scan(as_of_date=trading_date, top_n=8),
            force=force,
        )

        # 2. Market Hours: Paper Trading Execution across approved PAPER_TRADING strategies
        #    In live operation (outside unit tests), paper trades execute ONLY during regular US market hours
        #    (9:30 AM – 4:00 PM ET / 10:30 PM – 5:00 AM SGT in EST, 9:30 PM – 4:00 AM SGT in EDT).
        #    Do not lock daily_market_execution in job_executions when deferred outside market hours.
        import sys as _sys
        active_strats = self.registry.list_strategies(status=StrategyStatus.PAPER_TRADING.value)
        if "unittest" not in _sys.modules and not USTradingCalendar.is_market_open():
            market_exec_res = self.paper_engine.run_trading_session_for_strategies(
                active_strategies=active_strats,
                trading_date=trading_date,
            )
        else:
            live_exec_date = (
                USTradingCalendar.current_et_datetime().date().isoformat()
                if "unittest" not in _sys.modules
                else trading_date
            )
            market_exec_res = self.run_idempotent_job(
                job_name="daily_market_execution",
                idempotency_key=f"daily_market_execution:{live_exec_date}",
                fn=lambda: self.paper_engine.run_trading_session_for_strategies(
                    active_strategies=active_strats,
                    trading_date=live_exec_date,
                ),
                force=force,
            )

        # 3. Post-Close: Reconciliation, Risk Audit, and Performance Analyst Review
        def _post_close_fn() -> Dict[str, Any]:
            from core.indicators.technical import compute_indicator_series
            spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker, end_date=trading_date)
            spy_inds = compute_indicator_series(spy_bars) if spy_bars else {}
            spy_ind = spy_inds.get(trading_date) or (list(spy_inds.values())[-1] if spy_inds else None)
            detected_regime = self.backtest_engine._classify_regime(spy_ind)
            if detected_regime == "UNKNOWN":
                detected_regime = "BULL_LOW_VOL"

            risk_audit = self.risk_agent.audit_portfolio_health(eval_date=trading_date)
            perf_review = self.analyst_agent.review_session_performance(
                session_date=trading_date,
                current_regime=detected_regime,
            )
            now_op = datetime.now(self.settings.operator_tz).strftime("%Y-%m-%d %H:%M:%S %Z")
            return {
                "trading_date": trading_date,
                "operator_report_timestamp": now_op,
                "market_regime": detected_regime,
                "risk_audit": risk_audit,
                "performance_review": perf_review,
            }

        post_close_res = self.run_idempotent_job(
            job_name="daily_post_close",
            idempotency_key=f"daily_post_close:{trading_date}",
            fn=_post_close_fn,
            force=force,
        )

        return {
            "trading_date": trading_date,
            "pre_market": pre_market_res,
            "market_execution": market_exec_res,
            "post_close": post_close_res,
        }

    def run_pre_open_refresh(self, session_date: str) -> Dict[str, Any]:
        """Stage 2 (Pre-Open 9:00 AM ET / 9:00 PM SGT): Refresh research scan, live extended-hours quote cache, and paper AI catalyst sync."""
        scan_res = self.research_agent.run_market_scan(as_of_date=session_date, top_n=8)
        active_strats = self.registry.list_strategies(status=StrategyStatus.PAPER_TRADING.value)
        sync_res = self.paper_engine.sync_ai_catalysts_to_paper_accounts(
            active_strategies=active_strats,
            session_date=session_date,
        )
        copilot_plan = self.live_copilot.get_daily_action_plan(check_calendar_today=False)
        return {
            "session_date": session_date,
            "research_scanned": scan_res.get("universe_scanned", 0),
            "ai_paper_exits_triggered": len(sync_res.get("ai_paper_exits_triggered") or []),
            "copilot_buys_ready": len(copilot_plan.get("buy_actions") or []),
            "copilot_vetoed_count": len(copilot_plan.get("vetoed_signals") or []),
        }

    def run_weekly_workflow(
        self,
        week_ending_date: str,
        preferred_family: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Execute the Weekly Continuous Improvement Workflow:

        Research findings + Analyst proposals -> Strategy hypothesis -> Backtest -> Walk-Forward Validation -> Promotion/Rejection.
        """
        def _weekly_fn() -> Dict[str, Any]:
            latest_reports = self.research_agent.get_latest_reports(limit=10)
            proposals = self.analyst_agent.list_proposals(limit=5, status="PROPOSED")
            if not proposals:
                proposals = self.analyst_agent.list_proposals(limit=5)
            latest_proposal = proposals[0] if (proposals and not preferred_family) else None

            # Build Weekly Tournament Candidate Specs:
            # 1) Primary candidate (from Analyst Proposal or preferred_family)
            # 2) Secondary candidate (from top Market Research catalyst family, if distinct and not locked)
            candidate_specs: List[tuple[Optional[str], Optional[Dict[str, Any]]]] = [
                (preferred_family, latest_proposal)
            ]
            if preferred_family is None and latest_reports:
                top_research_fam = str(latest_reports[0].get("suggested_strategy_family", "MOMENTUM_TREND"))
                prop_sid = str((latest_proposal or {}).get("target_strategy_id", ""))
                if not prop_sid or top_research_fam.lower() not in prop_sid.lower():
                    candidate_specs.append((top_research_fam, None))

            tournament_results: List[Dict[str, Any]] = []
            seen_Strat_versions: set[tuple[str, int]] = set()

            for fam_hint, prop_item in candidate_specs:
                cand_strat = self.discovery_agent.propose_strategy_from_research(
                    research_candidates=latest_reports,
                    preferred_family=fam_hint,
                    analyst_proposal=prop_item,
                )
                if (cand_strat.strategy_id, cand_strat.version) in seen_Strat_versions:
                    continue
                seen_Strat_versions.add((cand_strat.strategy_id, cand_strat.version))

                self.registry.update_status(
                    cand_strat.strategy_id,
                    cand_strat.version,
                    StrategyStatus.BACKTESTING,
                    reason=f"Weekly tournament cycle ({week_ending_date})",
                )

                pipeline = self.backtest_engine.run_in_sample_validation_oos_pipeline(cand_strat)
                full_bt = pipeline["full_period"]

                eval_rep = self.evaluator_agent.evaluate_pipeline_results(
                    strategy=cand_strat,
                    pipeline_results=pipeline,
                    dataset_version=f"ds_weekly_{week_ending_date}",
                    auto_transition=True,
                )

                if prop_item and prop_item.get("proposal_id"):
                    self.analyst_agent.mark_proposal_status(
                        str(prop_item["proposal_id"]),
                        "PROMOTED" if eval_rep.promoted else "REJECTED",
                    )

                self.registry.record_experiment(
                    experiment_id=full_bt["experiment_id"],
                    strategy_id=cand_strat.strategy_id,
                    version=cand_strat.version,
                    experiment_type="WEEKLY_DISCOVERY",
                    dataset_version=f"ds_weekly_{week_ending_date}",
                    start_date=full_bt["start_date"],
                    end_date=full_bt["end_date"],
                    parameters={
                        "entry_rules": cand_strat.entry_rules,
                        "exit_rules": cand_strat.exit_rules,
                    },
                    metrics=full_bt["metrics"],
                    equity_curve=full_bt["equity_curve"],
                    trades=full_bt["trades"],
                    evaluation_report=eval_rep.to_dict(),
                    passed_promotion=eval_rep.promoted,
                )

                tournament_results.append(
                    {
                        "week_ending_date": week_ending_date,
                        "candidate_strategy_id": cand_strat.strategy_id,
                        "candidate_version": cand_strat.version,
                        "strategy_family": cand_strat.strategy_family,
                        "promoted": eval_rep.promoted,
                        "new_status": eval_rep.new_status,
                        "decision_summary": eval_rep.decision_summary,
                        "metrics": full_bt["metrics"],
                    }
                )

            # Rank tournament results: promoted strategies first, then highest Deflated Sharpe / Sharpe Ratio
            tournament_results.sort(
                key=lambda r: (
                    1 if r["promoted"] else 0,
                    float(r["metrics"].get("deflated_sharpe_pct", 0.0)),
                    float(r["metrics"].get("sharpe_ratio", 0.0)),
                ),
                reverse=True,
            )
            winner = dict(tournament_results[0])
            winner["tournament_candidates"] = tournament_results
            return winner

        return self.run_idempotent_job(
            job_name="weekly_research_and_validation",
            idempotency_key=f"weekly_research_and_validation:{week_ending_date}:{preferred_family or 'auto'}",
            fn=_weekly_fn,
            force=force,
        )

    def get_job_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM job_executions ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["summary"] = json.loads(r["summary_json"]) if r["summary_json"] else None
            out.append(d)
        return out

    def export_ide_ai_context(
        self,
        trading_date: Optional[str] = None,
        run_daily_first: bool = True,
    ) -> Dict[str, Any]:
        """Run deterministic daily ingestion/execution and export a compact JSON brief for the IDE AI Agent."""
        from core.indicators.technical import compute_indicator_series

        if not self.registry.list_strategies():
            self.bootstrap_baseline_system()

        if hasattr(self.market_data, "ensure_latest_market_data"):
            self.market_data.ensure_latest_market_data(target_date=trading_date)

        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker)
        latest_date = trading_date or (spy_bars[-1].bar_date if spy_bars else date.today().isoformat())

        daily_res = None
        if run_daily_first:
            daily_res = self.run_daily_workflow(trading_date=latest_date, force=False)

        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker, end_date=latest_date)
        spy_inds = compute_indicator_series(spy_bars) if spy_bars else {}
        spy_ind = spy_inds.get(latest_date) or (list(spy_inds.values())[-1] if spy_inds else None)
        regime = self.backtest_engine._classify_regime(spy_ind)
        if regime == "UNKNOWN":
            regime = "BULL_LOW_VOL"

        reports = self.research_agent.get_latest_reports(limit=8)
        compact_candidates = [
            {
                "ticker": r["ticker"],
                "company_name": r["company_name"],
                "sector": r["market_and_sector_context"]["sector"],
                "price": r["current_price"],
                "rs_20d_vs_spy_pct": r["relative_strength_vs_spy_20d"],
                "volume_ratio_20": r["volume_analysis"]["volume_ratio_20"],
                "rsi_14": (r.get("relevant_technical_indicators") or {}).get("rsi_14"),
                "consolidation_10d_pct": (r.get("relevant_technical_indicators") or {}).get("consolidation_range_10d_pct"),
                "suggested_strategy_family": r["suggested_strategy_family"],
                "composite_rank_score": r["composite_rank_score"],
                "current_bullish_thesis": r["bullish_thesis"],
                "current_bearish_thesis": r["bearish_thesis"],
            }
            for r in reports
        ]

        active_strats = self.registry.list_strategies(status=StrategyStatus.PAPER_TRADING.value)
        strat_summaries = [
            {
                "strategy_id": s.strategy_id,
                "version": s.version,
                "name": s.name,
                "strategy_family": s.strategy_family,
                "holding_period_max_days": s.holding_period_max_days,
                "entry_rules": s.entry_rules,
                "exit_rules": s.exit_rules,
                "backtest_metrics": {
                    k: (s.backtest_summary or {}).get(k)
                    for k in (
                        "total_return_pct",
                        "sharpe_ratio",
                        "deflated_sharpe_pct",
                        "profit_factor",
                        "max_drawdown_pct",
                        "win_rate_pct",
                        "trade_count",
                    )
                },
            }
            for s in active_strats
        ]

        ledger_sells = [
            t for t in self.paper_engine.get_trade_ledger(limit=30) if t.get("side") == "SELL"
        ][:8]

        import sys as _sys
        live_spy_px = round(float(spy_ind.close), 2) if spy_ind else None
        if "unittest" not in _sys.modules and hasattr(self.market_data, "fetch_live_quote_snapshots"):
            try:
                spy_snap = self.market_data.fetch_live_quote_snapshots([self.settings.benchmark_ticker])
                spy_info = spy_snap.get(self.settings.benchmark_ticker.upper()) or {}
                if spy_info.get("indicative_price"):
                    live_spy_px = round(float(spy_info["indicative_price"]), 2)
            except Exception:
                pass

        return {
            "calendar_date": date.today().isoformat(),
            "is_trading_day": USTradingCalendar.is_trading_day(date.today()),
            "is_market_open": USTradingCalendar.is_market_open(),
            "market_open_sgt": USTradingCalendar.market_open_sgt(),
            "market_close_sgt": USTradingCalendar.market_close_sgt(),
            "market_status_reason": USTradingCalendar.non_trading_reason(date.today()),
            "next_trading_day": USTradingCalendar.next_trading_day(
                date.today(), include_same_day=USTradingCalendar.is_trading_day(date.today())
            ),
            "session_date": latest_date,
            "market_regime": {
                "regime": regime,
                "spy_close": live_spy_px,
                "spy_last_daily_close": round(float(spy_ind.close), 2) if spy_ind else None,
                "spy_rsi_14": round(float(spy_ind.rsi_14), 2) if (spy_ind and spy_ind.rsi_14) else None,
                "spy_return_20d_pct": round(float(spy_ind.ret_20d_pct), 2) if (spy_ind and spy_ind.ret_20d_pct is not None) else None,
                "spy_volatility_20d_pct": round(float(spy_ind.realised_vol_20d_annualised), 2) if (spy_ind and spy_ind.realised_vol_20d_annualised is not None) else None,
            },
            "top_research_candidates": compact_candidates,
            "active_paper_strategies": strat_summaries,
            "paper_account_summary": self.paper_engine.get_account_summary(),
            "recent_closed_paper_trades": ledger_sells,
            "live_copilot_action_plan": self.live_copilot.get_daily_action_plan(
                as_of_date=trading_date, check_calendar_today=False
            ),
            "daily_workflow_status": daily_res.get("status", "COMPLETED") if isinstance(daily_res, dict) else "COMPLETED",
        }

    def apply_ide_ai_cycle(
        self,
        payload: Dict[str, Any],
        session_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply IDE AI Agent qualitative research updates and run multi-candidate strategy tournament."""
        import uuid
        from infrastructure.database.db import utc_now_iso

        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker)
        dt_str = session_date or payload.get("session_date") or (spy_bars[-1].bar_date if spy_bars else date.today().isoformat())
        now_iso = utc_now_iso()

        # 1. Enrich candidate research reports and catalyst table with IDE LLM's live web-search analysis
        research_updates = payload.get("research_updates") or []
        updated_tickers: List[str] = []
        for upd in research_updates:
            tkr = str(upd.get("ticker", "")).strip().upper()
            if not tkr:
                continue
            row = self.db.fetch_one(
                "SELECT report_id, report_json FROM research_reports WHERE ticker = ? ORDER BY as_of_date DESC, created_at DESC LIMIT 1",
                (tkr,),
            )
            if row:
                rep = json.loads(row["report_json"])
                if upd.get("bullish_thesis"):
                    rep["bullish_thesis"] = str(upd["bullish_thesis"])
                if upd.get("bearish_thesis"):
                    rep["bearish_thesis"] = str(upd["bearish_thesis"])
                if upd.get("catalyst_assessment"):
                    rep["catalyst_assessment"] = str(upd["catalyst_assessment"])
                if upd.get("main_risks") and isinstance(upd["main_risks"], list):
                    rep["main_risks"] = [str(x) for x in upd["main_risks"]]
                if upd.get("research_confidence_score") is not None:
                    rep["research_confidence_score"] = round(
                        max(0.1, min(0.95, float(upd["research_confidence_score"]))), 2
                    )
                self.db.execute(
                    "UPDATE research_reports SET report_json = ? WHERE report_id = ?",
                    (json.dumps(rep), row["report_id"]),
                )
                updated_tickers.append(tkr)

            # Also persist a structured MarketCatalyst record if catalyst_assessment or sentiment_score is provided
            cat_text = str(upd.get("catalyst_assessment") or upd.get("bullish_thesis") or "").strip()
            if cat_text:
                sent_val = float(upd.get("sentiment_score", 0.5))
                if upd.get("sentiment_score") is None and upd.get("research_confidence_score") is not None:
                    sent_val = round((float(upd["research_confidence_score"]) - 0.5) * 2.0, 2)
                self.db.execute(
                    """
                    INSERT INTO market_catalysts (
                        ticker, published_date, published_timestamp, catalyst_type,
                        headline, summary, sentiment_score, source_name, url
                    ) VALUES (?, ?, ?, 'IDE_AI_RESEARCH', ?, ?, ?, 'IDE AI Catalyst Engine', '')
                    """,
                    (
                        tkr,
                        dt_str,
                        now_iso,
                        cat_text[:140],
                        str(upd.get("bullish_thesis") or cat_text),
                        max(-1.0, min(1.0, sent_val)),
                    ),
                )

        # 2. Record optional AI Performance Analyst proposal
        prop_in = payload.get("analyst_proposal")
        recorded_proposal_id: Optional[str] = None
        if isinstance(prop_in, dict) and prop_in.get("proposed_hypothesis"):
            recorded_proposal_id = f"prop_ide_{dt_str.replace('-', '')}_{uuid.uuid4().hex[:6]}"
            target_sid = str(prop_in.get("target_strategy_id", "strat_momentum_trend"))
            self.db.execute(
                """
                INSERT INTO experiment_proposals (
                    proposal_id, session_date, target_strategy_id, identified_weakness,
                    market_regime, proposed_hypothesis, proposed_changes_json,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PROPOSED', ?)
                """,
                (
                    recorded_proposal_id,
                    dt_str,
                    target_sid,
                    str(prop_in.get("diagnosis_summary", "IDE LLM catalyst and attribution diagnosis.")),
                    str(prop_in.get("market_regime", "IDE_AI_ANALYSIS")),
                    str(prop_in["proposed_hypothesis"]),
                    json.dumps(prop_in.get("parameter_adjustments") or {}),
                    now_iso,
                ),
            )

        # 3. Evaluate AI-proposed StrategyConfig candidates in a 9-Gate Backtest & Walk-Forward Tournament
        candidate_specs = payload.get("candidate_strategies") or []
        tournament_results: List[Dict[str, Any]] = []
        for spec in candidate_specs:
            base_sid = str(spec.get("target_strategy_id", "strat_momentum_trend"))
            existing_versions = self.registry.list_strategies(strategy_id=base_sid)
            if not existing_versions:
                continue
            cand_strat = self.registry.create_new_version(
                base_strategy_id=base_sid,
                entry_rules_updates=spec.get("entry_rules_patch") or spec.get("entry_rules_updates") or {},
                exit_rules_updates=spec.get("exit_rules_patch") or spec.get("exit_rules_updates") or {},
                hypothesis_note=str(spec.get("hypothesis") or "IDE AI parameter hypothesis to maximize risk-adjusted P&L."),
            )
            self.registry.update_status(
                cand_strat.strategy_id,
                cand_strat.version,
                StrategyStatus.BACKTESTING,
                reason=f"IDE AI Tournament ({dt_str})",
            )
            pipeline = self.backtest_engine.run_in_sample_validation_oos_pipeline(cand_strat)
            full_bt = pipeline["full_period"]
            eval_rep = self.evaluator_agent.evaluate_pipeline_results(
                strategy=cand_strat,
                pipeline_results=pipeline,
                dataset_version=f"ds_ide_ai_{dt_str}",
                auto_transition=True,
            )
            self.registry.record_experiment(
                experiment_id=full_bt["experiment_id"],
                strategy_id=cand_strat.strategy_id,
                version=cand_strat.version,
                experiment_type="IDE_AI_TOURNAMENT",
                dataset_version=f"ds_ide_ai_{dt_str}",
                start_date=full_bt["start_date"],
                end_date=full_bt["end_date"],
                parameters={
                    "entry_rules": cand_strat.entry_rules,
                    "exit_rules": cand_strat.exit_rules,
                },
                metrics=full_bt["metrics"],
                equity_curve=full_bt["equity_curve"],
                trades=full_bt["trades"],
                evaluation_report=eval_rep.to_dict(),
                passed_promotion=eval_rep.promoted,
            )
            tournament_results.append(
                {
                    "strategy_id": cand_strat.strategy_id,
                    "version": cand_strat.version,
                    "hypothesis": cand_strat.hypothesis,
                    "promoted": eval_rep.promoted,
                    "new_status": eval_rep.new_status,
                    "decision_summary": eval_rep.decision_summary,
                    "metrics": {
                        k: full_bt["metrics"].get(k)
                        for k in (
                            "total_return_pct",
                            "sharpe_ratio",
                            "deflated_sharpe_pct",
                            "profit_factor",
                            "max_drawdown_pct",
                            "trade_count",
                        )
                    },
                }
            )

        if recorded_proposal_id and tournament_results:
            any_promoted = any(r["promoted"] for r in tournament_results)
            self.analyst_agent.mark_proposal_status(
                recorded_proposal_id, "PROMOTED" if any_promoted else "REJECTED"
            )

        active_paper_strats = self.registry.list_strategies(status=StrategyStatus.PAPER_TRADING.value)
        paper_ai_sync = {}
        if hasattr(self.paper_engine, "sync_ai_catalysts_to_paper_accounts"):
            paper_ai_sync = self.paper_engine.sync_ai_catalysts_to_paper_accounts(
                active_strategies=active_paper_strats,
                session_date=dt_str,
            )

        res_summary = {
            "session_date": dt_str,
            "research_tickers_enriched": updated_tickers,
            "recorded_proposal_id": recorded_proposal_id,
            "tournament_results": tournament_results,
            "paper_ai_sync": paper_ai_sync,
            "updated_copilot_action_plan": self.live_copilot.get_daily_action_plan(
                as_of_date=session_date, check_calendar_today=False
            ),
        }
        self.db.execute(
            """
            INSERT INTO job_executions (
                job_run_id, job_name, idempotency_key, status, started_at, completed_at, summary_json
            ) VALUES (?, 'ide_ai_cycle', ?, 'COMPLETED', ?, ?, ?)
            ON CONFLICT(idempotency_key) DO UPDATE SET
                status='COMPLETED', completed_at=excluded.completed_at, summary_json=excluded.summary_json
            """,
            (
                f"job_ide_{uuid.uuid4().hex[:10]}",
                f"ide_ai_cycle:{dt_str}:{uuid.uuid4().hex[:6]}",
                now_iso,
                now_iso,
                json.dumps(
                    {
                        "session_date": dt_str,
                        "research_tickers_enriched": updated_tickers,
                        "candidates_tested": len(tournament_results),
                        "promoted_count": sum(1 for r in tournament_results if r["promoted"]),
                    }
                ),
            ),
        )
        return res_summary

