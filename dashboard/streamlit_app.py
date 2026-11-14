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


def _format_short_date(iso_dt: str) -> str:
    """Format '2026-11-13' into 'Fri, Nov 13'."""
    try:
        d_obj = date.fromisoformat(str(iso_dt)[:10])
        return d_obj.strftime("%a, %b %d")
    except Exception:
        return str(iso_dt)


def _build_daily_takeaway(day_pods: List[Dict[str, Any]], pod_filter: str) -> str:
    """Generate a concise 1-sentence plain-English takeaway summarizing what the system did on a given day."""
    filled_tkrs: List[str] = []
    working_tkrs: List[str] = []
    ratchet_tkrs: List[str] = []
    total_holds = 0
    notable_skip_cnt = 0

    for p in day_pods:
        for e in p.get("executed_or_queued") or []:
            t = str(e.get("ticker") or "")
            st_u = str(e.get("order_status") or "").upper()
            if "FILLED" in st_u:
                filled_tkrs.append(t)
            else:
                working_tkrs.append(t)
        for r in p.get("ratchets_and_exits") or []:
            ratchet_tkrs.append(str(r.get("ticker") or ""))
        total_holds += len(p.get("active_holdings_plan") or [])
        notable_skip_cnt += sum(
            1 for s in (p.get("skipped_reasons") or []) if str(s.get("category", "")) != "NO_TECHNICAL_SIGNAL"
        )

    scope_lbl = "Across your accounts" if pod_filter == "All 3 Strategy Pods" else f"In {POD_DISPLAY_NAMES.get(pod_filter, pod_filter)}"
    clauses: List[str] = []
    if filled_tkrs:
        clauses.append(f"filled {len(filled_tkrs)} order{'s' if len(filled_tkrs) != 1 else ''} ({', '.join(filled_tkrs[:5])})")
    if working_tkrs:
        clauses.append(f"queued {len(working_tkrs)} working limit order{'s' if len(working_tkrs) != 1 else ''} ({', '.join(working_tkrs[:5])})")
    if ratchet_tkrs:
        clauses.append(f"raised stop-losses on {len(ratchet_tkrs)} position{'s' if len(ratchet_tkrs) != 1 else ''}")

    if clauses:
        action_part = ", ".join(clauses)
        hold_part = f", while managing {total_holds} open position{'s' if total_holds != 1 else ''} with automatic stop and target protection" if total_holds else ""
        return f"{scope_lbl}, the system {action_part}{hold_part}."

    if total_holds > 0:
        skip_note = f" ({notable_skip_cnt} candidate setup{'s' if notable_skip_cnt != 1 else ''} skipped by safety rules)" if notable_skip_cnt else ""
        return (
            f"{scope_lbl}, no new orders were placed after scanning the universe{skip_note}; "
            f"continued holding {total_holds} open position{'s' if total_holds != 1 else ''} with automatic stop-loss and target orders."
        )

    return f"{scope_lbl}, no stocks met all entry and safety criteria today, so capital remained 100% in cash."


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

    _code_version = "2026-11-14-v3.1"
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
    # TAB 2: DAILY JOURNAL (SINGLE-DAY UNIFIED ACTIVITY FLOW)
    # =========================================================================
    with tab2:
        # Hide pre-link 'Simulated' (SHADOW_POD) records by default so only real Alpaca Paper history shows
        live_only_logs = [
            d for d in decision_logs if not str(d.get("broker_mode") or "").startswith("SHADOW_POD")
        ]
        effective_logs = live_only_logs if live_only_logs else decision_logs

        # Top Control Bar: Account & Activity Filters
        fc1, fc2 = st.columns([1.0, 1.0])
        with fc1:
            pod_filter_opts = ["All 3 Strategy Pods"] + list(POD_DISPLAY_NAMES.keys())
            pod_filter = st.selectbox(
                "Account",
                options=pod_filter_opts,
                format_func=lambda x: "All Accounts" if x == "All 3 Strategy Pods" else POD_DISPLAY_NAMES.get(x, x),
                key="journal_pod_filter",
                label_visibility="collapsed",
            )
        with fc2:
            activity_filter = st.selectbox(
                "Show",
                options=["All Trading Days", "Days With New Orders Only"],
                format_func=lambda x: "Days with new orders only" if x == "Days With New Orders Only" else "All trading days",
                key="journal_activity_filter",
                label_visibility="collapsed",
            )

        logs_by_date: Dict[str, List[Dict[str, Any]]] = {}
        for dlog in effective_logs:
            dt_k = str(dlog.get("session_date") or "")[:10]
            if not dt_k:
                continue
            if pod_filter != "All 3 Strategy Pods" and dlog.get("pod_id") != pod_filter:
                continue
            logs_by_date.setdefault(dt_k, []).append(dlog)

        all_dates_desc = sorted(logs_by_date.keys(), reverse=True)
        if activity_filter == "Days With New Orders Only":
            filtered_dates = [
                d
                for d in all_dates_desc
                if sum(len(p.get("executed_or_queued") or []) + len(p.get("ratchets_and_exits") or []) for p in logs_by_date[d]) > 0
            ]
        else:
            filtered_dates = all_dates_desc

        if not filtered_dates:
            st.caption("No journal sessions matched your current filter.")
        else:
            # Build concise date labels with order preview (e.g. 'Fri, Nov 13 · 7 orders (Latest)')
            date_labels: Dict[str, str] = {}
            for idx_d, d_key in enumerate(filtered_dates):
                d_pods = logs_by_date[d_key]
                ord_cnt = sum(len(p.get("executed_or_queued") or []) for p in d_pods)
                hold_cnt = sum(len(p.get("active_holdings_plan") or []) for p in d_pods)
                act_txt = f"{ord_cnt} order{'s' if ord_cnt != 1 else ''}" if ord_cnt > 0 else f"0 orders, {hold_cnt} held"
                latest_suffix = " · Latest" if idx_d == 0 else ""
                date_labels[d_key] = f"{_format_short_date(d_key)}  ·  {act_txt}{latest_suffix}"

            # Keep selected date synchronized across <- Previous / Next -> buttons and dropdown
            cur_sel_date = str(st.session_state.get("journal_selected_date") or "")
            if cur_sel_date not in filtered_dates:
                cur_sel_date = filtered_dates[0]
                st.session_state["journal_selected_date"] = cur_sel_date

            cur_idx = filtered_dates.index(cur_sel_date)

            nav1, nav2, nav3 = st.columns([0.42, 1.56, 0.42])
            with nav1:
                if st.button(
                    "← Previous",
                    use_container_width=True,
                    disabled=(cur_idx >= len(filtered_dates) - 1),
                    key="journal_prev_day_btn",
                ):
                    st.session_state["journal_selected_date"] = filtered_dates[cur_idx + 1]
                    st.rerun()
            with nav3:
                if st.button(
                    "Next →",
                    use_container_width=True,
                    disabled=(cur_idx <= 0),
                    key="journal_next_day_btn",
                ):
                    st.session_state["journal_selected_date"] = filtered_dates[cur_idx - 1]
                    st.rerun()
            with nav2:
                picked_date = st.selectbox(
                    "Trading Session",
                    options=filtered_dates,
                    index=cur_idx,
                    format_func=lambda d: date_labels.get(d, d),
                    key="journal_date_picker",
                    label_visibility="collapsed",
                )
                if picked_date != cur_sel_date:
                    st.session_state["journal_selected_date"] = picked_date
                    st.rerun()

            dt_key = str(st.session_state.get("journal_selected_date") or filtered_dates[0])
            if dt_key not in logs_by_date:
                dt_key = filtered_dates[0]
            day_pods = sorted(logs_by_date[dt_key], key=lambda x: str(x.get("pod_id", "")))

            # Aggregate unified activity across accounts for the selected day
            day_entries: List[Dict[str, Any]] = []
            day_ratchets: List[Dict[str, Any]] = []
            day_holds: List[Dict[str, Any]] = []
            day_notable_skips: List[Dict[str, Any]] = []
            day_quiet_skips_by_tkr: Dict[str, Dict[str, Any]] = {}

            for p_log in day_pods:
                pid = str(p_log.get("pod_id") or "")
                p_disp = POD_DISPLAY_NAMES.get(pid, pid)
                acct_str = str(p_log.get("alpaca_account_number") or "Paper")
                acct_tag = f"{p_disp} ({acct_str})"

                for e in p_log.get("executed_or_queued") or []:
                    item_e = dict(e)
                    item_e["_acct_tag"] = acct_tag
                    day_entries.append(item_e)

                for r_act in p_log.get("ratchets_and_exits") or []:
                    item_r = dict(r_act)
                    item_r["_acct_tag"] = acct_tag
                    day_ratchets.append(item_r)

                for h in p_log.get("active_holdings_plan") or []:
                    item_h = dict(h)
                    item_h["_acct_tag"] = acct_tag
                    day_holds.append(item_h)

                for s in p_log.get("skipped_reasons") or []:
                    if str(s.get("category", "")) != "NO_TECHNICAL_SIGNAL":
                        item_s = dict(s)
                        item_s["_acct_tag"] = p_disp
                        day_notable_skips.append(item_s)
                    else:
                        tkr_q = str(s.get("ticker") or "")
                        if tkr_q and tkr_q not in day_quiet_skips_by_tkr:
                            day_quiet_skips_by_tkr[tkr_q] = s

            # Sort filled orders ahead of working orders
            day_entries.sort(key=lambda x: (0 if "FILLED" in str(x.get("order_status") or "").upper() else 1, str(x.get("ticker") or "")))

            # 0. Concise 1-Sentence Daily Takeaway Header
            human_dt = _format_human_date(dt_key)
            takeaway_txt = _build_daily_takeaway(day_pods, pod_filter)
            st.markdown(
                f"<div class='md-surface' style='margin-top:8px;'>"
                f"<div style='display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;'>"
                f"<span style='font-size:0.98rem;font-weight:600;color:#f8fafc;'>{html.escape(human_dt)}</span>"
                f"<span style='font-size:0.76rem;color:#64748b;font-family:monospace;'>{html.escape(dt_key)}</span>"
                f"</div>"
                f"<div style='font-size:0.83rem;color:#cbd5e1;margin-top:6px;line-height:1.48;'>"
                f"{html.escape(takeaway_txt)}"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # 1. Unified New Orders & Fills
            st.markdown(
                f"<div style='font-size:0.86rem;font-weight:600;color:#e2e8f0;margin:14px 0 8px 0;'>"
                f"New Orders &amp; Fills ({len(day_entries)})</div>",
                unsafe_allow_html=True,
            )
            if day_entries:
                entry_rows_html: List[str] = []
                for idx_e, e in enumerate(day_entries):
                    e_side = str(e.get("side") or "LONG").upper()
                    e_act = "Sell Short" if e_side == "SHORT" else "Buy"
                    e_tkr = str(e.get("ticker") or "")
                    e_shs = int(e.get("shares") or 0)
                    e_lim = float(e.get("max_chase_price") or e.get("live_price") or e.get("reference_close_price") or 0.0)
                    e_stop = float(e.get("stop_loss_price") or 0.0)
                    e_tp = float(e.get("take_profit_price") or 0.0)
                    e_cost = float(e.get("estimated_cost_usd") or (e_shs * e_lim))
                    raw_st = str(e.get("order_status") or "")
                    e_stat = _plain_english_order_status(raw_st, e_lim)
                    st_color = "#22c55e" if "FILLED" in raw_st.upper() else "#cbd5e1"
                    e_why = _plain_english_reason(
                        str(e.get("technical_trigger") or ""),
                        side=e_side,
                        ai_sent=float(e.get("ai_catalyst_sentiment") or 0.0),
                    )
                    border_style = "border-top:1px solid rgba(255,255,255,0.06);padding-top:12px;margin-top:12px;" if idx_e > 0 else ""
                    entry_rows_html.append(
                        f"<div style='{border_style}'>"
                        f"<div style='display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;'>"
                        f"<div>"
                        f"<strong style='color:#f8fafc;font-size:0.93rem;'>{html.escape(e_tkr)}</strong>"
                        f"<span style='color:#94a3b8;font-size:0.82rem;margin-left:8px;'>{e_act} {e_shs} shares · ${e_cost:,.0f}</span>"
                        f"<span style='color:#64748b;font-size:0.77rem;margin-left:8px;'>· {html.escape(str(e.get('_acct_tag', '')))}</span>"
                        f"</div>"
                        f"<div style='font-size:0.81rem;font-weight:500;color:{st_color};font-variant-numeric:tabular-nums;'>{html.escape(e_stat)}</div>"
                        f"</div>"
                        f"<div style='font-size:0.79rem;color:#94a3b8;margin-top:4px;font-variant-numeric:tabular-nums;'>"
                        f"Entry limit ${e_lim:,.2f} &nbsp;·&nbsp; Stop-Loss ${e_stop:,.2f} &nbsp;·&nbsp; Profit Target ${e_tp:,.2f}"
                        f"</div>"
                        f"<div style='font-size:0.79rem;color:#8b95a5;margin-top:3px;line-height:1.42;'>{html.escape(e_why)}</div>"
                        f"</div>"
                    )
                st.markdown(f"<div class='md-surface'>{''.join(entry_rows_html)}</div>", unsafe_allow_html=True)
            else:
                st.markdown(
                    "<div class='md-surface' style='padding:12px 18px;font-size:0.81rem;color:#8b95a5;'>"
                    "No new entry orders were placed on this trading day."
                    "</div>",
                    unsafe_allow_html=True,
                )

            # 2. Stop-Loss Adjustments (shown only when non-empty)
            if day_ratchets:
                st.markdown(
                    f"<div style='font-size:0.86rem;font-weight:600;color:#e2e8f0;margin:14px 0 8px 0;'>"
                    f"Stop-Loss Adjustments ({len(day_ratchets)})</div>",
                    unsafe_allow_html=True,
                )
                r_lines = [
                    f"<div style='padding:6px 0;font-size:0.81rem;color:#cbd5e1;'>"
                    f"<strong style='color:#f8fafc;'>{html.escape(str(r.get('ticker', '')))}</strong> "
                    f"<span style='color:#64748b;'>({html.escape(str(r.get('_acct_tag', '')))})</span> — "
                    f"Stop-Loss moved from ${float(r.get('old_stop_price') or 0):,.2f} to "
                    f"${float(r.get('new_stop_price') or 0):,.2f} to protect gains."
                    f"</div>"
                    for r in day_ratchets
                ]
                st.markdown(f"<div class='md-surface' style='padding:10px 18px;'>{''.join(r_lines)}</div>", unsafe_allow_html=True)

            # 3. Compact Clean Positions Held Table
            st.markdown(
                f"<div style='font-size:0.86rem;font-weight:600;color:#e2e8f0;margin:14px 0 8px 0;'>"
                f"Positions Held ({len(day_holds)})</div>",
                unsafe_allow_html=True,
            )
            if day_holds:
                st.dataframe(
                    [
                        {
                            "Ticker": h.get("ticker", ""),
                            "Account": h.get("_acct_tag", ""),
                            "Shares": (
                                f"Short {abs(int(h.get('quantity') or h.get('qty') or 0))}"
                                if str(h.get("side") or "LONG").upper() == "SHORT"
                                else int(h.get("quantity") or h.get("qty") or 0)
                            ),
                            "Entry": f"${float(h.get('avg_entry_price') or 0):,.2f}",
                            "Day's Close": f"${float(h.get('current_price') or h.get('avg_entry_price') or 0):,.2f}",
                            "P&L %": f"{float(h.get('unrealised_return_pct') or 0.0):+.2f}%",
                            "Stop-Loss": f"${float(h.get('current_stop_price') or 0):,.2f}",
                            "Target": f"${float(h.get('take_profit_price') or 0):,.2f}",
                        }
                        for h in day_holds
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No open positions held at the end of this session.")

            # 4. Single Combined Quiet Expandable Footer for Skipped & Untriggered Stocks
            total_footer_items = len(day_notable_skips) + len(day_quiet_skips_by_tkr)
            if total_footer_items > 0:
                footer_lbl = (
                    f"Skipped setups ({len(day_notable_skips)}) & stocks not meeting entry criteria ({len(day_quiet_skips_by_tkr)})"
                    if day_notable_skips
                    else f"Stocks scanned that did not meet entry criteria ({len(day_quiet_skips_by_tkr)})"
                )
                with st.expander(footer_lbl, expanded=False):
                    if day_notable_skips:
                        st.markdown("**Skipped by Safety or Portfolio Rules**")
                        for nv in day_notable_skips:
                            st.markdown(
                                f"- **{nv.get('ticker', '')}** ({nv.get('_acct_tag', '')}): "
                                f"{_plain_english_skip_reason(str(nv.get('reason', '')), str(nv.get('status_badge', '')))}"
                            )
                    if day_quiet_skips_by_tkr:
                        st.dataframe(
                            [
                                {
                                    "Ticker": qs.get("ticker", ""),
                                    "Sector": qs.get("sector", ""),
                                    "Close": f"${float(qs.get('live_price') or 0):,.2f}",
                                    "Reason Not Triggered": qs.get("technical_summary") or qs.get("reason", ""),
                                }
                                for qs in sorted(day_quiet_skips_by_tkr.values(), key=lambda x: str(x.get("ticker") or ""))
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )

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
