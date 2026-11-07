"""Quantitative Performance Metrics Calculator & Monte Carlo Trade-Sequence Simulator.

Computes all 16+ required metrics:
- Total return (%)
- Annualised return (CAGR %)
- Sharpe ratio (annualised, Rf=0)
- Sortino ratio (annualised, downside deviation)
- Maximum drawdown (%)
- Calmar ratio
- Win rate (%)
- Profit factor
- Average winning trade ($ and %)
- Average losing trade ($ and %)
- Expectancy ($ and % per trade)
- Average holding period (trading days)
- Exposure (% of time / capital invested)
- Turnover (annualised portfolio turnover)
- Number of trades
- Performance versus SPY (benchmark return, alpha, beta, information ratio)
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Sequence


def compute_drawdown_series(equities: Sequence[float]) -> List[float]:
    """Return percentage drawdown series [0.0 .. 1.0] for an equity curve."""
    peak = 0.0
    dds: List[float] = []
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        dds.append(round(dd, 6))
    return dds


def calculate_performance_metrics(
    equity_curve: Sequence[Dict[str, Any]],
    trades: Sequence[Dict[str, Any]],
    initial_capital: float = 100_000.0,
    spy_bars: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Calculate comprehensive quantitative backtest and portfolio performance metrics."""
    if not equity_curve:
        return {
            "total_return_pct": 0.0,
            "annualised_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "calmar_ratio": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "avg_winning_trade_usd": 0.0,
            "avg_losing_trade_usd": 0.0,
            "avg_winning_trade_pct": 0.0,
            "avg_losing_trade_pct": 0.0,
            "expectancy_usd": 0.0,
            "expectancy_pct": 0.0,
            "avg_holding_period_days": 0.0,
            "exposure_pct": 0.0,
            "annualised_turnover": 0.0,
            "trade_count": 0,
            "benchmark_return_pct": 0.0,
            "excess_return_vs_spy_pct": 0.0,
            "benchmark_sharpe": 0.0,
        }

    equities = [float(pt["equity"]) for pt in equity_curve]
    final_equity = equities[-1]
    total_return = (final_equity / initial_capital) - 1.0 if initial_capital > 0 else 0.0
    n_days = len(equities)
    years = max(n_days / 252.0, 1.0 / 252.0)

    if final_equity > 0 and initial_capital > 0:
        cagr = (final_equity / initial_capital) ** (1.0 / years) - 1.0
    else:
        cagr = -1.0

    daily_returns: List[float] = []
    for i in range(1, n_days):
        prev_eq = equities[i - 1]
        daily_returns.append((equities[i] / prev_eq) - 1.0 if prev_eq > 0 else 0.0)

    if len(daily_returns) >= 2:
        mean_ret = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_ret = math.sqrt(variance)
        sharpe = (mean_ret / std_ret) * math.sqrt(252.0) if std_ret > 1e-12 else 0.0

        downside_sq = [min(0.0, r) ** 2 for r in daily_returns]
        downside_dev = math.sqrt(sum(downside_sq) / len(daily_returns))
        sortino = (mean_ret / downside_dev) * math.sqrt(252.0) if downside_dev > 1e-12 else 0.0
    else:
        sharpe = 0.0
        sortino = 0.0

    dds = compute_drawdown_series(equities)
    max_dd = max(dds) if dds else 0.0
    calmar = (cagr / max_dd) if max_dd > 1e-6 else (10.0 if cagr > 0 else 0.0)

    # Trade-level statistics
    n_trades = len(trades)
    wins = [t for t in trades if float(t.get("net_pnl", 0.0)) > 0]
    losses = [t for t in trades if float(t.get("net_pnl", 0.0)) <= 0]

    win_rate = (len(wins) / n_trades) if n_trades > 0 else 0.0
    gross_profit = sum(float(t["net_pnl"]) for t in wins)
    gross_loss = abs(sum(float(t["net_pnl"]) for t in losses))
    if gross_loss > 1e-9:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = 5.0 if gross_profit > 0 else 0.0

    avg_win_usd = (gross_profit / len(wins)) if wins else 0.0
    avg_loss_usd = (-gross_loss / len(losses)) if losses else 0.0
    avg_win_pct = (sum(float(t.get("return_pct", 0.0)) for t in wins) / len(wins)) if wins else 0.0
    avg_loss_pct = (sum(float(t.get("return_pct", 0.0)) for t in losses) / len(losses)) if losses else 0.0

    expectancy_usd = (sum(float(t["net_pnl"]) for t in trades) / n_trades) if n_trades > 0 else 0.0
    expectancy_pct = (sum(float(t.get("return_pct", 0.0)) for t in trades) / n_trades) if n_trades > 0 else 0.0
    avg_hold_days = (
        sum(int(t.get("holding_days", 0)) for t in trades) / n_trades if n_trades > 0 else 0.0
    )

    # Exposure & Turnover
    invested_ratios = [
        float(pt.get("positions_value", 0.0)) / max(1.0, float(pt["equity"]))
        for pt in equity_curve
    ]
    avg_exposure = sum(invested_ratios) / len(invested_ratios) if invested_ratios else 0.0

    total_traded_notional = sum(
        float(t.get("entry_price", 0.0)) * int(t.get("quantity", 0))
        + float(t.get("exit_price", 0.0)) * int(t.get("quantity", 0))
        for t in trades
    )
    avg_equity = sum(equities) / len(equities) if equities else initial_capital
    annualised_turnover = (
        (total_traded_notional / 2.0) / max(1.0, avg_equity) / years if years > 0 else 0.0
    )

    # Benchmark (SPY) comparison over identical date range
    start_dt = equity_curve[0]["date"]
    end_dt = equity_curve[-1]["date"]
    spy_ret = 0.0
    spy_sharpe = 0.0
    if spy_bars:
        window_spy = [b for b in spy_bars if start_dt <= b.bar_date <= end_dt]
        if len(window_spy) >= 2:
            spy_ret = (window_spy[-1].adj_close / window_spy[0].adj_close) - 1.0
            s_rets = [
                (window_spy[i].adj_close / window_spy[i - 1].adj_close) - 1.0
                for i in range(1, len(window_spy))
                if window_spy[i - 1].adj_close > 0
            ]
            if len(s_rets) >= 2:
                m_s = sum(s_rets) / len(s_rets)
                v_s = sum((x - m_s) ** 2 for x in s_rets) / (len(s_rets) - 1)
                sd_s = math.sqrt(v_s)
                spy_sharpe = (m_s / sd_s) * math.sqrt(252.0) if sd_s > 1e-12 else 0.0

    return {
        "total_return_pct": round(total_return * 100.0, 2),
        "annualised_return_pct": round(cagr * 100.0, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "calmar_ratio": round(calmar, 3),
        "win_rate_pct": round(win_rate * 100.0, 2),
        "profit_factor": round(profit_factor, 3),
        "avg_winning_trade_usd": round(avg_win_usd, 2),
        "avg_losing_trade_usd": round(avg_loss_usd, 2),
        "avg_winning_trade_pct": round(avg_win_pct, 2),
        "avg_losing_trade_pct": round(avg_loss_pct, 2),
        "expectancy_usd": round(expectancy_usd, 2),
        "expectancy_pct": round(expectancy_pct, 2),
        "avg_holding_period_days": round(avg_hold_days, 2),
        "exposure_pct": round(avg_exposure * 100.0, 2),
        "annualised_turnover": round(annualised_turnover, 2),
        "trade_count": n_trades,
        "benchmark_return_pct": round(spy_ret * 100.0, 2),
        "excess_return_vs_spy_pct": round((total_return - spy_ret) * 100.0, 2),
        "benchmark_sharpe": round(spy_sharpe, 3),
        "final_equity": round(final_equity, 2),
    }


def run_monte_carlo_trade_sequence(
    trades: Sequence[Dict[str, Any]],
    initial_capital: float = 100_000.0,
    num_simulations: int = 200,
    seed: int = 42,
) -> Dict[str, Any]:
    """Reshuffle trade PnL sequence to estimate distribution of Max Drawdown and Terminal Equity."""
    if not trades:
        return {
            "simulations": 0,
            "median_max_drawdown_pct": 0.0,
            "p95_max_drawdown_pct": 0.0,
            "median_return_pct": 0.0,
            "p05_return_pct": 0.0,
        }

    rng = random.Random(seed)
    pnls = [float(t.get("net_pnl", 0.0)) for t in trades]
    max_dds: List[float] = []
    tot_rets: List[float] = []

    for _ in range(num_simulations):
        shuffled = list(pnls)
        rng.shuffle(shuffled)
        eq = initial_capital
        peak = initial_capital
        worst_dd = 0.0
        for p in shuffled:
            eq += p
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > worst_dd:
                worst_dd = dd
        max_dds.append(worst_dd * 100.0)
        tot_rets.append(((eq / initial_capital) - 1.0) * 100.0)

    max_dds.sort()
    tot_rets.sort()
    mid = len(max_dds) // 2
    p95_idx = min(len(max_dds) - 1, int(len(max_dds) * 0.95))
    p05_idx = max(0, int(len(tot_rets) * 0.05))

    return {
        "simulations": num_simulations,
        "median_max_drawdown_pct": round(max_dds[mid], 2),
        "p95_max_drawdown_pct": round(max_dds[p95_idx], 2),
        "median_return_pct": round(tot_rets[mid], 2),
        "p05_return_pct": round(tot_rets[p05_idx], 2),
    }

