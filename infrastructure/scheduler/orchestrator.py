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
from core.execution.paper_broker import PaperTradingEngine
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
        end_date: str = "2025-06-30",
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

        # 1. Pre-Market: Market Research Scan
        pre_market_res = self.run_idempotent_job(
            job_name="daily_pre_market",
            idempotency_key=f"daily_pre_market:{trading_date}",
            fn=lambda: self.research_agent.run_market_scan(as_of_date=trading_date, top_n=8),
            force=force,
        )

        # 2. Market Hours: Paper Trading Execution across approved PAPER_TRADING strategies
        active_strats = self.registry.list_strategies(status=StrategyStatus.PAPER_TRADING.value)
        market_exec_res = self.run_idempotent_job(
            job_name="daily_market_execution",
            idempotency_key=f"daily_market_execution:{trading_date}",
            fn=lambda: self.paper_engine.run_trading_session_for_strategies(
                active_strategies=active_strats,
                trading_date=trading_date,
            ),
            force=force,
        )

        # 3. Post-Close: Reconciliation, Risk Audit, and Performance Analyst Review
        def _post_close_fn() -> Dict[str, Any]:
            risk_audit = self.risk_agent.audit_portfolio_health(eval_date=trading_date)
            perf_review = self.analyst_agent.review_session_performance(
                session_date=trading_date,
                current_regime="BULL_LOW_VOL",
            )
            now_op = datetime.now(self.settings.operator_tz).strftime("%Y-%m-%d %H:%M:%S %Z")
            return {
                "trading_date": trading_date,
                "operator_report_timestamp": now_op,
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
            proposals = self.analyst_agent.list_proposals(limit=5)
            latest_proposal = proposals[0] if (proposals and not preferred_family) else None

            candidate_strat = self.discovery_agent.propose_strategy_from_research(
                research_candidates=latest_reports,
                preferred_family=preferred_family,
                analyst_proposal=latest_proposal,
            )

            self.registry.update_status(
                candidate_strat.strategy_id,
                candidate_strat.version,
                StrategyStatus.BACKTESTING,
                reason=f"Weekly experiment cycle ({week_ending_date})",
            )

            pipeline = self.backtest_engine.run_in_sample_validation_oos_pipeline(candidate_strat)
            full_bt = pipeline["full_period"]

            eval_report = self.evaluator_agent.evaluate_pipeline_results(
                strategy=candidate_strat,
                pipeline_results=pipeline,
                dataset_version=f"ds_weekly_{week_ending_date}",
                auto_transition=True,
            )

            self.registry.record_experiment(
                experiment_id=full_bt["experiment_id"],
                strategy_id=candidate_strat.strategy_id,
                version=candidate_strat.version,
                experiment_type="WEEKLY_DISCOVERY",
                dataset_version=f"ds_weekly_{week_ending_date}",
                start_date=full_bt["start_date"],
                end_date=full_bt["end_date"],
                parameters={
                    "entry_rules": candidate_strat.entry_rules,
                    "exit_rules": candidate_strat.exit_rules,
                },
                metrics=full_bt["metrics"],
                equity_curve=full_bt["equity_curve"],
                trades=full_bt["trades"],
                evaluation_report=eval_report.to_dict(),
                passed_promotion=eval_report.promoted,
            )

            return {
                "week_ending_date": week_ending_date,
                "candidate_strategy_id": candidate_strat.strategy_id,
                "candidate_version": candidate_strat.version,
                "strategy_family": candidate_strat.strategy_family,
                "promoted": eval_report.promoted,
                "new_status": eval_report.new_status,
                "decision_summary": eval_report.decision_summary,
                "metrics": full_bt["metrics"],
            }

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

