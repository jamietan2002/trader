"""Strategy Discovery Agent (`strategy_architect`).

Responsibilities:
- Convert research findings, market observations, and Performance Analyst proposals
  into testable, falsifiable quantitative hypotheses.
- Output strictly validated, machine-readable `StrategyConfig` objects (never allowing
  natural-language descriptions to bypass the structured strategy engine).
- Register new candidate strategies or incremented versions in the `StrategyRegistry`
  with status `DRAFT` for deterministic backtesting.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Sequence

from agents.base import BaseAgent, LLMProvider, validate_required_fields
from core.strategies.registry import (
    StrategyConfig,
    StrategyFamily,
    StrategyRegistry,
    StrategyStatus,
)
from infrastructure.configuration.settings import Settings


STRATEGY_HYPOTHESIS_SCHEMA: Dict[str, Any] = {
    "strategy_id": str,
    "name": str,
    "strategy_family": str,
    "observable_phenomenon": str,
    "hypothesis": str,
    "invalidation_conditions": str,
    "target_market_regimes": list,
    "holding_period_min_days": int,
    "holding_period_max_days": int,
    "universe": list,
    "required_indicators": list,
    "entry_rules": dict,
    "exit_rules": dict,
    "risk_params": dict,
}


class StrategyDiscoveryAgent(BaseAgent):
    """AI Agent that synthesizes research reports into machine-readable StrategyConfigs."""

    role_name = "strategy_architect"

    def __init__(
        self,
        settings: Settings,
        registry: StrategyRegistry,
        llm: Optional[LLMProvider] = None,
    ) -> None:
        super().__init__(settings, llm)
        self.registry = registry

    def propose_strategy_from_research(
        self,
        research_candidates: Sequence[Dict[str, Any]],
        preferred_family: Optional[str] = None,
        analyst_proposal: Optional[Dict[str, Any]] = None,
    ) -> StrategyConfig:
        """Generate a falsifiable quantitative hypothesis and register as a DRAFT StrategyConfig."""
        self.assert_permission("read_research_reports")
        self.assert_permission("read_strategy_registry")
        self.assert_permission("register_draft_strategy")

        # Determine dominant strategy family from top research candidates if not specified
        if preferred_family:
            family = preferred_family
        elif research_candidates:
            family_counts: Dict[str, int] = {}
            for c in research_candidates[:5]:
                fam = c.get("suggested_strategy_family", StrategyFamily.MOMENTUM_TREND.value)
                family_counts[fam] = family_counts.get(fam, 0) + 1
            family = max(family_counts.keys(), key=lambda k: family_counts[k])
        else:
            family = StrategyFamily.MOMENTUM_TREND.value

        universe = [
            "AAPL", "MSFT", "NVDA", "AMD", "AMZN", "TSLA", "META",
            "JPM", "GS", "LLY", "UNH", "XOM", "CAT", "AVGO",
        ]

        # If evolving an existing strategy from a Performance Analyst proposal, increment its version
        if analyst_proposal and analyst_proposal.get("target_strategy_id"):
            target_id = str(analyst_proposal["target_strategy_id"])
            existing_versions = self.registry.list_strategies(strategy_id=target_id)
            if existing_versions:
                changes = analyst_proposal.get("proposed_changes", {})
                return self.registry.create_new_version(
                    base_strategy_id=target_id,
                    entry_rules_updates=changes.get("entry_rules"),
                    exit_rules_updates=changes.get("exit_rules"),
                    hypothesis_note=analyst_proposal.get("proposed_hypothesis", "Regime-filtered refinement"),
                )

        fallback_spec = self._build_family_template(family, universe)
        llm_payload = self.llm.generate_structured_json(
            system_prompt=(
                "You are a quantitative strategy architect. Produce a machine-readable JSON strategy "
                "configuration matching STRATEGY_HYPOTHESIS_SCHEMA."
            ),
            user_prompt=json.dumps(
                {
                    "requested_family": family,
                    "top_candidates": [
                        {
                            "ticker": c.get("ticker"),
                            "rs_20d": c.get("relative_strength_vs_spy_20d"),
                            "suggested_family": c.get("suggested_strategy_family"),
                        }
                        for c in research_candidates[:5]
                    ],
                }
            ),
            fallback_payload=fallback_spec,
        )

        validate_required_fields(llm_payload, STRATEGY_HYPOTHESIS_SCHEMA, "StrategyHypothesisPayload")

        strat_id = str(llm_payload["strategy_id"])
        existing = self.registry.list_strategies(strategy_id=strat_id)
        next_version = (max(s.version for s in existing) + 1) if existing else 1

        config = StrategyConfig(
            strategy_id=strat_id,
            version=next_version,
            name=str(llm_payload["name"]),
            strategy_family=str(llm_payload["strategy_family"]),
            status=StrategyStatus.DRAFT.value,
            hypothesis=str(llm_payload["hypothesis"]),
            observable_phenomenon=str(llm_payload["observable_phenomenon"]),
            invalidation_conditions=str(llm_payload["invalidation_conditions"]),
            target_market_regimes=list(llm_payload["target_market_regimes"]),
            holding_period_min_days=int(llm_payload["holding_period_min_days"]),
            holding_period_max_days=int(llm_payload["holding_period_max_days"]),
            universe=list(llm_payload["universe"]),
            required_indicators=list(llm_payload["required_indicators"]),
            entry_rules=dict(llm_payload["entry_rules"]),
            exit_rules=dict(llm_payload["exit_rules"]),
            risk_params=dict(llm_payload["risk_params"]),
        )
        return self.registry.register_strategy(config)

    @staticmethod
    def _build_family_template(family: str, universe: List[str]) -> Dict[str, Any]:
        if family == StrategyFamily.MEAN_REVERSION.value:
            return {
                "strategy_id": "strat_mean_reversion_bb",
                "name": "Bollinger & RSI Short-Term Mean Reversion",
                "strategy_family": StrategyFamily.MEAN_REVERSION.value,
                "observable_phenomenon": (
                    "Liquid large-cap stocks in long-term uptrends (Close > SMA200) experiencing short-term "
                    "liquidity shocks below their lower 20-day Bollinger Band and RSI(14) <= 35 tend to revert "
                    "toward their 20-day mean over 3-8 trading days."
                ),
                "hypothesis": (
                    "Buying oversold pullbacks (RSI14 <= 35, Close <= 1.01 * LowerBB20) in structurally healthy "
                    "large-cap equities yields positive risk-adjusted returns with controlled drawdown."
                ),
                "invalidation_conditions": (
                    "Structural breakdown below 2.0x ATR stop-loss or persistent negative earnings shock."
                ),
                "target_market_regimes": ["SIDEWAYS_CHOPPY", "BULL_LOW_VOL"],
                "holding_period_min_days": 3,
                "holding_period_max_days": 8,
                "universe": universe,
                "required_indicators": ["rsi_14", "bb_lower_20", "sma_20", "sma_200", "atr_14"],
                "entry_rules": {
                    "max_rsi_14": 36.0,
                    "require_above_sma200": True,
                },
                "exit_rules": {
                    "stop_loss_atr_mult": 2.0,
                    "take_profit_atr_mult": 3.0,
                    "exit_rsi_above": 62.0,
                },
                "risk_params": {
                    "risk_per_trade_pct": 0.008,
                    "max_position_exposure_pct": 0.12,
                },
            }

        if family == StrategyFamily.SECTOR_ROTATION.value:
            return {
                "strategy_id": "strat_sector_rotation_leaders",
                "name": "Top-Sector Relative Strength Leaders",
                "strategy_family": StrategyFamily.SECTOR_ROTATION.value,
                "observable_phenomenon": (
                    "Institutional capital rotates across GICS sectors in multi-week waves; selecting the "
                    "strongest relative-strength stocks within the top-ranked sectors captures dual tailwinds."
                ),
                "hypothesis": (
                    "Entering equities with 20d RS vs SPY >= 3.0% inside top-2 ranked sectors when SPY > SMA50 "
                    "outperforms passive SPY exposure on a Sharpe-adjusted basis over 5-14 trading days."
                ),
                "invalidation_conditions": (
                    "Sector loses leadership rank or stock closes below SMA20 / 2.0x ATR stop."
                ),
                "target_market_regimes": ["BULL_TREND", "SECTOR_ROTATION"],
                "holding_period_min_days": 5,
                "holding_period_max_days": 14,
                "universe": universe,
                "required_indicators": ["rs_vs_spy_20d", "sma_20", "sma_50", "atr_14"],
                "entry_rules": {
                    "max_sector_rank": 2,
                    "min_rs_vs_spy_20d": 3.0,
                    "require_spy_above_sma50": True,
                },
                "exit_rules": {
                    "stop_loss_atr_mult": 2.0,
                    "take_profit_atr_mult": 3.8,
                    "trailing_stop_atr_mult": 2.3,
                    "exit_below_sma20": True,
                },
                "risk_params": {
                    "risk_per_trade_pct": 0.01,
                    "max_position_exposure_pct": 0.15,
                },
            }

        # Default adaptive momentum variant with regime filter
        return {
            "strategy_id": f"strat_adaptive_momentum_{uuid.uuid4().hex[:4]}",
            "name": "Regime-Filtered Relative Strength Swing",
            "strategy_family": StrategyFamily.MOMENTUM_TREND.value,
            "observable_phenomenon": (
                "High relative-strength equities with volume expansion and SPY regime filter avoid "
                "choppy market whipsaws while capturing strong 4-12 day momentum swings."
            ),
            "hypothesis": (
                "Filtering momentum entries for SPY > SMA50 and SPY 20d realized volatility <= 24% "
                "improves Sortino and Calmar ratios relative to unfiltered trend following."
            ),
            "invalidation_conditions": (
                "Close drops below SMA20 or 2.0x ATR stop-loss is triggered."
            ),
            "target_market_regimes": ["BULL_LOW_VOL", "BULL_HIGH_VOL"],
            "holding_period_min_days": 4,
            "holding_period_max_days": 12,
            "universe": universe,
            "required_indicators": ["sma_20", "sma_50", "rsi_14", "atr_14", "rs_vs_spy_20d", "volume_ratio_20"],
            "entry_rules": {
                "min_rs_vs_spy_20d": 2.2,
                "min_ret_20d_pct": 3.0,
                "min_volume_ratio_20": 1.10,
                "min_rsi_14": 54.0,
                "max_rsi_14": 76.0,
                "require_spy_above_sma50": True,
                "max_spy_realised_vol_20d": 24.0,
            },
            "exit_rules": {
                "stop_loss_atr_mult": 2.0,
                "take_profit_atr_mult": 3.8,
                "trailing_stop_atr_mult": 2.3,
                "exit_below_sma20": True,
            },
            "risk_params": {
                "risk_per_trade_pct": 0.01,
                "max_position_exposure_pct": 0.15,
            },
        }

