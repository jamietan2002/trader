# Swing Trading AI — User Guide, Design Decisions & Roadmap

Welcome to **Swing Trading AI**, an autonomous quantitative research, statistical validation, paper-trading, and real-account copilot platform for US equities (`NYSE` / `NASDAQ`), benchmarked against the S&P 500 (`SPY`).

---

## 1. What This Project Does (In 60 Seconds)

This platform runs a systematic **swing-trading engine** (holding liquid US large-cap stocks for **3 to 15 trading days**) with two distinct goals:
1. **Autonomous Forward Validation (`$100,000` Paper Account)**: Automatically tests and runs 5 uncorrelated swing-trading strategies every weekday after the US market close, tracking forward Daily, Weekly, and Total P&L net of realistic brokerage commissions and slippage.
2. **Air-Gapped Real-Account Execution (`Live Copilot` Tab)**: Generates a daily step-by-step `SELL`, `HOLD / Raise Stop`, and `BUY` checklist sized to your personal brokerage cash and confirmed holdings—**without ever connecting to or having access to your real trading account**.

### Core Operating Modes
- **100% Hands-Off Cloud Mode**: GitHub Actions runs the Daily loop (`Mon–Fri 21:30 UTC`) and Weekly self-improvement loop (`Sat 10:00 SGT`), committing updated state to `data/swing_trader.db` so the 24/7 Streamlit Cloud dashboard stays current with zero user intervention.
- **One-Word IDE AI Mode (`run`)**: Type **`run`** in this IDE chat at any time to have the IDE's built-in LLM search live web news catalysts (`search_web`), enrich stock research, run a multi-candidate strategy tournament, and output your daily Copilot briefing—with `$0` external API key cost.

---

## 2. How the System Works

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 1. DAILY EXECUTION LOOP (Mon–Fri After Market Close · Forward Paper & Copilot)   │
│                                                                                  │
│  [Alpaca Daily Bars] ──► [5 Golden Base Strategies] ──► [7-Rule Risk Manager]    │
│                                                                 │                │
│  [Live Copilot Checklist] & [Forward Paper Ledger]  ◄── [Next-Open Fill Model]   │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│ 2. WEEKLY SELF-IMPROVEMENT LOOP (Saturdays · Strictly In Backtesting)            │
│                                                                                  │
│  [Post-Trade Attribution] ──► [Propose Candidate v+1] ──► [In-Sample/OOS/WF]     │
│                                                                 │                │
│  [Keep Champion v1 or Promote v+1] ◄── [9-Gate Audit + SPY Dominance Check]      │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### The Five Golden Base (`v1 ★ Base`) Strategies
Every base strategy (`v1`) has been validated across multi-year history (`2023–2025`), Out-of-Sample (`OOS`) partitions, 4-window Walk-Forward folds (`100%` consistency), and $2\times$ transaction-cost stress tests to outperform `SPY` (`+61.90%` full period, `+9.67%` OOS):

| Strategy ID (`v1 ★ Base`) | Family | What It Trades | Full Return (`vs SPY +61.90%`) | OOS Return (`vs SPY +9.67%`) | Sharpe / PF / MaxDD |
|---|---|---|---|---|---|
| `strat_volatility_breakout` | `BREAKOUT` | 20-day high breakouts with volume expansion & relative strength vs `SPY` | **`+75.83%`** (`+13.93%` excess) | **`+22.96%`** (`+13.29%` excess) | `2.51` / `2.68` / `-4.83%` |
| `strat_sector_rotation_leaders` | `SECTOR_ROTATION` | Top relative-strength stocks inside the top-ranked GICS sectors | **`+77.45%`** (`+15.55%` excess) | **`+18.88%`** (`+9.21%` excess) | `2.47` / `2.19` / `-9.58%` |
| `strat_momentum_trend` | `MOMENTUM_TREND` | Aligned uptrends (`Close > SMA20 > SMA50`) beating `SPY` over 20 days | **`+73.37%`** (`+11.47%` excess) | **`+16.32%`** (`+6.65%` excess) | `2.29` / `2.11` / `-8.53%` |
| `strat_pead_drift` | `PEAD` | Post-earnings institutional drift following quarterly EPS & revenue beats | **`+73.80%`** (`+11.90%` excess) | **`+17.38%`** (`+7.71%` excess) | `2.15` / `2.08` / `-7.81%` |
| `strat_mean_reversion_bb` | `MEAN_REVERSION` | Value-zone pullbacks to `SMA20` / Lower Bollinger Band inside structural uptrends | **`+70.68%`** (`+8.78%` excess) | **`+11.52%`** (`+1.85%` excess) | `2.02` / `1.92` / `-9.59%` |

---

## 3. Navigating the Dashboard (6 Top-of-Mind Tabs)

1. **`1. Live Copilot (Real Account)`** *(Default Landing Tab)*:
   - **Trading-Day-Aware Checklist**: Automatically checks today's `NYSE`/`NASDAQ` calendar date. If today is a weekend or market holiday, it clearly states that US markets are closed, shows the next trading session date, and suppresses stale trade suggestions (with an optional preview toggle).
   - **Set Cash, Deposit, or Withdraw**: Update your uninvested broker cash, reset your 0% starting capital baseline, or log cash deposits/withdrawals (`Deposit / Withdraw`) without distorting your P&L %.
   - **Dynamic Bracket Sizing, Buy-Zone Limit & 1-Click Undo**: Every `BUY` card specifies an exact **Market-Open Buy-Zone Limit (`$Low – $MaxChase Limit`)**, **Order Timing (`9:30–9:45 AM ET Open Limit`)**, **AI Catalyst Sentiment badge**, and **If Target Not Hit Plan (`+1.0R Breakeven Ratchet` + `Day N Time-Stop`)**. Supports partial exits, custom tickers, custom entry dates, **`Restore Skipped`**, and **`Undo Last Trade`**.
2. **`2. Paper Account & Ledger`** *(Unified Forward `$100,000` Track Record)*:
   - Displays **Total Equity**, **Daily P&L**, **Weekly P&L (5 sessions)**, and **Total P&L (Realised + Unrealised)** starting from a clean `$100,000.00` baseline, alongside open paper positions, strategy attribution, and the **Day/Side/Strategy-Filtered Execution Ledger**.
3. **`3. Strategies, Rules & Backtests`** *(Complete Strategy Encyclopaedia)*:
   - Consolidates everything about each strategy into one place: **how it is conceived & its economic edge**, its **exact machine-readable `entry_rules`, `exit_rules`, and `risk_params`**, its **9-gate `SPY` benchmark audit** (**Full & OOS Excess Return**, **Recent 6-Month (`126d`) Return & Win Rate**, **Rolling 6M Profitable Windows %**, **System Quality Number (`SQN`)**, **Payoff Ratio**, **Jensen's Alpha $\alpha$**, **Beta $\beta$**, **Upside/Downside Capture**, **Ulcer Index**, **Martin Ratio**, **Omega Ratio**, **DSR**), its **historical backtest trade log**, and **1-Click `Revert All to Golden Base (v1)`**.
4. **`4. AI Research & IDE Bridge`** *(Watchlist + Direct Prompt-to-Engine Feed)*:
   - Features an **IDE AI Reminder Checklist**, a **Copyable Ready-to-Paste AI Prompt**, and a **Direct JSON Feed Textarea** (`Apply AI Output to Engine`) so you can either type **`run`** in the Antigravity IDE or paste LLM JSON directly in the browser to enrich stock catalysts and run the 9-gate strategy tournament.
5. **`5. Risk, Walk-Forward & Logs`**:
   - Displays real-time sector concentration against the `30%` cap, 4-window Walk-Forward validation folds, risk vetoes, and job execution logs.
6. **`6. Platform Guide`**:
   - Interactive mental-model diagram and walkthrough of the Daily and Weekly loops.

---

## 4. Key Architectural & Quantitative Design Decisions

1. **Strict Firewall Between Deterministic Finance and AI Reasoning**:
   - *Decision*: All price normalization, causal indicators, signal triggers, ATR position sizing, portfolio risk vetoes, and accounting live in deterministic Python (`core/`, `evaluation/`). AI agents (`agents/`) may only rank research candidates, propose structured JSON parameter hypotheses (`StrategyConfig`), and audit promotion gates.
   - *Why*: Eliminates LLM arithmetic errors, hallucinated orders, and non-reproducible backtests.
2. **Forward-Only Paper Account vs. Historical Backtest Isolation**:
   - *Decision*: Startup and cloud workflows never backfill historical trades into `paper_accounts` or `trade_ledger`. All historical experimentation runs strictly in `BacktestEngine` (`strategy_experiments`).
   - *Why*: Ensures Paper Account P&L (`Daily`, `Weekly`, `Total`) is a 100% clean, uncontaminated forward track record.
3. **Multi-Dimensional `SPY` Benchmark Dominance & 9-Gate Promotion**:
   - *Decision*: To be promoted to `PAPER_TRADING`, a strategy must pass 9 objective gates including positive Out-of-Sample net return, Walk-Forward consistency $\ge 60\%$, $2\times$ cost survival, Ulcer Index $\le 6.0$, and **S&P 500 (`SPY`) dominance** (beating `SPY` in Full & OOS return or achieving superior Return on Invested Capital, positive Jensen's Alpha $\alpha$, and Sharpe $\ge$ `SPY` Sharpe).
   - *Why*: Prevents low-exposure strategies from passing solely on Sharpe ratio while trailing passive `SPY` buy-and-hold returns.
4. **Immutable Golden Base (`v1`) Pinning & Strict Incumbent Protection**:
   - *Decision*: `v1` Golden Base models are never overwritten. Future weekly candidates (`v2+`) are automatically rejected unless they beat or match the active champion's Return, Sharpe, and Calmar (`beats_incumbent`), and operators can revert to `v1` in one click (`revert_to_golden_baseline`).
   - *Why*: Guarantees monotonic strategy quality and an instant safety net if a new parameter regime degrades.
5. **Profit-Activated Stop Ratchet ($+1.0\text{R}$ Chandelier & $+1.25\text{R}$ Breakeven+Friction) + Drawdown De-Gearing**:
   - *Decision*: Trailing stops only tighten after a trade reaches $\ge +1.0\text{R}$ unrealized gain (`trail_activation_r`), locking in breakeven plus transaction friction at $+1.25\text{R}$. At the portfolio level, risk-per-trade automatically scales down to `0.65x` if portfolio drawdown exceeds `7.5%` (halfway to the `15%` kill switch).
   - *Why*: Avoids premature stop-outs during normal day-1 noise while systematically protecting open profits and portfolio equity.
6. **Zero-Cost Pluggable AI + IDE-Native Bridge (`ide-context` / `ide-apply`)**:
   - *Decision*: Default scheduled runs use `LLM_PROVIDER=deterministic_research` (`$0` token cost), automatically upgrading to Gemini/OpenAI if API keys are present, while supporting full live-web AI catalyst research and tournament optimization via the IDE's built-in LLM (`run`).
   - *Why*: Delivers institutional AI alpha without mandatory paid API subscriptions.

---

## 5. Future Work & High-Impact Roadmap

1. **Dynamic Liquid Universe Expansion (Top 100 S&P 500 / Nasdaq-100 + Sector ETFs)**:
   - Expand beyond the 16 core large-cap equities to a dynamic 75–100 stock universe filtered point-in-time by `20-day Average Dollar Volume >= $50M`, providing more uncorrelated breakout and earnings-drift setups each week.
2. **Partial Profit Scaling (`50%` at $+1.5\text{R}$, Trail Remaining `50%`)**:
   - Upgrade `PaperTradingEngine` and `LiveTradingCopilotEngine` to support selling half of a position at the initial profit target while trailing the second half with the Chandelier ATR stop.
3. **Real-Account Equity Curve & Benchmark Comparison in `Live Copilot`**:
   - Add Daily, Weekly, and Total P&L charting vs. `SPY` inside the `Live Copilot (Real Account)` tab to mirror the Paper Account's analytics on confirmed personal trades.
4. **Intraday VWAP / Opening-Range Execution Timing**:
   - Enhance the next-day open execution model with optional 30-minute Opening Range Breakout (`ORB`) confirmation to reduce morning gap-fade risk on earnings and breakout entries.

---

## 6. Technical Appendix (Module Map)

| Layer | File | Responsibility |
|---|---|---|
| **CLI & API** | `main.py`, `api/server.py` | CLI commands (`bootstrap`, `daily`, `weekly`, `ide-context`, `ide-apply`, `revert-baseline`, `serve`) & REST endpoints |
| **Dashboards** | `dashboard/streamlit_app.py`, `dashboard/ui_template.py` | 8-tab Streamlit Cloud UI & local HTML/JS dashboard |
| **Market Data & Indicators** | `core/market_data/providers.py`, `core/indicators/technical.py` | Alpaca / Seeded OHLCV ingestion, point-in-time `BMO`/`AMC` earnings, causal indicators (`SMA`, `EMA`, `RSI`, `ATR`, `BB`, `RS vs SPY`) |
| **Strategies & Signals** | `core/strategies/registry.py` | 5 Golden Base strategy families, `StrategySignalEngine`, version registry, and `revert_to_golden_baseline()` |
| **Backtesting & Metrics** | `core/backtesting/engine.py`, `evaluation/metrics/performance.py` | Chronological backtester, Walk-Forward folds, 2x cost stress tests, SPY Alpha/Beta/Capture, Ulcer/Martin, PSR/DSR, Monte Carlo |
| **Risk & Execution** | `core/risk/manager.py`, `core/execution/paper_broker.py` | ATR sizing, drawdown de-gearing, 7 risk vetoes, `$100k` forward `PaperTradingEngine`, and air-gapped `LiveTradingCopilotEngine` |
| **AI Agents & Orchestration** | `agents/*`, `infrastructure/scheduler/orchestrator.py` | 5 role-scoped agents (`MarketResearch`, `StrategyDiscovery`, `StrategyEvaluation`, `PerformanceAnalyst`, `RiskManager`) & idempotent scheduler |
