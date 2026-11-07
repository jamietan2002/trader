"""Streamlit Community Cloud & Local Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

Designed to be intuitive, transparent, and beginner-friendly:
- Includes a dedicated "🧸 Start Here: Explain Like I'm 5" interactive tab with clickable deep-dives.
- Adds simple, concise "What You Need to Know" callouts at the top of every tab.
- Makes all Profit & Loss (P&L) displays 100% transparent: clearly separating Simulated Paper Account P&L
  from Historical Backtest P&L, and explicitly stating the exact Date Span, Strategy Used, and exact math
  formula (`Starting Cash + Realised P&L + Unrealised P&L - Fees = Current Equity`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is on sys.path when Streamlit runs `dashboard/streamlit_app.py`
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.server import PlatformApplication
from core.market_data.models import USTradingCalendar


def _get_paper_date_span(snapshots: List[Dict[str, Any]], ledger: List[Dict[str, Any]]) -> str:
    dates: List[str] = []
    for s in snapshots:
        if s.get("snapshot_date"):
            dates.append(str(s["snapshot_date"]))
    for l in ledger:
        if l.get("fill_date"):
            dates.append(str(l["fill_date"]))
    if not dates:
        return "No trading days recorded yet"
    dates.sort()
    return f"{dates[0]} to {dates[-1]} ({len(set(dates))} trading days)"


def _summarize_pnl_by_strategy(
    ledger: List[Dict[str, Any]],
    positions: List[Dict[str, Any]],
    strategies: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    strat_names = {
        f"{s['strategy_id']} v{s['version']}": s["name"] for s in strategies
    }
    by_strat: Dict[str, Dict[str, Any]] = {}

    for row in ledger:
        key = f"{row['strategy_id']} v{row['strategy_version']}"
        item = by_strat.setdefault(
            key,
            {
                "Strategy": key,
                "Plain English Name": strat_names.get(key, row["strategy_id"]),
                "First Trade Date": row["fill_date"],
                "Latest Trade Date": row["fill_date"],
                "Total Fills": 0,
                "Closed Sells": 0,
                "Realised P&L ($)": 0.0,
                "Unrealised P&L ($)": 0.0,
                "Fees & Slippage Paid ($)": 0.0,
            },
        )
        item["Total Fills"] += 1
        item["First Trade Date"] = min(item["First Trade Date"], row["fill_date"])
        item["Latest Trade Date"] = max(item["Latest Trade Date"], row["fill_date"])
        fees = float(row.get("commission_usd", 0.0)) + float(row.get("slippage_usd", 0.0))
        item["Fees & Slippage Paid ($)"] = round(item["Fees & Slippage Paid ($)"] + fees, 2)
        if row["side"] == "SELL":
            item["Closed Sells"] += 1
            item["Realised P&L ($)"] = round(
                item["Realised P&L ($)"] + float(row.get("realised_pnl", 0.0)), 2
            )

    for pos in positions:
        key = f"{pos['strategy_id']} v{pos['strategy_version']}"
        item = by_strat.setdefault(
            key,
            {
                "Strategy": key,
                "Plain English Name": strat_names.get(key, pos["strategy_id"]),
                "First Trade Date": pos["opened_date"],
                "Latest Trade Date": pos["opened_date"],
                "Total Fills": 1,
                "Closed Sells": 0,
                "Realised P&L ($)": 0.0,
                "Unrealised P&L ($)": 0.0,
                "Fees & Slippage Paid ($)": 0.0,
            },
        )
        item["Unrealised P&L ($)"] = round(
            item["Unrealised P&L ($)"] + float(pos.get("unrealised_pnl", 0.0)), 2
        )

    out: List[Dict[str, Any]] = []
    for item in by_strat.values():
        net_total = round(item["Realised P&L ($)"] + item["Unrealised P&L ($)"], 2)
        item["Total Net P&L ($)"] = net_total
        item["How It Arrived Here"] = (
            f"Realised (${item['Realised P&L ($)']:+,.2f}) + "
            f"Open Unrealised (${item['Unrealised P&L ($)']:+,.2f}) "
            f"[after ${item['Fees & Slippage Paid ($)']:,.2f} in fees/slippage]"
        )
        out.append(item)
    return out


def main() -> None:
    try:
        import streamlit as st
    except ImportError:
        print(
            "Streamlit is not installed in the current environment. "
            "Run `python3 main.py serve` to launch the built-in interactive web dashboard on http://127.0.0.1:8080."
        )
        return

    st.set_page_config(
        page_title="Swing Trading AI — Beginner-Friendly Dashboard",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    app = PlatformApplication()
    if not app.orchestrator.registry.list_strategies():
        with st.spinner("Setting up initial historical US stocks, 3 baseline strategies, and paper trades..."):
            app.orchestrator.bootstrap_baseline_system()
            for dt in USTradingCalendar.get_trading_days("2025-05-01", "2025-05-20"):
                app.orchestrator.run_daily_workflow(dt)
            app.orchestrator.run_weekly_workflow("2025-05-20", force=True)

    state = app.get_dashboard_state()
    acc = state["account"]
    strats = state["strategies"]
    snapshots = state["snapshots"]
    ledger = state["trade_ledger"]
    positions = state["positions"]

    active_paper_strats = [s for s in strats if s["status"] == "PAPER_TRADING"]
    rejected_strats = [s for s in strats if s["status"] == "REJECTED"]
    active_strat_names = (
        ", ".join(f"{s['name']} ({s['strategy_id']} v{s['version']})" for s in active_paper_strats)
        if active_paper_strats
        else "None currently active"
    )
    paper_date_span = _get_paper_date_span(snapshots, ledger)
    total_fees_paid = round(
        sum(float(l.get("commission_usd", 0.0)) + float(l.get("slippage_usd", 0.0)) for l in ledger),
        2,
    )
    net_dollar_pnl = round(float(acc["total_equity"]) - float(acc["starting_capital"]), 2)

    # Sidebar Controls
    with st.sidebar:
        st.header("🎮 Quick Controls")
        st.success("🔒 PAPER MODE ONLY ($100k Practice Money)")
        st.caption("No real money can be spent by this app.")
        st.markdown("---")
        st.markdown("**Want to trigger a run manually?**")
        if st.button("▶️ Run Today's Trading Check", use_container_width=True):
            app.orchestrator.run_daily_workflow("2025-06-27", force=True)
            st.rerun()
        if st.button("🧠 Run Weekly AI Self-Improvement", use_container_width=True):
            app.orchestrator.run_weekly_workflow("2025-06-27", force=True)
            st.rerun()
        st.markdown("---")
        st.caption(f"Data Feed: `{app.settings.market_data_provider.upper()}`")
        st.caption(f"Reporting Timezone: `{app.settings.operator_timezone}`")

    st.title("📈 Swing Trading AI — Simple & Transparent Dashboard")
    st.caption(
        "An autonomous system that researches US stocks, tests rules on past history, and practices with $100,000 of virtual paper money."
    )

    # Weekly 2-Minute Check-In Box
    with st.expander("📋 Your 2-Minute Weekly Check-In (What You Need to Know This Week)", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### 1. Is the Account Safe?")
            if not acc["kill_switch_engaged"]:
                st.success("🟢 **YES — Everything is healthy.**")
            else:
                st.error(f"🔴 **PAUSED — Kill Switch Active:** {acc['kill_switch_reason']}")
            st.write(f"- **Safety Brake (Drawdown)**: `-{acc['current_drawdown_pct']:.2f}%` (Auto-stops at `-15.0%`)")
            st.write(f"- **Stocks Held Right Now**: `{acc['open_positions_count']}` (Max allowed: `10`)")
        with c2:
            st.markdown("#### 2. How Did Paper P&L Arrive Here?")
            st.write(f"- **Date Span**: `{paper_date_span}`")
            st.write(f"- **Started With**: `${acc['starting_capital']:,.2f}`")
            st.write(
                f"- **Math**: `${acc['starting_capital']:,.0f}` + `${acc['realised_pnl']:+,.2f}` (Closed Trades) "
                f"+ `${acc['unrealised_pnl']:+,.2f}` (Open Trades) = **`${acc['total_equity']:,.2f}`**"
            )
            st.write(f"- **Strategies Used**: `{len(active_paper_strats)}` approved strategies")
        with c3:
            st.markdown("#### 3. Do I Need to Do Anything?")
            st.info(
                "**No action needed!** GitHub Actions runs this every weekday after the US market closes "
                "and tests new AI ideas every Saturday morning. Just check back once a week."
            )

    tabs = st.tabs(
        [
            "🧸 Start Here (Explain Like I'm 5)",
            "1. Overview & P&L Breakdown",
            "2. Stock Research",
            "3. Strategy Rulebooks",
            "4. Historical Backtests",
            "5. Paper Trading Ledger",
            "6. Risk & Sector Analytics",
            "7. System Logs",
        ]
    )

    # =========================================================================
    # TAB 0: EXPLAIN LIKE I'M 5 (INTERACTIVE GUIDE)
    # =========================================================================
    with tabs[0]:
        st.header("🧸 Explain Like I'm 5: What Does This App Actually Do?")
        st.markdown(
            """
            Imagine you have a **toy piggy bank with $100,000 of pretend money** (we call this **Paper Money**).
            You want to find out if a robot helper can grow that piggy bank by buying pieces of big US companies
            (like Apple, Microsoft, or NVIDIA), holding them for **3 to 15 days** (called **Swing Trading**), and selling them.

            Instead of letting an AI guess randomly, we split the job into **two strict teams**:
            1. 🧠 **The AI Detective Team (Ideas Only)**: Reads stock news, checks which stocks are moving fast, and writes down *ideas* for trading rules. **They are NEVER allowed to touch the money.**
            2. 🧮 **The Strict Calculator & Safety Guard (Math Only)**: Tests the AI's ideas against years of past history, checks strict safety rules, and only allows safe trades in the pretend piggy bank.
            """
        )

        st.markdown("### 👇 Click Any Button Below to Explore How Each Part Works:")
        if "eli5_topic" not in st.session_state:
            st.session_state["eli5_topic"] = "loop"

        b1, b2, b3, b4, b5 = st.columns(5)
        if b1.button("🔄 1. The Daily & Weekly Loop", use_container_width=True):
            st.session_state["eli5_topic"] = "loop"
        if b2.button("🤖 2. Meet the 5 AI Helpers", use_container_width=True):
            st.session_state["eli5_topic"] = "agents"
        if b3.button("📏 3. The 3 Trading Rulebooks", use_container_width=True):
            st.session_state["eli5_topic"] = "strategies"
        if b4.button("🛡️ 4. The Safety Seatbelts", use_container_width=True):
            st.session_state["eli5_topic"] = "safety"
        if b5.button("💰 5. How P&L Math Works", use_container_width=True):
            st.session_state["eli5_topic"] = "pnl"

        topic = st.session_state["eli5_topic"]
        if topic == "loop":
            st.info(
                """
                #### 🔄 Deep Dive: How the App Runs By Itself Every Day & Week
                - **Every Weekday (Mon–Fri after US Market Close)**:
                  1. **Look at Prices**: It downloads the latest stock prices from Alpaca Markets.
                  2. **Check Exit Rules**: If we own a pretend stock and it hit our profit goal, hit our safety stop-loss, or we held it for the maximum 10–12 days, it sells it.
                  3. **Check Entry Rules**: If a stock passes all checklist rules AND the Safety Guard approves, it buys shares using pretend cash.
                - **Every Saturday Morning (Self-Improvement Day)**:
                  1. **Learn from Mistakes**: The Performance Analyst looks at which trades lost money during the week.
                  2. **Try a New Rule**: The Strategy Architect proposes a new version (like `v2`) with an extra safety filter.
                  3. **Pass the 9-Part Exam**: The new version is tested on past history. Only if it passes all **9 strict tests** is it allowed to trade next week!
                """
            )
        elif topic == "agents":
            st.info(
                """
                #### 🤖 Deep Dive: Meet Your 5 Specialized Helpers
                1. 🔎 **Market Researcher**: Scans 15+ big US stocks every day and ranks them by strength and trading volume.
                2. 📐 **Strategy Architect**: Turns observations into exact math rules (`Buy when Price > 50-day Average`).
                3. ⚖️ **Strategy Evaluator (The Strict Teacher)**: Grades every strategy on a 9-point exam. Even if a strategy made money in the past, if it took too much risk, the teacher **REJECTS** it!
                4. 🛡️ **Portfolio Risk Manager (The Bouncer)**: Has veto power to block any trade that is too big or risky.
                5. 📊 **Performance Analyst (The Coach)**: Reviews closed trades after market close and suggests improvements for Saturday's test.
                """
            )
        elif topic == "strategies":
            st.info(
                """
                #### 📏 Deep Dive: The 3 Core Trading Rulebooks (Strategies)
                - **Rulebook 1: Momentum / Trend Following (`strat_momentum_trend`)**
                  *Idea*: "Winners keep winning for a few days." Buys stocks beating the S&P 500 (`SPY`) that are above their 20-day and 50-day average prices with strong trading volume. Holds 4–12 days.
                - **Rulebook 2: Post-Earnings Drift (`strat_pead_drift`)**
                  *Idea*: "Big earnings surprises take a week or two for everyone to price in." Buys companies that just beat quarterly profit & sales expectations with a burst of volume. Holds 4–10 days.
                - **Rulebook 3: Volatility Breakout (`strat_volatility_breakout`)**
                  *Idea*: "A coiled spring jumps high." Waits for a stock to trade in a tight, quiet range for 10 days and buys the moment it breaks above its 20-day high on high volume. Holds 3–11 days.
                """
            )
        elif topic == "safety":
            st.info(
                """
                #### 🛡️ Deep Dive: The 6 Safety Seatbelts Protecting the Portfolio
                1. **1% Max Risk Per Trade**: If a trade goes wrong and hits its stop-loss, it is sized so you lose at most ~1% (`$1,000`) of the `$100,000` portfolio.
                2. **Max 15% in Any One Stock**: Never puts more than `$15,000` into a single company.
                3. **Max 30% in Any One Sector**: Prevents putting all money into just Tech or just Banks.
                4. **Max 10 Stocks at Once**: Keeps the portfolio focused and easy to track.
                5. **Emergency Kill Switch at -15% Drawdown**: If the total account ever drops 15% from its highest peak, an automatic brake stops all new buying until you check it.
                6. **Paper Mode Lock**: Hardcoded to `TRADING_MODE=paper`. It cannot touch real bank money.
                """
            )
        elif topic == "pnl":
            st.info(
                """
                #### 💰 Deep Dive: Why Some Apps Have Confusing P&L — And How Ours Stays Honest
                Many trading apps confuse people by mixing **Backtest P&L** (what *would* have happened over the last 2.5 years) with **Paper Account P&L** (what happened in day-by-day simulated trading).
                - In **Tab 1 & Tab 5**, we show **Paper Account P&L**:
                  - **Starting Cash**: `$100,000.00`
                  - **Realised P&L**: Profit or loss locked in from trades we already bought AND sold.
                  - **Unrealised P&L**: Paper gain or loss on stocks we are still holding today.
                  - **Transaction Costs Included**: Every buy and sell subtracts realistic broker commissions (`$1+`), bid-ask spread, and slippage so the numbers aren't artificially inflated.
                - In **Tab 4**, we separately show **Historical Backtest P&L** (`2023-03-01 to 2025-06-30`) so you can compare how a rulebook performed across 2+ years of history vs. the `SPY` S&P 500 index.
                """
            )

    # =========================================================================
    # TAB 1: OVERVIEW & TRANSPARENT P&L BREAKDOWN
    # =========================================================================
    with tabs[1]:
        st.info(
            "💡 **What is this tab?** This is your **Paper Trading Account Scoreboard**. Every dollar shown here comes from "
            "day-by-day simulated paper trading (NOT a multi-year historical backtest), after deducting realistic broker fees and slippage."
        )

        st.subheader("💰 Transparent Profit & Loss (P&L) Breakdown")
        st.markdown(
            f"""
            - **What Strategy is Used**: {active_strat_names}
            - **Exact Date Span**: `{paper_date_span}`
            - **How We Arrived at Your Current Equity (`${acc['total_equity']:,.2f}`)**:
              > **Starting Capital** (`${acc['starting_capital']:,.2f}`)
              > **+** **Closed Trade Realised P&L** (`${acc['realised_pnl']:+,.2f}` across `{len([l for l in ledger if l['side']=='SELL'])}` closed trades, after `${total_fees_paid:,.2f}` in broker commissions & slippage)
              > **+** **Open Position Unrealised P&L** (`${acc['unrealised_pnl']:+,.2f}` across `{acc['open_positions_count']}` currently held stocks)
              > **= Current Total Equity** (**`${acc['total_equity']:,.2f}`** | Net P&L: **`${net_dollar_pnl:+,.2f}`** / **`{acc['total_return_pct']:+.2f}%`**)
            """
        )

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Current Total Equity", f"${acc['total_equity']:,.2f}", f"{ net_dollar_pnl:+,.2f} ({acc['total_return_pct']:+.2f}%)")
        k2.metric("Starting Virtual Cash", f"${acc['starting_capital']:,.2f}", "Base Capital")
        k3.metric("Locked-In (Realised) P&L", f"${acc['realised_pnl']:+,.2f}", f"After ${total_fees_paid:,.2f} fees")
        k4.metric("Open (Unrealised) P&L", f"${acc['unrealised_pnl']:+,.2f}", f"{acc['open_positions_count']} open stocks")
        k5.metric("Available Cash to Trade", f"${acc['cash_balance']:,.2f}", f"Max DD: -{acc['current_drawdown_pct']:.2f}%")

        st.subheader("📊 P&L Breakdown by Strategy (Paper Account)")
        strat_pnl_rows = _summarize_pnl_by_strategy(ledger, positions, strats)
        if strat_pnl_rows:
            st.dataframe(strat_pnl_rows, use_container_width=True)
        else:
            st.info(
                "Your paper account is currently holding $100,000.00 in cash with 0 trades executed in this window. "
                "Click **▶️ Run Today's Trading Check** in the left sidebar or view **Tab 4 (Historical Backtests)** to see 200+ historical trades."
            )

        st.subheader("📦 Stocks Currently Held in Your Paper Account")
        if positions:
            clean_pos = [
                {
                    "Ticker": p["ticker"],
                    "Strategy Used": f"{p['strategy_id']} v{p['strategy_version']}",
                    "Date Bought": p["opened_date"],
                    "Days Held": p["holding_days"],
                    "Shares": p["quantity"],
                    "Buy Price (incl. slippage)": f"${p['avg_entry_price']:.2f}",
                    "Current Price": f"${p['current_price']:.2f}",
                    "Safety Stop-Loss": f"${p['stop_loss_price']:.2f}" if p.get("stop_loss_price") else "-",
                    "Profit Target": f"${p['take_profit_price']:.2f}" if p.get("take_profit_price") else "-",
                    "Current Market Value": f"${p['market_value']:,.2f}",
                    "Unrealised P&L ($)": f"${p['unrealised_pnl']:+,.2f} ({p['unrealised_return_pct']:+.2f}%)",
                }
                for p in positions
            ]
            st.dataframe(clean_pos, use_container_width=True)
        else:
            st.write("No open stock positions right now (100% in safe cash).")

    # =========================================================================
    # TAB 2: STOCK RESEARCH
    # =========================================================================
    with tabs[2]:
        st.info(
            "💡 **What is this tab?** Every morning before the market opens, the **Market Research Agent** scans major US stocks "
            "and ranks them from strongest to weakest based on **Relative Strength vs S&P 500 (SPY)**, **Volume bursts**, and **Earnings surprises**."
        )
        st.subheader("🔎 Ranked US Stock Opportunities")
        reports_summary = [
            {
                "Rank": idx + 1,
                "Ticker": r["ticker"],
                "Company": r["company_name"],
                "Price": f"${r['current_price']:.2f}",
                "Sector": r["market_and_sector_context"]["sector"],
                "Beating SPY by (20d)": f"{r['relative_strength_vs_spy_20d']:+.2f}%",
                "Volume vs Normal": f"{r['volume_analysis']['volume_ratio_20']:.2f}x",
                "Best Matching Rulebook": r["suggested_strategy_family"],
                "Overall Rank Score (0-100)": r["composite_rank_score"],
                "Data Completeness Score*": f"{r['research_confidence_score'] * 100:.0f}%",
                "Plain-English Bullish Case": r["bullish_thesis"],
                "What Could Go Wrong (Bearish)": r["bearish_thesis"],
            }
            for idx, r in enumerate(state["research_reports"])
        ]
        st.dataframe(reports_summary, use_container_width=True)
        st.caption(
            "*Note: Data Completeness Score (`research_confidence_score`) measures how complete the data and indicator alignment are — it is NOT a guaranteed probability of profit."
        )

        st.subheader("💡 AI Coach's Proposals for Next Saturday's Self-Improvement Test")
        st.dataframe(state["proposals"], use_container_width=True)

    # =========================================================================
    # TAB 3: STRATEGY RULEBOOKS
    # =========================================================================
    with tabs[3]:
        st.info(
            "💡 **What is this tab?** These are the **Trading Rulebooks (Strategies)**. A strategy is only allowed to trade "
            "paper money if its status says **`PAPER_TRADING`**. If an AI-proposed strategy fails our 9 safety & statistical tests, it is marked **`REJECTED`**."
        )
        st.subheader("📚 All Strategy Versions & How They Performed in Historical Testing")
        strat_rows = []
        for s in strats:
            m = s["backtest_summary"] or {}
            start_eq = 100_000.0
            final_eq = m.get("final_equity", start_eq)
            net_bt_profit = final_eq - start_eq
            strat_rows.append(
                {
                    "Strategy ID": s["strategy_id"],
                    "Version": f"v{s['version']}",
                    "Plain-English Name": s["name"],
                    "Status": "✅ ACTIVE (PAPER_TRADING)" if s["status"] == "PAPER_TRADING" else f"❌ {s['status']}",
                    "Hold Period": f"{s['holding_period_min_days']}–{s['holding_period_max_days']} days",
                    "Backtest Date Span": "2023-03-01 to 2025-06-30",
                    "Backtest Net P&L ($ on $100k)": f"${net_bt_profit:+,.2f} ({m.get('total_return_pct', 0.0):+.2f}%)",
                    "S&P 500 (SPY) Return Same Period": f"+{m.get('benchmark_return_pct', 0.0):.2f}%",
                    "Total Trades Tested": m.get("trade_count", 0),
                    "Win Rate": f"{m.get('win_rate_pct', 0.0):.1f}%",
                    "Worst Drop (Max Drawdown)": f"-{m.get('max_drawdown_pct', 0.0):.2f}%",
                    "Why It Was Promoted or Rejected": s["promotion_decision_reason"],
                }
            )
        st.dataframe(strat_rows, use_container_width=True)

    # =========================================================================
    # TAB 4: HISTORICAL BACKTESTS
    # =========================================================================
    with tabs[4]:
        st.info(
            "💡 **What is this tab?** Before any strategy is allowed into the Paper Account, we test it on **2.3 years of past market data "
            "(`2023-03-01` to `2025-06-30`)**. Every backtest below states the exact **Strategy Used**, **Date Span**, and **How the P&L Was Calculated**."
        )
        st.subheader("🧪 Historical Backtest Results (With Full P&L Explanation)")
        for exp in state["experiments"][:6]:
            m = exp["metrics"]
            net_profit = float(m.get("final_equity", 100000.0)) - 100000.0
            title = (
                f"📌 Strategy: {exp['strategy_id']} v{exp['version']} | "
                f"Date Span: {exp['start_date']} → {exp['end_date']} | "
                f"Simulated Net P&L: ${net_profit:+,.2f} ({m.get('total_return_pct', 0.0):+.2f}% vs SPY +{m.get('benchmark_return_pct', 0.0):.2f}%)"
            )
            with st.expander(title, expanded=False):
                st.markdown(
                    f"""
                    #### 🧮 How This Historical Backtest Arrived at `${net_profit:+,.2f}` (`{m.get('total_return_pct', 0.0):+.2f}%`):
                    - **Strategy Tested**: `{exp['strategy_id']} v{exp['version']}`
                    - **Date Span**: `{exp['start_date']}` to `{exp['end_date']}`
                    - **Starting Capital**: `$100,000.00` $\\rightarrow$ **Ending Capital**: `${m.get('final_equity', 100000.0):,.2f}`
                    - **Total Trades Executed**: `{m.get('trade_count', 0)}` trades (Average hold: `{m.get('avg_holding_period_days', 0.0):.1f}` trading days)
                    - **Win / Loss Math**:
                      - **Win Rate**: `{m.get('win_rate_pct', 0.0):.1f}%` of trades were profitable
                      - **Average Winning Trade**: `${m.get('avg_winning_trade_usd', 0.0):+,.2f}` (`{m.get('avg_winning_trade_pct', 0.0):+.2f}%`)
                      - **Average Losing Trade**: `${m.get('avg_losing_trade_usd', 0.0):+,.2f}` (`{m.get('avg_losing_trade_pct', 0.0):+.2f}%`)
                      - **Average Expected Profit per Trade**: `${m.get('expectancy_usd', 0.0):+,.2f}` (after deducting broker commissions, bid-ask spread, and slippage on every trade)
                    - **Risk Score (Sharpe Ratio)**: `{m.get('sharpe_ratio', 0.0):.2f}` (Above `1.0` is good; SPY benchmark was `{m.get('benchmark_sharpe', 0.0):.2f}`)
                    - **Worst Historical Drop (Max Drawdown)**: `-{m.get('max_drawdown_pct', 0.0):.2f}%`
                    """
                )
                st.markdown("**Individual Historical Trades (First 25 Shown)**")
                st.dataframe(exp["trades"][:25], use_container_width=True)

    # =========================================================================
    # TAB 5: PAPER TRADING LEDGER
    # =========================================================================
    with tabs[5]:
        st.info(
            "💡 **What is this tab?** This is your **Permanent Receipt Book (Trade Ledger)**. Every time the paper account buys or sells "
            "a stock, it writes a permanent line here showing the exact strategy, date, share count, fill price, fee paid, and resulting cash balance."
        )
        st.subheader(f"🧾 Permanent Paper Trade Ledger (Date Span: {paper_date_span})")
        if ledger:
            clean_ledger = [
                {
                    "Date": l["fill_date"],
                    "Strategy Used": f"{l['strategy_id']} v{l['strategy_version']}",
                    "Action": "🟢 BUY" if l["side"] == "BUY" else "🔴 SELL",
                    "Ticker": l["ticker"],
                    "Shares": l["quantity"],
                    "Fill Price": f"${l['fill_price']:.2f}",
                    "Total Trade Value": f"${l['gross_amount']:,.2f}",
                    "Fees & Slippage Paid": f"${float(l['commission_usd']) + float(l['slippage_usd']):.2f}",
                    "Locked-In (Realised) P&L": f"${l['realised_pnl']:+,.2f}" if l["side"] == "SELL" else "$0.00 (Open)",
                    "Cash Balance After Trade": f"${l['cash_after']:,.2f}",
                    "Why This Trade Happened": l["notes"],
                }
                for l in ledger
            ]
            st.dataframe(clean_ledger, use_container_width=True)
        else:
            st.write("No paper trades filled yet.")

    # =========================================================================
    # TAB 6: RISK & SECTOR ANALYTICS
    # =========================================================================
    with tabs[6]:
        st.info(
            "💡 **What is this tab?** This shows **Where Your Money is Parked by Industry Sector** (making sure we never put more than 30% "
            "into one sector) and how strategies performed across **4 separate time periods (Walk-Forward Folds)** so we know they didn't just get lucky once."
        )
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🥧 Current Sector Exposure (Max 30% Allowed per Sector)")
            if acc["sector_exposures_pct"]:
                sec_rows = [
                    {"Sector": sec, "Current Portfolio %": f"{pct:.2f}%", "Max Allowed Limit": "30.00%"}
                    for sec, pct in acc["sector_exposures_pct"].items()
                ]
                st.dataframe(sec_rows, use_container_width=True)
            else:
                st.write("Currently 0% invested in sectors (100% in cash).")
        with c2:
            st.subheader("📅 4-Period Walk-Forward Consistency Test")
            st.caption("Divides history into 4 separate chunks to verify the strategy worked consistently across different market phases:")
            if strats and strats[0].get("validation_summary"):
                wf_windows = (strats[0]["validation_summary"].get("walk_forward") or {}).get("windows", [])
                st.dataframe(wf_windows, use_container_width=True)

    # =========================================================================
    # TAB 7: SYSTEM LOGS & SAFETY ALERTS
    # =========================================================================
    with tabs[7]:
        st.info(
            "💡 **What is this tab?** This is the **Black Box Flight Recorder**. It logs every automated daily/weekly job run "
            "and every time the **Portfolio Risk Manager** stepped in to block a trade that broke a safety limit."
        )
        st.subheader("🛡️ Trades Blocked by the Safety Bouncer (Risk Alerts & Vetoes)")
        if state["risk_alerts"]:
            st.dataframe(state["risk_alerts"], use_container_width=True)
        else:
            st.success("No risk limits breached — 0 safety alerts triggered.")

        st.subheader("⚙️ Automated Job Execution History")
        st.dataframe(state["jobs"], use_container_width=True)


if __name__ == "__main__":
    main()
