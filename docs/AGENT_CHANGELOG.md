# Agent Implementation & Maintenance Changelog

This log tracks architectural additions, strategy changes, schema updates, and verification runs performed by AI coding agents in this repository. Every implementation must append an entry here per the `maintain-project-context` skill.

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
- `docs/AGENT_CHANGELOG.md`

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

