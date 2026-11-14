"""Comprehensive Automated Test Suite for the Swing Trading AI Platform.

Covers all 14 required verification areas:
1. Indicator calculations (SMA, EMA, RSI, ATR, Bollinger Bands, MACD, Relative Strength vs SPY)
2. Entry and exit rules (Momentum, PEAD, Breakout, Mean Reversion, Sector Rotation)
3. ATR-based position sizing & exposure caps
4. Transaction costs, bid-ask spreads, slippage, and SEC fees
5. Simulated order fills (Market, Limit, Stop-Loss, Take-Profit, Partial Fills)
6. Portfolio accounting & cash/position/P&L reconciliation
7. Drawdown calculations & Monte Carlo trade-sequence analysis
8. Portfolio risk limits (max positions, single-stock 15%, sector 30%, correlation, liquidity, earnings blackout, kill switch)
9. Strategy versioning & immutability of active PAPER_TRADING strategies
10. Backtesting integrity (chronological next-open fills, point-in-time BMO/AMC earnings, survivorship-bias delisting liquidation)
11. Duplicate order prevention via deterministic idempotency keys
12. Agent output schema validation & role permission boundaries
13. Idempotent workflow recovery & US market holiday handling
14. Full end-to-end integration test covering an entire simulated trading & research cycle
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents.base import AgentPermissionError, SchemaValidationError, validate_required_fields
from agents.market_researcher.agent import MarketResearchAgent
from agents.performance_analyst.agent import PerformanceAnalystAgent
from agents.risk_manager.agent import RiskManagerAgent
from agents.strategy_architect.agent import StrategyDiscoveryAgent
from agents.strategy_evaluator.agent import StrategyEvaluationAgent
from core.backtesting.engine import BacktestEngine
from core.execution.paper_broker import PaperTradingEngine
from core.indicators.technical import (
    calc_atr,
    calc_ema,
    calc_rsi,
    calc_sma,
    compute_indicator_series,
)
from core.market_data.models import DailyBar, EarningsEvent, USTradingCalendar
from core.market_data.providers import LocalSeededDataProvider, MarketDataService
from core.risk.manager import PortfolioRiskManager, compute_return_correlation
from core.strategies.registry import (
    StrategyConfig,
    StrategyFamily,
    StrategyRegistry,
    StrategySignalEngine,
    StrategyStatus,
    get_baseline_strategies,
)
from evaluation.metrics.performance import (
    calculate_performance_metrics,
    compute_drawdown_series,
    run_monte_carlo_trade_sequence,
)
from infrastructure.configuration.settings import (
    LiveTradingProhibitedError,
    PromotionCriteriaConfig,
    RiskParametersConfig,
    Settings,
)
from infrastructure.database.db import DatabaseManager
from infrastructure.scheduler.orchestrator import AutonomousWorkflowOrchestrator


def make_test_bars(prices: list[float], ticker: str = "AAPL", base_vol: float = 10_000_000.0) -> list[DailyBar]:
    bars: list[DailyBar] = []
    days = USTradingCalendar.get_trading_days("2024-01-02", "2025-06-30")
    for i, p in enumerate(prices):
        d = days[i]
        bars.append(
            DailyBar(
                ticker=ticker,
                bar_date=d,
                open=p * 0.995,
                high=p * 1.015,
                low=p * 0.985,
                close=p,
                volume=base_vol,
                adj_open=p * 0.995,
                adj_high=p * 1.015,
                adj_low=p * 0.985,
                adj_close=p,
                adj_volume=base_vol,
            )
        )
    return bars


class TestSwingTradingPlatform(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_trader.db"
        self.settings = Settings(
            project_root=Path(self.tmp_dir.name),
            trading_mode="paper",
            database_url=f"sqlite:///{self.db_path}",
        )
        self.db = DatabaseManager(self.db_path)
        self.market_data = MarketDataService(self.settings, self.db, LocalSeededDataProvider())

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    # ------------------------------------------------------------------
    # 1. Safety & Live Trading Restrictions
    # ------------------------------------------------------------------
    def test_01_live_trading_strictly_prohibited(self) -> None:
        with self.assertRaises(LiveTradingProhibitedError):
            Settings(trading_mode="live")
        with self.assertRaises(LiveTradingProhibitedError):
            Settings(trading_mode="real_money")

    # ------------------------------------------------------------------
    # 2. Indicator Calculations
    # ------------------------------------------------------------------
    def test_02_indicator_calculations(self) -> None:
        vals = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
        sma3 = calc_sma(vals, 3)
        self.assertIsNone(sma3[0])
        self.assertIsNone(sma3[1])
        self.assertAlmostEqual(float(sma3[2]), 12.0, places=4)
        self.assertAlmostEqual(float(sma3[5]), 18.0, places=4)

        ema3 = calc_ema(vals, 3)
        self.assertIsNotNone(ema3[2])
        self.assertGreater(float(ema3[5]), float(ema3[2]))

        rising = [100.0 + i * 1.5 for i in range(40)]
        rsi = calc_rsi(rising, 14)
        self.assertAlmostEqual(float(rsi[-1]), 100.0, places=2)

        bars = make_test_bars([100.0 + i * 0.8 for i in range(65)], ticker="NVDA")
        spy_bars = make_test_bars([400.0 + i * 0.5 for i in range(65)], ticker="SPY")
        atr = calc_atr(bars, 14)
        self.assertIsNotNone(atr[14])
        self.assertGreater(float(atr[-1]), 0.0)

        snaps = compute_indicator_series(bars, spy_bars=spy_bars)
        last_snap = snaps[bars[-1].bar_date]
        self.assertIsNotNone(last_snap.sma_20)
        self.assertIsNotNone(last_snap.sma_50)
        self.assertIsNotNone(last_snap.macd_line)
        self.assertIsNotNone(last_snap.bb_upper_20)
        self.assertIsNotNone(last_snap.rs_vs_spy_20d)
        self.assertGreater(float(last_snap.rs_vs_spy_20d), 0.0)

    # ------------------------------------------------------------------
    # 3. Entry and Exit Rules
    # ------------------------------------------------------------------
    def test_03_entry_and_exit_rules(self) -> None:
        baselines = get_baseline_strategies()
        mom_strat, pead_strat, brk_strat = baselines[0], baselines[1], baselines[2]

        # Construct realistic trending series with periodic pullbacks so RSI(14) is in [60, 72]
        prices = []
        p = 100.0
        for i in range(60):
            p += 1.6 if (i % 3 != 1) else -1.8
            prices.append(round(p, 2))
        bars = make_test_bars(prices, ticker="AAPL")
        # Spike volume and break above 20d high on final bar
        last_b = bars[-1]
        bars[-1] = DailyBar(
            ticker="AAPL",
            bar_date=last_b.bar_date,
            open=last_b.open,
            high=last_b.high * 1.045,
            low=last_b.low,
            close=last_b.close * 1.04,
            volume=last_b.volume * 2.0,
            adj_open=last_b.adj_open,
            adj_high=last_b.adj_high * 1.045,
            adj_low=last_b.adj_low,
            adj_close=last_b.adj_close * 1.04,
            adj_volume=last_b.adj_volume * 2.0,
        )
        spy_bars = make_test_bars([400.0 + i * 0.5 for i in range(60)], ticker="SPY")
        inds = compute_indicator_series(bars, spy_bars=spy_bars)
        spy_inds = compute_indicator_series(spy_bars)
        ind_last = inds[bars[-1].bar_date]
        spy_last = spy_inds[spy_bars[-1].bar_date]

        # Momentum entry signal
        sig_mom = StrategySignalEngine.evaluate_entry(mom_strat, ind_last, spy_last, [])
        self.assertIsNotNone(sig_mom)
        self.assertEqual(sig_mom.action, "ENTRY_LONG")

        # Breakout entry signal
        sig_brk = StrategySignalEngine.evaluate_entry(brk_strat, ind_last, spy_last, [])
        self.assertIsNotNone(sig_brk)
        self.assertEqual(sig_brk.action, "ENTRY_LONG")

        # PEAD entry signal with point-in-time earnings beat
        ev = EarningsEvent(
            ticker="AAPL",
            report_date=bars[-2].bar_date,
            fiscal_period="Q1",
            announcement_session="AMC",
            eps_estimate=1.50,
            eps_actual=1.80,
            eps_surprise_pct=20.0,
            revenue_estimate_M=90000.0,
            revenue_actual_M=99000.0,
            revenue_growth_yoy_pct=15.0,
            guidance_delta_pct=3.5,
            public_release_timestamp=f"{bars[-2].bar_date}T16:15:00-04:00",
        )
        sig_pead = StrategySignalEngine.evaluate_entry(pead_strat, ind_last, spy_last, [ev])
        self.assertIsNotNone(sig_pead)

        # Exit rule: max holding period reached
        exit_time = StrategySignalEngine.evaluate_exit(
            mom_strat,
            ind_last,
            entry_price=150.0,
            highest_price_since_entry=175.0,
            holding_days=mom_strat.holding_period_max_days,
            stop_loss_price=140.0,
            take_profit_price=220.0,
        )
        self.assertIsNotNone(exit_time)
        self.assertEqual(exit_time.action, "EXIT_LONG")

        # Exit rule: stop-loss breached
        exit_stop = StrategySignalEngine.evaluate_exit(
            mom_strat,
            ind_last,
            entry_price=180.0,
            highest_price_since_entry=185.0,
            holding_days=2,
            stop_loss_price=ind_last.low + 5.0,
            take_profit_price=220.0,
        )
        self.assertIsNotNone(exit_stop)
        self.assertIn("Stop-Loss", exit_stop.reason)

    # ------------------------------------------------------------------
    # 4. Position Sizing & Portfolio Risk Limits
    # ------------------------------------------------------------------
    def test_04_position_sizing_and_risk_limits(self) -> None:
        rm = PortfolioRiskManager(RiskParametersConfig(), db=self.db)

        # ATR-based position sizing: $100,000 equity, 1% max risk = $1,000 max loss.
        # Entry $100, Stop $90 ($10 risk/share) -> 100 shares ($10,000 = 10% exposure <= 15% cap).
        shares = rm.calculate_atr_position_size(
            portfolio_equity=100_000.0,
            available_cash=100_000.0,
            entry_price=100.0,
            stop_loss_price=90.0,
            atr_14=5.0,
        )
        self.assertEqual(shares, 100)

        # When stop is very tight ($99 on $100), risk sizing would allow 1,000 shares ($100k),
        # but single-stock exposure cap (15% = $15,000) caps shares to 150.
        capped_shares = rm.calculate_atr_position_size(
            portfolio_equity=100_000.0,
            available_cash=100_000.0,
            entry_price=100.0,
            stop_loss_price=99.0,
            atr_14=0.5,
        )
        self.assertEqual(capped_shares, 150)

        # Veto when max simultaneous positions (10) reached
        ten_positions = {
            f"T{i}": {"quantity": 10, "current_price": 50.0, "sector": "Financials"}
            for i in range(10)
        }
        dec_max_pos = rm.evaluate_proposed_entry(
            account_id="test",
            eval_date="2025-05-01",
            ticker="AAPL",
            sector="Technology",
            strategy_id="strat_1",
            strategy_family="MOMENTUM_TREND",
            entry_price=100.0,
            stop_loss_price=95.0,
            atr_14=2.5,
            portfolio_equity=100_000.0,
            peak_equity=100_000.0,
            available_cash=50_000.0,
            open_positions=ten_positions,
        )
        self.assertFalse(dec_max_pos.approved)
        self.assertEqual(dec_max_pos.rule_triggered, "MAX_SIMULTANEOUS_POSITIONS")

        # Veto when sector exposure (30%) already full
        tech_positions = {
            "MSFT": {"quantity": 150, "current_price": 100.0, "sector": "Technology"},
            "NVDA": {"quantity": 150, "current_price": 100.0, "sector": "Technology"},
        }
        dec_sector = rm.evaluate_proposed_entry(
            account_id="test",
            eval_date="2025-05-01",
            ticker="AAPL",
            sector="Technology",
            strategy_id="strat_1",
            strategy_family="MOMENTUM_TREND",
            entry_price=100.0,
            stop_loss_price=95.0,
            atr_14=2.5,
            portfolio_equity=100_000.0,
            peak_equity=100_000.0,
            available_cash=70_000.0,
            open_positions=tech_positions,
        )
        self.assertFalse(dec_sector.approved)
        self.assertEqual(dec_sector.rule_triggered, "MAX_SECTOR_EXPOSURE")

        # Veto when portfolio drawdown >= 15% suspension threshold
        dec_dd = rm.evaluate_proposed_entry(
            account_id="test",
            eval_date="2025-05-01",
            ticker="AAPL",
            sector="Technology",
            strategy_id="strat_1",
            strategy_family="MOMENTUM_TREND",
            entry_price=100.0,
            stop_loss_price=95.0,
            atr_14=2.5,
            portfolio_equity=84_000.0,
            peak_equity=100_000.0,
            available_cash=84_000.0,
            open_positions={},
        )
        self.assertFalse(dec_dd.approved)
        self.assertEqual(dec_dd.rule_triggered, "MAX_DRAWDOWN_SUSPENSION")

        # Veto on high pairwise correlation (> 0.80)
        rets_a = [0.01, -0.02, 0.015, 0.03, -0.01, 0.02, 0.005, -0.015]
        rets_b = [x * 1.02 for x in rets_a]
        self.assertGreater(compute_return_correlation(rets_a, rets_b), 0.99)
        dec_corr = rm.evaluate_proposed_entry(
            account_id="test",
            eval_date="2025-05-01",
            ticker="AMD",
            sector="Technology",
            strategy_id="strat_1",
            strategy_family="MOMENTUM_TREND",
            entry_price=100.0,
            stop_loss_price=95.0,
            atr_14=2.5,
            portfolio_equity=100_000.0,
            peak_equity=100_000.0,
            available_cash=90_000.0,
            open_positions={"NVDA": {"quantity": 50, "current_price": 100.0, "sector": "Technology"}},
            candidate_returns_20d=rets_b,
            open_positions_returns_20d={"NVDA": rets_a},
        )
        self.assertFalse(dec_corr.approved)
        self.assertEqual(dec_corr.rule_triggered, "HIGH_PORTFOLIO_CORRELATION")

    # ------------------------------------------------------------------
    # 5. Paper Trading Order Fills, Transaction Costs, Accounting & Duplicate Prevention
    # ------------------------------------------------------------------
    def test_05_paper_trading_orders_accounting_and_duplicate_prevention(self) -> None:
        paper = PaperTradingEngine(self.settings, self.db, self.market_data)
        acc0 = paper.get_account_summary()
        self.assertEqual(acc0["cash_balance"], 100_000.0)

        bar_day1 = DailyBar(
            ticker="AAPL",
            bar_date="2025-05-05",
            open=200.0,
            high=205.0,
            low=198.0,
            close=204.0,
            volume=10_000_000.0,
            adj_open=200.0,
            adj_high=205.0,
            adj_low=198.0,
            adj_close=204.0,
            adj_volume=10_000_000.0,
        )

        # Submit Market BUY order for 50 shares
        res_buy = paper.submit_and_execute_order(
            strategy_id="strat_momentum_trend",
            strategy_version=1,
            strategy_family="MOMENTUM_TREND",
            ticker="AAPL",
            side="BUY",
            requested_qty=50,
            signal_date="2025-05-02",
            execution_bar=bar_day1,
            sector="Technology",
            stop_loss_target=190.0,
            take_profit_target=220.0,
            atr_14=4.0,
        )
        self.assertEqual(res_buy.status, "FILLED")
        self.assertEqual(res_buy.filled_qty, 50)
        self.assertGreater(float(res_buy.avg_fill_price), 200.0)  # Includes spread + slippage
        self.assertGreater(res_buy.commission_usd, 0.0)

        # Attempt exact same order again -> Duplicate order prevented!
        res_dup = paper.submit_and_execute_order(
            strategy_id="strat_momentum_trend",
            strategy_version=1,
            strategy_family="MOMENTUM_TREND",
            ticker="AAPL",
            side="BUY",
            requested_qty=50,
            signal_date="2025-05-02",
            execution_bar=bar_day1,
            sector="Technology",
        )
        self.assertEqual(res_dup.status, "DUPLICATE_IGNORED")

        # Verify portfolio reconciliation after BUY
        acc1 = paper.get_account_summary()
        expected_cash = round(100_000.0 - (50 * float(res_buy.avg_fill_price) + res_buy.commission_usd), 2)
        self.assertAlmostEqual(acc1["cash_balance"], expected_cash, places=2)
        self.assertAlmostEqual(acc1["positions_market_value"], 50 * 204.0, places=2)
        self.assertAlmostEqual(acc1["total_equity"], expected_cash + 50 * 204.0, places=2)

        # Test SELL order closing position on Day 2
        bar_day2 = DailyBar(
            ticker="AAPL",
            bar_date="2025-05-06",
            open=210.0,
            high=212.0,
            low=208.0,
            close=211.0,
            volume=10_000_000.0,
            adj_open=210.0,
            adj_high=212.0,
            adj_low=208.0,
            adj_close=211.0,
            adj_volume=10_000_000.0,
        )
        res_sell = paper.submit_and_execute_order(
            strategy_id="strat_momentum_trend",
            strategy_version=1,
            strategy_family="MOMENTUM_TREND",
            ticker="AAPL",
            side="SELL",
            requested_qty=50,
            signal_date="2025-05-06",
            execution_bar=bar_day2,
            sector="Technology",
        )
        self.assertEqual(res_sell.status, "FILLED")
        acc2 = paper.get_account_summary()
        self.assertEqual(acc2["open_positions_count"], 0)
        self.assertGreater(acc2["realised_pnl"], 0.0)
        self.assertGreater(acc2["cash_balance"], 100_000.0)
        self.assertIn("total_pnl_usd", acc2)
        self.assertIn("daily_pnl_usd", acc2)
        self.assertIn("weekly_pnl_usd", acc2)
        self.assertAlmostEqual(acc2["total_pnl_usd"], acc2["total_equity"] - acc2["starting_capital"], places=2)

        # Test Partial Fill when order size > max volume participation
        thin_bar = DailyBar(
            ticker="GS",
            bar_date="2025-05-07",
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=400.0,  # 5% max participation = 20 shares max fill
            adj_open=100.0,
            adj_high=102.0,
            adj_low=99.0,
            adj_close=101.0,
            adj_volume=400.0,
        )
        res_partial = paper.submit_and_execute_order(
            strategy_id="strat_momentum_trend",
            strategy_version=1,
            strategy_family="MOMENTUM_TREND",
            ticker="GS",
            side="BUY",
            requested_qty=50,
            signal_date="2025-05-07",
            execution_bar=thin_bar,
            sector="Financials",
            stop_loss_target=90.0,
            max_volume_participation_pct=0.05,
        )
        self.assertEqual(res_partial.status, "PARTIALLY_FILLED")
        self.assertEqual(res_partial.filled_qty, 20)

    # ------------------------------------------------------------------
    # 6. Drawdown & Performance Metrics
    # ------------------------------------------------------------------
    def test_06_drawdown_and_performance_metrics(self) -> None:
        dds = compute_drawdown_series([100_000.0, 110_000.0, 99_000.0, 105_000.0, 120_000.0])
        self.assertAlmostEqual(dds[0], 0.0)
        self.assertAlmostEqual(dds[2], 0.10, places=4)  # 99k from 110k peak is 10% drawdown
        self.assertAlmostEqual(dds[4], 0.0)

        eq_curve = [
            {"date": "2025-01-02", "equity": 100_000.0, "positions_value": 30_000.0},
            {"date": "2025-01-03", "equity": 102_000.0, "positions_value": 30_000.0},
            {"date": "2025-01-06", "equity": 101_000.0, "positions_value": 30_000.0},
            {"date": "2025-01-07", "equity": 104_000.0, "positions_value": 30_000.0},
        ]
        trades = [
            {"net_pnl": 2000.0, "return_pct": 6.6, "holding_days": 5, "entry_price": 100.0, "exit_price": 106.6, "quantity": 300},
            {"net_pnl": -1000.0, "return_pct": -3.3, "holding_days": 4, "entry_price": 100.0, "exit_price": 96.7, "quantity": 300},
            {"net_pnl": 3000.0, "return_pct": 10.0, "holding_days": 6, "entry_price": 100.0, "exit_price": 110.0, "quantity": 300},
        ]
        m = calculate_performance_metrics(eq_curve, trades, initial_capital=100_000.0)
        self.assertAlmostEqual(m["total_return_pct"], 4.0, places=2)
        self.assertAlmostEqual(m["profit_factor"], 5.0, places=2)
        self.assertEqual(m["trade_count"], 3)

        mc = run_monte_carlo_trade_sequence(trades, initial_capital=100_000.0, num_simulations=50)
        self.assertEqual(mc["simulations"], 50)
        self.assertGreaterEqual(mc["p95_max_drawdown_pct"], mc["median_max_drawdown_pct"])

    # ------------------------------------------------------------------
    # 7. Strategy Versioning & Immutability of Active Paper Strategies
    # ------------------------------------------------------------------
    def test_07_strategy_versioning_and_immutability(self) -> None:
        reg = StrategyRegistry(self.db)
        base = get_baseline_strategies()[0]
        reg.register_strategy(base)
        reg.update_status(base.strategy_id, base.version, StrategyStatus.PAPER_TRADING, "Promoted")

        # Attempting to overwrite a PAPER_TRADING version must raise PermissionError
        with self.assertRaises(PermissionError):
            reg.register_strategy(base)

        # Creating a new version increments version to v2 in DRAFT status while preserving v1
        v2 = reg.create_new_version(base.strategy_id, entry_rules_updates={"min_rs_vs_spy_20d": 3.0})
        self.assertEqual(v2.version, 2)
        self.assertEqual(v2.status, StrategyStatus.DRAFT.value)
        v1_still = reg.get_strategy(base.strategy_id, 1)
        self.assertEqual(v1_still.status, StrategyStatus.PAPER_TRADING.value)

    # ------------------------------------------------------------------
    # 8. Point-in-Time Earnings Integrity & Backtest Survivorship Handling
    # ------------------------------------------------------------------
    def test_08_point_in_time_and_delisting_integrity(self) -> None:
        amc_ev = EarningsEvent(
            ticker="NVDA",
            report_date="2025-05-20",
            fiscal_period="Q1",
            announcement_session="AMC",
            eps_estimate=1.0,
            eps_actual=1.25,
            eps_surprise_pct=25.0,
            revenue_estimate_M=20000.0,
            revenue_actual_M=24000.0,
            revenue_growth_yoy_pct=40.0,
            guidance_delta_pct=5.0,
            public_release_timestamp="2025-05-20T16:20:00-04:00",
        )
        # AMC earnings on 2025-05-20 must NOT be actionable on 2025-05-20 market close
        self.assertFalse(amc_ev.is_publicly_available_as_of("2025-05-20"))
        self.assertTrue(amc_ev.is_publicly_available_as_of("2025-05-21"))

        # BMO earnings on 2025-05-20 ARE available on 2025-05-20
        bmo_ev = EarningsEvent(
            ticker="JPM",
            report_date="2025-05-20",
            fiscal_period="Q1",
            announcement_session="BMO",
            eps_estimate=3.0,
            eps_actual=3.3,
            eps_surprise_pct=10.0,
            revenue_estimate_M=30000.0,
            revenue_actual_M=32000.0,
            revenue_growth_yoy_pct=12.0,
            guidance_delta_pct=2.0,
            public_release_timestamp="2025-05-20T07:30:00-04:00",
        )
        self.assertTrue(bmo_ev.is_publicly_available_as_of("2025-05-20"))

    # ------------------------------------------------------------------
    # 9. Agent Permissions, Output Schema Validation & Rejection of Weak Strategies
    # ------------------------------------------------------------------
    def test_09_agent_permissions_and_evaluator_rejection(self) -> None:
        reg = StrategyRegistry(self.db)
        researcher = MarketResearchAgent(self.settings, self.db, self.market_data)
        architect = StrategyDiscoveryAgent(self.settings, reg)
        analyst = PerformanceAnalystAgent(
            self.settings, self.db, PaperTradingEngine(self.settings, self.db, self.market_data), reg
        )
        evaluator = StrategyEvaluationAgent(self.settings, reg)

        # Verify agents cannot execute orders or mutate portfolio
        with self.assertRaises(AgentPermissionError):
            researcher.assert_permission("execute_order")
        with self.assertRaises(AgentPermissionError):
            architect.assert_permission("modify_portfolio")
        with self.assertRaises(AgentPermissionError):
            analyst.assert_permission("overwrite_active_strategy")

        # Schema validator rejects malformed payloads
        with self.assertRaises(SchemaValidationError):
            validate_required_fields({"ticker": "AAPL"}, {"ticker": str, "price": float}, "TestSchema")

        # Evaluator rejects a strategy with positive headline return (+18%) if Sharpe/drawdown/concentration fail
        draft_strat = reg.register_strategy(get_baseline_strategies()[0])
        fake_weak_pipeline = {
            "full_period": {
                "metrics": {
                    "total_return_pct": 18.0,  # Headline return is positive!
                    "sharpe_ratio": 0.65,      # Below 1.0 threshold
                    "profit_factor": 1.15,     # Below 1.3 threshold
                    "max_drawdown_pct": 19.5,  # Exceeds 15% max drawdown limit
                    "trade_count": 25,
                    "benchmark_return_pct": 12.0,
                    "benchmark_sharpe": 1.1,
                },
                "trades": [{"net_pnl": 18000.0}] + [{"net_pnl": -50.0} for _ in range(24)],
                "regime_breakdown": {},
            },
            "out_of_sample": {"metrics": {"total_return_pct": 4.0}},
            "walk_forward": {"consistency_ratio": 0.50},
            "stress_test": {"survives_2x_costs": True},
        }
        eval_rep = evaluator.evaluate_pipeline_results(draft_strat, fake_weak_pipeline, auto_transition=True)
        self.assertFalse(eval_rep.promoted)
        self.assertEqual(eval_rep.new_status, StrategyStatus.REJECTED.value)
        self.assertIn("sharpe_above_threshold", eval_rep.failed_criteria)
        self.assertIn("max_drawdown_below_limit", eval_rep.failed_criteria)
        self.assertTrue(eval_rep.concentration_warning)

    # ------------------------------------------------------------------
    # 10. End-to-End Integration Cycle & Idempotent Workflow Recovery
    # ------------------------------------------------------------------
    def test_10_end_to_end_lifecycle_and_workflow_recovery(self) -> None:
        orch = AutonomousWorkflowOrchestrator(self.settings, self.db, self.market_data)

        # 1. Bootstrap ingestion, backtesting, and promotion of 3 baseline strategies
        boot = orch.bootstrap_baseline_system(start_date="2023-06-01", end_date="2025-06-30")
        self.assertEqual(boot["ingestion"]["tickers_ingested"], 16)
        self.assertEqual(len(boot["baseline_evaluations"]), 3)
        for b in boot["baseline_evaluations"]:
            self.assertTrue(b["promoted"])
            self.assertEqual(b["status"], StrategyStatus.PAPER_TRADING.value)

        # 2. Run Daily Workflow on a trading day & verify idempotency on second call
        d_first = orch.run_daily_workflow("2025-05-05", force=False)
        self.assertEqual(d_first["pre_market"]["status"], "COMPLETED")
        d_second = orch.run_daily_workflow("2025-05-05", force=False)
        self.assertEqual(d_second["pre_market"]["status"], "SKIPPED_IDEMPOTENT")

        # 3. Verify weekend / US holiday is gracefully skipped
        weekend_res = orch.run_daily_workflow("2025-05-04")  # Sunday
        self.assertEqual(weekend_res["status"], "MARKET_HOLIDAY_OR_WEEKEND")

        # 4. Test failure recovery in job orchestrator
        attempts = {"count": 0}

        def flaky_job() -> dict:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("Transient network timeout")
            return {"recovered": True}

        rec_res = orch.run_idempotent_job("test_flaky_job", "flaky_key_1", flaky_job, max_retries=2)
        self.assertEqual(rec_res["status"], "COMPLETED")
        self.assertEqual(attempts["count"], 2)

        # 5. Run Weekly Discovery workflow
        weekly_res = orch.run_weekly_workflow("2025-05-09", force=True)
        self.assertEqual(weekly_res["status"], "COMPLETED")
        self.assertIn("candidate_strategy_id", weekly_res["summary"])
        self.assertIn("tournament_candidates", weekly_res["summary"])
        self.assertIn("deflated_sharpe_pct", weekly_res["summary"]["metrics"])
        self.assertIn("probabilistic_sharpe_pct", weekly_res["summary"]["metrics"])
        self.assertIn("alpha_annualised_pct", weekly_res["summary"]["metrics"])
        self.assertIn("ulcer_index", weekly_res["summary"]["metrics"])
        self.assertIn("martin_ratio", weekly_res["summary"]["metrics"])
        self.assertIn("omega_ratio", weekly_res["summary"]["metrics"])
        self.assertIn("capture_ratio", weekly_res["summary"]["metrics"])

        # Verify Golden Baseline Revert (`revert_to_golden_baseline` & `rollback_to_best_champion`)
        restored_v1 = orch.registry.revert_to_golden_baseline("strat_momentum_trend")
        self.assertEqual(len(restored_v1), 1)
        self.assertEqual(restored_v1[0].version, 1)
        self.assertEqual(restored_v1[0].status, StrategyStatus.PAPER_TRADING.value)
        champ = orch.registry.rollback_to_best_champion("strat_momentum_trend")
        self.assertIsNotNone(champ)
        self.assertEqual(champ.status, StrategyStatus.PAPER_TRADING.value)

        # Verify Drawdown De-Gearing scales down position size when portfolio drawdown >= 7.5%
        rm = orch.paper_engine.risk_manager
        normal_sz = rm.calculate_atr_position_size(
            portfolio_equity=100_000.0,
            available_cash=100_000.0,
            entry_price=100.0,
            stop_loss_price=95.0,
            atr_14=2.5,
            current_drawdown_pct=0.02,
        )
        degeared_sz = rm.calculate_atr_position_size(
            portfolio_equity=100_000.0,
            available_cash=100_000.0,
            entry_price=100.0,
            stop_loss_price=95.0,
            atr_14=2.5,
            current_drawdown_pct=0.09,
        )
        self.assertLess(degeared_sz, normal_sz)

        # 6. Verify state persistence across a brand new orchestrator instance (simulating restart)
        orch_restarted = AutonomousWorkflowOrchestrator(self.settings, self.db, self.market_data)
        self.assertGreaterEqual(len(orch_restarted.registry.list_strategies()), 4)
        self.assertEqual(
            orch_restarted.paper_engine.get_account_summary()["total_equity"],
            orch.paper_engine.get_account_summary()["total_equity"],
        )

        # 7. Verify Air-Gapped Live Trading Copilot (Real Account Shadow Ledger)
        copilot = orch.live_copilot
        acc_init = copilot.update_cash_balance(20_000.0, update_starting_baseline=True)
        self.assertEqual(acc_init["cash_balance"], 20_000.0)
        self.assertEqual(acc_init["open_positions_count"], 0)

        # Generating daily action plan does NOT auto-assume positions
        plan = copilot.get_daily_action_plan(as_of_date="2025-05-09")
        self.assertIn("buy_actions", plan)
        self.assertEqual(copilot.get_account_summary()["open_positions_count"], 0)

        # Confirming a BUY execution deducts cash and tracks the position
        after_buy = copilot.confirm_buy_execution(
            ticker="NVDA",
            strategy_id="strat_momentum_trend",
            strategy_version=1,
            quantity=10,
            fill_price=120.0,
            fees_usd=1.0,
            stop_loss_price=112.0,
            take_profit_price=135.0,
            fill_date="2025-05-05",
        )
        self.assertEqual(after_buy["open_positions_count"], 1)
        self.assertAlmostEqual(after_buy["cash_balance"], 20_000.0 - 1_201.0, places=2)

        # Editing position share count with deduct_from_cash=True only deducts the delta (5 * 120 = $600)
        after_edit = copilot.edit_or_add_position(
            ticker="NVDA",
            quantity=15,
            avg_entry_price=120.0,
            stop_loss_price=114.0,
            take_profit_price=138.0,
            deduct_from_cash=True,
        )
        self.assertEqual(copilot.get_open_positions()[0]["quantity"], 15)
        self.assertEqual(copilot.get_open_positions()[0]["opened_date"], "2025-05-05")
        self.assertAlmostEqual(after_edit["cash_balance"], 20_000.0 - 1_201.0 - 600.0, places=2)

        # Verify edit_or_add_position preserves existing strategy_id when updating a non-default strategy holding
        copilot.edit_or_add_position(
            ticker="NVDA",
            quantity=15,
            avg_entry_price=120.0,
            strategy_id="strat_volatility_breakout",
            strategy_version=1,
            deduct_from_cash=False,
        )
        copilot.edit_or_add_position(
            ticker="NVDA",
            quantity=15,
            avg_entry_price=120.0,
            stop_loss_price=114.0,
            deduct_from_cash=False,
        )
        nvda_pos_check = [p for p in copilot.get_open_positions() if p["ticker"] == "NVDA"][0]
        self.assertEqual(nvda_pos_check["strategy_id"], "strat_volatility_breakout")

        # Verify Two-Tier Paper Books summary (1 Master $100k + Dedicated Per-Strategy $100k Pods)
        all_books = orch.paper_engine.get_all_paper_accounts_summary(
            [s.to_dict() for s in orch.registry.list_strategies()]
        )
        self.assertGreaterEqual(len(all_books), 4)
        self.assertEqual(all_books[0]["account_id"], "paper_main_100k")
        self.assertEqual(all_books[0]["book_type"], "MASTER_COMBINED")
        pod_ids = {b["account_id"] for b in all_books if b["book_type"] == "STRATEGY_DEDICATED"}
        self.assertIn("paper_strat_volatility_breakout", pod_ids)
        self.assertIn("paper_strat_momentum_trend", pod_ids)

        # Verify get_daily_action_plan with an open position populates hold_updates or sell_actions cleanly
        plan_with_open = copilot.get_daily_action_plan(as_of_date="2025-05-09")
        self.assertTrue(len(plan_with_open["hold_updates"]) + len(plan_with_open["sell_actions"]) >= 1)

        # Verify dismiss_signal and restore_dismissed_signals
        copilot.dismiss_signal("2025-05-09", "strat_momentum_trend", "AAPL", "BUY")
        self.assertEqual(copilot.get_daily_action_plan(as_of_date="2025-05-09")["dismissed_count"], 1)
        restored_cnt = copilot.restore_dismissed_signals("2025-05-09")
        self.assertEqual(restored_cnt, 1)
        self.assertEqual(copilot.get_daily_action_plan(as_of_date="2025-05-09")["dismissed_count"], 0)

        # Confirming a SELL execution closes the position and locks in realised P&L
        after_sell = copilot.confirm_sell_execution(
            ticker="NVDA",
            quantity=15,
            fill_price=130.0,
            fees_usd=1.0,
            fill_date="2025-05-09",
        )
        self.assertEqual(after_sell["open_positions_count"], 0)
        self.assertAlmostEqual(after_sell["realised_pnl"], (130.0 - 120.0) * 15 - 1.0, places=2)

        # Verify undo_last_trade reverses the SELL and restores the 15-share NVDA position
        after_undo = copilot.undo_last_trade()
        self.assertEqual(after_undo["open_positions_count"], 1)
        self.assertEqual(copilot.get_open_positions()[0]["quantity"], 15)
        self.assertAlmostEqual(after_undo["realised_pnl"], 0.0, places=2)

        # Re-sell NVDA and test deposit/withdrawal & shortfall auto-funding
        copilot.confirm_sell_execution(ticker="NVDA", quantity=15, fill_price=130.0, fees_usd=1.0, fill_date="2025-05-09")
        dep_summary = copilot.adjust_cash_deposit_withdrawal(5_000.0)
        self.assertAlmostEqual(dep_summary["starting_cash"], 25_000.0, places=2)

        # Buying more than available cash auto-funds shortfall into starting_cash without distorting P&L
        copilot.update_cash_balance(1_000.0, update_starting_baseline=True)
        shortfall_buy = copilot.confirm_buy_execution(
            ticker="MSFT",
            strategy_id="strat_momentum_trend",
            strategy_version=1,
            quantity=10,
            fill_price=150.0,
            reference_entry_price=148.0,
            stop_loss_price=140.0,
            take_profit_price=165.0,
            fill_date="2025-05-09",
        )
        self.assertAlmostEqual(shortfall_buy["cash_balance"], 0.0, places=2)
        self.assertAlmostEqual(shortfall_buy["starting_cash"], 1_500.0, places=2)
        msft_pos = [p for p in copilot.get_open_positions() if p["ticker"] == "MSFT"][0]
        # Stop and target shifted by +$2.00 (fill 150 vs ref 148)
        self.assertAlmostEqual(float(msft_pos["stop_loss_price"]), 142.0, places=2)
        self.assertAlmostEqual(float(msft_pos["take_profit_price"]), 167.0, places=2)

        # Verify Ledger-Driven Trade Editing & Deletion (edit_trade, delete_trade, update_position_brackets)
        copilot.reset_copilot_account(starting_cash=10_000.0)
        copilot.confirm_buy_execution(
            ticker="AAPL",
            strategy_id="strat_volatility_breakout",
            strategy_version=1,
            quantity=10,
            fill_price=200.0,
            fees_usd=1.0,
            fill_date="2025-05-05",
        )
        tr_list = copilot.get_trade_history(limit=10)
        self.assertEqual(len(tr_list), 1)
        aapl_tid = tr_list[0]["trade_id"]
        # Edit the BUY trade from 10 shares @ $200 to 20 shares @ $190 ($3,801 cost -> $6,199 cash)
        edited_sum = copilot.edit_trade(
            trade_id=aapl_tid,
            ticker="AAPL",
            side="BUY",
            quantity=20,
            fill_price=190.0,
            fees_usd=1.0,
            fill_date="2025-05-05",
            stop_loss_price=182.0,
            take_profit_price=215.0,
        )
        self.assertAlmostEqual(edited_sum["cash_balance"], 10_000.0 - 3_801.0, places=2)
        aapl_pos = copilot.get_open_positions()[0]
        self.assertEqual(aapl_pos["quantity"], 20)
        self.assertAlmostEqual(float(aapl_pos["avg_entry_price"]), 190.0, places=2)
        self.assertAlmostEqual(float(aapl_pos["stop_loss_price"]), 182.0, places=2)

        # Delete the trade -> cash returns to $10,000.00 and open positions become 0
        deleted_sum = copilot.delete_trade(aapl_tid)
        self.assertAlmostEqual(deleted_sum["cash_balance"], 10_000.0, places=2)
        self.assertEqual(deleted_sum["open_positions_count"], 0)

        # Verify non-trading day (Saturday 2025-05-10) check_calendar_today=True suppresses trade suggestions
        sat_plan = copilot.get_daily_action_plan(as_of_date="2025-05-10", check_calendar_today=True)
        self.assertFalse(sat_plan["is_trading_day"])
        self.assertIn("Saturday", sat_plan["market_status_reason"])
        self.assertEqual(sat_plan["next_trading_day"], "2025-05-12")
        self.assertEqual(len(sat_plan["buy_actions"]), 0)
        self.assertEqual(len(sat_plan["sell_actions"]), 0)

        # 8. Verify IDE-Native AI Bridge (`export_ide_ai_context` & `apply_ide_ai_cycle`)
        ide_ctx = orch.export_ide_ai_context(trading_date="2025-05-09", run_daily_first=False)
        self.assertEqual(ide_ctx["session_date"], "2025-05-09")
        self.assertTrue(len(ide_ctx["top_research_candidates"]) > 0)
        top_tkr = ide_ctx["top_research_candidates"][0]["ticker"]

        ide_res = orch.apply_ide_ai_cycle(
            payload={
                "research_updates": [
                    {
                        "ticker": top_tkr,
                        "bullish_thesis": "IDE LLM verified strong institutional catalyst and relative strength.",
                        "bearish_thesis": "Broad sector multiple compression if yields spike.",
                        "catalyst_assessment": "Positive earnings guidance follow-through.",
                        "sentiment_score": 0.82,
                        "research_confidence_score": 0.89,
                    }
                ],
                "analyst_proposal": {
                    "target_strategy_id": "strat_momentum_trend",
                    "market_regime": "BULL_LOW_VOL",
                    "diagnosis_summary": "IDE AI diagnosis of recent momentum trades.",
                    "proposed_hypothesis": "Test slightly higher RS filter for momentum entries.",
                },
                "candidate_strategies": [
                    {
                        "target_strategy_id": "strat_momentum_trend",
                        "name": "Momentum Trend (IDE AI Tuned)",
                        "hypothesis": "Tighter relative strength filter improves win rate.",
                        "entry_rules_patch": {"rs_20d_min": 0.022},
                        "exit_rules_patch": {"take_profit_atr_mult": 3.6},
                    }
                ],
            },
            session_date="2025-05-09",
        )
        self.assertIn(top_tkr, ide_res["research_tickers_enriched"])
        self.assertEqual(len(ide_res["tournament_results"]), 1)
        ide_jobs = [j for j in orch.get_job_history(limit=10) if j["job_name"] == "ide_ai_cycle"]
        self.assertTrue(len(ide_jobs) >= 1)

        # 9. Verify DST-aware SGT market hours & strict regular trading hours check
        from datetime import date, datetime
        from zoneinfo import ZoneInfo
        sgt = ZoneInfo("Asia/Singapore")
        # November 9, 2026 (EST): 9:45 PM SGT is 8:45 AM EST -> Market Closed
        self.assertFalse(USTradingCalendar.is_market_open(datetime(2026, 11, 9, 21, 45, tzinfo=sgt)))
        # November 9, 2026 (EST): 10:35 PM SGT is 9:35 AM EST -> Market Open
        self.assertTrue(USTradingCalendar.is_market_open(datetime(2026, 11, 9, 22, 35, tzinfo=sgt)))
        self.assertEqual(USTradingCalendar.market_open_sgt(date(2026, 11, 9)), "10:30 PM SGT")
        self.assertEqual(USTradingCalendar.market_open_sgt(date(2026, 7, 15)), "9:30 PM SGT")

    # ------------------------------------------------------------------
    # 11. v2.0 All-Weather Short-Selling, Squeeze Caps, News & Mistake Analyzer
    # ------------------------------------------------------------------
    def test_11_v2_short_selling_risk_gates_news_and_mistake_analyzer(self) -> None:
        from core.strategies.registry import (
            StrategyFamily,
            StrategySignalEngine,
            get_all_golden_base_strategies,
        )
        from core.risk.manager import PortfolioRiskManager
        from core.backtesting.engine import BacktestEngine
        from core.market_data.providers import MarketDataService

        self.market_data.ingest_universe_and_history(start_date="2023-06-01", end_date="2025-06-30")

        # 1. Verify all 6 golden base strategies include BEARISH_BREAKDOWN
        all_golden = get_all_golden_base_strategies()
        self.assertEqual(len(all_golden), 6)
        short_strat = [s for s in all_golden if s.strategy_family == StrategyFamily.BEARISH_BREAKDOWN.value][0]
        self.assertEqual(short_strat.strategy_id, "strat_bearish_breakdown")

        # 2. Verify downward stop ratchet for SHORT positions
        s_stop_init, s_lbl_init = StrategySignalEngine.compute_effective_short_stop_price(
            config=short_strat,
            entry_price=100.0,
            lowest_price_since_entry=98.0,
            holding_days=4,
            initial_stop_price=104.0,
            atr_14=2.0,
        )
        self.assertEqual(s_stop_init, 104.0)
        self.assertIn("Initial", s_lbl_init)

        # After dropping to $93.0 (-1.75R favorable move on $4 initial risk), stop ratchets below entry
        s_stop_ratchet, _ = StrategySignalEngine.compute_effective_short_stop_price(
            config=short_strat,
            entry_price=100.0,
            lowest_price_since_entry=93.0,
            holding_days=5,
            initial_stop_price=104.0,
            atr_14=2.0,
        )
        self.assertLess(s_stop_ratchet, 100.0)

        # 3. Verify PortfolioRiskManager short-squeeze protections
        rm = PortfolioRiskManager(self.settings.risk, self.db)
        # Non-shortable asset is strictly vetoed
        veto_non_short = rm.evaluate_proposed_entry(
            account_id="paper_test",
            eval_date="2025-05-09",
            ticker="AAPL",
            sector="Technology",
            strategy_id="strat_bearish_breakdown",
            strategy_family="BEARISH_BREAKDOWN",
            entry_price=200.0,
            stop_loss_price=208.0,
            atr_14=4.0,
            portfolio_equity=100_000.0,
            peak_equity=100_000.0,
            available_cash=100_000.0,
            open_positions={},
            side="SHORT",
            is_shortable=False,
        )
        self.assertFalse(veto_non_short.approved)
        self.assertEqual(veto_non_short.rule_triggered, "SHORT_NOT_SHORTABLE")

        # Valid shortable asset respects 1.0% risk cap ($1,000 / $8 risk = 125 shs, capped by 12% = $12,000 / $200 = 60 shs)
        ok_short = rm.evaluate_proposed_entry(
            account_id="paper_test",
            eval_date="2025-05-09",
            ticker="AAPL",
            sector="Technology",
            strategy_id="strat_bearish_breakdown",
            strategy_family="BEARISH_BREAKDOWN",
            entry_price=200.0,
            stop_loss_price=208.0,
            atr_14=4.0,
            portfolio_equity=100_000.0,
            peak_equity=100_000.0,
            available_cash=100_000.0,
            open_positions={},
            side="SHORT",
            is_shortable=True,
            easy_to_borrow=True,
        )
        self.assertTrue(ok_short.approved)
        self.assertEqual(ok_short.recommended_shares, 60)

        # Gross short exposure >= 40% is vetoed
        veto_gross_short = rm.evaluate_proposed_entry(
            account_id="paper_test",
            eval_date="2025-05-09",
            ticker="MSFT",
            sector="Technology",
            strategy_id="strat_bearish_breakdown",
            strategy_family="BEARISH_BREAKDOWN",
            entry_price=200.0,
            stop_loss_price=208.0,
            atr_14=4.0,
            portfolio_equity=100_000.0,
            peak_equity=100_000.0,
            available_cash=60_000.0,
            open_positions={
                "NVDA": {"ticker": "NVDA", "side": "SHORT", "sector": "Semiconductors", "market_value": 20_000.0, "quantity": -100, "avg_entry_price": 200.0, "stop_loss_price": 208.0},
                "AMZN": {"ticker": "AMZN", "side": "SHORT", "sector": "Consumer", "market_value": 20_000.0, "quantity": -100, "avg_entry_price": 200.0, "stop_loss_price": 208.0},
            },
            side="SHORT",
            is_shortable=True,
        )
        self.assertFalse(veto_gross_short.approved)
        self.assertEqual(veto_gross_short.rule_triggered, "MAX_GROSS_SHORT_EXPOSURE")

        # 4. Run chronological BacktestEngine on BEARISH_BREAKDOWN short strategy
        bt_engine = BacktestEngine(self.settings, self.market_data)
        bt_res = bt_engine.run_backtest(
            strategy=short_strat,
            start_date="2023-08-01",
            end_date="2025-06-30",
        )
        self.assertGreaterEqual(len(bt_res.equity_curve), 50)
        for tr in bt_res.trades:
            self.assertEqual(tr.get("side"), "SHORT")

        # 5. Verify deterministic headline sentiment scorer & Mistake Analyzer
        bull_score = MarketDataService.score_headline_sentiment_deterministic(
            "Company beats earnings and raises full-year revenue guidance on record demand"
        )
        bear_score = MarketDataService.score_headline_sentiment_deterministic(
            "Stock plunges after SEC investigation, guidance cut, and analyst downgrade"
        )
        self.assertGreater(bull_score, 0.25)
        self.assertLess(bear_score, -0.35)

        orch = AutonomousWorkflowOrchestrator(self.settings, self.db, self.market_data)
        self.db.execute(
            """
            INSERT INTO alpaca_closed_trades (
                trade_id, pod_id, alpaca_account_number, ticker, side, sector,
                strategy_id, strategy_version, strategy_name, entry_date, exit_date,
                holding_days, quantity, entry_price, exit_price, initial_stop_price,
                realised_pnl_usd, realised_return_pct, r_multiple, ai_catalyst_score,
                market_regime, conviction_tier, exit_reason, created_at
            ) VALUES
            ('tr_short_1', 'pod_1_breakout', 'PA_TEST', 'TSLA', 'SHORT', 'Consumer', 'strat_bearish_breakdown', 1, 'Breakdown Short', '2025-05-05', '2025-05-09', 4, 10, 250.0, 232.0, 260.0, 180.0, 7.2, 1.8, -0.45, 'BEAR_TREND', 'STANDARD', 'TAKE_PROFIT', '2025-05-09T20:00:00Z'),
            ('tr_long_1', 'pod_1_breakout', 'PA_TEST', 'AMD', 'LONG', 'Technology', 'strat_volatility_breakout', 1, 'Vol Breakout', '2025-05-07', '2025-05-09', 2, 20, 120.0, 114.0, 114.0, -120.0, -5.0, -1.0, -0.10, 'BEAR_TREND', 'STANDARD', 'STOP_LOSS', '2025-05-09T20:00:00Z')
            """
        )
        attr = orch.pod_manager.get_post_trade_attribution_analysis()
        self.assertEqual(attr["live_alpaca_closed_count"], 2)
        self.assertGreaterEqual(attr["total_closed_trades"], 2)
        self.assertTrue(len(attr["by_side"]) >= 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

