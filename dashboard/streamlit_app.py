"""Streamlit Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

Also supports embedded HTML rendering when running standalone via `python3 main.py serve`.
"""

from __future__ import annotations

from api.server import PlatformApplication
from dashboard.ui_template import DASHBOARD_HTML


def main() -> None:
    try:
        import streamlit as st
        import streamlit.components.v1 as components
    except ImportError:
        print(
            "Streamlit is not installed in the current environment. "
            "Run `python3 main.py serve` to launch the built-in interactive web dashboard on http://127.0.0.1:8080."
        )
        return

    st.set_page_config(
        page_title="Swing Trading AI Platform",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    app = PlatformApplication()
    if not app.orchestrator.registry.list_strategies():
        app.orchestrator.bootstrap_baseline_system()
        for dt in ("2025-06-25", "2025-06-26", "2025-06-27"):
            app.orchestrator.run_daily_workflow(dt)

    state = app.get_dashboard_state()
    acc = state["account"]

    st.title("Swing Trading AI — Systematic Research & Paper-Trading Platform")
    st.caption(
        f"TRADING_MODE={acc['trading_mode'].upper()} | Starting Capital: ${acc['starting_capital']:,.2f} | "
        f"Benchmark: SPY | Reporting TZ: {app.settings.operator_timezone}"
    )

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Portfolio Equity", f"${acc['total_equity']:,.2f}", f"{acc['total_return_pct']:+.2f}%")
    col2.metric("Available Cash", f"${acc['cash_balance']:,.2f}")
    col3.metric("Realised P&L", f"${acc['realised_pnl']:+,.2f}")
    col4.metric("Open Positions", f"{acc['open_positions_count']} / 10")
    col5.metric("Current Drawdown", f"-{acc['current_drawdown_pct']:.2f}%")

    tabs = st.tabs(
        [
            "1. Overview",
            "2. Research",
            "3. Strategies",
            "4. Backtesting",
            "5. Paper Trading",
            "6. Analytics",
            "7. System Monitoring",
        ]
    )
    with tabs[0]:
        st.subheader("Open Positions")
        st.dataframe(state["positions"])
        st.subheader("Daily Snapshots")
        st.dataframe(state["snapshots"])
    with tabs[1]:
        st.subheader("Ranked Stock Candidates & Research Reports")
        st.dataframe(state["research_reports"])
        st.subheader("Experiment Proposals")
        st.dataframe(state["proposals"])
    with tabs[2]:
        st.subheader("Strategy Registry")
        st.dataframe(state["strategies"])
    with tabs[3]:
        st.subheader("Backtest Experiments")
        for exp in state["experiments"][:3]:
            st.markdown(f"**{exp['experiment_id']}** (`{exp['strategy_id']}` v{exp['version']})")
            st.json(exp["metrics"])
    with tabs[4]:
        st.subheader("Permanent Trade Ledger")
        st.dataframe(state["trade_ledger"])
    with tabs[5]:
        st.subheader("Sector Exposures (%)")
        st.json(acc["sector_exposures_pct"])
    with tabs[6]:
        st.subheader("Job Execution History")
        st.dataframe(state["jobs"])
        st.subheader("Risk Alerts")
        st.dataframe(state["risk_alerts"])


if __name__ == "__main__":
    main()

