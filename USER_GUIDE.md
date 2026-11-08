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

## 2. How the Engine Works & Exact Order Execution Rules

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 1. DAILY EXECUTION LOOP (Mon–Fri After Market Close · Forward Paper & Copilot)   │
│                                                                                  │
│  [Alpaca Daily Bars] ──► [5 Golden Base Strategies] ──► [AI Catalyst Filter]     │
│                                                                 │                │
│  [Live Copilot Checklist] & [Forward Paper Ledger]  ◄── [7-Rule Risk Manager]    │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│ 2. WEEKLY SELF-IMPROVEMENT LOOP (Saturdays · Strictly In Backtesting)            │
│                                                                                  │
│  [Post-Trade Attribution] ──► [Propose Candidate v+1] ──► [In-Sample/OOS/WF]     │
│                                                                 │                │
│  [Keep Champion v1 or Promote v+1] ◄── [9-Gate Audit + SPY Dominance Check]      │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Daily Routine (In Exact Order & Time, `ET` & `SGT`)
1. **Step 1 — Before Market Open (`Anytime before 9:30 AM ET / 9:30 PM SGT`): Optional AI Check (`type run in IDE`)**:
   - **How AI changes decisions**: Searches live web news (`search_web`) for your checklist stocks—automatically **vetoing** any `BUY` candidate with bearish breaking news (`sentiment <= -0.35`, e.g., guidance cut/probe) and **boosting** high-catalyst setups (`>= +0.25`).
   - **What if you forget or skip `run`?**: Nothing breaks! GitHub Actions already ran the deterministic daily engine automatically at `5:30 AM SGT` (`21:30 UTC`), so your checklist in `Live Copilot` is **already updated and ready to trade**.
2. **Step 2 — Priority #1 (`9:30–9:35 AM ET / 9:30–9:35 PM SGT`): Execute `SELL` Exits & `Raise Stop` Alerts First**:
   - Always execute **`SELL` exit cards first** at market open to free up cash and lock in P&L.
   - Next, if any holding shows a **`Raise Stop-Loss` alert** (`+1.0R` Chandelier or `+1.25R` Breakeven), update your broker's existing `GTC Stop-Loss` order to that higher price.
3. **Step 3 — Priority #2 (`9:30–9:45 AM ET` or Pre-Submitted Limit): Place `BUY` Orders + Attach Stop/Target Immediately**:
   - **Do you need to click at `9:30:00 AM ET` sharp?** **No!** You can either:
     - *Option A (Set-and-Forget Before Open)*: Anytime before `9:30 AM ET`, submit a **Regular-Hours (`RTH`) Day Limit Order** at the **`Max Chase` price** (`Ref + 0.50 ATR`) with an attached **OCO Bracket (`Stop-Loss` + `Take-Profit`)**. At `9:30 AM ET`, your broker fills you automatically if the open is $\le$ `Max Chase`.
     - *Option B (Live Open Window `9:30–9:45 AM ET`)*: Place a Limit order if the live price trades inside the **`Buy-Zone ($Low – $MaxChase)`** ($\left[\text{Ref} - 0.25\text{ ATR}, \, \text{Ref} + 0.50\text{ ATR}\right]$). Never trade illiquid Pre-Market or After-Hours sessions.
   - **When to set `Stop-Loss` and `Take-Profit`**: **Immediately when placing your `BUY` order** (as an attached **Bracket / OCO order**, or as a **`GTC Stop-Loss` + `GTC Limit Take-Profit`** within 1 minute of your fill). Because they are `GTC`, your `-1%` max risk and profit target are protected automatically every day even if you are offline.
4. **Step 4 — Log Confirmations (`✓ Sold` / `✓ Bought`) & Contingency Rules**:
   - **What if you forget to place orders for a day?**:
     - *Missed a `BUY`*: **Never chase it late.** Leave it—if the setup is still valid and inside the Buy-Zone tomorrow, it will appear on tomorrow's checklist with updated prices.
     - *Missed a `SELL`*: Your broker's `GTC Stop-Loss` and `Take-Profit` bracket continues protecting your downside/upside automatically, and the `SELL` card stays at the top of your checklist tomorrow until you execute and click `✓ Sold`.
   - **What if YOU decide to exit a position early (discretionary full or partial exit)?**:
     - Sell the shares in your broker (and cancel any leftover open `GTC Stop/Target` orders for that stock if not linked via OCO), then go to **Section 2 (`My Active Holdings`)** in `Live Copilot`, enter the shares sold and your actual exit price, and click **`Close`** (or **`Sell N`**). Your cash and Realised P&L update in 1 click!
   - **What if the Profit Target (`Take-Profit`) is not hit?**: Handled by the **4-Way Exit Bracket** (`+1.0R` to `+1.25R` Breakeven/Chandelier Stop Ratchet, Momentum Stall / `RSI >= 68` exit, or `Day N` Time-Stop after `8–15` trading days).

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
4. **Forward-Only Paper Account vs. Historical Backtest Isolation**:
   - *Decision*: Startup and cloud workflows never backfill historical trades into `paper_accounts`. All historical testing stays in `BacktestEngine`.
   - *Why*: Guarantees Paper Account P&L (`Daily`, `Weekly`, `Total`) is a 100% clean forward track record from `$100,000.00`.
5. **Immutable Golden Base (`v1`) Pinning & Strict Incumbent Protection**:
   - *Decision*: `v1` Golden Base models are never overwritten. Weekly candidates (`v2+`) are rejected unless they beat the active champion (`beats_incumbent`), and you can revert to `v1` in one click (`Revert All to Golden Base (v1)`).
   - *Why*: Guarantees monotonic strategy quality and an instant safety net.
6. **Opening Gap-Chase Cap (`max_entry_gap_atr`) + Profit-Activated `+1R` Stop Ratchet + Drawdown De-Gearing**:
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
| **`6. Platform Guide`** | `USER_GUIDE.md` | Visual architecture mental model and interactive workflow guide |
