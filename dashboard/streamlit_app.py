"""Streamlit Community Cloud & Local Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

Minimalist, institutional-grade layout with zero-intervention autonomous monitoring:
- No manual daily/weekly trigger buttons cluttering the interface (runs 100% autonomously via scheduled cloud workflows).
- Every tab features a concise one-line summary, hover tooltips on metrics, and an interactive "? How this tab works" guide.
- Dedicated "Strategies & Live Readiness" tab with a 5-point Real-Money Readiness Scorecard comparing 9-gate historical
  backtests against forward paper-trading proof.
- The "Platform Guide" tab provides a visual mental-model diagram of the Daily and Weekly loops, a clear explanation of
  what is (and isn't) needed from the user, an interactive step-by-step walkthrough, and expandable deep-dive sections.
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
                "_wins": 0,
                "_gross_profit": 0.0,
                "_gross_loss": 0.0,
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
            rpnl = float(row.get("realised_pnl", 0.0))
            item["Realised P&L ($)"] = round(item["Realised P&L ($)"] + rpnl, 2)
            if rpnl > 0:
                item["_wins"] += 1
                item["_gross_profit"] += rpnl
            elif rpnl < 0:
                item["_gross_loss"] += abs(rpnl)

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
                "_wins": 0,
                "_gross_profit": 0.0,
                "_gross_loss": 0.0,
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
        closed = item["Closed Trades"]
        win_rate = (item["_wins"] / closed * 100.0) if closed > 0 else 0.0
        pf = (
            (item["_gross_profit"] / item["_gross_loss"])
            if item["_gross_loss"] > 0
            else (2.5 if item["_gross_profit"] > 0 else 0.0)
        )
        out.append(
            {
                "Strategy": item["Strategy"],
                "Strategy Name": item["Strategy Name"],
                "Date Span": item["Date Span"],
                "Executions": item["Executions"],
                "Closed Trades": closed,
                "Paper Win Rate": f"{win_rate:.1f}%" if closed > 0 else "-",
                "Paper Profit Factor": f"{pf:.2f}" if closed > 0 else "-",
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


def _build_strategy_readiness_rows(
    strategies: List[Dict[str, Any]],
    ledger: List[Dict[str, Any]],
    positions: List[Dict[str, Any]],
    min_paper_trades: int = 20,
) -> List[Dict[str, Any]]:
    """Evaluate every strategy version across both 9-gate backtests and forward paper-trading readiness."""
    paper_stats: Dict[str, Dict[str, Any]] = {}
    for row in ledger:
        key = f"{row['strategy_id']}:{row['strategy_version']}"
        st_item = paper_stats.setdefault(
            key, {"closed": 0, "wins": 0, "gross_win": 0.0, "gross_loss": 0.0, "realised": 0.0, "unrealised": 0.0}
        )
        if row["side"] == "SELL":
            st_item["closed"] += 1
            rpnl = float(row.get("realised_pnl", 0.0))
            st_item["realised"] += rpnl
            if rpnl > 0:
                st_item["wins"] += 1
                st_item["gross_win"] += rpnl
            elif rpnl < 0:
                st_item["gross_loss"] += abs(rpnl)

    for pos in positions:
        key = f"{pos['strategy_id']}:{pos['strategy_version']}"
        st_item = paper_stats.setdefault(
            key, {"closed": 0, "wins": 0, "gross_win": 0.0, "gross_loss": 0.0, "realised": 0.0, "unrealised": 0.0}
        )
        st_item["unrealised"] += float(pos.get("unrealised_pnl", 0.0))

    rows: List[Dict[str, Any]] = []
    for s in strategies:
        key = f"{s['strategy_id']}:{s['version']}"
        m = s.get("backtest_summary") or {}
        val = s.get("validation_summary") or {}
        checks = val.get("criteria_checks") or {}
        passed_gates = sum(1 for v in checks.values() if v)
        total_gates = len(checks) if checks else 9

        p = paper_stats.get(
            key, {"closed": 0, "wins": 0, "gross_win": 0.0, "gross_loss": 0.0, "realised": 0.0, "unrealised": 0.0}
        )
        closed = p["closed"]
        net_paper = round(p["realised"] + p["unrealised"], 2)
        paper_pf = (
            p["gross_win"] / p["gross_loss"]
            if p["gross_loss"] > 0
            else (2.5 if p["gross_win"] > 0 else 0.0)
        )
        paper_wr = (p["wins"] / closed * 100.0) if closed > 0 else 0.0

        status = s["status"]
        if status == "REJECTED":
            readiness = "NOT READY — Failed Backtest Gates"
        elif status == "RETIRED":
            readiness = "RETIRED — Superseded by Newer Version"
        elif passed_gates == total_gates and closed >= min_paper_trades and paper_pf >= 1.3 and net_paper > 0:
            readiness = f"READY FOR LIVE REVIEW ({closed} paper trades, PF {paper_pf:.2f})"
        else:
            readiness = f"BUILDING PAPER TRACK RECORD ({closed} / {min_paper_trades} closed trades)"

        start_eq = 100_000.0
        final_eq = float(m.get("final_equity", start_eq))
        net_bt_profit = final_eq - start_eq

        rows.append(
            {
                "Strategy": f"{s['strategy_id']} v{s['version']}",
                "Name": s["name"],
                "Family": s["strategy_family"],
                "Status": status,
                "Backtest Gates": f"{passed_gates} / {total_gates} Passed",
                "Backtest Return (vs SPY)": f"{m.get('total_return_pct', 0.0):+.2f}% (SPY {m.get('benchmark_return_pct', 0.0):+.2f}%)",
                "Backtest Sharpe / PF": f"{m.get('sharpe_ratio', 0.0):.2f} / {m.get('profit_factor', 0.0):.2f}",
                "Backtest Max DD": f"-{m.get('max_drawdown_pct', 0.0):.2f}%",
                "Forward Paper Trades": f"{closed} closed",
                "Forward Paper P&L": f"${net_paper:+,.2f}" + (f" (WR {paper_wr:.0f}%, PF {paper_pf:.2f})" if closed > 0 else ""),
                "Live Trading Readiness": readiness,
                "_raw_strategy": s,
                "_checks": checks,
                "_bt_net_profit": net_bt_profit,
                "_paper_closed": closed,
                "_paper_net_pnl": net_paper,
                "_paper_pf": paper_pf,
                "_paper_wr": paper_wr,
            }
        )
    return rows


MENTAL_MODEL_HTML = """
<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:18px 20px;margin:10px 0 18px 0;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.06em;color:#94a3b8;margin-bottom:10px;">
    System Mental Model — 100% Autonomous Two-Loop Architecture (Zero User Input Required)
  </div>
  <div style="margin-bottom:14px;">
    <div style="font-size:0.84rem;font-weight:600;color:#38bdf8;margin-bottom:6px;">
      1. Daily Execution Loop (Mon–Fri at 21:30 UTC · Runs All Promoted Strategies in Parallel)
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;font-size:0.8rem;">
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #38bdf8;">
        <strong>Step 1 · Market Data</strong><br/><span style="color:#94a3b8;">Download daily prices &amp; earnings updates.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #38bdf8;">
        <strong>Step 2 · AI Research</strong><br/><span style="color:#94a3b8;">Rank liquid US stocks by trend &amp; catalysts.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #38bdf8;">
        <strong>Step 3 · Multi-Strategy Signals</strong><br/><span style="color:#94a3b8;">Check all approved strategies &amp; rank signals fairly.</span>
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
      2. Weekly Self-Improvement Loop (Saturdays at 10:00 SGT · Discovers &amp; Promotes Better Strategy Versions)
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;font-size:0.8rem;">
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #a855f7;">
        <strong>Step A · Review Trades</strong><br/><span style="color:#94a3b8;">Diagnose wins, losses &amp; current market regime.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #a855f7;">
        <strong>Step B · Draft Upgrade</strong><br/><span style="color:#94a3b8;">Create a candidate strategy version (v+1).</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #f59e0b;">
        <strong>Step C · 9-Gate Backtest</strong><br/><span style="color:#94a3b8;">Test across historical &amp; walk-forward periods.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #10b981;">
        <strong>Step D · Promote &amp; Retire Old</strong><br/><span style="color:#94a3b8;">If all 9 gates pass, v+1 goes live &amp; old version retires.</span>
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
        with st.spinner("Initializing market dataset, baseline strategies, and 60-day paper portfolio..."):
            app.orchestrator.bootstrap_baseline_system()
            spy_bars = app.orchestrator.market_data.get_bars("SPY")
            for b in spy_bars[-60:]:
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
    readiness_rows = _build_strategy_readiness_rows(strats, ledger, positions)
    ready_live_count = sum(1 for r in readiness_rows if r["Live Trading Readiness"].startswith("READY FOR LIVE REVIEW"))

    # Minimalist Autonomous Status Sidebar (No manual intervention required)
    with st.sidebar:
        st.markdown("### Autonomous Status")
        st.caption(f"Mode: **{acc['trading_mode'].upper()}** ($100,000 Virtual)")
        st.caption(f"Market Data: **{app.settings.market_data_provider.upper()}**")
        st.caption(f"Active Strategies: **{len(active_paper_strats)} running daily**")
        st.caption(f"Ready for Live Review: **{ready_live_count} strategy**")
        st.markdown("---")
        st.markdown("#### Automated Schedule")
        st.caption("**Daily Execution**: Mon–Fri, 21:30 UTC (after US market close)")
        st.caption("**Weekly Upgrade**: Saturday, 10:00 SGT (walk-forward discovery)")
        st.caption("**User Action Needed**: None (100% hands-off)")

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

    # Compact Executive Summary Expander
    status_label = (
        "Active"
        if not acc["kill_switch_engaged"]
        else f"Paused ({acc['kill_switch_reason']})"
    )
    with st.expander(
        f"System Snapshot — Equity: ${acc['total_equity']:,.2f} ({acc['total_return_pct']:+.2f}%) · "
        f"Active Strategies: {len(active_paper_strats)} · Ready for Live Review: {ready_live_count} · "
        f"Open Positions: {acc['open_positions_count']}/10",
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
            st.markdown("**Your Role (Zero Daily Input)**")
            st.write("- **Daily & Weekly**: Runs automatically on GitHub Actions.")
            st.write("- **When Ready for Real Trading**: Check the **Strategies & Readiness** tab for strategies marked `READY FOR LIVE REVIEW`.")

    tabs = st.tabs(
        [
            "Platform Guide",
            "Overview & P&L",
            "Strategies & Readiness",
            "Market Research",
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
            "It runs **100% automatically in the cloud**—you do not need to click any buttons or make daily decisions. "
            "**AI agents only research stocks and propose strategy upgrades**, while **strict mathematical code** "
            "tests those rules on historical data, enforces risk limits, and executes every trade."
        )

        # Visual Mental Model Diagram
        st.markdown(MENTAL_MODEL_HTML, unsafe_allow_html=True)

        # Interactive Step-by-Step Explorer
        st.markdown("##### Interactive Walkthrough — Click Any Question or Stage Below")
        if "walkthrough_step" not in st.session_state:
            st.session_state["walkthrough_step"] = "step_daily_vs_weekly"

        b1, b2, b3, b4, b5 = st.columns(5)
        if b1.button("1. Daily vs Weekly Run", use_container_width=True):
            st.session_state["walkthrough_step"] = "step_daily_vs_weekly"
        if b2.button("2. How Strategies Share Capital", use_container_width=True):
            st.session_state["walkthrough_step"] = "step_multi_strategy"
        if b3.button("3. Risk & Position Sizing", use_container_width=True):
            st.session_state["walkthrough_step"] = "step_risk"
        if b4.button("4. When to Trade Real Money", use_container_width=True):
            st.session_state["walkthrough_step"] = "step_readiness"
        if b5.button("5. What Is Needed From You", use_container_width=True):
            st.session_state["walkthrough_step"] = "step_user_role"

        step_info = {
            "step_daily_vs_weekly": (
                "**1. Daily Run vs. Weekly Run — What is the difference?**\n\n"
                "- **Daily Run (Mon–Fri after US Market Close)**: Executes the **currently approved strategies** (`PAPER_TRADING` status) on today's real market prices. It does *not* invent new rules—its job is to trade the approved rulebooks day after day to build a real-time paper track record.\n"
                "- **Weekly Run (Saturday 10:00 SGT)**: This is the **self-improvement engine**. It reviews the week's closed trades, drafts a refined strategy version (`v+1`), and tests it against the 9-gate historical & walk-forward exam. If `v+1` passes all 9 gates, it automatically replaces the older version (`RETIRED`)."
            ),
            "step_multi_strategy": (
                "**2. How Multiple Strategies Run Together Every Day**\n\n"
                "- The system starts with **3 baseline strategy families** (`Momentum Trend`, `Volatility Breakout`, and `Earnings Drift`) and tests all of them.\n"
                "- Every strategy that passes all 9 validation gates is set to **`PAPER_TRADING`** and runs **every single day**.\n"
                "- **Fair Signal Allocation**: When multiple strategies trigger buy signals on the same day, the execution engine interleaves signals across strategy families by conviction score so no single strategy hogs the portfolio's cash or sector limits."
            ),
            "step_risk": (
                "**3. Position Sizing & 7 Risk Guardrails (`PortfolioRiskManager`)**\n\n"
                "- **1.0% Risk Per Trade**: Share size is calculated from stock volatility (`ATR`) so that if a stock hits its stop-loss, the portfolio loses at most `~1.0%` (`$1,000` on `$100,000`).\n"
                "- **Portfolio Caps**: Max `5.0%` combined open stop-loss risk across all positions, max `15.0%` in one stock, max `30.0%` in one sector, max `10` open positions, and an automatic `15.0%` drawdown circuit breaker."
            ),
            "step_readiness": (
                "**4. How to Evaluate a Strategy for Real-Money Trading**\n\n"
                "Open the **Strategies & Readiness** tab. A strategy is flagged **`READY FOR LIVE REVIEW`** only when it proves itself in **both** historical testing and live forward paper trading:\n"
                "1. **9 / 9 Backtest & Walk-Forward Gates Passed** (Sharpe $\\ge 1.0$, Profit Factor $\\ge 1.3$, Max Drawdown $\\le 15\\%$, profitable after $2\\times$ fees).\n"
                "2. **At least 20 Closed Forward Paper Trades** (proving the edge works in live daily market conditions, not just past history).\n"
                "3. **Forward Paper Profit Factor $\\ge 1.30$** and **Positive Net Paper P&L** after brokerage commissions and slippage."
            ),
            "step_user_role": (
                "**5. What Exactly Is Needed From You?**\n\n"
                "- **Day-to-Day / Week-to-Week**: **Nothing (`0` user input).** Data ingestion, daily paper trading, and Saturday strategy discovery all run automatically in the background.\n"
                "- **Periodic Check-In (Whenever You Like)**: Glance at the **Strategies & Readiness** tab. Once a strategy reaches `READY FOR LIVE REVIEW` and you are comfortable with its drawdown and trade history, you can mirror its signals in your personal brokerage account."
            ),
        }
        st.info(step_info[st.session_state["walkthrough_step"]])

        st.markdown("##### Deeper Dives — Expand Any Topic Below")
        with st.expander("The 3 Strategy Families — How buy and sell signals work"):
            st.markdown(
                """
                1. **Momentum & Relative Strength (`strat_momentum_trend`)** — Buys liquid stocks in established uptrends (above 20d and 50d moving averages) that are outperforming the S&P 500 (`SPY`) with strong volume. Held for 4–12 trading days.
                2. **Volatility Breakout (`strat_volatility_breakout`)** — Identifies stocks that consolidate quietly in a tight 10-day range and then break above their 20-day high on 1.35x normal volume. Held for 3–12 trading days.
                3. **Post-Earnings Drift (`strat_pead_drift`)** — Captures multi-day follow-through after a company beats quarterly earnings and revenue estimates with a volume surge. Held for 3–10 trading days.
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
                  $$\\text{Current Equity} = \\text{Starting Capital (\\$100,000)} + \\text{Realised P\\&L (Closed Trades)} + \\text{Unrealised P\\&L (Open Positions)}$$
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
            "Overview & P&L: Real-time simulated portfolio value, multi-strategy attribution, and currently held positions.",
            "How this tab works",
            "**What this tab shows:** Your simulated `$100,000` paper trading account.\n\n"
            "- **Realised P&L**: Profit or loss locked in from completed (closed) trades after subtracting commissions and slippage.\n"
            "- **Unrealised P&L**: Floating profit or loss on stocks currently held, based on the latest market close price.\n"
            "- **Strategy Attribution Table**: Shows every strategy that has traded in the paper account, its win rate, profit factor, date span, and exact P&L contribution.",
        )

        st.markdown("#### Paper Portfolio Profit & Loss Attribution")
        st.markdown(
            f"""
            - **Active Daily Strategies**: {active_strat_names}
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
    # TAB 2: STRATEGIES & LIVE READINESS SCORECARD
    # =========================================================================
    with tabs[2]:
        _render_tab_header(
            st,
            "Strategies & Readiness: Side-by-side scorecard comparing 9-gate historical backtests with forward paper-trading proof to tell you when a strategy is ready for real trading.",
            "How to evaluate readiness",
            "**How to know when a strategy is ready for real money:**\n\n"
            "1. **Backtest Gates (`9 / 9 Passed`)**: Proves the strategy survived multi-year historical data, walk-forward windows, and $2\\times$ cost stress tests.\n"
            "2. **Forward Paper Trades (`>= 20 Closed Trades`)**: Proves the strategy works in live day-by-day market conditions.\n"
            "3. **Forward Profit Factor (`>= 1.30`) & Positive P&L**: Proves winning paper trades outweigh losing paper trades by at least $1.30 to $1.00 after fees.\n"
            "When all criteria are met, **Live Trading Readiness** turns **`READY FOR LIVE REVIEW`**.",
        )

        st.markdown("#### Strategy Evaluation & Live-Trading Readiness Scorecard")
        display_scorecard = [
            {k: v for k, v in r.items() if not k.startswith("_")}
            for r in readiness_rows
        ]
        st.dataframe(display_scorecard, use_container_width=True)

        st.markdown("#### Expand Any Strategy for Its 9-Gate Audit & Rulebook Details")
        for r in readiness_rows:
            s = r["_raw_strategy"]
            checks = r["_checks"]
            header_label = (
                f"{r['Strategy']} — {r['Name']}  ·  Status: {r['Status']}  ·  "
                f"Backtest: {r['Backtest Gates']}  ·  Readiness: {r['Live Trading Readiness']}"
            )
            with st.expander(header_label, expanded=False):
                c_left, c_right = st.columns(2)
                with c_left:
                    st.markdown("**1. Historical Backtest Audit (9 Promotion Gates)**")
                    if checks:
                        for gate_name, passed in checks.items():
                            icon = "PASS" if passed else "FAIL"
                            clean_gate = gate_name.replace("_", " ").title()
                            st.write(f"- **[{icon}]** {clean_gate}")
                    else:
                        st.write(s.get("promotion_decision_reason", "No gate breakdown recorded."))
                with c_right:
                    st.markdown("**2. Forward Paper-Trading Readiness Checklist**")
                    g1_ok = r["Backtest Gates"].startswith("9 / 9")
                    g2_ok = r["_paper_closed"] >= 20
                    g3_ok = r["_paper_pf"] >= 1.3 and r["_paper_closed"] > 0
                    g4_ok = r["_paper_net_pnl"] > 0
                    st.write(f"- **[{'PASS' if g1_ok else 'WAIT'}]** Passed all 9 historical backtest gates (`{r['Backtest Gates']}`)")
                    st.write(f"- **[{'PASS' if g2_ok else 'WAIT'}]** Minimum 20 closed paper trades (`{r['_paper_closed']} / 20 completed`)")
                    st.write(f"- **[{'PASS' if g3_ok else 'WAIT'}]** Forward Paper Profit Factor $\\ge 1.30$ (`Current: {r['_paper_pf']:.2f}`)")
                    st.write(f"- **[{'PASS' if g4_ok else 'WAIT'}]** Positive Forward Net Paper P&L (`Current: ${r['_paper_net_pnl']:+,.2f}`)")
                    st.caption(f"**Hypothesis**: {s['hypothesis']}")

    # =========================================================================
    # TAB 3: MARKET RESEARCH
    # =========================================================================
    with tabs[3]:
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
            "Paper Ledger: Chronological log of every simulated buy/sell fill across all active strategies, transaction fees, and resulting cash balance.",
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
