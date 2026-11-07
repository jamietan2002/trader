"""Streamlit Community Cloud & Local Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

Minimalist, institutional-grade layout with interactive progressive disclosure:
- Every tab features a concise one-line summary, hover tooltips on metrics/columns, and an expandable
  "How this tab works" guide.
- The "Platform Guide" tab provides a visual mental-model diagram of the Daily and Weekly loops,
  an interactive step-by-step lifecycle explorer, and expandable deep-dive sections.
- Profit & Loss (P&L) is presented with complete transparency: explicitly stating the Strategy Used,
  Exact Date Span, and step-by-step accounting formula (`Starting Capital + Realised P&L + Unrealised P&L = Total Equity`).
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


def _get_paper_date_span(snapshots: List[Dict[str, Any]], ledger: List[Dict[str, Any]]) -> str:
    dates: List[str] = []
    for s in snapshots:
        if s.get("snapshot_date"):
            dates.append(str(s["snapshot_date"]))
    for l in ledger:
        if l.get("fill_date"):
            dates.append(str(l["fill_date"]))
    if not dates:
        return "No active sessions recorded yet"
    dates.sort()
    return f"{dates[0]} to {dates[-1]} ({len(set(dates))} trading sessions)"


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
                "Strategy Name": strat_names.get(key, row["strategy_id"]),
                "Date Span": f"{row['fill_date']} → {row['fill_date']}",
                "_first_dt": row["fill_date"],
                "_last_dt": row["fill_date"],
                "Executions": 0,
                "Closed Trades": 0,
                "Realised P&L ($)": 0.0,
                "Unrealised P&L ($)": 0.0,
                "Transaction Costs ($)": 0.0,
            },
        )
        item["Executions"] += 1
        item["_first_dt"] = min(item["_first_dt"], row["fill_date"])
        item["_last_dt"] = max(item["_last_dt"], row["fill_date"])
        item["Date Span"] = f"{item['_first_dt']} → {item['_last_dt']}"
        fees = float(row.get("commission_usd", 0.0)) + float(row.get("slippage_usd", 0.0))
        item["Transaction Costs ($)"] = round(item["Transaction Costs ($)"] + fees, 2)
        if row["side"] == "SELL":
            item["Closed Trades"] += 1
            item["Realised P&L ($)"] = round(
                item["Realised P&L ($)"] + float(row.get("realised_pnl", 0.0)), 2
            )

    for pos in positions:
        key = f"{pos['strategy_id']} v{pos['strategy_version']}"
        item = by_strat.setdefault(
            key,
            {
                "Strategy": key,
                "Strategy Name": strat_names.get(key, pos["strategy_id"]),
                "Date Span": f"{pos['opened_date']} → Present",
                "_first_dt": pos["opened_date"],
                "_last_dt": pos["opened_date"],
                "Executions": 1,
                "Closed Trades": 0,
                "Realised P&L ($)": 0.0,
                "Unrealised P&L ($)": 0.0,
                "Transaction Costs ($)": 0.0,
            },
        )
        item["Unrealised P&L ($)"] = round(
            item["Unrealised P&L ($)"] + float(pos.get("unrealised_pnl", 0.0)), 2
        )

    out: List[Dict[str, Any]] = []
    for item in by_strat.values():
        net_total = round(item["Realised P&L ($)"] + item["Unrealised P&L ($)"], 2)
        out.append(
            {
                "Strategy": item["Strategy"],
                "Strategy Name": item["Strategy Name"],
                "Date Span": item["Date Span"],
                "Executions": item["Executions"],
                "Closed Trades": item["Closed Trades"],
                "Realised P&L ($)": item["Realised P&L ($)"],
                "Unrealised P&L ($)": item["Unrealised P&L ($)"],
                "Transaction Costs ($)": item["Transaction Costs ($)"],
                "Total Net P&L ($)": net_total,
                "Calculation Basis": (
                    f"Realised (${item['Realised P&L ($)']:+,.2f}) + "
                    f"Unrealised (${item['Unrealised P&L ($)']:+,.2f}) "
                    f"[net of ${item['Transaction Costs ($)']:,.2f} costs]"
                ),
            }
        )
    return out


MENTAL_MODEL_HTML = """
<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:18px 20px;margin:10px 0 18px 0;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.06em;color:#94a3b8;margin-bottom:10px;">
    System Mental Model — Two Automated Loops
  </div>
  <div style="margin-bottom:14px;">
    <div style="font-size:0.84rem;font-weight:600;color:#38bdf8;margin-bottom:6px;">
      1. Daily Execution Loop (Mon–Fri, After US Market Close)
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;font-size:0.8rem;">
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #38bdf8;">
        <strong>Step 1 · Market Data</strong><br/><span style="color:#94a3b8;">Download daily prices &amp; earnings updates.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #38bdf8;">
        <strong>Step 2 · AI Research</strong><br/><span style="color:#94a3b8;">Rank liquid US stocks by trend &amp; catalysts.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #38bdf8;">
        <strong>Step 3 · Rule Signals</strong><br/><span style="color:#94a3b8;">Check active strategies for buy/sell triggers.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #10b981;">
        <strong>Step 4 · Risk Gate</strong><br/><span style="color:#94a3b8;">Size trade (1% risk) &amp; verify 7 safety caps.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #10b981;">
        <strong>Step 5 · Paper Ledger</strong><br/><span style="color:#94a3b8;">Simulate fill after fees &amp; update P&amp;L.</span>
      </div>
    </div>
  </div>
  <div>
    <div style="font-size:0.84rem;font-weight:600;color:#a855f7;margin-bottom:6px;">
      2. Weekly Self-Improvement Loop (Saturdays, 10:00 SGT)
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;font-size:0.8rem;">
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #a855f7;">
        <strong>Step A · Review Trades</strong><br/><span style="color:#94a3b8;">Diagnose wins, losses &amp; current market regime.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #a855f7;">
        <strong>Step B · Draft Hypothesis</strong><br/><span style="color:#94a3b8;">Create a new candidate strategy version (v+1).</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #f59e0b;">
        <strong>Step C · 9-Gate Backtest</strong><br/><span style="color:#94a3b8;">Test across historical &amp; walk-forward periods.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #10b981;">
        <strong>Step D · Promote or Reject</strong><br/><span style="color:#94a3b8;">Only versions passing all 9 gates go live.</span>
      </div>
    </div>
  </div>
</div>
"""


def _render_tab_header(st: Any, summary: str, guide_title: str, guide_markdown: str) -> None:
    """Render a minimalist tab summary bar with an interactive 'How this tab works' toggle."""
    c_text, c_help = st.columns([4, 1])
    with c_text:
        st.caption(summary)
    with c_help:
        if hasattr(st, "popover"):
            with st.popover(f"? {guide_title}", use_container_width=True):
                st.markdown(guide_markdown)
        else:
            with st.expander(f"? {guide_title}"):
                st.markdown(guide_markdown)


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
        page_title="Swing Trading AI — Systematic Research & Paper Portfolio",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    app = PlatformApplication()
    if not app.orchestrator.registry.list_strategies():
        with st.spinner("Initializing market dataset, baseline strategies, and paper portfolio..."):
            app.orchestrator.bootstrap_baseline_system()
            spy_bars = app.orchestrator.market_data.get_bars("SPY")
            for b in spy_bars[-10:]:
                app.orchestrator.run_daily_workflow(b.bar_date)

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
        else "None active"
    )
    paper_date_span = _get_paper_date_span(snapshots, ledger)
    total_fees_paid = round(
        sum(float(l.get("commission_usd", 0.0)) + float(l.get("slippage_usd", 0.0)) for l in ledger),
        2,
    )
    net_dollar_pnl = round(float(acc["total_equity"]) - float(acc["starting_capital"]), 2)

    # Minimalist Sidebar Controls
    with st.sidebar:
        st.markdown("### Portfolio Controls")
        st.caption(f"Execution Mode: **{acc['trading_mode'].upper()}** ($100,000 Virtual)")
        st.caption(f"Data Source: **{app.settings.market_data_provider.upper()}**")
        st.caption(f"Timezone: **{app.settings.operator_timezone}**")
        st.markdown("---")
        spy_bars_all = app.orchestrator.market_data.get_bars("SPY")
        latest_bar_dt = spy_bars_all[-1].bar_date if spy_bars_all else "2025-06-27"
        if st.button(
            "Run Daily Session",
            use_container_width=True,
            help="Downloads latest market prices, evaluates stop-loss/take-profit exits, and checks for new strategy entries.",
        ):
            app.orchestrator.run_daily_workflow(latest_bar_dt, force=True)
            st.rerun()
        if st.button(
            "Run Weekly Strategy Discovery",
            use_container_width=True,
            help="Reviews recent trades, drafts a candidate strategy improvement, and tests it against the 9 validation gates.",
        ):
            app.orchestrator.run_weekly_workflow(latest_bar_dt, force=True)
            st.rerun()
        if acc["kill_switch_engaged"]:
            st.markdown("---")
            if st.button(
                "Reset Paper Account ($100k)",
                use_container_width=True,
                help="Clears the kill-switch lock and resets the simulated paper portfolio back to $100,000 cash.",
            ):
                app.orchestrator.paper_engine.reset_account_to_starting_capital()
                st.rerun()

    st.title("Swing Trading AI")
    st.caption(
        "Autonomous US Equities Research, Statistical Validation, and Paper-Trading Platform • Benchmark: SPY"
    )

    # Compact Executive Summary Expander (collapsed by default for minimalism, 1-click to open)
    status_label = (
        "Active"
        if not acc["kill_switch_engaged"]
        else f"Paused ({acc['kill_switch_reason']})"
    )
    with st.expander(
        f"System Snapshot — Equity: ${acc['total_equity']:,.2f} ({acc['total_return_pct']:+.2f}%) · "
        f"Status: {status_label} · Open Positions: {acc['open_positions_count']}/10",
        expanded=False,
    ):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Portfolio & Risk Status**")
            st.write(f"- **State**: {status_label}")
            st.write(f"- **Drawdown from Peak**: `-{acc['current_drawdown_pct']:.2f}%` (Limit: `15.0%`)")
            st.write(f"- **Open Positions**: `{acc['open_positions_count']} / 10`")
        with c2:
            st.markdown("**Paper Portfolio Accounting**")
            st.write(f"- **Window**: `{paper_date_span}`")
            st.write(
                f"- **Formula**: `${acc['starting_capital']:,.2f}` (Start) "
                f"+ `${acc['realised_pnl']:+,.2f}` (Closed) "
                f"+ `${acc['unrealised_pnl']:+,.2f}` (Open) "
                f"= **`${acc['total_equity']:,.2f}`**"
            )
            st.write(f"- **Strategies**: `{len(active_paper_strats)}` active (`{len(rejected_strats)}` rejected in testing)")
        with c3:
            st.markdown("**Automated Schedule**")
            st.write("- **Weekdays (21:30 UTC)**: Market scan, signal check, and paper execution.")
            st.write("- **Saturdays (10:00 SGT)**: Strategy discovery and walk-forward validation.")

    tabs = st.tabs(
        [
            "Platform Guide",
            "Overview & P&L",
            "Market Research",
            "Strategies",
            "Backtesting",
            "Paper Ledger",
            "Risk & Analytics",
            "System Logs",
        ]
    )

    # =========================================================================
    # TAB 0: PLATFORM GUIDE (SIMPLE OVERVIEW, DIAGRAM & EXPANDABLE DEEP-DIVES)
    # =========================================================================
    with tabs[0]:
        st.markdown("#### What This System Does & How It Runs")
        st.write(
            "This platform manages a simulated **$100,000 US stock portfolio** over **3 to 15 trading-day** holding periods (swing trading). "
            "To keep decision-making disciplined, **AI agents only research stocks and propose strategy rules**, while **strict mathematical code** "
            "tests those rules on historical data, enforces risk limits, and executes every trade."
        )

        # Visual Mental Model Diagram
        st.markdown(MENTAL_MODEL_HTML, unsafe_allow_html=True)

        # Interactive Step-by-Step Explorer
        st.markdown("##### Interactive Walkthrough — Click a Stage to Inspect How It Works")
        if "walkthrough_step" not in st.session_state:
            st.session_state["walkthrough_step"] = "step1"

        b1, b2, b3, b4, b5 = st.columns(5)
        if b1.button("1. Stock Scan", use_container_width=True):
            st.session_state["walkthrough_step"] = "step1"
        if b2.button("2. Strategy Signal", use_container_width=True):
            st.session_state["walkthrough_step"] = "step2"
        if b3.button("3. Risk & Sizing", use_container_width=True):
            st.session_state["walkthrough_step"] = "step3"
        if b4.button("4. Execution & Exit", use_container_width=True):
            st.session_state["walkthrough_step"] = "step4"
        if b5.button("5. Weekly Upgrade", use_container_width=True):
            st.session_state["walkthrough_step"] = "step5"

        step_info = {
            "step1": (
                "**Stage 1 — Daily Stock Scan (`MarketResearchAgent`)**\n\n"
                "- **What happens**: After the US market closes, the system downloads daily prices for liquid NYSE/NASDAQ large-cap stocks and compares them against the S&P 500 (`SPY`).\n"
                "- **What it looks for**: Stocks outperforming `SPY` over the last 20 days, trading on above-average volume, or reacting to positive quarterly earnings.\n"
                "- **Safety boundary**: Research rankings only highlight candidates—they never place orders on their own."
            ),
            "step2": (
                "**Stage 2 — Deterministic Strategy Signal (`StrategySignalEngine`)**\n\n"
                "- **What happens**: Approved strategy rulebooks check whether any stock meets exact mathematical entry criteria at today's close.\n"
                "- **Example (`Momentum Trend`)**: Price is above both its 20-day and 50-day moving averages, 20-day return beats `SPY` by at least `+2%`, RSI is between `50` and `72` (trending but not overheated), and volume is above average."
            ),
            "step3": (
                "**Stage 3 — Position Sizing & Risk Check (`PortfolioRiskManager`)**\n\n"
                "- **What happens**: Before a buy order is allowed, the Risk Manager calculates how many shares to buy and checks 7 portfolio limits.\n"
                "- **Volatility Sizing**: Share count is set so that if the stock drops to its stop-loss price, the portfolio loses at most **1.0% of total equity** (`~$1,000`).\n"
                "- **Veto Power**: If a trade would push a single stock above `15%`, a sector above `30%`, or total open stop-loss risk above `5%`, the trade is automatically blocked."
            ),
            "step4": (
                "**Stage 4 — Realistic Fill & Automatic Exit (`PaperTradingEngine`)**\n\n"
                "- **What happens**: Approved signals at Day `T` close fill at Day `T+1` open price, deducting realistic brokerage commission, bid-ask spread, and slippage.\n"
                "- **Automatic Exit**: Every position carries a protective **Stop-Loss**, a **Take-Profit target**, a **Trailing Stop**, and a **Maximum Holding Time (10–15 days)**. Whichever is hit first closes the trade."
            ),
            "step5": (
                "**Stage 5 — Saturday Self-Improvement (`StrategyDiscoveryAgent` & `StrategyEvaluationAgent`)**\n\n"
                "- **What happens**: Every Saturday, the system reviews closed trades from the week and proposes a refined strategy version (`v+1`).\n"
                "- **The 9-Gate Audit**: The new version is tested across historical and walk-forward windows. If it beats the 9 risk-adjusted criteria, it is promoted; if it fails even one gate, it is rejected."
            ),
        }
        st.info(step_info[st.session_state["walkthrough_step"]])

        st.markdown("##### Deeper Dives — Expand Any Topic Below")
        with st.expander("The 3 Trading Strategies — How signals are generated"):
            st.markdown(
                """
                1. **Momentum & Relative Strength (`strat_momentum_trend`)** — Buys liquid stocks in established uptrends (above 20d and 50d moving averages) that are outperforming the S&P 500 (`SPY`) with strong volume. Held for 4–12 trading days.
                2. **Post-Earnings Drift (`strat_pead_drift`)** — Captures multi-day follow-through after a company beats quarterly earnings and revenue estimates with a volume surge. Held for 3–10 trading days.
                3. **Volatility Breakout (`strat_volatility_breakout`)** — Identifies stocks that trade quietly in a tight 10-day range and then break above their 20-day high on 1.35x normal volume. Held for 3–12 trading days.
                """
            )
        with st.expander("The 7 Risk Controls — How the portfolio is protected from large losses"):
            st.markdown(
                """
                - **1.0% Max Risk Per Trade**: Position size scales automatically with stock volatility (`ATR`) so a stop-loss exit loses at most `~$1,000` on a `$100,000` account.
                - **5.0% Max Total Open Risk (Portfolio Heat)**: Combined stop-loss risk across all open positions cannot exceed `5.0%` of equity.
                - **15.0% Single-Stock Limit**: Prevents over-allocating to any single company.
                - **30.0% Sector Limit**: Prevents over-concentration in any single industry (e.g., Technology).
                - **Max 10 Open Positions**: Keeps the portfolio focused and liquid.
                - **Correlation & Liquidity Filter**: Blocks stocks with `<$20M` daily trading volume or `>0.80` return correlation with an existing holding.
                - **15.0% Drawdown Kill Switch**: Automatically pauses new buying if total portfolio equity drops `15%` below its peak.
                """
            )
        with st.expander("The 9 Validation Gates — How new strategy versions are tested before trading"):
            st.markdown(
                """
                A strategy or weekly upgrade is only allowed to trade paper capital (`PAPER_TRADING` status) if it passes all 9 tests on historical data:
                1. **Positive Out-of-Sample Return** (profitable on unseen test dates)
                2. **Sharpe Ratio $\\ge 1.0$** (strong return relative to daily volatility)
                3. **Profit Factor $\\ge 1.3$** (gross winning dollars $\\ge 1.3\\times$ gross losing dollars)
                4. **Maximum Drawdown $\\le 15.0\\%$** (worst peak-to-valley drop stays under 15%)
                5. **Minimum 15 Trades** (statistically meaningful sample size)
                6. **Walk-Forward Consistency $\\ge 60\\%$** (profitable across multiple rolling time windows)
                7. **Survives $2\\times$ Transaction Cost Stress Test** (remains profitable even if fees and slippage double)
                8. **Beats `SPY` Risk-Adjusted** (delivers higher Sharpe or lower drawdown than passive index holding)
                9. **No Single-Trade Dependency** (no single lucky trade accounts for $>65\\%$ of total profit)
                """
            )
        with st.expander("How Profit & Loss (P&L) Is Calculated — Paper Account vs. Historical Backtests"):
            st.markdown(
                """
                - **Simulated Paper Portfolio (Overview & Paper Ledger tabs)**: Tracks day-by-day trades starting from `$100,000.00`.
                  $$\text{Current Equity} = \text{Starting Capital (\$100,000)} + \text{Realised P\&L (Closed Trades)} + \text{Unrealised P\&L (Open Positions)}$$
                  Every trade deducts realistic brokerage commissions (`$0.005/share`, min `$1.00`) and bid-ask slippage (`5.5 bps`).
                - **Historical Backtests (Strategies & Backtesting tabs)**: Simulates how a strategy rulebook would have performed over multi-year historical data (`2023–2025`). Backtest numbers are used strictly to validate strategies and are never mixed into your live paper account balance.
                """
            )

    # =========================================================================
    # TAB 1: OVERVIEW & TRANSPARENT P&L BREAKDOWN
    # =========================================================================
    with tabs[1]:
        _render_tab_header(
            st,
            "Overview & P&L: Real-time simulated portfolio value, strategy attribution, and currently held positions.",
            "How this tab works",
            "**What this tab shows:** Your simulated `$100,000` paper trading account.\n\n"
            "- **Realised P&L**: Profit or loss locked in from completed (closed) trades after subtracting commissions and slippage.\n"
            "- **Unrealised P&L**: Floating profit or loss on stocks currently held, based on the latest market close price.\n"
            "- **Strategy Attribution Table**: Shows exactly which strategy generated each dollar of P&L and over what date range.",
        )

        st.markdown("#### Paper Portfolio Profit & Loss Attribution")
        st.markdown(
            f"""
            - **Active Strategies**: {active_strat_names}
            - **Measurement Window**: `{paper_date_span}`
            - **Derivation**:
              `Starting Capital ($100,000.00)` + `Realised P&L (${acc['realised_pnl']:+,.2f})` + `Unrealised P&L (${acc['unrealised_pnl']:+,.2f})` = **`Current Equity (${acc['total_equity']:,.2f})`** *(Net of `${total_fees_paid:,.2f}` in transaction costs)*
            """
        )

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric(
            "Total Equity",
            f"${acc['total_equity']:,.2f}",
            f"{net_dollar_pnl:+,.2f} ({acc['total_return_pct']:+.2f}%)",
            help="Cash Balance + Market Value of Open Positions. Equals Starting Capital ($100k) + Realised P&L + Unrealised P&L.",
        )
        k2.metric(
            "Starting Capital",
            f"${acc['starting_capital']:,.2f}",
            help="Initial virtual cash baseline in PAPER mode.",
        )
        k3.metric(
            "Realised P&L (Closed)",
            f"${acc['realised_pnl']:+,.2f}",
            f"Net of ${total_fees_paid:,.2f} costs",
            help="Locked-in net profit/loss from completed buy-and-sell trades after brokerage fees and slippage.",
        )
        k4.metric(
            "Unrealised P&L (Open)",
            f"${acc['unrealised_pnl']:+,.2f}",
            f"{acc['open_positions_count']} positions",
            help="Floating profit/loss on currently held positions marked to the latest closing price.",
        )
        k5.metric(
            "Available Cash",
            f"${acc['cash_balance']:,.2f}",
            f"Drawdown: -{acc['current_drawdown_pct']:.2f}%",
            help="Uninvested cash available for new swing entries. Drawdown measures the drop from the portfolio's highest equity peak.",
        )

        st.markdown("#### Strategy-Level P&L Breakdown (Paper Account)")
        strat_pnl_rows = _summarize_pnl_by_strategy(ledger, positions, strats)
        if strat_pnl_rows:
            st.dataframe(strat_pnl_rows, use_container_width=True)
        else:
            st.info("No paper trades executed in the current window.")

        st.markdown("#### Open Positions")
        if positions:
            clean_pos = [
                {
                    "Ticker": p["ticker"],
                    "Strategy": f"{p['strategy_id']} v{p['strategy_version']}",
                    "Entry Date": p["opened_date"],
                    "Holding Days": p["holding_days"],
                    "Quantity": p["quantity"],
                    "Avg Entry Price": f"${p['avg_entry_price']:.2f}",
                    "Current Price": f"${p['current_price']:.2f}",
                    "Stop-Loss": f"${p['stop_loss_price']:.2f}" if p.get("stop_loss_price") else "-",
                    "Take-Profit": f"${p['take_profit_price']:.2f}" if p.get("take_profit_price") else "-",
                    "Market Value": f"${p['market_value']:,.2f}",
                    "Unrealised P&L": f"${p['unrealised_pnl']:+,.2f} ({p['unrealised_return_pct']:+.2f}%)",
                }
                for p in positions
            ]
            st.dataframe(clean_pos, use_container_width=True)
        else:
            st.write("No open positions currently held (100% cash).")

    # =========================================================================
    # TAB 2: MARKET RESEARCH
    # =========================================================================
    with tabs[2]:
        _render_tab_header(
            st,
            "Market Research: Daily ranking of liquid US stocks by trend strength vs. SPY, volume activity, and earnings catalysts.",
            "How this tab works",
            "**What this tab shows:** The daily watchlist generated by the `MarketResearchAgent`.\n\n"
            "- **20d RS vs SPY**: How much the stock beat (or trailed) the S&P 500 over the past 20 trading days.\n"
            "- **Volume Ratio (20d)**: Today's trading volume divided by its 20-day average (`>1.2x` indicates institutional participation).\n"
            "- **Composite Score**: Overall multi-factor rank (`0–100`) combining trend, relative strength, volume, and earnings catalysts.\n"
            "- **Post-Session Proposals**: Observations written after market close suggesting future strategy experiments.",
        )
        st.markdown("#### Ranked US Equity Candidates")
        reports_summary = [
            {
                "Rank": idx + 1,
                "Ticker": r["ticker"],
                "Company": r["company_name"],
                "Price": f"${r['current_price']:.2f}",
                "Sector": r["market_and_sector_context"]["sector"],
                "20d RS vs SPY": f"{r['relative_strength_vs_spy_20d']:+.2f}%",
                "Volume Ratio (20d)": f"{r['volume_analysis']['volume_ratio_20']:.2f}x",
                "Strategy Archetype": r["suggested_strategy_family"],
                "Composite Score": r["composite_rank_score"],
                "Evidence Score*": f"{r['research_confidence_score'] * 100:.0f}%",
                "Bullish Thesis": r["bullish_thesis"],
                "Key Risk / Bearish Case": r["bearish_thesis"],
            }
            for idx, r in enumerate(state["research_reports"])
        ]
        st.dataframe(reports_summary, use_container_width=True)
        st.caption(
            "*Evidence Score reflects data completeness and indicator alignment; it is not a guarantee of future profit."
        )

        with st.expander("View Post-Session Experiment Proposals (`PerformanceAnalystAgent`)", expanded=False):
            st.dataframe(state["proposals"], use_container_width=True)

    # =========================================================================
    # TAB 3: STRATEGIES
    # =========================================================================
    with tabs[3]:
        _render_tab_header(
            st,
            "Strategies: Registry of all quantitative rulebooks, their historical test scores, and whether they are approved for paper trading.",
            "How this tab works",
            "**What this tab shows:** Every strategy version in the registry.\n\n"
            "- **`PAPER_TRADING` Status**: Passed all 9 validation gates and is actively trading in the paper portfolio.\n"
            "- **`REJECTED` Status**: Failed one or more validation gates (for example, Sharpe `< 1.0` or Profit Factor `< 1.3`) and is blocked from trading.\n"
            "- **Sharpe Ratio**: Risk-adjusted return (`>1.0` is good, `>1.5` is strong).\n"
            "- **Profit Factor**: Total dollars won divided by total dollars lost (`>1.3` required).",
        )
        st.markdown("#### Registered Strategy Versions & Validation Status")
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
                    "Name": s["name"],
                    "Family": s["strategy_family"],
                    "Status": s["status"],
                    "Holding Horizon": f"{s['holding_period_min_days']}–{s['holding_period_max_days']}d",
                    "Backtest Net P&L ($100k Base)": f"${net_bt_profit:+,.2f} ({m.get('total_return_pct', 0.0):+.2f}%)",
                    "Benchmark (SPY)": f"{m.get('benchmark_return_pct', 0.0):+.2f}%",
                    "Sharpe": m.get("sharpe_ratio"),
                    "Profit Factor": m.get("profit_factor"),
                    "Max Drawdown": f"-{m.get('max_drawdown_pct', 0.0):.2f}%",
                    "Trades": m.get("trade_count", 0),
                    "Validation Audit": s["promotion_decision_reason"],
                }
            )
        st.dataframe(strat_rows, use_container_width=True)

    # =========================================================================
    # TAB 4: BACKTESTING
    # =========================================================================
    with tabs[4]:
        _render_tab_header(
            st,
            "Backtesting: Multi-year historical simulations showing how each strategy performed across past market cycles.",
            "How this tab works",
            "**What this tab shows:** Historical simulations (`2023–2025`) used to test strategies before they are allowed to trade.\n\n"
            "- **Zero Look-Ahead Bias**: Signals triggered at Day `T` market close are filled at Day `T+1` market open.\n"
            "- **Realistic Friction**: Every simulated trade deducts brokerage commission, bid-ask spread, and slippage.\n"
            "- **Click any experiment bar below** to expand its P&L math, win/loss statistics, and individual historical trades.",
        )
        st.markdown("#### Historical Backtest Experiments (Click to Expand Details)")
        for exp in state["experiments"][:6]:
            m = exp["metrics"]
            net_profit = float(m.get("final_equity", 100000.0)) - 100000.0
            title = (
                f"{exp['strategy_id']} v{exp['version']} ({exp['experiment_type']})  ·  "
                f"Span: {exp['start_date']} → {exp['end_date']}  ·  "
                f"Net P&L: ${net_profit:+,.2f} ({m.get('total_return_pct', 0.0):+.2f}% vs SPY {m.get('benchmark_return_pct', 0.0):+.2f}%)"
            )
            with st.expander(title, expanded=False):
                st.markdown(
                    f"""
                    **Backtest P&L Derivation**
                    - **Strategy**: `{exp['strategy_id']} v{exp['version']}`
                    - **Date Span**: `{exp['start_date']}` to `{exp['end_date']}`
                    - **Capital Progression**: `$100,000.00` $\\rightarrow$ `${m.get('final_equity', 100000.0):,.2f}` (`{m.get('trade_count', 0)}` trades, average hold `{m.get('avg_holding_period_days', 0.0):.1f}` days)
                    - **Trade Distribution**: Win Rate `{m.get('win_rate_pct', 0.0):.1f}%` | Avg Win `${m.get('avg_winning_trade_usd', 0.0):+,.2f}` (`{m.get('avg_winning_trade_pct', 0.0):+.2f}%`) | Avg Loss `${m.get('avg_losing_trade_usd', 0.0):+,.2f}` (`{m.get('avg_losing_trade_pct', 0.0):+.2f}%`) | Expectancy `${m.get('expectancy_usd', 0.0):+,.2f}/trade`
                    - **Risk Metrics**: Sharpe `{m.get('sharpe_ratio', 0.0):.2f}` | Sortino `{m.get('sortino_ratio', 0.0):.2f}` | Profit Factor `{m.get('profit_factor', 0.0):.2f}` | Max Drawdown `-{m.get('max_drawdown_pct', 0.0):.2f}%`
                    """
                )
                st.dataframe(exp["trades"][:25], use_container_width=True)

    # =========================================================================
    # TAB 5: PAPER TRADING LEDGER
    # =========================================================================
    with tabs[5]:
        _render_tab_header(
            st,
            "Paper Ledger: Chronological log of every simulated buy/sell fill, transaction fee, and resulting cash balance.",
            "How this tab works",
            "**What this tab shows:** The accounting ledger for the simulated `$100,000` portfolio.\n\n"
            "- **`BUY` rows**: Deduct purchase cost plus commission/slippage from cash (`Realised P&L` is `$0.00` on entry).\n"
            "- **`SELL` rows**: Return sale proceeds to cash and lock in the net `Realised P&L` for that trade.\n"
            "- **Signal Rationale**: Explains the exact indicator trigger or exit rule (e.g., Take-Profit, Stop-Loss, Max Hold) for each fill.",
        )
        st.markdown(f"#### Trade Execution Ledger (`{paper_date_span}`)")
        if ledger:
            clean_ledger = [
                {
                    "Date": l["fill_date"],
                    "Strategy": f"{l['strategy_id']} v{l['strategy_version']}",
                    "Side": l["side"],
                    "Ticker": l["ticker"],
                    "Quantity": l["quantity"],
                    "Fill Price": f"${l['fill_price']:.2f}",
                    "Gross Notional": f"${l['gross_amount']:,.2f}",
                    "Costs (Comm + Slip)": f"${float(l['commission_usd']) + float(l['slippage_usd']):.2f}",
                    "Realised P&L": f"${l['realised_pnl']:+,.2f}" if l["side"] == "SELL" else "$0.00 (Entry)",
                    "Cash After Fill": f"${l['cash_after']:,.2f}",
                    "Signal Rationale": l["notes"],
                }
                for l in ledger
            ]
            st.dataframe(clean_ledger, use_container_width=True)
        else:
            st.write("No paper executions recorded yet.")

    # =========================================================================
    # TAB 6: RISK & ANALYTICS
    # =========================================================================
    with tabs[6]:
        _render_tab_header(
            st,
            "Risk & Analytics: Real-time sector exposure vs. the 30% cap and multi-window walk-forward stability.",
            "How this tab works",
            "**What this tab shows:** Portfolio diversification and statistical robustness.\n\n"
            "- **Sector Concentration**: Tracks how much of the portfolio is invested in each industry against the `30.0%` hard cap.\n"
            "- **Walk-Forward Validation Folds**: Splits historical data into 4 sequential time windows (`Fold 1` to `Fold 4`) to verify that a strategy stays profitable across changing market conditions rather than relying on one lucky period.",
        )
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Sector Concentration vs. 30% Cap")
            if acc["sector_exposures_pct"]:
                sec_rows = [
                    {"Sector": sec, "Portfolio Exposure": f"{pct:.2f}%", "Hard Limit": "30.00%"}
                    for sec, pct in acc["sector_exposures_pct"].items()
                ]
                st.dataframe(sec_rows, use_container_width=True)
            else:
                st.write("0% sector exposure (100% cash).")
        with c2:
            st.markdown("#### Walk-Forward Validation Folds")
            if strats and strats[0].get("validation_summary"):
                wf_windows = (strats[0]["validation_summary"].get("walk_forward") or {}).get("windows", [])
                st.dataframe(wf_windows, use_container_width=True)

    # =========================================================================
    # TAB 7: SYSTEM LOGS
    # =========================================================================
    with tabs[7]:
        _render_tab_header(
            st,
            "System Logs: Audit trail of automated daily/weekly runs and any trades blocked by the Risk Manager.",
            "How this tab works",
            "**What this tab shows:** Operational health and risk governance logs.\n\n"
            "- **Risk Vetoes & Alerts**: Whenever a strategy proposes a trade that would breach a safety limit (such as the `30%` sector cap or `5%` portfolio heat limit), the Risk Manager blocks the order and logs the exact reason here.\n"
            "- **Workflow Execution Log**: Confirms when each daily or weekly automation job ran and its completion status.",
        )
        st.markdown("#### Risk Vetoes & Alerts")
        if state["risk_alerts"]:
            st.dataframe(state["risk_alerts"], use_container_width=True)
        else:
            st.write("No risk alerts triggered.")

        with st.expander("View Workflow Execution Log", expanded=True):
            st.dataframe(state["jobs"], use_container_width=True)


if __name__ == "__main__":
    main()
