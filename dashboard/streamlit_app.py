"""Streamlit Community Cloud & Local Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

Provides:
- A "Weekly Operator Digest & Self-Improvement Summary" banner at the top so the operator
  can review the entire platform's health, active paper trades, and AI-discovered strategy
  promotions in under 2 minutes per week.
- Interactive controls to trigger Daily Sessions, Weekly AI Strategy Discovery, and Custom Backtests.
- Full 7-Tab Quantitative Dashboard (Overview, Research, Strategies, Backtesting, Paper Trading,
  Analytics, System Monitoring).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root is on sys.path when Streamlit runs `dashboard/streamlit_app.py`
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.server import PlatformApplication
from core.market_data.models import USTradingCalendar


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
        page_title="Swing Trading AI — Autonomous Research & Paper Trading",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    app = PlatformApplication()
    # Auto-bootstrap if database is fresh on Streamlit Cloud
    if not app.orchestrator.registry.list_strategies():
        with st.spinner("Bootstrapping historical US equities, 3 baseline strategies, and paper sessions..."):
            app.orchestrator.bootstrap_baseline_system()
            for dt in USTradingCalendar.get_trading_days("2025-05-01", "2025-05-20"):
                app.orchestrator.run_daily_workflow(dt)
            app.orchestrator.run_weekly_workflow("2025-05-20", force=True)

    state = app.get_dashboard_state()
    acc = state["account"]
    strats = state["strategies"]
    active_paper_strats = [s for s in strats if s["status"] == "PAPER_TRADING"]
    rejected_strats = [s for s in strats if s["status"] == "REJECTED"]

    # Sidebar Controls
    with st.sidebar:
        st.header("Autonomous Controls")
        st.success(f"Mode: {acc['trading_mode'].upper()} ($100k Virtual)")
        st.caption(f"Data Provider: `{app.settings.market_data_provider}`")
        st.caption(f"Reporting TZ: `{app.settings.operator_timezone}`")
        if st.button("Run Daily Session Now", use_container_width=True):
            app.orchestrator.run_daily_workflow("2025-06-27", force=True)
            st.rerun()
        if st.button("Run Weekly AI Discovery Now", use_container_width=True):
            app.orchestrator.run_weekly_workflow("2025-06-27", force=True)
            st.rerun()

    st.title("Swing Trading AI — Autonomous Research & Paper-Trading Platform")

    # Weekly Operator Digest Banner (2-Minute Weekly Check-in)
    with st.expander("📋 Weekly Operator Digest & Self-Improvement Status (2-Minute Check-In)", expanded=True):
        d1, d2, d3 = st.columns(3)
        with d1:
            st.markdown("#### 1. Portfolio & Risk Health")
            kill_status = "🟢 STANDBY (Healthy)" if not acc["kill_switch_engaged"] else f"🔴 ENGAGED ({acc['kill_switch_reason']})"
            st.write(f"- **Kill Switch**: {kill_status}")
            st.write(f"- **Total Equity**: `${acc['total_equity']:,.2f}` (`{acc['total_return_pct']:+.2f}%`)")
            st.write(f"- **Current Drawdown**: `-{acc['current_drawdown_pct']:.2f}%` (Limit: `15.0%`)")
        with d2:
            st.markdown("#### 2. Self-Improving Strategy Loop")
            st.write(f"- **Active Paper Strategies**: `{len(active_paper_strats)}` promoted")
            st.write(f"- **Rejected Weak Hypotheses**: `{len(rejected_strats)}` filtered out")
            if active_paper_strats:
                latest_s = active_paper_strats[0]
                st.write(f"- **Latest Promoted**: `{latest_s['strategy_id']} v{latest_s['version']}`")
        with d3:
            st.markdown("#### 3. Operator Action Required")
            if acc["kill_switch_engaged"]:
                st.error("Action Needed: Review drawdown alerts in Tab 7 before resetting kill switch.")
            else:
                st.info(
                    "Zero intervention needed! GitHub Actions automatically runs daily paper execution "
                    "and weekly strategy discovery/walk-forward validation."
                )

    # Top KPI Metrics
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Portfolio Equity", f"${acc['total_equity']:,.2f}", f"{acc['total_return_pct']:+.2f}%")
    col2.metric("Available Cash", f"${acc['cash_balance']:,.2f}")
    col3.metric("Realised P&L", f"${acc['realised_pnl']:+,.2f}")
    col4.metric("Unrealised P&L", f"${acc['unrealised_pnl']:+,.2f}")
    col5.metric("Open Positions", f"{acc['open_positions_count']} / 10")
    col6.metric("Current Drawdown", f"-{acc['current_drawdown_pct']:.2f}%")

    tabs = st.tabs(
        [
            "1. Overview",
            "2. Market Research",
            "3. Strategy Registry",
            "4. Backtesting Engine",
            "5. Paper Trading",
            "6. Portfolio Analytics",
            "7. System Monitoring",
        ]
    )

    with tabs[0]:
        st.subheader("Current Open Positions")
        if state["positions"]:
            st.dataframe(state["positions"], use_container_width=True)
        else:
            st.info("No open positions currently held.")
        st.subheader("Daily Portfolio Valuation History")
        st.dataframe(state["snapshots"], use_container_width=True)

    with tabs[1]:
        st.subheader("Ranked US Equity Swing Candidates")
        reports_summary = [
            {
                "Ticker": r["ticker"],
                "Company": r["company_name"],
                "Price": f"${r['current_price']:.2f}",
                "Sector": r["market_and_sector_context"]["sector"],
                "20d RS vs SPY (%)": r["relative_strength_vs_spy_20d"],
                "Vol Ratio": r["volume_analysis"]["volume_ratio_20"],
                "Suggested Family": r["suggested_strategy_family"],
                "Rank Score": r["composite_rank_score"],
                "Research Confidence (Not Profit Prob)": r["research_confidence_score"],
                "Bullish Thesis": r["bullish_thesis"],
            }
            for r in state["research_reports"]
        ]
        st.dataframe(reports_summary, use_container_width=True)
        st.subheader("Performance Analyst Experiment Proposals")
        st.dataframe(state["proposals"], use_container_width=True)

    with tabs[2]:
        st.subheader("Versioned Strategy Registry & Promotion Audit")
        strat_rows = [
            {
                "Strategy ID": s["strategy_id"],
                "Version": f"v{s['version']}",
                "Name": s["name"],
                "Family": s["strategy_family"],
                "Status": s["status"],
                "Hold (Days)": f"{s['holding_period_min_days']}-{s['holding_period_max_days']}d",
                "Sharpe": (s["backtest_summary"] or {}).get("sharpe_ratio"),
                "Profit Factor": (s["backtest_summary"] or {}).get("profit_factor"),
                "Total Return (%)": (s["backtest_summary"] or {}).get("total_return_pct"),
                "Max DD (%)": (s["backtest_summary"] or {}).get("max_drawdown_pct"),
                "Audit Decision": s["promotion_decision_reason"],
            }
            for s in strats
        ]
        st.dataframe(strat_rows, use_container_width=True)

    with tabs[3]:
        st.subheader("Backtest & Out-of-Sample Experiment History")
        for exp in state["experiments"][:5]:
            with st.expander(
                f"{exp['experiment_id']} — {exp['strategy_id']} v{exp['version']} ({exp['experiment_type']}) | "
                f"Return: {exp['metrics'].get('total_return_pct'):+.2f}%, Sharpe: {exp['metrics'].get('sharpe_ratio'):.2f}",
                expanded=False,
            ):
                st.json(exp["metrics"])
                st.markdown("**Simulated Trades (Sample)**")
                st.dataframe(exp["trades"][:25], use_container_width=True)

    with tabs[4]:
        st.subheader("Permanent Trade Ledger")
        st.dataframe(state["trade_ledger"], use_container_width=True)
        st.subheader("Order History (Idempotent)")
        st.dataframe(state["orders"], use_container_width=True)

    with tabs[5]:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Sector Exposure (%) vs 30% Cap")
            st.json(acc["sector_exposures_pct"])
        with c2:
            st.subheader("Walk-Forward Validation Windows")
            if strats and strats[0].get("validation_summary"):
                st.dataframe(
                    (strats[0]["validation_summary"].get("walk_forward") or {}).get("windows", []),
                    use_container_width=True,
                )

    with tabs[6]:
        st.subheader("Autonomous Workflow & Job Execution History")
        st.dataframe(state["jobs"], use_container_width=True)
        st.subheader("Portfolio Risk Alerts & Veto Audit Log")
        st.dataframe(state["risk_alerts"], use_container_width=True)


if __name__ == "__main__":
    main()
