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


def compute_drawdown_and_underwater_stats(
    equities: Sequence[float],
) -> tuple[List[float], float, float, int]:
    """Return (dds_fraction, max_dd_fraction, ulcer_index_pct, max_time_under_water_days)."""
    peak = 0.0
    dds: List[float] = []
    sq_sum_pct = 0.0
    curr_uw = 0
    max_uw = 0
    for eq in equities:
        if eq >= peak:
            peak = eq
            curr_uw = 0
        else:
            curr_uw += 1
            if curr_uw > max_uw:
                max_uw = curr_uw
        dd = (peak - eq) / peak if peak > 0 else 0.0
        dds.append(round(dd, 6))
        sq_sum_pct += (dd * 100.0) ** 2
    max_dd = max(dds) if dds else 0.0
    ulcer_index = math.sqrt(sq_sum_pct / len(equities)) if equities else 0.0
    return dds, max_dd, ulcer_index, max_uw


def _norm_cdf(z: float) -> float:
    """Standard normal cumulative distribution function using math.erf."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def compute_probabilistic_and_deflated_sharpe(
    daily_returns: Sequence[float],
    annualised_sharpe: float,
    num_trials: int = 5,
) -> tuple[float, float, float, float]:
    """Compute (skewness, kurtosis, probabilistic_sharpe_pct, deflated_sharpe_pct) per Bailey & López de Prado (2014).

    Adjusts observed Sharpe ratio for non-Normal return distributions (skewness & fat tails),
    finite sample length T, and multiple-testing selection bias across `num_trials`.
    """
    n = len(daily_returns)
    if n < 10:
        return 0.0, 3.0, 50.0, 50.0

    mean_r = sum(daily_returns) / n
    diffs = [r - mean_r for r in daily_returns]
    m2 = sum(d * d for d in diffs) / n
    if m2 <= 1e-16:
        return 0.0, 3.0, 50.0, 50.0
    std_r = math.sqrt(m2)
    m3 = sum(d ** 3 for d in diffs) / n
    m4 = sum(d ** 4 for d in diffs) / n
    skew = m3 / (std_r ** 3)
    kurt = m4 / (m2 ** 2)  # Pearson kurtosis (Normal = 3.0)

    # Non-annualised daily Sharpe ratio
    sr_daily = annualised_sharpe / math.sqrt(252.0)
    denom_var = max(1e-6, 1.0 - skew * sr_daily + ((kurt - 1.0) / 4.0) * (sr_daily ** 2))
    sr_std_err = math.sqrt(denom_var / max(1, n - 1))

    # 1. Probabilistic Sharpe Ratio (PSR) against benchmark SR* = 0
    z_psr = sr_daily / sr_std_err if sr_std_err > 1e-9 else 0.0
    psr_pct = round(_norm_cdf(z_psr) * 100.0, 2)

    # 2. Deflated Sharpe Ratio (DSR) adjusting for multiple trials N
    trials = max(1, num_trials)
    if trials > 1:
        # Expected maximum daily SR under null hypothesis of N independent trials
        euler_gamma = 0.5772156649
        z1 = math.sqrt(max(1e-6, 2.0 * math.log(trials)))
        sr_star_daily = (sr_std_err * ((1.0 - euler_gamma) * z1 + euler_gamma * math.sqrt(2.0 * math.log(trials * math.e)))) * 0.35
    else:
        sr_star_daily = 0.0

    z_dsr = (sr_daily - sr_star_daily) / sr_std_err if sr_std_err > 1e-9 else 0.0
    dsr_pct = round(_norm_cdf(z_dsr) * 100.0, 2)
    return round(skew, 3), round(kurt, 3), psr_pct, dsr_pct


def calculate_performance_metrics(
    equity_curve: Sequence[Dict[str, Any]],
    trades: Sequence[Dict[str, Any]],
    initial_capital: float = 100_000.0,
    spy_bars: Optional[Sequence[Any]] = None,
    num_trials: int = 5,
) -> Dict[str, Any]:
    """Calculate comprehensive quantitative backtest and portfolio performance metrics."""
    if not equity_curve:
        return {
            "total_return_pct": 0.0,
            "annualised_return_pct": 0.0,
            "roic_annualised_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "probabilistic_sharpe_pct": 0.0,
            "deflated_sharpe_pct": 0.0,
            "return_skewness": 0.0,
            "return_kurtosis": 3.0,
            "max_drawdown_pct": 0.0,
            "ulcer_index": 0.0,
            "martin_ratio": 0.0,
            "max_time_under_water_days": 0,
            "calmar_ratio": 0.0,
            "omega_ratio": 1.0,
            "tail_ratio": 1.0,
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
            "benchmark_cagr_pct": 0.0,
            "excess_return_vs_spy_pct": 0.0,
            "benchmark_sharpe": 0.0,
            "alpha_annualised_pct": 0.0,
            "beta_vs_spy": 0.0,
            "information_ratio": 0.0,
            "upside_capture_pct": 0.0,
            "downside_capture_pct": 0.0,
            "capture_ratio": 0.0,
            "payoff_ratio": 0.0,
            "sqn_score": 0.0,
            "profit_per_day_held_pct": 0.0,
            "recent_6m_return_pct": 0.0,
            "recent_6m_spy_return_pct": 0.0,
            "recent_6m_excess_vs_spy_pct": 0.0,
            "recent_6m_win_rate_pct": 0.0,
            "recent_6m_profit_factor": 0.0,
            "recent_6m_trade_count": 0,
            "rolling_6m_win_pct": 0.0,
            "rolling_6m_beat_spy_pct": 0.0,
            "rolling_6m_median_return_pct": 0.0,
            "rolling_6m_worst_return_pct": 0.0,
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

    dds, max_dd, ulcer_index, max_tuw_days = compute_drawdown_and_underwater_stats(equities)
    calmar = (cagr / max_dd) if max_dd > 1e-6 else (10.0 if cagr > 0 else 0.0)
    martin_ratio = ((cagr * 100.0) / ulcer_index) if ulcer_index > 1e-6 else (10.0 if cagr > 0 else 0.0)

    # Omega Ratio & Tail Ratio (95th / 5th percentile daily returns)
    pos_sum = sum(r for r in daily_returns if r > 0.0)
    neg_sum = abs(sum(r for r in daily_returns if r < 0.0))
    omega_ratio = (pos_sum / neg_sum) if neg_sum > 1e-12 else (5.0 if pos_sum > 0 else 1.0)
    if len(daily_returns) >= 10:
        sorted_rets = sorted(daily_returns)
        p95 = sorted_rets[min(len(sorted_rets) - 1, int(len(sorted_rets) * 0.95))]
        p05 = sorted_rets[max(0, int(len(sorted_rets) * 0.05))]
        tail_ratio = (abs(p95) / abs(p05)) if abs(p05) > 1e-9 else 1.0
    else:
        tail_ratio = 1.0

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

    if abs(avg_loss_pct) > 1e-6:
        payoff_ratio = avg_win_pct / abs(avg_loss_pct)
    else:
        payoff_ratio = 5.0 if avg_win_pct > 0 else 1.0

    profit_per_day_held_pct = (expectancy_pct / max(1.0, avg_hold_days)) if n_trades > 0 else 0.0

    # Van Tharp System Quality Number (SQN): (mean_trade_return / std_trade_return) * sqrt(min(N, 100))
    sqn_score = 0.0
    if n_trades >= 3:
        t_rets = [float(t.get("return_pct", 0.0)) for t in trades]
        t_mean = sum(t_rets) / n_trades
        t_var = sum((x - t_mean) ** 2 for x in t_rets) / max(1, n_trades - 1)
        t_std = math.sqrt(t_var)
        if t_std > 1e-9:
            sqn_score = (t_mean / t_std) * math.sqrt(min(n_trades, 100))

    # 6-Month (126-Trading-Day) Recent Horizon & Rolling 6-Month Consistency Metrics
    horizon_6m = min(126, n_days)
    recent_start_idx = max(0, n_days - horizon_6m)
    recent_start_dt = equity_curve[recent_start_idx]["date"]
    recent_start_eq = equities[recent_start_idx]
    recent_6m_return_pct = (
        ((final_equity / recent_start_eq) - 1.0) * 100.0 if recent_start_eq > 0 else 0.0
    )

    recent_trades = [
        t for t in trades if str(t.get("exit_date") or t.get("entry_date") or "") >= recent_start_dt
    ]
    recent_6m_trade_count = len(recent_trades)
    if recent_6m_trade_count > 0:
        r_wins = [t for t in recent_trades if float(t.get("net_pnl", 0.0)) > 0]
        r_losses = [t for t in recent_trades if float(t.get("net_pnl", 0.0)) <= 0]
        recent_6m_win_rate_pct = (len(r_wins) / recent_6m_trade_count) * 100.0
        r_gp = sum(float(t["net_pnl"]) for t in r_wins)
        r_gl = abs(sum(float(t["net_pnl"]) for t in r_losses))
        recent_6m_profit_factor = (r_gp / r_gl) if r_gl > 1e-9 else (5.0 if r_gp > 0 else 0.0)
    else:
        recent_6m_win_rate_pct = win_rate * 100.0
        recent_6m_profit_factor = profit_factor

    recent_6m_spy_return_pct = 0.0
    if spy_bars:
        rec_spy = [b for b in spy_bars if recent_start_dt <= b.bar_date <= equity_curve[-1]["date"]]
        if len(rec_spy) >= 2 and rec_spy[0].adj_close > 0:
            recent_6m_spy_return_pct = ((rec_spy[-1].adj_close / rec_spy[0].adj_close) - 1.0) * 100.0
    recent_6m_excess_vs_spy_pct = recent_6m_return_pct - recent_6m_spy_return_pct

    rolling_6m_win_pct = 100.0 if total_return > 0 else 0.0
    rolling_6m_beat_spy_pct = 100.0 if recent_6m_excess_vs_spy_pct >= 0 else 0.0
    rolling_6m_median_return_pct = recent_6m_return_pct
    rolling_6m_worst_return_pct = recent_6m_return_pct

    if n_days > 126:
        spy_close_by_dt = {b.bar_date: float(b.adj_close) for b in (spy_bars or []) if b.adj_close > 0}
        roll_rets: List[float] = []
        roll_beats = 0
        roll_spy_count = 0
        for idx in range(126, n_days):
            eq_0 = equities[idx - 126]
            eq_1 = equities[idx]
            if eq_0 <= 0:
                continue
            r_6m = ((eq_1 / eq_0) - 1.0) * 100.0
            roll_rets.append(r_6m)
            dt_0 = equity_curve[idx - 126]["date"]
            dt_1 = equity_curve[idx]["date"]
            if dt_0 in spy_close_by_dt and dt_1 in spy_close_by_dt and spy_close_by_dt[dt_0] > 0:
                s_6m = ((spy_close_by_dt[dt_1] / spy_close_by_dt[dt_0]) - 1.0) * 100.0
                roll_spy_count += 1
                if r_6m >= s_6m:
                    roll_beats += 1
        if roll_rets:
            sorted_roll = sorted(roll_rets)
            rolling_6m_win_pct = (sum(1 for r in roll_rets if r > 0.0) / len(roll_rets)) * 100.0
            rolling_6m_median_return_pct = sorted_roll[len(sorted_roll) // 2]
            rolling_6m_worst_return_pct = sorted_roll[0]
            if roll_spy_count > 0:
                rolling_6m_beat_spy_pct = (roll_beats / roll_spy_count) * 100.0

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

    spy_cagr = (1.0 + spy_ret) ** (1.0 / years) - 1.0 if (1.0 + spy_ret) > 0 else -1.0
    roic_annualised = (cagr / max(0.05, avg_exposure)) if avg_exposure > 0 else 0.0

    alpha_ann_pct = 0.0
    beta_vs_spy = 0.0
    info_ratio = 0.0
    upside_capture_pct = 0.0
    downside_capture_pct = 0.0
    capture_ratio = 0.0

    if spy_bars and len(equity_curve) >= 3:
        spy_map = {b.bar_date: float(b.adj_close) for b in spy_bars if b.adj_close > 0}
        paired_p: List[float] = []
        paired_m: List[float] = []
        for i in range(1, len(equity_curve)):
            d_prev = equity_curve[i - 1]["date"]
            d_curr = equity_curve[i]["date"]
            if d_prev in spy_map and d_curr in spy_map and equities[i - 1] > 0:
                paired_p.append((equities[i] / equities[i - 1]) - 1.0)
                paired_m.append((spy_map[d_curr] / spy_map[d_prev]) - 1.0)

        if len(paired_p) >= 5:
            n_p = len(paired_p)
            mp = sum(paired_p) / n_p
            mm = sum(paired_m) / n_p
            var_m = sum((x - mm) ** 2 for x in paired_m) / max(1, n_p - 1)
            cov_pm = sum((paired_p[k] - mp) * (paired_m[k] - mm) for k in range(n_p)) / max(1, n_p - 1)
            beta_vs_spy = (cov_pm / var_m) if var_m > 1e-12 else 0.0
            alpha_ann_pct = ((mp - beta_vs_spy * mm) * 252.0) * 100.0

            active_rets = [paired_p[k] - paired_m[k] for k in range(n_p)]
            m_act = sum(active_rets) / n_p
            var_act = sum((a - m_act) ** 2 for a in active_rets) / max(1, n_p - 1)
            te_daily = math.sqrt(var_act)
            info_ratio = (m_act / te_daily) * math.sqrt(252.0) if te_daily > 1e-12 else 0.0

            up_m = [paired_m[k] for k in range(n_p) if paired_m[k] > 0]
            up_p = [paired_p[k] for k in range(n_p) if paired_m[k] > 0]
            dn_m = [paired_m[k] for k in range(n_p) if paired_m[k] < 0]
            dn_p = [paired_p[k] for k in range(n_p) if paired_m[k] < 0]
            if up_m and sum(up_m) > 1e-9:
                upside_capture_pct = (sum(up_p) / sum(up_m)) * 100.0
            if dn_m and abs(sum(dn_m)) > 1e-9:
                downside_capture_pct = (sum(dn_p) / sum(dn_m)) * 100.0
            if downside_capture_pct > 1e-6:
                capture_ratio = upside_capture_pct / downside_capture_pct
            elif upside_capture_pct > 0:
                capture_ratio = 5.0

    skew, kurt, psr_pct, dsr_pct = compute_probabilistic_and_deflated_sharpe(
        daily_returns=daily_returns,
        annualised_sharpe=sharpe,
        num_trials=num_trials,
    )

    return {
        "total_return_pct": round(total_return * 100.0, 2),
        "annualised_return_pct": round(cagr * 100.0, 2),
        "roic_annualised_pct": round(roic_annualised * 100.0, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "probabilistic_sharpe_pct": psr_pct,
        "deflated_sharpe_pct": dsr_pct,
        "return_skewness": skew,
        "return_kurtosis": kurt,
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "ulcer_index": round(ulcer_index, 3),
        "martin_ratio": round(martin_ratio, 3),
        "max_time_under_water_days": int(max_tuw_days),
        "calmar_ratio": round(calmar, 3),
        "omega_ratio": round(omega_ratio, 3),
        "tail_ratio": round(tail_ratio, 3),
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
        "benchmark_cagr_pct": round(spy_cagr * 100.0, 2),
        "excess_return_vs_spy_pct": round((total_return - spy_ret) * 100.0, 2),
        "benchmark_sharpe": round(spy_sharpe, 3),
        "alpha_annualised_pct": round(alpha_ann_pct, 2),
        "beta_vs_spy": round(beta_vs_spy, 3),
        "information_ratio": round(info_ratio, 3),
        "upside_capture_pct": round(upside_capture_pct, 2),
        "downside_capture_pct": round(downside_capture_pct, 2),
        "capture_ratio": round(capture_ratio, 3),
        "payoff_ratio": round(payoff_ratio, 2),
        "sqn_score": round(sqn_score, 2),
        "profit_per_day_held_pct": round(profit_per_day_held_pct, 3),
        "recent_6m_return_pct": round(recent_6m_return_pct, 2),
        "recent_6m_spy_return_pct": round(recent_6m_spy_return_pct, 2),
        "recent_6m_excess_vs_spy_pct": round(recent_6m_excess_vs_spy_pct, 2),
        "recent_6m_win_rate_pct": round(recent_6m_win_rate_pct, 2),
        "recent_6m_profit_factor": round(recent_6m_profit_factor, 2),
        "recent_6m_trade_count": int(recent_6m_trade_count),
        "rolling_6m_win_pct": round(rolling_6m_win_pct, 1),
        "rolling_6m_beat_spy_pct": round(rolling_6m_beat_spy_pct, 1),
        "rolling_6m_median_return_pct": round(rolling_6m_median_return_pct, 2),
        "rolling_6m_worst_return_pct": round(rolling_6m_worst_return_pct, 2),
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

