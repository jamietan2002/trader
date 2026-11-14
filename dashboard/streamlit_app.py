"""Streamlit Community Cloud & Local Dashboard Entrypoint (`streamlit run dashboard/streamlit_app.py`).

v3.0 Minimalist Dark Autonomous Portfolio Hub (Linear / Apple Stocks Aesthetic):
- Clean full-width layout with no left sidebar, zero emojis, zero neon borders, and plain-English explanations.
- 3 focused tabs:
  1. Overview & Open Trades — Portfolio summary, 3 Paper Account cards, Working Entry Orders, and Open Positions with plain-English entry reasons and automatic Stop-Loss / Profit Target prices.
  2. Daily Journal — Clean chronological day-by-day log of orders placed/filled, positions held, and skipped setups.
  3. Performance & System — Strategy track record, closed-trade review, latest market news, and automated Daily/Weekly run log.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

# Ensure repository root is on sys.path when Streamlit runs `dashboard/streamlit_app.py`
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ALPACA_PAPER_PORTAL_URL = "https://app.alpaca.markets/paper/dashboard/overview"

POD_DISPLAY_NAMES = {
    "pod_1_breakout": "Account 1 · Breakout",
    "pod_2_mean_reversion": "Account 2 · Pullback",
    "pod_3_momentum": "Account 3 · Momentum",
}

POD_STRATEGY_DESCRIPTIONS = {
    "pod_1_breakout": "Buys stocks breaking above 20-day highs on strong volume; shorts support breakdowns.",
    "pod_2_mean_reversion": "Buys uptrending stocks during calm dips near their 20-day trend; shorts overextended bounces.",
    "pod_3_momentum": "Follows market leaders with sustained upward momentum and positive earnings catalysts.",
}

MINIMAL_DARK_CSS = """
<style>
  /* Hide Streamlit left sidebar & collapse control for a clean full-width web app */
  [data-testid="stSidebar"],
  [data-testid="collapsedControl"],
  [data-testid="stSidebarCollapsedControl"] {
    display: none !important;
  }

  .stApp {
    background-color: #0c0e12 !important;
    color: #f1f5f9 !important;
  }

  .block-container {
    padding-top: 2.0rem !important;
    padding-bottom: 3.5rem !important;
    max-width: 1140px !important;
  }

  /* Clean typography & tabular numerals */
  html, body, [class*="css"] {
    font-feature-settings: "cv02", "cv03", "cv04", "cv11";
    -webkit-font-smoothing: antialiased;
  }

  /* Minimalist tab bar (Linear style) */
  [data-baseweb="tab-list"] {
    gap: 24px !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    padding-bottom: 0px !important;
    background: transparent !important;
  }
  [data-baseweb="tab"] {
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    color: #8b95a5 !important;
    padding: 10px 2px 12px 2px !important;
    background: transparent !important;
  }
  [data-baseweb="tab"][aria-selected="true"] {
    color: #f8fafc !important;
    font-weight: 600 !important;
  }
  [data-baseweb="tab-highlight"] {
    background-color: #f8fafc !important;
    height: 2px !important;
  }

  /* Subtle expanders and dataframes */
  [data-testid="stExpander"] {
    background: #12151b !important;
    border: 1px solid rgba(255, 255, 255, 0.07) !important;
    border-radius: 8px !important;
  }
  hr {
    margin: 1.5rem 0 !important;
    border-color: rgba(255, 255, 255, 0.07) !important;
  }

  /* Reusable minimalist surface classes */
  .md-surface {
    background: #13161c;
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 12px;
  }
  .md-kpi-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    background: #13161c;
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 10px;
    padding: 16px 20px;
    gap: 20px;
    margin-bottom: 12px;
  }
  .md-acct-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }
  .md-acct-card {
    background: #13161c;
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 10px;
    padding: 14px 16px;
  }
  .md-pos-metrics {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 14px;
    padding: 12px 0;
    margin: 10px 0;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }
  .md-ord-metrics {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    padding: 10px 0 4px 0;
    margin-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
  .md-label {
    font-size: 0.70rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748b;
    font-weight: 500;
    margin-bottom: 3px;
  }
  .md-num {
    font-size: 0.98rem;
    font-weight: 600;
    color: #f1f5f9;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em;
  }
  .md-num-lg {
    font-size: 1.38rem;
    font-weight: 600;
    color: #f8fafc;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
  }
  .md-sub {
    font-size: 0.76rem;
    color: #8b95a5;
    font-variant-numeric: tabular-nums;
    margin-top: 2px;
  }
  .md-pos { color: #22c55e !important; }
  .md-neg { color: #ef4444 !important; }
  .md-muted { color: #8b95a5 !important; }

  @media (max-width: 860px) {
    .md-kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .md-acct-grid { grid-template-columns: 1fr; }
    .md-pos-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .md-ord-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
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


def _format_sgt_timestamp(iso_str: str) -> str:
    """Format an ISO timestamp into 'Nov 14, 11:48 SGT'."""
    raw = str(iso_str or "").strip()
    if not raw:
        return "—"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Singapore")).strftime("%b %d, %H:%M SGT")
    except Exception:
        return raw[:16].replace("T", " ")


def _pnl_class(val: float) -> str:
    if val > 0.004:
        return "md-pos"
    if val < -0.004:
        return "md-neg"
    return "md-muted"


def _compute_exit_numbers(
    side: str,
    entry_px: float,
    init_stop_px: float,
    cur_stop_px: float,
    stage1_trigger_px: float = 0.0,
    target_px: float = 0.0,
) -> Dict[str, float]:
    """Return clean Stop-Loss, Breakeven Trigger, and Profit Target prices."""
    is_short = str(side or "LONG").upper() == "SHORT"
    eff_init_stop = init_stop_px if init_stop_px > 0 else cur_stop_px
    one_r = abs(entry_px - eff_init_stop) if (entry_px > 0 and eff_init_stop > 0) else max(entry_px * 0.03, 0.01)
    one_r = max(one_r, 0.01)
    if is_short:
        be_trig = stage1_trigger_px if stage1_trigger_px > 0 else round(entry_px - one_r, 2)
        tp = target_px if target_px > 0 else round(entry_px - 2.2 * one_r, 2)
    else:
        be_trig = stage1_trigger_px if stage1_trigger_px > 0 else round(entry_px + one_r, 2)
        tp = target_px if target_px > 0 else round(entry_px + 2.2 * one_r, 2)
    return {
        "stop": cur_stop_px if cur_stop_px > 0 else eff_init_stop,
        "be_trigger": be_trig,
        "target": tp,
    }


def _plain_english_reason(raw_text: str, side: str = "LONG", ai_sent: float = 0.0) -> str:
    """Translate technical indicator triggers into clear, beginner-friendly English."""
    raw = str(raw_text or "").strip()
    low = raw.lower()
    is_short = str(side or "LONG").upper() == "SHORT"

    # Extract relative strength vs S&P 500 if present (e.g. RS20d=+6.9%)
    rs_match = re.search(r"rs20d\s*=\s*([+-]?\d+(?:\.\d+)?%)", raw, flags=re.IGNORECASE)
    rs_phrase = f" while outperforming the S&P 500 ({rs_match.group(1)} over 20 days)" if rs_match else ""

    # Check catalyst sentiment from string if not passed explicitly
    cat_match = re.search(r"catalyst\s*([+-]?\d+(?:\.\d+)?)", raw, flags=re.IGNORECASE)
    if cat_match and abs(ai_sent) < 0.01:
        try:
            ai_sent = float(cat_match.group(1))
        except Exception:
            pass

    if is_short:
        if "mean reversion" in low or "fade" in low or "overbought" in low:
            base = "Sold short after an overextended bounce inside a broader downtrend"
        elif "breakdown" in low or "20-day low" in low or "20d low" in low:
            base = "Sold short as price broke below recent support on elevated selling volume"
        else:
            base = "Sold short due to sustained downward trend and weak relative performance"
    else:
        if "mean reversion" in low or "pullback" in low or "lowerbb" in low or "oversold" in low:
            base = f"Bought during a calm dip in an uptrending stock{rs_phrase}"
        elif "breakout" in low or "20d high" in low or "20-day high" in low:
            base = f"Bought as price broke out near a new 20-day high on strong volume{rs_phrase}"
        elif "pead" in low or "earnings" in low:
            base = f"Bought following a positive earnings surprise and upward trend{rs_phrase}"
        elif "momentum" in low or "relative strength" in low:
            base = f"Bought for steady upward trend momentum{rs_phrase}"
        elif "working" in low and "limit" in low:
            base = "Limit order queued on Alpaca waiting for price to trade at or better than your entry limit"
        else:
            base = f"Bought after meeting trend and relative-strength entry rules{rs_phrase}"

    if not is_short and ai_sent >= 0.25:
        base += ", supported by positive news sentiment"
    elif is_short and ai_sent <= -0.25:
        base += ", reinforced by negative news sentiment"

    return base.rstrip(".") + "."


def _plain_english_order_status(raw_status: str, limit_px: float = 0.0) -> str:
    """Convert internal broker status codes into clean everyday text."""
    s = str(raw_status or "").strip()
    su = s.upper()
    fill_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", s)
    if "FILLED_ON_ALPACA" in su or su == "FILLED":
        if fill_match:
            return f"Filled at ${float(fill_match.group(1)):,.2f}"
        return "Filled"
    if "QUEUED_ON_ALPACA" in su or "SUBMITTED_TO_ALPACA" in su or su in ("ACCEPTED", "NEW", "PENDING_NEW"):
        return f"Working limit at ${limit_px:,.2f}" if limit_px > 0 else "Working on Alpaca"
    if "SIMULATED" in su:
        return "Simulated (pre-account link)"
    return s.replace("_", " ").title()


def _plain_english_skip_reason(raw_reason: str, badge: str = "") -> str:
    """Simplify veto/skip messages for beginners."""
    txt = str(raw_reason or badge or "").strip()
    low = txt.lower()
    if "already_held" in low or "already held" in low:
        return "Skipped because this stock is already held in the account."
    if "bearish" in low or "news" in low:
        return "Blocked because recent news sentiment was negative."
    if "squeeze" in low or "bullish" in low:
        return "Short setup blocked because news sentiment turned positive."
    if "max_sector" in low or "sector" in low:
        return "Skipped to avoid concentrating too much money in one sector."
    if "max_open" in low or "positions" in low:
        return "Skipped because the account reached its maximum open positions limit."
    if "earnings" in low:
        return "Skipped because an earnings report is scheduled within 2 trading days."
    if "cash" in low or "buying power" in low or "exposure" in low:
        return "Skipped to keep portfolio cash and position size within safety limits."
    if "pending scheduled" in low:
        return "Qualified at close; queued for the next scheduled execution window."
    return txt


def _tone_label(score: float) -> str:
    if score >= 0.20:
        return "Positive"
    if score <= -0.20:
        return "Negative"
    return "Neutral"


def _summarize_job_row(j: Dict[str, Any]) -> Dict[str, str]:
    j_name = str(j.get("job_name") or "")
    s = j.get("summary") or {}
    if not isinstance(s, dict):
        s = {}
    label_map = {
        "weekly_research_and_validation": "Weekly Strategy Review",
        "daily_pre_market": "Daily Market Scan",
        "daily_market_execution": "Daily Order Execution",
        "daily_post_close": "Daily Post-Close Review",
        "ide_ai_cycle": "IDE AI Research Run",
    }
    session_str = str(
        s.get("week_ending_date")
        or s.get("trading_date")
        or s.get("as_of_date")
        or s.get("session_date")
        or (str(j.get("idempotency_key") or "").split(":")[1] if ":" in str(j.get("idempotency_key") or "") else "—")
    )
    if j_name == "weekly_research_and_validation":
        cands = s.get("tournament_candidates") or ([] if not s.get("candidate_strategy_id") else [s])
        prom_cnt = sum(1 for c in cands if c.get("promoted"))
        outcome = (
            f"Tested {len(cands)} new strategy variations; {prom_cnt} promoted, active strategies retained"
            if prom_cnt == 0
            else f"Tested {len(cands)} variations; {prom_cnt} promoted"
        )
    elif j_name == "ide_ai_cycle":
        tkrs = ", ".join((s.get("research_tickers_enriched") or [])[:5])
        outcome = f"Reviewed live news for {tkrs or 'top stocks'} and tested {int(s.get('candidates_tested') or 0)} variations"
    elif j_name == "daily_post_close":
        outcome = "Reconciled positions, stops, and daily portfolio risk checks"
    elif j_name == "daily_pre_market":
        outcome = f"Scanned {s.get('universe_scanned', '—')} US stocks for entry setups"
    elif j_name == "daily_market_execution":
        outcome = f"{len(s.get('entries_executed') or [])} entries filled, {len(s.get('exits_executed') or [])} exits filled"
    else:
        outcome = str(j.get("error_message") or "Completed")

    raw_status = str(j.get("status") or "").upper()
    clean_status = "Completed" if raw_status == "COMPLETED" else raw_status.title()
    return {
        "Task": label_map.get(j_name, j_name),
        "Session": session_str,
        "Time (SGT)": _format_sgt_timestamp(str(j.get("completed_at") or j.get("started_at") or "")),
        "Status": clean_status,
        "Summary": outcome,
    }


def main() -> None:
    try:
        import streamlit as st
    except ImportError:
        print(
            "Streamlit is not installed in the current environment. "
            "Run `pip install streamlit` or launch the built-in zero-dependency web server via `python main.py serve`."
        )
        return

    st.set_page_config(
        page_title="Swing Trader · Paper Portfolio",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _sync_streamlit_secrets_to_env(st)
    st.markdown(MINIMAL_DARK_CSS, unsafe_allow_html=True)

    from api.server import PlatformApplication
    from core.market_data.models import USTradingCalendar

    _code_version = "2026-11-14-v3.0"
    if (
        "platform_app" not in st.session_state
        or st.session_state.get("platform_app_version") != _code_version
    ):
        app_inst = PlatformApplication()
        if not app_inst.orchestrator.registry.list_strategies():
            with st.spinner("Initializing strategies and historical market data..."):
                app_inst.orchestrator.bootstrap_baseline_system()
        else:
            app_inst.orchestrator.ensure_all_golden_strategies_registered()
        st.session_state["platform_app"] = app_inst
        st.session_state["platform_app_version"] = _code_version

    app: PlatformApplication = st.session_state["platform_app"]
    state = app.get_dashboard_state()

    pods_state = state.get("strategy_pods") or {}
    pods_list: List[Dict[str, Any]] = pods_state.get("pods") or []
    decision_logs: List[Dict[str, Any]] = app.orchestrator.pod_manager.get_recent_decision_logs(limit=90)
    mistake_analyzer: Dict[str, Any] = state.get("mistake_analyzer") or {}
    live_catalysts: List[Dict[str, Any]] = state.get("live_catalysts") or []
    universe_meta: List[Dict[str, Any]] = state.get("universe_metadata") or []
    strategies: List[Dict[str, Any]] = state.get("strategies") or []
    jobs: List[Dict[str, Any]] = state.get("jobs") or []

    # Market session timing
    et_now = USTradingCalendar.current_et_datetime()
    today_dt = et_now.date()
    is_trading_day = USTradingCalendar.is_trading_day(today_dt)
    is_mkt_open = USTradingCalendar.is_market_open()
    next_trading_day = USTradingCalendar.next_trading_day(today_dt, include_same_day=is_trading_day)
    open_sgt = USTradingCalendar.market_open_sgt() if hasattr(USTradingCalendar, "market_open_sgt") else "10:30 PM SGT"
    close_sgt = USTradingCalendar.market_close_sgt() if hasattr(USTradingCalendar, "market_close_sgt") else "5:00 AM SGT"

    if is_mkt_open:
        market_status_str = f"US Market Open · Closes {close_sgt}"
        status_dot_col = "#22c55e"
    elif is_trading_day:
        market_status_str = f"US Market Closed · Opens Today {open_sgt}"
        status_dot_col = "#94a3b8"
    else:
        next_human = _format_human_date(str(next_trading_day))
        market_status_str = f"US Market Closed · Next Session {next_human} ({open_sgt})"
        status_dot_col = "#64748b"

    # Aggregate portfolio & order state across all 3 accounts
    all_open_holdings: List[Dict[str, Any]] = []
    all_working_entry_orders: List[Dict[str, Any]] = []
    all_broker_orders: List[Dict[str, Any]] = []
    seen_order_keys: set[str] = set()

    total_equity = 0.0
    total_start_cap = 0.0
    total_cash = 0.0
    active_pod_accounts = 0

    for pod in pods_list:
        pod_id = str(pod.get("pod_id") or "")
        pod_name = POD_DISPLAY_NAMES.get(pod_id, str(pod.get("short_label") or pod_id))
        b_st = pod.get("broker_state") or pod.get("broker") or {}
        acct_num = str(b_st.get("alpaca_account_number") or b_st.get("account_number") or "Paper")
        eq = float(b_st.get("total_equity") or b_st.get("equity") or 100_000.0)
        sc = float(b_st.get("starting_capital") or 100_000.0)
        csh = float(b_st.get("cash_balance") or b_st.get("cash") or eq)

        total_equity += eq
        total_start_cap += sc
        total_cash += csh

        holdings_src = pod.get("active_holdings_plan") or b_st.get("positions") or []
        if holdings_src:
            active_pod_accounts += 1
        for pos in holdings_src:
            p_item = dict(pos)
            p_item["_pod_name"] = pod_name
            p_item["_pod_id"] = pod_id
            p_item["_account_number"] = acct_num
            all_open_holdings.append(p_item)

        for bo in b_st.get("open_orders") or []:
            o_item = dict(bo)
            o_item["_pod_name"] = pod_name
            o_item["_pod_id"] = pod_id
            o_item["_account_number"] = acct_num
            o_item["_bucket"] = "Open"
            oid_k = f"{acct_num}:{o_item.get('order_id') or o_item.get('client_order_id')}"
            seen_order_keys.add(oid_k)
            all_broker_orders.append(o_item)
            o_cls = str(o_item.get("order_class") or "").upper()
            o_cid = str(o_item.get("client_order_id") or "")
            if o_cls not in ("OCO", "OTO", "BRACKET_EXIT") and ":oco:" not in o_cid and ":exit:" not in o_cid:
                all_working_entry_orders.append(o_item)

        for bo in (b_st.get("recent_orders") or [])[:12]:
            o_item = dict(bo)
            oid_k = f"{acct_num}:{o_item.get('order_id') or o_item.get('client_order_id')}"
            if oid_k in seen_order_keys:
                continue
            seen_order_keys.add(oid_k)
            o_item["_pod_name"] = pod_name
            o_item["_pod_id"] = pod_id
            o_item["_account_number"] = acct_num
            o_item["_bucket"] = "Recent"
            all_broker_orders.append(o_item)

    if total_start_cap <= 0:
        total_start_cap = 300_000.0
        total_equity = 300_000.0
        total_cash = 300_000.0

    total_pnl = total_equity - total_start_cap
    total_ret_pct = (total_pnl / total_start_cap) * 100.0
    cash_pct = (total_cash / max(total_equity, 1.0)) * 100.0
    tot_pnl_cls = _pnl_class(total_pnl)

    # ---------------- CLEAN FULL-WIDTH HEADER ----------------
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:12px;margin-bottom:18px;'>"
        f"<div>"
        f"<span style='font-size:1.35rem;font-weight:600;color:#f8fafc;letter-spacing:-0.02em;'>Swing Trader</span>"
        f"<span style='font-size:0.86rem;color:#64748b;margin-left:10px;'>Autonomous Paper Portfolio</span>"
        f"</div>"
        f"<div style='font-size:0.80rem;color:#94a3b8;display:flex;align-items:center;gap:14px;'>"
        f"<span><span style='display:inline-block;width:7px;height:7px;border-radius:50%;background:{status_dot_col};margin-right:6px;vertical-align:middle;'></span>"
        f"{html.escape(market_status_str)}</span>"
        f"<a href='{ALPACA_PAPER_PORTAL_URL}' target='_blank' style='color:#cbd5e1;text-decoration:none;border-bottom:1px solid rgba(203,213,225,0.3);'>Alpaca Portal ↗</a>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ---------------- PORTFOLIO KPI STRIP ----------------
    st.markdown(
        f"<div class='md-kpi-strip'>"
        f"<div>"
        f"<div class='md-label'>Total Portfolio Value</div>"
        f"<div class='md-num-lg'>${total_equity:,.2f}</div>"
        f"<div class='md-sub {tot_pnl_cls}'>{total_pnl:+,.2f} USD ({total_ret_pct:+.2f}%)</div>"
        f"</div>"
        f"<div>"
        f"<div class='md-label'>Available Cash</div>"
        f"<div class='md-num-lg'>${total_cash:,.0f}</div>"
        f"<div class='md-sub'>{cash_pct:.0f}% of portfolio uninvested</div>"
        f"</div>"
        f"<div>"
        f"<div class='md-label'>Open Positions</div>"
        f"<div class='md-num-lg'>{len(all_open_holdings)}</div>"
        f"<div class='md-sub'>Active across {active_pod_accounts} of 3 accounts</div>"
        f"</div>"
        f"<div>"
        f"<div class='md-label'>Working Entry Orders</div>"
        f"<div class='md-num-lg'>{len(all_working_entry_orders)}</div>"
        f"<div class='md-sub'>{'Waiting for limit price on Alpaca' if all_working_entry_orders else 'No pending entry orders'}</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ---------------- 3 PAPER ACCOUNT CARDS ----------------
    if pods_list:
        acct_cards_html: List[str] = []
        for pod in pods_list:
            pid = str(pod.get("pod_id") or "")
            p_title = POD_DISPLAY_NAMES.get(pid, str(pod.get("short_label") or pid))
            p_desc = POD_STRATEGY_DESCRIPTIONS.get(pid, "")
            b_st = pod.get("broker_state") or pod.get("broker") or {}
            eq = float(b_st.get("total_equity") or b_st.get("equity") or 100_000.0)
            sc = float(b_st.get("starting_capital") or 100_000.0)
            csh = float(b_st.get("cash_balance") or b_st.get("cash") or eq)
            pnl = eq - sc
            ret_p = (pnl / max(sc, 1.0)) * 100.0
            acct_id = str(b_st.get("alpaca_account_number") or b_st.get("account_number") or "Paper")
            open_cnt = len(pod.get("active_holdings_plan") or b_st.get("positions") or [])
            work_cnt = sum(
                1
                for o in (b_st.get("open_orders") or [])
                if str(o.get("order_class") or "").upper() not in ("OCO", "OTO", "BRACKET_EXIT")
                and ":oco:" not in str(o.get("client_order_id") or "")
                and ":exit:" not in str(o.get("client_order_id") or "")
            )
            p_cls = _pnl_class(pnl)
            acct_cards_html.append(
                f"<div class='md-acct-card'>"
                f"<div style='display:flex;justify-content:space-between;align-items:baseline;'>"
                f"<span style='font-size:0.86rem;font-weight:600;color:#f1f5f9;'>{html.escape(p_title)}</span>"
                f"<span style='font-size:0.74rem;color:#64748b;font-family:monospace;'>{html.escape(acct_id)}</span>"
                f"</div>"
                f"<div style='display:flex;justify-content:space-between;align-items:baseline;margin-top:8px;'>"
                f"<span class='md-num' style='font-size:1.12rem;'>${eq:,.2f}</span>"
                f"<span class='md-sub {p_cls}' style='font-weight:500;'>{pnl:+,.2f} ({ret_p:+.2f}%)</span>"
                f"</div>"
                f"<div style='font-size:0.75rem;color:#8b95a5;margin-top:6px;'>"
                f"Cash ${csh:,.0f} &nbsp;·&nbsp; {open_cnt} open &nbsp;·&nbsp; {work_cnt} working"
                f"</div>"
                f"<div style='font-size:0.73rem;color:#64748b;margin-top:5px;line-height:1.35;'>{html.escape(p_desc)}</div>"
                f"</div>"
            )
        st.markdown(f"<div class='md-acct-grid'>{''.join(acct_cards_html)}</div>", unsafe_allow_html=True)

    # ---------------- 3 MINIMALIST TABS ----------------
    tab1, tab2, tab3 = st.tabs(
        [
            "Overview & Open Trades",
            "Daily Journal",
            "Performance & System",
        ]
    )

    # =========================================================================
    # TAB 1: OVERVIEW & OPEN TRADES
    # =========================================================================
    with tab1:
        acct_filter_opts = ["All Accounts"] + list(POD_DISPLAY_NAMES.keys())
        sel_acct = st.selectbox(
            "Account View",
            options=acct_filter_opts,
            format_func=lambda x: x if x == "All Accounts" else POD_DISPLAY_NAMES.get(x, x),
            key="overview_acct_filter",
            label_visibility="collapsed",
        )

        shown_working = [
            w for w in all_working_entry_orders if sel_acct == "All Accounts" or w.get("_pod_id") == sel_acct
        ]
        shown_holdings = [
            h for h in all_open_holdings if sel_acct == "All Accounts" or h.get("_pod_id") == sel_acct
        ]

        # 1. Working Entry Orders
        if shown_working:
            st.markdown(
                f"<div style='font-size:0.88rem;font-weight:600;color:#e2e8f0;margin:8px 0 10px 0;'>"
                f"Working Orders Waiting to Fill ({len(shown_working)})</div>",
                unsafe_allow_html=True,
            )
            for wo in shown_working:
                w_tkr = str(wo.get("ticker") or "")
                is_short_w = str(wo.get("side") or "BUY").upper() == "SELL"
                w_action = "Sell Short" if is_short_w else "Buy"
                w_qty = int(wo.get("qty") or 0)
                w_lim = float(wo.get("limit_price") or 0.0)
                w_stop = float(wo.get("stop_price") or 0.0)
                w_tp = float(wo.get("take_profit_price") or 0.0)
                w_val = round(w_qty * w_lim, 2)
                w_max_loss = round(abs(w_lim - w_stop) * w_qty, 2) if w_stop > 0 else 0.0
                w_est_gain = round(abs(w_tp - w_lim) * w_qty, 2) if w_tp > 0 else 0.0
                w_pod = str(wo.get("_pod_name") or "")
                w_acct = str(wo.get("_account_number") or "")

                st.markdown(
                    f"<div class='md-surface'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;'>"
                    f"<div>"
                    f"<span style='font-size:1.0rem;font-weight:600;color:#f8fafc;'>{html.escape(w_tkr)}</span>"
                    f"<span style='font-size:0.82rem;color:#94a3b8;margin-left:8px;'>{w_action} {w_qty} shares</span>"
                    f"<span style='font-size:0.78rem;color:#64748b;margin-left:8px;'>· {html.escape(w_pod)} ({html.escape(w_acct)})</span>"
                    f"</div>"
                    f"<div style='font-size:0.80rem;color:#94a3b8;'>Working on Alpaca</div>"
                    f"</div>"
                    f"<div class='md-ord-metrics'>"
                    f"<div><div class='md-label'>Entry Limit</div><div class='md-num'>${w_lim:,.2f}</div><div class='md-sub'>Max price to pay</div></div>"
                    f"<div><div class='md-label'>Order Value</div><div class='md-num'>${w_val:,.0f}</div><div class='md-sub'>{w_qty} shares</div></div>"
                    f"<div><div class='md-label'>Auto Stop-Loss</div><div class='md-num'>${w_stop:,.2f}</div><div class='md-sub'>Max loss -${w_max_loss:,.0f}</div></div>"
                    f"<div><div class='md-label'>Profit Target</div><div class='md-num'>${w_tp:,.2f}</div><div class='md-sub'>Target gain +${w_est_gain:,.0f}</div></div>"
                    f"</div>"
                    f"<div style='font-size:0.80rem;color:#8b95a5;margin-top:6px;line-height:1.45;'>"
                    f"Waiting to fill at ${w_lim:,.2f} or better during regular US market hours; Stop-Loss (${w_stop:,.2f}) and Profit Target (${w_tp:,.2f}) activate automatically on fill."
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # 2. Open Positions
        st.markdown(
            f"<div style='font-size:0.88rem;font-weight:600;color:#e2e8f0;margin:16px 0 10px 0;'>"
            f"Open Positions ({len(shown_holdings)})</div>",
            unsafe_allow_html=True,
        )
        if shown_holdings:
            for pos in shown_holdings:
                tkr = str(pos.get("ticker") or "")
                side = str(pos.get("side") or "LONG").upper()
                is_short = side == "SHORT"
                dir_lbl = "Short" if is_short else "Long"
                sec = str(pos.get("sector") or "")
                qty = abs(int(pos.get("quantity") or pos.get("qty") or 0))
                avg_px = float(pos.get("avg_entry_price") or pos.get("entry_price") or 0.0)
                cur_px = float(pos.get("current_price") or pos.get("live_price") or avg_px)
                mkt_val = abs(qty * cur_px)
                hold_d = int(pos.get("holding_days") or 0)
                max_d = int(pos.get("max_hold_days") or 15)
                u_pnl = float(
                    pos.get("unrealised_pnl")
                    if pos.get("unrealised_pnl") is not None
                    else (pos.get("unrealised_pnl_usd") if pos.get("unrealised_pnl_usd") is not None else 0.0)
                )
                u_pct = float(
                    pos.get("unrealised_return_pct")
                    if pos.get("unrealised_return_pct") is not None
                    else (pos.get("unrealised_pnl_pct") if pos.get("unrealised_pnl_pct") is not None else 0.0)
                )

                ex = _compute_exit_numbers(
                    side=side,
                    entry_px=avg_px,
                    init_stop_px=float(pos.get("initial_stop_price") or pos.get("current_stop_price") or 0.0),
                    cur_stop_px=float(pos.get("current_stop_price") or pos.get("stop_loss_price") or 0.0),
                    stage1_trigger_px=float(pos.get("stage1_ratchet_price") or 0.0),
                    target_px=float(pos.get("take_profit_price") or 0.0),
                )
                stop_px = ex["stop"]
                tp_px = ex["target"]
                be_px = ex["be_trigger"]

                stop_pnl = ((avg_px - stop_px) if is_short else (stop_px - avg_px)) * qty
                tp_pnl = ((avg_px - tp_px) if is_short else (tp_px - avg_px)) * qty

                why_plain = _plain_english_reason(
                    str(pos.get("entry_thesis") or ""),
                    side=side,
                    ai_sent=float(pos.get("ai_catalyst_score") or 0.0),
                )
                close_verb = "buys back" if is_short else "sells"
                pnl_cls = _pnl_class(u_pnl)
                sec_html = (
                    f"<span style='font-size:0.78rem;color:#64748b;margin-left:8px;'>· {html.escape(sec)}</span>"
                    if sec
                    else ""
                )

                st.markdown(
                    f"<div class='md-surface'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;'>"
                    f"<div>"
                    f"<span style='font-size:1.04rem;font-weight:600;color:#f8fafc;'>{html.escape(tkr)}</span>"
                    f"<span style='font-size:0.82rem;color:#94a3b8;margin-left:8px;'>{dir_lbl} · {qty} shares</span>"
                    f"{sec_html}"
                    f"<span style='font-size:0.78rem;color:#64748b;margin-left:8px;'>· {html.escape(str(pos.get('_pod_name', '')))} ({html.escape(str(pos.get('_account_number', '')))})</span>"
                    f"</div>"
                    f"<div style='font-variant-numeric:tabular-nums;font-size:0.95rem;font-weight:600;' class='{pnl_cls}'>"
                    f"{u_pnl:+,.2f} USD ({u_pct:+.2f}%)"
                    f"</div>"
                    f"</div>"
                    f"<div class='md-pos-metrics'>"
                    f"<div><div class='md-label'>Entry Price</div><div class='md-num'>${avg_px:,.2f}</div><div class='md-sub'>Day {hold_d} of {max_d} max</div></div>"
                    f"<div><div class='md-label'>Current Price</div><div class='md-num'>${cur_px:,.2f}</div><div class='md-sub'>Value ${mkt_val:,.0f}</div></div>"
                    f"<div><div class='md-label'>Stop-Loss</div><div class='md-num'>${stop_px:,.2f}</div><div class='md-sub'>{stop_pnl:+,.0f} USD vs entry</div></div>"
                    f"<div><div class='md-label'>Profit Target</div><div class='md-num'>${tp_px:,.2f}</div><div class='md-sub'>{tp_pnl:+,.0f} USD vs entry</div></div>"
                    f"<div><div class='md-label'>Breakeven Step</div><div class='md-num'>${be_px:,.2f}</div><div class='md-sub'>Raises stop to entry</div></div>"
                    f"</div>"
                    f"<div style='font-size:0.81rem;color:#cbd5e1;line-height:1.48;'>"
                    f"{html.escape(why_plain)} "
                    f"<span style='color:#8b95a5;'>Alpaca automatically {close_verb} at ${tp_px:,.2f} for profit or ${stop_px:,.2f} to cap loss.</span>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No open positions for the selected account view.")

        # 3. Clean Collapsible Broker Order Ledger
        shown_orders = [
            o for o in all_broker_orders if sel_acct == "All Accounts" or o.get("_pod_id") == sel_acct
        ]
        if shown_orders:
            with st.expander(f"View Alpaca Broker Order Log ({len(shown_orders)})", expanded=False):
                st.dataframe(
                    [
                        {
                            "Type": o.get("_bucket", ""),
                            "Account": o.get("_account_number", ""),
                            "Ticker": o.get("ticker") or o.get("symbol", ""),
                            "Action": str(o.get("side", "")).title(),
                            "Shares": o.get("qty", ""),
                            "Entry / Fill": (
                                f"${float(o['filled_avg_price']):,.2f}"
                                if o.get("filled_avg_price")
                                else (
                                    f"${float(o['limit_price']):,.2f}"
                                    if (o.get("limit_price") and str(o.get("order_class", "")).upper() not in ("OCO", "BRACKET_EXIT"))
                                    else "—"
                                )
                            ),
                            "Stop-Loss": f"${float(o['stop_price']):,.2f}" if o.get("stop_price") else "—",
                            "Profit Target": f"${float(o['take_profit_price']):,.2f}" if o.get("take_profit_price") else "—",
                            "Status": str(o.get("status", "")).replace("_", " ").title(),
                        }
                        for o in shown_orders[:40]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

    # =========================================================================
    # TAB 2: DAILY JOURNAL
    # =========================================================================
    with tab2:
        jf1, jf2, jf3 = st.columns([1.2, 1.2, 1.2])
        with jf1:
            pod_filter_opts = ["All 3 Strategy Pods"] + list(POD_DISPLAY_NAMES.keys())
            pod_filter = st.selectbox(
                "Account",
                options=pod_filter_opts,
                format_func=lambda x: "All Accounts" if x == "All 3 Strategy Pods" else POD_DISPLAY_NAMES.get(x, x),
                key="journal_pod_filter",
            )
        with jf2:
            activity_filter = st.selectbox(
                "Show",
                options=["All Trading Days", "Days With New Orders Only"],
                format_func=lambda x: "Days with new orders" if x == "Days With New Orders Only" else "All trading days",
                key="journal_activity_filter",
            )
        with jf3:
            ticker_search = st.text_input(
                "Search Ticker",
                placeholder="e.g. AAPL, LLY, SLB",
                key="journal_ticker_search",
            ).strip().upper()

        logs_by_date: Dict[str, List[Dict[str, Any]]] = {}
        for dlog in decision_logs:
            dt_k = str(dlog.get("session_date") or "")[:10]
            if not dt_k:
                continue
            if pod_filter != "All 3 Strategy Pods" and dlog.get("pod_id") != pod_filter:
                continue
            logs_by_date.setdefault(dt_k, []).append(dlog)

        ordered_dates = sorted(logs_by_date.keys(), reverse=True)

        if not ordered_dates:
            st.caption("No daily journal entries recorded yet.")
        else:
            rendered_days = 0
            for day_idx, dt_key in enumerate(ordered_dates):
                day_pods = sorted(logs_by_date[dt_key], key=lambda x: str(x.get("pod_id", "")))
                day_entries_total = sum(len(p.get("executed_or_queued") or []) for p in day_pods)
                day_holds_total = sum(len(p.get("active_holdings_plan") or []) for p in day_pods)
                day_ratchets_total = sum(len(p.get("ratchets_and_exits") or []) for p in day_pods)

                if activity_filter == "Days With New Orders Only" and day_entries_total == 0 and day_ratchets_total == 0:
                    continue

                if ticker_search and ticker_search not in json.dumps(day_pods).upper():
                    continue

                rendered_days += 1
                human_dt = _format_human_date(dt_key)
                latest_lbl = " · Latest Session" if day_idx == 0 else ""

                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;"
                    f"padding:18px 0 8px 0;border-bottom:1px solid rgba(255,255,255,0.08);margin-bottom:12px;'>"
                    f"<div style='font-size:0.98rem;font-weight:600;color:#f8fafc;'>{html.escape(human_dt)}"
                    f"<span style='font-size:0.78rem;color:#64748b;font-weight:400;margin-left:8px;'>{html.escape(dt_key)}{latest_lbl}</span></div>"
                    f"<div style='font-size:0.79rem;color:#8b95a5;'>"
                    f"{day_entries_total} orders &nbsp;·&nbsp; {day_holds_total} positions held"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

                for p_log in day_pods:
                    pid = str(p_log.get("pod_id") or "")
                    p_disp = POD_DISPLAY_NAMES.get(pid, pid)
                    acct_str = str(p_log.get("alpaca_account_number") or "Paper")
                    entries_list = p_log.get("executed_or_queued") or []
                    ratchets_list = p_log.get("ratchets_and_exits") or []
                    holds_list = p_log.get("active_holdings_plan") or []
                    skips_list = p_log.get("skipped_reasons") or []

                    notable_vetoes = [s for s in skips_list if str(s.get("category", "")) != "NO_TECHNICAL_SIGNAL"]
                    quiet_skips = [s for s in skips_list if str(s.get("category", "")) == "NO_TECHNICAL_SIGNAL"]

                    is_shadow_log = str(p_log.get("broker_mode") or "").startswith("SHADOW_POD")
                    if is_shadow_log:
                        status_txt = "Simulated (before Alpaca account link)"
                    elif entries_list:
                        status_txt = f"{len(entries_list)} order(s) placed or filled"
                    elif holds_list:
                        status_txt = f"Holding {len(holds_list)} position(s) · No new trades"
                    else:
                        status_txt = "No trades (100% cash)"

                    rows_html: List[str] = []
                    for e in entries_list:
                        e_side = str(e.get("side") or "LONG").upper()
                        e_act = "Sell Short" if e_side == "SHORT" else "Buy"
                        e_tkr = str(e.get("ticker") or "")
                        e_shs = int(e.get("shares") or 0)
                        e_lim = float(e.get("max_chase_price") or e.get("live_price") or e.get("reference_close_price") or 0.0)
                        e_stop = float(e.get("stop_loss_price") or 0.0)
                        e_tp = float(e.get("take_profit_price") or 0.0)
                        e_cost = float(e.get("estimated_cost_usd") or (e_shs * e_lim))
                        e_stat = _plain_english_order_status(str(e.get("order_status") or ""), e_lim)
                        e_why = _plain_english_reason(
                            str(e.get("technical_trigger") or ""),
                            side=e_side,
                            ai_sent=float(e.get("ai_catalyst_sentiment") or 0.0),
                        )
                        rows_html.append(
                            f"<div style='padding:10px 0;border-top:1px solid rgba(255,255,255,0.06);'>"
                            f"<div style='display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;'>"
                            f"<div><strong style='color:#f8fafc;font-size:0.90rem;'>{html.escape(e_tkr)}</strong> "
                            f"<span style='color:#94a3b8;font-size:0.82rem;'>{e_act} {e_shs} shares · ${e_cost:,.0f}</span></div>"
                            f"<div style='font-size:0.80rem;color:#e2e8f0;font-variant-numeric:tabular-nums;'>{html.escape(e_stat)}</div>"
                            f"</div>"
                            f"<div style='font-size:0.79rem;color:#94a3b8;margin-top:4px;font-variant-numeric:tabular-nums;'>"
                            f"Entry limit ${e_lim:,.2f} &nbsp;·&nbsp; Stop-Loss ${e_stop:,.2f} &nbsp;·&nbsp; Profit Target ${e_tp:,.2f}"
                            f"</div>"
                            f"<div style='font-size:0.79rem;color:#8b95a5;margin-top:3px;'>{html.escape(e_why)}</div>"
                            f"</div>"
                        )

                    for r_act in ratchets_list:
                        rows_html.append(
                            f"<div style='padding:8px 0;border-top:1px solid rgba(255,255,255,0.06);font-size:0.80rem;color:#cbd5e1;'>"
                            f"<strong>{html.escape(str(r_act.get('ticker', '')))}</strong> — Stop-Loss raised from "
                            f"${float(r_act.get('old_stop_price') or 0):,.2f} to ${float(r_act.get('new_stop_price') or 0):,.2f} to lock in gains."
                            f"</div>"
                        )

                    if holds_list:
                        hold_lines: List[str] = []
                        for h in holds_list:
                            h_tkr = str(h.get("ticker") or "")
                            h_qty = abs(int(h.get("quantity") or h.get("qty") or 0))
                            h_avg = float(h.get("avg_entry_price") or 0.0)
                            h_cur = float(h.get("current_price") or h_avg)
                            h_ret = float(h.get("unrealised_return_pct") or 0.0)
                            h_stop = float(h.get("current_stop_price") or 0.0)
                            h_tp = float(h.get("take_profit_price") or 0.0)
                            h_cls = _pnl_class(h_ret)
                            hold_lines.append(
                                f"<div style='display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;padding:5px 0;font-size:0.79rem;font-variant-numeric:tabular-nums;'>"
                                f"<span style='color:#cbd5e1;'><strong style='color:#f1f5f9;'>{html.escape(h_tkr)}</strong> · {h_qty} shs · Entry ${h_avg:,.2f} → ${h_cur:,.2f} "
                                f"(<span class='{h_cls}'>{h_ret:+.2f}%</span>)</span>"
                                f"<span style='color:#8b95a5;'>Stop ${h_stop:,.2f} · Target ${h_tp:,.2f}</span>"
                                f"</div>"
                            )
                        rows_html.append(
                            f"<div style='padding-top:8px;margin-top:4px;border-top:1px solid rgba(255,255,255,0.06);'>"
                            f"<div class='md-label' style='margin-bottom:4px;'>Positions Held ({len(holds_list)})</div>"
                            f"{''.join(hold_lines)}</div>"
                        )

                    if not entries_list and not holds_list:
                        rows_html.append(
                            "<div style='font-size:0.79rem;color:#64748b;padding-top:6px;border-top:1px solid rgba(255,255,255,0.05);'>"
                            "No stocks in the 40-stock universe met all entry and risk criteria today."
                            "</div>"
                        )

                    st.markdown(
                        f"<div class='md-surface'>"
                        f"<div style='display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;margin-bottom:6px;'>"
                        f"<div><span style='font-size:0.90rem;font-weight:600;color:#f8fafc;'>{html.escape(p_disp)}</span>"
                        f"<span style='font-size:0.76rem;color:#64748b;margin-left:8px;font-family:monospace;'>{html.escape(acct_str)}</span></div>"
                        f"<div style='font-size:0.78rem;color:#94a3b8;'>{html.escape(status_txt)}</div>"
                        f"</div>"
                        f"{''.join(rows_html)}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                    if notable_vetoes:
                        with st.expander(f"{p_disp} — {len(notable_vetoes)} setup(s) skipped by safety rules ({dt_key})", expanded=False):
                            for nv in notable_vetoes:
                                st.markdown(
                                    f"- **{nv.get('ticker', '')}**: {_plain_english_skip_reason(str(nv.get('reason', '')), str(nv.get('status_badge', '')))}"
                                )

                    if quiet_skips:
                        with st.expander(f"{p_disp} — {len(quiet_skips)} stocks did not meet entry criteria ({dt_key})", expanded=False):
                            st.dataframe(
                                [
                                    {
                                        "Ticker": qs.get("ticker", ""),
                                        "Sector": qs.get("sector", ""),
                                        "Close": f"${float(qs.get('live_price') or 0):,.2f}",
                                        "Detail": qs.get("technical_summary") or qs.get("reason", ""),
                                    }
                                    for qs in quiet_skips
                                ],
                                use_container_width=True,
                                hide_index=True,
                            )

            if rendered_days == 0:
                st.caption("No journal days matched your filter.")

    # =========================================================================
    # TAB 3: PERFORMANCE & SYSTEM
    # =========================================================================
    with tab3:
        latest_weekly_job = next(
            (j for j in jobs if j.get("job_name") == "weekly_research_and_validation"),
            None,
        )
        last_weekly_sgt = (
            _format_sgt_timestamp(str(latest_weekly_job.get("completed_at") or latest_weekly_job.get("started_at") or ""))
            if latest_weekly_job
            else "Scheduled Sat 10:00 AM SGT"
        )

        # 1. Clean 3-Column Autonomous Schedule Strip
        st.markdown(
            f"<div class='md-acct-grid' style='margin-top:8px;'>"
            f"<div class='md-acct-card'>"
            f"<div class='md-label'>Daily Automated Runs (Mon–Fri)</div>"
            f"<div style='font-size:0.84rem;color:#e2e8f0;margin-top:4px;font-weight:500;'>5:30 AM · 9:00/10:00 PM · 9:35/10:35 PM SGT</div>"
            f"<div style='font-size:0.76rem;color:#8b95a5;margin-top:4px;line-height:1.4;'>Scans closing prices, checks pre-market news &amp; gaps, and manages Alpaca orders automatically.</div>"
            f"</div>"
            f"<div class='md-acct-card'>"
            f"<div class='md-label'>Weekly Strategy Review (Sat 10:00 AM SGT)</div>"
            f"<div style='font-size:0.84rem;color:#e2e8f0;margin-top:4px;font-weight:500;'>Last Run: {html.escape(last_weekly_sgt)}</div>"
            f"<div style='font-size:0.76rem;color:#8b95a5;margin-top:4px;line-height:1.4;'>Tests new strategy variations against 2.3 years of data; replaces an active strategy only if it outperforms.</div>"
            f"</div>"
            f"<div class='md-acct-card'>"
            f"<div class='md-label'>Universe &amp; Risk Guardrails</div>"
            f"<div style='font-size:0.84rem;color:#e2e8f0;margin-top:4px;font-weight:500;'>{len(universe_meta)} Liquid US Stocks · Paper Mode</div>"
            f"<div style='font-size:0.76rem;color:#8b95a5;margin-top:4px;line-height:1.4;'>Every position has an automatic Stop-Loss and Profit Target on Alpaca with ~1% risk per trade.</div>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # 2. Active Strategy Track Record (Active PAPER_TRADING strategies first, clean labels)
        st.markdown(
            "<div style='font-size:0.88rem;font-weight:600;color:#e2e8f0;margin:8px 0 10px 0;'>"
            "Active Strategy Historical Track Record (2.3-Year Backtest)</div>",
            unsafe_allow_html=True,
        )
        active_strats = [s for s in strategies if str(s.get("status", "")).upper() == "PAPER_TRADING"]
        display_strats = active_strats if active_strats else strategies
        strat_rows = []
        for s in display_strats:
            m = s.get("backtest_summary") or {}
            val = s.get("validation_summary") or {}
            oos = val.get("oos_metrics") or {}
            strat_rows.append(
                {
                    "Strategy": s.get("name", s.get("strategy_id", "")),
                    "Direction": "Short" if "BEARISH" in str(s.get("strategy_family", "")).upper() else "Long",
                    "2.3-Yr Return": f"{float(m.get('total_return_pct', 0.0)):+.1f}%" if m else "—",
                    "Recent Test Return": f"{float(oos.get('total_return_pct', 0.0)):+.1f}%" if oos else "—",
                    "Win Rate": f"{float(m.get('win_rate_pct', 0.0)):.1f}%" if m and m.get("win_rate_pct") is not None else "—",
                    "Worst Historical Drop": f"-{float(m.get('max_drawdown_pct', 0.0)):.1f}%" if m else "—",
                    "Sample Trades": int(m.get("trade_count", 0)) if m else 0,
                }
            )
        if strat_rows:
            st.dataframe(strat_rows, use_container_width=True, hide_index=True)

        # 3. Closed Trade Review
        st.markdown(
            "<div style='font-size:0.88rem;font-weight:600;color:#e2e8f0;margin:20px 0 10px 0;'>"
            "Closed Trade Review</div>",
            unsafe_allow_html=True,
        )
        tot_closed = int(mistake_analyzer.get("total_closed_trades") or 0)
        win_r = float(mistake_analyzer.get("overall_win_rate_pct") or 0.0)
        pf_val = float(mistake_analyzer.get("overall_profit_factor") or 0.0)
        net_real = float(mistake_analyzer.get("total_net_pnl") or 0.0)
        real_cls = _pnl_class(net_real)

        st.markdown(
            f"<div class='md-kpi-strip'>"
            f"<div><div class='md-label'>Closed Trades Analyzed</div><div class='md-num'>{tot_closed}</div></div>"
            f"<div><div class='md-label'>Win Rate</div><div class='md-num'>{win_r:.1f}%</div></div>"
            f"<div><div class='md-label'>Gain-to-Loss Ratio</div><div class='md-num'>{pf_val:.2f}x</div></div>"
            f"<div><div class='md-label'>Net Realized P&amp;L</div><div class='md-num {real_cls}'>{net_real:+,.2f} USD</div></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # 4. Market News & Automated Run Log
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        nc1, nc2 = st.columns([1.05, 1.15])
        with nc1:
            st.markdown(
                "<div style='font-size:0.88rem;font-weight:600;color:#e2e8f0;margin-bottom:10px;'>"
                "Recent Stock News</div>",
                unsafe_allow_html=True,
            )
            if live_catalysts:
                news_items_html: List[str] = []
                for cat in live_catalysts[:10]:
                    c_score = float(cat.get("sentiment_score") or 0.0)
                    tone = _tone_label(c_score)
                    tone_col = "#22c55e" if tone == "Positive" else ("#ef4444" if tone == "Negative" else "#8b95a5")
                    url_str = str(cat.get("url") or "").strip()
                    link_html = (
                        f" · <a href='{html.escape(url_str)}' target='_blank' style='color:#94a3b8;text-decoration:none;'>Read ↗</a>"
                        if url_str.startswith("http")
                        else ""
                    )
                    news_items_html.append(
                        f"<div style='padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06);font-size:0.81rem;'>"
                        f"<div style='display:flex;justify-content:space-between;margin-bottom:3px;'>"
                        f"<strong style='color:#f8fafc;'>{html.escape(str(cat.get('ticker', '')))}</strong>"
                        f"<span style='font-size:0.74rem;color:{tone_col};'>{tone} · {html.escape(str(cat.get('published_date', ''))[:10])}{link_html}</span>"
                        f"</div>"
                        f"<div style='color:#cbd5e1;line-height:1.4;'>{html.escape(str(cat.get('headline', '')))}</div>"
                        f"</div>"
                    )
                st.markdown(f"<div class='md-surface' style='padding:6px 18px;'>{''.join(news_items_html)}</div>", unsafe_allow_html=True)
            else:
                st.caption("No recent news headlines stored yet.")

        with nc2:
            st.markdown(
                "<div style='font-size:0.88rem;font-weight:600;color:#e2e8f0;margin-bottom:10px;'>"
                "Automated Run Log</div>",
                unsafe_allow_html=True,
            )
            if jobs:
                st.dataframe(
                    [_summarize_job_row(j) for j in jobs[:15]],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No automated runs logged yet.")


if __name__ == "__main__":
    main()
