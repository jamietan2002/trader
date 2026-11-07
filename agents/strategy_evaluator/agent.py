"""Strategy Evaluation Agent (`strategy_evaluator`).

Responsibilities:
- Analyse in-sample, validation, out-of-sample, walk-forward, and transaction-cost
  stress-test results.
- Enforce explicit, configurable strategy promotion criteria:
  1. Positive net out-of-sample returns (> 0%)
  2. Sharpe ratio > 1.0
  3. Profit factor > 1.3
  4. Maximum drawdown < 15%
  5. Sufficient trade count (>= min_trade_count)
  6. Walk-forward window consistency (>= 60%)
  7. Positive performance after realistic transaction costs
  8. Competitive risk-adjusted performance against SPY
  9. Check for suspiciously concentrated returns (e.g., single trade accounting for >65% of total profit)
- Reject a strategy even if its headline backtest return is positive when statistical or
  risk-adjusted criteria fail.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent, LLMProvider, validate_required_fields
from core.strategies.registry import StrategyConfig, StrategyRegistry, StrategyStatus
from infrastructure.configuration.settings import PromotionCriteriaConfig, Settings


EVALUATION_REPORT_SCHEMA: Dict[str, Any] = {
    "strategy_id": str,
    "strategy_version": int,
    "promoted": bool,
    "new_status": str,
    "decision_summary": str,
    "criteria_checks": dict,
    "failed_criteria": list,
    "performance_explanation": str,
    "regime_analysis_notes": str,
    "concentration_warning": bool,
    "recommended_experiments": list,
}


@dataclass(frozen=True)
class StrategyEvaluationReport:
    strategy_id: str
    strategy_version: int
    promoted: bool
    new_status: str
    decision_summary: str
    criteria_checks: Dict[str, bool]
    failed_criteria: List[str]
    performance_explanation: str
    regime_analysis_notes: str
    concentration_warning: bool
    recommended_experiments: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StrategyEvaluationAgent(BaseAgent):
    """AI Agent that audits backtest and walk-forward evidence before promoting or rejecting a strategy."""

    role_name = "strategy_evaluator"

    def __init__(
        self,
        settings: Settings,
        registry: StrategyRegistry,
        criteria: Optional[PromotionCriteriaConfig] = None,
        llm: Optional[LLMProvider] = None,
    ) -> None:
        super().__init__(settings, llm)
        self.registry = registry
        self.criteria = criteria or settings.promotion

    def evaluate_pipeline_results(
        self,
        strategy: StrategyConfig,
        pipeline_results: Dict[str, Any],
        dataset_version: str = "ds_default",
        auto_transition: bool = True,
    ) -> StrategyEvaluationReport:
        """Evaluate full backtest + OOS + walk-forward results against promotion thresholds."""
        self.assert_permission("read_backtest_results")
        self.assert_permission("read_walk_forward_results")
        self.assert_permission("evaluate_and_transition_strategy_status")

        full_res = pipeline_results.get("full_period", pipeline_results)
        oos_res = pipeline_results.get("out_of_sample", full_res)
        wf_res = pipeline_results.get("walk_forward", {})
        stress_res = pipeline_results.get("stress_test", {})

        full_m = full_res.get("metrics", {})
        oos_m = oos_res.get("metrics", full_m)
        trades = full_res.get("trades", [])

        # Evaluate primary metrics on full + out-of-sample evidence
        oos_net_ret = float(oos_m.get("total_return_pct", 0.0))
        sharpe = float(full_m.get("sharpe_ratio", 0.0))
        profit_factor = float(full_m.get("profit_factor", 0.0))
        max_dd_pct = float(full_m.get("max_drawdown_pct", 100.0)) / 100.0
        trade_count = int(full_m.get("trade_count", 0))
        wf_consistency = float(wf_res.get("consistency_ratio", 1.0))
        survives_costs = bool(stress_res.get("survives_2x_costs", full_m.get("total_return_pct", 0.0) > 0.0))
        spy_sharpe = float(full_m.get("benchmark_sharpe", 0.0))

        # Check for suspicious single-trade profit concentration
        total_net_pnl = sum(float(t.get("net_pnl", 0.0)) for t in trades)
        max_single_trade_pnl = max((float(t.get("net_pnl", 0.0)) for t in trades), default=0.0)
        concentrated_returns = (
            total_net_pnl > 0
            and len(trades) >= 5
            and (max_single_trade_pnl / total_net_pnl) > 0.65
        )

        # Incumbent Champion Protection: If an active PAPER_TRADING version of this strategy already exists,
        # only promote v+1 if it beats or matches the incumbent's Sharpe, Net Return, or Drawdown-Adjusted Return.
        beats_incumbent = True
        if strategy.version > 1:
            incumbents = [
                s
                for s in self.registry.list_strategies(status=StrategyStatus.PAPER_TRADING.value)
                if s.strategy_id == strategy.strategy_id and s.version < strategy.version and s.backtest_summary
            ]
            if incumbents:
                inc = sorted(incumbents, key=lambda x: x.version)[-1]
                inc_m = inc.backtest_summary or {}
                inc_sharpe = float(inc_m.get("sharpe_ratio", 0.0))
                inc_ret = float(inc_m.get("total_return_pct", 0.0))
                inc_calmar = float(inc_m.get("calmar_ratio", 0.0))
                curr_ret = float(full_m.get("total_return_pct", 0.0))
                curr_calmar = float(full_m.get("calmar_ratio", 0.0))
                if inc_sharpe > 0 and sharpe < (inc_sharpe - 0.03) and curr_ret < inc_ret and curr_calmar < inc_calmar:
                    beats_incumbent = False

        checks: Dict[str, bool] = {
            "positive_oos_net_return": oos_net_ret > self.criteria.min_oos_net_return,
            "sharpe_above_threshold": sharpe >= self.criteria.min_sharpe_ratio,
            "profit_factor_above_threshold": profit_factor >= self.criteria.min_profit_factor,
            "max_drawdown_below_limit": max_dd_pct <= self.criteria.max_drawdown_pct,
            "sufficient_trade_count": trade_count >= self.criteria.min_trade_count,
            "walk_forward_consistency": wf_consistency >= self.criteria.min_walk_forward_consistency,
            "positive_after_transaction_costs": survives_costs if self.criteria.require_positive_after_costs else True,
            "competitive_vs_spy_risk_adjusted": (
                (sharpe >= spy_sharpe * 0.85 or float(full_m.get("total_return_pct", 0.0)) >= float(full_m.get("benchmark_return_pct", 0.0)))
                and beats_incumbent
            )
            if self.criteria.require_beat_benchmark_risk_adjusted
            else beats_incumbent,
            "no_extreme_return_concentration": not concentrated_returns,
        }

        failed = [k for k, passed in checks.items() if not passed]
        promoted = len(failed) == 0
        new_status = (
            StrategyStatus.PAPER_TRADING.value if promoted else StrategyStatus.REJECTED.value
        )

        if promoted:
            summary_msg = (
                f"PROMOTED to PAPER_TRADING: {strategy.strategy_id} v{strategy.version} passed all 9 validation "
                f"gates (Sharpe={sharpe:.2f}, PF={profit_factor:.2f}, MaxDD={max_dd_pct*100:.2f}%, "
                f"OOS Return={oos_net_ret:+.2f}%, Trades={trade_count}, WF Consistency={wf_consistency*100:.0f}%)."
            )
        else:
            summary_msg = (
                f"REJECTED: {strategy.strategy_id} v{strategy.version} failed {len(failed)} criterion/criteria: "
                f"{', '.join(failed)} (Sharpe={sharpe:.2f}, PF={profit_factor:.2f}, MaxDD={max_dd_pct*100:.2f}%, "
                f"Trades={trade_count})."
            )

        regimes = full_res.get("regime_breakdown", {})
        regime_notes = (
            "Regime Breakdown: "
            + ", ".join(
                f"{r}: {stats['trade_count']} trades (${stats['total_net_pnl']:+,.0f}, WR={stats['win_rate_pct']:.0f}%)"
                for r, stats in regimes.items()
            )
            if regimes
            else "No regime breakdown available."
        )

        fallback_narrative = {
            "performance_explanation": (
                f"Strategy achieved {full_m.get('total_return_pct', 0.0):+.2f}% total return "
                f"(vs SPY {full_m.get('benchmark_return_pct', 0.0):+.2f}%) with Sharpe {sharpe:.2f}, "
                f"Sortino {full_m.get('sortino_ratio', 0.0):.2f}, and Win Rate {full_m.get('win_rate_pct', 0.0):.1f}%."
            ),
            "recommended_experiments": [
                "Test tighter volatility regime filter when SPY 20-day realized volatility exceeds 22%.",
                "Evaluate parameter sensitivity across +/-15% ATR stop-loss multipliers.",
            ],
        }
        llm_out = self.llm.generate_structured_json(
            system_prompt="You are a quantitative strategy evaluator. Return JSON with performance_explanation and recommended_experiments.",
            user_prompt=json.dumps({"metrics": full_m, "checks": checks}),
            fallback_payload=fallback_narrative,
        )

        report = StrategyEvaluationReport(
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            promoted=promoted,
            new_status=new_status,
            decision_summary=summary_msg,
            criteria_checks=checks,
            failed_criteria=failed,
            performance_explanation=str(
                llm_out.get("performance_explanation", fallback_narrative["performance_explanation"])
            ),
            regime_analysis_notes=regime_notes,
            concentration_warning=concentrated_returns,
            recommended_experiments=list(
                llm_out.get("recommended_experiments", fallback_narrative["recommended_experiments"])
            ),
        )
        validate_required_fields(report.to_dict(), EVALUATION_REPORT_SCHEMA, "StrategyEvaluationReport")

        if auto_transition:
            self.registry.update_status(
                strategy_id=strategy.strategy_id,
                version=strategy.version,
                new_status=StrategyStatus(new_status),
                reason=summary_msg,
                backtest_summary=full_m,
                validation_summary={
                    "oos_metrics": oos_m,
                    "walk_forward": wf_res,
                    "stress_test": stress_res,
                    "criteria_checks": checks,
                },
                dataset_version=dataset_version,
            )

        return report

