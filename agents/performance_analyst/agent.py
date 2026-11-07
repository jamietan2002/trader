"""Performance Analyst Agent (`performance_analyst`).

Responsibilities:
- Review the paper account and strategy performance after each trading session.
- Analyse daily portfolio P&L, individual trade executions, strategy-level attribution,
  winning and losing patterns, market regime, sector exposure, drawdowns, and slippage.
- Identify recurring weaknesses and generate structured `ExperimentProposal` artefacts
  rather than directly mutating active live/paper strategy configurations.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent, LLMProvider, validate_required_fields
from core.execution.paper_broker import PaperTradingEngine
from core.strategies.registry import StrategyRegistry
from infrastructure.configuration.settings import Settings
from infrastructure.database.db import DatabaseManager, utc_now_iso


PERFORMANCE_REVIEW_SCHEMA: Dict[str, Any] = {
    "session_date": str,
    "account_equity": (int, float),
    "daily_return_pct": (int, float),
    "cumulative_return_pct": (int, float),
    "current_drawdown_pct": (int, float),
    "strategy_attribution": dict,
    "slippage_and_cost_summary": dict,
    "identified_weaknesses": list,
    "experiment_proposals": list,
}


@dataclass(frozen=True)
class ExperimentProposal:
    proposal_id: str
    session_date: str
    target_strategy_id: str
    identified_weakness: str
    market_regime: str
    proposed_hypothesis: str
    proposed_changes: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PerformanceAnalystAgent(BaseAgent):
    """Post-session Performance Analyst Agent that audits paper performance and proposes experiments."""

    role_name = "performance_analyst"

    def __init__(
        self,
        settings: Settings,
        db: DatabaseManager,
        paper_engine: PaperTradingEngine,
        registry: StrategyRegistry,
        llm: Optional[LLMProvider] = None,
    ) -> None:
        super().__init__(settings, llm)
        self.db = db
        self.paper_engine = paper_engine
        self.registry = registry

    def review_session_performance(self, session_date: str, current_regime: str = "BULL_LOW_VOL") -> Dict[str, Any]:
        """Analyse portfolio state, strategy attribution, slippage, and generate experiment proposals."""
        self.assert_permission("read_paper_account")
        self.assert_permission("read_trade_ledger")
        self.assert_permission("read_strategy_performance")
        self.assert_permission("write_experiment_proposal")

        summary = self.paper_engine.get_account_summary()
        ledger = self.paper_engine.get_trade_ledger(limit=500)
        snapshots = self.paper_engine.get_portfolio_snapshots()
        latest_snap = snapshots[-1] if snapshots else {}

        # Strategy-level attribution from trade ledger
        attribution: Dict[str, Dict[str, Any]] = {}
        total_comm = 0.0
        total_slippage = 0.0

        for entry in ledger:
            sid = entry["strategy_id"]
            grp = attribution.setdefault(
                sid,
                {
                    "executions": 0,
                    "sell_closes": 0,
                    "wins": 0,
                    "losses": 0,
                    "realised_pnl": 0.0,
                    "commissions_usd": 0.0,
                    "slippage_usd": 0.0,
                },
            )
            grp["executions"] += 1
            comm = float(entry["commission_usd"])
            slip = float(entry["slippage_usd"])
            pnl = float(entry["realised_pnl"])
            grp["commissions_usd"] = round(grp["commissions_usd"] + comm, 2)
            grp["slippage_usd"] = round(grp["slippage_usd"] + slip, 2)
            total_comm += comm
            total_slippage += slip

            if entry["side"] == "SELL":
                grp["sell_closes"] += 1
                grp["realised_pnl"] = round(grp["realised_pnl"] + pnl, 2)
                if pnl > 0:
                    grp["wins"] += 1
                else:
                    grp["losses"] += 1

        weaknesses: List[str] = []
        proposals: List[ExperimentProposal] = []

        for sid, stats in attribution.items():
            closes = stats["sell_closes"]
            wr = (stats["wins"] / closes) if closes > 0 else 1.0
            if closes >= 2 and (stats["realised_pnl"] < 0 or wr < 0.45):
                weakness_desc = (
                    f"Strategy '{sid}' has {wr * 100:.0f}% win rate and ${stats['realised_pnl']:+,.2f} "
                    f"realised P&L across {closes} closed paper trades during {current_regime} conditions."
                )
                weaknesses.append(weakness_desc)
                proposals.append(
                    ExperimentProposal(
                        proposal_id=f"prop_{session_date}_{uuid.uuid4().hex[:8]}",
                        session_date=session_date,
                        target_strategy_id=sid,
                        identified_weakness=weakness_desc,
                        market_regime=current_regime,
                        proposed_hypothesis=(
                            f"The {sid} strategy has suffered losses in {current_regime} conditions. "
                            "Test a market-regime filter based on SPY's 50-day moving average and a "
                            "22% realised volatility cap with a slightly tighter 1.8x ATR stop."
                        ),
                        proposed_changes={
                            "entry_rules": {
                                "require_spy_above_sma50": True,
                                "max_spy_realised_vol_20d": 22.0,
                            },
                            "exit_rules": {
                                "stop_loss_atr_mult": 1.8,
                            },
                        },
                    )
                )

        if not proposals:
            # Always provide a constructive next-experiment hypothesis for continuous improvement loop
            proposals.append(
                ExperimentProposal(
                    proposal_id=f"prop_{session_date}_{uuid.uuid4().hex[:8]}",
                    session_date=session_date,
                    target_strategy_id="strat_momentum_trend",
                    identified_weakness=(
                        "Momentum strategy performs well in trending regimes but can experience give-back "
                        "during sideways consolidation phases."
                    ),
                    market_regime=current_regime,
                    proposed_hypothesis=(
                        "The momentum strategy is performing well in strong market regimes but can suffer "
                        "whipsaws in sideways conditions. Test a market-regime filter based on SPY's 50-day "
                        "moving average and realised volatility <= 24%."
                    ),
                    proposed_changes={
                        "entry_rules": {
                            "require_spy_above_sma50": True,
                            "max_spy_realised_vol_20d": 24.0,
                            "min_rs_vs_spy_20d": 2.2,
                        },
                        "exit_rules": {
                            "trailing_stop_atr_mult": 2.2,
                        },
                    },
                )
            )

        now_iso = utc_now_iso()
        for prop in proposals:
            self.db.execute(
                """
                INSERT INTO experiment_proposals (
                    proposal_id, session_date, target_strategy_id,
                    identified_weakness, market_regime, proposed_hypothesis,
                    proposed_changes_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PROPOSED', ?)
                """,
                (
                    prop.proposal_id,
                    prop.session_date,
                    prop.target_strategy_id,
                    prop.identified_weakness,
                    prop.market_regime,
                    prop.proposed_hypothesis,
                    json.dumps(prop.proposed_changes),
                    now_iso,
                ),
            )

        review_payload: Dict[str, Any] = {
            "session_date": session_date,
            "account_equity": summary["total_equity"],
            "daily_return_pct": float(latest_snap.get("daily_return_pct", 0.0)),
            "cumulative_return_pct": summary["total_return_pct"],
            "current_drawdown_pct": summary["current_drawdown_pct"],
            "strategy_attribution": attribution,
            "slippage_and_cost_summary": {
                "total_commissions_usd": round(total_comm, 2),
                "total_slippage_usd": round(total_slippage, 2),
                "total_executions": len(ledger),
            },
            "identified_weaknesses": weaknesses,
            "experiment_proposals": [p.to_dict() for p in proposals],
        }

        validate_required_fields(review_payload, PERFORMANCE_REVIEW_SCHEMA, "PerformanceReviewReport")
        return review_payload

    def list_proposals(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM experiment_proposals ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["proposed_changes"] = json.loads(r["proposed_changes_json"])
            out.append(d)
        return out

