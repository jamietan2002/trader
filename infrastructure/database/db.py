"""Persistent relational database manager for the Swing Trading AI Platform.

Supports SQLite out-of-the-box with zero compilation requirements and provides
compatible SQL schema definitions for PostgreSQL deployments.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


SCHEMA_SQL = """
-- 1. Stock Universe & Metadata
CREATE TABLE IF NOT EXISTS equities_universe (
    ticker TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    exchange TEXT NOT NULL,
    sector TEXT NOT NULL,
    industry TEXT NOT NULL,
    market_cap_usd REAL NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    delisted_date TEXT,
    updated_at TEXT NOT NULL
);

-- 2. Historical Daily OHLCV Bars (Point-in-time & Split/Dividend Adjusted)
CREATE TABLE IF NOT EXISTS market_bars_daily (
    ticker TEXT NOT NULL,
    bar_date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    adj_open REAL NOT NULL,
    adj_high REAL NOT NULL,
    adj_low REAL NOT NULL,
    adj_close REAL NOT NULL,
    adj_volume REAL NOT NULL,
    split_factor REAL NOT NULL DEFAULT 1.0,
    dividend_amount REAL NOT NULL DEFAULT 0.0,
    provider_source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (ticker, bar_date)
);

CREATE INDEX IF NOT EXISTS idx_market_bars_date ON market_bars_daily(bar_date);

-- 3. Point-in-Time Fundamentals & Earnings Events
CREATE TABLE IF NOT EXISTS earnings_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    report_date TEXT NOT NULL,
    fiscal_period TEXT NOT NULL,
     announcement_session TEXT NOT NULL DEFAULT 'AMC', -- BMO or AMC
    eps_estimate REAL,
    eps_actual REAL,
    eps_surprise_pct REAL,
    revenue_estimate_M REAL,
    revenue_actual_M REAL,
    revenue_growth_yoy_pct REAL,
    guidance_delta_pct REAL,
    public_release_timestamp TEXT NOT NULL,
    provider_source TEXT NOT NULL,
    UNIQUE(ticker, report_date)
);

-- 4. Financial News & SEC Filings (Point-in-time)
CREATE TABLE IF NOT EXISTS market_catalysts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    published_date TEXT NOT NULL,
    published_timestamp TEXT NOT NULL,
    catalyst_type TEXT NOT NULL, -- NEWS | SEC_10K | SEC_10Q | SEC_8K | ANALYST
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    sentiment_score REAL NOT NULL,
    source_name TEXT NOT NULL,
    url TEXT
);

-- 5. Market Research Reports
CREATE TABLE IF NOT EXISTS research_reports (
    report_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    company_name TEXT NOT NULL,
    current_price REAL NOT NULL,
    sector TEXT NOT NULL,
    composite_rank_score REAL NOT NULL,
    research_confidence_score REAL NOT NULL,
    suggested_strategy_family TEXT NOT NULL,
    potential_holding_days_min INTEGER NOT NULL,
    potential_holding_days_max INTEGER NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 6. Strategy Registry (Immutable Versioned Strategies)
CREATE TABLE IF NOT EXISTS strategy_registry (
    strategy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    strategy_family TEXT NOT NULL,
    status TEXT NOT NULL, -- DRAFT | BACKTESTING | VALIDATION | PAPER_TRADING | APPROVED_FOR_REVIEW | REJECTED | RETIRED
    hypothesis TEXT NOT NULL,
    observable_phenomenon TEXT NOT NULL,
    invalidation_conditions TEXT NOT NULL,
    target_market_regimes TEXT NOT NULL,
    holding_period_min_days INTEGER NOT NULL,
    holding_period_max_days INTEGER NOT NULL,
    universe_json TEXT NOT NULL,
    indicators_json TEXT NOT NULL,
    entry_rules_json TEXT NOT NULL,
    exit_rules_json TEXT NOT NULL,
    risk_params_json TEXT NOT NULL,
    backtest_summary_json TEXT,
    validation_summary_json TEXT,
    promotion_decision_reason TEXT,
    dataset_version TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (strategy_id, version)
);

-- 7. Strategy Experiment & Audit History
CREATE TABLE IF NOT EXISTS strategy_experiments (
    experiment_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    experiment_type TEXT NOT NULL, -- IN_SAMPLE | VALIDATION | OUT_OF_SAMPLE | WALK_FORWARD | STRESS_TEST
    dataset_version TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    equity_curve_json TEXT NOT NULL,
    trades_json TEXT NOT NULL,
    evaluation_report_json TEXT,
    passed_promotion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- 8. Paper Trading Account State
CREATE TABLE IF NOT EXISTS paper_accounts (
    account_id TEXT PRIMARY KEY,
    trading_mode TEXT NOT NULL CHECK (trading_mode = 'paper'),
    base_currency TEXT NOT NULL DEFAULT 'USD',
    starting_cash REAL NOT NULL,
    cash_balance REAL NOT NULL,
    realised_pnl REAL NOT NULL DEFAULT 0.0,
    peak_equity REAL NOT NULL,
    kill_switch_engaged INTEGER NOT NULL DEFAULT 0,
    kill_switch_reason TEXT,
    updated_at TEXT NOT NULL
);

-- 9. Paper Trading Open Positions
CREATE TABLE IF NOT EXISTS paper_positions (
    account_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    strategy_version INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    avg_entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    stop_loss_price REAL,
    take_profit_price REAL,
    highest_price_since_entry REAL NOT NULL,
    opened_date TEXT NOT NULL,
    holding_days INTEGER NOT NULL DEFAULT 0,
    sector TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, ticker)
);

-- 10. Paper Trading Orders (with Idempotency Key to prevent duplicates)
CREATE TABLE IF NOT EXISTS paper_orders (
    order_id TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    account_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    strategy_version INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL, -- BUY | SELL
    order_type TEXT NOT NULL, -- MARKET | LIMIT | STOP_LOSS | TAKE_PROFIT
    requested_qty INTEGER NOT NULL,
    filled_qty INTEGER NOT NULL DEFAULT 0,
    limit_price REAL,
    stop_price REAL,
    avg_fill_price REAL,
    commission_usd REAL NOT NULL DEFAULT 0.0,
    slippage_usd REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL, -- PENDING | PARTIALLY_FILLED | FILLED | REJECTED | CANCELLED
    rejection_reason TEXT,
    signal_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 11. Permanent Trade Ledger (Completed & Partial Executions)
CREATE TABLE IF NOT EXISTS trade_ledger (
    ledger_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    strategy_version INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    fill_date TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    fill_price REAL NOT NULL,
    gross_amount REAL NOT NULL,
    commission_usd REAL NOT NULL,
    slippage_usd REAL NOT NULL,
    realised_pnl REAL NOT NULL DEFAULT 0.0,
    cash_after REAL NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);

-- 12. Daily Portfolio Valuation History
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    account_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    cash_balance REAL NOT NULL,
    positions_market_value REAL NOT NULL,
    total_equity REAL NOT NULL,
    daily_return_pct REAL NOT NULL,
    cumulative_return_pct REAL NOT NULL,
    drawdown_pct REAL NOT NULL,
    benchmark_price REAL,
    benchmark_cum_return_pct REAL,
    open_positions_count INTEGER NOT NULL,
    realised_pnl REAL NOT NULL,
    unrealised_pnl REAL NOT NULL,
    sector_exposures_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (account_id, snapshot_date)
);

-- 13. Risk Alerts & Veto Audit Log
CREATE TABLE IF NOT EXISTS risk_alerts (
    alert_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    alert_date TEXT NOT NULL,
    severity TEXT NOT NULL, -- INFO | WARNING | CRITICAL_VETO | KILL_SWITCH
    rule_name TEXT NOT NULL,
    ticker TEXT,
    strategy_id TEXT,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 14. Performance Analyst Proposals
CREATE TABLE IF NOT EXISTS experiment_proposals (
    proposal_id TEXT PRIMARY KEY,
    session_date TEXT NOT NULL,
    target_strategy_id TEXT,
    identified_weakness TEXT NOT NULL,
    market_regime TEXT NOT NULL,
    proposed_hypothesis TEXT NOT NULL,
    proposed_changes_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    created_at TEXT NOT NULL
);

-- 15. Job Execution & Agent Audit Logs
CREATE TABLE IF NOT EXISTS job_executions (
    job_run_id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL, -- RUNNING | COMPLETED | FAILED
    started_at TEXT NOT NULL,
    completed_at TEXT,
    summary_json TEXT,
    error_message TEXT
);

-- 16. API Response Cache
CREATE TABLE IF NOT EXISTS api_cache (
    cache_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DatabaseManager:
    """Thread-safe SQLite/PostgreSQL-compatible relational store."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA_SQL)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connection() as conn:
            conn.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: List[tuple[Any, ...]]) -> None:
        with self.connection() as conn:
            conn.executemany(sql, seq_of_params)

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            cur = conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row is not None else None

    def get_cached_response(self, cache_key: str) -> Optional[Any]:
        now = utc_now_iso()
        row = self.fetch_one(
            "SELECT payload_json FROM api_cache WHERE cache_key = ? AND expires_at > ?",
            (cache_key, now),
        )
        if row:
            return json.loads(row["payload_json"])
        return None

    def set_cached_response(
        self, cache_key: str, provider: str, payload: Any, expires_at_iso: str
    ) -> None:
        self.execute(
            """
            INSERT INTO api_cache (cache_key, provider, payload_json, retrieved_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload_json = excluded.payload_json,
                retrieved_at = excluded.retrieved_at,
                expires_at = excluded.expires_at
            """,
            (cache_key, provider, json.dumps(payload), utc_now_iso(), expires_at_iso),
        )

