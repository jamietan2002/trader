# Agent Implementation & Maintenance Changelog

This log tracks architectural additions, strategy changes, schema updates, and verification runs performed by AI coding agents in this repository. Every implementation must append an entry here per the `maintain-project-context` skill.

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

