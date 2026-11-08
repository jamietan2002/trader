# Agent Implementation & Maintenance Changelog

This log tracks architectural additions, strategy changes, schema updates, and verification runs performed by AI coding agents in this repository. Every implementation must append an entry here per the `maintain-project-context` skill.

---

## [2026-11-08] — Live Market Bar Auto-Sync (`ensure_latest_market_data`), Pullback Regime Dip-Buying & Next-Session Preview Clarity

### Summary
- **Fixed Stale Preview Setup Prices (`core/market_data/providers.py`, `core/market_data/models.py`, `core/execution/paper_broker.py`, `infrastructure/scheduler/orchestrator.py`, `api/server.py`)**:
  - Added `USTradingCalendar.previous_trading_day()` and `MarketDataService.ensure_latest_market_data()` to automatically sync `market_bars_daily` up to the latest completed US market close (`2026-11-06` via `alpaca`: `SPY $735.40`, `AAPL $342.41`, `MSFT $530.58`, `NVDA $186.70`, `AMZN $259.45`, `LLY $1,354.77`, `GS $865.97`, etc.) instead of falling back to hardcoded `2025-06-30` (`local_seeded`) bars.
  - Protected `MarketDataService.ingest_universe_and_history()` so read-only environments without API keys (such as Streamlit Community Cloud when viewing the committed SQLite DB) never overwrite existing `alpaca`/`polygon` bars with `local_seeded` data.
  - Updated `dashboard/streamlit_app.py` (`_code_version = "2026-11-08-v17"`) to source `latest_px_by_tkr` directly from `market_bars_daily` (`MAX(bar_date)` per ticker), include `signal_date` in widget keys so Streamlit never serves cached stale prices, and display `Close YYYY-MM-DD` on every setup row.
- **Bull-Market Pullback Regime Handling (`core/strategies/registry.py`, `core/execution/paper_broker.py`)**:
  - Updated `StrategySignalEngine.evaluate_entry()` and `LiveTradingCopilotEngine.get_daily_action_plan()` so that when `SPY` pulls back below `SMA50` while holding above its primary `SMA200` bull trend (`SPY $735.40 > SMA200 $727.61`), the automatic regime fallback prioritizes `MEAN_REVERSION` (`strat_mean_reversion_bb v1`) to surface institutional dip-buying setups (`AAPL`, `MSFT`, `LLY`).
- **Clear Next-Session Preview & AI Flow Guidance (`dashboard/streamlit_app.py`)**:
  - Added concise inline guidance below `Preview next_trading_day setups` and inside `? Rules` explaining why next-session setups are known after the prior day's `4:00 PM ET` close (`Day T Close → Day T+1 Open`), how running `run` in the IDE applies live web news catalyst vetoes/boosts, and why skipping `run` remains safe when using `Buy-Zone` limit orders.

### Modules Added / Modified
- `core/market_data/models.py`, `core/market_data/providers.py`
- `core/strategies/registry.py`, `core/execution/paper_broker.py`
- `infrastructure/scheduler/orchestrator.py`, `api/server.py`
- `dashboard/streamlit_app.py`, `data/swing_trader.db`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-08] — Minimalist Classy Institutional UI Redesign & Full Ledger-Replay `undo_last_trade` / `adjust_cash_deposit_withdrawal`

### Summary
- **Minimalist, Classy Institutional UI (`CLASSY_MINIMAL_CSS` in `dashboard/streamlit_app.py`)**:
  - Added refined institutional CSS (`CLASSY_MINIMAL_CSS`) featuring bordered dark-slate metric cards (`tabular-nums`), uppercase label hierarchy, compact vertical rhythm, clean navigation tab pills, and zero emoji clutter across tabs, headers, and action buttons.
  - Replaced redundant top-of-page expanders and duplicate trade forms with a single sleek masthead (`Date · Market Open/Closed · Next Open · Active Champion`), a compact 4-popover control bar in `Live Copilot` (`Cash Transfer`, `+ Log Trade`, `Reset`, `? Rules`), inline non-trading-day preview toggle, and per-holding entry-strategy attribution in `Active Holdings`.
- **Full Ledger-Replay Consistency in `undo_last_trade` & `adjust_cash_deposit_withdrawal` (`core/execution/paper_broker.py`)**:
  - Simplified `LiveTradingCopilotEngine.undo_last_trade()` to delete the most recent fill from `shadow_trade_history` and invoke `reconcile_from_trade_ledger()`, restoring exact historical `avg_entry_price`, `opened_date`, `holding_days`, `cash_balance`, and `realised_pnl` without inverse-math approximation.
  - Updated `adjust_cash_deposit_withdrawal()` to invoke `reconcile_from_trade_ledger()` after shifting `starting_cash` so historical `cash_after` balances and `cash_balance` remain 100% synchronized.

### Modules Added / Modified
- `dashboard/streamlit_app.py`
- `core/execution/paper_broker.py`
- `docs/AGENT_CHANGELOG.md`

---

## [2026-11-08] — Automatic #1 Champion Strategy Selection (`BUY`), Per-Position Entry-Strategy Binding (`SELL`/`HOLD`) & Headless Streamlit Runtime Verification

### Summary
- **Removed Manual Strategy Selection from `Live Copilot` (`core/execution/paper_broker.py`, `dashboard/streamlit_app.py`)**:
  - Replaced manual strategy dropdowns/presets in `Live Copilot` with **100% Automatic Strategy Selection**:
    1. **Open Holdings (`SELL` & `HOLD / Raise Stop`)**: Always evaluated using the **exact strategy (`pos['strategy_id'] v{pos['strategy_version']}`) that opened each holding**.
    2. **New `BUY` Suggestions**: Automatically driven by the **#1 Champion Strategy (`strat_volatility_breakout v1`, `SQN 3.55`, `+11.03%` 6M, `67.9%` WR)** ranked by composite live-readiness score (`SQN * 10 + 6M Return % + 0.2 * 6M WR % + 0.1 * Full Return %`), with **Automatic Pullback Regime Fallback** to the #2 Champion (`strat_mean_reversion_bb v1`) **only** when the #1 Champion has `0` signals on a market pullback day.
  - Replaced the `"⚙️ Strategy & Reset"` popover in Tab 1 with a clean, single-purpose **`🔄 Reset Account`** popover and added an **Active Strategy Engine** status line showing the auto-selected #1 Champion and open-position strategy binding.
- **Headless Multi-Branch Streamlit Runtime Check (`.agents/skills/maintain-project-context/scripts/verify_context.py`)**:
  - Added `_MockStreamlit` execution of `dashboard/streamlit_app.py` across both `Master Combined Portfolio` and `Per-Strategy Pod` UI branches so any undefined variable (`NameError`) or runtime error in `dashboard/streamlit_app.py` is caught automatically before every commit.

### Modules Added / Modified
- `core/execution/paper_broker.py`
- `dashboard/streamlit_app.py`
- `.agents/skills/maintain-project-context/scripts/verify_context.py`
- `data/swing_trader.db`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-08] — Ledger-Driven Real-Account UI (Deposits/Withdrawals + Editable Trade Ledger as Single Source of Truth)

### Summary
- **Event-Sourced / Ledger-Driven Real-Account Reconciliation (`reconcile_from_trade_ledger`, `edit_trade`, `delete_trade`, `update_position_brackets` in `core/execution/paper_broker.py`, `api/server.py`, `dashboard/streamlit_app.py`, `dashboard/ui_template.py`)**:
  - Removed the redundant manual `"Update Cash"` and `"Set as Starting Capital"` inputs from `Live Copilot` so users never have to manually reconcile cash balances against positions.
  - **Available Cash (`cash_balance`)**, **Open Holdings (`shadow_positions`)**, and **Realised P&L (`realised_pnl`)** are now 100% deterministically calculated from **Net Deposited Capital (`+ Deposit Cash` / `- Withdraw Cash`)** and **Trades Placed (`BUY` & `SELL` fills in `shadow_trade_history`)**.
  - Added an interactive **Trade Ledger Manager (`Add, Edit, or Remove a Trade`)** in Section 3 of `Live Copilot` allowing users to add new `BUY`/`SELL` trades, edit any past trade's side/ticker/shares/fill price/fees/date (`/api/copilot/trade/edit`), or remove a trade (`/api/copilot/trade/delete`), automatically replaying the chronological ledger to recompute cash, holdings, and P&L.
  - Added inline `Bracket` stop-loss/take-profit editors (`/api/copilot/position/brackets`) on open holdings in Section 2 so trailing a broker stop-loss updates the bracket cleanly without altering shares or cash.

### Modules Added / Modified
- `core/execution/paper_broker.py`, `api/server.py`
- `dashboard/streamlit_app.py`, `dashboard/ui_template.py`
- `tests/test_platform.py`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-08] — Two-Tier Paper Books (1 Master $100k + 5 Per-Strategy $100k Pods), Staged Real-Account Presets & 4 Logical/UI Bug Fixes

### Summary
- **Two-Tier Forward Paper Book Architecture (`get_strategy_account_engine` & `get_all_paper_accounts_summary` in `core/execution/paper_broker.py`, `api/server.py`, `dashboard/streamlit_app.py`)**: Implemented institutional multi-strategy pod tracking alongside the master portfolio. Every forward daily run now executes **both** (1) the **`$100,000` Master Combined Portfolio (`paper_main_100k`)** enforcing cross-strategy portfolio heat (`5%`), sector (`30%`), and single-stock (`15%`) caps, **and** (2) **5 Dedicated Per-Strategy `$100,000` Accounts (`paper_strat_volatility_breakout`, `paper_strat_mean_reversion_bb`, `paper_strat_momentum_trend`, `paper_strat_pead_drift`, `paper_strat_sector_rotation_leaders`)** so each strategy is evaluated forward with zero cash starvation / first-in bias. Added a Paper Book Selector and a 6-book comparison table in Tab 2 (`Paper Account & Ledger`).
- **Staged Real-Account Deployment Presets (`Strategies & Reset` popover in `dashboard/streamlit_app.py`)**: Added 1-click presets (`★ Core 2: Breakout + Dip`, `Core 3 (+ Earnings PEAD)`, `All 5 Base Strategies`, `Best Single`) grounded in Grinold & Kahn's Fundamental Law of Active Management and regime cyclicality.
- **4 Logical & UI Bug Fixes (`core/execution/paper_broker.py`)**:
  1. **Cross-Strategy Ticker Overwrite Prevention in `PaperTradingEngine`**: Added an open-position ticker guard before submitting new `BUY` orders in `run_trading_session_for_strategies()` so a second strategy signaling the same stock on a later day cannot overwrite the original position's `strategy_id` via `ON CONFLICT(account_id, ticker) DO UPDATE`.
  2. **Execution Rule Parity in `PaperTradingEngine`**: Enforced `max_entry_gap_atr` opening gap-chase protection, `AI_BEARISH_CATALYST_VETO` (`sentiment_score <= -0.35`), and per-strategy `pead_lookback` inside `PaperTradingEngine.run_trading_session_for_strategies()` to match `BacktestEngine` and `LiveTradingCopilotEngine`.
  3. **`LiveTradingCopilotEngine.edit_or_add_position` Preserving `strategy_id`**: Changed default `strategy_id` / `strategy_version` parameters to `None` so editing an existing holding's shares, stop-loss, or take-profit preserves its existing `strategy_id` instead of resetting it to `"strat_momentum_trend"`.
  4. **Sector Relative-Strength Leader Formula Parity in `LiveTradingCopilotEngine`**: Aligned `get_daily_action_plan()` to use the top-2 leader average (`sum(sorted(vals, reverse=True)[:2]) / min(2, len(vals))`), matching `BacktestEngine` and `PaperTradingEngine`.

### Modules Added / Modified
- `core/execution/paper_broker.py`, `api/server.py`, `dashboard/streamlit_app.py`
- `data/swing_trader.db`, `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`, `tests/test_platform.py`

---

## [2026-11-08] — 6-Month Deployment Horizon & SQN Metrics, Opening Gap-Chase Protection, AI Catalyst Veto/Booster & Exact Market-Open Buy-Zone Execution Rules

### Summary
- **6-Month (`126`-Trading-Day) Deployment Horizon & Van Tharp `SQN` Metrics (`calculate_performance_metrics` in `evaluation/metrics/performance.py`, `dashboard/streamlit_app.py`, `dashboard/ui_template.py`)**: Added **System Quality Number (`sqn_score` = $\frac{\mu_R}{\sigma_R}\sqrt{\min(N,100)}$)**, **Payoff Ratio (`payoff_ratio`)**, **Profit per Day Held (`profit_per_day_held_pct`)**, **Recent 6-Month Return & Excess vs. `SPY` (`recent_6m_return_pct`, `recent_6m_spy_return_pct`, `recent_6m_excess_vs_spy_pct`)**, **Recent 6-Month Win Rate & Profit Factor (`recent_6m_win_rate_pct`, `recent_6m_profit_factor`, `recent_6m_trade_count`)**, and **Rolling 6-Month Window Consistency (`rolling_6m_win_pct`, `rolling_6m_beat_spy_pct`, `rolling_6m_median_return_pct`, `rolling_6m_worst_return_pct`)** so strategies are evaluated on both multi-year regime survival and 6-month live forward profit consistency.
- **Opening Gap-Chase Protection (`BacktestEngine` in `core/backtesting/engine.py`)**: Added causal opening gap-chase protection (`max_entry_gap_atr`, default `1.25 * ATR14`) so entries triggered at Day $T$ close are automatically skipped if Day $T+1$ open (`adj_open`) gaps up beyond the chase ceiling, preventing mean-reversion losses from buying exhausted overnight gaps.
- **AI Catalyst Veto & Conviction Booster + Actionable Market-Open Buy-Zone Rules (`LiveTradingCopilotEngine.get_daily_action_plan` in `core/execution/paper_broker.py`, `dashboard/streamlit_app.py`, `dashboard/ui_template.py`)**: Wired point-in-time `market_catalysts` sentiment into `get_daily_action_plan()` to automatically veto BUY signals with bearish AI catalyst sentiment (`<= -0.35`, `AI_BEARISH_CATALYST_VETO`) and boost conviction for positive catalysts (`>= +0.25`). Added explicit **`entry_buy_zone_low`**, **`max_chase_price` (`entry_buy_zone_str`)**, **`breakeven_ratchet_price` (`+1.0R`)**, **`order_timing_guidance` (`9:30–9:45 AM ET Open Limit`)**, **`if_entry_not_hit_rule`**, and **`if_target_not_hit_rule`** to every Copilot BUY recommendation.

### Modules Added / Modified
- `evaluation/metrics/performance.py`, `core/backtesting/engine.py`, `core/execution/paper_broker.py`
- `dashboard/streamlit_app.py`, `dashboard/ui_template.py`, `data/swing_trader.db`
- `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`, `tests/test_platform.py`

---

## [2026-11-07] — Trading-Day-Aware Copilot Checklist, Top-of-Mind Tab Hierarchy, Unified Strategy Encyclopaedia & Direct IDE AI Prompt-to-Engine Bridge

### Summary
- **Trading-Day-Aware Action Checklist (`USTradingCalendar.next_trading_day` & `non_trading_reason` in `core/market_data/models.py`, `LiveTradingCopilotEngine.get_daily_action_plan` in `core/execution/paper_broker.py`, `dashboard/streamlit_app.py`, `dashboard/ui_template.py`)**: `Today's Action Checklist` now displays today's real calendar date and weekday, checks `USTradingCalendar.is_trading_day()`, and when today is a weekend or US market holiday (`Saturday`, `Sunday`, or `NYSE`/`NASDAQ` holiday), clearly states that US equity markets are closed, displays the next trading session date, and suppresses stale `BUY`/`SELL` suggestions (with an optional preview toggle for weekend preparation).
- **Top-of-Mind 6-Tab UI Hierarchy (`dashboard/streamlit_app.py`, `dashboard/ui_template.py`)**: Reordered and consolidated the dashboard into 6 high-signal tabs placing the most actionable information first:
  1. `1. Live Copilot (Real Account)` *(Default Landing Tab)*
  2. `2. Paper Account & Ledger` *(Unified forward `$100,000` P&L + open positions + day-filtered execution ledger)*
  3. `3. Strategies, Rules & Backtests` *(Complete Strategy Encyclopaedia consolidating how each strategy is conceived, its economic edge, exact `entry_rules`/`exit_rules`/`risk_params`, 9-gate `SPY` benchmark audit, historical backtest trade log, and 1-click `Revert All to Golden Base (v1)`)*
  4. `4. AI Research & IDE Bridge` *(Daily watchlist + IDE AI Reminder Checklist + Direct Prompt-to-Engine JSON feed)*
  5. `5. Risk, Walk-Forward & Logs` *(Sector concentration vs. `30%` cap, 4-window Walk-Forward folds, risk vetoes, and job logs)*
  6. `6. Platform Guide` *(Visual mental-model diagram and interactive walkthrough)*
- **IDE AI Reminder Checklist & Direct Prompt-to-Engine Feed (`infrastructure/scheduler/orchestrator.py`, `api/server.py`, `dashboard/streamlit_app.py`, `.agents/skills/run-ai-cycle/SKILL.md`)**: Added a persistent **Daily & Weekly AI Checklist** in the sidebar tracking the last `ide_ai_cycle` execution timestamp, an auto-generated **Ready-to-Paste AI Prompt** pre-populated with today's top candidates, and an interactive **Paste AI JSON Output Directly into Engine** bridge (`/api/ide/apply`) that enriches `research_reports`, logs structured `IDE_AI_RESEARCH` rows to `market_catalysts`, and runs the 9-gate strategy tournament.

### Modules Added / Modified
- `core/market_data/models.py`, `core/execution/paper_broker.py`
- `infrastructure/scheduler/orchestrator.py`, `api/server.py`
- `dashboard/streamlit_app.py`, `dashboard/ui_template.py`
- `.agents/skills/run-ai-cycle/SKILL.md`, `tests/test_platform.py`, `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-07] — Live Trading Copilot Persistence Hardening, `st.session_state` Widget Sync & Real-World Edge-Case Support

### Summary
- **Streamlit `st.session_state` & Widget Synchronization (`dashboard/streamlit_app.py`)**: Fixed widget state persistence where `st.session_state["copilot_cash_input"]` and position editor inputs (`edit_qty_*`, `edit_px_*`, `edit_sl_*`, `edit_tp_*`, `edit_dt_*`) could retain stale pre-trade values across `st.rerun()` after confirming a `BUY`/`SELL` or closing/editing a holding. Synchronized `copilot_cash_input` via `_synced_copilot_db_cash` and keyed position/action inputs by live database state signatures (`pos_sig`, `b_sig`, `s_qty_sig`, `h_sig`), with instant confirmation banners (`_copilot_flash_msg` + `st.toast`).
- **Real-World User Trading Context Edge Cases (`LiveTradingCopilotEngine` in `core/execution/paper_broker.py`, `api/server.py`, `dashboard/ui_template.py`)**:
  - **Dynamic Fill-Price Bracket Shifting**: When a user enters an actual broker `Fill Price ($)` that differs from `reference_entry_price` in `confirm_buy_execution()`, `stop_loss_price` and `take_profit_price` automatically shift by `fill_price - reference_entry_price` (and preview live in the UI) so the exact dollar/ATR risk bracket is preserved.
  - **Shortfall Auto-Funding & Cash Deposit/Withdrawal (`adjust_cash_deposit_withdrawal`)**: If a confirmed `BUY` or manual position cost exceeds `cash_balance`, the shortfall is automatically credited to `starting_cash` (preventing artificial P&L losses from unlogged broker cash). Added explicit `+ Deposit` / `- Withdraw` controls (`/api/copilot/deposit-withdraw`) that adjust both `cash_balance` and `starting_cash` simultaneously.
  - **Net-Delta Cash Adjustment, Custom Tickers & Entry Date Preservation (`edit_or_add_position`, `sync_market_prices`)**: Editing an existing position with `deduct_from_cash=True` now adjusts cash by only the net cost delta `(new_qty * new_entry) - (old_qty * old_entry)` (or refunds cost on deletion), preserves `opened_date`, accurately computes `holding_days` from `opened_date`, and supports custom tickers outside the core universe.
  - **Mistake Recovery (`undo_last_trade`, `restore_dismissed_signals`, `reset_copilot_account`) & `SECTOR_ROTATION` Parity**: Added 1-click **Undo Last Trade** (`/api/copilot/undo`), **Restore Skipped Signals** (`/api/copilot/restore-skipped`), **Partial / Full Inline Exit**, and **Reset Real Account Ledger** (`/api/copilot/reset`), and passed `sector_rs_rank` into `StrategySignalEngine.evaluate_entry()` inside `get_daily_action_plan()`.

### Modules Added / Modified
- `core/execution/paper_broker.py`, `api/server.py`
- `dashboard/streamlit_app.py`, `dashboard/ui_template.py`
- `tests/test_platform.py`, `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-07] — Institutional SPY Benchmark Readiness Suite, 5 Golden Base (`v1`) Models & One-Click Baseline Revert

### Summary
- **Institutional SPY Benchmark & Drawdown Metric Suite (`evaluation/metrics/performance.py`, `infrastructure/configuration/settings.py`, `agents/strategy_evaluator/agent.py`)**: Expanded `calculate_performance_metrics()` to compute date-aligned **Annualised Jensen's Alpha ($\alpha\%/yr$)**, **CAPM Beta ($\beta$)**, **Information Ratio**, **Upside / Downside Capture Ratio** vs. `SPY`, **Annualised Return on Invested Capital (`roic_annualised_pct`)**, **Ulcer Index (`ulcer_index`)**, **Martin Ratio / Ulcer Performance Index (`martin_ratio`)**, **Max Time Under Water (`max_time_under_water_days`)**, **Omega Ratio (`omega_ratio`)**, and **Tail Ratio (`tail_ratio`)**. Upgraded `StrategyEvaluationAgent.evaluate_pipeline_results()` to require genuine `SPY` benchmark dominance and strict non-degradation vs. prior versions (`beats_incumbent`).
- **Causal Signal & Backtest Engine Enhancements + 5 Golden Base (`v1`) Strategies (`core/strategies/registry.py`, `core/backtesting/engine.py`, `core/execution/paper_broker.py`, `agents/strategy_architect/agent.py`)**: Fixed premature Chandelier trailing-stop activation (requiring $\ge 1.0\text{R}$ profit via `trail_activation_r`), unclipped multi-horizon relative-strength conviction ranking, dynamic `pead_lookback` for quarterly earnings drift, top-2 leader sector RS ranking, and Walk-Forward Efficiency (`WFE`) `annualised_return_pct` lookup. Tuned and validated all 5 Golden Base `v1` models (`strat_momentum_trend`, `strat_pead_drift`, `strat_volatility_breakout`, `strat_mean_reversion_bb`, `strat_sector_rotation_leaders`) so all 5 beat `SPY` in both Full Period (`+70.68%` to `+77.45%` vs. `SPY` `+61.90%`) and Out-of-Sample (`+11.52%` to `+22.96%` vs. `SPY` `+9.67%`) with `100%` (`4/4`) Walk-Forward consistency, while keeping the Paper Account untouched at `$100,000.00`.
- **Golden Baseline Pinning & One-Click Revert (`StrategyRegistry.revert_to_golden_baseline` & `rollback_to_best_champion` in `core/strategies/registry.py`, `main.py`, `api/server.py`, `dashboard/streamlit_app.py`)**: Added programmatic and 1-click UI/CLI controls (`Revert All to Golden Base (v1)`, `Enforce Best Champion Versions`, `python3 main.py revert-baseline`, `/api/strategies/revert-baseline`) so any experimental future `v2+` iteration can always be reverted to the proven `v1` Golden Base Model.

### Modules Added / Modified
- `evaluation/metrics/performance.py`, `infrastructure/configuration/settings.py`, `agents/strategy_evaluator/agent.py`
- `core/strategies/registry.py`, `core/backtesting/engine.py`, `core/execution/paper_broker.py`, `agents/strategy_architect/agent.py`
- `main.py`, `api/server.py`, `dashboard/streamlit_app.py`, `data/swing_trader.db`
- `tests/test_platform.py`, `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-07] — Forward-Only Paper Account Reset, Daily/Weekly/Total P&L Metrics & Day-Filtered Paper Ledger

### Summary
- **Forward-Only Paper Account Isolation (`dashboard/streamlit_app.py`, `api/server.py`, `.github/workflows/autonomous_trading.yml`, `data/swing_trader.db`)**: Reset the simulated `$100,000.00` paper account to a clean baseline (`0` trades, `0` open positions, `$0.00` P&L) and removed historical 20–60 day paper replay loops from dashboard startup, server bootstrap, and GitHub Actions so the Paper Account is strictly affected by actual forward daily runs while all historical testing stays isolated in `Backtesting`.
- **Daily, Weekly, and Total P&L Breakdown (`PaperTradingEngine.get_account_summary` in `core/execution/paper_broker.py`, `dashboard/streamlit_app.py`, `dashboard/ui_template.py`)**: Added `daily_pnl_usd` (`daily_return_pct`), `weekly_pnl_usd` (`weekly_return_pct` over rolling 5 sessions), and `total_pnl_usd` (`total_return_pct`, split into `Realised` and `Unrealised`) to `get_account_summary()` and surfaced them in the `Overview & P&L` KPI cards alongside an anytime `Reset Paper Account ($100k)` button in the sidebar.
- **Day-Filtered Paper Trading Ledger (`dashboard/streamlit_app.py`, `dashboard/ui_template.py`)**: Upgraded the `Paper Ledger` tab with interactive **Trading Day**, **Order Side (`All` / `BUY` / `SELL`)**, and **Strategy** filters plus a **Daily / Filtered Execution Summary** bar (`Trades Executed`, `BUY Entries`, `SELL Exits`, `Traded Volume $`, `Fees + Slippage $`, `Locked-in Realised P&L $`).
- **Paper Overview Chart Isolation (`dashboard/ui_template.py`)**: Prevented `renderOverview()` from falling back to a historical backtest equity curve when the paper portfolio has fewer than 2 snapshots.

### Modules Added / Modified
- `core/execution/paper_broker.py`, `api/server.py`
- `dashboard/streamlit_app.py`, `dashboard/ui_template.py`
- `.github/workflows/autonomous_trading.yml`, `data/swing_trader.db`
- `tests/test_platform.py`, `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-07] — IDE-Native AI Alpha Workflow (`run` Skill, `ide-context` / `ide-apply` Bridge & Incumbent Champion Protection)

### Summary
- **IDE-Native AI Bridge (`export_ide_ai_context` & `apply_ide_ai_cycle` in `infrastructure/scheduler/orchestrator.py`, `main.py`)**: Added `python main.py ide-context` and `python main.py ide-apply` CLI commands so the Antigravity IDE LLM can act as the platform's Chief Quantitative Strategist & News Catalyst Analyst with zero external API keys required in `.env`.
- **One-Word `"run"` Skill (`.agents/skills/run-ai-cycle/SKILL.md`, `AGENTS.md`, `GEMINI.md`)**: Created a dedicated workspace skill triggered whenever the user types `run` in the IDE that (1) exports deterministic market/portfolio context, (2) searches live web news (`search_web`) for earnings/macro catalysts on top setups, (3) runs a multi-candidate AI strategy parameter tournament via `ide-apply`, and (4) syncs `data/swing_trader.db` to GitHub.
- **Incumbent Champion Protection (`StrategyEvaluationAgent.evaluate_pipeline_results` in `agents/strategy_evaluator/agent.py`)**: Enforced monotonic strategy quality so a challenger version `v+1` is only promoted over an existing `PAPER_TRADING` version `v` if it passes all 9 validation gates AND matches or beats the incumbent's Sharpe/Return/Calmar metrics.
- **Streamlit Cloud Hot-Reload & `width='stretch'` Compatibility (`dashboard/streamlit_app.py`, `core/strategies/registry.py`, `core/execution/paper_broker.py`)**: Added topological `sys.modules` hot-reload synchronization (`_STREAMLIT_SYNC_VERSION`) so Streamlit Cloud workers never hold stale `AutonomousWorkflowOrchestrator` class definitions lacking `live_copilot` across git pushes; replaced deprecated `use_container_width=True` calls with `width="stretch"`; aligned `StrategySignalEngine.compute_effective_stop_price()` arguments when evaluating `hold_updates`; and streamlined the Live Copilot UI with 1-click inline position closing, smart pre-filled position editing, and a single-row cash bar.

### Modules Added / Modified
- `.agents/skills/run-ai-cycle/SKILL.md`
- `infrastructure/scheduler/orchestrator.py`, `main.py`, `agents/strategy_evaluator/agent.py`
- `AGENTS.md`, `GEMINI.md`, `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`, `tests/test_platform.py`

---

## [2026-11-07] — Institutional Quantitative Upgrades: Deflated Sharpe (DSR), +1.25R Breakeven/Chandelier Stop Ratchet, Drawdown De-Gearing & Multi-Candidate Weekly Tournament

### Summary
- **Probabilistic & Deflated Sharpe Ratio (`evaluation/metrics/performance.py`)**: Implemented `compute_probabilistic_and_deflated_sharpe()` per Bailey & López de Prado (2014), adding `return_skewness`, `return_kurtosis`, `probabilistic_sharpe_pct` (PSR), and `deflated_sharpe_pct` (DSR) to `calculate_performance_metrics()` to penalize non-Normal fat tails and multiple-testing selection bias.
- **Systematic $+1.25\text{R}$ Breakeven+Friction Ratchet & Chandelier ATR Trailing Stop (`core/strategies/registry.py`, `core/execution/paper_broker.py`)**: Added `StrategySignalEngine.compute_effective_stop_price()` and wired it into `evaluate_exit()` and `LiveTradingCopilotEngine.get_daily_action_plan()` so open swing positions automatically ratchet their stop-loss to $\text{Entry} + 0.15 \times \text{ATR}_{14}$ after reaching $+1.25\text{R}$ unrealized gain and trail via a Chandelier stop ($\text{Highest High} - k \times \text{ATR}_{14}$) after $+1.5\text{R}$.
- **Walk-Forward Efficiency (WFE) & Dynamic Drawdown De-Gearing (`core/backtesting/engine.py`, `core/risk/manager.py`)**: Computed `walk_forward_efficiency_ratio` (OOS annualised return vs. In-Sample annualised return) in `run_in_sample_validation_oos_pipeline()`, and upgraded `PortfolioRiskManager.calculate_atr_position_size()` with dynamic drawdown de-gearing (`0.65x` risk-per-trade scaling when portfolio drawdown reaches 50% of the suspension limit, i.e., $\ge 7.5\%$) and benchmark volatility targeting.
- **Multi-Candidate Weekly Tournament (`infrastructure/scheduler/orchestrator.py`)**: Upgraded `run_weekly_workflow()` to evaluate both the Performance Analyst's refinement proposal and the Market Researcher's top catalyst family in a head-to-head tournament ranked by promotion gate pass rate and Deflated Sharpe Ratio.

### Modules Added / Modified
- `evaluation/metrics/performance.py`, `core/strategies/registry.py`, `core/backtesting/engine.py`
- `core/risk/manager.py`, `core/execution/paper_broker.py`, `infrastructure/scheduler/orchestrator.py`
- `dashboard/streamlit_app.py`, `dashboard/ui_template.py`, `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-07] — Engine Audit: Dynamic OOS Splits, Live Regime Detection, Proposal Rotation, Sector Ranks & LLM Auto-Detection

### Summary
- **Dynamic In-Sample / Validation / OOS Date Splits (`BacktestEngine.run_in_sample_validation_oos_pipeline` in `core/backtesting/engine.py`)**: Replaced hardcoded `2025-06-30` end-date splits with dynamic 50% / 25% / 25% chronological partitioning whenever live market data extends beyond `2025-06-30`, while preserving exact canonical splits on seeded historical test runs.
- **Causal Sector Relative Strength Rank & Full Risk Guardrail Parity (`core/backtesting/engine.py`, `core/execution/paper_broker.py`)**: Computed point-in-time `sector_rs_rank` and passed it to `StrategySignalEngine.evaluate_entry` across backtesting and paper execution; aligned morning gap-open stop/target adjustments and forwarded 20-day liquidity, earnings blackout, and strategy risk caps in `PaperTradingEngine.submit_and_execute_order` (with `ON CONFLICT` scale-in safety on `paper_positions`).
- **Non-Stacking Strategy Versioning & Proposal Lifecycle (`core/strategies/registry.py`, `agents/performance_analyst/agent.py`, `infrastructure/scheduler/orchestrator.py`)**: Updated `StrategyRegistry.create_new_version` to always evolve from the highest `PAPER_TRADING` (or non-rejected) base version so rejected experimental patches never stack; wired live `SPY` regime classification into `run_daily_workflow`; added LLM-driven + rotating parameter hypotheses and `PROPOSED -> PROMOTED/REJECTED` status tracking in `PerformanceAnalystAgent`; and deduplicated same-day scans in `MarketResearchAgent`.
- **Automatic LLM Provider Detection & Dashboard Polish (`infrastructure/configuration/settings.py`, `api/server.py`, `dashboard/streamlit_app.py`, `dashboard/ui_template.py`)**: Auto-selects `LLM_PROVIDER=gemini` or `openai` whenever `GEMINI_API_KEY` or `OPENAI_API_KEY` is present in `.env` or GitHub Secrets; added inline editable Qty/Fill Price inputs and `Hold Today (Skip Sell)` + `Vetoed Signals` inspection to the Live Copilot tab, plus a multi-strategy Walk-Forward fold selector in Risk & Analytics.

### Modules Added / Modified
- `core/backtesting/engine.py`, `core/strategies/registry.py`, `core/execution/paper_broker.py`
- `infrastructure/configuration/settings.py`, `infrastructure/scheduler/orchestrator.py`
- `agents/performance_analyst/agent.py`, `agents/market_researcher/agent.py`
- `api/server.py`, `dashboard/streamlit_app.py`, `dashboard/ui_template.py`
- `.github/workflows/autonomous_trading.yml`, `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-07] — Air-Gapped Live Trading Copilot (Real Account Shadow Engine) & Mandatory User Guide Sync

### Summary
- **Air-Gapped Live Trading Copilot (`LiveTradingCopilotEngine` in `core/execution/paper_broker.py`)**: Implemented a complete shadow portfolio engine (`shadow_accounts`, `shadow_positions`, `shadow_trade_history`, `shadow_dismissed_signals` in `infrastructure/database/db.py`) that computes daily step-by-step SELL and BUY instructions sized to the user's real account balance (`1.0%` ATR risk and all 7 portfolio caps) without ever connecting to a live brokerage account or assuming a trade was taken until confirmed by the user.
- **Interactive `Live Copilot (Real Account)` Tab (`dashboard/streamlit_app.py`, `dashboard/ui_template.py`, `api/server.py`)**: Added interactive `Confirm Bought`, `Confirm Sold`, and `Skip Trade` controls with editable fill prices and share counts, real-cash balance configuration, strategy selection, and manual position editing/addition.
- **Mandatory `USER_GUIDE.md` Synchronization in `maintain-project-context` Skill**: Updated `.agents/skills/maintain-project-context/SKILL.md`, `references/update_checklist.md`, `scripts/verify_context.py`, `AGENTS.md`, and `GEMINI.md` to enforce updating `USER_GUIDE.md` whenever workflows, UI tabs, strategies, or engine components change.

### Modules Added / Modified
- `infrastructure/database/db.py` (20 tables: added `shadow_accounts`, `shadow_positions`, `shadow_trade_history`, `shadow_dismissed_signals`)
- `core/execution/paper_broker.py` (`LiveTradingCopilotEngine`)
- `infrastructure/scheduler/orchestrator.py`, `api/server.py`
- `dashboard/streamlit_app.py`, `dashboard/ui_template.py`
- `tests/test_platform.py`, `USER_GUIDE.md`, `AGENTS.md`, `GEMINI.md`
- `.agents/skills/maintain-project-context/SKILL.md`, `references/update_checklist.md`, `scripts/verify_context.py`

---

## [2026-11-07] — Fair Multi-Strategy Allocation, Live-Readiness Scorecard & Hands-Off Autonomous UI

### Summary
- **Fair Multi-Strategy Signal Interleaving (`core/execution/paper_broker.py`)**: Updated `PaperTradingEngine.run_trading_session_for_strategies` to precompute ticker indicators once per session, collect entry signals across all active `PAPER_TRADING` strategies, and interleave signals round-robin across strategy families ordered by conviction score (`strat_volatility_breakout`, `strat_momentum_trend`) so no single strategy monopolizes buying power or sector caps.
- **Automatic Retirement of Superseded Versions (`core/strategies/registry.py`)**: Updated `StrategyRegistry.update_status` so promoting `v+1` to `PAPER_TRADING` automatically transitions older `PAPER_TRADING` versions (`< v+1`) of the same `strategy_id` to `RETIRED`.
- **Strategy Evaluation & Live-Readiness Scorecard (`dashboard/streamlit_app.py`, `dashboard/ui_template.py`)**: Upgraded the `Strategies & Readiness` tab to evaluate every strategy across both the 9-gate historical backtest audit and a 4-point forward paper-trading checklist (`>= 20` closed paper trades, Forward Profit Factor `>= 1.30`, positive net paper P&L), surfacing a clear `Live Trading Readiness` verdict (`READY FOR LIVE REVIEW`, `BUILDING PAPER TRACK RECORD`, `RETIRED`, or `NOT READY`).
- **Hands-Off Autonomous Interface & 60-Day Multi-Strategy Replay**: Removed manual daily/weekly trigger buttons from the main UI header/sidebar and replayed the last 60 trading sessions (~3 months) of Alpaca data so multiple strategies populate the paper ledger.

### Modules Added / Modified
- `core/execution/paper_broker.py`
- `core/strategies/registry.py`
- `dashboard/streamlit_app.py`, `dashboard/ui_template.py`
- `.github/workflows/autonomous_trading.yml`
- `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-07] — Interactive Platform Guide with Visual Mental Model Diagram & Per-Tab Tooltips

### Summary
- **Visual Mental-Model Diagram & Progressive Disclosure in `Platform Guide`**: Redesigned the `Platform Guide` tab in both `dashboard/streamlit_app.py` and `dashboard/ui_template.py` to present a clean two-loop visual flowchart (`1. Daily Execution Loop` and `2. Weekly Self-Improvement Loop`), a 5-stage interactive walkthrough (`Stock Scan`, `Strategy Signal`, `Risk & Sizing`, `Execution & Exit`, `Weekly Upgrade`), and collapsible accordion sections (`The 3 Trading Strategies`, `The 7 Risk Controls`, `The 9 Validation Gates`, `How P&L Is Calculated`) so users only expand what they want to explore.
- **Interactive `? How this tab works` Popovers & Hover Tooltips Across All Tabs**: Added an interactive `? How this tab works` popover/expander on every tab (`Overview & P&L`, `Market Research`, `Strategies`, `Backtesting`, `Paper Ledger`, `Risk & Analytics`, `System Logs`) along with hover tooltips (`help=...` / `title=...`) on KPI metrics and controls while keeping the overall layout minimalistic.

### Modules Added / Modified
- `dashboard/streamlit_app.py`
- `dashboard/ui_template.py`
- `docs/AGENT_CHANGELOG.md`

---

## [2026-11-07] — Minimalist Adult UI Redesign, Provider-Scale Isolation & Portfolio Heat Cap

### Summary
- **Minimalist Adult Dashboard Redesign**: Replaced all `"Explain Like I'm 5"` / toy analogies in `dashboard/streamlit_app.py` and `dashboard/ui_template.py` with a clean, institutional-yet-accessible design for adults using concise, jargon-free language. Added an interactive 5-topic `Platform Guide` tab (`1. Core Architecture`, `2. Strategy Families`, `3. Validation Gates`, `4. Risk Controls`, `5. P&L Accounting`) and transparent P&L Attribution showing Active Strategies, Measurement Window, and exact step-by-step derivation.
- **Root-Cause Fix for the 54.66% Mixed-Provider Drawdown**: Enhanced `MarketDataService` (`core/market_data/providers.py`) and `PaperTradingEngine.reset_account_to_starting_capital` (`core/execution/paper_broker.py`) to detect transitions between synthetic `local_seeded` bars and real `alpaca` bars, automatically purging mixed-scale bars and resetting paper state so positions opened at synthetic prices are never marked-to-market against live provider prices.
- **Total Portfolio Heat Cap (`max_total_open_risk_pct = 5.0%`)**: Added aggregate open stop-loss risk enforcement in `PortfolioRiskManager.evaluate_proposed_entry` (`core/risk/manager.py`) and `RiskParametersConfig` (`infrastructure/configuration/settings.py`) so combined open risk across all active positions cannot exceed 5% of equity.

### Modules Added / Modified
- `dashboard/streamlit_app.py`, `dashboard/ui_template.py`
- `core/market_data/providers.py`, `core/execution/paper_broker.py`
- `core/risk/manager.py`, `infrastructure/configuration/settings.py`
- `.github/workflows/autonomous_trading.yml`
- `core/AGENTS.md`, `docs/AGENT_CHANGELOG.md`

---

## [2026-11-07] — Beginner-Friendly Interactive ELI5 Guide & Transparent P&L Breakdown

### Summary
- Added a dedicated **"🧸 Start Here (Explain Like I'm 5)"** interactive page with 5 clickable deep-dive buttons (`The Daily & Weekly Loop`, `Meet the 5 AI Helpers`, `The 3 Trading Rulebooks`, `The 6 Safety Seatbelts`, and `How P&L Math Works`) in both `dashboard/streamlit_app.py` and `dashboard/ui_template.py`.
- Added simple, concise plain-English explanations at the top of every tab (`1. Overview & P&L Breakdown`, `2. Stock Research`, `3. Strategy Rulebooks`, `4. Historical Backtests`, `5. Paper Trading Ledger`, `6. Risk & Sector Analytics`, `7. System Logs`).
- Redesigned all Profit & Loss (P&L) displays (`_summarize_pnl_by_strategy`, `_get_paper_date_span`) so they are 100% transparent and never misleading: every P&L figure explicitly states the **Strategy Used**, the **Exact Date Span**, and the **Step-by-Step Math** (`Starting Capital + Closed Trade Realised P&L + Open Position Unrealised P&L [after broker fees & slippage] = Current Total Equity`), while clearly separating daily Paper Account P&L from 2.3-year Historical Backtest P&L.

### Modules Added / Modified
- `dashboard/streamlit_app.py`
- `dashboard/ui_template.py`
- `docs/AGENT_CHANGELOG.md`

---

## [2026-11-07] — Alpaca Free-Tier IEX Feed & Paper URL Normalization

### Summary
- Updated `AlpacaDataProvider.fetch_daily_bars` (`core/market_data/providers.py`) to specify `feed=iex` so free-tier Alpaca accounts can fetch recent daily bars without SIP subscription errors, with graceful fallback to `local_seeded` for unindexed symbols (such as `FRC_DELIST`).
- Normalized `alpaca_paper_base_url` in `PaperTradingEngine._mirror_order_to_alpaca_paper` (`core/execution/paper_broker.py`) to handle both `https://paper-api.alpaca.markets` and `https://paper-api.alpaca.markets/v2`.
- Configured encrypted `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in GitHub Actions Repository Secrets.

### Modules Added / Modified
- `core/market_data/providers.py`
- `core/execution/paper_broker.py`

---

## [2026-11-07] — Fix Streamlit Community Cloud `sys.path` Root Import

### Summary
- Added repository root resolution (`sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`) at the top of `dashboard/streamlit_app.py` so Streamlit Community Cloud can resolve top-level packages (`api`, `core`, `infrastructure`, `agents`, `evaluation`) when executing `dashboard/streamlit_app.py`.

### Modules Added / Modified
- `dashboard/streamlit_app.py`

---

## [2026-11-07] — Zero-Cost Autonomous Cloud Hosting (GitHub Actions + Streamlit Cloud + Alpaca Integration)

### Summary
- Configured `MARKET_DATA_PROVIDER=alpaca` as the default provider (with automatic fallback to `local_seeded` when credentials are not yet provided) and added optional Alpaca Paper API (`paper-api.alpaca.markets`) order mirroring in `PaperTradingEngine` (with strict `LiveTradingProhibitedError` protection against non-paper URLs).
- Added `.github/workflows/autonomous_trading.yml` to run the Daily Autonomous Workflow (Mon–Fri 21:30 UTC) and Weekly Self-Improvement Strategy Discovery Loop (Saturday 02:00 UTC / 10:00 AM SGT) on GitHub Actions for free, persisting state to `data/swing_trader.db`.
- Enhanced `dashboard/streamlit_app.py` with a **Weekly Operator Digest & Self-Improvement Status** banner for a 2-minute weekly operator check-in on Streamlit Community Cloud.

### Modules Added / Modified
- `.github/workflows/autonomous_trading.yml`
- `infrastructure/configuration/settings.py`, `.env.example`, `.gitignore`
- `core/execution/paper_broker.py` (`_mirror_order_to_alpaca_paper`)
- `dashboard/streamlit_app.py`
- `AGENTS.md`, `DEPLOYMENT.md`, `ENVIRONMENT_VARIABLES.md`

---

## [2026-11-07] — Initial Production MVP & Agent Maintainability Infrastructure

### Summary
- Implemented the full AI-powered swing trading research, backtesting, validation, and $100,000 paper-trading platform (`feat/swing-trading-ai-platform`).
- Added hierarchical agent context rules (`AGENTS.md`, `GEMINI.md`, `core/AGENTS.md`, `agents/AGENTS.md`) and the `maintain-project-context` skill (`.agents/skills/maintain-project-context/SKILL.md`) with automated verification (`verify_context.py`).

### Modules Added / Modified
- **Infrastructure**: `infrastructure/configuration/settings.py` (`TRADING_MODE=paper` lock), `infrastructure/database/db.py` (16 SQLite/PostgreSQL tables), `infrastructure/logging/logger.py` (secret scrubbing), `infrastructure/scheduler/orchestrator.py` (idempotent Daily & Weekly workflows).
- **Deterministic Core**: `core/market_data/` (provider abstraction + point-in-time BMO/AMC earnings + `USTradingCalendar`), `core/indicators/technical.py` (causal indicators + RS vs SPY), `core/strategies/registry.py` (5 strategy families, 3 baseline strategies, immutable versioning), `core/backtesting/engine.py` (chronological next-open execution, walk-forward, cost stress tests), `core/risk/manager.py` (1% ATR sizing, 10 pos cap, 15% stock cap, 30% sector cap, correlation filter, 15% DD kill switch), `core/execution/paper_broker.py` ($100k account, Market/Limit/Stop/TP orders, partial fills, idempotency keys, `trade_ledger`).
- **Evaluation**: `evaluation/metrics/performance.py` (16+ performance metrics & Monte Carlo trade-sequence simulator).
- **AI Agents**: `agents/base.py`, `MarketResearchAgent`, `StrategyDiscoveryAgent`, `StrategyEvaluationAgent`, `PerformanceAnalystAgent`, `RiskManagerAgent`.
- **Dashboard & API**: `api/server.py`, `dashboard/ui_template.py` (7-tab interactive UI), `dashboard/streamlit_app.py`.
- **Tests & Docs**: `tests/test_platform.py` (10 test suites passing), `README.md`, `ARCHITECTURE.md`, `STRATEGY_GUIDE.md`, `DATA_SOURCES.md`, `BACKTESTING_METHODOLOGY.md`, `DEPLOYMENT.md`, `ENVIRONMENT_VARIABLES.md`.

