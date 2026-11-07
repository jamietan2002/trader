# Swing Trading AI — Systematic Quantitative Research & Paper-Trading Platform

A production-quality, autonomous AI-powered swing trading research, backtesting, validation, and paper-trading platform for US equities (NYSE & NASDAQ).

> **Core Governance Principle**: Deterministic financial software handles all price/indicator math, signal generation, ATR position sizing, risk checks, order simulation, portfolio accounting, P&L reconciliation, and promotion gating. AI agents operate strictly via structured, validated schemas to research markets, propose falsifiable hypotheses, audit backtest results, and diagnose strategy weaknesses.
>
> **Safety Lock**: `TRADING_MODE=paper` ($100,000 USD virtual account) is enforced at startup and before every order submission. Real-money execution is strictly prohibited (`LiveTradingProhibitedError`).

---

## Quick Start (Local Execution)

### 1. Verify Python Environment
The platform runs out-of-the-box with Python 3.11+ (using a zero-compilation standard-library SQLite + HTTP core, while supporting optional external providers and Docker/PostgreSQL deployments).

```bash
# Create or use virtual environment
/Library/GoogleCorpSupport/Python/3.11/bin/python3 -m venv .venv

# Copy environment configuration template
cp .env.example .env
```

### 2. Run the End-to-End Quantitative & Paper-Trading Lifecycle Demo
```bash
.venv/bin/python main.py demo
```
This command:
1. Ingests historical US equity data (16 symbols across 6 GICS sectors + `SPY` benchmark + delisted security `FRC_DELIST` for survivorship-bias verification, corporate actions, and point-in-time BMO/AMC earnings).
2. Registers and backtests the **3 baseline strategies** (`strat_momentum_trend`, `strat_pead_drift`, `strat_volatility_breakout`) across In-Sample, Validation, Out-of-Sample, Walk-Forward, and Transaction Cost Stress-Testing splits.
3. Evaluates each strategy via the `StrategyEvaluationAgent` against 9 statistical promotion gates.
4. Runs the autonomous **Daily Workflow** (Pre-Market Research Scan -> Market-Hours Paper Execution -> Post-Close Reconciliation & Performance Analysis) in a **$100,000 USD paper account**.
5. Runs the autonomous **Weekly Workflow** (AI Strategy Discovery -> Backtest -> Walk-Forward Validation -> Promotion/Rejection).

### 3. Launch the Interactive 7-Tab Web Dashboard & REST API
```bash
.venv/bin/python main.py serve --host 127.0.0.1 --port 8080
```
Open **`http://127.0.0.1:8080`** in your browser to inspect:
1. **Overview**: Portfolio equity, total/daily return vs `SPY`, available cash, open positions, drawdown, and equity curves.
2. **Market Research**: Ranked US equity candidates, bullish/bearish theses, catalysts, earnings, and `research_confidence_score` (explicitly distinguished from profit probability).
3. **Strategy Registry**: Versioned strategies (`DRAFT -> BACKTESTING -> VALIDATION -> PAPER_TRADING -> REJECTED -> RETIRED`).
4. **Backtesting Engine**: Launch custom backtests, inspect equity & drawdown curves, and audit individual trade executions.
5. **Paper Trading**: Open positions, order history, cash/buying power, realised & unrealised P&L, and strategy attribution.
6. **Portfolio Analytics**: Performance by market regime, sector exposure concentration, and walk-forward validation folds.
7. **System Monitoring**: Idempotent job execution logs and `PortfolioRiskManager` veto/alert audit trails.

### 4. Run the Automated Test Suite
```bash
.venv/bin/python -m unittest discover -s tests -p "test_*.py" -v
```

---

## Documentation Index

- [AGENTS.md](AGENTS.md) & [GEMINI.md](GEMINI.md) — Agent context, architectural invariants, codebase map, and mandatory maintenance rules.
- [`maintain-project-context` Skill](.agents/skills/maintain-project-context/SKILL.md) — Workspace skill & automated verification script (`verify_context.py`) ensuring agents keep context and docs synchronized on every implementation.
- [docs/AGENT_CHANGELOG.md](docs/AGENT_CHANGELOG.md) — Chronological agent implementation and architectural changelog.
- [ARCHITECTURE.md](ARCHITECTURE.md) — Modular monolith design, deterministic vs AI boundaries, and database schema.
- [STRATEGY_GUIDE.md](STRATEGY_GUIDE.md) — Specification of the 5 strategy families, entry/exit rules, and ATR risk sizing.
- [DATA_SOURCES.md](DATA_SOURCES.md) — Evaluation of Alpaca, Polygon, FMP, Finnhub, SEC EDGAR, and point-in-time normalization.
- [BACKTESTING_METHODOLOGY.md](BACKTESTING_METHODOLOGY.md) — Bias prevention, transaction cost modeling, walk-forward validation, and promotion criteria.
- [DEPLOYMENT.md](DEPLOYMENT.md) — Local CLI, Web Server, Streamlit, and Docker Compose deployment instructions.
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) — Complete reference for `.env` configuration and safety variables.

