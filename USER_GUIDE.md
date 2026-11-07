# Swing Trading AI — Operator User Guide & Technical Appendix

This guide explains in plain English what the platform does, how it runs on its own, whether it consumes AI tokens, and how you evaluate strategies when deciding to trade real money.

---

## Part 1: High-Level User Guide

### 1. What This Platform Does (In One Minute)
This system manages a simulated **$100,000 US stock portfolio** across liquid large-cap stocks on the NYSE and NASDAQ (`AAPL`, `MSFT`, `NVDA`, `AMD`, `AMZN`, `META`, `TSLA`, `AVGO`, `JPM`, `GS`, `LLY`, `UNH`, `XOM`, `CAT`), benchmarked against the S&P 500 (`SPY`).

- **Trading Style**: **Swing Trading** — holding stocks for **3 to 15 trading days** to capture multi-day price trends, breakouts, and post-earnings moves.
- **Safety Lock**: The system is hardcoded to **`TRADING_MODE = paper`**. It cannot touch real money.
- **100% Hands-Off**: It runs automatically in the cloud via GitHub Actions and displays live results on your hosted Streamlit dashboard. **Zero daily or weekly actions are required from you.**

---

### 2. How the Two Automated Loops Work

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ 1. DAILY LOOP (Mon–Fri at 21:30 UTC · After US Market Close)                 │
│                                                                              │
│  [Alpaca Market Data] ──► [AI Stock Scan] ──► [Active Strategy Rulebooks]    │
│                                                        │                     │
│  [Paper Ledger & P&L] ◄── [Paper Broker Fill] ◄── [7-Rule Risk Gate]         │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ 2. WEEKLY SELF-IMPROVEMENT LOOP (Saturdays at 10:00 AM SGT)                  │
│                                                                              │
│  [Review Week's Closed Trades] ──► [Draft Strategy Upgrade (v+1)]            │
│                                              │                               │
│  [Promote v+1 & Retire Old v]  ◄── [9-Gate Historical & Walk-Forward Audit]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### A. The Daily Loop (Mon–Fri, After US Market Close)
- **Purpose**: **Executes your approved strategies in real time** to build a forward paper-trading track record.
- **How it works**:
  1. Downloads the latest daily prices from Alpaca.
  2. Checks any currently held paper positions: if a stock hit its **Stop-Loss**, **Take-Profit**, **Trailing Stop**, or **Maximum Holding Period (10–15 days)**, it sells the stock and locks in **Realised P&L**.
  3. Checks all currently approved strategies (`PAPER_TRADING` status). Currently, two independent strategy families run every day:
     - **Momentum & Trend (`strat_momentum_trend`)**: Buys stocks in strong uptrends (above 20-day and 50-day moving averages) beating `SPY` over the last 20 days.
     - **Volatility Breakout (`strat_volatility_breakout`)**: Buys stocks breaking above their 20-day high on high volume after a quiet 10-day consolidation.
     - *(Note: A third baseline strategy, `strat_pead_drift`, failed 3 of the 9 historical validation gates and was automatically marked `REJECTED` so it cannot trade).*
  4. Interleaves buy signals fairly across all active strategies, sizes each position using volatility (`ATR`) so a stop-loss loses at most **1% of portfolio equity (`~$1,000`)**, verifies all **7 Risk Guardrails**, and logs the simulated trade after deducting brokerage commission and slippage.

#### B. The Weekly Loop (Saturdays, 10:00 AM SGT)
- **Purpose**: **Self-improves the strategies.**
- **How it works**:
  1. Reviews the week's closed paper trades and market regime.
  2. Proposes a refined version (`v2`, `v3`, etc.) of a strategy by adjusting quantitative entry/exit thresholds (for example, tightening the RSI filter or volume confirmation ratio).
  3. Tests the new version across **2.3+ years of historical data**, **4 walk-forward time windows**, and a **2x transaction-cost stress test**.
  4. If the new version passes **all 9 validation gates**, it is promoted to `PAPER_TRADING` and the older version (`v1`) is automatically marked `RETIRED`. If it fails even 1 gate, it is marked `REJECTED` and ignored.

---

### 3. Does It Use AI Tokens Daily or Weekly, or Is It Running a Script?
**By default, it uses zero paid AI tokens (`$0.00` LLM cost) and runs 100% via deterministic quantitative Python scripts.**

- **Default Mode (`LLM_PROVIDER = deterministic_research`)**:
  - All 5 agents (`MarketResearchAgent`, `StrategyDiscoveryAgent`, `StrategyEvaluationAgent`, `PerformanceAnalystAgent`, `RiskManagerAgent`) run using built-in **deterministic quantitative rule synthesis** (`DeterministicQuantReasoningProvider`).
  - Why? Because stock ranking, indicator calculation, parameter mutation (`v1 -> v2`), backtesting, and the 9-gate pass/fail audit are mathematical operations. Running them deterministically guarantees **zero hallucination, 100% reproducibility, and $0 token cost** on every daily and weekly run.
- **Optional LLM Narrative Mode (`gemini` or `openai`)**:
  - If you ever add a `GEMINI_API_KEY` or `OPENAI_API_KEY` to GitHub Secrets and set `LLM_PROVIDER=gemini` (or `openai`), the agents will use LLM tokens *only* to write richer natural-language commentary on research theses and post-session reviews.
  - Even with an LLM enabled, **all price math, signals, position sizing, risk vetoes, backtesting, and promotion pass/fail gates remain 100% deterministic Python code.**

---

### 4. What You Need to Know & When to Trade Real Money

1. **What is required from you day-to-day?**
   - **Nothing.** There are no buttons you need to press.
2. **How do you read the Profit & Loss (P&L) numbers?**
   - **Paper Portfolio P&L (`Overview & P&L` and `Paper Ledger` tabs)**: Shows your simulated `$100,000` account trading day-by-day:
     $$\text{Current Equity} = \$100,000\text{ (Start)} + \text{Realised P\&L (Closed Trades)} + \text{Unrealised P\&L (Open Positions)}$$
     Every fill already subtracts realistic broker fees and bid-ask slippage.
   - **Historical Backtest P&L (`Strategies & Readiness` and `Backtesting` tabs)**: Shows how a strategy rulebook performed over multi-year past history (`2023–2025`). Backtest numbers are used strictly to test rulebooks and are never mixed into your paper account cash.
3. **How do you evaluate when a strategy is ready for real trading?**
   - Open the **`Strategies & Readiness`** tab. Look at the **`Live Trading Readiness`** column:
   - A strategy automatically flips from `BUILDING PAPER TRACK RECORD` to **`READY FOR LIVE REVIEW`** only when it satisfies **all 4 real-money readiness checks**:
     1. **Passed 9 / 9 Historical Backtest & Walk-Forward Gates** (Sharpe $\ge 1.0$, Profit Factor $\ge 1.3$, Max Drawdown $\le 15\%$).
     2. **Completed $\ge 20$ Closed Paper Trades** in live forward daily sessions.
     3. **Forward Paper Profit Factor $\ge 1.30$** (making at least $\$1.30$ for every $\$1.00$ lost in live paper trading).
     4. **Positive Net Forward Paper P&L** after all fees and slippage.
   - Once a strategy reaches `READY FOR LIVE REVIEW`, you can simply check the `Overview & P&L` / `Paper Ledger` tab after market close and mirror its trades in your own brokerage account.

---

## Part 2: Technical Appendix (Engine Component Reference)

### A. Deterministic Quantitative Core (`core/` & `evaluation/`)
1. **Market Data Service (`core/market_data/providers.py`, `models.py`)**:
   - Ingests daily OHLCV bars from `AlpacaDataProvider` (`feed=iex`, with automatic fallback to `LocalSeededDataProvider` for offline testing), normalizes split/dividend adjustments (`adj_open`, `adj_high`, `adj_low`, `adj_close`), enforces US market holiday calendars (`USTradingCalendar`), and prevents look-ahead bias on `BMO`/`AMC` earnings releases.
   - Includes **Provider-Transition Isolation**: automatically detects if the database switches between synthetic (`local_seeded`) and live (`alpaca`) providers, purging incompatible price scales and resetting paper state so positions are never marked-to-market across different price scales.
2. **Causal Indicator Engine (`core/indicators/technical.py`)**:
   - Computes strictly causal technical series (`bars[0 : i + 1]`) for every bar: `SMA(20, 50, 200)`, `EMA(12, 26)`, `MACD(12, 26, 9)`, Wilder's `RSI(14)`, Wilder's `ATR(14)`, `Bollinger Bands(20, 2)`, `20-day Volume Ratio`, `10-day Consolidation Range %`, `20-day / 252-day Prior Highs`, and `20-day / 60-day Relative Strength vs. SPY`.
3. **Strategy Signal Engine & Version Registry (`core/strategies/registry.py`)**:
   - Evaluates structured JSON entry and exit rules (`StrategyConfig`) without free-form text interpretation.
   - Enforces immutable versioning (`DRAFT -> BACKTESTING -> VALIDATION -> PAPER_TRADING -> RETIRED / REJECTED`). Promoting `v+1` automatically transitions `v` to `RETIRED`.
4. **Chronological Backtesting & Walk-Forward Engine (`core/backtesting/engine.py`)**:
   - Simulates bar-by-bar trading across **In-Sample (60%)**, **Validation (20%)**, and **Out-of-Sample (20%)** partitions, plus a **4-Window Rolling Walk-Forward** audit and a **2x Transaction Cost Stress Test**.
   - Signals triggered at Day `T` close fill at Day `T + 1` open (`adj_open` + `2.5 bps` half-spread + `3.0 bps` slippage + `$0.005/sh` commission).
5. **Portfolio Risk Manager (`core/risk/manager.py`)**:
   - Sizes every position using `14-day ATR` so entry-to-stop-loss risk is capped at `1.0%` of equity.
   - Exercises hard veto authority over 7 limits: `1.0%` per-trade risk, `5.0%` total open portfolio heat (`MAX_TOTAL_OPEN_RISK`), `15.0%` single-stock cap, `30.0%` sector cap, `10` max positions, `0.80` pairwise return correlation cap, `$20M` minimum daily dollar volume, and a `15.0%` drawdown kill switch.
6. **Paper Brokerage & Multi-Strategy Execution Engine (`core/execution/paper_broker.py`)**:
   - Manages the `$100,000` virtual account, prevents duplicate orders via SHA-256 `idempotency_key`s, interleaves signals round-robin across active strategies by conviction score, reconciles cash/positions/dividends, and writes an immutable `trade_ledger`.

### B. Autonomous Agent Layer (`agents/`)
| Agent Class | File | Role & Permitted Scope |
|---|---|---|
| `MarketResearchAgent` | `agents/market_researcher/agent.py` | Scans the equity universe daily and outputs schema-validated `CandidateResearchReport` rankings. Cannot place orders. |
| `StrategyDiscoveryAgent` | `agents/strategy_architect/agent.py` | Proposes falsifiable `StrategyConfig` versions (`v+1`) in `DRAFT` status based on research and analyst feedback. |
| `StrategyEvaluationAgent` | `agents/strategy_evaluator/agent.py` | Audits candidate strategies against all 9 out-of-sample and walk-forward gates; promotes winners to `PAPER_TRADING` or marks them `REJECTED`. |
| `PerformanceAnalystAgent` | `agents/performance_analyst/agent.py` | Reviews daily post-close attribution and writes `ExperimentProposal` records for the Saturday discovery loop. |
| `RiskManagerAgent` | `agents/risk_manager/agent.py` | Audits portfolio-level drawdown, concentration, and risk alerts after each session. |

### C. Cloud Persistence & Automation (`infrastructure/` & `.github/workflows/`)
- **Database (`infrastructure/database/db.py`)**: 16-table SQLite database (`data/swing_trader.db`) storing market bars, strategy versions, backtest experiments, paper orders, trade ledger fills, daily snapshots, risk alerts, and idempotent job logs.
- **Orchestrator (`infrastructure/scheduler/orchestrator.py`)**: Wraps every daily and weekly step in `run_idempotent_job()` keyed by date so a job never double-executes on the same trading session.
- **GitHub Actions (`.github/workflows/autonomous_trading.yml`)**: Runs the Daily and Weekly workflows on Ubuntu runners, commits the updated `data/swing_trader.db` back to `main`, and triggers Streamlit Community Cloud (`dashboard/streamlit_app.py`) to refresh automatically.
