"""Streamlit Community Cloud & Local Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

v2.0 All-Weather 4-Tab Decision Hub:
1. Today's Trade Cards & Visual Setups — Ranked Long & Short setups across 3 Alpaca Pods, Custom Capital Sizing Slider, 60-day OHLC Candlestick + SMA20/SMA50 charts, and filtered-signal diagnostics.
2. Active Holdings & Live Exit Guardian — Real-time Long & Short positions across all 3 Alpaca Paper accounts, R-multiple progress bars, GTC OCO bracket verification, and Day-by-Day Decision Journal.
3. Strategy Tournament & Mistake Analyzer — 9-Gate Out-of-Sample / Walk-Forward leaderboard (6 strategy families incl. Bearish Breakdown) + Post-Trade Attribution & Auto-Tuner Mistake Analyzer.
4. Live News, Universe & System Health — 24/7 Alpaca News & AI Catalyst sentiment stream, 40+ Core & Dynamic Universe Explorer with on-demand ticker onboarding, and autonomous job logs.
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


def _render_candlestick_svg(
    bars: List[Dict[str, Any]],
    ticker: str,
    side: str = "LONG",
    entry_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    stage1_price: Optional[float] = None,
    stage2_price: Optional[float] = None,
    target_price: Optional[float] = None,
    height: int = 245,
) -> str:
    """Render a crisp 60-day OHLC Candlestick + SMA20 + SMA50 SVG chart with horizontal Trade Card overlays."""
    if not bars:
        return (
            "<div style='padding:18px;background:rgba(15,23,42,0.45);border-radius:8px;"
            "color:#94a3b8;font-size:0.8rem;text-align:center;'>No 60-day bar history available yet.</div>"
        )

    width = 680
    pad_l, pad_r, pad_t, pad_b = 14, 78, 22, 24
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    all_prices: List[float] = []
    for b in bars:
        h_val = float(b.get("h") if b.get("h") is not None else b["high"])
        l_val = float(b.get("l") if b.get("l") is not None else b["low"])
        all_prices.extend([h_val, l_val])
        s20_v = b.get("sma20") if b.get("sma20") is not None else b.get("sma_20")
        s50_v = b.get("sma50") if b.get("sma50") is not None else b.get("sma_50")
        if s20_v:
            all_prices.append(float(s20_v))
        if s50_v:
            all_prices.append(float(s50_v))
    for lvl in (entry_price, stop_price, stage1_price, stage2_price, target_price):
        if lvl and lvl > 0:
            all_prices.append(float(lvl))

    min_p = min(all_prices) * 0.992
    max_p = max(all_prices) * 1.008
    span_p = max(max_p - min_p, 0.01)

    def _y(px: float) -> float:
        return pad_t + plot_h - ((px - min_p) / span_p) * plot_h

    n = len(bars)
    step_x = plot_w / max(n, 1)
    candle_w = max(2.4, min(7.5, step_x * 0.66))

    # Grid lines
    grid_svg: List[str] = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        gy = pad_t + plot_h * frac
        gp = max_p - span_p * frac
        grid_svg.append(
            f"<line x1='{pad_l}' y1='{gy:.1f}' x2='{width - pad_r}' y2='{gy:.1f}' "
            f"stroke='rgba(148,163,184,0.10)' stroke-width='1'/>"
            f"<text x='{width - pad_r + 6}' y='{gy + 3:.1f}' fill='#64748b' font-size='9.5' "
            f"font-family='monospace'>${gp:.2f}</text>"
        )

    # Candlesticks
    candles_svg: List[str] = []
    sma20_pts: List[str] = []
    sma50_pts: List[str] = []
    for idx, b in enumerate(bars):
        cx = pad_l + idx * step_x + step_x * 0.5
        o_px = float(b.get("o") if b.get("o") is not None else b["open"])
        h_px = float(b.get("h") if b.get("h") is not None else b["high"])
        l_px = float(b.get("l") if b.get("l") is not None else b["low"])
        c_px = float(b.get("c") if b.get("c") is not None else b["close"])
        color = "#10b981" if c_px >= o_px else "#ef4444"
        y_high, y_low = _y(h_px), _y(l_px)
        y_open, y_close = _y(o_px), _y(c_px)
        rect_top = min(y_open, y_close)
        rect_h = max(1.6, abs(y_close - y_open))
        candles_svg.append(
            f"<line x1='{cx:.1f}' y1='{y_high:.1f}' x2='{cx:.1f}' y2='{y_low:.1f}' stroke='{color}' stroke-width='1.15'/>"
            f"<rect x='{cx - candle_w / 2:.1f}' y='{rect_top:.1f}' width='{candle_w:.1f}' height='{rect_h:.1f}' fill='{color}' rx='0.8'/>"
        )
        s20_v = b.get("sma20") if b.get("sma20") is not None else b.get("sma_20")
        s50_v = b.get("sma50") if b.get("sma50") is not None else b.get("sma_50")
        if s20_v:
            sma20_pts.append(f"{cx:.1f},{_y(float(s20_v)):.1f}")
        if s50_v:
            sma50_pts.append(f"{cx:.1f},{_y(float(s50_v)):.1f}")

    sma_svg = ""
    if len(sma20_pts) >= 2:
        sma_svg += f"<polyline fill='none' stroke='#38bdf8' stroke-width='1.5' points='{' '.join(sma20_pts)}'/>"
    if len(sma50_pts) >= 2:
        sma_svg += f"<polyline fill='none' stroke='#f59e0b' stroke-width='1.5' points='{' '.join(sma50_pts)}'/>"

    # Horizontal Trade Levels
    overlays_svg: List[str] = []
    level_specs = [
        (target_price, "#22c55e", "Target", "4,3"),
        (stage2_price, "#a855f7", "1.65R", "3,3"),
        (stage1_price, "#eab308", "1.0R BE", "3,3"),
        (entry_price, "#38bdf8", "Entry", "5,2"),
        (stop_price, "#ef4444", "Stop", "4,2"),
    ]
    for lvl_px, l_col, lbl, dash in level_specs:
        if lvl_px and lvl_px > 0:
            ly = _y(float(lvl_px))
            overlays_svg.append(
                f"<line x1='{pad_l}' y1='{ly:.1f}' x2='{width - pad_r}' y2='{ly:.1f}' "
                f"stroke='{l_col}' stroke-width='1.35' stroke-dasharray='{dash}'/>"
                f"<rect x='{width - pad_r + 2}' y='{ly - 7:.1f}' width='73' height='14' rx='3' fill='rgba(15,23,42,0.88)' stroke='{l_col}' stroke-width='0.7'/>"
                f"<text x='{width - pad_r + 5}' y='{ly + 3:.1f}' fill='{l_col}' font-size='8.8' font-weight='600' font-family='monospace'>{lbl} ${lvl_px:.2f}</text>"
            )

    first_dt = str(bars[0].get("d") or bars[0].get("date") or "")
    last_dt = str(bars[-1].get("d") or bars[-1].get("date") or "")
    side_col = "#10b981" if side == "LONG" else "#f87171"
    header_lbl = f"{html.escape(ticker)} · 60D OHLC ({side}) · Blue=SMA20 · Amber=SMA50"

    return (
        f"<svg viewBox='0 0 {width} {height}' style='width:100%;height:auto;background:rgba(15,23,42,0.62);"
        f"border:1px solid rgba(148,163,184,0.16);border-radius:8px;display:block;'>"
        f"<text x='{pad_l + 4}' y='15' fill='{side_col}' font-size='10.5' font-weight='600' "
        f"font-family='-apple-system,BlinkMacSystemFont,sans-serif'>{header_lbl}</text>"
        f"{''.join(grid_svg)}"
        f"{sma_svg}"
        f"{''.join(candles_svg)}"
        f"{''.join(overlays_svg)}"
        f"<text x='{pad_l + 2}' y='{height - 6}' fill='#64748b' font-size='9' font-family='monospace'>{first_dt}</text>"
        f"<text x='{width - pad_r - 58}' y='{height - 6}' fill='#64748b' font-size='9' font-family='monospace'>{last_dt}</text>"
        f"</svg>"
    )


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


def _compute_custom_capital_sizing(
    custom_capital: float,
    entry_price: float,
    stop_price: float,
    side: str,
    long_risk_pct: float = 0.0125,
    short_risk_pct: float = 0.0100,
) -> Dict[str, Any]:
    """Scale any Pod Trade Card to the user's Custom Capital Slider ($10k - $500k)."""
    if entry_price <= 0:
        return {"shares": 0, "notional": 0.0, "dollar_risk": 0.0, "exposure_pct": 0.0}
    risk_pct = short_risk_pct if side == "SHORT" else long_risk_pct
    max_exp_pct = 0.12 if side == "SHORT" else 0.18
    per_share_risk = max(abs(entry_price - stop_price), entry_price * 0.01)
    risk_budget = custom_capital * risk_pct
    shares_by_risk = int(risk_budget // per_share_risk)
    shares_by_cap = int((custom_capital * max_exp_pct) // entry_price)
    shares = max(0, min(shares_by_risk, shares_by_cap))
    notional = round(shares * entry_price, 2)
    dollar_risk = round(shares * per_share_risk, 2)
    exp_pct = round((notional / custom_capital) * 100.0, 1) if custom_capital > 0 else 0.0
    return {
        "shares": shares,
        "notional": notional,
        "dollar_risk": dollar_risk,
        "exposure_pct": exp_pct,
    }


def _fetch_chart_bars_for_ticker(app: Any, ticker: str) -> List[Dict[str, Any]]:
    """Fetch 60-day OHLC + SMA20/SMA50 series for any ticker on demand."""
    from core.indicators.technical import compute_indicator_series

    t_bars = app.orchestrator.market_data.get_bars(ticker)
    if not t_bars:
        return []
    spy_bars = app.orchestrator.market_data.get_bars("SPY")
    ind_map = compute_indicator_series(t_bars, spy_bars)
    return app.orchestrator.pod_manager._build_60d_chart_bars(t_bars, ind_map)


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
        page_title="Swing Trading AI · v2.0 All-Weather Hub",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CLASSY_MINIMAL_CSS, unsafe_allow_html=True)
    _sync_streamlit_secrets_to_env(st)

    _code_version = "2026-11-14-v2.0"
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
    research_reports: List[Dict[str, Any]] = state.get("research_reports") or []
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

    # ---------------- SIDEBAR ----------------
    with st.sidebar:
        st.markdown("### ⚡ All-Weather Control")
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
        st.markdown("#### 💰 Custom Capital Sizing")
        custom_capital = float(
            st.slider(
                "Your Real Account Capital ($ USD)",
                min_value=10_000,
                max_value=500_000,
                value=25_000,
                step=5_000,
                help="Dynamically scales share counts, position notional, and 1R dollar stop risk on every Long & Short Trade Card.",
            )
        )
        custom_long_risk_pct = (
            float(
                st.select_slider(
                    "Long Risk / Trade (%)",
                    options=[0.50, 0.75, 1.00, 1.25, 1.50],
                    value=1.25,
                )
            )
            / 100.0
        )
        st.caption(
            f"1R Budget: **${custom_capital * custom_long_risk_pct:,.0f}** (Long) · "
            f"**${custom_capital * 0.01:,.0f}** (Short 1.0% cap)"
        )

        st.markdown("---")
        st.markdown("#### 🔄 Live Broker & News Sync")
        if st.button("Sync All 3 Alpaca Pods & News Now", type="primary", use_container_width=True):
            with st.spinner("Scanning live Alpaca news, quotes & syncing 3 Paper Pods..."):
                if hasattr(app.orchestrator.market_data, "ensure_latest_market_data"):
                    app.orchestrator.market_data.ensure_latest_market_data()
                if hasattr(app.orchestrator.market_data, "scan_live_alpaca_news_and_movers"):
                    app.orchestrator.market_data.scan_live_alpaca_news_and_movers(cache_ttl_seconds=0)
                spy_bars_now = app.orchestrator.market_data.get_bars("SPY")
                latest_dt = spy_bars_now[-1].bar_date if spy_bars_now else today_iso
                app.orchestrator.research_agent.run_market_scan(as_of_date=latest_dt, top_n=10)
                app.orchestrator.pod_manager.evaluate_and_sync_all_pods(
                    session_date=latest_dt,
                    execute_live_orders=True,
                )
            st.rerun()

        if st.button("Run 9-Gate Strategy Tournament", use_container_width=True):
            with st.spinner("Running 9-Gate OOS + Walk-Forward + Mistake Analyzer Tournament..."):
                spy_bars_now = app.orchestrator.market_data.get_bars("SPY")
                latest_dt = spy_bars_now[-1].bar_date if spy_bars_now else today_iso
                app.orchestrator.run_weekly_workflow(week_ending_date=latest_dt, force=True)
            st.rerun()

        st.markdown("---")
        st.markdown(
            f"🔗 **[Open Alpaca Paper Portal ↗]({ALPACA_PAPER_PORTAL_URL})**\n\n"
            f"• Safety Lock: `TRADING_MODE=paper`\n"
            f"• Active Universe: **{len(universe_meta)} liquid US equities**\n"
            f"• Strategies Tracked: **{len(strategies)} versions**"
        )

    # ---------------- AGGREGATE POD DATA ----------------
    all_trade_cards: List[Dict[str, Any]] = []
    all_open_holdings: List[Dict[str, Any]] = []
    all_exit_actions: List[Dict[str, Any]] = []
    all_vetoed: List[Dict[str, Any]] = []
    all_broker_orders: List[Dict[str, Any]] = []

    for pod in pods_list:
        pod_name = str(pod.get("label") or pod.get("short_label") or pod.get("pod_name") or pod.get("pod_id") or "")
        pod_id = str(pod.get("pod_id") or "")
        b_st = pod.get("broker_state") or pod.get("broker") or {}
        acct_num = str(b_st.get("alpaca_account_number") or b_st.get("account_number") or "N/A")
        for c in pod.get("executed_or_queued") or pod.get("approved_buys") or []:
            item = dict(c)
            item["_pod_name"] = pod_name
            item["_pod_id"] = pod_id
            item["_account_number"] = acct_num
            all_trade_cards.append(item)
        holdings_src = pod.get("active_holdings_plan") or b_st.get("positions") or []
        for pos in holdings_src:
            p_item = dict(pos)
            p_item["_pod_name"] = pod_name
            p_item["_pod_id"] = pod_id
            p_item["_account_number"] = acct_num
            all_open_holdings.append(p_item)
        for act in pod.get("ratchets_and_exits") or pod.get("sell_decisions") or []:
            a_item = dict(act)
            a_item["_pod_name"] = pod_name
            a_item["_account_number"] = acct_num
            all_exit_actions.append(a_item)
        for vet in pod.get("skipped_reasons") or pod.get("filtered_signals") or []:
            v_item = dict(vet)
            v_item["_pod_name"] = pod_name
            all_vetoed.append(v_item)
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

    all_trade_cards.sort(key=lambda x: float(x.get("composite_alpha_score") or x.get("alpha_score") or x.get("conviction_score") or 0.0), reverse=True)

    # ---------------- TOP BRIEFING BANNER + 3 POD CARDS ----------------
    market_regime = str(pods_payload.get("market_regime") or "SIDEWAYS_CHOPPY")
    session_dt = str(pods_payload.get("session_date") or today_iso)
    long_cards_cnt = sum(1 for c in all_trade_cards if str(c.get("side", "LONG")).upper() == "LONG")
    short_cards_cnt = sum(1 for c in all_trade_cards if str(c.get("side", "LONG")).upper() == "SHORT")
    long_hold_cnt = sum(1 for p in all_open_holdings if str(p.get("side", "LONG")).upper() == "LONG")
    short_hold_cnt = sum(1 for p in all_open_holdings if str(p.get("side", "LONG")).upper() == "SHORT")
    latest_news_headline = (
        f"{live_catalysts[0]['ticker']}: {live_catalysts[0]['headline']}"
        if live_catalysts
        else "24/7 Alpaca News & Screener active — click 'Sync All 3 Alpaca Pods & News Now' to refresh."
    )

    st.markdown(
        f"<div style='background:linear-gradient(90deg,rgba(15,23,42,0.88),rgba(30,41,59,0.78));"
        f"border:1px solid rgba(56,189,248,0.28);border-radius:10px;padding:13px 18px;margin-bottom:14px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;'>"
        f"<div><span style='font-size:1.08rem;font-weight:700;color:#f8fafc;'>All-Weather Swing Trading Decision Hub</span> "
        f"<span style='background:rgba(56,189,248,0.16);color:#38bdf8;padding:2px 9px;border-radius:999px;font-size:0.74rem;font-weight:600;margin-left:6px;'>"
        f"Regime: {html.escape(market_regime)}</span> "
        f"<span style='color:#94a3b8;font-size:0.79rem;margin-left:8px;'>Bar Date: <code>{html.escape(session_dt)}</code></span></div>"
        f"<div style='font-size:0.81rem;color:#cbd5e1;'>"
        f"Setups Today: <strong style='color:#10b981;'>{long_cards_cnt} Long</strong> · <strong style='color:#f87171;'>{short_cards_cnt} Short</strong> &nbsp;|&nbsp; "
        f"Open Holdings: <strong>{long_hold_cnt}L / {short_hold_cnt}S</strong> &nbsp;|&nbsp; "
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

    # ---------------- 4-TAB DECISION HUB ----------------
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            f"🎯 Today's Trade Cards ({len(all_trade_cards)})",
            f"🛡️ Active Holdings & Exit Guardian ({len(all_open_holdings)})",
            "🏆 Strategy Tournament & Mistake Analyzer",
            f"📰 Live News & Universe ({len(universe_meta)})",
        ]
    )

    # =========================================================================
    # TAB 1: TODAY'S TRADE CARDS & VISUAL SETUPS
    # =========================================================================
    with tab1:
        f_col1, f_col2 = st.columns([2.2, 2.8])
        with f_col1:
            dir_filter = st.radio(
                "Direction Filter",
                options=["All Setups", "Long Only (🟢)", "Short Only (🔴)"],
                horizontal=True,
                label_visibility="collapsed",
            )
        with f_col2:
            st.caption(
                f"Showing setups scaled for both **$100k Alpaca Pod** and **Your ${custom_capital:,.0f} Custom Capital** "
                f"(`{custom_long_risk_pct * 100:.2f}%` Long / `1.00%` Short risk per trade)."
            )

        filtered_cards = all_trade_cards
        if "Long" in dir_filter:
            filtered_cards = [c for c in all_trade_cards if str(c.get("side", "LONG")).upper() == "LONG"]
        elif "Short" in dir_filter:
            filtered_cards = [c for c in all_trade_cards if str(c.get("side", "LONG")).upper() == "SHORT"]

        if filtered_cards:
            for card in filtered_cards:
                side = str(card.get("side", "LONG")).upper()
                ticker = str(card.get("ticker", ""))
                entry_px = float(card.get("live_price") or card.get("entry_price") or card.get("reference_close") or 0.0)
                limit_px = float(card.get("max_chase_price") or card.get("max_chase_limit_price") or entry_px)
                stop_px = float(card.get("stop_loss_price") or card.get("stop_loss") or 0.0)
                s1_px = float(card.get("stage1_ratchet_price") or 0.0)
                s2_px = float(card.get("stage2_ratchet_price") or 0.0)
                tp_px = float(card.get("take_profit_price") or card.get("take_profit") or 0.0)
                pod_shares = int(card.get("shares") or card.get("qty") or 0)
                cust = _compute_custom_capital_sizing(
                    custom_capital=custom_capital,
                    entry_price=entry_px,
                    stop_price=stop_px,
                    side=side,
                    long_risk_pct=custom_long_risk_pct,
                )
                side_badge = (
                    "<span style='background:rgba(16,185,129,0.2);color:#34d399;padding:3px 10px;border-radius:6px;font-weight:700;font-size:0.8rem;'>🟢 BUY LONG</span>"
                    if side == "LONG"
                    else "<span style='background:rgba(239,68,68,0.22);color:#f87171;padding:3px 10px;border-radius:6px;font-weight:700;font-size:0.8rem;'>🔴 SELL SHORT</span>"
                )
                news_score = float(card.get("ai_catalyst_score") or card.get("news_sentiment_score") or 0.0)
                sent_html = _sentiment_badge_html(news_score)
                alpha_val = float(card.get("composite_alpha_score") or card.get("alpha_score") or card.get("conviction_score") or 0.0)
                rationale_txt = str(card.get("signal_reason") or card.get("rationale") or "; ".join(card.get("factors") or []))

                with st.container(border=True):
                    c_left, c_right = st.columns([1.25, 1.35])
                    with c_left:
                        st.markdown(
                            f"{side_badge} &nbsp; <strong style='font-size:1.18rem;'>{html.escape(ticker)}</strong> "
                            f"<span style='color:#94a3b8;font-size:0.82rem;'>({html.escape(str(card.get('sector', '')))}) · "
                            f"{html.escape(str(card.get('_pod_name', '')))} · Alpha <code>{alpha_val:.2f}</code></span> "
                            f"&nbsp; {sent_html}",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f"**Your `${custom_capital:,.0f}` Sizing:** `{cust['shares']} shs` "
                            f"(`${cust['notional']:,.0f}` · `{cust['exposure_pct']:.1f}%` cap · **1R Risk `${cust['dollar_risk']:,.0f}`**)\n\n"
                            f"**Pod `$100k` Sizing (`{card.get('_account_number', '')}`):** `{pod_shares} shs` · "
                            f"Order Status: `{card.get('order_status', 'READY')}`"
                        )
                        limit_lbl = "Max Limit Buy" if side == "LONG" else "Min Limit Short"
                        st.markdown(
                            f"- **Ref / Live Price:** `${entry_px:.2f}` ({limit_lbl}: `${limit_px:.2f}`)\n"
                            f"- **Hard Stop (`-1.0R`):** `${stop_px:.2f}` · **Stage 1 (`1.0R` BE):** `${s1_px:.2f}`\n"
                            f"- **Stage 2 (`1.65R` Lock):** `${s2_px:.2f}` · **Target:** `${tp_px:.2f}`"
                        )
                        st.caption(f"**Setup Rationale:** {rationale_txt}")
                        if card.get("news_headline"):
                            st.caption(f"📰 **Catalyst:** {card.get('news_headline')}")
                    with c_right:
                        chart_bars = card.get("chart_bars_60d") or []
                        if not chart_bars:
                            chart_bars = _fetch_chart_bars_for_ticker(app, ticker)
                        st.markdown(
                            _render_candlestick_svg(
                                bars=chart_bars,
                                ticker=ticker,
                                side=side,
                                entry_price=entry_px,
                                stop_price=stop_px,
                                stage1_price=s1_px,
                                stage2_price=s2_px,
                                target_price=tp_px,
                            ),
                            unsafe_allow_html=True,
                        )
        else:
            st.info(
                "**No New Entry Cards Triggered Right Now — Capital Preserved.** "
                "All 3 Pods evaluated both Long and Short mandates against regime, liquidity, ATR risk, and live news filters. "
                "Inspect the top watchlist charts or filtered-signal diagnostics below."
            )
            if research_reports:
                st.markdown("##### 📊 Top Watchlist 60-Day Candlestick Inspector")
                watch_tickers = [str(r.get("ticker")) for r in research_reports[:8] if r.get("ticker")]
                sel_watch = st.selectbox("Inspect Watchlist Ticker (60-Day OHLC + SMA20/SMA50)", options=watch_tickers)
                if sel_watch:
                    rep_match = next((r for r in research_reports if r.get("ticker") == sel_watch), {})
                    w_bars = _fetch_chart_bars_for_ticker(app, sel_watch)
                    wc1, wc2 = st.columns([1.05, 1.55])
                    with wc1:
                        st.markdown(
                            f"**{sel_watch} — {rep_match.get('company_name', '')}**\n\n"
                            f"- **Price:** `${float(rep_match.get('current_price') or 0):.2f}`\n"
                            f"- **20d RS vs SPY:** `{float(rep_match.get('relative_strength_vs_spy_20d') or 0):+.2f}%`\n"
                            f"- **Suggested Family:** `{rep_match.get('suggested_strategy_family', '')}`\n"
                            f"- **Bullish Thesis:** {rep_match.get('bullish_thesis', '')}\n"
                            f"- **Bearish Thesis:** {rep_match.get('bearish_thesis', '')}"
                        )
                    with wc2:
                        st.markdown(
                            _render_candlestick_svg(bars=w_bars, ticker=sel_watch, side="LONG"),
                            unsafe_allow_html=True,
                        )

        st.markdown("---")
        with st.expander(f"🔍 Why Stocks Were Filtered / Vetoed Across All 3 Pods ({len(all_vetoed)} diagnostics)", expanded=False):
            q_search = st.text_input("Search Ticker or Veto Rule (e.g. NVDA, NEWS_VETO, SHORT, EXPOSURE)", key="veto_search")
            shown_vetoes = [
                v for v in all_vetoed
                if not q_search
                or q_search.upper() in str(v.get("ticker", "")).upper()
                or q_search.upper() in str(v.get("status_badge") or v.get("gate") or "").upper()
                or q_search.upper() in str(v.get("reason", "")).upper()
            ]
            if shown_vetoes:
                st.dataframe(
                    [
                        {
                            "Pod": v.get("_pod_name", ""),
                            "Side": v.get("side", "LONG"),
                            "Ticker": v.get("ticker", ""),
                            "Gate / Filter": v.get("status_badge") or v.get("category") or v.get("gate", ""),
                            "Reason": v.get("reason") or v.get("technical_summary", ""),
                        }
                        for v in shown_vetoes[:60]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No matching filtered-signal diagnostics.")

    # =========================================================================
    # TAB 2: ACTIVE HOLDINGS & LIVE EXIT GUARDIAN
    # =========================================================================
    with tab2:
        if all_open_holdings:
            st.markdown("#### 🛡️ Live Alpaca Paper Positions Across All 3 Pods")
            for pos in all_open_holdings:
                tkr = str(pos.get("ticker", ""))
                side = str(pos.get("side", "LONG")).upper()
                qty = int(pos.get("quantity") or pos.get("qty") or 0)
                avg_px = float(pos.get("entry_price") or pos.get("avg_entry_price") or 0.0)
                cur_px = float(pos.get("live_price") or pos.get("current_price") or avg_px)
                u_pnl = float(pos.get("unrealised_pnl_usd") if pos.get("unrealised_pnl_usd") is not None else (pos.get("unrealized_pl") or 0.0))
                u_pct = float(pos.get("unrealised_pnl_pct") if pos.get("unrealised_pnl_pct") is not None else (pos.get("unrealized_plpc") or 0.0))
                stop_px = float(pos.get("current_stop_price") or pos.get("stop_loss_price") or 0.0)
                tp_px = float(pos.get("take_profit_price") or 0.0)
                has_oco = bool(pos.get("has_live_oco_bracket") or pos.get("stop_stage_label"))

                init_risk = max(abs(avg_px - stop_px), avg_px * 0.02) if stop_px > 0 else max(avg_px * 0.03, 0.01)
                r_mult = ((cur_px - avg_px) / init_risk) if side == "LONG" else ((avg_px - cur_px) / init_risk)
                prog_val = max(0.0, min(1.0, (r_mult + 1.0) / 3.5))

                dir_pill = "🟢 LONG" if side == "LONG" else "🔴 SHORT"
                oco_pill = "✅ Live GTC OCO Protected" if has_oco else "⚠️ Self-Healing Bracket Pending"
                pnl_txt = f"${u_pnl:+,.2f} ({u_pct:+.2f}%)"

                with st.container(border=True):
                    hc1, hc2, hc3, hc4 = st.columns([1.5, 1.1, 1.2, 1.2])
                    hc1.markdown(f"**{dir_pill} · {tkr}** (`{qty} shs`)\n\n{pos.get('_pod_name', '')} (`{pos.get('_account_number', '')}`)")
                    hc2.metric("Entry → Current", f"${cur_px:.2f}", f"Avg ${avg_px:.2f}")
                    hc3.metric("Unrealized P&L", pnl_txt, f"{r_mult:+.2f}R")
                    hc4.markdown(
                        f"**Bracket:** {oco_pill}\n\n"
                        f"Stop: `${stop_px:.2f}` · Target: `${tp_px:.2f}`"
                    )
                    st.progress(prog_val, text=f"R-Multiple Trajectory: {r_mult:+.2f}R (Stage 1 BE @ +1.0R · Stage 2 Profit Lock @ +1.65R)")
                    with st.expander(f"📈 View {tkr} 60-Day Candlestick & Active Stop Chart"):
                        p_bars = pos.get("chart_bars_60d") or _fetch_chart_bars_for_ticker(app, tkr)
                        st.markdown(
                            _render_candlestick_svg(
                                bars=p_bars,
                                ticker=tkr,
                                side=side,
                                entry_price=avg_px,
                                stop_price=stop_px if stop_px > 0 else None,
                                target_price=tp_px if tp_px > 0 else None,
                            ),
                            unsafe_allow_html=True,
                        )
        else:
            st.info("No open positions across the 3 Alpaca Paper accounts right now (`100% Cash`).")

        if all_exit_actions:
            st.markdown("#### ⚙️ Latest Exit Guardian & Stop-Ratchet Verdicts")
            st.dataframe(
                [
                    {
                        "Pod": a.get("_pod_name", ""),
                        "Account": a.get("_account_number", ""),
                        "Side": a.get("side", "LONG"),
                        "Ticker": a.get("ticker", ""),
                        "Action": a.get("action", ""),
                        "Live Price": f"${float(a.get('live_price') or 0):.2f}",
                        "Effective Stop": f"${float(a.get('effective_stop') or 0):.2f}" if a.get("effective_stop") else "—",
                        "Target": f"${float(a.get('take_profit') or 0):.2f}" if a.get("take_profit") else "—",
                        "Reason": a.get("reason", ""),
                    }
                    for a in all_exit_actions
                ],
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("---")
        oc1, oc2 = st.columns(2)
        with oc1:
            st.markdown("##### 📋 Live & Recent Alpaca Broker Orders")
            if all_broker_orders:
                st.dataframe(
                    [
                        {
                            "Bucket": o.get("_bucket", ""),
                            "Account": o.get("_account_number", ""),
                            "Ticker": o.get("symbol", ""),
                            "Side": str(o.get("side", "")).upper(),
                            "Type": o.get("type", ""),
                            "Qty": o.get("qty", ""),
                            "Status": o.get("status", ""),
                            "Limit / Stop": o.get("limit_price") or o.get("stop_price") or "MKT",
                        }
                        for o in all_broker_orders[:30]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No open or recent broker orders recorded yet.")

        with oc2:
            st.markdown("##### 📓 Day-by-Day Pod Decision Journal")
            decision_logs = app.orchestrator.pod_manager.get_recent_decision_logs(limit=12)
            if decision_logs:
                for dlog in decision_logs[:6]:
                    st.markdown(
                        f"- **`{dlog.get('session_date', '')}` · {dlog.get('pod_id', '')}** "
                        f"(`{dlog.get('status', '')}`): {dlog.get('executive_summary', '')}"
                    )
            else:
                st.caption("Decision journal entries populate automatically on every Pod sync.")

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
        ma1.metric("Closed Round-Trips Analyzed", f"{tot_closed}", mistake_analyzer.get("data_source", "PAPER_LEDGER"))
        ma2.metric("Overall Win Rate", f"{float(mistake_analyzer.get('overall_win_rate_pct') or 0.0):.1f}%")
        ma3.metric("Realized Profit Factor", f"{float(mistake_analyzer.get('overall_profit_factor') or 0.0):.2f}x")
        ma4.metric("Total Realized Net P&L", f"${float(mistake_analyzer.get('total_net_pnl') or 0.0):+,.2f}")

        weaknesses = mistake_analyzer.get("detected_weaknesses") or []
        if weaknesses:
            st.markdown("##### 🔧 Detected Mistake Patterns & Auto-Tuner Rule Patches")
            for w in weaknesses:
                st.warning(
                    f"**[{w.get('category', 'DIAGNOSIS')} — {w.get('bucket', '')}]** {w.get('finding', '')}\n\n"
                    f"👉 **Auto-Tuner Remedy (`{w.get('target_strategy_id', '')}`):** {w.get('remedy', '')}"
                )
        else:
            st.success(
                "No recurring post-trade pathology flagged yet. As Alpaca closed round-trips accumulate in `alpaca_closed_trades`, "
                "the Mistake Analyzer automatically diagnoses regime, sector, direction, and premature-stop patterns."
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

        with st.expander("🤖 Advanced: Apply IDE AI JSON Cycle Payload (`apply_ide_ai_cycle`)"):
            raw_ai_json = st.text_area(
                "Paste JSON payload (`discovered_tickers`, `research_updates`, `candidate_strategies`)",
                height=130,
                placeholder='{"discovered_tickers": ["CRWD"], "research_updates": [], "candidate_strategies": []}',
            )
            if st.button("Execute AI Tournament Payload"):
                try:
                    parsed_payload = json.loads(raw_ai_json)
                    res_ai = app.orchestrator.apply_ide_ai_cycle(parsed_payload)
                    st.success(
                        f"Applied AI cycle: onboarded={res_ai.get('dynamic_onboarding', {}).get('onboarded', [])}, "
                        f"enriched={res_ai.get('research_tickers_enriched', [])}"
                    )
                except Exception as exc:
                    st.error(f"Invalid JSON or execution error: {exc}")

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
                st.caption("No catalysts stored yet — click 'Sync All 3 Alpaca Pods & News Now' in the sidebar.")

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
