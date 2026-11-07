"""Deterministic Quantitative Backtesting Engine.

Key guarantees:
1. Chronological bar-by-bar simulation: Signals generated on Day T close are queued
   and executed at Day T+1 market open (plus half-spread and slippage), preventing look-ahead bias.
2. Point-in-time earnings & fundamental checks: AMC earnings on Day T are only visible starting Day T+1.
3. Survivorship-bias protection: Delisted securities (e.g., `FRC_DELIST`) remain in the historical
   universe until their delisting date, where any open position is forcibly liquidated on the final bar.
4. Transaction costs, bid-ask spreads, slippage, SEC regulatory fees, and dividends are accounted for.
5. Portfolio-level risk constraints (ATR sizing, max 10 positions, 15% single-stock cap, 30% sector cap,
   drawdown suspension) are enforced via `PortfolioRiskManager`.
6. Supports In-Sample / Validation / Out-of-Sample splits, Walk-Forward validation, Parameter Sensitivity,
   Regime Analysis, Transaction Cost Stress Testing, and Monte Carlo simulation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence

from core.indicators.technical import IndicatorSnapshot, compute_indicator_series
from core.market_data.models import DailyBar, EarningsEvent, EquityMetadata
from core.market_data.providers import MarketDataService
from core.risk.manager import PortfolioRiskManager
from core.strategies.registry import StrategyConfig, StrategySignalEngine, TradeSignal
from evaluation.metrics.performance import (
    calculate_performance_metrics,
    run_monte_carlo_trade_sequence,
)
from infrastructure.configuration.settings import (
    RiskParametersConfig,
    Settings,
    TransactionCostConfig,
)


@dataclass
class BacktestResult:
    experiment_id: str
    strategy_id: str
    strategy_version: int
    experiment_type: str  # FULL | IN_SAMPLE | VALIDATION | OUT_OF_SAMPLE | WALK_FORWARD | STRESS_TEST
    start_date: str
    end_date: str
    initial_capital: float
    final_equity: float
    metrics: Dict[str, Any]
    equity_curve: List[Dict[str, Any]]
    trades: List[Dict[str, Any]]
    regime_breakdown: Dict[str, Any]
    sector_breakdown: Dict[str, Any]
    monte_carlo: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BacktestEngine:
    """Deterministic event-driven daily swing backtesting engine."""

    def __init__(
        self,
        settings: Settings,
        market_data: MarketDataService,
        cost_config: Optional[TransactionCostConfig] = None,
        risk_config: Optional[RiskParametersConfig] = None,
    ) -> None:
        self.settings = settings
        self.market_data = market_data
        self.cost_config = cost_config or settings.costs
        self.risk_config = risk_config or settings.risk
        self.risk_manager = PortfolioRiskManager(self.risk_config, db=None)

    def _compute_execution_costs(
        self, side: str, shares: int, raw_price: float, cost_multiplier: float = 1.0
    ) -> tuple[float, float, float]:
        """Return (fill_price, commission_usd, slippage_and_spread_usd)."""
        half_spread_pct = (self.cost_config.default_half_spread_bps / 10_000.0) * cost_multiplier
        slippage_pct = (self.cost_config.default_slippage_bps / 10_000.0) * cost_multiplier
        total_friction_pct = half_spread_pct + slippage_pct

        if side.upper() == "BUY":
            fill_price = round(raw_price * (1.0 + total_friction_pct), 4)
        else:
            fill_price = round(max(0.01, raw_price * (1.0 - total_friction_pct)), 4)

        slippage_usd = round(abs(fill_price - raw_price) * shares, 2)
        comm = max(
            self.cost_config.min_commission_per_order,
            shares * self.cost_config.commission_per_share,
        ) * cost_multiplier
        if side.upper() == "SELL":
            comm += (shares * fill_price) * self.cost_config.sec_fee_per_dollar_sold
        return fill_price, round(comm, 2), slippage_usd

    def run_backtest(
        self,
        strategy: StrategyConfig,
        start_date: str,
        end_date: str,
        experiment_type: str = "FULL",
        initial_capital: Optional[float] = None,
        cost_multiplier: float = 1.0,
    ) -> BacktestResult:
        """Execute a strictly chronological backtest over `[start_date, end_date]`."""
        init_cap = initial_capital if initial_capital is not None else self.settings.initial_capital_usd
        universe_meta = self.market_data.get_universe_metadata(include_delisted=True)

        # Load historical bars with warmup buffer prior to start_date so 50d/200d indicators are ready
        spy_all_bars = self.market_data.get_bars(self.settings.benchmark_ticker, end_date=end_date)
        spy_indicators = compute_indicator_series(spy_all_bars)
        spy_bars_by_date = {b.bar_date: b for b in spy_all_bars}

        tickers = [t for t in strategy.universe if t != self.settings.benchmark_ticker]
        bars_by_ticker: Dict[str, Dict[str, DailyBar]] = {}
        indicators_by_ticker: Dict[str, Dict[str, IndicatorSnapshot]] = {}
        last_bar_date_by_ticker: Dict[str, str] = {}

        for ticker in tickers:
            t_bars = self.market_data.get_bars(ticker, end_date=end_date)
            if not t_bars:
                continue
            bars_by_ticker[ticker] = {b.bar_date: b for b in t_bars}
            indicators_by_ticker[ticker] = compute_indicator_series(t_bars, spy_bars=spy_all_bars)
            last_bar_date_by_ticker[ticker] = t_bars[-1].bar_date

        sim_dates = sorted(
            [b.bar_date for b in spy_all_bars if start_date <= b.bar_date <= end_date]
        )

        cash = init_cap
        peak_equity = init_cap
        kill_switch_engaged = False

        # Open positions: ticker -> dict
        open_positions: Dict[str, Dict[str, Any]] = {}
        pending_entry_signals: List[TradeSignal] = []
        pending_exit_signals: Dict[str, TradeSignal] = {}

        equity_curve: List[Dict[str, Any]] = []
        closed_trades: List[Dict[str, Any]] = []

        for day_idx, current_date in enumerate(sim_dates):
            # ------------------------------------------------------------------
            # STEP 1: At Market Open of `current_date`, execute pending exits & entries
            # generated from yesterday's close.
            # ------------------------------------------------------------------
            for ticker, exit_sig in list(pending_exit_signals.items()):
                if ticker not in open_positions:
                    continue
                pos = open_positions[ticker]
                bar = bars_by_ticker.get(ticker, {}).get(current_date)
                raw_exec_price = bar.adj_open if bar else pos["current_price"]
                fill_price, comm, slip = self._compute_execution_costs(
                    "SELL", pos["quantity"], raw_exec_price, cost_multiplier
                )
                proceeds = pos["quantity"] * fill_price - comm
                cash += proceeds
                gross_pnl = (fill_price - pos["avg_entry_price"]) * pos["quantity"]
                net_pnl = gross_pnl - comm - pos["entry_commission"] + pos.get("dividends_collected", 0.0)
                ret_pct = ((fill_price / pos["avg_entry_price"]) - 1.0) * 100.0

                closed_trades.append(
                    {
                        "trade_id": f"bt_trd_{uuid.uuid4().hex[:10]}",
                        "strategy_id": strategy.strategy_id,
                        "strategy_version": strategy.version,
                        "ticker": ticker,
                        "sector": pos["sector"],
                        "entry_date": pos["entry_date"],
                        "exit_date": current_date,
                        "holding_days": pos["holding_days"],
                        "quantity": pos["quantity"],
                        "entry_price": round(pos["avg_entry_price"], 4),
                        "exit_price": round(fill_price, 4),
                        "gross_pnl": round(gross_pnl, 2),
                        "net_pnl": round(net_pnl, 2),
                        "return_pct": round(ret_pct, 2),
                        "commission_usd": round(comm + pos["entry_commission"], 2),
                        "slippage_usd": round(slip + pos["entry_slippage"], 2),
                        "entry_reason": pos["entry_reason"],
                        "exit_reason": exit_sig.reason,
                        "market_regime": pos.get("entry_regime", "UNKNOWN"),
                    }
                )
                del open_positions[ticker]
            pending_exit_signals.clear()

            # Sort pending entries deterministically by conviction score descending
            pending_entry_signals.sort(key=lambda s: (-s.conviction_score, s.ticker))
            for entry_sig in pending_entry_signals:
                ticker = entry_sig.ticker
                bar = bars_by_ticker.get(ticker, {}).get(current_date)
                if bar is None:
                    continue
                ind_prev = indicators_by_ticker.get(ticker, {}).get(entry_sig.signal_date)
                meta = universe_meta.get(ticker)
                sector = meta.sector if meta else "Unknown"

                # Current portfolio equity at open before new entry
                pos_val_open = sum(
                    p["quantity"]
                    * (
                        bars_by_ticker.get(t, {}).get(current_date).adj_open
                        if bars_by_ticker.get(t, {}).get(current_date)
                        else p["current_price"]
                    )
                    for t, p in open_positions.items()
                )
                curr_eq_open = cash + pos_val_open

                # Adjust stop/target relative to actual open gap
                open_gap = bar.adj_open - entry_sig.close_at_signal
                adj_stop = (
                    round(max(0.01, entry_sig.stop_loss_price + open_gap), 2)
                    if entry_sig.stop_loss_price
                    else None
                )
                adj_tp = (
                    round(entry_sig.take_profit_price + open_gap, 2)
                    if entry_sig.take_profit_price
                    else None
                )

                upcoming_ev = self.market_data.get_upcoming_earnings_within_days(ticker, current_date, 3)
                days_to_earn = 1 if upcoming_ev else None

                decision = self.risk_manager.evaluate_proposed_entry(
                    account_id="backtest",
                    eval_date=current_date,
                    ticker=ticker,
                    sector=sector,
                    strategy_id=strategy.strategy_id,
                    strategy_family=strategy.strategy_family,
                    entry_price=bar.adj_open,
                    stop_loss_price=adj_stop,
                    atr_14=entry_sig.atr_at_signal,
                    portfolio_equity=curr_eq_open,
                    peak_equity=peak_equity,
                    available_cash=cash,
                    open_positions=open_positions,
                    avg_daily_dollar_volume_20d=ind_prev.avg_dollar_volume_20d if ind_prev else None,
                    upcoming_earnings_days=days_to_earn,
                    kill_switch_engaged=kill_switch_engaged,
                    strategy_risk_pct=strategy.risk_params.get("risk_per_trade_pct"),
                    strategy_max_exp_pct=strategy.risk_params.get("max_position_exposure_pct"),
                )

                if not decision.approved or decision.recommended_shares <= 0:
                    if decision.rule_triggered == "MAX_DRAWDOWN_SUSPENSION":
                        kill_switch_engaged = True
                    continue

                shares = decision.recommended_shares
                fill_price, comm, slip = self._compute_execution_costs(
                    "BUY", shares, bar.adj_open, cost_multiplier
                )
                total_cost = shares * fill_price + comm
                if total_cost > cash:
                    shares = int((cash - comm) // fill_price)
                    if shares <= 0:
                        continue
                    total_cost = shares * fill_price + comm

                cash -= total_cost
                spy_ind_now = spy_indicators.get(current_date)
                entry_regime = self._classify_regime(spy_ind_now)

                open_positions[ticker] = {
                    "ticker": ticker,
                    "sector": sector,
                    "quantity": shares,
                    "avg_entry_price": fill_price,
                    "current_price": bar.adj_close,
                    "highest_price_since_entry": max(fill_price, bar.adj_high),
                    "stop_loss_price": adj_stop,
                    "take_profit_price": adj_tp,
                    "entry_date": current_date,
                    "holding_days": 0,
                    "entry_commission": comm,
                    "entry_slippage": slip,
                    "dividends_collected": 0.0,
                    "entry_reason": entry_sig.reason,
                    "entry_regime": entry_regime,
                }
            pending_entry_signals.clear()

            # ------------------------------------------------------------------
            # STEP 2: Intraday & Market Close updates for open positions
            # (dividends, delisting check, stop/exit evaluation for next open)
            # ------------------------------------------------------------------
            for ticker, pos in list(open_positions.items()):
                bar = bars_by_ticker.get(ticker, {}).get(current_date)
                if bar is not None:
                    pos["current_price"] = bar.adj_close
                    pos["highest_price_since_entry"] = max(
                        pos["highest_price_since_entry"], bar.adj_high
                    )
                    pos["holding_days"] += 1
                    if bar.dividend_amount > 0:
                        div_cash = pos["quantity"] * bar.dividend_amount
                        cash += div_cash
                        pos["dividends_collected"] += div_cash

                # Survivorship bias protection: if security delists on `current_date`, liquidate at close
                meta = universe_meta.get(ticker)
                is_delisting_today = (
                    (meta is not None and meta.delisted_date == current_date)
                    or last_bar_date_by_ticker.get(ticker) == current_date
                    and meta is not None
                    and not meta.is_active
                )
                if is_delisting_today:
                    fill_price, comm, slip = self._compute_execution_costs(
                        "SELL", pos["quantity"], pos["current_price"], cost_multiplier
                    )
                    cash += pos["quantity"] * fill_price - comm
                    gross_pnl = (fill_price - pos["avg_entry_price"]) * pos["quantity"]
                    net_pnl = gross_pnl - comm - pos["entry_commission"] + pos["dividends_collected"]
                    closed_trades.append(
                        {
                            "trade_id": f"bt_trd_{uuid.uuid4().hex[:10]}",
                            "strategy_id": strategy.strategy_id,
                            "strategy_version": strategy.version,
                            "ticker": ticker,
                            "sector": pos["sector"],
                            "entry_date": pos["entry_date"],
                            "exit_date": current_date,
                            "holding_days": pos["holding_days"],
                            "quantity": pos["quantity"],
                            "entry_price": round(pos["avg_entry_price"], 4),
                            "exit_price": round(fill_price, 4),
                            "gross_pnl": round(gross_pnl, 2),
                            "net_pnl": round(net_pnl, 2),
                            "return_pct": round(((fill_price / pos["avg_entry_price"]) - 1.0) * 100.0, 2),
                            "commission_usd": round(comm + pos["entry_commission"], 2),
                            "slippage_usd": round(slip + pos["entry_slippage"], 2),
                            "entry_reason": pos["entry_reason"],
                            "exit_reason": f"Delisting liquidation on {current_date}",
                            "market_regime": pos.get("entry_regime", "UNKNOWN"),
                        }
                    )
                    del open_positions[ticker]
                    continue

                ind = indicators_by_ticker.get(ticker, {}).get(current_date)
                if ind is not None:
                    exit_sig = StrategySignalEngine.evaluate_exit(
                        config=strategy,
                        ind=ind,
                        entry_price=pos["avg_entry_price"],
                        highest_price_since_entry=pos["highest_price_since_entry"],
                        holding_days=pos["holding_days"],
                        stop_loss_price=pos["stop_loss_price"],
                        take_profit_price=pos["take_profit_price"],
                    )
                    if exit_sig is not None:
                        pending_exit_signals[ticker] = exit_sig

            # ------------------------------------------------------------------
            # STEP 3: Update End-of-Day Portfolio Valuation & Drawdown
            # ------------------------------------------------------------------
            positions_val = sum(
                p["quantity"] * p["current_price"] for p in open_positions.values()
            )
            total_equity = cash + positions_val
            if total_equity > peak_equity:
                peak_equity = total_equity
            dd_pct = ((peak_equity - total_equity) / peak_equity) if peak_equity > 0 else 0.0
            if dd_pct >= self.risk_config.drawdown_suspension_threshold_pct:
                kill_switch_engaged = True

            spy_bar = spy_bars_by_date.get(current_date)
            equity_curve.append(
                {
                    "date": current_date,
                    "cash": round(cash, 2),
                    "positions_value": round(positions_val, 2),
                    "equity": round(total_equity, 2),
                    "drawdown_pct": round(dd_pct * 100.0, 2),
                    "open_positions": len(open_positions),
                    "spy_close": spy_bar.adj_close if spy_bar else None,
                }
            )

            # ------------------------------------------------------------------
            # STEP 4: Generate End-of-Day Entry Signals for Day T+1 Open
            # ------------------------------------------------------------------
            if not kill_switch_engaged and day_idx < len(sim_dates) - 1:
                spy_ind = spy_indicators.get(current_date)
                for ticker in tickers:
                    if ticker in open_positions or ticker in pending_exit_signals:
                        continue
                    ind = indicators_by_ticker.get(ticker, {}).get(current_date)
                    if ind is None:
                        continue
                    recent_ev = self.market_data.get_point_in_time_earnings(
                        ticker, current_date, lookback_days=10
                    )
                    sig = StrategySignalEngine.evaluate_entry(
                        config=strategy,
                        ind=ind,
                        spy_ind=spy_ind,
                        recent_earnings=recent_ev,
                    )
                    if sig is not None:
                        pending_entry_signals.append(sig)

        metrics = calculate_performance_metrics(
            equity_curve=equity_curve,
            trades=closed_trades,
            initial_capital=init_cap,
            spy_bars=spy_all_bars,
        )
        regime_breakdown = self._summarize_by_key(closed_trades, "market_regime")
        sector_breakdown = self._summarize_by_key(closed_trades, "sector")
        mc = run_monte_carlo_trade_sequence(closed_trades, initial_capital=init_cap)

        return BacktestResult(
            experiment_id=f"exp_{strategy.strategy_id}_v{strategy.version}_{experiment_type.lower()}_{uuid.uuid4().hex[:8]}",
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            experiment_type=experiment_type,
            start_date=start_date,
            end_date=end_date,
            initial_capital=init_cap,
            final_equity=metrics.get("final_equity", init_cap),
            metrics=metrics,
            equity_curve=equity_curve,
            trades=closed_trades,
            regime_breakdown=regime_breakdown,
            sector_breakdown=sector_breakdown,
            monte_carlo=mc,
        )

    def run_in_sample_validation_oos_pipeline(
        self,
        strategy: StrategyConfig,
        in_sample_range: tuple[str, str] = ("2023-03-01", "2024-02-29"),
        validation_range: tuple[str, str] = ("2024-03-01", "2024-09-30"),
        oos_range: tuple[str, str] = ("2024-10-01", "2025-06-30"),
    ) -> Dict[str, Any]:
        """Execute strict three-split evaluation (In-Sample -> Validation -> Untouched Out-of-Sample)."""
        is_res = self.run_backtest(strategy, in_sample_range[0], in_sample_range[1], "IN_SAMPLE")
        val_res = self.run_backtest(strategy, validation_range[0], validation_range[1], "VALIDATION")
        oos_res = self.run_backtest(strategy, oos_range[0], oos_range[1], "OUT_OF_SAMPLE")
        full_res = self.run_backtest(strategy, in_sample_range[0], oos_range[1], "FULL")
        wf_res = self.run_walk_forward_validation(strategy, in_sample_range[0], oos_range[1], num_windows=4)
        stress_res = self.run_transaction_cost_stress_test(strategy, oos_range[0], oos_range[1])

        return {
            "in_sample": is_res.to_dict(),
            "validation": val_res.to_dict(),
            "out_of_sample": oos_res.to_dict(),
            "full_period": full_res.to_dict(),
            "walk_forward": wf_res,
            "stress_test": stress_res,
        }

    def run_walk_forward_validation(
        self,
        strategy: StrategyConfig,
        start_date: str,
        end_date: str,
        num_windows: int = 4,
    ) -> Dict[str, Any]:
        """Run rolling walk-forward evaluation across `num_windows` contiguous out-of-sample folds."""
        spy_bars = self.market_data.get_bars(
            self.settings.benchmark_ticker, start_date=start_date, end_date=end_date
        )
        dates = [b.bar_date for b in spy_bars]
        if len(dates) < num_windows * 20:
            return {"windows": [], "consistency_ratio": 0.0, "profitable_windows": 0, "total_windows": 0}

        chunk_size = len(dates) // num_windows
        windows: List[Dict[str, Any]] = []
        profitable_count = 0

        for w in range(num_windows):
            w_start = dates[w * chunk_size]
            w_end = dates[-1] if w == num_windows - 1 else dates[(w + 1) * chunk_size - 1]
            res = self.run_backtest(strategy, w_start, w_end, experiment_type=f"WF_WINDOW_{w+1}")
            tot_ret = float(res.metrics.get("total_return_pct", 0.0))
            if tot_ret > 0.0:
                profitable_count += 1
            windows.append(
                {
                    "window_index": w + 1,
                    "start_date": w_start,
                    "end_date": w_end,
                    "total_return_pct": tot_ret,
                    "sharpe_ratio": res.metrics.get("sharpe_ratio", 0.0),
                    "max_drawdown_pct": res.metrics.get("max_drawdown_pct", 0.0),
                    "trade_count": res.metrics.get("trade_count", 0),
                }
            )

        consistency = profitable_count / num_windows if num_windows > 0 else 0.0
        return {
            "windows": windows,
            "profitable_windows": profitable_count,
            "total_windows": num_windows,
            "consistency_ratio": round(consistency, 3),
        }

    def run_transaction_cost_stress_test(
        self,
        strategy: StrategyConfig,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """Test strategy robustness under 1x (baseline), 2x (elevated), and 3x (severe) slippage/spread costs."""
        res_1x = self.run_backtest(strategy, start_date, end_date, "STRESS_1X", cost_multiplier=1.0)
        res_2x = self.run_backtest(strategy, start_date, end_date, "STRESS_2X", cost_multiplier=2.0)
        res_3x = self.run_backtest(strategy, start_date, end_date, "STRESS_3X", cost_multiplier=3.0)
        return {
            "baseline_1x_return_pct": res_1x.metrics["total_return_pct"],
            "double_cost_2x_return_pct": res_2x.metrics["total_return_pct"],
            "triple_cost_3x_return_pct": res_3x.metrics["total_return_pct"],
            "survives_2x_costs": res_2x.metrics["total_return_pct"] > 0.0,
        }

    @staticmethod
    def _classify_regime(spy_ind: Optional[IndicatorSnapshot]) -> str:
        if spy_ind is None:
            return "UNKNOWN"
        vol = spy_ind.realised_vol_20d_annualised or 15.0
        above_sma50 = spy_ind.sma_50 is not None and spy_ind.close >= spy_ind.sma_50
        if above_sma50 and vol < 18.0:
            return "BULL_LOW_VOL"
        if above_sma50 and vol >= 18.0:
            return "BULL_HIGH_VOL"
        if not above_sma50 and vol >= 20.0:
            return "BEAR_VOLATILE"
        return "SIDEWAYS_CHOPPY"

    @staticmethod
    def _summarize_by_key(trades: Sequence[Dict[str, Any]], key: str) -> Dict[str, Any]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for t in trades:
            k = str(t.get(key, "UNKNOWN"))
            groups.setdefault(k, []).append(t)
        summary: Dict[str, Any] = {}
        for k, grp in groups.items():
            pnls = [float(x["net_pnl"]) for x in grp]
            wins = [p for p in pnls if p > 0]
            summary[k] = {
                "trade_count": len(grp),
                "total_net_pnl": round(sum(pnls), 2),
                "win_rate_pct": round((len(wins) / len(grp)) * 100.0, 2) if grp else 0.0,
                "avg_return_pct": round(
                    sum(float(x.get("return_pct", 0.0)) for x in grp) / len(grp), 2
                )
                if grp
                else 0.0,
            }
        return summary

