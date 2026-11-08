# Swing Trading AI — User Guide, Quantitative Design Decisions, Monitoring & Roadmap

Welcome to **Swing Trading AI**, an autonomous quantitative research, statistical validation, paper-trading, and real-account copilot platform for US equities (`NYSE` / `NASDAQ`), benchmarked against the S&P 500 (`SPY`).

---

## 1. What This Project Does (In 60 Seconds)

This platform runs a systematic **swing-trading engine** (holding liquid US large-cap stocks for **3 to 15 trading days**) with two distinct goals:
1. **Autonomous Forward Validation (`$100,000` Paper Account)**: Automatically tests and runs 5 uncorrelated swing-trading strategies every weekday after the US market close, tracking forward Daily, Weekly, and Total P&L net of realistic brokerage commissions and slippage.
2. **Air-Gapped Real-Account Execution (`Live Copilot` Tab)**: Generates a daily step-by-step `SELL`, `HOLD / Raise Stop`, and `BUY` checklist sized to your personal brokerage cash and confirmed holdings—**without ever connecting to or having access to your real trading account**.

### Core Operating Modes
- **100% Hands-Off Cloud Mode**: GitHub Actions runs the Daily loop (`Mon–Fri 21:30 UTC`) and Weekly self-improvement loop (`Sat 10:00 SGT`), committing updated state to `data/swing_trader.db` so the 24/7 Streamlit Cloud dashboard stays current with zero user intervention.
- **One-Word IDE AI Mode (`run`)**: Type **`run`** in this IDE chat (or paste AI JSON in Tab 4) to have the LLM search live web news catalysts (`search_web`), veto negative-news traps, boost high-catalyst setups, and run a 9-gate strategy tournament—with `$0` external API key cost.

---

## 2. How the Engine Works & Two-Stage Daily Execution Rules

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: POST-CLOSE STRUCTURAL SCAN (5:30 PM ET / 5:30 AM SGT · Auto via GitHub) │
│                                                                                  │
│  [4:00 PM ET Closing Bars] ──► [#1 Champion + Entry-Bound Exits] ──► [2d Earn    │
│                                                                      Blackout]   │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: PRE-OPEN GAP & AI CATALYST GATE (8:45–9:25 AM ET · Type "run" in IDE)   │
│                                                                                  │
│  [AMC/BMO Earnings + Web News] + [Alpaca Pre-Market Snapshots]                   │
│       ├──► Veto Bearish BUY Setups (Sentiment <= -0.35 or Gap <= -0.75 ATR)      │
│       ├──► Emergency SELL Alert on Holdings (Severe News <= -0.50)               │
│       └──► Re-Rank Top Catalysts (>= +0.25) & Flag Extended Gaps (> Max Chase)   │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: MARKET OPEN EXECUTION (9:30–9:45 AM ET · Regular Trading Hours Only)    │
│                                                                                  │
│  1. Execute SELL Exits & Raise +1R GTC Stops (9:30–9:35 AM ET)                   │
│  2. Submit Day Limit BUY Orders inside Buy-Zone (<= Max Chase) + GTC Bracket     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Why Do We Run a Two-Stage Engine (Post-Close + Pre-Open)?
1. **Why Stage 1 Runs Post-Market (`5:30 PM ET` / `5:30 AM SGT`)**:
   - Over **98% of US equity volume** (and **15–25%** in the `4:00 PM ET` closing auction alone) trades during Regular Trading Hours (`9:30 AM – 4:00 PM ET`). After-hours and pre-market trade `< 2%` of daily volume with wide bid-ask spreads.
   - Structural daily indicators (`SMA-20/50/200`, `RSI-14`, `ATR-14`, `20d High`, `Volume Ratio`) **must** be computed from the official `4:00 PM ET` closing bar, while enforcing a **2-Day Earnings Blackout (`earnings_blackout_days_before = 2`)** so non-PEAD strategies never propose buying right before a scheduled `AMC` or `BMO` earnings call.
2. **Why Stage 2 Runs Pre-Open (`8:45–9:25 AM ET` / `8:45–9:25 PM SGT`) & How `run` Changes Trade Decisions**:
   - Between `4:00 PM ET` (Day $T$) and `9:30 AM ET` (Day $T+1$), **`AMC` earnings (`4:05–5:30 PM ET`)**, **`BMO` earnings (`6:00–8:30 AM ET`)**, overnight macro/analyst news, and pre-market price gaps occur.
   - Typing **`run`** in the IDE `15–45 minutes` before the `9:30 AM ET` open **directly updates your trade decisions in 4 ways**:
     1. **Hard Veto on Bearish `BUY` Candidates (`sentiment <= -0.35`)**: Automatically removes any `BUY` candidate hit by an overnight guidance cut, downgrade, SEC/FDA probe, or macro shock.
     2. **Emergency `SELL` Protection on Open Holdings (`sentiment <= -0.50`)**: Triggers an immediate `SELL` action if a stock you already hold suffers a severe overnight catalyst shock.
     3. **Conviction Re-Ranking (`sentiment >= +0.25`)**: Boosts conviction and re-orders `buy_actions` BEFORE cash allocation so your `$10k` capital funds the highest-catalyst setup first.
     4. **Live Extended-Hours / Pre-Market Gap Gate (`fetch_live_quote_snapshots`)**: Queries Alpaca's live IEX snapshot (`indicative_price` vs `Close`):
        - **Severe Gap Breakdown (`<= -0.75 ATR`) or Runaway Gap (`> +2.5 ATR`)**: Automatically vetoes the `BUY` setup (`PRE_OPEN_GAP_VETO`).
        - **Extended Above `Max Chase` (`> Close + 0.50 ATR`)**: Flags **`Extended — Do Not Chase`**; keep your Limit Order at `<= Max Chase` so you only buy if price pulls back into the Buy-Zone after `9:30 AM ET`.

### Daily User Actions (Concise 4-Step Checklist, `ET` & `SGT`)
1. **`8:45–9:25 AM ET` (`8:45–9:25 PM SGT`) — Pre-Open AI & Gap Check (`type run in IDE`)**:
   - Type **`run`** in the IDE after `BMO` earnings (`8:30 AM ET`) and before the `9:30 AM ET` open so overnight news vetoes, catalyst re-rankings, and pre-market gap checks update your `Live Copilot` checklist.
   - *What if you skip `run`?* GitHub Actions automatically runs both Post-Close (`21:30 UTC`) and Pre-Open (`13:00 UTC` / `9:00 AM ET`), and your **Buy-Zone Limit Order (`<= Max Chase`)** automatically protects you from chasing overnight gap-ups.
2. **`9:30–9:35 AM ET` (`9:30–9:35 PM SGT`) — Execute `SELL` Exits & Raise `+1R` Stops First**:
   - Execute **`SELL` cards first** to free cash and lock in P&L, then raise your broker's `GTC Stop-Loss` on any holding showing a **`Raise Stop`** alert (`+1R` Breakeven / Chandelier).
3. **`9:30–9:45 AM ET` (or Pre-Set `RTH` Limit) — Place `BUY` Limit Orders in `Buy-Zone` + `GTC Bracket`**:
   - Submit a **Regular-Hours (`RTH`) Day Limit Order** inside the **`Buy-Zone ($Low – $MaxChase)`** and immediately attach your **`GTC Stop-Loss` + `GTC Take-Profit`** bracket. Never trade illiquid pre-market or after-hours sessions.
4. **Post-Fill — Click `Sold` / `Bought` in `Live Copilot`**:
   - Confirm your actual broker fill price and shares in Tab 1 (or edit/add/remove any trade in Section 3 `Account Ledger`). Cash, holdings, and P&L reconcile automatically from your ledger.

---

## 3. Why You Can Trust the Strategies (Empirical Evidence & Anti-Bias Safeguards)

To ensure strategies are not curve-fit to a single bull run **and** are optimized to make money over a **6-month live deployment window**, every Golden Base (`v1 ★ Base`) strategy passes a dual-horizon validation suite:
- **Zero Look-Ahead & Survivorship Bias**: Signals on Day $T$ execute at Day $T+1$ open (`adj_open` + spread + slippage) with an opening gap-chase cap (`max_entry_gap_atr = 1.25`). `AMC` earnings on Day $T$ are only visible on Day $T+1$. Delisted stocks (`FRC_DELIST`, `-97%` collapse) remain in historical backtests.
- **2.3-Year Multi-Regime Survival + 6-Month (`126d`) Regime Alpha + Van Tharp `SQN`**:

| Strategy ID (`v1 ★ Base`) | 2.3-Yr Full (`vs SPY +61.90%`) | OOS (`vs SPY +9.67%`) | Recent 6M (`vs SPY +3.39%`) | Recent 6M Win Rate | Rolling 6M Win % (`Median 6M`) | `SQN` / Payoff |
|---|---|---|---|---|---|---|
| `strat_volatility_breakout` | **`+77.54%`** (`+15.64%` α) | **`+21.96%`** | **`+11.03%`** (`+7.65%` α) | **`67.86%`** (`28t`) | **`98.3%`** (`+12.32%`) | **`3.55`** / `2.19x` |
| `strat_mean_reversion_bb` | **`+74.07%`** (`+12.17%` α) | **`+10.17%`** | **`+10.11%`** (`+6.72%` α) | **`64.71%`** (`34t`) | **`86.1%`** (`+8.03%`) | **`2.85`** / `1.46x` |
| `strat_momentum_trend` | **`+71.44%`** (`+9.54%` α) | **`+16.32%`** | **`+7.49%`** (`+4.11%` α) | **`61.54%`** (`26t`) | **`91.1%`** (`+8.73%`) | **`3.29`** / `1.96x` |
| `strat_pead_drift` | **`+73.80%`** (`+11.90%` α) | **`+17.75%`** | **`+4.73%`** (`+1.35%` α) | **`51.52%`** (`33t`) | **`96.1%`** (`+9.79%`) | **`2.99`** / `1.77x` |
| `strat_sector_rotation_leaders` | **`+67.32%`** (`+5.42%` α) | **`+18.49%`** | **`+6.87%`** (`+3.49%` α) | **`57.69%`** (`26t`) | **`91.7%`** (`+7.82%`) | **`2.91`** / `1.75x` |

---

## 4. Key Architectural & Quantitative Design Decisions

1. **Strict Firewall Between Deterministic Finance and AI Reasoning**:
   - *Decision*: All price normalization, causal indicators, signal triggers, ATR position sizing, portfolio risk vetoes, and accounting live in deterministic Python (`core/`, `evaluation/`). AI agents (`agents/`) may only rank research candidates, score news catalysts, propose structured `StrategyConfig` drafts, and audit promotion gates.
   - *Why*: Eliminates LLM arithmetic errors, hallucinated orders, and non-reproducible backtests.
2. **AI Used for Catalyst Veto & Conviction Filtering (Not Raw Price Guessing)**:
   - *Decision*: Live web AI research (`run` in IDE or JSON paste in Tab 4) writes structured sentiment scores into `market_catalysts`. `LiveTradingCopilotEngine` automatically **vetoes** any BUY signal with bearish AI catalyst sentiment ($\le -0.35$, e.g., guidance cut, legal probe) and **boosts conviction** for verified positive catalysts ($\ge +0.25$).
   - *Why*: Academic research shows LLMs excel at unstructured news/catalyst tone analysis while deterministic indicators excel at price/volume timing.
3. **Dual-Horizon Evaluation (`2.3-Yr Multi-Regime` + `6-Month Recent/Rolling` + `SQN`)**:
   - *Decision*: Strategies are evaluated on 9 gates combining 2.3-year survival, Out-of-Sample `SPY` dominance, **Recent 6-Month (`126d`) Return & Win Rate**, **Rolling 6-Month Win Probability (`86%–98%`)**, and **Van Tharp's System Quality Number (`SQN >= 2.85`)**.
   - *Why*: Prevents promoting strategies that made all their money 2 years ago while ensuring trade-by-trade consistency over a 6-month live horizon.
4. **Two-Tier Forward Paper Book (`1 Master Combined $100k` + `5 Dedicated Per-Strategy $100k Pods`)**:
   - *Decision*: `PaperTradingEngine` runs **both** (1) a **`$100,000` Master Combined Portfolio (`paper_main_100k`)** enforcing shared cross-strategy heat (`5%`), sector (`30%`), and single-stock (`15%`) caps, **and** (2) **5 Dedicated Per-Strategy `$100,000` Accounts (`paper_strat_*`)** where each strategy trades its own isolated `$100,000` pod.
   - *Why*: A single master account alone suffers from **cash starvation / first-in bias** (Strategy A uses cash on Monday and blocks Strategy B on Tuesday, masking Strategy B's true edge). Isolated pods alone miss **cross-strategy risk collisions** (3 strategies buying `Technology` simultaneously). Running both tiers gives institutional multi-strategy pod attribution plus real-account portfolio risk simulation.
5. **Staged Real-Account Strategy Deployment (`Core 2` $\rightarrow$ `Core 3` $\rightarrow$ `All 5`)**:
   - *Decision*: In `Live Copilot` (`Strategies & Reset`), 1-click deployment presets allow staging real-capital deployment:
     - **Phase 1 (`★ Core 2: Volatility Breakout + Mean Reversion`, recommended for accounts $< \$30\text{k}$ or Months 1–2)**: Combines two negatively correlated regimes—`strat_volatility_breakout v1` (`SQN 3.55`, `+11.03%` 6M, `67.9%` WR in bull breakouts) + `strat_mean_reversion_bb v1` (`SQN 2.85`, `+10.11%` 6M, `64.7%` WR in pullbacks/dips).
     - **Phase 2 (`Core 3: + Earnings PEAD`, $\$30\text{k}$–$\$50\text{k}$)**: Adds `strat_pead_drift v1` (`SQN 2.99`) during earnings season.
     - **Phase 3 (`All 5 Base Strategies`, $\$50\text{k}+$)**: Full 5-sleeve institutional book.
   - *Why*: Grounded in Grinold & Kahn's Fundamental Law of Active Management ($\text{SR}_{\text{port}} = \text{SR}_{\text{avg}} \sqrt{K / (1 + (K-1)\bar{\rho})}$)—pairing 2–3 low-correlation regime specialists smooths the equity curve without over-fragmenting smaller accounts into tiny ticket sizes.
6. **Immutable Golden Base (`v1`) Pinning & Strict Incumbent Protection**:
   - *Decision*: `v1` Golden Base models are never overwritten. Weekly candidates (`v2+`) are rejected unless they beat the active champion (`beats_incumbent`), and you can revert to `v1` in one click (`Revert All to Golden Base (v1)`).
   - *Why*: Guarantees monotonic strategy quality and an instant safety net.
7. **Opening Gap-Chase Cap (`max_entry_gap_atr`) + Profit-Activated `+1R` Stop Ratchet + Drawdown De-Gearing**:
   - *Decision*: Skips opening gaps $> 1.25 \times \text{ATR}_{14}$ (`+0.50 ATR` in Copilot Buy-Zone), ratchets stops to Breakeven/Chandelier after $+1.0\text{R}$ gain, and scales risk-per-trade down to `0.65x` if portfolio drawdown reaches `7.5%` (with a hard kill-switch at `15.0%`).
   - *Why*: Protects win rate against exhausted morning gaps and locks in open gains before reversals.

---

## 5. What to Monitor During Live & Paper Trading

Check these 5 health indicators weekly (in **Tab 1**, **Tab 2**, and **Tab 3**):
1. **Forward Win Rate & Payoff Ratio vs. Backtest Baseline (Tab 2 & Tab 3)**:
   - *Healthy*: Forward Win Rate stays within `50%–68%` and Profit Factor $\ge 1.30$ after `15–20` closed trades.
   - *Action if Degraded*: If a promoted `v2+` strategy drops below a `45%` win rate or `< 1.0` Profit Factor over 10+ trades, click **`Revert All to Golden Base (v1)`** in Tab 3.
2. **Execution Slippage vs. Buy-Zone Ceiling (Tab 1 — Live Copilot)**:
   - *Monitor*: Compare your actual broker fill prices against `reference_entry_price`. If your fills consistently exceed `Max Chase` (`Ref + 0.50 ATR`), switch from Market orders to strict **Limit orders inside the Buy Zone** at `9:30–9:45 AM ET`.
3. **Portfolio Heat & Sector Concentration (Tab 5 — Risk & Walk-Forward)**:
   - *Monitor*: Total open stop-loss risk should stay $\le 5.0\%$ of equity (`1.0%` per trade across at most 5–8 positions) and single-sector exposure $\le 30.0\%$.
4. **IDE AI Run Freshness (Sidebar Checklist & Tab 4)**:
   - *Monitor*: Check the `Last IDE AI Run` timestamp in the sidebar before placing new `BUY` orders to ensure recent earnings or breaking news catalysts have been screened.
5. **Current Drawdown vs. `7.5%` De-Gearing & `15.0%` Kill Switch (Tab 2)**:
   - *Monitor*: If portfolio drawdown exceeds `7.5%`, the engine automatically scales position sizes to `0.65x`; at `15.0%`, new entries pause automatically until reviewed.

---

## 6. How the Engine Can Be Improved in the Future (Roadmap)

1. **Dynamic Point-in-Time Liquid Universe Expansion (`Top 100 S&P 500 / Nasdaq-100`)**:
   - Expand beyond the 16 core large-cap leaders to a dynamic 75–100 stock universe filtered point-in-time by `20-day Avg Dollar Volume >= $50M`, increasing the number of high-conviction breakout and `PEAD` setups each week.
2. **Partial Profit Scaling (`Sell 50% at +1.5R, Trail 50%`)**:
   - Upgrade `PaperTradingEngine` and `LiveTradingCopilotEngine` to lock in half of the position at `+1.5R` while trailing the remaining half with the Chandelier ATR stop—boosting both realized win rate and multi-week trend capture.
3. **Intraday 30-Minute Opening Range Breakout (`ORB`) Confirmation**:
   - Add an optional intraday check requiring price to hold above the `9:30–10:00 AM ET` opening range VWAP before triggering a `BUY` fill, further reducing morning gap-fade losses.
4. **Real-Account Equity Curve & `SPY` Benchmark Charting in `Live Copilot`**:
   - Add dedicated Daily, Weekly, and Total P&L equity charting vs. `SPY` for your confirmed personal trades in Tab 1.

---

## 7. Navigating the 6 Dashboard Tabs & Module Map

| Tab / Layer | Key File(s) | What It Provides |
|---|---|---|
| **`1. Live Copilot (Real Account)`** | `dashboard/streamlit_app.py`, `core/execution/paper_broker.py` | Trading-day-aware `SELL` / `BUY` / `HOLD` checklist, `Buy-Zone Limit ($Low–$MaxChase)`, `+1R` ratchet, cash/deposit controls, `Undo Last Trade` |
| **`2. Paper Account & Ledger`** | `core/execution/paper_broker.py` | Forward-only `$100,000` portfolio (`Daily`, `Weekly`, `Total` P&L), open positions, and Day/Side/Strategy-filtered trade ledger |
| **`3. Strategies, Rules & Backtests`** | `core/strategies/registry.py`, `evaluation/metrics/performance.py` | Strategy origin, exact `entry_rules`/`exit_rules`, 9-gate `SPY` & `6M`/`SQN` audit, historical trades, and `Revert All to Golden Base (v1)` |
| **`4. AI Research & IDE Bridge`** | `infrastructure/scheduler/orchestrator.py`, `.agents/skills/run-ai-cycle/SKILL.md` | Watchlist rankings, IDE AI checklist, copyable prompt, and direct JSON-to-Engine feed (`/api/ide/apply`) |
| **`5. Risk, Walk-Forward & Logs`** | `core/risk/manager.py`, `core/backtesting/engine.py` | Sector exposure vs. `30%` cap, 4-window Walk-Forward folds, risk vetoes, and job execution logs |
| **`6. Platform Guide`** | `USER_GUIDE.md`, `docs/QUANTITATIVE_EVOLUTION_AND_LESSONS.md` | Visual architecture mental model, interactive workflow guide, and Initial-vs-Upgraded design evolution log |
