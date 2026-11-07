# AGENTS.md — Swing Trading AI Platform Context & Engineering Rules

This file provides authoritative project context, architectural invariants, safety rules, and mandatory maintenance workflows for AI coding agents working in this repository.

---

## 1. Project Overview & Core Philosophy

This repository implements an autonomous **AI-Powered Swing Trading Research, Backtesting, Validation, and Paper-Trading Platform** for US equities (`NYSE` and `NASDAQ`, benchmarked against `SPY`).

### Non-Negotiable Architectural Firewall
**Deterministic financial software is strictly separated from AI reasoning.**

- **Deterministic Core (`core/`, `evaluation/`, `infrastructure/`)** MUST handle all:
  - Price, corporate-action (split/dividend), and point-in-time (`BMO`/`AMC`) earnings normalization.
  - Causal technical indicator calculations (`SMA`, `EMA`, `MACD`, `RSI`, `ATR`, `Bollinger`, `RS vs SPY`).
  - Strategy signal generation from approved machine-readable rules (`StrategySignalEngine`).
  - ATR-based position sizing, portfolio risk vetoes, and emergency kill-switch logic (`PortfolioRiskManager`).
  - Chronological bar-by-bar backtesting, walk-forward validation, and transaction cost stress testing (`BacktestEngine`).
  - Simulated order execution, duplicate order prevention (`idempotency_key`), cash/position reconciliation, and trade ledger accounting (`PaperTradingEngine`).
- **AI Agent Layer (`agents/`)** MAY ONLY:
  - Scan markets and produce schema-validated `CandidateResearchReport` artefacts (`MarketResearchAgent`).
  - Propose falsifiable hypotheses and machine-readable `StrategyConfig` drafts (`StrategyDiscoveryAgent`).
  - Audit backtest/walk-forward evidence against promotion thresholds (`StrategyEvaluationAgent`).
  - Review post-close session attribution and write `ExperimentProposal` artefacts (`PerformanceAnalystAgent`).
  - Audit portfolio risk health and trigger kill-switch protections (`RiskManagerAgent`).

---

## 2. Hard Safety & Quantitative Invariants

1. **Paper Trading Lock (`TRADING_MODE=paper`)**:
   - `infrastructure/configuration/settings.py` enforces `TRADING_MODE=paper` ($100,000 USD virtual account). Any non-paper mode raises `LiveTradingProhibitedError`. Never bypass or weaken this check.
2. **No Secret Leakage**:
   - Never hardcode or log API keys, tokens, or credentials. Always use `get_logger()` from `infrastructure/logging/logger.py` (`SecretScrubbingFilter`).
3. **Zero Look-Ahead & Survivorship Bias**:
   - Indicator functions in `core/indicators/technical.py` must be strictly causal up to bar $i$.
   - Signals generated at Day $T$ close must execute at Day $T+1$ open (`adj_open` + spread + slippage) in `core/backtesting/engine.py`.
   - `AMC` (After-Market-Close) earnings on Day $T$ are only visible starting Day $T+1$ (`EarningsEvent.is_publicly_available_as_of`).
   - Delisted securities (`is_active=False`, `delisted_date`) must remain in historical backtests until their delisting date.
4. **Immutable Active Strategies**:
   - Never overwrite a `StrategyConfig` version in `strategy_registry` whose status is `PAPER_TRADING`. Use `StrategyRegistry.create_new_version()` to create `v+1` in `DRAFT` status.
5. **Role Permission Enforcement**:
   - Every agent method must call `self.assert_permission("<action>")` (`agents/base.py`) and validate outputs with `validate_required_fields()`.

---

## 3. Codebase Map & Module Reference

| Directory / File | Responsibility | Key Symbols |
|---|---|---|
| `main.py` | CLI entrypoint (`demo`, `bootstrap`, `daily`, `weekly`, `serve`) | `main()`, `cmd_demo()` |
| `infrastructure/configuration/settings.py` | Environment config, risk & promotion defaults, paper-mode lock | `Settings`, `RiskParametersConfig`, `PromotionCriteriaConfig`, `LiveTradingProhibitedError` |
| `infrastructure/database/db.py` | 16-table SQLite/PostgreSQL relational persistence & API cache | `DatabaseManager`, `SCHEMA_SQL` |
| `infrastructure/logging/logger.py` | Structured logging with regex & explicit secret redaction | `get_logger()`, `SecretScrubbingFilter` |
| `infrastructure/scheduler/orchestrator.py` | Idempotent Daily & Weekly workflow job orchestration | `AutonomousWorkflowOrchestrator` |
| `core/market_data/models.py` | Domain models & NYSE/NASDAQ holiday calendar | `DailyBar`, `EarningsEvent`, `EquityMetadata`, `USTradingCalendar` |
| `core/market_data/providers.py` | Pluggable data providers & normalization/deduplication service | `MarketDataService`, `LocalSeededDataProvider`, `AlpacaDataProvider`, `PolygonDataProvider` |
| `core/indicators/technical.py` | Causal technical indicators & relative strength vs `SPY` | `compute_indicator_series()`, `IndicatorSnapshot` |
| `core/strategies/registry.py` | 5 Strategy families, deterministic signal engine, version registry | `StrategyConfig`, `StrategySignalEngine`, `StrategyRegistry`, `get_baseline_strategies()` |
| `core/backtesting/engine.py` | Event-driven chronological backtester, walk-forward, stress tests | `BacktestEngine`, `BacktestResult` |
| `core/risk/manager.py` | Trade veto authority, ATR sizing, sector/stock caps, kill switch | `PortfolioRiskManager`, `RiskDecision` |
| `core/execution/paper_broker.py` | $100k simulated brokerage, order types, idempotency, trade ledger, and air-gapped Live Trading Copilot | `PaperTradingEngine`, `LiveTradingCopilotEngine`, `OrderSubmissionResult` |
| `evaluation/metrics/performance.py` | 16+ performance metrics & Monte Carlo trade-sequence simulator | `calculate_performance_metrics()`, `run_monte_carlo_trade_sequence()` |
| `agents/base.py` | LLM abstraction (`deterministic_research`, `gemini`, `openai`), permissions | `BaseAgent`, `LLMProvider`, `validate_required_fields()` |
| `agents/market_researcher/agent.py` | Universe scanner & multi-factor candidate ranker | `MarketResearchAgent`, `CandidateResearchReport` |
| `agents/strategy_architect/agent.py` | Falsifiable hypothesis & `StrategyConfig` generator | `StrategyDiscoveryAgent` |
| `agents/strategy_evaluator/agent.py` | 9-gate promotion/rejection auditor | `StrategyEvaluationAgent`, `StrategyEvaluationReport` |
| `agents/performance_analyst/agent.py` | Post-session attribution & `ExperimentProposal` generator | `PerformanceAnalystAgent`, `ExperimentProposal` |
| `agents/risk_manager/agent.py` | Portfolio health & kill-switch governance agent | `RiskManagerAgent` |
| `api/server.py` | HTTP REST API & 7-tab Web Dashboard server | `PlatformApplication`, `run_server()` |
| `dashboard/ui_template.py` | Interactive 7-tab HTML/SVG/JS frontend | `DASHBOARD_HTML` |
| `dashboard/streamlit_app.py` | Streamlit Community Cloud 24/7 hosted dashboard & Weekly Digest | `main()` |
| `.github/workflows/autonomous_trading.yml` | Scheduled Daily & Weekly GitHub Actions automation | `autonomous-trading-cycle` |
| `tests/test_platform.py` | 10-suite unit & end-to-end integration test runner | `TestSwingTradingPlatform` |

---

## 4. Mandatory Agent Maintenance Protocol (For Every Implementation)

Whenever you implement a feature, fix a bug, add an indicator/strategy/agent/provider, or modify schemas in this repository, you **MUST** activate and follow the workspace skill:
- **`maintain-project-context`** (`.agents/skills/maintain-project-context/SKILL.md`)

Before completing any task, you must:
1. Run `.venv/bin/python .agents/skills/maintain-project-context/scripts/verify_context.py` to verify all unit/integration tests and documentation sync checks pass.
2. Update `AGENTS.md`, `GEMINI.md`, `USER_GUIDE.md`, subdirectory context files (`core/AGENTS.md`, `agents/AGENTS.md`), and the relevant topical Markdown docs (`ARCHITECTURE.md`, `STRATEGY_GUIDE.md`, `DATA_SOURCES.md`, `BACKTESTING_METHODOLOGY.md`, `DEPLOYMENT.md`, `ENVIRONMENT_VARIABLES.md`, `README.md`) to reflect your changes.
3. Append a concise entry to ` docs/AGENT_CHANGELOG.md` recording the architectural/code changes made.

