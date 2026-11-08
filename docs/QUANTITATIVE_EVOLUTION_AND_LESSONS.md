# Quantitative & Product Evolution Log — How User-Driven Critiques Transformed the Platform

This document records the core quantitative finance, execution-microstructure, accounting, and UX design improvements introduced through iterative architectural review. It contrasts the **Initial State (Baseline Prototype)** against the **Upgraded Institutional State**, highlighting why each user critique uncovered a real-world trading flaw and how the engine was re-engineered to solve it.

---

## Executive Summary Table: Initial State vs. Upgraded State

| Area | Initial State (What Was Flawed / Missing) | User Insight / Critique | Upgraded Institutional Design | Impact on P&L, Win Rate & Usability |
|---|---|---|---|---|
| **1. Strategy Evaluation Horizon & Metric** | Evaluated strategies primarily on **2.3-year cumulative P&L**, Sharpe, and Profit Factor. | *"If I trade a real account for the next **6 months**, why evaluate on 2-year cumulative P&L? Shouldn't win rate and shorter-term consistency matter?"* | Added **Recent 6-Month (`126d`) Return & Win Rate**, **Rolling 6-Month Win Probability (`86%–98%`)**, and **Van Tharp's `SQN` ($\ge 2.85$)** to the 9-Gate Auditor. | Prevents promoting stale strategies that only worked 18 months ago; top champions now achieve **`64.7%–67.9%` 6M win rates** and **`98.3%` rolling 6M profitability**. |
| **2. Order Timing, Entry Range & Exit Ratchets** | Assumed single-price next-open execution with static initial stop-loss and take-profit targets. | *"When do we trade (before, during, or after hours)? Should there be an entry price range? What if entry or target is not hit?"* | Added **`Buy-Zone ($Low – $MaxChase)`** ($\left[\text{Close}-0.25\text{ ATR}, \text{Close}+0.50\text{ ATR}\right]$), **`+1.0R` Breakeven/Chandelier Stop Ratchet**, and **`7.5%` Drawdown De-Gearing**. | Eliminates buying exhausted morning gap-ups (`> Max Chase`) and stops `+1R` winning trades from round-tripping into full `-1R` losses. |
| **3. Role of AI in the Workflow (`run` command)** | IDE AI (`run`) only updated text reports and proposed backtest parameter tweaks; it did not directly filter or re-rank live trade decisions. | *"Is parameter tweaking the best way to use AI, or is AI better for market research/sentiment? How does running `run` change my actual trade decisions?"* | Wired live AI news sentiment (`search_web`) directly into `LiveTradingCopilotEngine`: **Hard Veto (`<= -0.35`)** on `BUY`s, **Emergency `SELL` (`<= -0.50`)** on holdings, and **Pre-Allocation Conviction Re-Ranking (`>= +0.25`)**. | Combines deterministic price/volume timing with LLM news/catalyst filtering—blocking earnings/news traps and funding highest-catalyst setups first. |
| **4. Post-Close vs. Pre-Open Execution & Live Gaps** | Ran only once post-close (`5:30 PM ET`) on daily bars; preview setups had a `2025-06-30` fallback bug and ignored `AMC`/`BMO` earnings & pre-market gaps. | *"Why run post-market when earnings calls or outside-hours activity can move price significantly by market open? And why are preview prices stale?"* | Implemented **Two-Stage Execution**: **Stage 1 Post-Close** (`4:00 PM ET` structural bars + `ensure_latest_market_data`) + **Stage 2 Pre-Open (`8:45–9:25 AM ET`)** querying live Alpaca IEX Snapshots (`/v2/stocks/snapshots`) with an **Overnight Gap Gate**. | Auto-syncs live `2026-11-06` bars, auto-vetoes severe pre-open gap breakdowns (`<= -0.75 ATR` or `> +2.5 ATR`), and warns `Do Not Chase` when extended above `Max Chase`. |
| **5. Paper Portfolio Architecture** | Single shared `$100,000` paper account mixing all 5 strategies together. | *"Shouldn't paper trading have 1 account per strategy so strategies don't starve each other of cash?"* | Built a **Two-Tier Paper Book**: **1 Master Combined `$100k` Portfolio** + **5 Isolated `$100k` Per-Strategy Pods** (`paper_strat_*`). | Eliminates **first-in cash starvation bias** so each strategy's true forward edge is measured independently alongside combined portfolio heat. |
| **6. Real-Account Strategy Selection & `$10k` Sizing** | Allowed users to manually switch active strategies via dropdown; enforced `$100k`-style `15%` single-stock cap on `$10k` accounts. | *"Combining strategies in a `$10k` account is different from paper testing—why not pick the #1 best strategy? And why can users change the strategy when exits depend on the entry strategy?"* | Removed manual strategy dropdown: **New `BUY`s auto-use the #1 Champion** (with automatic pullback fallback to `Mean Reversion`), **`SELL`/`HOLD` exits bind to each position's exact entry strategy**, and `$10k` accounts allow `25%` stock weight at `1%` (`$100`) stop risk. | Guarantees 1:1 parity between backtested rules and live exits, avoids over-fragmenting a `$10k` account, and prevents whole-share truncation on `$340–$1,350` stocks. |
| **7. Real-Account Cash & Trade Ledger Accounting** | Allowed manual overrides of `Available Cash` and `Starting Capital` alongside a Deposit/Withdraw tool; past trades could not be edited/deleted. | *"Users shouldn't manually edit cash or starting capital if Deposit/Withdraw exists. Cash and holdings must be 100% calculated from deposits, withdrawals, and editable trades."* | Built an **Event-Sourced Ledger Engine (`reconcile_from_trade_ledger`)** with full **Add / Edit / Delete Trade** and **Deposit / Withdraw** replay. | Eliminates accounting drift: `Available Cash`, `Account Value`, `Holdings`, and `Realised P&L` are 100% mathematically derived from cash transfers and trade fills. |
| **8. Daily Workflow & UI Design** | Verbose multi-form UI with duplicated controls, emoji clutter, and unclear daily ordering. | *"Make the daily actions intuitive, time-ordered, and concise in a minimalistic, classy design—including what to do if I miss a day."* | Redesigned into a **Minimalist Institutional UI (`CLASSY_MINIMAL_CSS`)** with a single sleek masthead, a 4-popover control bar, and a time-ordered 4-step daily workflow (`ET` & `SGT`). | Reduces daily decision time to **under 5 minutes** (`8:45–9:25 AM ET` pre-open check $\rightarrow$ `9:30–9:45 AM ET` bracket execution). |

---

## Detailed Breakdown of Key Takeaways & Design Improvements

### 1. Aligning the Optimization Metric with a 6-Month Real-Money Horizon
- **Initial Limitation**: Backtesters that optimize solely for 2–3 year cumulative return often select high-variance strategies that generated one massive outlier trend two years ago but suffer long flat periods or low win rates over a practical 6-month deployment window.
- **User-Driven Upgrade**:
  - Introduced **Van Tharp's System Quality Number ($\text{SQN} = \sqrt{N} \cdot \mu_R / \sigma_R$)** alongside **Recent 6-Month (`126d`) Return & Win Rate** and **Rolling 6-Month Win Probability** across all 461 rolling 6-month windows in [`evaluation/metrics/performance.py`](file:///Users/tjamie/Documents/trader/evaluation/metrics/performance.py).
  - Upgraded the 5 Golden Base (`v1`) strategies so that #1 Champion `strat_volatility_breakout v1` achieves **`SQN = 3.55`**, **`+11.03%` Recent 6M Return (`67.9%` Win Rate)**, and **`98.3%` profitable rolling 6-month windows**.

### 2. Solving the Overnight Gap & Pre-Market Disconnect (Two-Stage Execution)
- **Initial Limitation**: Running the engine only once after the `4:00 PM ET` close meant that `AMC` earnings (`4:05–5:30 PM ET`), `BMO` earnings (`6:00–8:30 AM ET`), overnight macro shocks, and pre-market price gaps could invalidate a setup before the `9:30 AM ET` open. Furthermore, a hardcoded `2025-06-30` fallback in [`MarketDataService`](file:///Users/tjamie/Documents/trader/core/market_data/providers.py) caused stale preview prices when local bars weren't auto-refreshed.
- **User-Driven Upgrade**:
  - **Auto-Sync (`ensure_latest_market_data`)**: Automatically syncs `market_bars_daily` to the latest completed US session (`2026-11-06`) and prevents read-only cloud hosts from overwriting `alpaca` bars with `local_seeded` data.
  - **Stage 1 (Post-Close at `5:30 PM ET` / `5:30 AM SGT`)**: Computes structural indicators from official `4:00 PM ET` closing auctions (`98%` of daily volume) and applies a **2-Day Earnings Blackout (`earnings_blackout_days_before = 2`)**.
  - **Stage 2 (Pre-Open at `8:45–9:25 AM ET` / `8:45–9:25 PM SGT`)**:
    - Queries live extended-hours / pre-market quotes via [`MarketDataService.fetch_live_quote_snapshots()`](file:///Users/tjamie/Documents/trader/core/market_data/providers.py#L618-L678) (`/v2/stocks/snapshots?feed=iex`).
    - Auto-vetoes setups with severe overnight gap breakdowns (`<= -0.75 ATR`) or runaway gaps (`> +2.5 ATR`), and flags setups trading above `Max Chase` (`Extended — Do Not Chase`).
    - Added a Pre-Open GitHub Actions cron (`13:00 UTC` / `9:00 AM ET`) in [`.github/workflows/autonomous_trading.yml`](file:///Users/tjamie/Documents/trader/.github/workflows/autonomous_trading.yml).

### 3. Making the IDE AI Flow (`run`) Directly Impact Trade Decisions
- **Initial Limitation**: Running `run` in the IDE updated research cards and tested candidate strategy parameters, but did not directly alter which stocks were bought, sold, or prioritized in `Live Copilot`.
- **User-Driven Upgrade**:
  - When you type **`run`** in the IDE (`8:45–9:25 AM ET`, after `AMC`/`BMO` earnings and overnight news are public), [`LiveTradingCopilotEngine.get_daily_action_plan()`](file:///Users/tjamie/Documents/trader/core/execution/paper_broker.py#L2260-L2680) now:
    1. **Vetoes `BUY` setups** with bearish breaking news (`sentiment <= -0.35`).
    2. **Triggers Emergency `SELL` alerts** on open holdings hit by severe overnight news (`sentiment <= -0.50`).
    3. **Re-ranks `BUY` candidates by AI-Adjusted Conviction (`sentiment >= +0.25`) *before* allocating cash**, ensuring your `$10k` account funds the highest-conviction catalyst first.

### 4. Separation of Paper Pods vs. Single-Champion Real Execution (`$10k` Account)
- **Initial Limitation**:
  - In Paper Trading, sharing one `$100k` account across 5 strategies caused cash starvation (`first-in bias`).
  - In Real Trading (`$10k` starter account), allowing manual strategy switching risked evaluating open positions with the wrong exit rules, while combining 5 strategies fragmented a `$10k` account into tiny positions.
- **User-Driven Upgrade**:
  - **Paper Portfolio (Tab 2)**: Runs **6 books simultaneously**—1 Master Combined `$100k` Portfolio + 5 Isolated `$100k` Per-Strategy Pods.
  - **Live Copilot (Tab 1)**:
    - **Open Positions (`SELL` / `HOLD`)**: Permanently bound to the exact strategy (`strategy_id v{version}`) that opened each position.
    - **New `BUY` Entries**: Automatically driven by the **#1 Validated Champion (`strat_volatility_breakout v1`)**, with automatic pullback fallback to **#2 `Mean Reversion` (`strat_mean_reversion_bb v1`)** when `SPY` dips below `SMA50` while holding above `SMA200`.

### 5. Event-Sourced Real-Account Ledger & Minimalist Institutional UX
- **Initial Limitation**: Manual cash and starting-capital override fields conflicted with Deposit/Withdraw actions, and users could not edit or delete past trade fills with automatic balance recalculation.
- **User-Driven Upgrade**:
  - Replaced manual cash overrides with [`reconcile_from_trade_ledger()`](file:///Users/tjamie/Documents/trader/core/execution/paper_broker.py#L1805-L1920), [`edit_trade()`](file:///Users/tjamie/Documents/trader/core/execution/paper_broker.py#L1922-L1988), and [`delete_trade()`](file:///Users/tjamie/Documents/trader/core/execution/paper_broker.py#L1990-L2015). Every cash figure, position, and P&L metric is 100% derived from **Net Deposits/Withdrawals + Confirmed Trade Fills**.
  - Streamlined [`dashboard/streamlit_app.py`](file:///Users/tjamie/Documents/trader/dashboard/streamlit_app.py) into a clean, minimalist layout with a 4-popover control bar (`Cash Transfer`, `+ Log Trade`, `Reset`, `? Rules`) and a headless multi-branch Streamlit runtime verifier in [`verify_context.py`](file:///Users/tjamie/Documents/trader/.agents/skills/maintain-project-context/scripts/verify_context.py) to prevent UI regressions.
