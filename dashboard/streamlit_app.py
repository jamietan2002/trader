"""Streamlit Community Cloud & Local Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

v2.2 Autonomous 3-Pod Paper Trading Hub (Numbers-First Entry & Exit Plans · Zero Clutter):
1. Day-by-Day Pod Decision Journal — Intuitive chronological day-by-day diary across all 3 Alpaca Paper Pods with exact Entry & 4-Step Exit Strategy Numbers and concise plain-English explanations.
2. Active Holdings & Exit Plans — Real-time Long & Short positions across all 3 Alpaca Paper accounts with scannable 4-Point Exit Numbers, GTC OCO verification, Broker Orders, and a 3-Pod Entry/Exit Strategy Rules Cheat-Sheet.
3. Strategy Tournament & Mistake Analyzer — 9-Gate Out-of-Sample / Walk-Forward leaderboard (6 strategy families incl. Bearish Breakdown) + Post-Trade Attribution & Auto-Tuner Mistake Analyzer.
4. Live News, Universe & System Health — 24/7 Alpaca News & AI Catalyst stream, 40+ Core & Dynamic Universe Explorer with on-demand ticker onboarding, and autonomous job logs.
"""

from __future__ import annotations

import html
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

# Ensure repository root is on sys.path when Streamlit runs `dashboard/streamlit_app.py`
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ALPACA_PAPER_PORTAL_URL = "https://app.alpaca.markets/paper/dashboard/overview"

POD_DISPLAY_NAMES = {
    "pod_1_breakout": "Pod #1 · Breakout & Breakdown",
    "pod_2_mean_reversion": "Pod #2 · Value Pullback & Fade",
    "pod_3_momentum": "Pod #3 · Momentum & Drift",
}

CLASSY_MINIMAL_CSS = """
<style>
  .block-container {
    padding-top: 1.25rem !important;
    padding-bottom: 2.5rem !important;
    max-width: 1460px !important;
  }
  [data-testid="stMetric"] {
    background: rgba(15, 23, 42, 0.48);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 8px;
    padding: 11px 14px !important;
  }
  [data-testid="stMetricLabel"] {
    font-size: 0.72rem !important;
    text-transform: uppercase;
    letter-spacing: 0.045em;
    color: #94a3b8 !important;
    font-weight: 600 !important;
  }
  [data-testid="stMetricValue"] {
    font-size: 1.35rem !important;
    font-weight: 600 !important;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
  }
  [data-baseweb="tab-list"] {
    gap: 8px !important;
    border-bottom: 1px solid rgba(148, 163, 184, 0.18) !important;
    padding-bottom: 2px !important;
  }
  [data-baseweb="tab"] {
    font-size: 0.87rem !important;
    font-weight: 600 !important;
    padding: 9px 16px !important;
  }
  hr {
    margin: 1.0rem 0 !important;
    border-color: rgba(148, 163, 184, 0.14) !important;
  }
  body:has([data-testid="stStatusWidget"]) button,
  body:has([data-testid="stStatusWidget"]) input {
    pointer-events: none !important;
    opacity: 0.55 !important;
    cursor: wait !important;
  }
</style>
"""


def _sync_streamlit_secrets_to_env(st: Any) -> None:
    """Safely mirror Streamlit Cloud secrets into os.environ without logging values."""
    secret_keys = (
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "ALPACA_API_KEY_2",
        "ALPACA_SECRET_KEY_2",
        "ALPACA_API_KEY_3",
        "ALPACA_SECRET_KEY_3",
        "POLYGON_API_KEY",
        "MARKET_DATA_PROVIDER",
    )
    try:
        secrets_obj = getattr(st, "secrets", None)
        if secrets_obj is None:
            return
        for key in secret_keys:
            if not os.environ.get(key):
                val = secrets_obj.get(key)
                if val:
                    os.environ[key] = str(val).strip()
    except Exception:
        pass


def _format_human_date(iso_dt: str) -> str:
    """Format '2026-11-13' into 'Friday, Nov 13, 2026'."""
    try:
        d_obj = date.fromisoformat(str(iso_dt)[:10])
        return d_obj.strftime("%A, %b %d, %Y")
    except Exception:
        return str(iso_dt)


def _compute_exit_ladder_numbers(
    side: str,
    entry_px: float,
    init_stop_px: float,
    cur_stop_px: float,
    stage1_trigger_px: float = 0.0,
    stage1_stop_px: float = 0.0,
    stage2_trigger_px: float = 0.0,
    stage2_stop_px: float = 0.0,
    target_px: float = 0.0,
) -> Dict[str, float]:
    """Derive complete, consistent 4-step exit strategy numbers for both current and historical records."""
    is_short = str(side or "LONG").upper() == "SHORT"
    eff_init_stop = init_stop_px if init_stop_px > 0 else cur_stop_px
    one_r = abs(entry_px - eff_init_stop) if (entry_px > 0 and eff_init_stop > 0) else max(entry_px * 0.03, 0.01)
    one_r = max(one_r, 0.01)

    if is_short:
        s1_trig = stage1_trigger_px if stage1_trigger_px > 0 else round(entry_px - 1.0 * one_r, 2)
        s1_lock = stage1_stop_px if stage1_stop_px > 0 else round(entry_px - 0.10 * one_r, 2)
        s2_trig = stage2_trigger_px if stage2_trigger_px > 0 else round(entry_px - 1.65 * one_r, 2)
        s2_lock = stage2_stop_px if stage2_stop_px > 0 else round(entry_px - 1.0 * one_r, 2)
        tp = target_px if target_px > 0 else round(entry_px - 2.2 * one_r, 2)
        rr = round(max(0.0, (entry_px - tp) / one_r), 2)
    else:
        s1_trig = stage1_trigger_px if stage1_trigger_px > 0 else round(entry_px + 1.0 * one_r, 2)
        s1_lock = stage1_stop_px if stage1_stop_px > 0 else round(entry_px + 0.10 * one_r, 2)
        s2_trig = stage2_trigger_px if stage2_trigger_px > 0 else round(entry_px + 1.65 * one_r, 2)
        s2_lock = stage2_stop_px if stage2_stop_px > 0 else round(entry_px + 1.0 * one_r, 2)
        tp = target_px if target_px > 0 else round(entry_px + 2.2 * one_r, 2)
        rr = round(max(0.0, (tp - entry_px) / one_r), 2)

    return {
        "one_r": one_r,
        "init_stop": eff_init_stop,
        "cur_stop": cur_stop_px if cur_stop_px > 0 else eff_init_stop,
        "s1_trig": s1_trig,
        "s1_lock": s1_lock,
        "s2_trig": s2_trig,
        "s2_lock": s2_lock,
        "tp": tp,
        "rr": rr,
    }


def _render_four_step_exit_grid_html(
    stop_px: float,
    stop_sub: str,
    s1_trig: float,
    s1_lock: float,
    s2_trig: float,
    s2_lock: float,
    tp_px: float,
    tp_sub: str,
) -> str:
    """Render a crisp 4-column numerical Exit Strategy strip (no charts/diagrams)."""
    return (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:8px;margin:7px 0;'>"
        f"<div style='background:rgba(239,68,68,0.09);border:1px solid rgba(239,68,68,0.28);border-radius:6px;padding:7px 10px;'>"
        f"<div style='font-size:0.69rem;color:#fca5a5;font-weight:700;text-transform:uppercase;'>1 · Hard Stop (-1.0R)</div>"
        f"<div style='font-size:0.98rem;font-weight:700;color:#f8fafc;font-family:monospace;margin-top:2px;'>${stop_px:.2f}</div>"
        f"<div style='font-size:0.72rem;color:#cbd5e1;'>{html.escape(stop_sub)}</div>"
        "</div>"
        f"<div style='background:rgba(234,179,8,0.09);border:1px solid rgba(234,179,8,0.28);border-radius:6px;padding:7px 10px;'>"
        f"<div style='font-size:0.69rem;color:#fde047;font-weight:700;text-transform:uppercase;'>2 · +1.0R Breakeven Trigger</div>"
        f"<div style='font-size:0.98rem;font-weight:700;color:#f8fafc;font-family:monospace;margin-top:2px;'>Hit ${s1_trig:.2f}</div>"
        f"<div style='font-size:0.72rem;color:#cbd5e1;'>Moves stop → <code>${s1_lock:.2f}</code> (+0.1R)</div>"
        "</div>"
        f"<div style='background:rgba(168,85,247,0.10);border:1px solid rgba(168,85,247,0.28);border-radius:6px;padding:7px 10px;'>"
        f"<div style='font-size:0.69rem;color:#d8b4fe;font-weight:700;text-transform:uppercase;'>3 · +1.65R Profit Lock</div>"
        f"<div style='font-size:0.98rem;font-weight:700;color:#f8fafc;font-family:monospace;margin-top:2px;'>Hit ${s2_trig:.2f}</div>"
        f"<div style='font-size:0.72rem;color:#cbd5e1;'>Locks stop → <code>${s2_lock:.2f}</code> (+1.0R)</div>"
        "</div>"
        f"<div style='background:rgba(16,185,129,0.10);border:1px solid rgba(16,185,129,0.28);border-radius:6px;padding:7px 10px;'>"
        f"<div style='font-size:0.69rem;color:#6ee7b7;font-weight:700;text-transform:uppercase;'>4 · Take-Profit &amp; Time Cap</div>"
        f"<div style='font-size:0.98rem;font-weight:700;color:#f8fafc;font-family:monospace;margin-top:2px;'>${tp_px:.2f}</div>"
        f"<div style='font-size:0.72rem;color:#cbd5e1;'>{html.escape(tp_sub)}</div>"
        "</div>"
        "</div>"
    )


def _render_pod_rules_cheatsheet_html(pods_list: List[Dict[str, Any]]) -> str:
    """Render concise numerical Entry & Exit Strategy Rules for each of the 3 Autonomous Pods."""
    pod_specs = [
        {
            "pod_id": "pod_1_breakout",
            "title": "Pod #1 · Breakout & Breakdown",
            "edge": "Buys tight 10-day consolidations breaking 20-day highs on volume; shorts high-volume support breakdowns.",
            "long_entry": "Close within 3% of 20d High · > SMA50 · Vol ≥ 1.15x · 10d Range ≤ 25% · 20d RS vs SPY ≥ +2.0%",
            "short_entry": "Close breaks 20d Low · < SMA50 · Vol ≥ 1.25x · Bearish/Weak RS (vetoed if News ≥ +0.30)",
            "exit_nums": "Stop 1.9x ATR (-1R) · +1.0R → BE+0.1R · +1.65R → Lock +1.0R · Target 4.0x–4.5x ATR · Time-Stop 15d",
        },
        {
            "pod_id": "pod_2_mean_reversion",
            "title": "Pod #2 · Value Pullback & Fade",
            "edge": "Buys institutional uptrend leaders pulling back calmly toward rising 20-day support; fades overbought bear rallies.",
            "long_entry": "Close > SMA200 · SMA20 > SMA50 · Within +8% of SMA20 · RSI(14) 50–74 · 20d RS vs SPY ≥ +1.5%",
            "short_entry": "Downtrend (< SMA50 & < SMA200) · Overbought bounce RSI ≥ 62 into resistance",
            "exit_nums": "Stop 1.8x ATR (-1R) · +1.0R → BE+0.1R · +1.65R → Lock +1.0R · Target 3.6x–4.0x ATR · Time-Stop 10d",
        },
        {
            "pod_id": "pod_3_momentum",
            "title": "Pod #3 · Momentum & Drift",
            "edge": "Rides persistent relative-strength leaders and post-earnings catalyst winners; shorts post-miss downward drift.",
            "long_entry": "Close > SMA20 > SMA50 · 20d Return ≥ +3.5% · 20d RS vs SPY ≥ +2.2% · Vol ≥ 0.95x",
            "short_entry": "Close < SMA20 < SMA50 · Negative 20d RS & post-catalyst distribution",
            "exit_nums": "Stop 2.0x ATR (-1R) · +1.0R → BE+0.1R · +1.65R → Lock +1.0R · Target 4.2x–4.5x ATR · Time-Stop 15d",
        },
    ]

    acct_by_pod = {}
    for p in pods_list:
        pid = str(p.get("pod_id") or "")
        bs = p.get("broker_state") or p.get("broker") or {}
        acct_by_pod[pid] = str(bs.get("alpaca_account_number") or bs.get("account_number") or "Paper")

    cards: List[str] = []
    for sp in pod_specs:
        acct = acct_by_pod.get(sp["pod_id"], "Paper")
        cards.append(
            f"<div style='background:rgba(15,23,42,0.56);border:1px solid rgba(148,163,184,0.18);"
            f"border-left:3px solid #38bdf8;border-radius:7px;padding:10px 12px;margin-bottom:8px;font-size:0.79rem;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;'>"
            f"<strong style='color:#f8fafc;font-size:0.85rem;'>{html.escape(sp['title'])}</strong>"
            f"<code style='color:#38bdf8;font-size:0.73rem;'>{html.escape(acct)}</code></div>"
            f"<div style='color:#cbd5e1;margin-bottom:5px;'>{html.escape(sp['edge'])}</div>"
            f"<div style='color:#94a3b8;'><strong>🟢 Long Trigger:</strong> <code>{html.escape(sp['long_entry'])}</code></div>"
            f"<div style='color:#94a3b8;margin-top:2px;'><strong>🔴 Short Trigger:</strong> <code>{html.escape(sp['short_entry'])}</code></div>"
            f"<div style='color:#e2e8f0;margin-top:4px;'><strong>🎯 Exit Numbers:</strong> <code>{html.escape(sp['exit_nums'])}</code></div>"
            "</div>"
        )
    return "".join(cards)


def _render_equity_curve_svg(curve: List[Dict[str, Any]], height: int = 195) -> str:
    """Render a clean SVG equity curve vs $100k baseline for Tab 3 Strategy Inspector."""
    if len(curve) < 2:
        return ""
    width = 680
    pad_l, pad_r, pad_t, pad_b = 14, 72, 18, 22
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    vals = [float(pt.get("equity", 100000.0)) for pt in curve]
    min_v = min(min(vals), 100000.0) * 0.99
    max_v = max(max(vals), 100000.0) * 1.01
    span = max(max_v - min_v, 1.0)

    def _y(v: float) -> float:
        return pad_t + plot_h - ((v - min_v) / span) * plot_h

    pts = [
        f"{pad_l + (i / (len(vals) - 1)) * plot_w:.1f},{_y(v):.1f}"
        for i, v in enumerate(vals)
    ]
    base_y = _y(100000.0)
    end_col = "#10b981" if vals[-1] >= 100000.0 else "#ef4444"
    return (
        f"<svg viewBox='0 0 {width} {height}' style='width:100%;height:auto;background:rgba(15,23,42,0.58);"
        f"border:1px solid rgba(148,163,184,0.16);border-radius:8px;display:block;'>"
        f"<line x1='{pad_l}' y1='{base_y:.1f}' x2='{width - pad_r}' y2='{base_y:.1f}' stroke='rgba(148,163,184,0.28)' stroke-dasharray='4,3'/>"
        f"<polyline fill='none' stroke='{end_col}' stroke-width='2.0' points='{' '.join(pts)}'/>"
        f"<text x='{width - pad_r + 5}' y='{_y(vals[-1]) + 3:.1f}' fill='{end_col}' font-size='9.5' font-weight='600' font-family='monospace'>${vals[-1]:,.0f}</text>"
        f"<text x='{pad_l + 4}' y='{height - 6}' fill='#64748b' font-size='9' font-family='monospace'>{curve[0].get('date', '')}</text>"
        f"<text x='{width - pad_r - 60}' y='{height - 6}' fill='#64748b' font-size='9' font-family='monospace'>{curve[-1].get('date', '')}</text>"
        f"</svg>"
    )


def _sentiment_badge_html(score: float, label: str = "") -> str:
    if score <= -0.35:
        col, bg, txt = "#fca5a5", "rgba(239,68,68,0.18)", f"BEARISH VETO ({score:+.2f})"
    elif score <= -0.15:
        col, bg, txt = "#fdba74", "rgba(249,115,22,0.16)", f"Bearish ({score:+.2f})"
    elif score >= 0.30:
        col, bg, txt = "#6ee7b7", "rgba(16,185,129,0.18)", f"BULLISH CATALYST ({score:+.2f})"
    elif score >= 0.15:
        col, bg, txt = "#93c5fd", "rgba(59,130,246,0.16)", f"Positive ({score:+.2f})"
    else:
        col, bg, txt = "#cbd5e1", "rgba(148,163,184,0.14)", f"Neutral ({score:+.2f})"
    extra = f" · {html.escape(label)}" if label else ""
    return (
        f"<span style='background:{bg};color:{col};padding:2px 8px;border-radius:999px;"
        f"font-size:0.73rem;font-weight:600;'>{txt}{extra}</span>"
    )


def main() -> None:
    try:
        import streamlit as st
    except ImportError:
        print(
            "Streamlit is not installed in the current environment. "
            "Run `python3 main.py serve` to launch the built-in web server on http://127.0.0.1:8080."
        )
        return

    st.set_page_config(
        page_title="Swing Trading AI · 3-Pod Autonomous Paper Hub",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CLASSY_MINIMAL_CSS, unsafe_allow_html=True)
    _sync_streamlit_secrets_to_env(st)

    _code_version = "2026-11-14-v2.3"
    import api.server as _srv_mod
    import core.market_data.models as _md_mod
    import core.execution.paper_broker as _pb_check_mod
    if (
        getattr(_srv_mod, "_STREAMLIT_SYNC_VERSION", None) != _code_version
        or not hasattr(_pb_check_mod, "AlpacaPaperPodManager")
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
        import core.market_data.models as _md_mod

        setattr(_srv_mod, "_STREAMLIT_SYNC_VERSION", _code_version)

    USTradingCalendar = _md_mod.USTradingCalendar
    app = _srv_mod.PlatformApplication()
    app.db.initialize_schema()

    if not app.orchestrator.registry.list_strategies():
        with st.spinner("Initializing baseline strategies & market data..."):
            app.orchestrator.bootstrap_baseline_system()
    app.orchestrator.ensure_all_golden_strategies_registered()

    state = app.get_dashboard_state()
    pods_payload = state.get("strategy_pods") or {"pods": []}
    pods_list: List[Dict[str, Any]] = pods_payload.get("pods") or []
    mistake_analyzer: Dict[str, Any] = state.get("mistake_analyzer") or {}
    live_catalysts: List[Dict[str, Any]] = state.get("live_catalysts") or []
    universe_meta: List[Dict[str, Any]] = state.get("universe_metadata") or []
    strategies: List[Dict[str, Any]] = state.get("strategies") or []
    experiments: List[Dict[str, Any]] = state.get("experiments") or []
    jobs: List[Dict[str, Any]] = state.get("jobs") or []
    risk_alerts: List[Dict[str, Any]] = state.get("risk_alerts") or []

    today_dt = date.today()
    today_iso = today_dt.isoformat()
    today_weekday = today_dt.strftime("%A")
    is_trading_day = USTradingCalendar.is_trading_day(today_dt)
    is_mkt_open = USTradingCalendar.is_market_open()
    non_trading_reason = USTradingCalendar.non_trading_reason(today_dt)
    next_trading_day = USTradingCalendar.next_trading_day(today_dt, include_same_day=is_trading_day)
    open_sgt = USTradingCalendar.market_open_sgt() if hasattr(USTradingCalendar, "market_open_sgt") else "10:30 PM SGT"
    close_sgt = USTradingCalendar.market_close_sgt() if hasattr(USTradingCalendar, "market_close_sgt") else "5:00 AM SGT"
    now_sgt = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%H:%M:%S SGT")
    now_et = datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M:%S ET")

    # ---------------- CLEAN SIDEBAR (100% PAPER POD FOCUSED) ----------------
    with st.sidebar:
        st.markdown("### ⚡ Autonomous Paper Hub")
        if is_mkt_open:
            st.success(f"**MARKET OPEN** · `{now_et}`\n\n`{now_sgt}` · NYSE / NASDAQ")
        elif is_trading_day:
            st.info(
                f"**{today_iso}** ({today_weekday})\n\n"
                f"Session Hours: **{open_sgt} – {close_sgt}**\n\nNow: `{now_sgt}` (`{now_et}`)"
            )
        else:
            st.warning(
                f"**{today_iso}** ({today_weekday})\n\n"
                f"{non_trading_reason}\n\nNext Session: **{next_trading_day}**"
            )

        st.markdown("---")
        st.markdown(
            "#### 🤖 Autonomous Schedule\n"
            "• **Daily Runs (`Mon–Fri`)**:\n"
            "  - `5:30 AM SGT` · Post-Close Scan\n"
            "  - `9:00/10:00 PM SGT` · Pre-Open News & Gap Gate\n"
            "  - `9:35/10:35 PM SGT` · Market-Open Execution\n"
            "• **Weekly Run (`Sat 10:00 AM SGT`)**:\n"
            "  - Mistake Analyzer + 9-Gate Tournament\n"
            "• **IDE AI (`type run`)**:\n"
            "  - Live Web Catalyst Search + AI Strategy Tuning"
        )

        st.markdown("---")
        st.markdown(
            f"🔗 **[Open Alpaca Paper Portal ↗]({ALPACA_PAPER_PORTAL_URL})**\n\n"
            f"• Mode: `100% Autonomous Paper`\n"
            f"• Active Universe: **{len(universe_meta)} liquid US equities**\n"
            f"• Strategies Tracked: **{len(strategies)} versions**"
        )

    # ---------------- AGGREGATE LIVE POD STATE ----------------
    all_open_holdings: List[Dict[str, Any]] = []
    all_broker_orders: List[Dict[str, Any]] = []
    today_entries_count = 0

    for pod in pods_list:
        pod_name = str(pod.get("label") or pod.get("short_label") or pod.get("pod_name") or pod.get("pod_id") or "")
        pod_id = str(pod.get("pod_id") or "")
        b_st = pod.get("broker_state") or pod.get("broker") or {}
        acct_num = str(b_st.get("alpaca_account_number") or b_st.get("account_number") or "N/A")
        today_entries_count += len(pod.get("executed_or_queued") or [])
        holdings_src = pod.get("active_holdings_plan") or b_st.get("positions") or []
        for pos in holdings_src:
            p_item = dict(pos)
            p_item["_pod_name"] = pod_name
            p_item["_pod_id"] = pod_id
            p_item["_account_number"] = acct_num
            all_open_holdings.append(p_item)
        for bo in b_st.get("open_orders") or []:
            o_item = dict(bo)
            o_item["_pod_name"] = pod_name
            o_item["_account_number"] = acct_num
            o_item["_bucket"] = "OPEN"
            all_broker_orders.append(o_item)
        for bo in (b_st.get("recent_orders") or [])[:8]:
            o_item = dict(bo)
            o_item["_pod_name"] = pod_name
            o_item["_account_number"] = acct_num
            o_item["_bucket"] = "RECENT"
            all_broker_orders.append(o_item)

    # ---------------- TOP BRIEFING BANNER + 3 POD ACCOUNT CARDS ----------------
    market_regime = str(pods_payload.get("market_regime") or "SIDEWAYS_CHOPPY")
    session_dt = str(pods_payload.get("session_date") or today_iso)
    long_hold_cnt = sum(1 for p in all_open_holdings if str(p.get("side", "LONG")).upper() == "LONG")
    short_hold_cnt = sum(1 for p in all_open_holdings if str(p.get("side", "LONG")).upper() == "SHORT")
    latest_news_headline = (
        f"{live_catalysts[0]['ticker']}: {live_catalysts[0]['headline']}"
        if live_catalysts
        else "24/7 Alpaca News & Screener active — updates automatically on scheduled Daily & Weekly runs."
    )

    st.markdown(
        f"<div style='background:linear-gradient(90deg,rgba(15,23,42,0.88),rgba(30,41,59,0.78));"
        f"border:1px solid rgba(56,189,248,0.28);border-radius:10px;padding:13px 18px;margin-bottom:14px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;'>"
        f"<div><span style='font-size:1.08rem;font-weight:700;color:#f8fafc;'>3-Pod Autonomous Paper Trading Hub</span> "
        f"<span style='background:rgba(56,189,248,0.16);color:#38bdf8;padding:2px 9px;border-radius:999px;font-size:0.74rem;font-weight:600;margin-left:6px;'>"
        f"Regime: {html.escape(market_regime)}</span> "
        f"<span style='color:#94a3b8;font-size:0.79rem;margin-left:8px;'>Latest Session: <code>{html.escape(session_dt)}</code></span></div>"
        f"<div style='font-size:0.81rem;color:#cbd5e1;'>"
        f"Latest Session Orders: <strong style='color:#38bdf8;'>{today_entries_count}</strong> &nbsp;|&nbsp; "
        f"Open Pod Holdings: <strong>{long_hold_cnt} Long / {short_hold_cnt} Short</strong> &nbsp;|&nbsp; "
        f"<a href='{ALPACA_PAPER_PORTAL_URL}' target='_blank' style='color:#38bdf8;text-decoration:none;font-weight:600;'>Alpaca Paper Portal ↗</a>"
        f"</div></div>"
        f"<div style='margin-top:6px;font-size:0.78rem;color:#94a3b8;'>"
        f"📰 <strong>Latest Catalyst Wire:</strong> {html.escape(latest_news_headline[:155])}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if pods_list:
        pod_cols = st.columns(len(pods_list))
        for idx, pod in enumerate(pods_list):
            b_state = pod.get("broker_state") or pod.get("broker") or {}
            eq = float(b_state.get("total_equity") or b_state.get("equity") or 100_000.0)
            cash = float(b_state.get("unencumbered_cash") or b_state.get("cash_balance") or b_state.get("cash") or 100_000.0)
            pnl_d = eq - 100_000.0
            pnl_pct = (pnl_d / 100_000.0) * 100.0
            acct_no = str(b_state.get("alpaca_account_number") or b_state.get("account_number") or "Disconnected")
            connected = bool(b_state.get("broker_connected") or b_state.get("connected"))
            p_positions = pod.get("active_holdings_plan") or b_state.get("positions") or []
            n_long = sum(1 for p in p_positions if str(p.get("side", "LONG")).upper() == "LONG")
            n_short = sum(1 for p in p_positions if str(p.get("side", "LONG")).upper() == "SHORT")
            pnl_col = "#10b981" if pnl_d >= 0 else "#f87171"
            conn_col = "#10b981" if connected else "#f59e0b"
            pod_title = str(pod.get("label") or pod.get("short_label") or pod.get("pod_name") or "")
            pod_mandate = str(pod.get("archetype_summary") or pod.get("why_nominated") or pod.get("mandate") or "")
            with pod_cols[idx]:
                st.markdown(
                    f"<div style='background:rgba(15,23,42,0.58);border:1px solid rgba(148,163,184,0.18);"
                    f"border-top:3px solid {conn_col};border-radius:9px;padding:12px 14px;margin-bottom:8px;'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                    f"<strong style='font-size:0.86rem;color:#f1f5f9;'>{html.escape(pod_title)}</strong>"
                    f"<a href='{ALPACA_PAPER_PORTAL_URL}' target='_blank' style='font-size:0.73rem;color:#38bdf8;text-decoration:none;'>"
                    f"<code>{html.escape(acct_no)}</code> ↗</a></div>"
                    f"<div style='font-size:0.73rem;color:#94a3b8;margin-top:2px;'>{html.escape(pod_mandate[:84])}</div>"
                    f"<div style='display:flex;justify-content:space-between;align-items:baseline;margin-top:8px;'>"
                    f"<span style='font-size:1.22rem;font-weight:700;color:#f8fafc;'>${eq:,.2f}</span>"
                    f"<span style='font-size:0.82rem;font-weight:600;color:{pnl_col};'>{pnl_d:+,.2f} ({pnl_pct:+.2f}%)</span>"
                    f"</div>"
                    f"<div style='font-size:0.74rem;color:#94a3b8;margin-top:4px;'>"
                    f"Buying Cash: <code>${cash:,.0f}</code> · Holdings: <strong>{n_long}L / {n_short}S</strong></div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ---------------- 4 AUTONOMOUS PAPER-POD TABS ----------------
    decision_logs = app.orchestrator.pod_manager.get_recent_decision_logs(limit=90)
    unique_journal_dates = sorted({str(d.get("session_date", "")) for d in decision_logs if d.get("session_date")}, reverse=True)

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            f"📓 Day-by-Day Pod Decision Journal ({len(unique_journal_dates)} Days)",
            f"🛡️ Active Holdings & Exit Plans ({len(all_open_holdings)})",
            "🏆 Strategy Tournament & Mistake Analyzer",
            f"📰 Live News & Universe ({len(universe_meta)})",
        ]
    )

    # =========================================================================
    # TAB 1: DAY-BY-DAY POD DECISION JOURNAL (NUMBERS-FIRST CHRONOLOGICAL DIARY)
    # =========================================================================
    with tab1:
        jc_filter1, jc_filter2, jc_filter3 = st.columns([1.8, 1.5, 1.7])
        with jc_filter1:
            pod_filter = st.selectbox(
                "Filter by Strategy Pod",
                options=[
                    "All 3 Strategy Pods",
                    "pod_1_breakout",
                    "pod_2_mean_reversion",
                    "pod_3_momentum",
                ],
                format_func=lambda x: POD_DISPLAY_NAMES.get(x, x),
                key="journal_pod_filter",
            )
        with jc_filter2:
            activity_filter = st.radio(
                "Journal View",
                options=["All Trading Days", "Days With New Orders Only"],
                horizontal=True,
                key="journal_activity_filter",
            )
        with jc_filter3:
            ticker_search = st.text_input(
                "Search Ticker in Journal (e.g. AAPL, HD, LLY)",
                placeholder="Filter by ticker...",
                key="journal_ticker_search",
            ).strip().upper()

        logs_by_date: Dict[str, List[Dict[str, Any]]] = {}
        for dlog in decision_logs:
            dt_k = str(dlog.get("session_date") or "")
            if not dt_k:
                continue
            if pod_filter != "All 3 Strategy Pods" and dlog.get("pod_id") != pod_filter:
                continue
            logs_by_date.setdefault(dt_k, []).append(dlog)

        ordered_dates = sorted(logs_by_date.keys(), reverse=True)

        if not ordered_dates:
            st.info("No Pod decision journal entries recorded yet — entries populate automatically on each scheduled Daily run.")
        else:
            rendered_days = 0
            for day_idx, dt_key in enumerate(ordered_dates):
                day_pods = sorted(logs_by_date[dt_key], key=lambda x: str(x.get("pod_id", "")))
                day_entries_total = sum(len(p.get("executed_or_queued") or []) for p in day_pods)
                day_holds_total = sum(len(p.get("active_holdings_plan") or []) for p in day_pods)
                day_ratchets_total = sum(len(p.get("ratchets_and_exits") or []) for p in day_pods)
                day_vetoes_total = sum(
                    1
                    for p in day_pods
                    for s in (p.get("skipped_reasons") or [])
                    if str(s.get("category", "")) != "NO_TECHNICAL_SIGNAL"
                )

                if activity_filter == "Days With New Orders Only" and day_entries_total == 0 and day_ratchets_total == 0:
                    continue

                if ticker_search:
                    day_blob = json.dumps(day_pods).upper()
                    if ticker_search not in day_blob:
                        continue

                rendered_days += 1
                human_dt = _format_human_date(dt_key)
                latest_tag = (
                    "<span style='background:rgba(16,185,129,0.20);color:#34d399;padding:2px 8px;border-radius:999px;"
                    "font-size:0.72rem;font-weight:700;margin-left:8px;'>LATEST SESSION</span>"
                    if day_idx == 0
                    else ""
                )

                st.markdown(
                    f"<div style='background:linear-gradient(90deg,rgba(30,41,59,0.92),rgba(15,23,42,0.82));"
                    f"border-left:4px solid #38bdf8;border-top:1px solid rgba(148,163,184,0.18);"
                    f"border-right:1px solid rgba(148,163,184,0.18);border-bottom:1px solid rgba(148,163,184,0.18);"
                    f"border-radius:8px;padding:10px 16px;margin-top:14px;margin-bottom:10px;"
                    f"display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;'>"
                    f"<div><span style='font-size:1.02rem;font-weight:700;color:#f8fafc;'>📅 {html.escape(human_dt)}</span> "
                    f"<code style='font-size:0.78rem;color:#94a3b8;margin-left:6px;'>{html.escape(dt_key)}</code>{latest_tag}</div>"
                    f"<div style='font-size:0.79rem;color:#cbd5e1;'>"
                    f"<span style='color:#34d399;font-weight:600;'>{day_entries_total} Orders Placed/Filled</span> &nbsp;·&nbsp; "
                    f"<span style='color:#38bdf8;font-weight:600;'>{day_holds_total} Positions Held</span> &nbsp;·&nbsp; "
                    f"<span style='color:#fbbf24;font-weight:600;'>{day_ratchets_total} Ratchets/Exits</span> &nbsp;·&nbsp; "
                    f"<span style='color:#f87171;font-weight:600;'>{day_vetoes_total} News/Risk Vetoes</span>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

                for p_log in day_pods:
                    pid = str(p_log.get("pod_id") or "")
                    p_disp = POD_DISPLAY_NAMES.get(pid, pid)
                    acct_str = str(p_log.get("alpaca_account_number") or "Paper")
                    strat_nm = str(p_log.get("strategy_name") or p_log.get("strategy_id") or "")
                    entries_list = p_log.get("executed_or_queued") or []
                    ratchets_list = p_log.get("ratchets_and_exits") or []
                    holds_list = p_log.get("active_holdings_plan") or []
                    skips_list = p_log.get("skipped_reasons") or []

                    notable_vetoes = [
                        s for s in skips_list if str(s.get("category", "")) != "NO_TECHNICAL_SIGNAL"
                    ]
                    quiet_skips = [
                        s for s in skips_list if str(s.get("category", "")) == "NO_TECHNICAL_SIGNAL"
                    ]

                    if entries_list:
                        status_pill = (
                            f"<span style='background:rgba(16,185,129,0.20);color:#34d399;padding:3px 10px;"
                            f"border-radius:999px;font-size:0.75rem;font-weight:700;'>"
                            f"🟢 {len(entries_list)} TRADE(S) PLACED / FILLED</span>"
                        )
                    elif holds_list:
                        status_pill = (
                            f"<span style='background:rgba(56,189,248,0.18);color:#38bdf8;padding:3px 10px;"
                            f"border-radius:999px;font-size:0.75rem;font-weight:700;'>"
                            f"🛡️ HOLDING {len(holds_list)} POSITION(S) · 0 NEW ENTRIES</span>"
                        )
                    else:
                        status_pill = (
                            "<span style='background:rgba(148,163,184,0.16);color:#cbd5e1;padding:3px 10px;"
                            "border-radius:999px;font-size:0.75rem;font-weight:600;'>"
                            "⏸️ STOOD ASIDE (100% CASH)</span>"
                        )

                    with st.container(border=True):
                        st.markdown(
                            f"<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:6px;'>"
                            f"<div><strong style='font-size:0.95rem;color:#f8fafc;'>{html.escape(p_disp)}</strong> "
                            f"<span style='color:#94a3b8;font-size:0.8rem;'>(<code>{html.escape(acct_str)}</code> · {html.escape(strat_nm)})</span></div>"
                            f"<div>{status_pill}</div></div>",
                            unsafe_allow_html=True,
                        )

                        # 1. New Orders Executed / Queued on this day — Clear Entry & 4-Step Exit Numbers + Concise Explanation
                        if entries_list:
                            st.markdown("**1 · New Orders Placed / Filled — Entry & Exit Strategy Numbers:**")
                            for e in entries_list:
                                e_side = str(e.get("side") or "LONG").upper()
                                e_tkr = str(e.get("ticker") or "")
                                e_sec = str(e.get("sector") or "")
                                e_shs = int(e.get("shares") or 0)
                                e_ref = float(e.get("reference_close_price") or e.get("live_price") or 0.0)
                                e_live = float(e.get("live_price") or e_ref)
                                e_lim = float(e.get("max_chase_price") or e_live or e_ref)
                                e_zone = str(e.get("buy_zone_str") or f"<= ${e_lim:.2f}")
                                e_stat = str(e.get("order_status") or "QUEUED")
                                e_cost = float(e.get("estimated_cost_usd") or (e_shs * e_lim))
                                e_wt = float(e.get("portfolio_weight_pct") or (e_cost / 1000.0))
                                e_risk = float(e.get("risk_usd") or 0.0)
                                e_risk_pct = float(e.get("risk_pct") or 1.0)
                                e_max_d = int(e.get("max_hold_days") or 15)
                                e_trig = str(e.get("technical_trigger") or e.get("signal_reason") or "")
                                e_cat_sent = float(e.get("ai_catalyst_sentiment") or 0.0)
                                e_cat_note = str(e.get("ai_catalyst_note") or "")
                                e_guide = str(e.get("pre_open_guidance") or "")

                                ladder = _compute_exit_ladder_numbers(
                                    side=e_side,
                                    entry_px=e_ref if e_ref > 0 else e_lim,
                                    init_stop_px=float(e.get("stop_loss_price") or 0.0),
                                    cur_stop_px=float(e.get("stop_loss_price") or 0.0),
                                    stage1_trigger_px=float(e.get("stage1_ratchet_price") or 0.0),
                                    stage1_stop_px=float(e.get("stage1_stop_price") or 0.0),
                                    stage2_trigger_px=float(e.get("stage2_ratchet_price") or 0.0),
                                    stage2_stop_px=float(e.get("stage2_stop_price") or 0.0),
                                    target_px=float(e.get("take_profit_price") or 0.0),
                                )
                                rr_val = float(e.get("reward_risk_ratio") or ladder["rr"])
                                dir_tag = "🟢 LONG" if e_side == "LONG" else "🔴 SHORT"
                                stat_col = "#34d399" if "FILLED" in e_stat.upper() else "#38bdf8"
                                cap_lbl = "Short Limit Floor" if e_side == "SHORT" else "Buy Limit Cap"

                                exit_grid_html = _render_four_step_exit_grid_html(
                                    stop_px=ladder["cur_stop"],
                                    stop_sub=f"1R Risk = ${e_risk:,.0f} ({e_risk_pct:.2f}% pod)",
                                    s1_trig=ladder["s1_trig"],
                                    s1_lock=ladder["s1_lock"],
                                    s2_trig=ladder["s2_trig"],
                                    s2_lock=ladder["s2_lock"],
                                    tp_px=ladder["tp"],
                                    tp_sub=f"{rr_val:.1f}R Target · Max {e_max_d}d Hold",
                                )

                                news_clause = (
                                    f" · <strong>News ({e_cat_sent:+.2f}):</strong> {html.escape(e_cat_note[:125])}"
                                    if e_cat_note
                                    else f" · <strong>News ({e_cat_sent:+.2f}):</strong> Clear (no adverse catalyst)"
                                )
                                exec_clause = (
                                    f"<div style='color:#94a3b8;font-size:0.77rem;margin-top:2px;'>"
                                    f"<strong>Execution Plan:</strong> {html.escape(e_guide)}</div>"
                                    if e_guide
                                    else ""
                                )

                                st.markdown(
                                    f"<div style='padding:10px 13px;margin:7px 0;background:rgba(15,23,42,0.58);"
                                    f"border:1px solid rgba(148,163,184,0.16);border-left:3px solid {stat_col};"
                                    f"border-radius:7px;font-size:0.82rem;'>"
                                    f"<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;'>"
                                    f"<div><strong style='font-size:0.9rem;color:#f8fafc;'>{dir_tag} {html.escape(e_tkr)}</strong> "
                                    f"<span style='color:#94a3b8;'>({html.escape(e_sec)})</span> · "
                                    f"<code>{e_shs} shs</code> · Value <code>${e_cost:,.0f}</code> (<code>{e_wt:.1f}%</code> pod)</div>"
                                    f"<span style='color:{stat_col};font-weight:700;'>{html.escape(e_stat)}</span></div>"
                                    f"<div style='margin-top:5px;color:#e2e8f0;'>"
                                    f"<strong>Entry Numbers:</strong> Signal Close <code>${e_ref:.2f}</code> · "
                                    f"Entry Zone <code>{html.escape(e_zone)}</code> · "
                                    f"{cap_lbl} <code>${e_lim:.2f}</code> · Quote <code>${e_live:.2f}</code></div>"
                                    f"{exit_grid_html}"
                                    f"<div style='color:#cbd5e1;font-size:0.79rem;margin-top:3px;'>"
                                    f"<strong>Why Entered:</strong> {html.escape(e_trig)}{news_clause}</div>"
                                    f"{exec_clause}"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.caption(f"**Why 0 New Entries:** {p_log.get('summary_headline', 'No new setups passed all entry & risk gates.')}")

                        # 2. Stop Ratchets & Exits on this day
                        if ratchets_list:
                            st.markdown("**2 · Stop-Loss Ratchets & Exits Triggered:**")
                            for r_act in ratchets_list:
                                st.markdown(
                                    f"- **{r_act.get('action', 'RATCHET')} · `{r_act.get('ticker', '')}`**: "
                                    f"Stop `${float(r_act.get('old_stop_price') or 0):.2f}` → **`${float(r_act.get('new_stop_price') or 0):.2f}`** "
                                    f"({r_act.get('reason', '')})"
                                )

                        # 3. Open Positions Held on this day — Scannable Entry/Current/Stop/Target/Day Numbers
                        if holds_list:
                            hold_rows_html: List[str] = []
                            for h in holds_list:
                                h_tkr = str(h.get("ticker", ""))
                                h_side = str(h.get("side", "LONG")).upper()
                                h_qty = int(h.get("quantity") or h.get("qty") or 0)
                                h_avg = float(h.get("avg_entry_price") or 0.0)
                                h_cur = float(h.get("current_price") or h_avg)
                                h_ret = float(h.get("unrealised_return_pct") or 0.0)
                                h_r = float(h.get("r_multiple") or 0.0)
                                h_stop = float(h.get("current_stop_price") or 0.0)
                                h_tp = float(h.get("take_profit_price") or 0.0)
                                h_s1 = float(h.get("stage1_ratchet_price") or 0.0)
                                h_day = int(h.get("holding_days") or 0)
                                h_max_d = int(h.get("max_hold_days") or 15)
                                h_stage = str(h.get("stop_stage_label") or "Initial -1R Stop")
                                h_col = "#34d399" if h_ret >= 0 else "#f87171"
                                hold_rows_html.append(
                                    f"<div style='background:rgba(30,41,59,0.72);border:1px solid rgba(148,163,184,0.18);"
                                    f"border-radius:6px;padding:6px 10px;margin:4px 0;font-size:0.79rem;"
                                    f"display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;'>"
                                    f"<div><strong>{html.escape(h_tkr)}</strong> ({h_side} <code>{h_qty} shs</code>) · "
                                    f"Entry <code>${h_avg:.2f}</code> → Now <code>${h_cur:.2f}</code> "
                                    f"(<span style='color:{h_col};font-weight:700;'>{h_ret:+.2f}% / {h_r:+.2f}R</span>)</div>"
                                    f"<div style='color:#cbd5e1;'>"
                                    f"Active Stop <code>${h_stop:.2f}</code> <span style='color:#94a3b8;'>[{html.escape(h_stage)}]</span> · "
                                    f"1.0R BE <code>${h_s1:.2f}</code> · Target <code>${h_tp:.2f}</code> · "
                                    f"<code>Day {h_day}/{h_max_d}</code></div>"
                                    f"</div>"
                                )
                            st.markdown(
                                f"<div style='margin-top:8px;'><div style='font-size:0.8rem;color:#94a3b8;font-weight:600;margin-bottom:3px;'>"
                                f"Active Holdings Guarded ({len(holds_list)}):</div>{''.join(hold_rows_html)}</div>",
                                unsafe_allow_html=True,
                            )

                        if notable_vetoes:
                            with st.expander(
                                f"🚫 {len(notable_vetoes)} Triggered Signal(s) Blocked by News / Risk Guardrails on {dt_key}",
                                expanded=(day_idx == 0 and len(notable_vetoes) <= 6),
                            ):
                                for nv in notable_vetoes:
                                    nv_badge = str(nv.get("status_badge") or nv.get("category") or "Vetoed")
                                    is_news = "NEWS" in nv_badge.upper() or "AI" in str(nv.get("category", "")).upper()
                                    b_col = "#f87171" if is_news else "#fbbf24"
                                    st.markdown(
                                        f"<div style='padding:5px 10px;margin-bottom:4px;background:rgba(15,23,42,0.45);"
                                        f"border-left:3px solid {b_col};border-radius:4px;font-size:0.8rem;'>"
                                        f"<strong>{html.escape(str(nv.get('ticker', '')))}</strong> "
                                        f"(<span style='color:{b_col};font-weight:600;'>{html.escape(nv_badge)}</span>) — "
                                        f"{html.escape(str(nv.get('reason', '')))}</div>",
                                        unsafe_allow_html=True,
                                    )

                        if quiet_skips:
                            with st.expander(f"🔎 View {len(quiet_skips)} Stocks That Did Not Trigger Technical Entry Rules ({dt_key})"):
                                st.dataframe(
                                    [
                                        {
                                            "Ticker": qs.get("ticker", ""),
                                            "Sector": qs.get("sector", ""),
                                            "Price": f"${float(qs.get('live_price') or 0):.2f}",
                                            "Why Entry Rules Did Not Fire": qs.get("technical_summary") or qs.get("reason", ""),
                                        }
                                        for qs in quiet_skips
                                    ],
                                    use_container_width=True,
                                    hide_index=True,
                                )

            if rendered_days == 0:
                st.info("No journal days matched your current Pod / Ticker filter.")

    # =========================================================================
    # TAB 2: ACTIVE HOLDINGS & EXIT PLANS (NUMBERS + CONCISE EXPLANATIONS)
    # =========================================================================
    with tab2:
        if all_open_holdings:
            st.markdown("#### 🛡️ Live Alpaca Paper Positions — Entry & 4-Step Exit Strategy Numbers")
            for pos in all_open_holdings:
                tkr = str(pos.get("ticker", ""))
                side = str(pos.get("side", "LONG")).upper()
                sec = str(pos.get("sector") or "")
                qty = int(pos.get("quantity") or pos.get("qty") or 0)
                avg_px = float(pos.get("avg_entry_price") or pos.get("entry_price") or 0.0)
                cur_px = float(pos.get("current_price") or pos.get("live_price") or avg_px)
                mkt_val = abs(qty * cur_px)
                entry_dt = str(pos.get("entry_date") or session_dt)
                hold_d = int(pos.get("holding_days") or 0)
                max_d = int(pos.get("max_hold_days") or 15)
                u_pnl = float(
                    pos.get("unrealised_pnl")
                    if pos.get("unrealised_pnl") is not None
                    else (pos.get("unrealised_pnl_usd") if pos.get("unrealised_pnl_usd") is not None else (pos.get("unrealized_pl") or 0.0))
                )
                u_pct = float(
                    pos.get("unrealised_return_pct")
                    if pos.get("unrealised_return_pct") is not None
                    else (pos.get("unrealised_pnl_pct") if pos.get("unrealised_pnl_pct") is not None else (pos.get("unrealized_plpc") or 0.0))
                )

                ladder = _compute_exit_ladder_numbers(
                    side=side,
                    entry_px=avg_px,
                    init_stop_px=float(pos.get("initial_stop_price") or pos.get("current_stop_price") or 0.0),
                    cur_stop_px=float(pos.get("current_stop_price") or pos.get("stop_loss_price") or 0.0),
                    stage1_trigger_px=float(pos.get("stage1_ratchet_price") or 0.0),
                    stage1_stop_px=float(pos.get("stage1_stop_price") or 0.0),
                    stage2_trigger_px=float(pos.get("stage2_ratchet_price") or 0.0),
                    stage2_stop_px=float(pos.get("stage2_stop_price") or 0.0),
                    target_px=float(pos.get("take_profit_price") or 0.0),
                )
                stop_px = ladder["cur_stop"]
                tp_px = ladder["tp"]
                one_r = ladder["one_r"]

                r_mult = float(
                    pos.get("r_multiple")
                    if pos.get("r_multiple") is not None
                    else (((cur_px - avg_px) / one_r) if side == "LONG" else ((avg_px - cur_px) / one_r))
                )
                prog_val = max(0.0, min(1.0, (r_mult + 1.0) / 3.5))

                has_oco = bool(pos.get("oco_bracket_active") or pos.get("has_live_oco_bracket"))
                stop_stage_lbl = str(pos.get("stop_stage_label") or "Initial -1.0R Hard Stop")
                entry_thesis = str(pos.get("entry_thesis") or f"{pos.get('strategy_name', 'Pod Strategy')} technical & relative-strength entry.")

                if cur_px > 0:
                    dist_stop_pct = ((stop_px - cur_px) / cur_px) * 100.0
                    dist_tp_pct = ((tp_px - cur_px) / cur_px) * 100.0
                else:
                    dist_stop_pct, dist_tp_pct = 0.0, 0.0

                dir_pill = "🟢 LONG" if side == "LONG" else "🔴 SHORT"
                oco_pill = "✅ Live GTC OCO Active" if has_oco else "⚠️ Self-Healing OCO On Next Sync"
                pnl_txt = f"${u_pnl:+,.2f} ({u_pct:+.2f}%)"

                with st.container(border=True):
                    hc1, hc2, hc3, hc4 = st.columns([1.55, 1.05, 1.15, 1.25])
                    hc1.markdown(
                        f"**{dir_pill} · {tkr}** (`{qty} shs` · `${mkt_val:,.0f}`)\n\n"
                        f"{pos.get('_pod_name', '')} (`{pos.get('_account_number', '')}`) · Entered `{entry_dt}`"
                    )
                    hc2.metric("Entry → Current", f"${cur_px:.2f}", f"Avg Entry ${avg_px:.2f}")
                    hc3.metric("Unrealized P&L", pnl_txt, f"{r_mult:+.2f}R")
                    hc4.markdown(
                        f"**Protection:** {oco_pill}\n\n"
                        f"**Stage:** `{stop_stage_lbl}` · **Hold:** `Day {hold_d}/{max_d}`"
                    )

                    st.markdown(
                        _render_four_step_exit_grid_html(
                            stop_px=stop_px,
                            stop_sub=f"{dist_stop_pct:+.2f}% from current (Init ${ladder['init_stop']:.2f})",
                            s1_trig=ladder["s1_trig"],
                            s1_lock=ladder["s1_lock"],
                            s2_trig=ladder["s2_trig"],
                            s2_lock=ladder["s2_lock"],
                            tp_px=tp_px,
                            tp_sub=f"{dist_tp_pct:+.2f}% to target · Exit Day {max_d}",
                        ),
                        unsafe_allow_html=True,
                    )

                    st.progress(
                        prog_val,
                        text=(
                            f"R-Multiple Progress: {r_mult:+.2f}R  |  "
                            f"Stop ${stop_px:.2f}  →  +1.0R BE ${ladder['s1_trig']:.2f}  →  "
                            f"+1.65R Lock ${ladder['s2_trig']:.2f}  →  Target ${tp_px:.2f}"
                        ),
                    )

                    exit_action_word = "Buy-to-Cover" if side == "SHORT" else "Sell"
                    news_exit_thresh = ">= +0.50 bullish squeeze" if side == "SHORT" else "<= -0.50 bearish shock"
                    st.markdown(
                        f"<div style='background:rgba(15,23,42,0.45);border-radius:6px;padding:7px 11px;font-size:0.8rem;color:#cbd5e1;'>"
                        f"<div><strong>Why Entered:</strong> {html.escape(entry_thesis)}"
                        f"{(' (' + html.escape(sec) + ')') if sec else ''}</div>"
                        f"<div style='margin-top:3px;color:#94a3b8;'><strong>Plain-English Exit Plan:</strong> "
                        f"Alpaca holds a live GTC OCO bracket to {exit_action_word} automatically at <code>${tp_px:.2f}</code> (profit target) "
                        f"or <code>${stop_px:.2f}</code> (active stop). Stop ratchets automatically to <code>${ladder['s1_lock']:.2f}</code> "
                        f"at <code>${ladder['s1_trig']:.2f}</code> (+1.0R) and locks +1.0R profit (<code>${ladder['s2_lock']:.2f}</code>) at "
                        f"<code>${ladder['s2_trig']:.2f}</code> (+1.65R). Exits early on adverse news ({news_exit_thresh}) or Day <code>{max_d}</code> time-stop.</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.info("No open positions across the 3 Alpaca Paper accounts right now (`100% Cash`).")

        st.markdown("---")
        oc1, oc2 = st.columns([1.15, 1.25])
        with oc1:
            st.markdown("##### 📋 Live & Recent Alpaca Broker Orders")
            if all_broker_orders:
                st.dataframe(
                    [
                        {
                            "Bucket": o.get("_bucket", ""),
                            "Account": o.get("_account_number", ""),
                            "Ticker": o.get("ticker") or o.get("symbol", ""),
                            "Side": str(o.get("side", "")).upper(),
                            "Type": o.get("type", ""),
                            "Qty": o.get("qty", ""),
                            "Status": o.get("status", ""),
                            "Limit / Stop": o.get("limit_price") or o.get("stop_price") or "MKT",
                        }
                        for o in all_broker_orders[:35]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No open or recent broker orders recorded yet.")

        with oc2:
            st.markdown("##### 📐 3-Pod Entry & Exit Strategy Rules Cheat-Sheet")
            st.markdown(_render_pod_rules_cheatsheet_html(pods_list), unsafe_allow_html=True)

    # =========================================================================
    # TAB 3: STRATEGY TOURNAMENT & MISTAKE ANALYZER
    # =========================================================================
    with tab3:
        st.markdown("#### 🏆 9-Gate Strategy Leaderboard (6 Long & Short Strategy Families)")
        strat_rows = []
        for s in strategies:
            m = s.get("backtest_summary") or {}
            val = s.get("validation_summary") or {}
            oos = val.get("oos_metrics") or {}
            checks = val.get("criteria_checks") or {}
            passed = sum(1 for v in checks.values() if v)
            total_g = len(checks) if checks else 9
            strat_rows.append(
                {
                    "Strategy": f"{s['strategy_id']} v{s['version']}",
                    "Name": s.get("name", ""),
                    "Family": s.get("strategy_family", ""),
                    "Status": s.get("status", ""),
                    "Gates": f"{passed}/{total_g}" if m else "Ready to Test",
                    "Full Return": f"{float(m.get('total_return_pct', 0.0)):+.1f}%" if m else "—",
                    "OOS Return": f"{float(oos.get('total_return_pct', 0.0)):+.1f}%" if oos else "—",
                    "Sharpe": f"{float(m.get('sharpe_ratio', 0.0)):.2f}" if m else "—",
                    "Profit Factor": f"{float(m.get('profit_factor', 0.0)):.2f}" if m else "—",
                    "Max DD": f"-{float(m.get('max_drawdown_pct', 0.0)):.2f}%" if m else "—",
                    "Trades": int(m.get("trade_count", 0)) if m else 0,
                }
            )
        if strat_rows:
            st.dataframe(strat_rows, use_container_width=True, hide_index=True)

        if experiments:
            with st.expander("📈 Inspect Strategy Backtest Equity Curve & Machine-Readable Rules", expanded=False):
                exp_opts = {
                    f"{e['strategy_id']} v{e['version']} ({e['experiment_type']} · {e['created_at'][:10]})": e
                    for e in experiments[:20]
                }
                sel_exp_lbl = st.selectbox("Select Backtest Experiment", options=list(exp_opts.keys()))
                sel_exp = exp_opts[sel_exp_lbl]
                eq_svg = _render_equity_curve_svg(sel_exp.get("equity_curve") or [])
                if eq_svg:
                    st.markdown(eq_svg, unsafe_allow_html=True)
                st.json(sel_exp.get("parameters") or {})

        st.markdown("---")
        st.markdown("#### 🧠 Post-Trade Attribution & Autonomous Mistake Analyzer")
        tot_closed = int(mistake_analyzer.get("total_closed_trades") or 0)
        ma1, ma2, ma3, ma4 = st.columns(4)
        ma1.metric("Closed Round-Trips Analyzed", f"{tot_closed}", mistake_analyzer.get("data_source", "OOS_AUDIT"))
        ma2.metric("Overall Win Rate", f"{float(mistake_analyzer.get('overall_win_rate_pct') or 0.0):.1f}%")
        ma3.metric("Realized Profit Factor", f"{float(mistake_analyzer.get('overall_profit_factor') or 0.0):.2f}x")
        ma4.metric("Total Realized Net P&L", f"${float(mistake_analyzer.get('total_net_pnl') or 0.0):+,.2f}")

        weaknesses = mistake_analyzer.get("detected_weaknesses") or []
        if weaknesses:
            st.markdown("##### 🔧 Mistake Analyzer Findings & Auto-Tuner Remedies")
            for w in weaknesses:
                st.info(
                    f"**[{w.get('dimension') or w.get('category', 'DIAGNOSIS')}]** {w.get('finding', '')}\n\n"
                    f"👉 **Auto-Tuner Remedy:** {w.get('remedy', '')}"
                )

        b_col1, b_col2 = st.columns(2)
        with b_col1:
            st.markdown("###### Breakdown: Long vs. Short & Market Regime")
            side_bd = mistake_analyzer.get("by_side") or []
            reg_bd = mistake_analyzer.get("by_regime") or []
            if side_bd or reg_bd:
                st.dataframe(side_bd + reg_bd, use_container_width=True, hide_index=True)
            else:
                st.caption("Awaiting closed round-trip trades.")
        with b_col2:
            st.markdown("###### Breakdown: Exit Reason & Sector")
            exit_bd = mistake_analyzer.get("by_exit_reason") or []
            sec_bd = mistake_analyzer.get("by_sector") or []
            if exit_bd or sec_bd:
                st.dataframe(exit_bd + sec_bd, use_container_width=True, hide_index=True)
            else:
                st.caption("Awaiting closed round-trip trades.")

    # =========================================================================
    # TAB 4: LIVE NEWS, UNIVERSE & SYSTEM HEALTH
    # =========================================================================
    with tab4:
        nc1, nc2 = st.columns([1.35, 1.15])
        with nc1:
            st.markdown("#### 📰 24/7 Live Alpaca News & AI Catalyst Stream")
            if live_catalysts:
                for cat in live_catalysts[:20]:
                    c_score = float(cat.get("sentiment_score") or 0.0)
                    c_badge = _sentiment_badge_html(c_score, str(cat.get("catalyst_type", "")))
                    url_str = str(cat.get("url") or "").strip()
                    link_html = (
                        f" · <a href='{html.escape(url_str)}' target='_blank' style='color:#38bdf8;'>Source ↗</a>"
                        if url_str.startswith("http")
                        else ""
                    )
                    st.markdown(
                        f"<div style='padding:8px 12px;margin-bottom:7px;background:rgba(15,23,42,0.52);"
                        f"border:1px solid rgba(148,163,184,0.14);border-radius:7px;font-size:0.82rem;'>"
                        f"<strong>{html.escape(str(cat.get('ticker', '')))}</strong> &nbsp; {c_badge} "
                        f"<span style='color:#64748b;font-size:0.74rem;margin-left:6px;'>{html.escape(str(cat.get('published_date', '')))}</span>"
                        f"{link_html}<br/>"
                        f"<span style='color:#e2e8f0;'>{html.escape(str(cat.get('headline', '')))}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No catalysts stored yet — headlines populate automatically on scheduled Daily runs.")

        with nc2:
            st.markdown(f"#### 🌐 Liquid Equity Universe ({len(universe_meta)} Active)")
            with st.form("dynamic_ticker_onboard_form", clear_on_submit=True):
                new_tkrs_raw = st.text_input(
                    "Onboard New Catalyst Ticker(s) (Gates: Price ≥ $15, 20d ADV ≥ $50M/day, NYSE/NASDAQ)",
                    placeholder="e.g. CRWD, NOW, ANET",
                )
                sub_onboard = st.form_submit_button("Validate & Onboard to Universe")
                if sub_onboard and new_tkrs_raw.strip():
                    req_list = [t.strip().upper() for t in new_tkrs_raw.replace(";", ",").split(",") if t.strip()]
                    onb_res = app.orchestrator.market_data.onboard_dynamic_tickers(req_list, source="UI_OPERATOR")
                    if onb_res.get("onboarded"):
                        st.success(f"Onboarded: {', '.join(onb_res['onboarded'])}")
                        st.rerun()
                    else:
                        st.warning(f"No tickers passed liquidity/exchange gates: {onb_res.get('rejected')}")

            if universe_meta:
                st.dataframe(
                    [
                        {
                            "Ticker": m.get("ticker", ""),
                            "Sector": m.get("sector", ""),
                            "Source": m.get("discovery_source", "CORE"),
                            "Shortable": "✅" if m.get("is_shortable", True) else "🚫",
                            "ETB": "✅" if m.get("easy_to_borrow", True) else "—",
                        }
                        for m in sorted(universe_meta, key=lambda x: (str(x.get("discovery_source", "CORE")) != "CORE", str(x.get("ticker", ""))))
                    ],
                    use_container_width=True,
                    hide_index=True,
                    height=380,
                )

        st.markdown("---")
        jc1, jc2 = st.columns(2)
        with jc1:
            st.markdown("##### ⚙️ Autonomous Job Execution History")
            if jobs:
                st.dataframe(
                    [
                        {
                            "Job": j.get("job_name", ""),
                            "Status": j.get("status", ""),
                            "Started": str(j.get("started_at", ""))[:19].replace("T", " "),
                        }
                        for j in jobs[:15]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
        with jc2:
            st.markdown("##### 🚨 Portfolio Risk Alerts & Pod Account Reset")
            if risk_alerts:
                for al in risk_alerts[:6]:
                    st.caption(f"• **[{al.get('severity', 'INFO')}]** `{al.get('category', '')}`: {al.get('message', '')}")
            else:
                st.caption("Zero active risk alerts — kill switch disarmed.")

            with st.expander("🧹 Emergency Pod Orders / Positions Liquidation"):
                rst_pod = st.selectbox(
                    "Select Alpaca Paper Pod to Cancel Open Orders & Close Positions",
                    options=[p.get("pod_id") for p in pods_list] if pods_list else ["pod_1_breakout"],
                )
                if st.button("Cancel Orders & Flatten Selected Pod"):
                    res_rst = app.orchestrator.pod_manager.reset_alpaca_paper_account(pod_id=str(rst_pod))
                    st.info(f"Reset result: {res_rst}")
                    st.rerun()


if __name__ == "__main__":
    main()
