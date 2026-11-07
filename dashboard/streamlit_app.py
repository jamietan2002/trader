"""Streamlit Community Cloud & Local Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

Minimalist, institutional-grade layout using clear, plain-English explanations without jargon:
- Includes a clean "System Architecture & Guide" tab with interactive module selectors.
- Provides concise context headers at the top of every tab.
- Presents Profit & Loss (P&L) with complete transparency: explicitly stating the Strategy Used,
  Exact Date Span, and step-by-step accounting formula (`Starting Capital + Realised P&L + Unrealised P&L = Total Equity`),
  strictly separated from multi-year historical backtest simulations.
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
        if st.button("Run Daily Session", use_container_width=True):
            app.orchestrator.run_daily_workflow(latest_bar_dt, force=True)
            st.rerun()
        if st.button("Run Weekly Strategy Discovery", use_container_width=True):
            app.orchestrator.run_weekly_workflow(latest_bar_dt, force=True)
            st.rerun()
        if acc["kill_switch_engaged"]:
            st.markdown("---")
            if st.button("Reset Paper Account ($100k)", use_container_width=True):
                app.orchestrator.paper_engine.reset_account_to_starting_capital()
                st.rerun()

    st.title("Swing Trading AI")
    st.caption(
        "Autonomous US Equities Research, Statistical Validation, and Paper-Trading Platform • Benchmark: SPY"
    )

    # Executive Weekly Summary Banner
    with st.expander("Executive Weekly Summary (Operator Briefing)", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Portfolio & Risk Status**")
            status_label = (
                "Active — Normal Operation"
                if not acc["kill_switch_engaged"]
                else f"Trading Paused — {acc['kill_switch_reason']}"
            )
            st.write(f"- **System State**: {status_label}")
            st.write(f"- **Drawdown from Peak**: `-{acc['current_drawdown_pct']:.2f}%` (Hard Stop Limit: `15.0%`)")
            st.write(f"- **Active Holdings**: `{acc['open_positions_count']} / 10` maximum positions")
        with c2:
            st.markdown("**Paper Portfolio Accounting**")
            st.write(f"- **Date Span**: `{paper_date_span}`")
            st.write(
                f"- **Valuation**: `${acc['starting_capital']:,.2f}` (Start) "
                f"+ `${acc['realised_pnl']:+,.2f}` (Closed) "
                f"+ `${acc['unrealised_pnl']:+,.2f}` (Open) "
                f"= **`${acc['total_equity']:,.2f}`**"
            )
            st.write(f"- **Active Strategies**: `{len(active_paper_strats)}` promoted (`{len(rejected_strats)}` rejected)")
        with c3:
            st.markdown("**Operator Schedule**")
            st.write("- **Weekdays (21:30 UTC)**: Automated market scan, signal execution, and P&L reconciliation.")
            st.write("- **Saturdays (10:00 SGT)**: Automated hypothesis testing and walk-forward validation.")

    tabs = st.tabs(
        [
            "Overview & P&L",
            "Market Research",
            "Strategies",
            "Backtesting",
            "Paper Ledger",
            "Risk & Analytics",
            "System Logs",
            "Platform Guide",
        ]
    )

    # =========================================================================
    # TAB 1: OVERVIEW & TRANSPARENT P&L BREAKDOWN
    # =========================================================================
    with tabs[0]:
        st.caption(
            "Overview: Tracks real-time simulated paper trading performance from $100,000 starting capital, net of brokerage commissions and bid-ask slippage."
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
        k1.metric("Total Equity", f"${acc['total_equity']:,.2f}", f"{net_dollar_pnl:+,.2f} ({acc['total_return_pct']:+.2f}%)")
        k2.metric("Starting Capital", f"${acc['starting_capital']:,.2f}")
        k3.metric("Realised P&L (Closed)", f"${acc['realised_pnl']:+,.2f}", f"Net of ${total_fees_paid:,.2f} costs")
        k4.metric("Unrealised P&L (Open)", f"${acc['unrealised_pnl']:+,.2f}", f"{acc['open_positions_count']} positions")
        k5.metric("Available Cash", f"${acc['cash_balance']:,.2f}", f"Drawdown: -{acc['current_drawdown_pct']:.2f}%")

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
    with tabs[1]:
        st.caption(
            "Market Research: Daily multi-factor scan ranking liquid US equities by 20-day relative strength vs SPY, volume expansion, trend alignment, and earnings catalysts."
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
            "*Evidence Score reflects data completeness and indicator convergence; it is not a statistical probability of profit."
        )

        st.markdown("#### Post-Session Experiment Proposals")
        st.dataframe(state["proposals"], use_container_width=True)

    # =========================================================================
    # TAB 3: STRATEGIES
    # =========================================================================
    with tabs[2]:
        st.caption(
            "Strategies: Versioned rulebooks. Only strategies passing all 9 out-of-sample and risk-adjusted validation gates achieve PAPER_TRADING status."
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
    with tabs[3]:
        st.caption(
            "Backtesting: Chronological historical simulations (signals at Day T close execute at Day T+1 open with spread, slippage, and commissions). Strictly separated from live paper account balances."
        )
        st.markdown("#### Historical Backtest Experiments")
        for exp in state["experiments"][:6]:
            m = exp["metrics"]
            net_profit = float(m.get("final_equity", 100000.0)) - 100000.0
            title = (
                f"{exp['strategy_id']} v{exp['version']} ({exp['experiment_type']})  |  "
                f"Span: {exp['start_date']} → {exp['end_date']}  |  "
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
    with tabs[4]:
        st.caption(
            "Paper Ledger: Immutable audit trail of every simulated order fill, transaction fee, realised P&L, and post-trade cash balance."
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
    with tabs[5]:
        st.caption(
            "Risk & Analytics: Monitors portfolio concentration against hard limits (15% single-stock cap, 30% sector cap) and out-of-sample walk-forward stability."
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
    with tabs[6]:
        st.caption(
            "System Logs: Records idempotent daily/weekly workflow runs and PortfolioRiskManager trade vetoes."
        )
        st.markdown("#### Risk Vetoes & Alerts")
        if state["risk_alerts"]:
            st.dataframe(state["risk_alerts"], use_container_width=True)
        else:
            st.write("No risk alerts triggered.")

        st.markdown("#### Workflow Execution Log")
        st.dataframe(state["jobs"], use_container_width=True)

    # =========================================================================
    # TAB 8: PLATFORM GUIDE (INTERACTIVE REFERENCE)
    # =========================================================================
    with tabs[7]:
        st.caption(
            "Platform Guide: Concise reference explaining how the system researches, validates, sizes positions, and manages risk."
        )
        st.markdown("#### Interactive Architecture & Methodology Reference")
        if "guide_section" not in st.session_state:
            st.session_state["guide_section"] = "architecture"

        g1, g2, g3, g4, g5 = st.columns(5)
        if g1.button("1. Core Architecture", use_container_width=True):
            st.session_state["guide_section"] = "architecture"
        if g2.button("2. Strategy Families", use_container_width=True):
            st.session_state["guide_section"] = "strategies"
        if g3.button("3. Validation Gates", use_container_width=True):
            st.session_state["guide_section"] = "validation"
        if g4.button("4. Risk Controls", use_container_width=True):
            st.session_state["guide_section"] = "risk"
        if g5.button("5. P&L Accounting", use_container_width=True):
            st.session_state["guide_section"] = "accounting"

        sec = st.session_state["guide_section"]
        if sec == "architecture":
            st.markdown(
                """
                **Separation of AI Reasoning and Quantitative Execution**
                - **AI Agent Layer (`agents/`)**: Scans market data, summarizes catalysts, proposes testable strategy hypotheses (`StrategyConfig`), and reviews post-session trade attribution. Agents have zero direct access to order execution or account balances.
                - **Deterministic Core (`core/`)**: Computes causal technical indicators, evaluates entry/exit rules chronologically, enforces portfolio risk limits, and reconciles paper brokerage cash and positions.
                - **Autonomous Schedule**: GitHub Actions executes daily post-close workflows (Mon–Fri 21:30 UTC) and weekly strategy discovery & walk-forward validation (Saturday 10:00 SGT).
                """
            )
        elif sec == "strategies":
            st.markdown(
                """
                **Baseline Swing Strategy Archetypes (3–15 Trading Day Horizon)**
                1. **Momentum & Relative Strength (`strat_momentum_trend`)**: Enters liquid large-cap equities outperforming `SPY` over 20 days when price is aligned above the 20-day and 50-day moving averages on above-average volume.
                2. **Post-Earnings Announcement Drift (`strat_pead_drift`)**: Captures multi-day follow-through after positive quarterly EPS and revenue surprises accompanied by volume expansion.
                3. **Volatility Consolidation Breakout (`strat_volatility_breakout`)**: Identifies stocks breaking above their prior 20-day high following a low-volatility 10-day consolidation range.
                """
            )
        elif sec == "validation":
            st.markdown(
                """
                **9 Statistical Promotion Gates (`StrategyEvaluationAgent`)**
                Before any strategy is allowed to trade paper capital, it must pass all 9 criteria across historical In-Sample, Validation, and Out-of-Sample partitions:
                - Positive net Out-of-Sample return after transaction costs
                - Annualised Sharpe Ratio $\\ge 1.0$ and Profit Factor $\\ge 1.3$
                - Maximum Drawdown $\\le 15.0\\%$ and minimum 15 completed trades
                - At least $60\\%$ profitable folds in 4-window Walk-Forward validation
                - Positive net return under $2\\times$ stressed slippage and commission assumptions
                - No single outlier trade accounting for $>65\\%$ of total profit
                """
            )
        elif sec == "risk":
            st.markdown(
                """
                **Portfolio Risk Manager (`PortfolioRiskManager`)**
                Every proposed entry is sized using 14-day Average True Range (`ATR`) and checked against 7 hard limits:
                - **Risk Per Trade**: Capped at $1.0\\%$ of portfolio equity (`$1,000` risk on `$100,000`) based on entry-to-stop distance.
                - **Total Open Risk Cap (Portfolio Heat)**: Combined stop-loss risk across all simultaneously open positions cannot exceed $5.0\\%$ of portfolio equity.
                - **Single-Stock Cap**: Maximum $15.0\\%$ of portfolio equity in any single company.
                - **Sector Cap**: Maximum $30.0\\%$ of portfolio equity in any single GICS sector.
                - **Position Count**: Maximum 10 concurrent open positions.
                - **Correlation & Liquidity**: Blocks entries with $>0.80$ 20-day return correlation to existing holdings or $<\\$20\\text{M}$ average daily dollar volume.
                - **Drawdown Circuit Breaker**: Warning logged at $10.0\\%$ drawdown; new entries automatically suspended at $15.0\\%$ portfolio drawdown.
                """
            )
        elif sec == "accounting":
            st.markdown(
                """
                **Transparent P&L Accounting**
                - **Paper Portfolio P&L (Tab 1 & Tab 5)**: Tracks chronological simulated orders starting from `$100,000.00`. Every fill deducts half-spread (`2.5 bps`), market impact slippage (`3.0 bps`), and per-share commissions (`$0.005/sh`, min `$1.00`).
                - **Historical Backtest P&L (Tab 3 & Tab 4)**: Evaluates how a strategy rulebook performed over multi-year historical data (`2023–2025`) vs. the `SPY` benchmark. Backtest results never alter paper account cash or equity.
                """
            )


if __name__ == "__main__":
    main()
