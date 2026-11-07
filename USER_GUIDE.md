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

### 3. Why Do We Have "AI Agents" If Zero Tokens Are Used? (And How to Enable Live LLM Tokens)

The platform implements 5 specialized agent classes (`MarketResearchAgent`, `StrategyDiscoveryAgent`, `StrategyEvaluationAgent`, `PerformanceAnalystAgent`, and `RiskManagerAgent`) that call a pluggable reasoning interface (`self.llm.generate_structured_json()` in `agents/base.py`):

1. **Why `$0` Tokens Are Used by Default (`LLM_PROVIDER = deterministic_research`)**:
   - Every agent computes exact quantitative metrics first (20d relative strength vs `SPY`, volume ratios, win/loss attribution by market regime, and 9-gate pass/fail scores) and passes a structured `fallback_payload` into `self.llm.generate_structured_json()`.
   - When `LLM_PROVIDER=deterministic_research` (the default), `DeterministicQuantReasoningProvider` returns that quantitative synthesis directly without making an external LLM API call. This guarantees **zero hallucination, 100% reproducibility, and $0 token cost**.
2. **When Real AI Tokens *Are* Used (`LLM_PROVIDER = gemini` or `openai`)**:
   - When you set `LLM_PROVIDER=gemini` and provide a `GEMINI_API_KEY` (from Google AI Studio / Vertex AI) in `.env` or GitHub Actions Secrets, `GeminiLLMProvider` (`agents/base.py`) calls `gemini-2.5-pro` with `responseMimeType: "application/json"` on:
     - **Daily Run**: `MarketResearchAgent` (synthesizing bullish/bearish theses and risk factors per stock) and `PerformanceAnalystAgent` (diagnosing session attribution and proposing Saturday experiments).
     - **Weekly Run**: `StrategyDiscoveryAgent` (proposing parameter refinements for `v+1`) and `StrategyEvaluationAgent` (writing the multi-regime evaluation narrative).
   - **Ways to Expand AI Token Usage for Higher Alpha**:
     - **SEC 8-K / 10-Q & Earnings Transcript Sentiment**: Feed quarterly earnings call transcripts and SEC filings into `MarketResearchAgent` so Gemini scores management guidance tone before `strat_pead_drift` enters.
     - **News Catalyst Filtering**: Have Gemini classify breaking news headlines to distinguish genuine fundamental catalysts from noise before taking a breakout trade.
     - **Adaptive Hypothesis Generation**: Let `StrategyDiscoveryAgent` use Gemini to analyze all losing trades from the past month and propose targeted multi-indicator entry/exit filters for `v+1`.
3. **Using ONLY This IDE's Built-In LLM (Zero External API Keys Needed — Just Type `run`)**:
   - Even without an external `GEMINI_API_KEY` or `OPENAI_API_KEY` in `.env`, you can run full AI research and strategy optimization directly through **this Antigravity IDE conversation** by simply typing **`run`** in the chat (powered by `.agents/skills/run-ai-cycle/SKILL.md`, `python main.py ide-context`, and `python main.py ide-apply`):
     1. **Step 1 (`ide-context`)**: Runs deterministic market ingestion and exports a compact JSON brief of the current `SPY` market regime, top technical candidates, open paper/Copilot holdings, and active strategy parameters.
     2. **Step 2 (Live Web News Catalyst Audit via `search_web`)**: The IDE AI agent searches real-time financial news, earnings call reactions, and macro catalysts for the top candidates and writes enriched `bullish_thesis`, `bearish_thesis`, and `catalyst_assessment` analyses directly into `data/swing_trader.db`.
     3. **Step 3 (Multi-Candidate AI Strategy Tournament via `ide-apply`)**: The IDE AI agent designs 2–3 regime-tuned strategy parameter improvements and tests them through the **9-Gate Out-of-Sample & Walk-Forward Backtest Tournament** with **Incumbent Champion Protection** (a new version `v+1` is only promoted to `PAPER_TRADING` if it passes all 9 validation gates *and* beats or matches the active champion's Sharpe/Return/Calmar metrics).
     4. **Step 4 (Cloud Sync & Copilot Briefing)**: Automatically pushes `data/swing_trader.db` to GitHub so your 24/7 Streamlit Cloud dashboard updates immediately, and prints your daily **Real-Account Copilot Checklist** in chat.
   - **Want it 100% hands-free on a schedule inside the IDE?** You can also type `/schedule` (or ask the agent to set up a scheduled automation) so Antigravity automatically runs this `run` workflow in the background every weekday after market close!

---

### 4. Using the "Live Trading Copilot (Real Account)" Tab

Once a strategy reaches `READY FOR LIVE REVIEW` (or whenever you choose to mirror signals in your personal brokerage account), open the **`Live Copilot (Real Account)`** tab:

1. **100% Air-Gapped Security (Zero Broker Access)**:
   - The platform never connects to your real brokerage account or asks for trading credentials.
2. **Set Your Real Cash Balance**:
   - Expand **"Configure My Real Cash Balance & Active Copilot Strategies"** and enter your actual uninvested cash (for example, `$15,000` or `$25,000`).
   - All BUY recommendations automatically scale their share count so that hitting a stop-loss risks **at most 1.0% of your real account equity** (e.g., `$150` max risk on `$15,000`).
3. **Never Assumes Your Positions**:
   - Each day's **Step-by-Step Action Checklist** shows pending **SELL Orders** (on positions you actually hold that hit their Stop-Loss, Take-Profit, or Max Hold days) and **BUY Candidates**.
   - Nothing is added to or removed from your real portfolio until you click **`Confirm Bought`** or **`Confirm Sold`** (where you can edit the exact share count and fill price you got at your broker), **`Skip Trade`**, or **`Hold Today`** (to skip a sell signal for the day).
   - You can also inspect **Signals Filtered Out by Your Risk Caps Today** and manually **Add, Edit, or Close** any position at any time if you traded independently in your broker.

---

### 5. What You Need to Know & When to Trade Real Money

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
   - Includes a **Systematic $+1.25\text{R}$ Breakeven+Friction Ratchet & Chandelier ATR Trailing Stop** (`compute_effective_stop_price()`): once a trade reaches $+1.25\text{R}$ unrealized gain, the stop-loss automatically ratchets to $\text{Entry} + 0.15 \times \text{ATR}$ (covering commissions and slippage), and once it reaches $+1.5\text{R}$, a Chandelier trailing stop ($\text{Highest High Since Entry} - k \times \text{ATR}_{14}$) locks in swing gains.
   - Enforces immutable versioning (`DRAFT -> BACKTESTING -> VALIDATION -> PAPER_TRADING -> RETIRED / REJECTED`). Promoting `v+1` automatically transitions `v` to `RETIRED`.
4. **Chronological Backtesting, Walk-Forward Efficiency & Deflated Sharpe (`core/backtesting/engine.py`, `evaluation/metrics/performance.py`)**:
   - Simulates bar-by-bar trading across **In-Sample (50–60%)**, **Validation (20–25%)**, and **Out-of-Sample (20–25%)** partitions, plus a **4-Window Rolling Walk-Forward** audit, **Walk-Forward Efficiency (WFE) Ratio**, and a **2x Transaction Cost Stress Test**.
   - Computes **Probabilistic Sharpe Ratio (PSR %)** and **Deflated Sharpe Ratio (DSR %)** (Bailey & López de Prado) adjusted for return skewness, fat tails (kurtosis), sample length, and multiple-testing bias across weekly strategy tournaments.
   - Signals triggered at Day `T` close fill at Day `T + 1` open (`adj_open` + `2.5 bps` half-spread + `3.0 bps` slippage + `$0.005/sh` commission).
5. **Portfolio Risk Manager (`core/risk/manager.py`)**:
   - Sizes every position using `14-day ATR` so entry-to-stop-loss risk is capped at `1.0%` of equity, with **Dynamic Drawdown De-Gearing** (automatically scaling risk per trade down to `0.65x` if portfolio drawdown exceeds `7.5%`, halfway to the `15%` kill switch) and **Volatility-Regime Targeting**.
   - Exercises hard veto authority over 7 limits: `1.0%` per-trade risk, `5.0%` total open portfolio heat (`MAX_TOTAL_OPEN_RISK`), `15.0%` single-stock cap, `30.0%` sector cap, `10` max positions, `0.80` pairwise return correlation cap, `$20M` minimum daily dollar volume, and a `15.0%` drawdown kill switch.
6. **Paper Brokerage & Air-Gapped Live Trading Copilot (`core/execution/paper_broker.py`)**:
   - `PaperTradingEngine`: Manages the `$100,000` virtual account, prevents duplicate orders via SHA-256 `idempotency_key`s, interleaves signals round-robin across active strategies by conviction score, reconciles cash/positions/dividends, and writes an immutable `trade_ledger`.
   - `LiveTradingCopilotEngine`: Air-gapped shadow portfolio engine (`shadow_accounts`, `shadow_positions`, `shadow_trade_history`, `shadow_dismissed_signals`) that provides daily step-by-step `SELL`, `HOLD` (including live stop-ratchet alerts), and `BUY` instructions sized to your real cash and holdings without ever connecting to your brokerage account.

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

