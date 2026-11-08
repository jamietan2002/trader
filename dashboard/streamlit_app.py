"""Streamlit Community Cloud & Local Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

Minimalist, institutional-grade layout with top-of-mind operator hierarchy:
1. Live Copilot (Real Account) — Today's trading-day-aware action checklist, 1-click confirmations, and real account shadow ledger.
2. Paper Account & Ledger — Forward $100,000 paper portfolio (Daily, Weekly, Total P&L) and day-filtered execution ledger.
3. Strategies, Rules & Backtests — Unified hub for how every strategy is conceived, its exact entry/exit rules, 9-gate SPY benchmark audit, historical backtest trade logs, and 1-click Golden Base (v1) revert.
4. AI Research & IDE Bridge — Daily watchlist, post-session proposals, IDE AI reminder checklist, and direct JSON feed bridge (`apply_ide_ai_cycle`).
5. Risk, Walk-Forward & Logs — Sector concentration vs. 30% cap, 4-window Walk-Forward folds, risk vetoes, and job logs.
6. Platform Guide — Visual mental-model diagram, interactive walkthrough, and expandable deep dives.
"""

from __future__ import annotations

import json
import sys
from datetime import date
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
        oos = val.get("oos_metrics") or {}
        wf = val.get("walk_forward") or {}
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
        beats_spy_full = float(m.get("total_return_pct", 0.0)) >= float(m.get("benchmark_return_pct", 0.0))
        beats_spy_oos = float(oos.get("total_return_pct", 0.0)) >= float(oos.get("benchmark_return_pct", 0.0))
        if status == "REJECTED":
            readiness = "NOT READY — Failed Backtest Gates"
        elif status == "RETIRED":
            readiness = "RETIRED — Superseded or Reverted"
        elif passed_gates == total_gates and closed >= min_paper_trades and paper_pf >= 1.3 and net_paper > 0:
            readiness = f"READY FOR LIVE REVIEW ({closed} paper trades, PF {paper_pf:.2f})"
        elif passed_gates == total_gates and beats_spy_full and beats_spy_oos:
            readiness = f"GOLDEN BASE READY (Beats SPY Full & OOS · {closed}/{min_paper_trades} paper trades)"
        else:
            readiness = f"BUILDING PAPER TRACK RECORD ({closed} / {min_paper_trades} closed trades)"

        start_eq = 100_000.0
        final_eq = float(m.get("final_equity", start_eq))
        net_bt_profit = final_eq - start_eq

        rows.append(
            {
                "Strategy": f"{s['strategy_id']} v{s['version']}" + (" ★ Base" if int(s["version"]) == 1 else ""),
                "Name": s["name"],
                "Family": s["strategy_family"],
                "Status": status,
                "Gates": f"{passed_gates} / {total_gates} Passed",
                "Full Return (vs SPY)": (
                    f"{m.get('total_return_pct', 0.0):+.2f}% "
                    f"(SPY {m.get('benchmark_return_pct', 0.0):+.2f}% · α {m.get('excess_return_vs_spy_pct', 0.0):+.2f}%)"
                ),
                "OOS Return (vs SPY)": (
                    f"{oos.get('total_return_pct', 0.0):+.2f}% "
                    f"(SPY {oos.get('benchmark_return_pct', 0.0):+.2f}%)"
                ),
                "Recent 6M (vs SPY & WR)": (
                    f"{m.get('recent_6m_return_pct', 0.0):+.2f}% "
                    f"(α {m.get('recent_6m_excess_vs_spy_pct', 0.0):+.2f}% · WR {m.get('recent_6m_win_rate_pct', m.get('win_rate_pct', 0.0)):.0f}%)"
                ),
                "SQN / Payoff / Win%": (
                    f"SQN {m.get('sqn_score', 0.0):.2f} · "
                    f"{m.get('payoff_ratio', 1.5):.2f}x · "
                    f"{m.get('win_rate_pct', 0.0):.0f}%"
                ),
                "Sharpe / PF / WF": (
                    f"{m.get('sharpe_ratio', 0.0):.2f} / {m.get('profit_factor', 0.0):.2f} / "
                    f"{float(wf.get('consistency_ratio', 0.0))*100:.0f}%"
                ),
                "Max DD / Ulcer": (
                    f"-{m.get('max_drawdown_pct', 0.0):.2f}% "
                    f"(UI {m.get('ulcer_index', 0.0):.2f})"
                ),
                "Forward Paper": f"{closed} trades (${net_paper:+,.0f})",
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


STRATEGY_GENESIS_BY_FAMILY: Dict[str, Dict[str, str]] = {
    "MOMENTUM_TREND": {
        "origin": "Cross-sectional intermediate-horizon relative strength (Jegadeesh & Titman) combined with dual moving-average trend alignment.",
        "edge": "Institutional fund accumulation occurs over multi-week cycles; stocks trading above rising 20d/50d SMAs that outperform SPY over 20 days with volume expansion continue drifting higher over 4–14 day swing windows.",
        "regime": "Bull & steady uptrend regimes (`SPY > SMA50`).",
    },
    "PEAD": {
        "origin": "Post-Earnings Announcement Drift (`PEAD`, Ball & Brown / Bernard & Thomas) with strict point-in-time (`BMO`/`AMC`) visibility.",
        "edge": "Analysts and institutional committees under-react to major quarterly EPS/revenue beats accompanied by volume surges, creating a multi-day upward drift.",
        "regime": "Earnings season across all non-crash market regimes.",
    },
    "BREAKOUT": {
        "origin": "Volatility Contraction Pattern (`VCP`) and 20-day Donchian channel breakout with institutional volume confirmation.",
        "edge": "When a leading stock consolidates in a tight 10-day range (`<= 14%`) and breaks above its prior 20-day high on `>= 1.1x` volume, overhead supply is exhausted and rapid price expansion follows.",
        "regime": "Transition from consolidation to expansion (`SPY > SMA50`).",
    },
    "MEAN_REVERSION": {
        "origin": "Short-horizon institutional value-zone pullback inside a primary structural uptrend (`Close > SMA200` and `SPY > SMA50`).",
        "edge": "Liquid leaders experiencing temporary 3-to-5 day pullbacks (`RSI < 55` or near `SMA20` / Lower Bollinger Band) attract dip-buying liquidity and revert toward their upper trend channel.",
        "regime": "Rotational bull and sideways-up markets.",
    },
    "SECTOR_ROTATION": {
        "origin": "Top-Down GICS Sector Relative Strength Leadership paired with bottom-up stock momentum.",
        "edge": "Over 60% of intermediate equity movement is driven by sector-level institutional rotation; buying the strongest stocks inside the #1 and #2 ranked sectors captures concentrated institutional inflows.",
        "regime": "Sector-led bull and macro-rotation markets.",
    },
}


MENTAL_MODEL_HTML = """
<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:18px 20px;margin:10px 0 18px 0;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.06em;color:#94a3b8;margin-bottom:10px;">
    System Mental Model — 100% Autonomous Two-Loop Architecture + IDE AI Alpha Booster
  </div>
  <div style="margin-bottom:14px;">
    <div style="font-size:0.84rem;font-weight:600;color:#38bdf8;margin-bottom:6px;">
      1. Daily Execution Loop (Mon–Fri at 21:30 UTC · Or Type "run" in Antigravity IDE)
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;font-size:0.8rem;">
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #38bdf8;">
        <strong>Step 1 · Market Data</strong><br/><span style="color:#94a3b8;">Download daily prices &amp; point-in-time earnings.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #38bdf8;">
        <strong>Step 2 · AI Research</strong><br/><span style="color:#94a3b8;">Rank liquid US stocks by trend &amp; live catalysts.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #38bdf8;">
        <strong>Step 3 · Multi-Strategy Signals</strong><br/><span style="color:#94a3b8;">Evaluate 5 Golden Base models &amp; interleave signals.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #10b981;">
        <strong>Step 4 · Risk Gate</strong><br/><span style="color:#94a3b8;">Size trade (1% risk) &amp; verify 7 safety caps.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #10b981;">
        <strong>Step 5 · Copilot &amp; Paper</strong><br/><span style="color:#94a3b8;">Update Paper Ledger &amp; Real-Account Copilot Plan.</span>
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
        <strong>Step C · 9-Gate + SPY Exam</strong><br/><span style="color:#94a3b8;">Must beat SPY &amp; incumbent champion in OOS &amp; WF.</span>
      </div>
      <div style="background:#1e293b;padding:10px 12px;border-radius:6px;border-left:3px solid #10b981;">
        <strong>Step D · Promote or Revert</strong><br/><span style="color:#94a3b8;">Promote v+1 if superior; revert to v1 Golden Base anytime.</span>
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
            with st.popover(f"? {guide_title}", width="stretch"):
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
        page_title="Swing Trading AI — Systematic Research, Copilot & Paper Portfolio",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    app = PlatformApplication()
    _code_version = "2026-11-08-v13"
    import api.server as _srv_mod
    if (
        getattr(_srv_mod, "_STREAMLIT_SYNC_VERSION", None) != _code_version
        or not hasattr(app.orchestrator, "live_copilot")
    ):
        import importlib

        _ordered_modules = [
            "infrastructure.configuration.settings",
            "infrastructure.database.db",
            "core.market_data.models",
            "core.market_data.providers",
            "core.indicators.technical",
            "evaluation.metrics.performance",
            "core.strategies.registry",
            "core.risk.manager",
            "core.backtesting.engine",
            "core.execution.paper_broker",
            "agents.base",
            "agents.market_researcher.agent",
            "agents.strategy_architect.agent",
            "agents.strategy_evaluator.agent",
            "agents.performance_analyst.agent",
            "agents.risk_manager.agent",
            "infrastructure.scheduler.orchestrator",
            "api.server",
        ]
        for _mod_name in _ordered_modules:
            if _mod_name in sys.modules:
                importlib.reload(sys.modules[_mod_name])
        import api.server as _srv_mod
        import core.execution.paper_broker as _pb_mod

        setattr(_srv_mod, "_STREAMLIT_SYNC_VERSION", _code_version)
        app = _srv_mod.PlatformApplication()
        app.db.initialize_schema()
        if not hasattr(app.orchestrator, "live_copilot"):
            app.orchestrator.live_copilot = _pb_mod.LiveTradingCopilotEngine(
                app.settings, app.db, app.orchestrator.market_data, app.orchestrator.risk_manager, app.orchestrator.registry
            )
    if not app.orchestrator.registry.list_strategies():
        with st.spinner("Initializing market dataset and baseline strategies (Backtesting only — Paper Account stays at $100k)..."):
            app.orchestrator.bootstrap_baseline_system()
            spy_bars = app.orchestrator.market_data.get_bars("SPY")
            if spy_bars:
                app.orchestrator.research_agent.run_market_scan(as_of_date=spy_bars[-1].bar_date)

    state = app.get_dashboard_state()
    acc = state["account"]
    strats = state["strategies"]
    snapshots = state["snapshots"]
    ledger = state["trade_ledger"]
    positions = state["positions"]
    jobs = state["jobs"]

    # Determine today's real calendar date and NYSE/NASDAQ market open status
    today_dt = date.today()
    today_iso = today_dt.isoformat()
    today_weekday_name = today_dt.strftime("%A")
    is_today_trading_day = USTradingCalendar.is_trading_day(today_dt)
    market_status_reason = USTradingCalendar.non_trading_reason(today_dt)
    next_trading_day_iso = USTradingCalendar.next_trading_day(today_dt, include_same_day=is_today_trading_day)

    # Check when the IDE AI Cycle (`ide_ai_cycle`) or Daily Workflow was last executed
    ide_jobs = [j for j in jobs if j.get("job_name") == "ide_ai_cycle"]
    last_ide_job = ide_jobs[0] if ide_jobs else None
    last_ide_run_ts = str(last_ide_job["completed_at"])[:16].replace("T", " ") if (last_ide_job and last_ide_job.get("completed_at")) else "Never run yet"
    ide_ran_today = bool(last_ide_job and str(last_ide_job.get("completed_at", "")).startswith(today_iso))

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
    net_dollar_pnl = round(float(acc.get("total_pnl_usd", float(acc["total_equity"]) - float(acc["starting_capital"]))), 2)
    daily_pnl_usd = float(acc.get("daily_pnl_usd", 0.0))
    daily_ret_pct = float(acc.get("daily_return_pct", 0.0))
    weekly_pnl_usd = float(acc.get("weekly_pnl_usd", 0.0))
    weekly_ret_pct = float(acc.get("weekly_return_pct", 0.0))
    readiness_rows = _build_strategy_readiness_rows(strats, ledger, positions)
    golden_ready_count = sum(
        1 for r in readiness_rows if "READY" in r["Live Trading Readiness"]
    )

    # Minimalist Autonomous Status & IDE AI Reminder Sidebar
    with st.sidebar:
        st.markdown("### Market & Calendar Status")
        if is_today_trading_day:
            st.success(f"**Today: `{today_iso}` ({today_weekday_name})**\n\n🟢 **NYSE / NASDAQ Trading Day**")
        else:
            st.warning(
                f"**Today: `{today_iso}` ({today_weekday_name})**\n\n"
                f"⏸️ **{market_status_reason}**\n\n"
                f"Next Market Open: **`{next_trading_day_iso}`**"
            )

        st.markdown("---")
        st.markdown("### Daily Routine (In Exact Order)")
        st.caption("Times shown in **US Eastern (`ET`)** & **Singapore (`SGT`)**:")
        st.checkbox(
            "Step 1 (Before 9:30 AM ET / 9:30 PM SGT): Optional — Type `run` in IDE",
            value=ide_ran_today,
            key="sidebar_chk_ide_run",
            help="Run BEFORE market open if you want live web news to veto negative-news traps (<= -0.35) or boost high-catalyst BUY setups. If you skip this, GitHub Actions already updated your checklist automatically at 5:30 AM SGT!",
        )
        st.checkbox(
            "Step 2 (9:30–9:35 AM ET / 9:30–9:35 PM SGT): Execute SELLs & Raise Stops First",
            value=False,
            key="sidebar_chk_sells_stops",
            help="Always execute SELL exits first to free up cash, and update any GTC Stop-Loss orders on holdings that reached +1R.",
        )
        st.checkbox(
            "Step 3 (9:30–9:45 AM ET or Pre-Set Limit): Place BUYs + Attach GTC Stop/Target",
            value=False,
            key="sidebar_chk_copilot",
            help="Either pre-submit a Regular-Hours Day Limit order at the Max Chase price (with attached GTC Stop-Loss & Take-Profit bracket) before 9:30 AM ET, or place it live during 9:30–9:45 AM ET.",
        )
        st.checkbox(
            "Step 4 (After Execution): Click `✓ Sold` / `✓ Bought` in Tab 1",
            value=False,
            key="sidebar_chk_fills",
            help="Confirm only what actually filled in your broker so your shadow cash and holdings stay 100% accurate.",
        )
        st.caption(f"Last IDE AI Run: **`{last_ide_run_ts}`**")

        st.markdown("---")
        st.markdown("### Autonomous Status")
        st.caption(f"Mode: **{acc['trading_mode'].upper()}** ($100,000 Virtual)")
        st.caption(f"Market Data: **{app.settings.market_data_provider.upper()}**")
        st.caption(f"Active Strategies: **{len(active_paper_strats)} Golden Base / Champions**")
        st.caption(f"Benchmark-Validated: **{golden_ready_count} strategies beat SPY**")
        st.markdown("---")
        if st.button(
            "Reset Paper Account ($100k)",
            width="stretch",
            help="Clears all simulated paper trades, open positions, and snapshots, resetting the forward paper account to $100,000.00 cash.",
        ):
            app.orchestrator.paper_engine.reset_account_to_starting_capital()
            st.rerun()

    st.title("Swing Trading AI")
    st.caption(
        f"Today: **{today_iso} ({today_weekday_name})** · "
        f"US Market: **{'OPEN SESSION' if is_today_trading_day else market_status_reason}** · "
        f"Next Trading Session: **{next_trading_day_iso}** · Benchmark: **SPY**"
    )

    # Top-of-Mind Executive Command Bar
    status_label = (
        "Active"
        if not acc["kill_switch_engaged"]
        else f"Paused ({acc['kill_switch_reason']})"
    )
    with st.expander(
        f"Executive Snapshot & IDE AI Reminder — Paper Equity: ${acc['total_equity']:,.2f} ({acc['total_return_pct']:+.2f}%) · "
        f"Active Strategies: {len(active_paper_strats)} · IDE AI Status: {'Ran Today' if ide_ran_today else 'Ready to Run (`type run in IDE`)'}",
        expanded=False,
    ):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**1. Market Calendar & Portfolio Health**")
            st.write(f"- **Today's Date**: `{today_iso}` (`{today_weekday_name}`)")
            st.write(f"- **Market Status**: `{market_status_reason}` (Next Open: `{next_trading_day_iso}`)")
            st.write(f"- **Risk State**: {status_label} (Drawdown `-{acc['current_drawdown_pct']:.2f}%` / Limit `15.0%`)")
        with c2:
            st.markdown("**2. Paper Portfolio Accounting (Forward Only)**")
            st.write(f"- **Window**: `{paper_date_span}`")
            st.write(
                f"- **Formula**: `${acc['starting_capital']:,.2f}` (Start) "
                f"+ `${acc['realised_pnl']:+,.2f}` (Closed) "
                f"+ `${acc['unrealised_pnl']:+,.2f}` (Open) "
                f"= **`${acc['total_equity']:,.2f}`**"
            )
            st.write(f"- **Active Strategies**: `{len(active_paper_strats)}` (`{len(rejected_strats)}` rejected in testing)")
        with c3:
            st.markdown("**3. Maximize P&L with IDE AI (`run`)**")
            st.write("- **One-Word IDE Trigger**: Type **`run`** in the Antigravity IDE chat on any trading day (or weekend).")
            st.write("- **Or Paste AI JSON Directly**: Open **Tab 4 (`AI Research & IDE Bridge`)** to copy an LLM prompt and feed the JSON response directly into the engine.")

    # Reorganized Top-of-Mind Tab Hierarchy (6 Focused, High-Signal Tabs)
    tabs = st.tabs(
        [
            "1. Live Copilot (Real Account)",
            "2. Paper Account & Ledger",
            "3. Strategies, Rules & Backtests",
            "4. AI Research & IDE Bridge",
            "5. Risk, Walk-Forward & Logs",
            "6. Platform Guide",
        ]
    )

    # =========================================================================
    # TAB 0: LIVE TRADING COPILOT (TOP-OF-MIND DAILY ACTION CHECKLIST)
    # =========================================================================
    with tabs[0]:
        _render_tab_header(
            st,
            "Live Copilot (Real Account): Today's trading-day-aware BUY/SELL checklist and real-account shadow portfolio—with zero access to your brokerage account.",
            "How Live Copilot works",
            "**100% Air-Gapped Shadow Portfolio:**\n\n"
            "- **Trading-Day Aware**: Automatically checks today's calendar date (`NYSE`/`NASDAQ` calendar). On weekends or market holidays, it clearly states the market is closed and suppresses stale trade suggestions.\n"
            "- **Never Assumes Your Positions**: Recommendations stay pending until you click **✓ Bought** or **✓ Sold**.\n"
            "- **Adapts to Your Real Holdings**: Stop-loss ratchets (`+1.25R` Breakeven, `+1.0R` Chandelier), holding-day countdowns, and 1% risk sizing adapt to your actual confirmed positions and cash balance.\n"
            "- **Full Mistake Recovery**: Use **Undo Last Trade**, **Restore Skipped Signals**, or **Add / Edit a Position** anytime.",
        )

        # Display flash notification banner if a Copilot action just completed
        if st.session_state.get("_copilot_flash_msg"):
            flash_msg = st.session_state.pop("_copilot_flash_msg")
            if hasattr(st, "toast"):
                st.toast(flash_msg)
            st.success(flash_msg)

        copilot_data = state.get("copilot") or {}
        plan = copilot_data.get("action_plan") or app.orchestrator.live_copilot.get_daily_action_plan()
        real_acc = plan["account_summary"]
        raw_sell_actions = plan["sell_actions"]
        raw_buy_actions = plan["buy_actions"]
        hold_updates = plan["hold_updates"]
        dismissed_count = int(plan.get("dismissed_count") or 0)
        real_positions = copilot_data.get("positions") or []
        real_history = copilot_data.get("trade_history") or []
        latest_bar_date = str(plan.get("session_date") or today_iso)

        # Synchronize st.session_state["copilot_cash_input"] whenever database cash_balance changes
        db_cash_val = round(float(real_acc["cash_balance"]), 2)
        if st.session_state.get("_synced_copilot_db_cash") != db_cash_val:
            st.session_state["copilot_cash_input"] = db_cash_val
            st.session_state["_synced_copilot_db_cash"] = db_cash_val

        # 1. Real Account Summary Metrics + Quick Cash Bar
        total_real_pnl = round(float(real_acc["realised_pnl"]) + float(real_acc["unrealised_pnl"]), 2)
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric(
            "My Account Value",
            f"${real_acc['total_equity']:,.2f}",
            f"{real_acc['total_return_pct']:+.2f}% vs ${real_acc['starting_cash']:,.0f} baseline",
            help="Confirmed Uninvested Cash + Market Value of your confirmed Open Holdings.",
        )
        rc2.metric(
            "Available Cash",
            f"${real_acc['cash_balance']:,.2f}",
            help="Uninvested cash used to size BUY signals (1.0% max risk per trade).",
        )
        rc3.metric(
            "Open Holdings",
            f"{real_acc['open_positions_count']} / 10",
            f"${real_acc['positions_market_value']:,.2f} invested",
            help="Positions you have confirmed buying or holding.",
        )
        rc4.metric(
            "Total Real P&L",
            f"${total_real_pnl:+,.2f}",
            f"Closed: ${real_acc['realised_pnl']:+,.0f} · Open: ${real_acc['unrealised_pnl']:+,.0f}",
            help="Combined Realised P&L (closed trades) and Unrealised P&L (open positions).",
        )

        # Compact 1-Row Cash & Account Controls Bar
        cash_c1, cash_c2, cash_c3, cash_c4, cash_c5 = st.columns([1.5, 0.9, 1.1, 1.1, 1.1])
        new_cash_val = cash_c1.number_input(
            "My Broker Cash Balance ($)",
            min_value=0.0,
            value=db_cash_val,
            step=500.0,
            key="copilot_cash_input",
            help="Enter your current uninvested cash so BUY share counts scale to your exact account size.",
        )
        with cash_c2:
            st.write("")
            if st.button("Update Cash", key="btn_upd_cash", width="stretch", help="Updates your uninvested cash balance while keeping your starting capital baseline intact."):
                app.orchestrator.live_copilot.update_cash_balance(float(new_cash_val), False)
                st.session_state["_copilot_flash_msg"] = f"Updated Available Cash to ${float(new_cash_val):,.2f}."
                st.rerun()
        with cash_c3:
            st.write("")
            if st.button("Set as Starting Capital", key="btn_reset_base_cash", width="stretch", help="Sets your current Cash + Open Holdings cost basis as your 0% P&L baseline."):
                app.orchestrator.live_copilot.update_cash_balance(float(new_cash_val), True)
                st.session_state["_copilot_flash_msg"] = f"Updated Cash to ${float(new_cash_val):,.2f} and reset 0% Starting Capital baseline."
                st.rerun()
        with cash_c4:
            st.write("")
            with st.popover("Deposit / Withdraw", width="stretch"):
                st.caption("Adjust cash & starting capital together so deposits/withdrawals don't distort your P&L %.")
                dw_amt = st.number_input("Amount ($)", min_value=1.0, value=1000.0, step=250.0, key="copilot_dw_amt")
                dw_c1, dw_c2 = st.columns(2)
                if dw_c1.button("+ Deposit", width="stretch"):
                    app.orchestrator.live_copilot.adjust_cash_deposit_withdrawal(float(dw_amt))
                    st.session_state["_copilot_flash_msg"] = f"Deposited +${float(dw_amt):,.2f} into broker cash & baseline."
                    st.rerun()
                if dw_c2.button("- Withdraw", width="stretch"):
                    try:
                        app.orchestrator.live_copilot.adjust_cash_deposit_withdrawal(-float(dw_amt))
                        st.session_state["_copilot_flash_msg"] = f"Withdrew -${float(dw_amt):,.2f} from broker cash & baseline."
                        st.rerun()
                    except ValueError as err:
                        st.error(str(err))
        with cash_c5:
            st.write("")
            with st.popover("Strategies & Reset", width="stretch"):
                avail_keys = [
                    f"{s['strategy_id']}:{s['version']}"
                    for s in strats
                    if s["status"] in ("PAPER_TRADING", "APPROVED_FOR_REVIEW")
                ]
                default_keys = real_acc.get("enabled_strategies") or avail_keys
                valid_defaults = [k for k in default_keys if k in avail_keys] or avail_keys
                st.caption("**1-Click Real-Account Deployment Presets:**")
                pr_c1, pr_c2 = st.columns(2)
                if pr_c1.button("★ Core 2 (Breakout + Dip)", width="stretch", help="Recommended for accounts <$30k or Phase 1 Live: Volatility Breakout (SQN 3.55) + Mean Reversion (64.7% 6M WR)."):
                    core2 = [k for k in avail_keys if "volatility_breakout" in k or "mean_reversion" in k] or avail_keys
                    app.orchestrator.live_copilot.set_enabled_strategies(core2)
                    st.session_state["copilot_strats_select"] = core2
                    st.session_state["_copilot_flash_msg"] = "Applied Core 2 Uncorrelated Preset (Volatility Breakout + Mean Reversion)."
                    st.rerun()
                if pr_c2.button("All 5 Base Strategies", width="stretch", help="Full institutional diversification across all 5 uncorrelated Golden Base strategy sleeves."):
                    app.orchestrator.live_copilot.set_enabled_strategies(avail_keys)
                    st.session_state["copilot_strats_select"] = avail_keys
                    st.session_state["_copilot_flash_msg"] = "Enabled all 5 Golden Base strategies."
                    st.rerun()
                pr_c3, pr_c4 = st.columns(2)
                if pr_c3.button("Core 3 (+ Earnings PEAD)", width="stretch", help="Core 2 + Post-Earnings Announcement Drift (ideal during quarterly earnings season)."):
                    core3 = [k for k in avail_keys if any(x in k for x in ("volatility_breakout", "mean_reversion", "pead"))] or avail_keys
                    app.orchestrator.live_copilot.set_enabled_strategies(core3)
                    st.session_state["copilot_strats_select"] = core3
                    st.session_state["_copilot_flash_msg"] = "Applied Core 3 Preset (Breakout + Mean Reversion + PEAD)."
                    st.rerun()
                if pr_c4.button("Best Single (Breakout)", width="stretch", help="Single highest SQN (3.55) & 6-month return (+11.03%) strategy only."):
                    single1 = [k for k in avail_keys if "volatility_breakout" in k] or avail_keys[:1]
                    app.orchestrator.live_copilot.set_enabled_strategies(single1)
                    st.session_state["copilot_strats_select"] = single1
                    st.session_state["_copilot_flash_msg"] = "Enabled Single Best Champion (Volatility Breakout)."
                    st.rerun()
                chosen_keys = st.multiselect(
                    "Or customize active strategies",
                    options=avail_keys,
                    default=valid_defaults,
                    key="copilot_strats_select",
                )
                if st.button("Apply Custom Selection", width="stretch"):
                    app.orchestrator.live_copilot.set_enabled_strategies(chosen_keys)
                    st.session_state["_copilot_flash_msg"] = f"Active strategy filter saved ({len(chosen_keys)} strategies enabled)."
                    st.rerun()
                st.markdown("---")
                if real_history and st.button("Undo Last Confirmed Trade", width="stretch", help="Reverses your most recent BUY or SELL confirmation and restores cash/positions."):
                    last_t = real_history[0]
                    app.orchestrator.live_copilot.undo_last_trade()
                    st.session_state["_copilot_flash_msg"] = f"Undid last {last_t['side']} of {last_t['quantity']} {last_t['ticker']} @ ${float(last_t['fill_price']):.2f}."
                    st.rerun()
                if st.button("Reset Real Account Ledger", width="stretch", help="Clears all confirmed holdings and trade history in Live Copilot."):
                    app.orchestrator.live_copilot.reset_copilot_account()
                    st.session_state["_copilot_flash_msg"] = "Reset Live Copilot ledger to clean starting cash."
                    st.rerun()

        st.markdown("---")
        chk_hdr_c1, chk_hdr_c2, chk_hdr_c3 = st.columns([3.0, 1.1, 1.1])
        chk_hdr_c1.markdown(
            f"#### 1. Today's Action Checklist — `{today_iso}` ({today_weekday_name})"
        )
        if dismissed_count > 0:
            if chk_hdr_c2.button(f"Restore Skipped ({dismissed_count})", key="btn_restore_skipped", width="stretch", help="Bring back signals you clicked Skip or Hold on."):
                restored_n = app.orchestrator.live_copilot.restore_dismissed_signals(latest_bar_date)
                st.session_state["_copilot_flash_msg"] = f"Restored {restored_n} skipped signal(s)."
                st.rerun()
        if real_history:
            last_t = real_history[0]
            if chk_hdr_c3.button(f"Undo Last ({last_t['side']} {last_t['ticker']})", key="btn_quick_undo", width="stretch", help="One-click undo of your most recent trade confirmation."):
                app.orchestrator.live_copilot.undo_last_trade()
                st.session_state["_copilot_flash_msg"] = f"Undid {last_t['side']} {last_t['quantity']} {last_t['ticker']} @ ${float(last_t['fill_price']):.2f}."
                st.rerun()

        # Compact 4-Step Daily Playbook & "What If" Contingency Guide
        with st.expander(
            "⏱️ Daily Order of Operations (By Time) — What Comes First, When to Set Stop/Target, What If You Forget a Day or Exit Early?",
            expanded=False,
        ):
            g_col1, g_col2 = st.columns(2)
            with g_col1:
                st.markdown(
                    "**A. Exact Daily Sequence (In Order, `ET` & `SGT`)**\n\n"
                    "1. **Step 1 — Before Market Open (`Anytime before 9:30 AM ET / 9:30 PM SGT`): Optional AI Check (`type run in IDE`)**\n"
                    "   - **How AI changes decisions**: Searches live web news (`search_web`) for your checklist stocks—automatically **vetoing** any `BUY` setup with bearish breaking news (`sentiment <= -0.35`, e.g., guidance cut/probe) and **boosting** high-catalyst setups (`>= +0.25`).\n"
                    "   - **If you skip `run`**: GitHub Actions already ran the deterministic engine at `5:30 AM SGT` (`21:30 UTC`), so your checklist below is **already updated and ready to trade**.\n"
                    "2. **Step 2 — Priority #1 (`9:30–9:35 AM ET / 9:30–9:35 PM SGT`): Execute `SELL` Exits & `Raise Stop` Alerts First**\n"
                    "   - Always execute **`SELL` signals first** at market open to free up cash and lock in P&L.\n"
                    "   - Next, if any open holding shows **`Raise Stop → $X.XX`**, update your broker's existing `GTC Stop-Loss` order to that higher price.\n"
                    "3. **Step 3 — Priority #2 (`9:30–9:45 AM ET` or Pre-Submitted Limit): Place `BUY` Orders + Attach Stop/Target Immediately**\n"
                    "   - **Do I need to trade at `9:30:00` sharp?** **No!** You can either:\n"
                    "     - *Option A (Set-and-Forget Before Open)*: Anytime before `9:30 AM ET`, submit a **Regular-Hours (`RTH`) Day Limit Order** at the **`Max Chase` price** (top of Buy-Zone) with an attached **OCO Bracket (`Stop-Loss` + `Take-Profit`)**. At `9:30 AM ET`, your broker fills you automatically if the open is $\\le$ `Max Chase`.\n"
                    "     - *Option B (Live Open Window `9:30–9:45 AM ET`)*: Place a Limit order if the live price is inside the **`Buy-Zone ($Low – $MaxChase)`**.\n"
                    "4. **Step 4 — After Broker Fill: Click `✓ Sold` / `✓ Bought` Below**"
                )
            with g_col2:
                st.markdown(
                    "**B. When to Set Stop/Target, What If You Forget a Day, or Exit Early?**\n\n"
                    "- **When should I set `Stop-Loss` and `Take-Profit`?**\n"
                    "  - **Immediately when placing your `BUY` order** (as an attached **Bracket / OCO order**, or as a **`GTC Stop-Loss` + `GTC Limit Take-Profit`** within 1 minute of your BUY fill). Because they are `GTC` (Good-Til-Cancelled), your broker protects your `-1%` max risk and upside target automatically every day even if you are away from your screen.\n"
                    "- **What if I forget to run or place orders for a day?**\n"
                    "  - **Forgot a `BUY`**: **Never chase it late.** Leave it—if the stock is still valid and inside the Buy-Zone tomorrow, it will appear on tomorrow's checklist with updated prices. If it gapped away, missing it saved you from chasing!\n"
                    "  - **Forgot a `SELL`**: Your broker's `GTC Stop-Loss` and `Take-Profit` bracket continues protecting your downside/upside automatically, and the `SELL` card will remain at the top of your checklist tomorrow until you execute and click `✓ Sold`.\n"
                    "- **What if I decide to exit a position early on my own?**\n"
                    "  1. Sell the shares in your broker (and cancel any leftover open `GTC Stop/Target` orders for that stock if not linked via OCO).\n"
                    "  2. Scroll to **Section 2 (`My Active Holdings`)** below, type the shares sold and your actual exit price, and click **`Close / Sell`**. Your cash and Realised P&L update in 1 click!"
                )

        # Trading-Day Gate: If today is a weekend or US market holiday, state so and suppress suggestions by default
        show_signals_today = is_today_trading_day
        if not is_today_trading_day:
            st.info(
                f"**No Trade Suggestions Today (`{today_iso}` — {market_status_reason})**\n\n"
                f"US equity markets (`NYSE` & `NASDAQ`) are closed today, so no new `BUY` or `SELL` orders should be placed today. "
                f"The next trading session is **`{next_trading_day_iso}`** (latest completed market data bar: `{latest_bar_date}`)."
            )
            show_signals_today = st.checkbox(
                f"Preview watchlist setups from latest market close (`{latest_bar_date}`) for `{next_trading_day_iso}` preparation",
                value=False,
                key="copilot_preview_non_trading_day",
            )
        else:
            st.caption(
                f"🟢 **Today (`{today_iso}`) is an active US Trading Day.** "
                f"**Execution Order**: **1)** Optional `run` in IDE before open → **2)** Execute `SELL` exits & `Raise Stop` updates first (`9:30–9:35 AM ET` / `9:30–9:35 PM SGT`) → **3)** Place `BUY` Limit orders inside Buy-Zone (`9:30–9:45 AM ET` or pre-set RTH Limit) with immediate `GTC Stop-Loss` & `Take-Profit` bracket."
            )

        sell_actions = raw_sell_actions if show_signals_today else []
        buy_actions = raw_buy_actions if show_signals_today else []
        ratchet_alerts = [
            h for h in hold_updates if h.get("stop_mode") and h.get("stop_mode") != "Initial ATR Stop"
        ] if show_signals_today else []

        if show_signals_today:
            # PRIORITY 1: SELL Actions (Exits on confirmed positions)
            if sell_actions:
                st.markdown("##### Priority 1 (At Open `9:30–9:35 AM ET` / `9:30–9:35 PM SGT`) — `SELL` Exit Signals on Your Holdings *(Execute First to Free Cash)*")
                for idx, sa in enumerate(sell_actions):
                    sc_info, sc_qty, sc_px, sc_btn1, sc_btn2 = st.columns([2.6, 0.8, 0.9, 0.9, 0.7])
                    s_qty_sig = f"{sa['ticker']}_{sa['quantity_to_sell']}_{sa['reference_exit_price']}"
                    s_qty = sc_qty.number_input(
                        "Shares",
                        min_value=1,
                        max_value=int(sa["quantity_to_sell"]),
                        value=int(sa["quantity_to_sell"]),
                        key=f"sell_qty_{s_qty_sig}_{idx}",
                    )
                    s_price = sc_px.number_input(
                        "Exit Price ($)",
                        min_value=0.01,
                        value=float(sa["reference_exit_price"]),
                        step=0.10,
                        key=f"sell_px_{s_qty_sig}_{idx}",
                    )
                    live_est_pnl = round((float(s_price) - float(sa["avg_entry_price"])) * int(s_qty), 2)
                    with sc_info:
                        st.warning(
                            f"**SELL `{s_qty}` `{sa['ticker']}`** (`Est. P&L: ${live_est_pnl:+,.2f}`) · *Execute at Open (`9:30–9:35 AM ET`)*\n\n"
                            f"Your Entry `${sa['avg_entry_price']:.2f}` → Exit `${float(s_price):.2f}` · *{sa['reason']}* (Cancel any old GTC bracket after selling)"
                        )
                    with sc_btn1:
                        st.write("")
                        if st.button(f"✓ Sold {sa['ticker']}", key=f"btn_sell_{s_qty_sig}_{idx}", width="stretch"):
                            app.orchestrator.live_copilot.confirm_sell_execution(
                                ticker=sa["ticker"],
                                quantity=int(s_qty),
                                fill_price=float(s_price),
                                fees_usd=0.0,
                                notes=sa["reason"],
                            )
                            st.session_state["_copilot_flash_msg"] = (
                                f"Confirmed SELL {int(s_qty)} {sa['ticker']} @ ${float(s_price):.2f} "
                                f"(Realised P&L: ${live_est_pnl:+,.2f})."
                            )
                            st.rerun()
                    with sc_btn2:
                        st.write("")
                        if st.button("Hold", key=f"btn_skip_sell_{s_qty_sig}_{idx}", width="stretch", help="Hide this sell signal for today and keep holding."):
                            app.orchestrator.live_copilot.dismiss_signal(
                                signal_date=sa["signal_date"],
                                strategy_id=sa["strategy_id"],
                                ticker=sa["ticker"],
                                action="SELL",
                            )
                            st.session_state["_copilot_flash_msg"] = f"Marked {sa['ticker']} as Hold for today (click 'Restore Skipped' to undo)."
                            st.rerun()

            # PRIORITY 2: Stop-Loss Ratchet Alerts on Open Holdings
            if ratchet_alerts:
                st.markdown("##### Priority 2 (Anytime Today) — `Raise Stop-Loss` on Your Winning Holdings *(Lock In Profit Floor)*")
                for r_h in ratchet_alerts:
                    st.info(
                        f"🛡️ **`{r_h['ticker']}` (`{r_h['quantity']} sh`) reached `+1R+` profit!** "
                        f"Update your broker's `GTC Stop-Loss` order from `${float(r_h.get('initial_stop_price') or r_h['stop_loss_price']):.2f}` "
                        f"→ **`${float(r_h['stop_loss_price']):.2f}`** (`{r_h['stop_mode']}`) · Keep `Take-Profit` at `${float(r_h['take_profit_price']):.2f}`."
                    )

            # PRIORITY 3: BUY Actions (New entries sized to user's real cash & equity)
            if buy_actions:
                st.markdown(
                    "##### Priority 3 (`9:30–9:45 AM ET` / `9:30–9:45 PM SGT` or Pre-Set RTH Limit) — `BUY` New Setups *(Attach GTC Stop-Loss & Take-Profit Immediately)*"
                )
                for idx, ba in enumerate(buy_actions):
                    bc_info, bc_qty, bc_px, bc_btn1, bc_btn2 = st.columns([2.6, 0.8, 0.9, 0.9, 0.7])
                    b_sig = f"{ba['ticker']}_{ba['recommended_shares']}_{ba['reference_entry_price']}"
                    b_qty = bc_qty.number_input(
                        "Shares",
                        min_value=1,
                        value=int(ba["recommended_shares"]),
                        step=1,
                        key=f"buy_qty_{b_sig}_{idx}",
                    )
                    b_price = bc_px.number_input(
                        "Fill Price ($)",
                        min_value=0.01,
                        value=float(ba["reference_entry_price"]),
                        step=0.10,
                        key=f"buy_px_{b_sig}_{idx}",
                    )
                    ref_px = float(ba["reference_entry_price"])
                    px_shift = float(b_price) - ref_px
                    adj_stop = round(max(0.01, float(ba["stop_loss_price"]) + px_shift), 2) if ba.get("stop_loss_price") else 0.0
                    adj_tp = round(max(float(b_price) + 0.01, float(ba["take_profit_price"]) + px_shift), 2) if ba.get("take_profit_price") else 0.0
                    live_cost = round(int(b_qty) * float(b_price), 2)
                    live_weight = round((live_cost / max(1.0, float(real_acc["total_equity"]))) * 100.0, 1)
                    live_risk = round(max(0.0, (float(b_price) - adj_stop) * int(b_qty)), 0)
                    buy_zone_str = ba.get("entry_buy_zone_str") or f"${ref_px * 0.995:.2f} – ${ref_px * 1.015:.2f}"
                    ratchet_1r = float(ba.get("breakeven_ratchet_price") or round(float(b_price) + max(0.01, float(b_price) - adj_stop), 2))
                    ai_sent_val = float(ba.get("ai_catalyst_sentiment", 0.0))
                    ai_badge_html = (
                        f" · <span style='color:#4ade80;font-weight:600;'>AI Catalyst {ai_sent_val:+.2f}</span>"
                        if ai_sent_val >= 0.20
                        else ""
                    )
                    with bc_info:
                        st.markdown(
                            f"**BUY `{int(b_qty)}` `{ba['ticker']}` @ `${float(b_price):.2f}`** "
                            f"(`~${live_cost:,.0f}` · `{live_weight:.1f}%` of account) · "
                            f"**Buy-Zone Limit: `{buy_zone_str}`** (Open `9:30–9:45 AM ET`){ai_badge_html}  \n"
                            f"Set Broker Bracket: **Stop-Loss `${adj_stop:.2f}`** (`-${live_risk:,.0f}` max risk) · "
                            f"**Take-Profit `${adj_tp:.2f}`** · *At `+1R (${ratchet_1r:.2f})` raise Stop → Breakeven; Time-Stop `{ba['holding_horizon_days']}`*  \n"
                            f"<span style='color:#94a3b8;font-size:0.82rem;'>{ba['strategy_id']} v{ba['strategy_version']} — {ba['reason']} · "
                            f"{ba.get('if_entry_not_hit_rule', 'Skip if open gaps above Buy-Zone ceiling.')}</span>",
                            unsafe_allow_html=True,
                        )
                    with bc_btn1:
                        st.write("")
                        if st.button(
                            f"✓ Bought {ba['ticker']}",
                            key=f"btn_buy_{b_sig}_{idx}",
                            width="stretch",
                        ):
                            app.orchestrator.live_copilot.confirm_buy_execution(
                                ticker=ba["ticker"],
                                strategy_id=ba["strategy_id"],
                                strategy_version=int(ba["strategy_version"]),
                                quantity=int(b_qty),
                                fill_price=float(b_price),
                                fees_usd=0.0,
                                stop_loss_price=ba["stop_loss_price"],
                                take_profit_price=ba["take_profit_price"],
                                reference_entry_price=ref_px,
                                sector=ba["sector"],
                                notes=ba["reason"],
                            )
                            st.session_state["_copilot_flash_msg"] = (
                                f"Confirmed BUY {int(b_qty)} {ba['ticker']} @ ${float(b_price):.2f} "
                                f"(Stop ${adj_stop:.2f} · Target ${adj_tp:.2f})."
                            )
                            st.rerun()
                    with bc_btn2:
                        st.write("")
                        if st.button(
                            "Skip",
                            key=f"btn_skip_{b_sig}_{idx}",
                            width="stretch",
                        ):
                            app.orchestrator.live_copilot.dismiss_signal(
                                signal_date=ba["signal_date"],
                                strategy_id=ba["strategy_id"],
                                ticker=ba["ticker"],
                                action="BUY",
                            )
                            st.session_state["_copilot_flash_msg"] = f"Skipped {ba['ticker']} for today (click 'Restore Skipped' to undo)."
                            st.rerun()
            elif not sell_actions:
                st.info("No new BUY or SELL actions required today. All open holdings remain within their target brackets.")

            vetoed_sigs = plan.get("vetoed_signals") or []
            if vetoed_sigs:
                with st.expander(f"Signals Filtered Out by Your Risk Caps ({len(vetoed_sigs)})", expanded=False):
                    st.dataframe(vetoed_sigs, width="stretch")

        st.markdown("---")
        # 2. My Confirmed Real Positions with 1-Click Partial/Full Close & Smart Pre-Filled Editor
        st.markdown("#### 2. My Active Holdings, Stop-Loss Ratchets & Early Exit Controls")
        st.caption(
            "**Want to exit a position early (or log a Stop-Loss / Take-Profit fill)?** "
            "1) Sell in your broker & cancel any leftover GTC bracket for that stock → "
            "2) Enter the **Shares** & **Exit Price ($)** on that row below → "
            "3) Click **`Close`** (or **`Sell N`** for a partial exit) to immediately credit your Cash and log Realised P&L."
        )
        if hold_updates:
            for h_idx, h in enumerate(hold_updates):
                hc1, hc2, hc3, hc4, hc5 = st.columns([2.5, 1.3, 0.7, 0.8, 0.8])
                h_sig = f"{h['ticker']}_{h['quantity']}_{h['avg_entry_price']}"
                pnl_sign = f"+${h['unrealised_pnl']:,.2f}" if h["unrealised_pnl"] >= 0 else f"-${abs(h['unrealised_pnl']):,.2f}"
                hc1.markdown(
                    f"**`{h['ticker']}`** · `{h['quantity']} shares` · "
                    f"Entry `${h['avg_entry_price']:.2f}` → Now `${h['current_price']:.2f}` (**`{pnl_sign}`**)  \n"
                    f"<span style='color:#94a3b8;font-size:0.83rem;'>{h['status']}</span>",
                    unsafe_allow_html=True,
                )
                stop_disp = f"${h['stop_loss_price']:.2f}" if h.get("stop_loss_price") else "-"
                tp_disp = f"${h['take_profit_price']:.2f}" if h.get("take_profit_price") else "-"
                hc2.markdown(
                    f"**Stop**: `{stop_disp}` · **Target**: `{tp_disp}`  \n"
                    f"<span style='color:#38bdf8;font-size:0.8rem;'>{h.get('stop_mode', 'Initial ATR Stop')}</span>",
                    unsafe_allow_html=True,
                )
                close_qty = hc3.number_input(
                    f"Qty ({h['ticker']})",
                    min_value=1,
                    max_value=int(h["quantity"]),
                    value=int(h["quantity"]),
                    step=1,
                    key=f"quick_close_qty_{h_sig}_{h_idx}",
                    label_visibility="collapsed",
                    help="Shares to sell (supports partial or full exit).",
                )
                close_px = hc4.number_input(
                    f"Exit $ ({h['ticker']})",
                    min_value=0.01,
                    value=float(h["current_price"]),
                    step=0.10,
                    key=f"quick_close_px_{h_sig}_{h_idx}",
                    label_visibility="collapsed",
                    help="Actual broker sale price per share.",
                )
                btn_lbl = f"Sell {close_qty} {h['ticker']}" if int(close_qty) < int(h["quantity"]) else f"Close {h['ticker']}"
                if hc5.button(btn_lbl, key=f"btn_qclose_{h_sig}_{h_idx}", width="stretch", help="Confirm you sold these shares in your brokerage account."):
                    app.orchestrator.live_copilot.confirm_sell_execution(
                        ticker=h["ticker"],
                        quantity=int(close_qty),
                        fill_price=float(close_px),
                        fees_usd=0.0,
                        notes="Manual position exit via Copilot",
                    )
                    est_p = round((float(close_px) - float(h["avg_entry_price"])) * int(close_qty), 2)
                    st.session_state["_copilot_flash_msg"] = (
                        f"Confirmed SELL {int(close_qty)} {h['ticker']} @ ${float(close_px):.2f} "
                        f"(Realised P&L: ${est_p:+,.2f})."
                    )
                    st.rerun()
        elif real_positions:
            st.dataframe(real_positions, width="stretch")
        else:
            st.caption("No active holdings logged yet. Click **✓ Bought** on a setup above or log an existing broker holding below.")

        with st.expander("Log an Existing Broker Holding or Edit a Position (Any Ticker, Shares, Entry Date, Stop/Target)", expanded=False):
            universe_tickers = sorted({t for s in strats for t in s["universe"]} | {p["ticker"] for p in real_positions})
            ticker_options = universe_tickers + ["+ Custom Ticker..."]
            pos_by_tkr = {p["ticker"]: p for p in real_positions}
            latest_px_by_tkr = {r["ticker"]: float(r["current_price"]) for r in state["research_reports"]}

            ec1, ec2, ec3, ec4, ec5, ec6 = st.columns([1.15, 0.85, 0.95, 0.95, 0.95, 1.05])
            sel_tkr_opt = ec1.selectbox("Ticker", options=ticker_options, key="edit_pos_ticker")
            if sel_tkr_opt == "+ Custom Ticker...":
                e_ticker = ec1.text_input("Custom Symbol", value="TSLA", key="edit_pos_custom_tkr").strip().upper() or "TSLA"
            else:
                e_ticker = sel_tkr_opt

            existing_p = pos_by_tkr.get(e_ticker)
            pos_sig = (
                f"{e_ticker}_{existing_p['quantity']}_{existing_p['avg_entry_price']}_"
                f"{existing_p.get('stop_loss_price')}_{existing_p.get('take_profit_price')}_{existing_p.get('opened_date')}"
                if existing_p
                else f"{e_ticker}_new"
            )
            default_qty = int(existing_p["quantity"]) if existing_p else 10
            default_px = (
                float(existing_p["avg_entry_price"])
                if existing_p
                else round(latest_px_by_tkr.get(e_ticker, 150.0), 2)
            )
            default_sl = float(existing_p["stop_loss_price"]) if (existing_p and existing_p.get("stop_loss_price")) else 0.0
            default_tp = float(existing_p["take_profit_price"]) if (existing_p and existing_p.get("take_profit_price")) else 0.0
            default_dt = str(existing_p["opened_date"]) if existing_p else latest_bar_date

            e_qty = ec2.number_input("Shares (0=Remove)", min_value=0, value=default_qty, step=1, key=f"edit_qty_{pos_sig}")
            e_entry = ec3.number_input("Avg Entry ($)", min_value=0.01, value=default_px, step=0.50, key=f"edit_px_{pos_sig}")
            e_stop = ec4.number_input("Stop $ (0=Auto)", min_value=0.0, value=default_sl, step=0.50, key=f"edit_sl_{pos_sig}")
            e_tp = ec5.number_input("Target $ (0=Auto)", min_value=0.0, value=default_tp, step=0.50, key=f"edit_tp_{pos_sig}")
            e_date = ec6.text_input("Entry Date (YYYY-MM-DD)", value=default_dt, key=f"edit_dt_{pos_sig}")

            act_c1, act_c2 = st.columns([1.5, 2.5])
            deduct_label = (
                "Adjust my Available Cash by the net share change"
                if existing_p is not None
                else "Deduct purchase cost from my Available Cash (leave unchecked if your cash balance above already excludes this holding)"
            )
            deduct_chk = act_c2.checkbox(
                deduct_label,
                value=False,
                key=f"edit_deduct_{pos_sig}",
            )
            btn_save_label = f"Remove {e_ticker}" if int(e_qty) == 0 else (f"Update {e_ticker} Holding" if existing_p else f"Add {e_ticker} Holding")
            if act_c1.button(btn_save_label, key=f"btn_save_{pos_sig}", width="stretch"):
                app.orchestrator.live_copilot.edit_or_add_position(
                    ticker=e_ticker,
                    quantity=int(e_qty),
                    avg_entry_price=float(e_entry),
                    stop_loss_price=float(e_stop) if e_stop > 0 else None,
                    take_profit_price=float(e_tp) if e_tp > 0 else None,
                    opened_date=e_date.strip() or latest_bar_date,
                    deduct_from_cash=deduct_chk,
                )
                st.session_state["_copilot_flash_msg"] = (
                    f"Removed {e_ticker} from holdings."
                    if int(e_qty) == 0
                    else f"Saved {e_ticker}: {int(e_qty)} shares @ ${float(e_entry):.2f} (Entry Date: {e_date.strip()})."
                )
                st.rerun()

        # 3. Confirmed Real Trade History
        if real_history:
            with st.expander(f"3. My Confirmed Real Trade History ({len(real_history)} fills)", expanded=False):
                st.dataframe(real_history, width="stretch")

    # =========================================================================
    # TAB 1: PAPER ACCOUNT & LEDGER (TWO-TIER: MASTER $100K + 5 PER-STRATEGY $100K BOOKS)
    # =========================================================================
    with tabs[1]:
        _render_tab_header(
            st,
            "Paper Account & Ledger: Two-Tier Forward $100k Books (1 Master Combined Portfolio + 5 Dedicated Per-Strategy $100k Accounts) & Day-Filtered Execution Ledger.",
            "Why We Run Both a Master $100k Book & 5 Dedicated Per-Strategy $100k Books",
            "**Institutional Multi-Strategy Pod Architecture (Zero Cash Starvation + Real Risk Governance):**\n\n"
            "- **Tier 1 — Master Combined Portfolio (`$100,000` Shared Book)**: Runs all active strategies together under your real-account risk caps (`5%` portfolio heat, `30%` sector cap, `15%` single-stock cap). Simulates exact multi-strategy execution in a single brokerage account.\n"
            "- **Tier 2 — 5 Dedicated Per-Strategy `$100,000` Books (`1 Account Per Strategy`)**: Each strategy (`Volatility Breakout`, `Mean Reversion`, `PEAD Drift`, `Momentum Trend`, `Sector Rotation`) also gets its own isolated `$100,000` account. This eliminates **cash starvation / first-in bias** (where Strategy A uses up cash on Monday and blocks Strategy B on Tuesday) so you can measure every strategy's true standalone forward edge.\n"
            "- **Strict Forward Isolation**: Only actual daily runs (`21:30 UTC` or `run` in IDE) affect these accounts. Historical backtests are isolated in Tab 3.",
        )

        all_paper_books = app.orchestrator.paper_engine.get_all_paper_accounts_summary(strats)
        book_options = [b["account_id"] for b in all_paper_books]
        book_labels = {
            b["account_id"]: (
                f"★ {b['book_label']} — Equity: ${b['total_equity']:,.2f} ({b['total_return_pct']:+.2f}%) · {b['open_positions_count']} Open · {b['total_fills']} Fills"
                if b["book_type"] == "MASTER_COMBINED"
                else f"Pod: {b['book_label']} ({b['strategy_id']}) — Equity: ${b['total_equity']:,.2f} ({b['total_return_pct']:+.2f}%) · {b['open_positions_count']} Open · {b['total_fills']} Fills"
            )
            for b in all_paper_books
        }

        sel_book_col1, sel_book_col2 = st.columns([2.2, 1.8])
        with sel_book_col1:
            selected_book_id = st.selectbox(
                "Select Paper Account Book to Inspect",
                options=book_options,
                index=0,
                format_func=lambda aid: book_labels.get(aid, aid),
                key="paper_book_selector",
                help="Switch between the Master Combined $100k Portfolio (all active strategies sharing capital and risk caps) and each strategy's dedicated $100k isolated pod.",
            )
        with sel_book_col2:
            st.caption(
                "**Senior Quant Best Practice**: Use the **Master Combined `$100k` Book** to monitor cross-strategy portfolio risk & drawdown, "
                "and inspect the **5 Per-Strategy `$100k` Pods** to compare pure unstarved strategy alpha before sizing up your real account."
            )

        if selected_book_id == app.orchestrator.paper_engine.DEFAULT_ACCOUNT_ID:
            book_engine = app.orchestrator.paper_engine
            book_acc = acc
            book_positions = positions
            book_ledger = ledger
            book_snaps = snaps
            book_title_label = f"Master Combined Portfolio (`$100k` Shared Across: {active_strat_names})"
        else:
            strat_id_for_book = selected_book_id.replace("paper_", "", 1)
            book_engine = app.orchestrator.paper_engine.get_strategy_account_engine(strat_id_for_book)
            book_acc = book_engine.get_account_summary()
            book_positions = book_engine.get_open_positions()
            book_ledger = book_engine.get_trade_ledger(limit=500)
            book_snaps = book_engine.get_equity_curve()
            book_title_label = f"Dedicated Strategy Pod: `{strat_id_for_book}` (`$100,000` Isolated Account)"

        book_daily_pnl_usd, book_daily_ret_pct, book_weekly_pnl_usd, book_weekly_ret_pct, book_net_dollar_pnl = _compute_period_pnl(book_acc, book_snaps)
        book_total_fees = sum(
            float(l.get("commission_usd", 0.0)) + float(l.get("slippage_usd", 0.0))
            for l in book_ledger
        )
        book_fill_dates = sorted({str(l.get("fill_date")) for l in book_ledger if l.get("fill_date")})
        if book_fill_dates:
            book_date_span = f"{book_fill_dates[0]} → {book_fill_dates[-1]} ({len(book_fill_dates)} active fill days)"
        else:
            book_date_span = f"{latest_market_date} (Clean $100k baseline — waiting for next daily session)"

        st.markdown(f"#### 1. Paper Portfolio Profit & Loss Attribution — {book_title_label}")
        st.markdown(
            f"""
            - **Selected Book**: {book_title_label}
            - **Measurement Window**: `{book_date_span}` *(Forward daily runs only — historical testing is isolated in Tab 3)*
            - **Derivation**:
              `Starting Capital ($100,000.00)` + `Realised P&L (${book_acc['realised_pnl']:+,.2f})` + `Unrealised P&L (${book_acc['unrealised_pnl']:+,.2f})` = **`Current Equity (${book_acc['total_equity']:,.2f})`** *(Net of `${book_total_fees:,.2f}` in transaction costs)*
            """
        )

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric(
            "Total Equity",
            f"${book_acc['total_equity']:,.2f}",
            f"Start: ${book_acc['starting_capital']:,.0f} ({book_acc['total_return_pct']:+.2f}%)",
            help="Cash Balance + Market Value of Open Positions. Equals Starting Capital ($100k) + Realised P&L + Unrealised P&L.",
        )
        k2.metric(
            "Daily P&L (Latest Session)",
            f"${book_daily_pnl_usd:+,.2f}",
            f"{book_daily_ret_pct:+.2f}% today",
            help="Single-session change in Total Equity from the prior trading session close to the latest session close.",
        )
        k3.metric(
            "Weekly P&L (Last 5 Sessions)",
            f"${book_weekly_pnl_usd:+,.2f}",
            f"{book_weekly_ret_pct:+.2f}% (5d)",
            help="Rolling 5-session (1 trading week) change in Total Equity across actual forward paper runs.",
        )
        k4.metric(
            "Total P&L (Since Reset)",
            f"${book_net_dollar_pnl:+,.2f}",
            f"Realised ${book_acc['realised_pnl']:+,.0f} | Unrealised ${book_acc['unrealised_pnl']:+,.0f}",
            help="Cumulative net P&L since the $100,000 baseline reset (Realised P&L from closed trades + Unrealised P&L on open positions, net of fees).",
        )
        k5.metric(
            "Available Cash",
            f"${book_acc['cash_balance']:,.2f}",
            f"{book_acc['open_positions_count']} open | DD -{book_acc['current_drawdown_pct']:.2f}%",
            help="Uninvested cash available for new swing entries. Drawdown measures the drop from the portfolio's highest equity peak.",
        )

        p_col1, p_col2 = st.columns([1.05, 1.15])
        with p_col1:
            st.markdown("#### 2. Open Paper Positions (Selected Book)")
            if book_positions:
                clean_pos = [
                    {
                        "Ticker": p["ticker"],
                        "Strategy": f"{p['strategy_id']} v{p['strategy_version']}",
                        "Entry Date": p["opened_date"],
                        "Hold": f"{p['holding_days']}d",
                        "Qty": p["quantity"],
                        "Entry": f"${p['avg_entry_price']:.2f}",
                        "Now": f"${p['current_price']:.2f}",
                        "Stop / Target": f"${p['stop_loss_price']:.2f} / ${p['take_profit_price']:.2f}" if p.get("stop_loss_price") else "-",
                        "Unrealised P&L": f"${p['unrealised_pnl']:+,.2f} ({p['unrealised_return_pct']:+.2f}%)",
                    }
                    for p in book_positions
                ]
                st.dataframe(clean_pos, width="stretch", hide_index=True)
            else:
                st.info("No open paper positions currently held in this book (100% cash at `$100,000.00`).")

        with p_col2:
            st.markdown("#### 3. Master vs. Per-Strategy `$100k` Paper Books Comparison")
            book_comparison_rows = [
                {
                    "Paper Book": "★ Master Combined ($100k)" if b["book_type"] == "MASTER_COMBINED" else f"Pod: {b['book_label']}",
                    "Account ID": b["account_id"],
                    "Equity": f"${b['total_equity']:,.2f}",
                    "Total P&L": f"${b['total_pnl']:+,.2f} ({b['total_return_pct']:+.2f}%)",
                    "Realised / Unrealised": f"${b['realised_pnl']:+,.0f} / ${b['unrealised_pnl']:+,.0f}",
                    "Win Rate": f"{b['win_rate_pct']:.1f}% ({b['closed_sells']} closed)" if b["closed_sells"] > 0 else "— (0 closed)",
                    "Open / Cash": f"{b['open_positions_count']} open · ${b['cash_balance']:,.0f}",
                }
                for b in all_paper_books
            ]
            st.dataframe(book_comparison_rows, width="stretch", hide_index=True)
            strat_pnl_rows = _summarize_pnl_by_strategy(book_ledger, book_positions, strats)
            if strat_pnl_rows:
                with st.expander("View Strategy Attribution Inside Selected Book", expanded=False):
                    st.dataframe(strat_pnl_rows, width="stretch", hide_index=True)

        st.markdown("---")
        st.markdown(f"#### 4. Day-Filtered Paper Execution Ledger (`{book_date_span}`)")
        if book_ledger:
            unique_days = sorted({str(l["fill_date"]) for l in book_ledger if l.get("fill_date")}, reverse=True)
            unique_strats = sorted({f"{l['strategy_id']} v{l['strategy_version']}" for l in book_ledger})

            f_col1, f_col2, f_col3 = st.columns([2, 1.5, 2])
            with f_col1:
                selected_day = st.selectbox(
                    "Filter by Trading Day",
                    options=["All Trading Days"] + unique_days,
                    index=0,
                    key="paper_ledger_day_filter",
                )
            with f_col2:
                selected_side = st.selectbox(
                    "Filter by Order Side",
                    options=["All Sides (BUY & SELL)", "BUY (Entries Only)", "SELL (Exits Only)"],
                    index=0,
                    key="paper_ledger_side_filter",
                )
            with f_col3:
                selected_strat = st.selectbox(
                    "Filter by Strategy",
                    options=["All Strategies"] + unique_strats,
                    index=0,
                    key="paper_ledger_strat_filter",
                )

            filtered_ledger = [
                l
                for l in book_ledger
                if (selected_day == "All Trading Days" or str(l.get("fill_date")) == selected_day)
                and (
                    selected_side == "All Sides (BUY & SELL)"
                    or (selected_side.startswith("BUY") and l.get("side") == "BUY")
                    or (selected_side.startswith("SELL") and l.get("side") == "SELL")
                )
                and (
                    selected_strat == "All Strategies"
                    or f"{l['strategy_id']} v{l['strategy_version']}" == selected_strat
                )
            ]

            buy_count = sum(1 for l in filtered_ledger if l.get("side") == "BUY")
            sell_count = sum(1 for l in filtered_ledger if l.get("side") == "SELL")
            traded_vol = sum(float(l.get("gross_amount", 0.0)) for l in filtered_ledger)
            day_costs = sum(
                float(l.get("commission_usd", 0.0)) + float(l.get("slippage_usd", 0.0))
                for l in filtered_ledger
            )
            day_realised = sum(
                float(l.get("realised_pnl", 0.0)) for l in filtered_ledger if l.get("side") == "SELL"
            )

            s1, s2, s3, s4, s5 = st.columns(5)
            s1.metric("Trades Executed", f"{len(filtered_ledger)} fills", f"{buy_count} BUY · {sell_count} SELL")
            s2.metric("BUY Entries", f"{buy_count}", "New positions opened")
            s3.metric("SELL Exits", f"{sell_count}", "Positions closed")
            s4.metric("Traded Volume", f"${traded_vol:,.2f}", f"Costs: ${day_costs:.2f}")
            s5.metric("Realised P&L (Filtered)", f"${day_realised:+,.2f}", "Locked-in on SELLs")

            clean_ledger = [
                {
                    "Trading Day": l["fill_date"],
                    "Action": "🟢 BUY (Entry)" if l["side"] == "BUY" else "🔴 SELL (Exit)",
                    "Ticker": l["ticker"],
                    "Quantity": l["quantity"],
                    "Fill Price": f"${l['fill_price']:.2f}",
                    "Gross Notional": f"${l['gross_amount']:,.2f}",
                    "Fees + Slip": f"${float(l['commission_usd']) + float(l['slippage_usd']):.2f}",
                    "Realised P&L": f"${l['realised_pnl']:+,.2f}" if l["side"] == "SELL" else "— (Open Entry)",
                    "Cash After Fill": f"${l['cash_after']:,.2f}",
                    "Strategy": f"{l['strategy_id']} v{l['strategy_version']}",
                    "Execution Rationale": l["notes"],
                }
                for l in filtered_ledger
            ]
            st.dataframe(clean_ledger, width="stretch", hide_index=True)
        else:
            st.info(
                "This Paper Book is clean at $100,000.00 cash with 0 trades executed. "
                "New trades will appear here automatically after each forward daily run (`21:30 UTC` or `run` in IDE)."
            )

    # =========================================================================
    # TAB 2: STRATEGIES, RULES & BACKTESTS (EVERYTHING ABOUT EACH STRATEGY IN ONE PLACE)
    # =========================================================================
    with tabs[2]:
        _render_tab_header(
            st,
            "Strategies, Rules & Backtests: Everything about how each strategy is conceived, its exact entry/exit rulebook, 9-gate SPY benchmark audit, historical trade logs, and 1-click Golden Base (v1) revert.",
            "How Strategies are Conceived & Validated",
            "**Everything About Each Strategy in One Unified Place:**\n\n"
            "1. **How Strategies Are Conceived**: Built on 5 institutional swing anomalies (`Momentum Trend`, `Post-Earnings Drift`, `Volatility Breakout`, `Mean Reversion`, `Sector Rotation Leaders`). Weekly AI discovery (`StrategyDiscoveryAgent`) and IDE `run` cycles propose parameter refinements (`v2+`).\n"
            "2. **9-Gate + SPY Dominance Exam**: Every strategy must pass 9 quantitative gates and beat the S&P 500 (`SPY`) in both Full Period (`2023–2025`) and Out-of-Sample (`OOS`) before trading.\n"
            "3. **Golden Base (`v1`) Safety Net**: `v1 ★ Base` strategies are permanently pinned. Future versions (`v2+`) are only promoted if they beat the incumbent champion—and you can revert to `v1` in one click.",
        )

        st.markdown("#### 1. Strategy Scorecard & SPY Benchmark Readiness")
        rb_col1, rb_col2, rb_col3 = st.columns([2.4, 1.3, 1.3])
        with rb_col1:
            st.caption(
                "**Golden Base Safeguard**: All 5 `v1 ★ Base` models beat `SPY` "
                "in Full Period (`+70.7%` to `+77.5%` vs SPY `+61.9%`) and Out-of-Sample (`+11.5%` to `+23.0%` vs SPY `+9.7%`). "
                "Expand any strategy below to see **how it was conceived, its exact entry/exit rules, its 9-gate audit, and its historical backtest trades**."
            )
        with rb_col2:
            if st.button(
                "Revert All to Golden Base (v1)",
                width="stretch",
                help="Immediately restores all Golden Base v1 models to PAPER_TRADING and retires any experimental v2+ versions.",
            ):
                app.orchestrator.registry.revert_to_golden_baseline()
                st.rerun()
        with rb_col3:
            if st.button(
                "Enforce Best Champion Versions",
                width="stretch",
                help="Ensures the highest-performing evaluated version (by Return & Sharpe) of each strategy family is active.",
            ):
                for sid in {s["strategy_id"] for s in strats}:
                    app.orchestrator.registry.rollback_to_best_champion(sid)
                st.rerun()

        display_scorecard = [
            {k: v for k, v in r.items() if not k.startswith("_")}
            for r in readiness_rows
        ]
        st.dataframe(display_scorecard, width="stretch", hide_index=True)

        # Index latest experiment per strategy version so we can show historical trades directly inside each strategy card
        exp_by_strat_ver: Dict[str, Dict[str, Any]] = {}
        for exp in state["experiments"]:
            k_sv = f"{exp['strategy_id']}:{exp['version']}"
            if k_sv not in exp_by_strat_ver:
                exp_by_strat_ver[k_sv] = exp

        st.markdown("#### 2. Complete Strategy Encyclopaedia — Origin, Exact Rules, 9-Gate Audit & Historical Backtest Trades")
        for r in readiness_rows:
            s = r["_raw_strategy"]
            k_sv = f"{s['strategy_id']}:{s['version']}"
            m = s.get("backtest_summary") or {}
            val = s.get("validation_summary") or {}
            oos = val.get("oos_metrics") or {}
            wf = val.get("walk_forward") or {}
            checks = r["_checks"]
            fam = str(s.get("strategy_family", "MOMENTUM_TREND"))
            genesis = STRATEGY_GENESIS_BY_FAMILY.get(fam, STRATEGY_GENESIS_BY_FAMILY["MOMENTUM_TREND"])
            exp_match = exp_by_strat_ver.get(k_sv)

            header_label = (
                f"{r['Strategy']} — {r['Name']} ({fam})  ·  Status: {r['Status']}  ·  "
                f"Full: {m.get('total_return_pct', 0.0):+.2f}% (vs SPY {m.get('benchmark_return_pct', 0.0):+.2f}%)  ·  "
                f"OOS: {oos.get('total_return_pct', 0.0):+.2f}%"
            )
            with st.expander(header_label, expanded=False):
                # Row A: How it is conceived + Exact Entry/Exit/Risk Rules
                g_col1, g_col2 = st.columns([1.3, 1.7])
                with g_col1:
                    st.markdown("**A. How This Strategy Is Conceived & Economic Edge**")
                    st.write(f"- **Quantitative Origin**: {genesis['origin']}")
                    st.write(f"- **Why It Generates Alpha**: {genesis['edge']}")
                    st.write(f"- **Target Market Regime**: {genesis['regime']}")
                    st.write(f"- **Version Hypothesis (`v{s['version']}`)**: {s['hypothesis']}")
                    st.write(f"- **Holding Horizon**: `{s['holding_period_min_days']}` to `{s['holding_period_max_days']}` trading days")
                    st.write(f"- **Tradable Universe ({len(s['universe'])} stocks)**: `{', '.join(s['universe'])}`")
                with g_col2:
                    st.markdown("**B. Exact Machine-Readable Rulebook (`entry_rules`, `exit_rules`, `risk_params`)**")
                    rule_c1, rule_c2, rule_c3 = st.columns(3)
                    with rule_c1:
                        st.caption("**Entry Rules (`BUY` Trigger)**")
                        for rk, rv in (s.get("entry_rules") or {}).items():
                            st.write(f"- `{rk}`: **{rv}**")
                    with rule_c2:
                        st.caption("**Exit & Stop-Ratchet Rules (`SELL`)**")
                        for rk, rv in (s.get("exit_rules") or {}).items():
                            st.write(f"- `{rk}`: **{rv}**")
                    with rule_c3:
                        st.caption("**Position Sizing & Risk Caps**")
                        for rk, rv in (s.get("risk_params") or {}).items():
                            st.write(f"- `{rk}`: **{rv}**")

                st.markdown("---")
                # Row B: 9-Gate Audit + SPY Benchmark Dominance + Version Control
                c_left, c_mid, c_right = st.columns([1.2, 1.5, 1.3])
                with c_left:
                    st.markdown("**C. 9-Gate Validation Audit**")
                    if checks:
                        for gate_name, passed in checks.items():
                            icon = "PASS" if passed else "FAIL"
                            clean_gate = gate_name.replace("_", " ").title()
                            st.write(f"- **[{icon}]** {clean_gate}")
                    else:
                        st.write(s.get("promotion_decision_reason", "No gate breakdown recorded."))
                with c_mid:
                    st.markdown("**D. Benchmark Dominance vs. S&P 500 (`SPY`)**")
                    st.write(
                        f"- **Full Return (`2023–2025`)**: `{m.get('total_return_pct', 0.0):+.2f}%` vs SPY `{m.get('benchmark_return_pct', 0.0):+.2f}%` "
                        f"(**Excess: `{m.get('excess_return_vs_spy_pct', 0.0):+.2f}%`** · `$100k → ${m.get('final_equity', 100000.0):,.0f}`)"
                    )
                    st.write(
                        f"- **Out-of-Sample (`OOS`)**: `{oos.get('total_return_pct', 0.0):+.2f}%` vs SPY `{oos.get('benchmark_return_pct', 0.0):+.2f}%` "
                        f"(**OOS Excess: `{float(oos.get('total_return_pct', 0.0)) - float(oos.get('benchmark_return_pct', 0.0)):+.2f}%`**)"
                    )
                    st.write(
                        f"- **Recent 6-Month Regime (`126d`)**: `{m.get('recent_6m_return_pct', 0.0):+.2f}%` "
                        f"(vs SPY `{m.get('recent_6m_spy_return_pct', 0.0):+.2f}%` · **Excess `{m.get('recent_6m_excess_vs_spy_pct', 0.0):+.2f}%`** · "
                        f"6M Win Rate `{m.get('recent_6m_win_rate_pct', m.get('win_rate_pct', 0.0)):.1f}%`)"
                    )
                    st.write(
                        f"- **Rolling 6-Month Consistency & SQN**: `{m.get('rolling_6m_win_pct', 100.0):.1f}%` of rolling 6M windows profitable · "
                        f"`SQN = {m.get('sqn_score', 0.0):.2f}` · `Payoff = {m.get('payoff_ratio', 1.5):.2f}x`"
                    )
                    st.write(
                        f"- **Jensen's Alpha & Beta**: `α = {m.get('alpha_annualised_pct', 0.0):+.2f}%/yr` · "
                        f"`β = {m.get('beta_vs_spy', 0.0):.2f}` · `Info Ratio = {m.get('information_ratio', 0.0):.2f}`"
                    )
                    st.write(
                        f"- **Upside / Downside Capture**: `{m.get('upside_capture_pct', 0.0):.1f}%` up / "
                        f"`{m.get('downside_capture_pct', 0.0):.1f}%` down (**Ratio: `{m.get('capture_ratio', 0.0):.2f}x`**)"
                    )
                    st.write(
                        f"- **Drawdown & Ulcer**: MaxDD `-{m.get('max_drawdown_pct', 0.0):.2f}%` · "
                        f"Ulcer Index `{m.get('ulcer_index', 0.0):.2f}` · Martin `{m.get('martin_ratio', 0.0):.2f}` · "
                        f"Under Water `{m.get('max_time_under_water_days', 0)}d`"
                    )
                    st.write(
                        f"- **Trade Statistics**: `{m.get('trade_count', 0)}` trades · Win Rate `{m.get('win_rate_pct', 0.0):.1f}%` · "
                        f"Expectancy `${m.get('expectancy_usd', 0.0):+,.2f}/trade` · Omega `{m.get('omega_ratio', 1.0):.2f}` · "
                        f"ROIC `{m.get('roic_annualised_pct', 0.0):.1f}%/yr` · WF `{float(wf.get('consistency_ratio', 0.0))*100:.0f}%`"
                    )
                with c_right:
                    st.markdown("**E. Forward Paper Track Record & Version Control**")
                    g1_ok = r["Gates"].startswith("9 / 9")
                    g2_ok = r["_paper_closed"] >= 20
                    g3_ok = r["_paper_pf"] >= 1.3 and r["_paper_closed"] > 0
                    g4_ok = r["_paper_net_pnl"] > 0
                    st.write(f"- **[{'PASS' if g1_ok else 'WAIT'}]** Passed all 9 historical & SPY gates (`{r['Gates']}`)")
                    st.write(f"- **[{'PASS' if g2_ok else 'WAIT'}]** 20+ forward paper trades (`{r['_paper_closed']} / 20`)")
                    st.write(f"- **[{'PASS' if g3_ok else 'WAIT'}]** Forward Paper PF $\\ge 1.30$ (`{r['_paper_pf']:.2f}`)")
                    st.write(f"- **[{'PASS' if g4_ok else 'WAIT'}]** Positive Forward Paper P&L (`${r['_paper_net_pnl']:+,.2f}`)")
                    if st.button(
                        f"Revert {s['strategy_id']} to Golden Base (v1)",
                        key=f"revert_v1_{s['strategy_id']}_{s['version']}",
                        width="stretch",
                    ):
                        app.orchestrator.registry.revert_to_golden_baseline(s["strategy_id"])
                        st.rerun()

                if exp_match and exp_match.get("trades"):
                    st.markdown(f"**F. Historical Backtest Trades for `{s['strategy_id']} v{s['version']}` (Showing Latest 25 of `{len(exp_match['trades'])}` Trades)**")
                    st.dataframe(exp_match["trades"][:25], width="stretch", hide_index=True)

    # =========================================================================
    # TAB 3: AI RESEARCH & IDE BRIDGE (DAILY WATCHLIST + DIRECT AI PROMPT/JSON FEED)
    # =========================================================================
    with tabs[3]:
        _render_tab_header(
            st,
            "AI Research & IDE Bridge: Daily multi-factor stock rankings, IDE AI reminder checklist, and a direct Prompt-to-Engine JSON bridge to feed AI outputs straight into the trading engine.",
            "How the IDE AI Bridge works",
            "**Two Ways to Incorporate AI into Your Daily/Weekly Loop ($0 API Cost):**\n\n"
            "1. **Automatic 1-Word Trigger in Antigravity IDE (Recommended)**: Simply type **`run`** in the Antigravity IDE chat. The IDE agent automatically runs `ide-context`, searches live web news (`search_web`), tests 2–3 strategy upgrades (`ide-apply`), and pushes to GitHub.\n"
            "2. **Direct Prompt-to-Engine JSON Feed (Right Here in the UI)**: Copy the auto-generated **Ready-to-Paste AI Prompt** below into any LLM (or IDE chat), paste its JSON output into the box on the right, and click **`Apply AI Output to Engine`**. It immediately enriches stock catalysts, runs the 9-gate strategy tournament, and updates your Live Copilot plan!",
        )

        if st.session_state.get("_ide_bridge_flash"):
            st.success(st.session_state.pop("_ide_bridge_flash"))

        # Section 1: IDE AI Reminder & Direct Prompt-to-Engine Feed
        st.markdown("#### 1. IDE AI Alpha Booster & Direct Prompt-to-Engine Feed")
        ai_c1, ai_c2 = st.columns([1.25, 1.35])
        top_reps = state["research_reports"][:5]
        compact_prompt_context = [
            {
                "ticker": r["ticker"],
                "price": r["current_price"],
                "sector": r["market_and_sector_context"]["sector"],
                "rs_20d_vs_spy_pct": r["relative_strength_vs_spy_20d"],
                "volume_ratio_20": r["volume_analysis"]["volume_ratio_20"],
                "suggested_family": r["suggested_strategy_family"],
            }
            for r in top_reps
        ]
        ready_prompt_text = (
            f"You are the Chief Quantitative Swing Strategist. Today is {today_iso} (latest market close: {latest_bar_date}).\n"
            f"Top ranked US equity candidates: {json.dumps(compact_prompt_context)}\n\n"
            "Search live news/earnings catalysts for the top tickers and propose 1-2 regime-tuned strategy parameter upgrades "
            "to maximize Out-of-Sample Net P&L and SPY Excess Return. Return ONLY valid JSON matching this exact schema:\n"
            "{\n"
            '  "research_updates": [\n'
            '    {"ticker": "NVDA", "bullish_thesis": "...", "bearish_thesis": "...", "catalyst_assessment": "...", "sentiment_score": 0.80, "research_confidence_score": 0.90}\n'
            "  ],\n"
            '  "analyst_proposal": {\n'
            '    "target_strategy_id": "strat_momentum_trend", "market_regime": "BULL_LOW_VOL", "diagnosis_summary": "...", "proposed_hypothesis": "..."\n'
            "  },\n"
            '  "candidate_strategies": [\n'
            '    {"target_strategy_id": "strat_momentum_trend", "hypothesis": "...", "entry_rules_patch": {"rs_20d_min": 0.025}, "exit_rules_patch": {"take_profit_atr_mult": 4.2}}\n'
            "  ]\n"
            "}"
        )

        with ai_c1:
            st.markdown("##### Option A: Type `run` in Antigravity IDE (1-Word Automation)")
            st.info(
                f"**Last IDE AI Run**: `{last_ide_run_ts}`\n\n"
                "- **In Antigravity IDE Chat**: Just type **`run`**.\n"
                "- The IDE agent automatically executes `python3 main.py ide-context`, performs live web searches (`search_web`), "
                "evaluates candidate strategies via `python3 main.py ide-apply`, and pushes the updated database."
            )
            with st.expander("Copy Ready-to-Use AI Prompt (For Any LLM or Manual Chat)", expanded=False):
                st.code(ready_prompt_text, language="json")

        with ai_c2:
            st.markdown("##### Option B: Paste AI JSON Output Directly into Engine")
            default_sample_json = json.dumps(
                {
                    "research_updates": [
                        {
                            "ticker": top_reps[0]["ticker"] if top_reps else "NVDA",
                            "bullish_thesis": "Strong institutional relative strength vs SPY with expanding volume.",
                            "bearish_thesis": "Watch sector multiple compression if treasury yields spike.",
                            "catalyst_assessment": "Positive institutional accumulation following earnings guidance.",
                            "sentiment_score": 0.78,
                            "research_confidence_score": 0.88,
                        }
                    ],
                    "candidate_strategies": [],
                },
                indent=2,
            )
            ai_json_input = st.text_area(
                "Paste JSON from IDE / LLM (`research_updates`, `analyst_proposal`, `candidate_strategies`)",
                value=default_sample_json,
                height=155,
                key="ide_bridge_json_textarea",
            )
            if st.button("Apply AI Output to Engine (Enrich Research & Run 9-Gate Tournament)", width="stretch"):
                try:
                    parsed_payload = json.loads(ai_json_input)
                    res_apply = app.orchestrator.apply_ide_ai_cycle(payload=parsed_payload)
                    enriched_n = len(res_apply.get("research_tickers_enriched") or [])
                    tourn_list = res_apply.get("tournament_results") or []
                    prom_n = sum(1 for t in tourn_list if t.get("promoted"))
                    st.session_state["_ide_bridge_flash"] = (
                        f"Applied AI output for session `{res_apply['session_date']}`: "
                        f"enriched `{enriched_n}` research report(s) and tested `{len(tourn_list)}` candidate strategy version(s) "
                        f"(`{prom_n}` promoted, Champion protection active)."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Invalid AI JSON payload: {exc}")

        st.markdown("---")
        st.markdown("#### 2. Ranked US Equity Candidates (`MarketResearchAgent` + IDE AI Catalyst Enrichment)")
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
                "Catalyst Assessment": r.get("catalyst_assessment", ""),
                "Bullish Thesis": r["bullish_thesis"],
                "Key Risk / Bearish Case": r["bearish_thesis"],
            }
            for idx, r in enumerate(state["research_reports"])
        ]
        st.dataframe(reports_summary, width="stretch", hide_index=True)

        with st.expander("View Post-Session Experiment Proposals (`PerformanceAnalystAgent`)", expanded=False):
            st.dataframe(state["proposals"], width="stretch")

    # =========================================================================
    # TAB 4: RISK, WALK-FORWARD & LOGS
    # =========================================================================
    with tabs[4]:
        _render_tab_header(
            st,
            "Risk, Walk-Forward & Logs: Real-time sector exposure vs. the 30% cap, 4-window Walk-Forward folds, risk vetoes, and automation logs.",
            "How this tab works",
            "**Portfolio Risk & Governance Audit:**\n\n"
            "- **Sector Concentration**: Verifies that no single GICS sector exceeds `30.0%` of portfolio equity.\n"
            "- **Walk-Forward Validation Folds**: Splits historical data into 4 rolling time windows to verify consistent out-of-sample profitability.\n"
            "- **Risk Vetoes & Job Logs**: Tracks every trade blocked by the Risk Manager and every scheduled or IDE AI workflow execution.",
        )
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Sector Concentration vs. 30% Cap")
            if acc["sector_exposures_pct"]:
                sec_rows = [
                    {"Sector": sec, "Portfolio Exposure": f"{pct:.2f}%", "Hard Limit": "30.00%"}
                    for sec, pct in acc["sector_exposures_pct"].items()
                ]
                st.dataframe(sec_rows, width="stretch", hide_index=True)
            else:
                st.info("0% paper sector exposure (100% cash).")
        with c2:
            st.markdown("#### Walk-Forward Validation Folds (4 Rolling Windows)")
            if strats:
                strat_labels = [f"{s['strategy_id']} v{s['version']} ({s['name']})" for s in strats]
                sel_idx = st.selectbox(
                    "Select Strategy to Inspect Walk-Forward Folds",
                    options=list(range(len(strats))),
                    format_func=lambda i: strat_labels[i],
                    key="wf_strat_select",
                )
                chosen_s = strats[sel_idx]
                if chosen_s.get("validation_summary"):
                    wf_windows = (chosen_s["validation_summary"].get("walk_forward") or {}).get("windows", [])
                    st.dataframe(wf_windows, width="stretch", hide_index=True)

        st.markdown("---")
        l_col1, l_col2 = st.columns(2)
        with l_col1:
            st.markdown("#### Portfolio Risk Vetoes & Alerts")
            if state["risk_alerts"]:
                st.dataframe(state["risk_alerts"], width="stretch")
            else:
                st.write("No risk alerts triggered.")
        with l_col2:
            st.markdown("#### Autonomous & IDE AI Workflow Execution Log")
            st.dataframe(state["jobs"], width="stretch")

    # =========================================================================
    # TAB 5: PLATFORM GUIDE (MENTAL MODEL, WALKTHROUGH & DEEP DIVES)
    # =========================================================================
    with tabs[5]:
        st.markdown("#### What This System Does & How It Maximizes Risk-Adjusted P&L")
        st.write(
            "This platform manages both a **Real-Account Live Trading Copilot** (Tab 1) and a forward **$100,000 Paper Portfolio** (Tab 2) "
            "over **3 to 15 trading-day** swing horizons. **Deterministic mathematical code** computes indicators, enforces 7 risk guardrails, "
            "and executes backtests, while **AI agents** (and your 1-word **`run`** command in the Antigravity IDE) enrich stock catalysts and "
            "test regime-adapted strategy upgrades."
        )

        st.markdown(MENTAL_MODEL_HTML, unsafe_allow_html=True)

        st.markdown("##### Interactive Walkthrough — Click Any Topic Below")
        if "walkthrough_step" not in st.session_state:
            st.session_state["walkthrough_step"] = "step_daily_vs_weekly"

        b1, b2, b3, b4, b5 = st.columns(5)
        if b1.button("1. Daily vs Weekly Loop", width="stretch"):
            st.session_state["walkthrough_step"] = "step_daily_vs_weekly"
        if b2.button("2. The 5 Golden Base Models", width="stretch"):
            st.session_state["walkthrough_step"] = "step_multi_strategy"
        if b3.button("3. Risk & Profit Ratchets", width="stretch"):
            st.session_state["walkthrough_step"] = "step_risk"
        if b4.button("4. SPY Dominance & Revert", width="stretch"):
            st.session_state["walkthrough_step"] = "step_readiness"
        if b5.button("5. Using IDE AI (`run`)", width="stretch"):
            st.session_state["walkthrough_step"] = "step_user_role"

        step_info = {
            "step_daily_vs_weekly": (
                "**1. Daily Run, Weekly Run & Exact Order Execution Timing**\n\n"
                "- **Daily Run (`Mon–Fri >16:00 ET / 21:30 UTC`)**: Computes signals from completed daily closing bars (eliminating intraday look-ahead bias), evaluates exits and `+1.0R` stop-loss ratchets on open holdings, and filters new `BUY` candidates through the AI Catalyst Veto (`sentiment <= -0.35`) & 7-rule Risk Manager.\n"
                "- **When & How to Execute Orders (`9:30–9:45 AM ET Open Limit`)**: Place **Limit Orders inside the Buy-Zone (`$Low – $MaxChase`, i.e., `Ref - 0.25 ATR` to `Ref + 0.50 ATR`)** during regular market open (`9:30–9:45 AM ET`). Never chase opening gaps above `Max Chase`, and never trade illiquid pre-market/after-hours.\n"
                "- **Weekly Run (`Saturday 10:00 SGT`)**: Reviews closed trade attribution, drafts candidate strategy versions (`v+1`), and tests them in the 9-gate Out-of-Sample & Walk-Forward tournament."
            ),
            "step_multi_strategy": (
                "**2. Five Uncorrelated Golden Base (`v1 ★ Base`) Models — 2.3-Yr, Recent 6M & `SQN` Evidence**\n\n"
                "- **`strat_volatility_breakout`**: `+77.54%` Full · `+21.96%` OOS · **`+11.03%` Recent 6M (`67.9%` WR)** · `98.3%` Rolling 6M Win · **`SQN 3.55`**\n"
                "- **`strat_mean_reversion_bb`**: `+74.07%` Full · `+10.17%` OOS · **`+10.11%` Recent 6M (`64.7%` WR)** · `86.1%` Rolling 6M Win · **`SQN 2.85`**\n"
                "- **`strat_momentum_trend`**: `+71.44%` Full · `+16.32%` OOS · **`+7.49%` Recent 6M (`61.5%` WR)** · `91.1%` Rolling 6M Win · **`SQN 3.29`**\n"
                "- **`strat_pead_drift`**: `+73.80%` Full · `+17.75%` OOS · **`+4.73%` Recent 6M (`51.5%` WR)** · `96.1%` Rolling 6M Win · **`SQN 2.99`**\n"
                "- **`strat_sector_rotation_leaders`**: `+67.32%` Full · `+18.49%` OOS · **`+6.87%` Recent 6M (`57.7%` WR)** · `91.7%` Rolling 6M Win · **`SQN 2.91`**"
            ),
            "step_risk": (
                "**3. What Happens If Target Is Not Hit? (4-Way Exit Bracket & 7 Risk Guardrails)**\n\n"
                "- **`+1.0R` to `+1.25R` Stop Ratchet**: Once a trade reaches `+1.0R` unrealized profit (`breakeven_ratchet_price` on your BUY card), raise your Stop-Loss to Breakeven / Chandelier trail (`Highest High - k * ATR`). Even if the full Take-Profit is not hit, a reversal locks in a winning trade.\n"
                "- **Momentum Stall & `Day N` Time-Stop (`8–15` days)**: Exits early if trend alignment breaks (`Close < SMA20` or `RSI >= 68`), or exits on Day $N_{\\max}$ if neither Target nor Stop is hit.\n"
                "- **Hard Portfolio Caps**: `1.0%` max risk per trade (`0.65%` if drawdown $\\ge 7.5\\%$), `5.0%` max open portfolio heat, `15.0%` single stock, `30.0%` single sector, and `15.0%` drawdown circuit breaker."
            ),
            "step_readiness": (
                "**4. Dual-Horizon Validation (`2.3-Yr` + `6-Month` + `SQN`) & What to Monitor Weekly**\n\n"
                "- **Dual-Horizon + `SPY` Dominance**: Every strategy must survive 2.3 years (`4/4` Walk-Forward folds), beat `SPY` (`+61.90%` Full, `+9.67%` OOS, `+3.39%` Recent 6M), and achieve high trade consistency (`SQN >= 2.85`).\n"
                "- **Weekly Monitoring Checklist**: (1) Forward Win Rate (`50%–68%`) & Profit Factor (`>= 1.30`); (2) Broker fill prices staying inside the `Buy-Zone Limit`; (3) Portfolio heat `<= 5.0%` & sector `<= 30.0%`; (4) `Last IDE AI Run` freshness in sidebar; (5) If any experimental `v2+` model drops below `45%` WR after 10+ trades, click **`Revert All to Golden Base (v1)`** in Tab 3."
            ),
            "step_user_role": (
                "**5. Your Optimal Workflow & Future Roadmap**\n\n"
                "1. **Type `run` in Antigravity IDE** (or paste JSON in Tab 4) on trading days so live web news catalysts (`search_web`) automatically veto bearish traps (`<= -0.35`) and boost high-catalyst setups (`>= +0.25`).\n"
                "2. **Execute at Market Open (`9:30–9:45 AM ET`)**: Place Limit Orders inside the `Buy-Zone Limit ($Low – $MaxChase)` and click `✓ Bought` / `✓ Sold` in Tab 1 after broker execution.\n"
                "3. **Future Upgrades Roadmap**: Dynamic Top-100 S&P/Nasdaq liquid universe expansion, `50%` partial profit scaling at `+1.5R`, and 30-minute Opening Range Breakout (`ORB`) confirmation."
            ),
        }
        st.info(step_info[st.session_state["walkthrough_step"]])


if __name__ == "__main__":
    main()
