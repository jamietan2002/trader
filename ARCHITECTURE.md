# System Architecture

## 1. Core Architectural Philosophy: Deterministic Quant vs. AI Reasoning

The platform is engineered as a **modular monolith** with a strict, auditable firewall between **AI agent reasoning** and **deterministic financial execution**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI AGENT LAYER (Structured JSON)                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────────────┐  │
│  │ MarketResearch   │  │ StrategyDiscovery│  │ StrategyEvaluationAgent   │  │
│  │ Agent            │─▶│ Agent            │─▶│ (9 Promotion Gates)       │  │
│  └──────────────────┘  └──────────────────┘  └───────────────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐                                 │
│  │ Performance      │  │ RiskManager      │  * Restricted Tool Permissions  │
│  │ AnalystAgent     │  │ Agent (Audit)    │  * Schema Validation Required   │
│  └──────────────────┘  └──────────────────┘                                 │
└───────────────┬───────────────────┬─────────────────────────┬───────────────┘
                │ Persisted         │ Machine-Readable        │ Status
                ▼ Research          ▼ StrategyConfig          ▼ Transitions
┌─────────────────────────────────────────────────────────────────────────────┐
│                   DETERMINISTIC QUANTITATIVE CORE ENGINE                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────────────┐  │
│  │ MarketDataService│  │ Technical        │  │ StrategySignalEngine      │  │
│  │ (Point-in-Time)  │─▶│ Indicators (ATR) │─▶│ (Chronological Rules)     │  │
│  └──────────────────┘  └──────────────────┘  └───────────────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────────────┐  │
│  │ BacktestEngine & │  │ PortfolioRisk    │  │ PaperTradingEngine        │  │
│  │ Walk-Forward     │  │ Manager (Veto)   │─▶│ ($100k USD, Idempotent)   │  │
│  └──────────────────┘  └──────────────────┘  └───────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Role Permission Matrix (`agents/base.py`)

| Agent Role | Allowed Actions | Strictly Prohibited Actions |
|---|---|---|
| `market_researcher` | `read_market_data`, `read_indicators`, `read_earnings_and_catalysts`, `write_research_report` | `execute_order`, `modify_portfolio`, `promote_strategy` |
| `strategy_architect` | `read_research_reports`, `read_strategy_registry`, `register_draft_strategy` | `execute_order`, `modify_portfolio`, `promote_strategy` |
| `strategy_evaluator` | `read_backtest_results`, `read_walk_forward_results`, `evaluate_and_transition_strategy_status` | `execute_order`, `modify_portfolio` |
| `performance_analyst` | `read_paper_account`, `read_trade_ledger`, `read_strategy_performance`, `write_experiment_proposal` | `execute_order`, `modify_portfolio`, `overwrite_active_strategy` |
| `risk_manager` | `read_paper_account`, `veto_order`, `trigger_kill_switch` | Direct arbitrary order creation |

---

## 2. Repository Structure

```
trader/
├── agents/
│   ├── base.py                        # LLM abstraction, schema validator, permission guardrails
│   ├── market_researcher/agent.py     # Universe scanner & multi-factor candidate ranker
│   ├── strategy_architect/agent.py    # Falsifiable hypothesis & StrategyConfig generator
│   ├── strategy_evaluator/agent.py    # 9-gate promotion/rejection auditor
│   ├── performance_analyst/agent.py   # Post-close attribution & ExperimentProposal generator
│   └── risk_manager/agent.py          # Portfolio health & kill-switch governance agent
├── core/
│   ├── market_data/
│   │   ├── models.py                  # DailyBar, EarningsEvent (BMO/AMC), USTradingCalendar
│   │   └── providers.py               # LocalSeeded, Alpaca, Polygon, FMP, Finnhub, SEC EDGAR
│   ├── indicators/technical.py        # Causal SMA, EMA, RSI, ATR, Bollinger, MACD, RS vs SPY
│   ├── strategies/registry.py         # 6 Strategy families (Long & Short), SignalEngine, immutable versioning
│   ├── backtesting/engine.py          # Chronological Long & Short bar-by-bar backtester, WF, stress tests
│   ├── risk/manager.py                # ATR sizing, Long/Short exposure & squeeze caps, kill switch
│   └── execution/paper_broker.py      # $100K paper account, 3-Pod All-Weather Alpaca Manager & Mistake Analyzer
├── evaluation/
│   └── metrics/performance.py         # 16+ metrics (Sharpe, Sortino, Calmar, PF) & Monte Carlo
├── infrastructure/
│   ├── configuration/settings.py      # Env settings, TRADING_MODE=paper lock, secret scrubbing
│   ├── database/db.py                 # 23-table relational schema (SQLite / PostgreSQL)
│   ├── logging/logger.py              # Regex secret-scrubbing structured logger
│   └── scheduler/orchestrator.py      # Idempotent Daily & Weekly workflows + holiday calendar
├── dashboard/
│   ├── ui_template.py                 # 7-tab interactive local SVG/HTML/JS dashboard
│   └── streamlit_app.py               # v2.1 4-Tab Autonomous Paper Hub, Day-by-Day Journal & Candlestick Charts
├── api/
│   └── server.py                      # REST API & web dashboard server
├── tests/
│   └── test_platform.py               # Automated unit & end-to-end integration test suite
└── main.py                            # CLI entrypoint (demo, bootstrap, daily, weekly, serve)
```

