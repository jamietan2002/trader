# Agent Implementation & Maintenance Changelog

This log tracks architectural additions, strategy changes, schema updates, and verification runs performed by AI coding agents in this repository. Every implementation must append an entry here per the `maintain-project-context` skill.

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

