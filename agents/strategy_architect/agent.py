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
                    "Institutional dip-buying at the 20-day moving average in top relative-strength uptrends "
                    "creates repeatable mean-reversion swings without catching falling knives."
                ),
                "hypothesis": (
                    "Buying value-zone pullbacks near SMA20 / Lower Bollinger Band (50 <= RSI14 <= 74, RS20d >= 1.5%) "
                    "in structurally aligned uptrends (Close > SMA200, SMA20 > SMA50) captures high-win-rate swing rebounds."
                ),
                "invalidation_conditions": (
                    "Structural breakdown below 1.9x ATR stop-loss or RSI14 overbought exhaustion >= 78."
                ),
                "target_market_regimes": ["SIDEWAYS_CHOPPY", "BULL_LOW_VOL", "BULL_TREND"],
                "holding_period_min_days": 3,
                "holding_period_max_days": 12,
                "universe": universe,
                "required_indicators": ["rsi_14", "bb_lower_20", "sma_20", "sma_50", "sma_200", "atr_14", "rs_vs_spy_20d"],
                "entry_rules": {
                    "max_rsi_14": 74.0,
                    "min_rsi_14": 50.0,
                    "min_rs_vs_spy_20d": 1.5,
                    "max_dist_above_sma20_pct": 8.0,
                    "require_above_sma200": True,
                    "require_sma20_above_sma50": True,
                    "require_spy_above_sma50": True,
                },
                "exit_rules": {
                    "stop_loss_atr_mult": 1.9,
                    "take_profit_atr_mult": 4.0,
                    "trailing_stop_atr_mult": 2.4,
                    "exit_rsi_above": 78.0,
                },
                "risk_params": {
                    "risk_per_trade_pct": 0.01,
                    "max_position_exposure_pct": 0.15,
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
                    "Entering equities with 20d RS vs SPY >= 2.8% inside top-3 ranked sectors when SPY > SMA50 "
                    "outperforms passive SPY exposure across both full-period and out-of-sample regimes."
                ),
                "invalidation_conditions": (
                    "Sector loses leadership rank or stock closes below SMA20 / 2.0x ATR stop."
                ),
                "target_market_regimes": ["BULL_TREND", "SECTOR_ROTATION"],
                "holding_period_min_days": 4,
                "holding_period_max_days": 12,
                "universe": universe,
                "required_indicators": ["rs_vs_spy_20d", "sma_20", "sma_50", "atr_14", "rsi_14"],
                "entry_rules": {
                    "max_sector_rank": 3,
                    "min_rs_vs_spy_20d": 2.8,
                    "min_ret_20d_pct": 2.5,
                    "min_rsi_14": 50.0,
                    "max_rsi_14": 76.0,
                    "require_spy_above_sma50": True,
                },
                "exit_rules": {
                    "stop_loss_atr_mult": 2.0,
                    "take_profit_atr_mult": 4.0,
                    "trailing_stop_atr_mult": 2.4,
                    "exit_below_sma20": True,
                },
                "risk_params": {
                    "risk_per_trade_pct": 0.01,
                    "max_position_exposure_pct": 0.15,
                },
            }

        if family == StrategyFamily.BEARISH_BREAKDOWN.value:
            return {
                "strategy_id": "strat_bearish_breakdown",
                "name": "Structural Breakdown & Relative Weakness Short",
                "strategy_family": StrategyFamily.BEARISH_BREAKDOWN.value,
                "observable_phenomenon": (
                    "Institutional distribution below 20-day support in laggards underperforming SPY "
                    "produces multi-day downside continuation swings with negative drift."
                ),
                "hypothesis": (
                    "Shorting liquid, easy-to-borrow equities breaking below 20d structural support "
                    "(Close < SMA50, 20d RS vs SPY <= -3.0%, 26 <= RSI14 <= 52, Vol >= 1.15x) "
                    "generates uncorrelated bear-market and dispersion alpha."
                ),
                "invalidation_conditions": (
                    "Short-squeeze reclaim above SMA20 + 0.5x ATR, 1.8x ATR hard buy-to-cover stop, or RSI14 <= 26 oversold cover."
                ),
                "target_market_regimes": ["BEAR_TREND", "HIGH_VOL_CORRECTION", "SIDEWAYS_CHOPPY"],
                "holding_period_min_days": 3,
                "holding_period_max_days": 10,
                "universe": universe,
                "required_indicators": ["sma_20", "sma_50", "rsi_14", "atr_14", "rs_vs_spy_20d", "volume_ratio_20"],
                "entry_rules": {
                    "side": "SHORT",
                    "breakdown_lookback_days": 15,
                    "breakdown_tolerance_pct": 1.2,
                    "max_rs_vs_spy_20d": -3.0,
                    "min_volume_ratio_20": 1.15,
                    "min_rsi_14": 26.0,
                    "max_rsi_14": 52.0,
                    "require_below_sma50": True,
                },
                "exit_rules": {
                    "stop_loss_atr_mult": 1.8,
                    "take_profit_atr_mult": 3.4,
                    "trailing_stop_atr_mult": 2.1,
                    "exit_above_sma20": True,
                    "cover_rsi_below": 26.0,
                },
                "risk_params": {
                    "risk_per_trade_pct": 0.01,
                    "max_position_exposure_pct": 0.12,
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

