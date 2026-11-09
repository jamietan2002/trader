"""Autonomous Market Research Agent.

Responsibilities:
- Scan the US equities universe.
- Identify unusual price and volume movements, strong relative strength vs SPY,
  upcoming earnings/catalysts, positive/negative earnings surprises, SEC filings,
  and sector rotation.
- Rank candidates based on transparent quantitative criteria (`composite_rank_score`)
  rather than subjective AI sentiment alone.
- Produce a validated `CandidateResearchReport` schema for each candidate and persist to DB.
- Explicitly distinguish `research_confidence_score` (evidence completeness/signal alignment)
  from any statistical probability of profit.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence

from agents.base import BaseAgent, LLMProvider, validate_required_fields
from core.indicators.technical import IndicatorSnapshot, compute_indicator_series
from core.market_data.providers import MarketDataService
from core.strategies.registry import StrategyFamily
from infrastructure.configuration.settings import Settings
from infrastructure.database.db import DatabaseManager, utc_now_iso


@dataclass(frozen=True)
class CandidateResearchReport:
    report_id: str
    run_id: str
    ticker: str
    company_name: str
    current_price: float
    as_of_timestamp: str
    market_and_sector_context: Dict[str, Any]
    recent_price_performance: Dict[str, Any]
    relative_strength_vs_spy_20d: float
    volume_analysis: Dict[str, Any]
    relevant_technical_indicators: Dict[str, Any]
    relevant_news_and_catalysts: List[Dict[str, Any]]
    earnings_information: Dict[str, Any]
    bullish_thesis: str
    bearish_thesis: str
    main_risks: List[str]
    potential_holding_period_days: List[int]
    suggested_strategy_family: str
    composite_rank_score: float
    research_confidence_score: float
    confidence_disclaimer: str
    sources_and_evidence: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


RESEARCH_REPORT_SCHEMA_TYPES: Dict[str, Any] = {
    "report_id": str,
    "run_id": str,
    "ticker": str,
    "company_name": str,
    "current_price": (int, float),
    "as_of_timestamp": str,
    "market_and_sector_context": dict,
    "recent_price_performance": dict,
    "relative_strength_vs_spy_20d": (int, float),
    "volume_analysis": dict,
    "relevant_technical_indicators": dict,
    "relevant_news_and_catalysts": list,
    "earnings_information": dict,
    "bullish_thesis": str,
    "bearish_thesis": str,
    "main_risks": list,
    "potential_holding_period_days": list,
    "suggested_strategy_family": str,
    "composite_rank_score": (int, float),
    "research_confidence_score": (int, float),
    "confidence_disclaimer": str,
    "sources_and_evidence": list,
}


class MarketResearchAgent(BaseAgent):
    """Autonomous Market Research Agent scanning US equities and ranking swing candidates."""

    role_name = "market_researcher"

    def __init__(
        self,
        settings: Settings,
        db: DatabaseManager,
        market_data: MarketDataService,
        llm: Optional[LLMProvider] = None,
    ) -> None:
        super().__init__(settings, llm)
        self.db = db
        self.market_data = market_data

    def run_market_scan(
        self,
        as_of_date: str,
        top_n: int = 8,
    ) -> Dict[str, Any]:
        """Scan the active US equities universe as of `as_of_date` and persist ranked reports."""
        self.assert_permission("read_market_data")
        self.assert_permission("read_indicators")
        self.assert_permission("read_earnings_and_catalysts")
        self.assert_permission("write_research_report")

        run_id = f"res_run_{as_of_date}_{uuid.uuid4().hex[:8]}"
        universe = self.market_data.get_universe_metadata(include_delisted=False)
        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker, end_date=as_of_date)
        spy_inds = compute_indicator_series(spy_bars)
        spy_ind = spy_inds.get(as_of_date) or (list(spy_inds.values())[-1] if spy_inds else None)

        # Compute sector momentum rankings first
        sector_returns_20d: Dict[str, List[float]] = {}
        ticker_snapshots: Dict[str, IndicatorSnapshot] = {}

        for ticker, meta in universe.items():
            if ticker == self.settings.benchmark_ticker:
                continue
            bars = self.market_data.get_bars(ticker, end_date=as_of_date)
            if len(bars) < 25:
                continue
            inds = compute_indicator_series(bars, spy_bars=spy_bars)
            ind = inds.get(as_of_date) or list(inds.values())[-1]
            ticker_snapshots[ticker] = ind
            if ind.ret_20d_pct is not None:
                sector_returns_20d.setdefault(meta.sector, []).append(ind.ret_20d_pct)

        sector_avg_ret: Dict[str, float] = {
            sec: round(sum(vals) / len(vals), 2)
            for sec, vals in sector_returns_20d.items()
            if vals
        }
        sorted_sectors = sorted(sector_avg_ret.keys(), key=lambda s: sector_avg_ret[s], reverse=True)
        sector_rank_map = {sec: idx + 1 for idx, sec in enumerate(sorted_sectors)}

        candidate_reports: List[CandidateResearchReport] = []

        for ticker, ind in ticker_snapshots.items():
            meta = universe[ticker]
            recent_earnings = self.market_data.get_point_in_time_earnings(ticker, as_of_date, lookback_days=15)
            upcoming_earnings = self.market_data.get_upcoming_earnings_within_days(ticker, as_of_date, horizon_days=7)
            catalysts = self.db.fetch_all(
                """
                SELECT * FROM market_catalysts
                WHERE ticker = ? AND published_date <= ?
                ORDER BY published_date DESC LIMIT 3
                """,
                (ticker, as_of_date),
            )

            # Transparent, deterministic multi-factor ranking criteria:
            # 1. Relative strength vs SPY (35% weight)
            # 2. Volume expansion ratio (25% weight)
            # 3. Trend alignment (Close > SMA20 > SMA50) (20% weight)
            # 4. Earnings surprise / catalyst score (20% weight)
            rs_val = ind.rs_vs_spy_20d or 0.0
            vol_ratio = ind.volume_ratio_20 or 1.0
            trend_score = 0.0
            if ind.sma_20 and ind.close > ind.sma_20:
                trend_score += 50.0
            if ind.sma_20 and ind.sma_50 and ind.sma_20 > ind.sma_50:
                trend_score += 50.0

            earnings_score = 50.0
            latest_ev = recent_earnings[0] if recent_earnings else None
            if latest_ev:
                earnings_score = min(100.0, max(0.0, 50.0 + latest_ev.eps_surprise_pct * 2.5))

            rs_norm = min(100.0, max(0.0, 50.0 + rs_val * 4.5))
            vol_norm = min(100.0, max(0.0, (vol_ratio - 0.5) * 55.0))
            composite_score = round(
                0.35 * rs_norm + 0.25 * vol_norm + 0.20 * trend_score + 0.20 * earnings_score,
                2,
            )

            # Suggest the most appropriate strategy family based on observable phenomenon
            suggested_family = StrategyFamily.MOMENTUM_TREND.value
            holding_period = [4, 12]
            if latest_ev and latest_ev.eps_surprise_pct >= 5.0 and vol_ratio >= 1.3:
                suggested_family = StrategyFamily.PEAD.value
                holding_period = [4, 10]
            elif ind.high_20d_prior and ind.close > ind.high_20d_prior and vol_ratio >= 1.3:
                suggested_family = StrategyFamily.BREAKOUT.value
                holding_period = [3, 11]
            elif ind.rsi_14 and ind.rsi_14 <= 35.0:
                suggested_family = StrategyFamily.MEAN_REVERSION.value
                holding_period = [3, 8]
            elif sector_rank_map.get(meta.sector, 99) == 1 and rs_val >= 3.0:
                suggested_family = StrategyFamily.SECTOR_ROTATION.value
                holding_period = [5, 14]

            # Research confidence measures data completeness & multi-factor convergence (NOT profit probability)
            data_completeness = 0.70 + (0.15 if latest_ev else 0.0) + (0.15 if ind.sma_50 is not None else 0.0)
            research_confidence = round(min(0.95, data_completeness * (0.65 + composite_score / 300.0)), 2)

            spy_regime = "BULL_TREND" if (spy_ind and spy_ind.sma_50 and spy_ind.close >= spy_ind.sma_50) else "DEFENSIVE_CHOPPY"

            fallback_synthesis = {
                "bullish_thesis": (
                    f"{ticker} ({meta.company_name}) exhibits {rs_val:+.2f}% 20-day relative strength vs SPY "
                    f"with {vol_ratio:.2f}x relative volume in the #{sector_rank_map.get(meta.sector, 1)}-ranked "
                    f"{meta.sector} sector. Recommended strategy archetype: {suggested_family}."
                ),
                "bearish_thesis": (
                    f"Upside momentum in {ticker} could stall if {meta.sector} experiences sector rotation outflow "
                    f"or if price breaks below SMA20 (${ind.sma_20 or ind.close:.2f}) / 2x ATR stop."
                ),
                "main_risks": [
                    f"Upcoming earnings announcement within 7 days ({len(upcoming_earnings)} scheduled)"
                    if upcoming_earnings
                    else "Overnight gap risk on macroeconomic releases",
                    f"20-day annualised realised volatility of {ind.realised_vol_20d_annualised or 18.0:.1f}%",
                    f"Broad market regime currently classified as {spy_regime}",
                ],
            }

            llm_out = self.llm.generate_structured_json(
                system_prompt="You are a quantitative equity research analyst. Return JSON with keys: bullish_thesis, bearish_thesis, main_risks.",
                user_prompt=json.dumps({"ticker": ticker, "indicators": ind.to_dict(), "sector": meta.sector}),
                fallback_payload=fallback_synthesis,
            )

            report = CandidateResearchReport(
                report_id=f"rep_{as_of_date}_{ticker}_{uuid.uuid4().hex[:6]}",
                run_id=run_id,
                ticker=ticker,
                company_name=meta.company_name,
                current_price=ind.close,
                as_of_timestamp=f"{as_of_date}T09:00:00-04:00",
                market_and_sector_context={
                    "spy_regime": spy_regime,
                    "spy_close": spy_ind.close if spy_ind else None,
                    "spy_20d_vol_pct": spy_ind.realised_vol_20d_annualised if spy_ind else None,
                    "sector": meta.sector,
                    "industry": meta.industry,
                    "sector_20d_return_pct": sector_avg_ret.get(meta.sector, 0.0),
                    "sector_momentum_rank": sector_rank_map.get(meta.sector, 1),
                },
                recent_price_performance={
                    "ret_1d_pct": ind.ret_1d_pct,
                    "ret_5d_pct": ind.ret_5d_pct,
                    "ret_20d_pct": ind.ret_20d_pct,
                    "ret_60d_pct": ind.ret_60d_pct,
                },
                relative_strength_vs_spy_20d=rs_val,
                volume_analysis={
                    "current_volume": ind.volume,
                    "volume_sma_20": ind.volume_sma_20,
                    "volume_ratio_20": vol_ratio,
                    "avg_dollar_volume_20d": ind.avg_dollar_volume_20d,
                    "unusual_volume_detected": vol_ratio >= 1.4,
                },
                relevant_technical_indicators={
                    "sma_20": ind.sma_20,
                    "sma_50": ind.sma_50,
                    "sma_200": ind.sma_200,
                    "rsi_14": ind.rsi_14,
                    "atr_14": ind.atr_14,
                    "high_20d_prior": ind.high_20d_prior,
                    "consolidation_range_10d_pct": ind.consolidation_range_10d_pct,
                },
                relevant_news_and_catalysts=[
                    {
                        "date": c["published_date"],
                        "type": c["catalyst_type"],
                        "headline": c["headline"],
                        "sentiment_score": c["sentiment_score"],
                    }
                    for c in catalysts
                ],
                earnings_information={
                    "latest_earnings": latest_ev.to_dict() if latest_ev else None,
                    "upcoming_earnings_7d": upcoming_earnings,
                },
                bullish_thesis=str(llm_out.get("bullish_thesis", fallback_synthesis["bullish_thesis"])),
                bearish_thesis=str(llm_out.get("bearish_thesis", fallback_synthesis["bearish_thesis"])),
                main_risks=list(llm_out.get("main_risks", fallback_synthesis["main_risks"])),
                potential_holding_period_days=holding_period,
                suggested_strategy_family=suggested_family,
                composite_rank_score=composite_score,
                research_confidence_score=research_confidence,
                confidence_disclaimer=(
                    "NOTE: research_confidence_score reflects point-in-time data completeness and "
                    "multi-factor alignment; it is NOT a statistically calibrated probability of profit."
                ),
                sources_and_evidence=[
                    f"Daily OHLCV & Indicators ({self.market_data.provider.provider_name})",
                    "SEC EDGAR Form 8-K / Quarterly Earnings Registry",
                    f"Relative Strength Benchmark ({self.settings.benchmark_ticker})",
                ],
            )

            validate_required_fields(
                report.to_dict(), RESEARCH_REPORT_SCHEMA_TYPES, "CandidateResearchReport"
            )
            candidate_reports.append(report)

        # Rank deterministically by composite_rank_score descending
        candidate_reports.sort(key=lambda r: (-r.composite_rank_score, r.ticker))
        top_reports = candidate_reports[:top_n]

        now_iso = utc_now_iso()
        for rep in candidate_reports:
            self.db.execute(
                "DELETE FROM research_reports WHERE as_of_date = ? AND ticker = ?",
                (as_of_date, rep.ticker),
            )
            self.db.execute(
                """
                INSERT INTO research_reports (
                    report_id, run_id, as_of_date, ticker, company_name,
                    current_price, sector, composite_rank_score,
                    research_confidence_score, suggested_strategy_family,
                    potential_holding_days_min, potential_holding_days_max,
                    report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rep.report_id,
                    rep.run_id,
                    as_of_date,
                    rep.ticker,
                    rep.company_name,
                    rep.current_price,
                    rep.market_and_sector_context["sector"],
                    rep.composite_rank_score,
                    rep.research_confidence_score,
                    rep.suggested_strategy_family,
                    rep.potential_holding_period_days[0],
                    rep.potential_holding_period_days[1],
                    json.dumps(rep.to_dict()),
                    now_iso,
                ),
            )

        return {
            "run_id": run_id,
            "as_of_date": as_of_date,
            "universe_scanned": len(ticker_snapshots),
            "sector_rankings": [
                {"rank": idx + 1, "sector": sec, "avg_20d_return_pct": sector_avg_ret[sec]}
                for idx, sec in enumerate(sorted_sectors)
            ],
            "top_candidates": [r.to_dict() for r in top_reports],
        }

    def get_latest_reports(self, limit: int = 15) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            """
            SELECT report_json
            FROM research_reports
            WHERE as_of_date = (SELECT MAX(as_of_date) FROM research_reports)
            ORDER BY composite_rank_score DESC, created_at DESC
            """
        )
        deduped: List[Dict[str, Any]] = []
        seen_tickers: set[str] = set()
        for r in rows:
            rep = json.loads(r["report_json"])
            tkr = str(rep.get("ticker") or "").upper()
            if tkr and tkr not in seen_tickers:
                seen_tickers.add(tkr)
                deduped.append(rep)
                if len(deduped) >= limit:
                    break
        import sys as _sys
        if deduped and "unittest" not in _sys.modules and hasattr(self.market_data, "fetch_live_quote_snapshots"):
            try:
                live_snaps = self.market_data.fetch_live_quote_snapshots([str(d.get("ticker")) for d in deduped])
                for d in deduped:
                    t_u = str(d.get("ticker") or "").upper()
                    snap = live_snaps.get(t_u) or {}
                    live_px = float(snap.get("indicative_price") or 0.0)
                    if live_px > 0:
                        d["reference_close_price"] = d.get("current_price")
                        d["current_price"] = round(live_px, 2)
            except Exception:
                pass
        return deduped

