"""Deterministic Technical Indicators Engine.

All indicator calculations are strictly causal (point-in-time up to index `i`),
preventing any look-ahead bias.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence

from core.market_data.models import DailyBar


@dataclass(frozen=True)
class IndicatorSnapshot:
    """Point-in-time indicator values for a single ticker on a single trading day."""

    ticker: str
    bar_date: str
    close: float
    open: float
    high: float
    low: float
    volume: float
    sma_20: Optional[float]
    sma_50: Optional[float]
    sma_200: Optional[float]
    ema_12: Optional[float]
    ema_26: Optional[float]
    macd_line: Optional[float]
    macd_signal: Optional[float]
    macd_hist: Optional[float]
    rsi_14: Optional[float]
    atr_14: Optional[float]
    bb_upper_20: Optional[float]
    bb_mid_20: Optional[float]
    bb_lower_20: Optional[float]
    bb_width_pct: Optional[float]
    volume_sma_20: Optional[float]
    volume_ratio_20: Optional[float]
    high_20d_prior: Optional[float]
    low_20d_prior: Optional[float]
    high_252d_prior: Optional[float]
    ret_1d_pct: Optional[float]
    ret_5d_pct: Optional[float]
    ret_20d_pct: Optional[float]
    ret_60d_pct: Optional[float]
    realised_vol_20d_annualised: Optional[float]
    rs_vs_spy_20d: Optional[float]
    consolidation_range_10d_pct: Optional[float]
    avg_dollar_volume_20d: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calc_sma(values: Sequence[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    running_sum = sum(values[:period])
    out[period - 1] = running_sum / period
    for i in range(period, len(values)):
        running_sum += values[i] - values[i - period]
        out[i] = running_sum / period
    return out


def calc_ema(values: Sequence[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    mult = 2.0 / (period + 1.0)
    ema_val = sum(values[:period]) / period
    out[period - 1] = ema_val
    for i in range(period, len(values)):
        ema_val = (values[i] - ema_val) * mult + ema_val
        out[i] = ema_val
    return out


def calc_rsi(closes: Sequence[float], period: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(0.0, delta))
        losses.append(max(0.0, -delta))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def _to_rsi(g: float, l: float) -> float:
        if l == 0.0:
            return 100.0 if g > 0 else 50.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = _to_rsi(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = max(0.0, delta)
        loss = max(0.0, -delta)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _to_rsi(avg_gain, avg_loss)
    return out


def calc_atr(bars: Sequence[DailyBar], period: int = 14) -> List[Optional[float]]:
    n = len(bars)
    out: List[Optional[float]] = [None] * n
    if n == 0:
        return out
    tr_list: List[float] = [bars[0].adj_high - bars[0].adj_low]
    for i in range(1, n):
        high = bars[i].adj_high
        low = bars[i].adj_low
        prev_close = bars[i - 1].adj_close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    if n < period:
        return out
    atr_val = sum(tr_list[:period]) / period
    out[period - 1] = atr_val
    for i in range(period, n):
        atr_val = (atr_val * (period - 1) + tr_list[i]) / period
        out[i] = atr_val
    return out


def compute_indicator_series(
    bars: Sequence[DailyBar],
    spy_bars: Optional[Sequence[DailyBar]] = None,
) -> Dict[str, IndicatorSnapshot]:
    """Compute causal point-in-time indicators for a sequence of daily bars keyed by `bar_date`."""
    n = len(bars)
    if n == 0:
        return {}

    closes = [b.adj_close for b in bars]
    highs = [b.adj_high for b in bars]
    lows = [b.adj_low for b in bars]
    volumes = [b.adj_volume for b in bars]
    dollar_vols = [b.adj_close * b.adj_volume for b in bars]

    sma_20 = calc_sma(closes, 20)
    sma_50 = calc_sma(closes, 50)
    sma_200 = calc_sma(closes, 200)
    ema_12 = calc_ema(closes, 12)
    ema_26 = calc_ema(closes, 26)
    rsi_14 = calc_rsi(closes, 14)
    atr_14 = calc_atr(bars, 14)
    vol_sma_20 = calc_sma(volumes, 20)
    dvol_sma_20 = calc_sma(dollar_vols, 20)

    # MACD (12, 26, 9)
    macd_line: List[Optional[float]] = [None] * n
    macd_valid_vals: List[float] = []
    macd_valid_indices: List[int] = []
    for i in range(n):
        if ema_12[i] is not None and ema_26[i] is not None:
            val = float(ema_12[i]) - float(ema_26[i])
            macd_line[i] = val
            macd_valid_vals.append(val)
            macd_valid_indices.append(i)

    macd_sig_compact = calc_ema(macd_valid_vals, 9)
    macd_signal: List[Optional[float]] = [None] * n
    macd_hist: List[Optional[float]] = [None] * n
    for compact_idx, orig_idx in enumerate(macd_valid_indices):
        sig = macd_sig_compact[compact_idx]
        if sig is not None and macd_line[orig_idx] is not None:
            macd_signal[orig_idx] = sig
            macd_hist[orig_idx] = float(macd_line[orig_idx]) - sig

    # Map SPY 20d returns by date for Relative Strength calculation
    spy_ret_20d_by_date: Dict[str, float] = {}
    if spy_bars:
        for j in range(20, len(spy_bars)):
            prev_c = spy_bars[j - 20].adj_close
            if prev_c > 0:
                spy_ret_20d_by_date[spy_bars[j].bar_date] = (
                    (spy_bars[j].adj_close / prev_c) - 1.0
                ) * 100.0

    daily_rets: List[float] = [0.0] * n
    for i in range(1, n):
        daily_rets[i] = (closes[i] / closes[i - 1]) - 1.0 if closes[i - 1] > 0 else 0.0

    snapshots: Dict[str, IndicatorSnapshot] = {}
    for i, b in enumerate(bars):
        # Bollinger Bands (20, 2.0)
        bb_mid = sma_20[i]
        bb_up: Optional[float] = None
        bb_low: Optional[float] = None
        bb_width: Optional[float] = None
        if bb_mid is not None and i >= 19:
            window = closes[i - 19 : i + 1]
            variance = sum((x - bb_mid) ** 2 for x in window) / 20.0
            std_dev = math.sqrt(variance)
            bb_up = bb_mid + 2.0 * std_dev
            bb_low = bb_mid - 2.0 * std_dev
            bb_width = ((bb_up - bb_low) / bb_mid) * 100.0 if bb_mid > 0 else None

        # Prior 20d and 252d highs/lows (strictly prior bars [i-N : i] to detect clean breakouts)
        high_20d_prior = max(highs[max(0, i - 20) : i]) if i >= 5 else None
        low_20d_prior = min(lows[max(0, i - 20) : i]) if i >= 5 else None
        high_252d_prior = max(highs[max(0, i - 252) : i]) if i >= 20 else None

        # Prior 10-day consolidation range % (excluding today's breakout bar)
        consol_10d_pct: Optional[float] = None
        if i >= 11:
            prior_10_h = max(highs[i - 10 : i])
            prior_10_l = min(lows[i - 10 : i])
            if prior_10_l > 0:
                consol_10d_pct = ((prior_10_h - prior_10_l) / prior_10_l) * 100.0

        ret_1d = ((closes[i] / closes[i - 1]) - 1.0) * 100.0 if i >= 1 and closes[i - 1] > 0 else None
        ret_5d = ((closes[i] / closes[i - 5]) - 1.0) * 100.0 if i >= 5 and closes[i - 5] > 0 else None
        ret_20d = ((closes[i] / closes[i - 20]) - 1.0) * 100.0 if i >= 20 and closes[i - 20] > 0 else None
        ret_60d = ((closes[i] / closes[i - 60]) - 1.0) * 100.0 if i >= 60 and closes[i - 60] > 0 else None

        realised_vol_20d: Optional[float] = None
        if i >= 20:
            w_rets = daily_rets[i - 19 : i + 1]
            mean_r = sum(w_rets) / 20.0
            var_r = sum((r - mean_r) ** 2 for r in w_rets) / 19.0
            realised_vol_20d = math.sqrt(var_r) * math.sqrt(252.0) * 100.0

        vol_ratio = (
            b.adj_volume / vol_sma_20[i]
            if vol_sma_20[i] is not None and vol_sma_20[i] > 0
            else None
        )

        spy_20 = spy_ret_20d_by_date.get(b.bar_date)
        rs_vs_spy = (ret_20d - spy_20) if (ret_20d is not None and spy_20 is not None) else ret_20d

        snapshots[b.bar_date] = IndicatorSnapshot(
            ticker=b.ticker,
            bar_date=b.bar_date,
            close=b.adj_close,
            open=b.adj_open,
            high=b.adj_high,
            low=b.adj_low,
            volume=b.adj_volume,
            sma_20=round(sma_20[i], 4) if sma_20[i] is not None else None,
            sma_50=round(sma_50[i], 4) if sma_50[i] is not None else None,
            sma_200=round(sma_200[i], 4) if sma_200[i] is not None else None,
            ema_12=round(ema_12[i], 4) if ema_12[i] is not None else None,
            ema_26=round(ema_26[i], 4) if ema_26[i] is not None else None,
            macd_line=round(macd_line[i], 4) if macd_line[i] is not None else None,
            macd_signal=round(macd_signal[i], 4) if macd_signal[i] is not None else None,
            macd_hist=round(macd_hist[i], 4) if macd_hist[i] is not None else None,
            rsi_14=round(rsi_14[i], 2) if rsi_14[i] is not None else None,
            atr_14=round(atr_14[i], 4) if atr_14[i] is not None else None,
            bb_upper_20=round(bb_up, 4) if bb_up is not None else None,
            bb_mid_20=round(bb_mid, 4) if bb_mid is not None else None,
            bb_lower_20=round(bb_low, 4) if bb_low is not None else None,
            bb_width_pct=round(bb_width, 2) if bb_width is not None else None,
            volume_sma_20=round(vol_sma_20[i], 2) if vol_sma_20[i] is not None else None,
            volume_ratio_20=round(vol_ratio, 3) if vol_ratio is not None else None,
            high_20d_prior=round(high_20d_prior, 4) if high_20d_prior is not None else None,
            low_20d_prior=round(low_20d_prior, 4) if low_20d_prior is not None else None,
            high_252d_prior=round(high_252d_prior, 4) if high_252d_prior is not None else None,
            ret_1d_pct=round(ret_1d, 3) if ret_1d is not None else None,
            ret_5d_pct=round(ret_5d, 3) if ret_5d is not None else None,
            ret_20d_pct=round(ret_20d, 3) if ret_20d is not None else None,
            ret_60d_pct=round(ret_60d, 3) if ret_60d is not None else None,
            realised_vol_20d_annualised=round(realised_vol_20d, 2) if realised_vol_20d is not None else None,
            rs_vs_spy_20d=round(rs_vs_spy, 3) if rs_vs_spy is not None else None,
            consolidation_range_10d_pct=round(consol_10d_pct, 2) if consol_10d_pct is not None else None,
            avg_dollar_volume_20d=round(dvol_sma_20[i], 2) if dvol_sma_20[i] is not None else None,
        )

    return snapshots

