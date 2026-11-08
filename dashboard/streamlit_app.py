"""Streamlit Community Cloud & Local Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

Minimalist, institutional-grade layout with top-of-mind operator hierarchy:
1. Live Copilot — Today's trading-day-aware action checklist, 1-click confirmations, and ledger-driven real account.
2. Paper Portfolio — Two-tier forward $100k books (Master Combined + 5 Strategy Pods) and execution ledger.
3. Strategies & Backtests — Unified hub for strategy thesis, machine-readable rules, 9-gate SPY audit, and backtest trades.
4. AI & Watchlist — Daily ranked candidates and direct Prompt-to-Engine JSON bridge (`apply_ide_ai_cycle`).
5. Risk & Logs — Sector concentration vs. 30% cap, 4-window Walk-Forward folds, risk vetoes, and job logs.
6. Guide — Visual architecture diagram, interactive walkthrough, and expandable deep dives.
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

CLASSY_MINIMAL_CSS = """
<style>
  /* Compact, balanced layout container */
  .block-container {
    padding-top: 1.4rem !important;
    padding-bottom: 2.5rem !important;
    max-width: 1440px !important;
  }
  /* Crisp institutional metric cards */
  [data-testid="stMetric"] {
    background: rgba(15, 23, 42, 0.45);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 8px;
    padding: 12px 15px !important;
  }
  [data-testid="stMetricLabel"] {
    font-size: 0.73rem !important;
    text-transform: uppercase;
    letter-spacing: 0.045em;
    color: #94a3b8 !important;
    font-weight: 600 !important;
  }
  [data-testid="stMetricValue"] {
    font-size: 1.42rem !important;
    font-weight: 600 !important;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
  }
  [data-testid="stMetricDelta"] {
    font-size: 0.76rem !important;
    font-variant-numeric: tabular-nums;
  }
  /* Clean navigation tabs */
  [data-baseweb="tab-list"] {
    gap: 8px !important;
    border-bottom: 1px solid rgba(148, 163, 184, 0.16) !important;
    padding-bottom: 2px !important;
  }
  [data-baseweb="tab"] {
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    padding: 8px 14px !important;
    letter-spacing: 0.01em;
  }
  /* Subtle horizontal dividers */
  hr {
    margin: 1.05rem 0 !important;
    border-color: rgba(148, 163, 184, 0.14) !important;
  }
  /* Clean typography for headings */
  h1, h2, h3, h4, h5 {
    letter-spacing: -0.015em !important;
    font-weight: 600 !important;
  }
  /* Anti-Race-Condition Lock: Automatically disable all buttons/inputs & show loading banner while Streamlit is executing */
  body:has([data-testid="stStatusWidget"]) button,
  body:has([data-testid="stStatusWidget"]) input,
  body:has([data-testid="stStatusWidget"]) [data-baseweb="select"] {
    pointer-events: none !important;
    opacity: 0.52 !important;
    cursor: wait !important;
    transition: opacity 0.12s ease-in-out;
  }
  body:has([data-testid="stStatusWidget"])::after {
    content: "Updating portfolio & reconciling ledger — controls locked...";
    position: fixed;
    top: 14px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(15, 23, 42, 0.94);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.45);
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 0.79rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    z-index: 999999;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
  }
</style>
"""


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
    return f"{dates[0]} to {dates[-1]} ({len(set(dates))} sessions)"


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
                "Name": strat_names.get(key, row["strategy_id"]),
                "Date Span": f"{row['fill_date']} → {row['fill_date']}",
                "_first_dt": row["fill_date"],
                "_last_dt": row["fill_date"],
                "Fills": 0,
                "Closed": 0,
                "_wins": 0,
                "_gross_profit": 0.0,
                "_gross_loss": 0.0,
                "Realised P&L ($)": 0.0,
                "Unrealised P&L ($)": 0.0,
                "Costs ($)": 0.0,
            },
        )
        item["Fills"] += 1
        item["_first_dt"] = min(item["_first_dt"], row["fill_date"])
        item["_last_dt"] = max(item["_last_dt"], row["fill_date"])
        item["Date Span"] = f"{item['_first_dt']} → {item['_last_dt']}"
        fees = float(row.get("commission_usd", 0.0)) + float(row.get("slippage_usd", 0.0))
        item["Costs ($)"] = round(item["Costs ($)"] + fees, 2)
        if row["side"] == "SELL":
            item["Closed"] += 1
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
                "Name": strat_names.get(key, pos["strategy_id"]),
                "Date Span": f"{pos['opened_date']} → Present",
                "_first_dt": pos["opened_date"],
                "_last_dt": pos["opened_date"],
                "Fills": 1,
                "Closed": 0,
                "_wins": 0,
                "_gross_profit": 0.0,
                "_gross_loss": 0.0,
                "Realised P&L ($)": 0.0,
                "Unrealised P&L ($)": 0.0,
                "Costs ($)": 0.0,
            },
        )
        item["Unrealised P&L ($)"] = round(
            item["Unrealised P&L ($)"] + float(pos.get("unrealised_pnl", 0.0)), 2
        )

    out: List[Dict[str, Any]] = []
    for item in by_strat.values():
        net_total = round(item["Realised P&L ($)"] + item["Unrealised P&L ($)"], 2)
        closed = item["Closed"]
        win_rate = (item["_wins"] / closed * 100.0) if closed > 0 else 0.0
        pf = (
            (item["_gross_profit"] / item["_gross_loss"])
            if item["_gross_loss"] > 0
            else (2.5 if item["_gross_profit"] > 0 else 0.0)
        )
        out.append(
            {
                "Strategy": item["Strategy"],
                "Name": item["Name"],
                "Span": item["Date Span"],
                "Fills": item["Fills"],
                "Closed": closed,
                "Win Rate": f"{win_rate:.1f}%" if closed > 0 else "—",
                "Profit Factor": f"{pf:.2f}" if closed > 0 else "—",
                "Realised ($)": item["Realised P&L ($)"],
                "Unrealised ($)": item["Unrealised P&L ($)"],
                "Net P&L ($)": net_total,
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
            readiness = "Rejected (Failed Gates)"
        elif status == "RETIRED":
            readiness = "Retired"
        elif passed_gates == total_gates and closed >= min_paper_trades and paper_pf >= 1.3 and net_paper > 0:
            readiness = f"Live Ready ({closed} paper trades)"
        elif passed_gates == total_gates and beats_spy_full and beats_spy_oos:
            readiness = f"Golden Base Ready ({closed}/{min_paper_trades} paper)"
        else:
            readiness = f"Paper Tracking ({closed}/{min_paper_trades})"

        start_eq = 100_000.0
        final_eq = float(m.get("final_equity", start_eq))
        net_bt_profit = final_eq - start_eq

        rows.append(
            {
                "Strategy": f"{s['strategy_id']} v{s['version']}" + (" · Base" if int(s["version"]) == 1 else ""),
                "Name": s["name"],
                "Status": status,
                "Gates": f"{passed_gates}/{total_gates}",
                "Full Return (vs SPY)": (
                    f"{m.get('total_return_pct', 0.0):+.1f}% "
                    f"(α {m.get('excess_return_vs_spy_pct', 0.0):+.1f}%)"
                ),
                "OOS (vs SPY)": (
                    f"{oos.get('total_return_pct', 0.0):+.1f}% "
                    f"(SPY {oos.get('benchmark_return_pct', 0.0):+.1f}%)"
                ),
                "Recent 6M": (
                    f"{m.get('recent_6m_return_pct', 0.0):+.1f}% · "
                    f"{m.get('recent_6m_win_rate_pct', m.get('win_rate_pct', 0.0)):.0f}% WR"
                ),
                "SQN · Payoff": (
                    f"{m.get('sqn_score', 0.0):.2f} · "
                    f"{m.get('payoff_ratio', 1.5):.2f}x"
                ),
                "Max DD": f"-{m.get('max_drawdown_pct', 0.0):.2f}%",
                "Readiness": readiness,
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
        "origin": "Cross-sectional intermediate relative strength (Jegadeesh & Titman) with dual SMA alignment.",
        "edge": "Institutional accumulation over multi-week cycles drives 4–14 day continuation when price holds above rising 20d/50d SMAs.",
        "regime": "Bull & steady uptrend regimes (`SPY > SMA50`).",
    },
    "PEAD": {
        "origin": "Post-Earnings Announcement Drift (`PEAD`, Bernard & Thomas) with point-in-time (`BMO`/`AMC`) visibility.",
        "edge": "Institutional under-reaction to quarterly EPS/revenue beats with volume surges creates multi-day upward drift.",
        "regime": "Earnings season across non-crash regimes.",
    },
    "BREAKOUT": {
        "origin": "Volatility Contraction Pattern (`VCP`) and 20-day Donchian channel breakout with volume expansion.",
        "edge": "Tight 10-day range compression (`<= 14%`) breaking above 20-day highs on `>= 1.1x` volume exhausts overhead supply.",
        "regime": "Consolidation-to-expansion transitions (`SPY > SMA50`).",
    },
    "MEAN_REVERSION": {
        "origin": "Short-horizon value-zone pullback inside a primary structural uptrend (`Close > SMA200`, `SPY > SMA50`).",
        "edge": "Liquid leaders pulling back 3–5 days (`RSI < 55` near `SMA20` / Lower Bollinger) attract institutional dip-buying.",
        "regime": "Rotational bull and sideways-up markets.",
    },
    "SECTOR_ROTATION": {
        "origin": "Top-Down GICS Sector Relative Strength Leadership paired with bottom-up stock momentum.",
        "edge": "Buying top momentum leaders inside the #1 and #2 ranked sectors captures concentrated institutional rotation.",
        "regime": "Sector-led bull and macro-rotation markets.",
    },
}


MENTAL_MODEL_HTML = """
<div style="background:rgba(15,23,42,0.55);border:1px solid rgba(148,163,184,0.16);border-radius:10px;padding:18px 20px;margin:8px 0 16px 0;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="font-size:0.74rem;text-transform:uppercase;letter-spacing:0.06em;color:#94a3b8;margin-bottom:10px;">
    Architecture — Autonomous Two-Loop Engine + IDE AI Catalyst Filter
  </div>
  <div style="margin-bottom:14px;">
    <div style="font-size:0.82rem;font-weight:600;color:#38bdf8;margin-bottom:6px;">
      1. Daily Execution Loop (Mon–Fri 21:30 UTC · Or Type "run" in Antigravity IDE)
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;font-size:0.79rem;">
      <div style="background:rgba(30,41,59,0.7);padding:9px 11px;border-radius:6px;border-left:2px solid #38bdf8;">
        <strong>1 · Market Data</strong><br/><span style="color:#94a3b8;">Daily closes &amp; point-in-time earnings.</span>
      </div>
      <div style="background:rgba(30,41,59,0.7);padding:9px 11px;border-radius:6px;border-left:2px solid #38bdf8;">
        <strong>2 · AI Catalysts</strong><br/><span style="color:#94a3b8;">Rank stocks &amp; veto bearish news (&le; -0.35).</span>
      </div>
      <div style="background:rgba(30,41,59,0.7);padding:9px 11px;border-radius:6px;border-left:2px solid #38bdf8;">
        <strong>3 · Signal Engine</strong><br/><span style="color:#94a3b8;">#1 Champion for BUYs; entry strat for SELLs.</span>
      </div>
      <div style="background:rgba(30,41,59,0.7);padding:9px 11px;border-radius:6px;border-left:2px solid #10b981;">
        <strong>4 · Risk Gate</strong><br/><span style="color:#94a3b8;">1% ATR risk sizing &amp; exposure caps.</span>
      </div>
      <div style="background:rgba(30,41,59,0.7);padding:9px 11px;border-radius:6px;border-left:2px solid #10b981;">
        <strong>5 · Copilot &amp; Pods</strong><br/><span style="color:#94a3b8;">Update Copilot Plan &amp; 6 Paper Books.</span>
      </div>
    </div>
  </div>
  <div>
    <div style="font-size:0.82rem;font-weight:600;color:#a855f7;margin-bottom:6px;">
      2. Weekly Self-Improvement Loop (Saturdays 10:00 SGT · 9-Gate Tournament)
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;font-size:0.79rem;">
      <div style="background:rgba(30,41,59,0.7);padding:9px 11px;border-radius:6px;border-left:2px solid #a855f7;">
        <strong>A · Attribution</strong><br/><span style="color:#94a3b8;">Review closed trades &amp; regime.</span>
      </div>
      <div style="background:rgba(30,41,59,0.7);padding:9px 11px;border-radius:6px;border-left:2px solid #a855f7;">
        <strong>B · Hypothesis</strong><br/><span style="color:#94a3b8;">Draft candidate version (v+1).</span>
      </div>
      <div style="background:rgba(30,41,59,0.7);padding:9px 11px;border-radius:6px;border-left:2px solid #f59e0b;">
        <strong>C · 9-Gate Audit</strong><br/><span style="color:#94a3b8;">Must beat SPY &amp; incumbent champion.</span>
      </div>
      <div style="background:rgba(30,41,59,0.7);padding:9px 11px;border-radius:6px;border-left:2px solid #10b981;">
        <strong>D · Promote / Revert</strong><br/><span style="color:#94a3b8;">Auto-promote v+1 or revert to v1 Base.</span>
      </div>
    </div>
  </div>
</div>
"""


def _render_tab_header(st: Any, summary: str, guide_title: str, guide_markdown: str) -> None:
    """Render a minimalist tab summary bar with a compact '? Guide' popover."""
    c_text, c_help = st.columns([4.6, 0.9])
    with c_text:
        st.caption(summary)
    with c_help:
        if hasattr(st, "popover"):
            with st.popover(f"? {guide_title}", width="stretch"):
                st.markdown(guide_markdown)
        else:
            with st.expander(f"? {guide_title}"):
                st.markdown(guide_markdown)


def _format_factors_html(factors: List[str]) -> str:
    """Format concise trade confidence factors into a clean, scannable HTML block."""
    if not factors:
        return ""
    items_html = "".join(
        f"<div style='margin-top:2px;'>• {f}</div>" for f in factors[:4]
    )
    return (
        "<div style='background:rgba(15,23,42,0.55);border-left:2px solid #38bdf8;"
        "padding:6px 10px;margin-top:5px;border-radius:4px;font-size:0.78rem;color:#94a3b8;'>"
        "<strong style='color:#cbd5e1;'>Factors Considered:</strong>"
        f"{items_html}</div>"
    )


def _render_removed_signals_section(st: Any, vetoed_sigs: List[Dict[str, Any]], context_label: str = "Live Copilot") -> None:
    """Render a clear, transparent summary of setups removed by AI findings, pre-open gaps, or risk caps."""
    if not vetoed_sigs:
        return
    ai_or_gap_removed = [
        v for v in vetoed_sigs
        if v.get("veto_rule") in ("AI_BEARISH_CATALYST_VETO", "PRE_OPEN_GAP_BREAKDOWN", "OVERNIGHT_EXTREME_GAP_UP")
    ]
    header_lbl = (
        f"Removed / Filtered Setups ({len(vetoed_sigs)}) — {len(ai_or_gap_removed)} Removed by Latest AI / Gap Check"
        if ai_or_gap_removed
        else f"Removed / Filtered Setups ({len(vetoed_sigs)} — Filtered by Cash / Exposure Caps)"
    )
    with st.expander(header_lbl, expanded=bool(ai_or_gap_removed)):
        for v in vetoed_sigs:
            removed_by = str(v.get("removed_by") or v.get("veto_rule") or "Risk Cap")
            is_ai = "AI" in removed_by or "AI" in str(v.get("veto_rule", ""))
            badge_color = "#f87171" if is_ai else ("#f59e0b" if "Gap" in removed_by else "#94a3b8")
            trig_txt = f" · Technical Setup: {v['technical_trigger']}" if v.get("technical_trigger") else ""
            st.markdown(
                f"<div style='padding:6px 10px;margin-bottom:6px;background:rgba(15,23,42,0.5);"
                f"border-left:3px solid {badge_color};border-radius:4px;font-size:0.81rem;'>"
                f"<strong>{v.get('ticker', '')}</strong> (<code>{v.get('strategy', '')}</code> · Ref <code>${float(v.get('reference_price') or 0.0):.2f}</code>) — "
                f"<span style='color:{badge_color};font-weight:600;'>{removed_by}</span><br/>"
                f"<span style='color:#cbd5e1;'>{v.get('reason', '')}</span>"
                f"<span style='color:#64748b;font-size:0.76rem;'>{trig_txt}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )


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
        page_title="Swing Trading AI",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CLASSY_MINIMAL_CSS, unsafe_allow_html=True)

    app = PlatformApplication()
    _code_version = "2026-11-08-v19"
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
        with st.spinner("Initializing baseline strategies (Backtesting only — Paper Account stays at $100k)..."):
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

    today_dt = date.today()
    today_iso = today_dt.isoformat()
    today_weekday_name = today_dt.strftime("%A")
    is_today_trading_day = USTradingCalendar.is_trading_day(today_dt)
    market_status_reason = USTradingCalendar.non_trading_reason(today_dt)
    next_trading_day_iso = USTradingCalendar.next_trading_day(today_dt, include_same_day=is_today_trading_day)

    ide_jobs = [j for j in jobs if j.get("job_name") == "ide_ai_cycle"]
    last_ide_job = ide_jobs[0] if ide_jobs else None
    last_ide_run_ts = str(last_ide_job["completed_at"])[:16].replace("T", " ") if (last_ide_job and last_ide_job.get("completed_at")) else "Not run yet"
    ide_ran_today = bool(last_ide_job and str(last_ide_job.get("completed_at", "")).startswith(today_iso))

    active_paper_strats = [s for s in strats if s["status"] == "PAPER_TRADING"]
    active_strat_names = (
        ", ".join(f"{s['name']} ({s['strategy_id']} v{s['version']})" for s in active_paper_strats)
        if active_paper_strats
        else "None active"
    )
    readiness_rows = _build_strategy_readiness_rows(strats, ledger, positions)
    golden_ready_count = sum(
        1 for r in readiness_rows if "Ready" in r["Live Trading Readiness"] or "READY" in r["Live Trading Readiness"]
    )

    copilot_data = state.get("copilot") or {}
    plan = copilot_data.get("action_plan") or app.orchestrator.live_copilot.get_daily_action_plan()
    active_champ = plan.get("active_champion") or {}
    active_champ_id = str(active_champ.get("strategy_id") or "strat_volatility_breakout")
    active_champ_ver = int(active_champ.get("version") or 1)
    active_champ_name = str(active_champ.get("name") or "Volatility Compression Breakout")
    active_champ_sqn = float(active_champ.get("sqn_score") or 3.55)
    active_champ_r6m = float(active_champ.get("recent_6m_return_pct") or 11.03)
    active_champ_wr = float(active_champ.get("recent_6m_win_rate_pct") or 67.9)

    # Minimalist Sidebar
    with st.sidebar:
        st.markdown("#### Session & Calendar")
        if is_today_trading_day:
            st.success(f"**{today_iso}** ({today_weekday_name})\n\nMarket Open · NYSE / NASDAQ")
        else:
            st.info(
                f"**{today_iso}** ({today_weekday_name})\n\n"
                f"{market_status_reason}\n\n"
                f"Next Session: **{next_trading_day_iso}**"
            )

        st.markdown("---")
        st.markdown("#### Daily Workflow")
        st.caption("Eastern (`ET`) / Singapore (`SGT`)")
        st.checkbox(
            "1. 8:45–9:25 ET: Type `run` in IDE",
            value=ide_ran_today,
            key="sidebar_chk_ide_run",
            help="Best run 15–45 mins before 9:30 AM ET open (after BMO/AMC earnings & overnight news): vetoes bearish news (<= -0.35), re-ranks top catalysts (>= +0.25), and checks pre-market gaps.",
        )
        st.checkbox(
            "2. 9:30 ET: Execute SELLs & Stops",
            value=False,
            key="sidebar_chk_sells_stops",
            help="Execute SELL exits first to free cash and raise GTC stops on holdings at +1R.",
        )
        st.checkbox(
            "3. 9:30–9:45 ET: Place BUY Limits",
            value=False,
            key="sidebar_chk_copilot",
            help="Submit Day Limit orders inside the Buy-Zone (<= Max Chase) with an attached GTC Stop-Loss and Take-Profit bracket.",
        )
        st.checkbox(
            "4. Post-Fill: Confirm in Copilot",
            value=False,
            key="sidebar_chk_fills",
            help="Click Sold / Bought in Tab 1 so cash and holdings stay reconciled.",
        )
        st.caption(f"Last IDE AI Run: `{last_ide_run_ts}`")

        st.markdown("---")
        st.markdown("#### System Status")
        st.caption(f"Champion: **{active_champ_id} v{active_champ_ver}**")
        st.caption(f"Paper Mode: **{acc['trading_mode'].upper()}** (`$100k` × 6 Pods)")
        st.caption(f"Market Data: **{app.settings.market_data_provider.upper()}**")
        st.caption(f"Validated Models: **{golden_ready_count} / {len(active_paper_strats)} beat SPY**")
        if st.button(
            "Reset Paper Books ($100k)",
            width="stretch",
            help="Resets the simulated $100,000 paper books to $100,000.00 cash (0 trades).",
        ):
            with st.spinner("Resetting all 6 $100k paper books..."):
                app.orchestrator.paper_engine.reset_account_to_starting_capital()
            st.rerun()

    # Sleek Minimalist Top Masthead
    hdr_left, hdr_right = st.columns([2.2, 2.8])
    with hdr_left:
        st.markdown("### Swing Trading AI")
    with hdr_right:
        mkt_badge = "MARKET OPEN" if is_today_trading_day else f"CLOSED ({today_weekday_name.upper()})"
        st.markdown(
            f"<div style='text-align:right;padding-top:8px;font-size:0.82rem;color:#94a3b8;'>"
            f"<strong style='color:#e2e8f0;'>{today_iso}</strong> · {mkt_badge} · "
            f"Next Open: <strong style='color:#e2e8f0;'>{next_trading_day_iso}</strong> · "
            f"Champion: <strong style='color:#38bdf8;'>{active_champ_id} v{active_champ_ver}</strong>"
            f"</div>",
            unsafe_allow_html=True,
        )

    tabs = st.tabs(
        [
            "Live Copilot",
            "Paper Portfolio",
            "Strategies & Backtests",
            "AI & Watchlist",
            "Risk & Logs",
            "Guide",
        ]
    )

    # =========================================================================
    # TAB 0: LIVE COPILOT (REAL ACCOUNT)
    # =========================================================================
    with tabs[0]:
        if st.session_state.get("_copilot_flash_msg"):
            flash_msg = st.session_state.pop("_copilot_flash_msg")
            if hasattr(st, "toast"):
                st.toast(flash_msg)
            st.success(flash_msg)

        real_acc = plan["account_summary"]
        raw_sell_actions = plan["sell_actions"]
        raw_buy_actions = plan["buy_actions"]
        hold_updates = plan["hold_updates"]
        dismissed_count = int(plan.get("dismissed_count") or 0)
        real_positions = copilot_data.get("positions") or []
        real_history = copilot_data.get("trade_history") or []
        latest_bar_date = str(plan.get("session_date") or today_iso)
        universe_tickers = sorted({t for s in strats for t in s["universe"]} | {p["ticker"] for p in real_positions})
        db_latest_rows = app.db.fetch_all(
            "SELECT ticker, close FROM market_bars_daily "
            "WHERE (ticker, bar_date) IN (SELECT ticker, MAX(bar_date) FROM market_bars_daily GROUP BY ticker)"
        )
        latest_px_by_tkr = {r["ticker"]: float(r["current_price"]) for r in state["research_reports"]}
        for _dbr in db_latest_rows:
            latest_px_by_tkr[str(_dbr["ticker"])] = float(_dbr["close"])

        # 1. KPI Strip (100% Ledger-Calculated)
        total_real_pnl = round(float(real_acc["realised_pnl"]) + float(real_acc["unrealised_pnl"]), 2)
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric(
            "Account Value",
            f"${real_acc['total_equity']:,.2f}",
            f"{real_acc['total_return_pct']:+.2f}% vs ${real_acc['starting_cash']:,.0f} deposited",
            help="Available Cash + Market Value of Open Holdings.",
        )
        rc2.metric(
            "Available Cash",
            f"${real_acc['cash_balance']:,.2f}",
            f"Net Deposited: ${real_acc['starting_cash']:,.0f}",
            help="Calculated automatically from Deposits/Withdrawals minus BUY costs plus SELL proceeds.",
        )
        rc3.metric(
            "Open Holdings",
            f"{real_acc['open_positions_count']} / 10",
            f"${real_acc['positions_market_value']:,.2f} invested",
            help="Derived automatically from your confirmed BUY and SELL fills.",
        )
        rc4.metric(
            "Total Real P&L",
            f"${total_real_pnl:+,.2f}",
            f"Realised: ${real_acc['realised_pnl']:+,.0f} · Open: ${real_acc['unrealised_pnl']:+,.0f}",
            help="Combined Realised P&L (closed SELLs) and Unrealised P&L (open holdings).",
        )

        # Compact Control Bar: Engine Summary on Left + 4 Clean Popovers on Right
        fallback_badge = (
            f" · Pullback Fallback: `{active_champ.get('fallback_strategy')}`"
            if active_champ.get("fallback_triggered")
            else ""
        )
        ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4, ctrl_c5 = st.columns([2.5, 0.9, 0.9, 0.75, 0.75])
        with ctrl_c1:
            st.caption(
                f"**Engine**: `{active_champ_name}` (`v{active_champ_ver}` · SQN `{active_champ_sqn:.2f}` · "
                f"6M `{active_champ_r6m:+.1f}%` · `{active_champ_wr:.0f}%` WR){fallback_badge} · "
                f"Exits bound to each holding's entry strategy."
            )
        with ctrl_c2:
            with st.popover("Cash Transfer", width="stretch"):
                st.markdown("**Deposit or Withdraw Cash**")
                st.caption(
                    f"Net Deposited: `${real_acc['starting_cash']:,.2f}` · "
                    f"Available Cash: `${real_acc['cash_balance']:,.2f}`"
                )
                dw_amt = st.number_input("Amount ($)", min_value=1.0, value=1000.0, step=250.0, key="copilot_dw_amt")
                dw_c1, dw_c2 = st.columns(2)
                if dw_c1.button("+ Deposit", width="stretch"):
                    with st.spinner("Recording deposit & reconciling ledger..."):
                        app.orchestrator.live_copilot.adjust_cash_deposit_withdrawal(float(dw_amt))
                        st.session_state["_copilot_flash_msg"] = f"Deposited +${float(dw_amt):,.2f}."
                    st.rerun()
                if dw_c2.button("- Withdraw", width="stretch"):
                    try:
                        with st.spinner("Recording withdrawal & reconciling ledger..."):
                            app.orchestrator.live_copilot.adjust_cash_deposit_withdrawal(-float(dw_amt))
                            st.session_state["_copilot_flash_msg"] = f"Withdrew -${float(dw_amt):,.2f}."
                        st.rerun()
                    except ValueError as err:
                        st.error(str(err))
        with ctrl_c3:
            with st.popover("+ Log Trade", width="stretch"):
                st.markdown("**Log Broker Fill (`BUY` / `SELL`)**")
                lt_c1, lt_c2 = st.columns(2)
                lt_side = lt_c1.selectbox("Side", options=["BUY", "SELL"], key="lt_side_sel")
                lt_tkr_opts = (
                    [p["ticker"] for p in real_positions] or universe_tickers
                    if lt_side == "SELL"
                    else universe_tickers + ["+ Custom Ticker..."]
                )
                lt_tkr_sel = lt_c2.selectbox("Ticker", options=lt_tkr_opts, key="lt_tkr_sel")
                if lt_tkr_sel == "+ Custom Ticker...":
                    lt_tkr = st.text_input("Symbol", value="TSLA", key="lt_custom_tkr").strip().upper() or "TSLA"
                else:
                    lt_tkr = lt_tkr_sel
                lt_default_px = round(latest_px_by_tkr.get(lt_tkr, 150.0), 2)
                lt_c3, lt_c4, lt_c5 = st.columns(3)
                lt_qty = lt_c3.number_input("Shares", min_value=1, value=10, step=1, key="lt_qty_inp")
                lt_px = lt_c4.number_input("Fill Price ($)", min_value=0.01, value=lt_default_px, step=0.50, key=f"lt_px_inp_{lt_tkr}_{latest_bar_date}")
                lt_fee = lt_c5.number_input("Fees ($)", min_value=0.0, value=0.0, step=0.50, key="lt_fee_inp")
                lt_c6, lt_c7, lt_c8 = st.columns(3)
                lt_date = lt_c6.text_input("Date", value=latest_bar_date, key="lt_date_inp")
                lt_sl = lt_c7.number_input("Stop $ (0=Auto)", min_value=0.0, value=0.0, step=0.50, key="lt_sl_inp")
                lt_tp = lt_c8.number_input("Target $ (0=Auto)", min_value=0.0, value=0.0, step=0.50, key="lt_tp_inp")
                if st.button(f"Record {lt_side} {int(lt_qty)} {lt_tkr}", width="stretch", key="btn_record_manual_trade"):
                    if lt_side == "BUY":
                        with st.spinner("Recording BUY fill & updating holdings..."):
                            app.orchestrator.live_copilot.confirm_buy_execution(
                                ticker=lt_tkr,
                                strategy_id=active_champ_id,
                                strategy_version=active_champ_ver,
                                quantity=int(lt_qty),
                                fill_price=float(lt_px),
                                fees_usd=float(lt_fee),
                                stop_loss_price=float(lt_sl) if lt_sl > 0 else None,
                                take_profit_price=float(lt_tp) if lt_tp > 0 else None,
                                fill_date=lt_date.strip() or latest_bar_date,
                                notes="Logged via Copilot",
                            )
                            st.session_state["_copilot_flash_msg"] = f"Logged BUY {int(lt_qty)} {lt_tkr} @ ${float(lt_px):.2f}."
                        st.rerun()
                    else:
                        try:
                            with st.spinner("Recording SELL fill & updating cash..."):
                                app.orchestrator.live_copilot.confirm_sell_execution(
                                    ticker=lt_tkr,
                                    quantity=int(lt_qty),
                                    fill_price=float(lt_px),
                                    fees_usd=float(lt_fee),
                                    fill_date=lt_date.strip() or latest_bar_date,
                                    notes="Logged via Copilot",
                                )
                                st.session_state["_copilot_flash_msg"] = f"Logged SELL {int(lt_qty)} {lt_tkr} @ ${float(lt_px):.2f}."
                            st.rerun()
                        except KeyError as err:
                            st.error(str(err))
        with ctrl_c4:
            with st.popover("Reset", width="stretch"):
                st.markdown("**Reset Account Ledger**")
                st.caption("Clears all trades and holdings and resets your account to a fresh initial deposit.")
                reset_dep = st.number_input("Initial Cash Deposit ($)", min_value=100.0, value=float(real_acc["starting_cash"]), step=1000.0, key="reset_init_dep_inp")
                if st.button("Confirm Reset", width="stretch"):
                    with st.spinner("Resetting account ledger..."):
                        app.orchestrator.live_copilot.reset_copilot_account(starting_cash=float(reset_dep))
                        st.session_state["_copilot_flash_msg"] = f"Reset account to ${float(reset_dep):,.2f} initial deposit."
                    st.rerun()
        with ctrl_c5:
            with st.popover("? Rules", width="stretch"):
                st.markdown(
                    "**Two-Stage Institutional Swing Execution (`ET` / `SGT`)**\n\n"
                    f"1. **Stage 1 — Post-Close Structural Scan (`5:30 PM ET` / `5:30 AM SGT` Auto)**: Daily indicators (`SMA`, `RSI`, `ATR`, `20d High`) require the official `4:00 PM ET` closing auction (`98%` of daily volume). Stage 1 locks in structural setups (`Close {latest_bar_date}`) and blocks non-PEAD entries within 2 days before `AMC`/`BMO` earnings.\n"
                    f"2. **Stage 2 — Pre-Open AI & Gap Gate (`8:45–9:25 AM ET` / `8:45–9:25 PM SGT` — Type `run` in IDE)**: Running `run` 15–45 mins before the `{next_trading_day_iso}` open checks overnight/`AMC`/`BMO` earnings and news—**removing** any `BUY` with bearish news (`<= -0.35`), triggering **emergency `SELL` alerts** on holdings with severe news (`<= -0.50`), **re-ranking** positive catalysts (`>= +0.25`) to #1 priority, and checking live pre-market gaps.\n"
                    "3. **At Open (`9:30–9:45 AM ET`)**: Execute **`SELL` exits first**, raise `+1R` `GTC Stops`, and place **Day Limit Orders inside the `Buy-Zone (<= Max Chase)`** with attached `GTC Stop + Target` brackets. If a stock gaps above `Max Chase`, your limit order automatically prevents chasing."
                )

        st.markdown("---")
        # Section 1: Today's Step-by-Step Required Actions
        chk_hdr_c1, chk_hdr_c2, chk_hdr_c3 = st.columns([3.2, 1.0, 1.0])
        chk_hdr_c1.markdown(f"##### 1. Step-by-Step Required Actions — `{today_iso}` ({today_weekday_name})")
        if dismissed_count > 0:
            if chk_hdr_c2.button(f"Restore Skipped ({dismissed_count})", key="btn_restore_skipped", width="stretch"):
                with st.spinner("Restoring skipped setups..."):
                    restored_n = app.orchestrator.live_copilot.restore_dismissed_signals(latest_bar_date)
                    st.session_state["_copilot_flash_msg"] = f"Restored {restored_n} skipped signal(s)."
                st.rerun()
        if real_history:
            last_t = real_history[0]
            if chk_hdr_c3.button(f"Undo Last ({last_t['side']} {last_t['ticker']})", key="btn_quick_undo", width="stretch"):
                with st.spinner("Undoing last trade & replaying ledger..."):
                    app.orchestrator.live_copilot.undo_last_trade()
                    st.session_state["_copilot_flash_msg"] = f"Undid {last_t['side']} {last_t['quantity']} {last_t['ticker']}."
                st.rerun()

        show_signals_today = is_today_trading_day
        if not is_today_trading_day:
            nt_c1, nt_c2 = st.columns([3.1, 1.4])
            nt_c1.caption(
                f"Markets closed today (**{market_status_reason}**). No orders should be placed today. "
                f"Next session: **`{next_trading_day_iso}`** (computed from completed close: **`{latest_bar_date}`**)."
            )
            show_signals_today = nt_c2.checkbox(
                f"Preview `{next_trading_day_iso}` setups",
                value=False,
                key="copilot_preview_non_trading_day",
            )

        sell_actions = raw_sell_actions if show_signals_today else []
        buy_actions = raw_buy_actions if show_signals_today else []
        ratchet_alerts = [
            h for h in hold_updates if h.get("stop_mode") and h.get("stop_mode") != "Initial ATR Stop"
        ] if show_signals_today else []
        vetoed_sigs = (plan.get("vetoed_signals") or []) if show_signals_today else []

        if show_signals_today:
            ai_status_txt = (
                f"Verified (`{last_ide_run_ts}`)"
                if ide_ran_today
                else "Deterministic Ready · Optional: type `run` in IDE at `8:45–9:25 AM ET` (`8:45–9:25 PM SGT`)"
            )
            st.markdown(
                f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px;margin:4px 0 12px 0;font-size:0.8rem;'>"
                f"<div style='background:rgba(15,23,42,0.55);border:1px solid rgba(148,163,184,0.16);border-radius:6px;padding:8px 12px;'>"
                f"<strong style='color:#38bdf8;'>STEP 1 · 8:45–9:25 AM ET (Pre-Open)</strong><br/>"
                f"<span style='color:#cbd5e1;'>{ai_status_txt}</span></div>"
                f"<div style='background:rgba(15,23,42,0.55);border:1px solid rgba(148,163,184,0.16);border-radius:6px;padding:8px 12px;'>"
                f"<strong style='color:#f59e0b;'>STEP 2 · 9:30–9:35 AM ET (Exits &amp; Stops)</strong><br/>"
                f"<span style='color:#cbd5e1;'><strong>{len(sell_actions)}</strong> Position(s) to Close · <strong>{len(ratchet_alerts)}</strong> Stop Ratchet(s)</span></div>"
                f"<div style='background:rgba(15,23,42,0.55);border:1px solid rgba(148,163,184,0.16);border-radius:6px;padding:8px 12px;'>"
                f"<strong style='color:#10b981;'>STEP 3 · 9:30–9:45 AM ET (New Entries)</strong><br/>"
                f"<span style='color:#cbd5e1;'><strong>{len(buy_actions)}</strong> Position(s) to Open (Day Limit &le; Max Chase + GTC Bracket)</span></div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            if sell_actions:
                st.caption("STEP 2A · POSITIONS TO CLOSE AT MARKET OPEN (9:30–9:35 AM ET — EXECUTE FIRST TO FREE CASH)")
                for idx, sa in enumerate(sell_actions):
                    sc_info, sc_qty, sc_px, sc_btn1, sc_btn2 = st.columns([2.7, 0.75, 0.85, 0.85, 0.65])
                    s_qty_sig = f"{sa['ticker']}_{sa['quantity_to_sell']}_{sa['reference_exit_price']}_{sa.get('signal_date', latest_bar_date)}"
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
                    sell_factors_html = _format_factors_html(sa.get("factors_considered") or [])
                    with sc_info:
                        st.markdown(
                            f"**SELL `{s_qty}` `{sa['ticker']}`** · Est. P&L **`${live_est_pnl:+,.2f}`**  \n"
                            f"<span style='color:#94a3b8;font-size:0.82rem;'>Entry `${sa['avg_entry_price']:.2f}` → Exit `${float(s_price):.2f}` (Close `{sa.get('signal_date', latest_bar_date)}`) · "
                            f"{sa['strategy_id']} v{sa['strategy_version']}</span>"
                            f"{sell_factors_html}",
                            unsafe_allow_html=True,
                        )
                    with sc_btn1:
                        st.write("")
                        if st.button(f"Sold {sa['ticker']}", key=f"btn_sell_{s_qty_sig}_{idx}", width="stretch"):
                            with st.spinner(f"Confirming SELL {sa['ticker']} & updating cash..."):
                                app.orchestrator.live_copilot.confirm_sell_execution(
                                    ticker=sa["ticker"],
                                    quantity=int(s_qty),
                                    fill_price=float(s_price),
                                    fees_usd=0.0,
                                    notes=sa["reason"],
                                )
                                st.session_state["_copilot_flash_msg"] = (
                                    f"Confirmed SELL {int(s_qty)} {sa['ticker']} @ ${float(s_price):.2f} (${live_est_pnl:+,.2f})."
                                )
                            st.rerun()
                    with sc_btn2:
                        st.write("")
                        if st.button("Hold", key=f"btn_skip_sell_{s_qty_sig}_{idx}", width="stretch"):
                            with st.spinner(f"Holding {sa['ticker']} for today..."):
                                app.orchestrator.live_copilot.dismiss_signal(
                                    signal_date=sa["signal_date"],
                                    strategy_id=sa["strategy_id"],
                                    ticker=sa["ticker"],
                                    action="SELL",
                                )
                                st.session_state["_copilot_flash_msg"] = f"Held {sa['ticker']} for today."
                            st.rerun()

            if ratchet_alerts:
                st.caption("STEP 2B · RAISE GTC STOP-LOSS BRACKETS IN YOUR BROKER")
                for r_h in ratchet_alerts:
                    st.info(
                        f"**`{r_h['ticker']}` (`{r_h['quantity']} sh`)** reached `+1R+`: "
                        f"Raise broker `GTC Stop-Loss` from `${float(r_h.get('initial_stop_price') or r_h['stop_loss_price']):.2f}` "
                        f"→ **`${float(r_h['stop_loss_price']):.2f}`** (`{r_h['stop_mode']}`) · Target `${float(r_h['take_profit_price']):.2f}`."
                    )

            if buy_actions:
                st.caption("STEP 3 · POSITIONS TO OPEN (9:30–9:45 AM ET — PLACE DAY LIMIT IN BUY-ZONE + ATTACH GTC STOP & TARGET)")
                for idx, ba in enumerate(buy_actions):
                    bc_info, bc_qty, bc_px, bc_btn1, bc_btn2 = st.columns([2.7, 0.75, 0.85, 0.85, 0.65])
                    b_sig = f"{ba['ticker']}_{ba['recommended_shares']}_{ba['reference_entry_price']}_{ba.get('signal_date', latest_bar_date)}"
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
                        f" · <span style='color:#4ade80;font-weight:600;'>Catalyst {ai_sent_val:+.2f}</span>"
                        if ai_sent_val >= 0.20
                        else ""
                    )
                    pre_open_status = str(ba.get("pre_open_status") or "READY_IN_BUY_ZONE")
                    ind_px = float(ba.get("indicative_price") or ref_px)
                    gap_pct = float(ba.get("overnight_gap_pct") or 0.0)
                    if pre_open_status == "EXTENDED_ABOVE_MAX_CHASE":
                        gap_badge_html = (
                            f" · <span style='color:#f59e0b;font-weight:600;'>Extended ${ind_px:.2f} ({gap_pct:+.1f}%) — Do Not Chase &gt; Max Chase</span>"
                        )
                    elif pre_open_status == "DIPPED_BELOW_BUY_ZONE":
                        gap_badge_html = (
                            f" · <span style='color:#f59e0b;font-weight:600;'>Pre-Open ${ind_px:.2f} ({gap_pct:+.1f}%) — Wait for Buy-Zone Reclaim</span>"
                        )
                    elif abs(gap_pct) >= 0.05:
                        gap_badge_html = (
                            f" · <span style='color:#38bdf8;'>Live Quote ${ind_px:.2f} ({gap_pct:+.1f}% · In Buy-Zone)</span>"
                        )
                    else:
                        gap_badge_html = " · <span style='color:#38bdf8;'>In Buy-Zone</span>"
                    buy_factors_html = _format_factors_html(ba.get("factors_considered") or [])
                    with bc_info:
                        st.markdown(
                            f"**BUY `{int(b_qty)}` `{ba['ticker']}` @ `${float(b_price):.2f}`** "
                            f"(`${live_cost:,.0f}` · `{live_weight:.1f}%` · Close `{ba.get('signal_date', latest_bar_date)}`) · "
                            f"Buy-Zone **`{buy_zone_str}`**{gap_badge_html}{ai_badge_html}  \n"
                            f"<span style='color:#cbd5e1;font-size:0.83rem;'>Broker Order: <strong>Day Limit &le; ${float(ba.get('max_chase_price') or ref_px):.2f}</strong> · "
                            f"Attach Bracket: <strong>GTC Stop ${adj_stop:.2f}</strong> (-${live_risk:,.0f} risk) &amp; "
                            f"<strong>GTC Target ${adj_tp:.2f}</strong> (+1R Breakeven ${ratchet_1r:.2f} · {ba['holding_horizon_days']})</span>"
                            f"{buy_factors_html}",
                            unsafe_allow_html=True,
                        )
                    with bc_btn1:
                        st.write("")
                        if st.button(f"Bought {ba['ticker']}", key=f"btn_buy_{b_sig}_{idx}", width="stretch"):
                            with st.spinner(f"Confirming BUY {ba['ticker']} & updating holdings..."):
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
                        if st.button("Skip", key=f"btn_skip_{b_sig}_{idx}", width="stretch"):
                            with st.spinner(f"Skipping {ba['ticker']} for today..."):
                                app.orchestrator.live_copilot.dismiss_signal(
                                    signal_date=ba["signal_date"],
                                    strategy_id=ba["strategy_id"],
                                    ticker=ba["ticker"],
                                    action="BUY",
                                )
                                st.session_state["_copilot_flash_msg"] = f"Skipped {ba['ticker']} for today."
                            st.rerun()
            elif not sell_actions:
                st.caption("No new BUY or SELL actions required today. All open holdings remain within their target brackets.")

            _render_removed_signals_section(st, vetoed_sigs, context_label="Live Copilot")

        st.markdown("---")
        # Section 2: Active Holdings
        st.markdown("##### 2. Active Holdings")
        if hold_updates:
            for h_idx, h in enumerate(hold_updates):
                hc1, hc2, hc3, hc4, hc5, hc6 = st.columns([2.35, 1.25, 0.65, 0.75, 0.75, 0.65])
                h_sig = f"{h['ticker']}_{h['quantity']}_{h['avg_entry_price']}"
                pnl_sign = f"+${h['unrealised_pnl']:,.2f}" if h["unrealised_pnl"] >= 0 else f"-${abs(h['unrealised_pnl']):,.2f}"
                hc1.markdown(
                    f"**`{h['ticker']}`** · `{h['quantity']} sh` · "
                    f"`${h['avg_entry_price']:.2f}` → `${h['current_price']:.2f}` (**`{pnl_sign}`**)  \n"
                    f"<span style='color:#94a3b8;font-size:0.8rem;'>{h.get('strategy', '')} · {h['status']}</span>",
                    unsafe_allow_html=True,
                )
                stop_disp = f"${h['stop_loss_price']:.2f}" if h.get("stop_loss_price") else "—"
                tp_disp = f"${h['take_profit_price']:.2f}" if h.get("take_profit_price") else "—"
                hc2.markdown(
                    f"Stop `{stop_disp}` · Target `{tp_disp}`  \n"
                    f"<span style='color:#38bdf8;font-size:0.78rem;'>{h.get('stop_mode', 'Initial ATR Stop')}</span>",
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
                )
                close_px = hc4.number_input(
                    f"Exit $ ({h['ticker']})",
                    min_value=0.01,
                    value=float(h["current_price"]),
                    step=0.10,
                    key=f"quick_close_px_{h_sig}_{h_idx}",
                    label_visibility="collapsed",
                )
                btn_lbl = f"Sell {close_qty}" if int(close_qty) < int(h["quantity"]) else f"Close {h['ticker']}"
                if hc5.button(btn_lbl, key=f"btn_qclose_{h_sig}_{h_idx}", width="stretch"):
                    with st.spinner(f"Recording SELL {int(close_qty)} {h['ticker']} & reconciling portfolio..."):
                        app.orchestrator.live_copilot.confirm_sell_execution(
                            ticker=h["ticker"],
                            quantity=int(close_qty),
                            fill_price=float(close_px),
                            fees_usd=0.0,
                            notes="Position exit via Copilot",
                        )
                        est_p = round((float(close_px) - float(h["avg_entry_price"])) * int(close_qty), 2)
                        st.session_state["_copilot_flash_msg"] = (
                            f"Confirmed SELL {int(close_qty)} {h['ticker']} @ ${float(close_px):.2f} (${est_p:+,.2f})."
                        )
                    st.rerun()
                with hc6:
                    with st.popover("Bracket", width="stretch"):
                        st.caption(f"Update `{h['ticker']}` Broker Bracket")
                        new_sl = st.number_input(
                            "Stop-Loss ($)",
                            min_value=0.01,
                            value=float(h.get("stop_loss_price") or round(float(h["avg_entry_price"]) * 0.95, 2)),
                            step=0.25,
                            key=f"brk_sl_{h_sig}_{h_idx}",
                        )
                        new_tp = st.number_input(
                            "Take-Profit ($)",
                            min_value=0.01,
                            value=float(h.get("take_profit_price") or round(float(h["avg_entry_price"]) * 1.08, 2)),
                            step=0.25,
                            key=f"brk_tp_{h_sig}_{h_idx}",
                        )
                        if st.button("Save", key=f"btn_brk_{h_sig}_{h_idx}", width="stretch"):
                            with st.spinner(f"Saving {h['ticker']} bracket..."):
                                app.orchestrator.live_copilot.update_position_brackets(h["ticker"], float(new_sl), float(new_tp))
                                st.session_state["_copilot_flash_msg"] = f"Updated {h['ticker']} bracket."
                            st.rerun()
        elif real_positions:
            st.dataframe(real_positions, width="stretch", hide_index=True)
        else:
            st.caption("No open holdings. Confirm a BUY setup above or click **+ Log Trade** in the top bar.")

        st.markdown("---")
        # Section 3: Trade Ledger
        st.markdown(f"##### 3. Trade Ledger ({len(real_history)} fills)")
        if real_history:
            clean_real_trades = [
                {
                    "Trade ID": t["trade_id"],
                    "Date": t["fill_date"],
                    "Side": t["side"],
                    "Ticker": t["ticker"],
                    "Shares": int(t["quantity"]),
                    "Fill Price": f"${float(t['fill_price']):.2f}",
                    "Fees": f"${float(t.get('fees_usd') or 0.0):.2f}",
                    "Notional": f"${int(t['quantity']) * float(t['fill_price']):,.2f}",
                    "Realised P&L": f"${float(t.get('realised_pnl') or 0.0):+,.2f}" if t["side"] == "SELL" else "—",
                    "Cash After": f"${float(t.get('cash_after') or 0.0):,.2f}",
                    "Strategy": f"{t.get('strategy_id', '')} v{t.get('strategy_version', 1)}",
                }
                for t in real_history
            ]
            st.dataframe(clean_real_trades, width="stretch", hide_index=True)

            with st.expander("Edit or Delete a Recorded Trade", expanded=False):
                trade_by_id = {t["trade_id"]: t for t in real_history}
                trade_select_opts = [t["trade_id"] for t in real_history]
                trade_select_labels = {
                    t["trade_id"]: (
                        f"{t['fill_date']} · {t['side']} {t['quantity']} {t['ticker']} @ ${float(t['fill_price']):.2f} "
                        f"[{t['trade_id']}]"
                    )
                    for t in real_history
                }
                sel_trade_id = st.selectbox(
                    "Select Trade",
                    options=trade_select_opts,
                    format_func=lambda tid: trade_select_labels.get(tid, tid),
                    key="copilot_trade_editor_select",
                )
                editing_trade = trade_by_id.get(sel_trade_id)
                if editing_trade:
                    tr_sig = f"{editing_trade['trade_id']}_{editing_trade['side']}_{editing_trade['ticker']}_{editing_trade['quantity']}_{editing_trade['fill_price']}"
                    te_c1, te_c2, te_c3, te_c4, te_c5, te_c6 = st.columns([0.9, 1.15, 0.85, 0.95, 0.85, 1.05])
                    default_side_idx = 1 if editing_trade["side"] == "SELL" else 0
                    te_side = te_c1.selectbox("Side", options=["BUY", "SELL"], index=default_side_idx, key=f"te_side_{tr_sig}")
                    tkr_list = sorted(set(universe_tickers) | {editing_trade["ticker"]})
                    default_tkr_idx = tkr_list.index(editing_trade["ticker"]) if editing_trade["ticker"] in tkr_list else 0
                    te_ticker = te_c2.selectbox("Ticker", options=tkr_list, index=default_tkr_idx, key=f"te_tkr_{tr_sig}")
                    te_qty = te_c3.number_input("Shares", min_value=1, value=int(editing_trade["quantity"]), step=1, key=f"te_qty_{tr_sig}")
                    te_px = te_c4.number_input("Fill Price ($)", min_value=0.01, value=float(editing_trade["fill_price"]), step=0.50, key=f"te_px_{tr_sig}")
                    te_fee = te_c5.number_input("Fees ($)", min_value=0.0, value=float(editing_trade.get("fees_usd") or 0.0), step=0.50, key=f"te_fee_{tr_sig}")
                    te_dt = te_c6.text_input("Date", value=str(editing_trade["fill_date"]), key=f"te_dt_{tr_sig}")

                    btn_col1, btn_col2, _ = st.columns([1.2, 1.2, 2.6])
                    if btn_col1.button("Save Changes", key=f"btn_save_tr_{tr_sig}", width="stretch"):
                        with st.spinner(f"Updating trade {editing_trade['trade_id']} & replaying ledger..."):
                            app.orchestrator.live_copilot.edit_trade(
                                trade_id=editing_trade["trade_id"],
                                ticker=te_ticker,
                                side=te_side,
                                quantity=int(te_qty),
                                fill_price=float(te_px),
                                fees_usd=float(te_fee),
                                fill_date=te_dt.strip() or latest_bar_date,
                            )
                            st.session_state["_copilot_flash_msg"] = f"Updated trade {editing_trade['trade_id']}."
                        st.rerun()
                    if btn_col2.button("Delete Trade", key=f"btn_del_tr_{tr_sig}", width="stretch"):
                        with st.spinner(f"Deleting trade {editing_trade['trade_id']} & replaying ledger..."):
                            app.orchestrator.live_copilot.delete_trade(editing_trade["trade_id"])
                            st.session_state["_copilot_flash_msg"] = f"Deleted trade {editing_trade['trade_id']}."
                        st.rerun()
        else:
            st.caption("No trades recorded yet (`0` fills). Cash, holdings, and P&L update automatically when trades are logged.")

    # =========================================================================
    # TAB 1: PAPER PORTFOLIO (MASTER $100K + 5 STRATEGY PODS)
    # =========================================================================
    with tabs[1]:
        _render_tab_header(
            st,
            "Forward $100,000 Paper Books: 1 Master Combined Portfolio + 5 Dedicated Per-Strategy $100k Pods (Synchronized with IDE `run` AI Catalysts).",
            "Two-Tier Paper Architecture & AI Sync",
            "- **Master Combined (`$100k`)**: Runs all active strategies under shared portfolio heat (`5%`), sector (`30%`), and AI Catalyst rules.\n"
            "- **5 Strategy Pods (`$100k` each)**: Isolates each strategy in its own `$100k` account to measure pure forward alpha without cash starvation.\n"
            "- **Live AI Sync**: Typing `run` in the IDE updates both Live Copilot and all 6 Paper Books (vetoing bearish `<= -0.35` setups, triggering emergency `<= -0.50` exits, and re-ranking `>= +0.25` catalysts first).",
        )

        all_paper_books = app.orchestrator.paper_engine.get_all_paper_accounts_summary(strats)
        book_options = [b["account_id"] for b in all_paper_books]
        book_labels = {
            b["account_id"]: (
                f"Master Combined ($100k) — ${b['total_equity']:,.2f} ({b['total_return_pct']:+.2f}%) · {b['open_positions_count']} Open"
                if b["book_type"] == "MASTER_COMBINED"
                else f"Pod: {b['book_label']} — ${b['total_equity']:,.2f} ({b['total_return_pct']:+.2f}%) · {b['open_positions_count']} Open"
            )
            for b in all_paper_books
        }

        sel_book_col1, sel_book_col2 = st.columns([2.2, 2.8])
        with sel_book_col1:
            selected_book_id = st.selectbox(
                "Paper Book",
                options=book_options,
                index=0,
                format_func=lambda aid: book_labels.get(aid, aid),
                key="paper_book_selector",
                label_visibility="collapsed",
            )

        all_reg_strats = app.orchestrator.registry.list_strategies()
        if selected_book_id == app.orchestrator.paper_engine.DEFAULT_ACCOUNT_ID:
            book_engine = app.orchestrator.paper_engine
            book_acc = acc
            book_positions = positions
            book_ledger = ledger
            book_snaps = snapshots
            book_title_label = "Master Combined Portfolio ($100k Shared)"
            paper_book_strats = [s for s in all_reg_strats if s.status == "PAPER_TRADING"]
        else:
            strat_id_for_book = selected_book_id.replace("paper_", "", 1)
            book_engine = app.orchestrator.paper_engine.get_strategy_account_engine(strat_id_for_book)
            book_acc = book_engine.get_account_summary()
            book_positions = book_engine.get_open_positions()
            book_ledger = book_engine.get_trade_ledger(limit=500)
            book_snaps = book_engine.get_portfolio_snapshots()
            book_title_label = f"Strategy Pod: {strat_id_for_book} ($100k Isolated)"
            paper_book_strats = [
                s for s in all_reg_strats
                if s.strategy_id == strat_id_for_book and s.status == "PAPER_TRADING"
            ]
            if not paper_book_strats:
                paper_book_strats = [s for s in all_reg_strats if s.strategy_id == strat_id_for_book][:1]

        book_net_dollar_pnl = round(
            float(book_acc.get("total_pnl_usd", float(book_acc["total_equity"]) - float(book_acc["starting_capital"]))),
            2,
        )
        book_daily_pnl_usd = float(book_acc.get("daily_pnl_usd", 0.0))
        book_daily_ret_pct = float(book_acc.get("daily_return_pct", 0.0))
        book_weekly_pnl_usd = float(book_acc.get("weekly_pnl_usd", 0.0))
        book_weekly_ret_pct = float(book_acc.get("weekly_return_pct", 0.0))
        book_total_fees = round(
            sum(float(l.get("commission_usd", 0.0)) + float(l.get("slippage_usd", 0.0)) for l in book_ledger),
            2,
        )
        book_date_span = _get_paper_date_span(book_snaps, book_ledger)

        with sel_book_col2:
            st.caption(
                f"**{book_title_label}** · Window: `{book_date_span}` · Costs: `${book_total_fees:,.2f}`"
            )

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric(
            "Total Equity",
            f"${book_acc['total_equity']:,.2f}",
            f"{book_acc['total_return_pct']:+.2f}% vs $100k",
        )
        k2.metric(
            "Daily P&L",
            f"${book_daily_pnl_usd:+,.2f}",
            f"{book_daily_ret_pct:+.2f}%",
        )
        k3.metric(
            "Weekly P&L (5d)",
            f"${book_weekly_pnl_usd:+,.2f}",
            f"{book_weekly_ret_pct:+.2f}%",
        )
        k4.metric(
            "Total P&L",
            f"${book_net_dollar_pnl:+,.2f}",
            f"Realised ${book_acc['realised_pnl']:+,.0f} · Open ${book_acc['unrealised_pnl']:+,.0f}",
        )
        k5.metric(
            "Available Cash",
            f"${book_acc['cash_balance']:,.2f}",
            f"{book_acc['open_positions_count']} open · DD -{book_acc['current_drawdown_pct']:.2f}%",
        )

        # Compute exact Next-Session / Today's Planned Paper Actions + AI & Risk Removals for this Paper Book
        paper_plan = app.orchestrator.live_copilot.get_daily_action_plan(
            check_calendar_today=False,
            custom_account_summary=book_acc,
            custom_open_positions=book_positions,
            custom_strategies=paper_book_strats,
        )
        p_sells = paper_plan.get("sell_actions") or []
        p_buys = paper_plan.get("buy_actions") or []
        p_vetoed = paper_plan.get("vetoed_signals") or []

        st.markdown("---")
        st.markdown(
            f"##### Planned Paper Execution (`{next_trading_day_iso}` Open) — "
            f"`{len(p_sells)}` Close · `{len(p_buys)}` Open · `{len(p_vetoed)}` Removed"
        )
        st.caption(
            f"Shows the exact positions this `$100k` Paper Book is scheduled to close or open at the `{next_trading_day_iso}` open "
            f"(using the same AI Catalyst filter, Pre-Open Gap check, and ATR risk sizing as Live Copilot)."
        )
        if p_sells or p_buys:
            for psa in p_sells:
                p_factors_html = _format_factors_html(psa.get("factors_considered") or [])
                st.markdown(
                    f"<div style='background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.3);border-radius:8px;padding:10px 14px;margin-bottom:8px;'>"
                    f"<div><strong style='color:#fca5a5;'>CLOSE (`SELL`) · {psa['ticker']}</strong> · "
                    f"<code>{psa['quantity_to_sell']} sh</code> · Est. Fill <code>${psa['reference_exit_price']:.2f}</code> · "
                    f"Est. P&L <strong>${psa['estimated_realised_pnl']:+,.2f}</strong> · "
                    f"<span style='color:#94a3b8;font-size:0.82rem;'>{psa.get('strategy_name', psa.get('strategy_id', ''))} — {psa.get('reason', '')}</span></div>"
                    f"{p_factors_html}</div>",
                    unsafe_allow_html=True,
                )
            for pba in p_buys:
                p_factors_html = _format_factors_html(pba.get("factors_considered") or [])
                ai_sent = float(pba.get("ai_catalyst_sentiment") or 0.0)
                ai_badge = (
                    f" · <span style='color:#4ade80;font-weight:600;'>AI Catalyst {ai_sent:+.2f}</span>"
                    if ai_sent >= 0.25
                    else f" · <span style='color:#94a3b8;'>AI {ai_sent:+.2f}</span>"
                )
                st.markdown(
                    f"<div style='background:rgba(56,189,248,0.07);border:1px solid rgba(56,189,248,0.28);border-radius:8px;padding:10px 14px;margin-bottom:8px;'>"
                    f"<div><strong style='color:#38bdf8;'>OPEN (`BUY`) · {pba['ticker']}</strong> ({pba.get('sector', '')}) · "
                    f"<code>{pba['recommended_shares']} sh</code> @ Limit <code>${pba['reference_entry_price']:.2f}</code> "
                    f"(Max Chase <code>${float(pba.get('max_chase_price') or pba['reference_entry_price']):.2f}</code>) · "
                    f"Notional <code>${pba['estimated_cost_usd']:,.0f}</code> ({pba['portfolio_weight_pct']:.1f}% of book) · "
                    f"Stop <code>${pba['stop_loss_price']:.2f}</code> · Target <code>${pba['take_profit_price']:.2f}</code> · "
                    f"1R Risk <code>${pba['estimated_risk_usd']:.0f}</code> ({pba['risk_pct_of_equity']:.2f}%) · "
                    f"<span style='color:#94a3b8;font-size:0.82rem;'>{pba.get('strategy_name', pba.get('strategy_id', ''))}{ai_badge}</span></div>"
                    f"{p_factors_html}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No new paper positions queued to open or close right now.")

        _render_removed_signals_section(st, p_vetoed, context_label=book_title_label)

        st.markdown("---")
        p_col1, p_col2 = st.columns([1.05, 1.15])
        with p_col1:
            st.markdown("##### Open Positions (Selected Book)")
            if book_positions:
                clean_pos = [
                    {
                        "Ticker": p["ticker"],
                        "Strategy": f"{p['strategy_id']} v{p['strategy_version']}",
                        "Opened": p["opened_date"],
                        "Hold": f"{p['holding_days']}d",
                        "Qty": p["quantity"],
                        "Entry": f"${p['avg_entry_price']:.2f}",
                        "Now": f"${p['current_price']:.2f}",
                        "Stop / Target": f"${p['stop_loss_price']:.2f} / ${p['take_profit_price']:.2f}" if p.get("stop_loss_price") else "—",
                        "Unrealised P&L": f"${p['unrealised_pnl']:+,.2f} ({p['unrealised_return_pct']:+.2f}%)",
                    }
                    for p in book_positions
                ]
                st.dataframe(clean_pos, width="stretch", hide_index=True)
            else:
                st.caption("No open positions in this book (`$100,000.00` cash).")

        with p_col2:
            st.markdown("##### All 6 Paper Books (`$100k` Master + 5 Pods)")
            book_comparison_rows = [
                {
                    "Book": "Master Combined" if b["book_type"] == "MASTER_COMBINED" else b["book_label"],
                    "Equity": f"${b['total_equity']:,.2f}",
                    "Total P&L": f"${b['total_pnl']:+,.2f} ({b['total_return_pct']:+.2f}%)",
                    "Win Rate": f"{b['win_rate_pct']:.1f}% ({b['closed_sells']})" if b["closed_sells"] > 0 else "—",
                    "Open / Cash": f"{b['open_positions_count']} · ${b['cash_balance']:,.0f}",
                }
                for b in all_paper_books
            ]
            st.dataframe(book_comparison_rows, width="stretch", hide_index=True)
            strat_pnl_rows = _summarize_pnl_by_strategy(book_ledger, book_positions, strats)
            if strat_pnl_rows:
                with st.expander("Strategy Attribution (Selected Book)", expanded=False):
                    st.dataframe(strat_pnl_rows, width="stretch", hide_index=True)

        st.markdown("---")
        st.markdown(f"##### Execution Ledger (`{book_date_span}`)")
        if book_ledger:
            unique_days = sorted({str(l["fill_date"]) for l in book_ledger if l.get("fill_date")}, reverse=True)
            unique_strats = sorted({f"{l['strategy_id']} v{l['strategy_version']}" for l in book_ledger})

            f_col1, f_col2, f_col3 = st.columns([2, 1.5, 2])
            with f_col1:
                selected_day = st.selectbox(
                    "Trading Day",
                    options=["All Trading Days"] + unique_days,
                    index=0,
                    key="paper_ledger_day_filter",
                )
            with f_col2:
                selected_side = st.selectbox(
                    "Side",
                    options=["All Sides (BUY & SELL)", "BUY (Entries Only)", "SELL (Exits Only)"],
                    index=0,
                    key="paper_ledger_side_filter",
                )
            with f_col3:
                selected_strat = st.selectbox(
                    "Strategy",
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

            clean_ledger = [
                {
                    "Date": l["fill_date"],
                    "Side": l["side"],
                    "Ticker": l["ticker"],
                    "Qty": l["quantity"],
                    "Fill Price": f"${l['fill_price']:.2f}",
                    "Notional": f"${l['gross_amount']:,.2f}",
                    "Costs": f"${float(l['commission_usd']) + float(l['slippage_usd']):.2f}",
                    "Realised P&L": f"${l['realised_pnl']:+,.2f}" if l["side"] == "SELL" else "—",
                    "Cash After": f"${l['cash_after']:,.2f}",
                    "Strategy": f"{l['strategy_id']} v{l['strategy_version']}",
                    "Notes": l["notes"],
                }
                for l in filtered_ledger
            ]
            st.dataframe(clean_ledger, width="stretch", hide_index=True)
        else:
            st.caption("No forward paper trades executed yet (`$100,000.00` cash). Trades populate automatically after daily runs.")

    # =========================================================================
    # TAB 2: STRATEGIES & BACKTESTS
    # =========================================================================
    with tabs[2]:
        _render_tab_header(
            st,
            "Strategy Scorecard, Machine-Readable Rules, 9-Gate SPY Audit & Historical Backtest Trades.",
            "Validation & Golden Base",
            "- **9-Gate + SPY Dominance**: Every active strategy beats `SPY` in both Full Period (`2023–2025`) and Out-of-Sample (`OOS`).\n"
            "- **Golden Base (`v1`) Pinning**: `v1` baseline strategies are permanently preserved and can be restored in one click.",
        )

        rb_col1, rb_col2, rb_col3 = st.columns([2.8, 1.1, 1.1])
        with rb_col1:
            st.markdown("##### Strategy Scorecard")
        with rb_col2:
            if st.button("Revert All to Base (v1)", width="stretch"):
                app.orchestrator.registry.revert_to_golden_baseline()
                st.rerun()
        with rb_col3:
            if st.button("Enforce Best Champions", width="stretch"):
                for sid in {s["strategy_id"] for s in strats}:
                    app.orchestrator.registry.rollback_to_best_champion(sid)
                st.rerun()

        display_scorecard = [
            {k: v for k, v in r.items() if not k.startswith("_") and k != "Live Trading Readiness"}
            for r in readiness_rows
        ]
        st.dataframe(display_scorecard, width="stretch", hide_index=True)

        exp_by_strat_ver: Dict[str, Dict[str, Any]] = {}
        for exp in state["experiments"]:
            k_sv = f"{exp['strategy_id']}:{exp['version']}"
            if k_sv not in exp_by_strat_ver:
                exp_by_strat_ver[k_sv] = exp

        st.markdown("##### Strategy Rulebooks & Backtest Audits")
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
                f"{r['Strategy']} — {r['Name']}  ·  "
                f"6M: {m.get('recent_6m_return_pct', 0.0):+.1f}% ({m.get('recent_6m_win_rate_pct', m.get('win_rate_pct', 0.0)):.0f}% WR)  ·  "
                f"Full: {m.get('total_return_pct', 0.0):+.1f}%  ·  SQN {m.get('sqn_score', 0.0):.2f}"
            )
            with st.expander(header_label, expanded=False):
                g_col1, g_col2 = st.columns([1.3, 1.7])
                with g_col1:
                    st.markdown("**Thesis & Universe**")
                    st.write(f"- **Origin**: {genesis['origin']}")
                    st.write(f"- **Edge**: {genesis['edge']}")
                    st.write(f"- **Regime**: {genesis['regime']}")
                    st.write(f"- **Holding Period**: `{s['holding_period_min_days']}–{s['holding_period_max_days']}` trading days")
                    st.write(f"- **Universe ({len(s['universe'])})**: `{', '.join(s['universe'])}`")
                with g_col2:
                    st.markdown("**Machine-Readable Parameters**")
                    rule_c1, rule_c2, rule_c3 = st.columns(3)
                    with rule_c1:
                        st.caption("Entry Rules")
                        for rk, rv in (s.get("entry_rules") or {}).items():
                            st.write(f"- `{rk}`: **{rv}**")
                    with rule_c2:
                        st.caption("Exit Rules")
                        for rk, rv in (s.get("exit_rules") or {}).items():
                            st.write(f"- `{rk}`: **{rv}**")
                    with rule_c3:
                        st.caption("Risk Sizing")
                        for rk, rv in (s.get("risk_params") or {}).items():
                            st.write(f"- `{rk}`: **{rv}**")

                st.markdown("---")
                c_left, c_mid, c_right = st.columns([1.15, 1.55, 1.1])
                with c_left:
                    st.markdown("**9-Gate Audit**")
                    if checks:
                        for gate_name, passed in checks.items():
                            icon = "PASS" if passed else "FAIL"
                            clean_gate = gate_name.replace("_", " ").title()
                            st.write(f"- **[{icon}]** {clean_gate}")
                with c_mid:
                    st.markdown("**Performance vs. S&P 500 (`SPY`)**")
                    st.write(
                        f"- **Full (`2023–2025`)**: `{m.get('total_return_pct', 0.0):+.2f}%` vs SPY `{m.get('benchmark_return_pct', 0.0):+.2f}%` "
                        f"(**α `{m.get('excess_return_vs_spy_pct', 0.0):+.2f}%`**)"
                    )
                    st.write(
                        f"- **Out-of-Sample (`OOS`)**: `{oos.get('total_return_pct', 0.0):+.2f}%` vs SPY `{oos.get('benchmark_return_pct', 0.0):+.2f}%`"
                    )
                    st.write(
                        f"- **Recent 6M (`126d`)**: `{m.get('recent_6m_return_pct', 0.0):+.2f}%` "
                        f"(α `{m.get('recent_6m_excess_vs_spy_pct', 0.0):+.2f}%` · WR `{m.get('recent_6m_win_rate_pct', m.get('win_rate_pct', 0.0)):.1f}%`)"
                    )
                    st.write(
                        f"- **Rolling 6M & SQN**: `{m.get('rolling_6m_win_pct', 100.0):.1f}%` profitable windows · "
                        f"SQN `{m.get('sqn_score', 0.0):.2f}` · Payoff `{m.get('payoff_ratio', 1.5):.2f}x`"
                    )
                    st.write(
                        f"- **Risk & Efficiency**: MaxDD `-{m.get('max_drawdown_pct', 0.0):.2f}%` · "
                        f"Sharpe `{m.get('sharpe_ratio', 0.0):.2f}` · PF `{m.get('profit_factor', 0.0):.2f}` · "
                        f"WF `{float(wf.get('consistency_ratio', 0.0))*100:.0f}%`"
                    )
                with c_right:
                    st.markdown("**Version Control**")
                    st.write(f"- Status: **{r['Status']}**")
                    st.write(f"- Gates: **{r['Gates']}**")
                    st.write(f"- Paper Fills: **{r['_paper_closed']}** (`${r['_paper_net_pnl']:+,.2f}`)")
                    if st.button(
                        f"Revert to v1 Base",
                        key=f"revert_v1_{s['strategy_id']}_{s['version']}",
                        width="stretch",
                    ):
                        app.orchestrator.registry.revert_to_golden_baseline(s["strategy_id"])
                        st.rerun()

                if exp_match and exp_match.get("trades"):
                    st.markdown(f"**Recent Backtest Trades (`{len(exp_match['trades'])}` total)**")
                    st.dataframe(exp_match["trades"][:25], width="stretch", hide_index=True)

    # =========================================================================
    # TAB 3: AI & WATCHLIST
    # =========================================================================
    with tabs[3]:
        _render_tab_header(
            st,
            "Daily Multi-Factor Stock Rankings & Direct IDE AI Bridge.",
            "IDE AI Workflow",
            "- **Option A**: Type **`run`** in the Antigravity IDE chat to scan live web news and evaluate candidate upgrades.\n"
            "- **Option B**: Copy the prompt below into any LLM and paste the JSON response to enrich catalysts & run the 9-gate tournament.",
        )

        if st.session_state.get("_ide_bridge_flash"):
            st.success(st.session_state.pop("_ide_bridge_flash"))

        st.markdown("##### 1. Ranked US Equity Watchlist")
        reports_summary = [
            {
                "Rank": idx + 1,
                "Ticker": r["ticker"],
                "Company": r["company_name"],
                "Price": f"${r['current_price']:.2f}",
                "Sector": r["market_and_sector_context"]["sector"],
                "20d RS vs SPY": f"{r['relative_strength_vs_spy_20d']:+.2f}%",
                "Volume (20d)": f"{r['volume_analysis']['volume_ratio_20']:.2f}x",
                "Archetype": r["suggested_strategy_family"],
                "Score": r["composite_rank_score"],
                "Confidence": f"{r['research_confidence_score'] * 100:.0f}%",
                "Catalyst": r.get("catalyst_assessment", ""),
                "Bullish Thesis": r["bullish_thesis"],
            }
            for idx, r in enumerate(state["research_reports"])
        ]
        st.dataframe(reports_summary, width="stretch", hide_index=True)

        st.markdown("---")
        with st.expander("2. IDE AI Prompt & JSON Bridge (Manual LLM Feed)", expanded=False):
            ai_c1, ai_c2 = st.columns([1.2, 1.4])
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
                f"You are the Chief Quantitative Swing Strategist. Today is {today_iso} (latest close: {latest_bar_date}).\n"
                f"Top ranked US equity candidates: {json.dumps(compact_prompt_context)}\n\n"
                "Search live news/earnings catalysts for the top tickers and propose 1-2 regime-tuned strategy parameter upgrades. "
                "Return ONLY valid JSON matching:\n"
                "{\n"
                '  "research_updates": [{"ticker": "NVDA", "bullish_thesis": "...", "bearish_thesis": "...", "catalyst_assessment": "...", "sentiment_score": 0.80, "research_confidence_score": 0.90}],\n'
                '  "candidate_strategies": []\n'
                "}"
            )
            with ai_c1:
                st.caption(f"Last IDE AI Run: `{last_ide_run_ts}` · Or type **`run`** in Antigravity IDE chat.")
                st.code(ready_prompt_text, language="json")
            with ai_c2:
                default_sample_json = json.dumps(
                    {
                        "research_updates": [
                            {
                                "ticker": top_reps[0]["ticker"] if top_reps else "NVDA",
                                "bullish_thesis": "Strong institutional relative strength vs SPY with expanding volume.",
                                "bearish_thesis": "Watch sector multiple compression if yields spike.",
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
                    "Paste JSON Output (`research_updates`, `candidate_strategies`)",
                    value=default_sample_json,
                    height=140,
                    key="ide_bridge_json_textarea",
                )
                if st.button("Apply AI Output to Engine", width="stretch"):
                    try:
                        parsed_payload = json.loads(ai_json_input)
                        res_apply = app.orchestrator.apply_ide_ai_cycle(payload=parsed_payload)
                        enriched_n = len(res_apply.get("research_tickers_enriched") or [])
                        tourn_list = res_apply.get("tournament_results") or []
                        prom_n = sum(1 for t in tourn_list if t.get("promoted"))
                        st.session_state["_ide_bridge_flash"] = (
                            f"Applied AI output (`{res_apply['session_date']}`): "
                            f"enriched `{enriched_n}` report(s), evaluated `{len(tourn_list)}` candidate(s) (`{prom_n}` promoted)."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Invalid AI JSON payload: {exc}")

        if state["proposals"]:
            with st.expander("3. Post-Session Experiment Proposals", expanded=False):
                st.dataframe(state["proposals"], width="stretch", hide_index=True)

    # =========================================================================
    # TAB 4: RISK & LOGS
    # =========================================================================
    with tabs[4]:
        _render_tab_header(
            st,
            "Sector Exposure vs. 30% Cap, 4-Window Walk-Forward Folds, Risk Vetoes & Execution Logs.",
            "Risk Governance",
            "- **Hard Caps**: `1.0%` max risk per trade, `5.0%` max portfolio heat, `30%` sector cap (`50%` on `<= $15k` starter accounts), and `15.0%` drawdown circuit breaker.",
        )
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Sector Concentration vs. 30% Cap")
            if acc["sector_exposures_pct"]:
                sec_rows = [
                    {"Sector": sec, "Exposure": f"{pct:.2f}%", "Limit": "30.00%"}
                    for sec, pct in acc["sector_exposures_pct"].items()
                ]
                st.dataframe(sec_rows, width="stretch", hide_index=True)
            else:
                st.caption("0% paper sector exposure (100% cash).")
        with c2:
            st.markdown("##### Walk-Forward Validation Folds (4 Windows)")
            if strats:
                strat_labels = [f"{s['strategy_id']} v{s['version']} ({s['name']})" for s in strats]
                sel_idx = st.selectbox(
                    "Strategy",
                    options=list(range(len(strats))),
                    format_func=lambda i: strat_labels[i],
                    key="wf_strat_select",
                    label_visibility="collapsed",
                )
                chosen_s = strats[sel_idx]
                if chosen_s.get("validation_summary"):
                    wf_windows = (chosen_s["validation_summary"].get("walk_forward") or {}).get("windows", [])
                    st.dataframe(wf_windows, width="stretch", hide_index=True)

        st.markdown("---")
        l_col1, l_col2 = st.columns(2)
        with l_col1:
            st.markdown("##### Portfolio Risk Vetoes")
            if state["risk_alerts"]:
                st.dataframe(state["risk_alerts"], width="stretch", hide_index=True)
            else:
                st.caption("No risk alerts triggered.")
        with l_col2:
            st.markdown("##### Workflow Execution Log")
            st.dataframe(state["jobs"], width="stretch", hide_index=True)

    # =========================================================================
    # TAB 5: GUIDE
    # =========================================================================
    with tabs[5]:
        st.markdown("##### System Architecture & Operating Guide")
        st.caption(
            "Deterministic code computes indicators, enforces risk guardrails, and executes backtests; "
            "AI agents (`run` in IDE) enrich live catalysts and propose candidate strategy versions."
        )

        st.markdown(MENTAL_MODEL_HTML, unsafe_allow_html=True)

        if "walkthrough_step" not in st.session_state:
            st.session_state["walkthrough_step"] = "step_daily_vs_weekly"

        b1, b2, b3, b4, b5 = st.columns(5)
        if b1.button("1. Daily vs Weekly", width="stretch"):
            st.session_state["walkthrough_step"] = "step_daily_vs_weekly"
        if b2.button("2. Golden Base Models", width="stretch"):
            st.session_state["walkthrough_step"] = "step_multi_strategy"
        if b3.button("3. Risk & Ratchets", width="stretch"):
            st.session_state["walkthrough_step"] = "step_risk"
        if b4.button("4. Validation & SQN", width="stretch"):
            st.session_state["walkthrough_step"] = "step_readiness"
        if b5.button("5. IDE AI (`run`)", width="stretch"):
            st.session_state["walkthrough_step"] = "step_user_role"

        step_info = {
            "step_daily_vs_weekly": (
                "**1. Daily Run, Weekly Run & Market-Open Execution**\n\n"
                "- **Daily Run (`Mon–Fri 21:30 UTC`)**: Computes signals from completed daily closes, evaluates exits and `+1.0R` stop ratchets on open holdings, and sizes new `BUY` setups.\n"
                "- **Market-Open Execution (`9:30–9:45 AM ET`)**: Place **Day Limit Orders inside the Buy-Zone (`Ref - 0.25 ATR` to `Ref + 0.50 ATR`)** with an attached `GTC` Stop-Loss & Take-Profit bracket. Skip if the open gaps above `Max Chase`.\n"
                "- **Weekly Run (`Saturday 10:00 SGT`)**: Evaluates candidate `v+1` upgrades in the 9-gate Out-of-Sample & Walk-Forward tournament."
            ),
            "step_multi_strategy": (
                "**2. Five Golden Base (`v1`) Models — 2.3-Yr, Recent 6M & `SQN` Evidence**\n\n"
                "- **`strat_volatility_breakout` (#1 Champion)**: `+77.5%` Full · `+22.0%` OOS · **`+11.0%` 6M (`67.9%` WR)** · **`SQN 3.55`**\n"
                "- **`strat_mean_reversion_bb` (#2 Pullback Fallback)**: `+74.1%` Full · `+10.2%` OOS · **`+9.5%` 6M (`61.1%` WR)** · **`SQN 2.28`**\n"
                "- **`strat_momentum_trend`**: `+71.4%` Full · `+16.3%` OOS · **`+7.5%` 6M (`61.5%` WR)** · **`SQN 3.29`**\n"
                "- **`strat_pead_drift`**: `+73.8%` Full · `+17.8%` OOS · **`+4.7%` 6M (`51.5%` WR)** · **`SQN 2.99`**\n"
                "- **`strat_sector_rotation_leaders`**: `+67.3%` Full · `+18.5%` OOS · **`+6.9%` 6M (`57.7%` WR)** · **`SQN 2.91`**"
            ),
            "step_risk": (
                "**3. 4-Way Exit Bracket & Risk Guardrails**\n\n"
                "- **`+1.0R` to `+1.25R` Stop Ratchet**: Once a trade reaches `+1.0R` profit, raise your Stop-Loss to Breakeven / Chandelier trail.\n"
                "- **Momentum Stall & `Day N` Time-Stop (`8–15d`)**: Exits early if trend alignment breaks or on Day $N_{\\max}$ if Target is not hit.\n"
                "- **Portfolio Caps**: `1.0%` risk per trade, `5.0%` max open heat, `15.0%` single stock (`25%` on `<= $15k` accounts), `30.0%` sector (`50%` on `<= $15k` accounts), `15.0%` drawdown kill switch."
            ),
            "step_readiness": (
                "**4. Dual-Horizon Validation (`2.3-Yr` + `6-Month` + `SQN`)**\n\n"
                "- **Why Both Horizons**: The 2.3-year window proves survival across bull, correction, and rate-shock regimes; the **6-Month (`126d`) window** and **Van Tharp `SQN`** measure trade-by-trade consistency over a realistic 6-month live deployment."
            ),
            "step_user_role": (
                "**5. Incorporating AI (`type run in IDE`)**\n\n"
                "- **Strict Firewall**: AI never invents prices or overrides risk limits.\n"
                "- **Live Catalyst Filter**: Typing **`run`** in the Antigravity IDE searches live web news (`search_web`)—automatically vetoing `BUY` setups with bearish breaking catalysts (`<= -0.35`) and boosting high-conviction catalysts (`>= +0.25`)."
            ),
        }
        st.info(step_info.get(st.session_state["walkthrough_step"], step_info["step_daily_vs_weekly"]))


if __name__ == "__main__":
    main()
