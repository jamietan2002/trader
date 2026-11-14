# core/AGENTS.md — Deterministic Quantitative Core Rules

Rules for modifying any module inside `core/` (`market_data`, `indicators`, `strategies`, `backtesting`, `risk`, `execution`, `portfolio`):

1. **Pure Determinism**: No LLM calls or non-deterministic heuristics are allowed inside `core/`. Given the same historical dataset and `StrategyConfig`, `BacktestEngine` and `StrategySignalEngine` must produce bit-for-bit identical signals, fills, and P&L.
2. **Causal Indicator Computation (`core/indicators/technical.py`)**:
   - Indicator values at index `i` (`bar_date`) must only read `bars[0 : i + 1]`.
   - Prior high/low breakout references (`high_20d_prior`, `high_252d_prior`, `consolidation_range_10d_pct`) must strictly use prior bars `bars[i - N : i]` (excluding bar `i`) so today's close can be cleanly compared against prior resistance.
   - When adding a new indicator field to `IndicatorSnapshot`, update `compute_indicator_series()` and document it in `STRATEGY_GUIDE.md`.
3. **Chronological Backtesting (`core/backtesting/engine.py`)**:
   - Entry and exit signals evaluated on Day `T` close must be queued and filled at Day `T + 1` market open (`adj_open` adjusted for half-spread and slippage).
   - Point-in-time earnings (`MarketDataService.get_point_in_time_earnings`) must respect `BMO` vs `AMC` session visibility.
   - Delisted equities must be forcibly liquidated on their `delisted_date` / final bar.
4. **Portfolio Risk Veto & Paper Execution (`core/risk/manager.py`, `core/execution/paper_broker.py`)**:
   - Every `LONG` and `SHORT` entry in `PaperTradingEngine` and `AlpacaPaperPodManager` must pass through `PortfolioRiskManager.evaluate_proposed_entry` (enforcing per-trade risk caps, 6% total open portfolio heat cap, single-stock exposure caps, 12% single-short & 40% gross-short squeeze caps, `SHORT_NOT_SHORTABLE` verification, 30% sector cap, and 15% drawdown suspension).
   - Chronological short backtests in `BacktestEngine` must enforce zero-leverage 100%-cash-collateralized short margin, `50 bps/yr` borrow fee drag, and short dividend liability.
   - Every order must carry a deterministic `idempotency_key` (`PaperTradingEngine.build_idempotency_key`) or Pod `client_order_id` to prevent duplicate execution.
   - Every fill must write an immutable record to `trade_ledger` and reconcile `paper_accounts.cash_balance` and `paper_positions`.
   - When switching `provider_source` in `MarketDataService` (e.g., `local_seeded` to `alpaca`), mixed-provider bars must be purged and paper positions reset so positions are never marked-to-market across incompatible price scales.

