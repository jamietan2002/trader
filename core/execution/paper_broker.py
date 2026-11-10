"""Paper Trading Execution Engine & Simulated Brokerage Account.

Responsibilities:
- Manage a $100,000 USD virtual paper brokerage account (`TRADING_MODE=paper` strictly enforced).
- Support Market, Limit, Stop-Loss, and Take-Profit orders, plus partial fills when order size
  exceeds a configurable fraction of daily bar volume.
- Prevent duplicate orders via deterministic `idempotency_key` enforcement.
- Maintain open positions, available cash, buying power, realised & unrealised P&L, corporate actions
  (dividends/splits), daily portfolio snapshots, and a permanent immutable `trade_ledger`.
- Never allow AI agents to directly mutate account balances or bypass `PortfolioRiskManager`.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from core.indicators.technical import compute_indicator_series
from core.market_data.models import DailyBar, USTradingCalendar
from core.market_data.providers import MarketDataService
from core.risk.manager import PortfolioRiskManager
from core.strategies.registry import StrategyConfig, StrategySignalEngine
from infrastructure.configuration.settings import LiveTradingProhibitedError, Settings
from infrastructure.database.db import DatabaseManager, utc_now_iso
from infrastructure.logging.logger import get_logger

logger = get_logger("core.execution.paper")


@dataclass
class OrderSubmissionResult:
    order_id: str
    idempotency_key: str
    status: str  # FILLED | PARTIALLY_FILLED | PENDING | REJECTED | DUPLICATE_IGNORED
    filled_qty: int
    avg_fill_price: Optional[float]
    commission_usd: float
    slippage_usd: float
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PaperTradingEngine:
    """Deterministic simulated brokerage and portfolio accounting engine."""

    DEFAULT_ACCOUNT_ID = "paper_main_100k"

    def __init__(
        self,
        settings: Settings,
        db: DatabaseManager,
        market_data: MarketDataService,
        risk_manager: Optional[PortfolioRiskManager] = None,
        account_id: str = DEFAULT_ACCOUNT_ID,
    ) -> None:
        settings.validate_trading_mode()
        self.settings = settings
        self.db = db
        self.market_data = market_data
        self.risk_manager = risk_manager or PortfolioRiskManager(settings.risk, db=db)
        self.account_id = account_id
        self.ensure_account_initialized()

    def ensure_account_initialized(self) -> Dict[str, Any]:
        """Initialize the $100,000 USD paper account if it does not yet exist."""
        self.settings.validate_trading_mode()
        existing = self.db.fetch_one(
            "SELECT * FROM paper_accounts WHERE account_id = ?", (self.account_id,)
        )
        if existing is not None:
            return existing

        now_iso = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO paper_accounts (
                account_id, trading_mode, base_currency, starting_cash,
                cash_balance, realised_pnl, peak_equity,
                kill_switch_engaged, kill_switch_reason, updated_at
            ) VALUES (?, 'paper', ?, ?, ?, 0.0, ?, 0, NULL, ?)
            """,
            (
                self.account_id,
                self.settings.base_currency,
                self.settings.initial_capital_usd,
                self.settings.initial_capital_usd,
                self.settings.initial_capital_usd,
                now_iso,
            ),
        )
        acc = self.db.fetch_one(
            "SELECT * FROM paper_accounts WHERE account_id = ?", (self.account_id,)
        )
        assert acc is not None
        return acc

    @staticmethod
    def build_idempotency_key(
        account_id: str,
        strategy_id: str,
        strategy_version: int,
        ticker: str,
        side: str,
        signal_date: str,
        order_type: str = "MARKET",
    ) -> str:
        raw = f"{account_id}:{strategy_id}:v{strategy_version}:{ticker}:{side.upper()}:{signal_date}:{order_type.upper()}"
        return f"idem_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"

    def get_account_summary(self) -> Dict[str, Any]:
        """Return reconciled cash, positions market value, total equity, buying power, and P&L."""
        acc = self.ensure_account_initialized()
        positions = self.get_open_positions()
        positions_mv = sum(
            int(p["quantity"]) * float(p["current_price"]) for p in positions
        )
        unrealised_pnl = sum(
            int(p["quantity"]) * (float(p["current_price"]) - float(p["avg_entry_price"]))
            for p in positions
        )
        cash = float(acc["cash_balance"])
        starting_cash = float(acc["starting_cash"])
        total_equity = cash + positions_mv
        peak_equity = max(float(acc["peak_equity"]), total_equity)
        drawdown_pct = ((peak_equity - total_equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
        total_pnl_usd = total_equity - starting_cash
        total_return_pct = ((total_equity / starting_cash) - 1.0) * 100.0 if starting_cash > 0 else 0.0

        # Daily & Weekly (5-session) P&L from forward portfolio snapshots
        snap_rows = self.db.fetch_all(
            "SELECT snapshot_date, total_equity FROM portfolio_snapshots WHERE account_id = ? ORDER BY snapshot_date ASC",
            (self.account_id,),
        )
        if len(snap_rows) >= 2:
            prev_day_eq = float(snap_rows[-2]["total_equity"])
        elif len(snap_rows) == 1:
            prev_day_eq = starting_cash
        else:
            prev_day_eq = total_equity
        daily_pnl_usd = total_equity - prev_day_eq
        daily_return_pct = ((total_equity / prev_day_eq) - 1.0) * 100.0 if prev_day_eq > 0 else 0.0

        if len(snap_rows) >= 6:
            prev_week_eq = float(snap_rows[-6]["total_equity"])
        elif len(snap_rows) >= 1:
            prev_week_eq = starting_cash
        else:
            prev_week_eq = total_equity
        weekly_pnl_usd = total_equity - prev_week_eq
        weekly_return_pct = ((total_equity / prev_week_eq) - 1.0) * 100.0 if prev_week_eq > 0 else 0.0

        # Sector exposures
        sector_totals: Dict[str, float] = {}
        for p in positions:
            sec = p["sector"]
            val = int(p["quantity"]) * float(p["current_price"])
            sector_totals[sec] = sector_totals.get(sec, 0.0) + val
        sector_exposures_pct = {
            sec: round((val / total_equity) * 100.0, 2) if total_equity > 0 else 0.0
            for sec, val in sector_totals.items()
        }

        return {
            "account_id": self.account_id,
            "trading_mode": acc["trading_mode"],
            "base_currency": acc["base_currency"],
            "starting_capital": round(starting_cash, 2),
            "cash_balance": round(cash, 2),
            "buying_power": round(cash, 2),  # 1x cash account (no risky margin amplification)
            "positions_market_value": round(positions_mv, 2),
            "total_equity": round(total_equity, 2),
            "total_pnl_usd": round(total_pnl_usd, 2),
            "total_return_pct": round(total_return_pct, 2),
            "daily_pnl_usd": round(daily_pnl_usd, 2),
            "daily_return_pct": round(daily_return_pct, 2),
            "weekly_pnl_usd": round(weekly_pnl_usd, 2),
            "weekly_return_pct": round(weekly_return_pct, 2),
            "realised_pnl": round(float(acc["realised_pnl"]), 2),
            "unrealised_pnl": round(unrealised_pnl, 2),
            "peak_equity": round(peak_equity, 2),
            "current_drawdown_pct": round(drawdown_pct, 2),
            "open_positions_count": len(positions),
            "kill_switch_engaged": bool(acc["kill_switch_engaged"]),
            "kill_switch_reason": acc["kill_switch_reason"],
            "sector_exposures_pct": sector_exposures_pct,
            "updated_at": acc["updated_at"],
        }

    def refresh_live_positions_mark_to_market(self, cache_ttl_seconds: int = 30) -> Dict[str, float]:
        """Fetch live Alpaca snapshot quotes and update current_price & highest_price_since_entry on open positions."""
        import sys as _sys

        if "unittest" in _sys.modules or not hasattr(self.market_data, "fetch_live_quote_snapshots"):
            return {}
        rows = self.db.fetch_all(
            "SELECT ticker, current_price, highest_price_since_entry FROM paper_positions WHERE account_id = ?",
            (self.account_id,),
        )
        if not rows:
            return {}
        tickers = [str(r["ticker"]).upper() for r in rows]
        quotes = self.market_data.fetch_live_quote_snapshots(tickers, cache_ttl_seconds=cache_ttl_seconds) or {}
        if not quotes:
            return {}
        now_iso = utc_now_iso()
        updated_prices: Dict[str, float] = {}
        for r in rows:
            tkr = str(r["ticker"]).upper()
            q = quotes.get(tkr)
            if not q:
                continue
            live_p = float(q.get("latest_trade_price") or q.get("indicative_price") or 0.0)
            if live_p <= 0:
                continue
            d_high = float(q.get("daily_high") or live_p)
            new_high = max(float(r["highest_price_since_entry"]), live_p, d_high)
            self.db.execute(
                """
                UPDATE paper_positions
                SET current_price = ?, highest_price_since_entry = ?, updated_at = ?
                WHERE account_id = ? AND ticker = ?
                """,
                (round(live_p, 4), round(new_high, 4), now_iso, self.account_id, r["ticker"]),
            )
            updated_prices[tkr] = round(live_p, 4)
        return updated_prices

    def get_open_positions(self) -> List[Dict[str, Any]]:
        self.refresh_live_positions_mark_to_market(cache_ttl_seconds=30)
        rows = self.db.fetch_all(
            "SELECT * FROM paper_positions WHERE account_id = ? ORDER BY ticker ASC",
            (self.account_id,),
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            qty = int(r["quantity"])
            entry = float(r["avg_entry_price"])
            curr = float(r["current_price"])
            item["market_value"] = round(qty * curr, 2)
            item["unrealised_pnl"] = round(qty * (curr - entry), 2)
            item["unrealised_return_pct"] = round(((curr / entry) - 1.0) * 100.0, 2) if entry > 0 else 0.0
            out.append(item)
        return out

    def get_orders(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if status:
            return self.db.fetch_all(
                "SELECT * FROM paper_orders WHERE account_id = ? AND status = ? ORDER BY created_at DESC LIMIT ?",
                (self.account_id, status, limit),
            )
        return self.db.fetch_all(
            "SELECT * FROM paper_orders WHERE account_id = ? ORDER BY created_at DESC LIMIT ?",
            (self.account_id, limit),
        )

    def get_trade_ledger(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.db.fetch_all(
            "SELECT * FROM trade_ledger WHERE account_id = ? ORDER BY fill_date DESC, created_at DESC LIMIT ?",
            (self.account_id, limit),
        )

    def get_portfolio_snapshots(self) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM portfolio_snapshots WHERE account_id = ? ORDER BY snapshot_date ASC",
            (self.account_id,),
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["sector_exposures"] = json.loads(r["sector_exposures_json"])
            out.append(d)
        return out

    def set_kill_switch(self, engaged: bool, reason: str = "") -> None:
        self.db.execute(
            """
            UPDATE paper_accounts
            SET kill_switch_engaged = ?, kill_switch_reason = ?, updated_at = ?
            WHERE account_id = ?
            """,
            (1 if engaged else 0, reason if engaged else None, utc_now_iso(), self.account_id),
        )

    def get_strategy_account_engine(self, strategy_id: str) -> "PaperTradingEngine":
        """Return an isolated $100,000 PaperTradingEngine instance dedicated to a single strategy sleeve."""
        clean_id = str(strategy_id).strip()
        acc_id = clean_id if clean_id.startswith("paper_") else f"paper_{clean_id}"
        return PaperTradingEngine(
            settings=self.settings,
            db=self.db,
            market_data=self.market_data,
            risk_manager=self.risk_manager,
            account_id=acc_id,
        )

    def get_all_paper_accounts_summary(self, strategies: Sequence[Any]) -> List[Dict[str, Any]]:
        """Return account summaries + trade stats for the Master $100k account and each strategy's dedicated $100k account."""
        best_by_sid: Dict[str, Tuple[str, str, int, int]] = {}
        for s in strategies:
            sid = s.strategy_id if hasattr(s, "strategy_id") else str(s.get("strategy_id", ""))
            if not sid:
                continue
            sname = s.name if hasattr(s, "name") else str(s.get("name", sid))
            sver = int(s.version if hasattr(s, "version") else s.get("version", 1))
            status = s.status if hasattr(s, "status") else str(s.get("status", "PAPER_TRADING"))
            prio = 2 if status == "PAPER_TRADING" else (1 if status == "APPROVED_FOR_REVIEW" else 0)
            prev = best_by_sid.get(sid)
            if prev is None or (prio, sver) > (prev[3], prev[2]):
                best_by_sid[sid] = (sid, sname, sver, prio)

        seen_sids: List[Tuple[str, str, int]] = [
            (sid, sname, sver) for sid, sname, sver, _ in sorted(best_by_sid.values(), key=lambda x: x[0])
        ]

        accounts_to_check: List[Tuple[str, str, str]] = [
            (self.DEFAULT_ACCOUNT_ID, "Master Combined Portfolio ($100k — All Active Strategies)", "ALL_ACTIVE")
        ]
        for sid, sname, sver in seen_sids:
            accounts_to_check.append((f"paper_{sid}", f"{sname} ({sid} v{sver} — Dedicated $100k)", sid))

        rows: List[Dict[str, Any]] = []
        for acc_id, label, strat_key in accounts_to_check:
            eng = (
                self
                if acc_id == self.account_id
                else PaperTradingEngine(self.settings, self.db, self.market_data, self.risk_manager, account_id=acc_id)
            )
            summ = eng.get_account_summary()
            led = eng.get_trade_ledger(limit=500)
            sells = [l for l in led if l.get("side") == "SELL"]
            wins = [l for l in sells if float(l.get("realised_pnl", 0.0)) > 0]
            losses = [l for l in sells if float(l.get("realised_pnl", 0.0)) <= 0]
            wr = (len(wins) / len(sells) * 100.0) if sells else 0.0
            gp = sum(float(l.get("realised_pnl", 0.0)) for l in wins)
            gl = abs(sum(float(l.get("realised_pnl", 0.0)) for l in losses))
            pf = (gp / gl) if gl > 1e-9 else (2.5 if gp > 0 else 0.0)
            is_master = acc_id == self.DEFAULT_ACCOUNT_ID
            rows.append(
                {
                    "account_id": acc_id,
                    "label": label,
                    "book_label": label,
                    "book_type": "MASTER_COMBINED" if is_master else "STRATEGY_DEDICATED",
                    "strategy_id": strat_key,
                    "total_equity": summ["total_equity"],
                    "starting_capital": summ["starting_capital"],
                    "cash_balance": summ["cash_balance"],
                    "daily_pnl_usd": summ["daily_pnl_usd"],
                    "daily_return_pct": summ["daily_return_pct"],
                    "weekly_pnl_usd": summ["weekly_pnl_usd"],
                    "weekly_return_pct": summ["weekly_return_pct"],
                    "total_pnl": summ["total_pnl_usd"],
                    "total_pnl_usd": summ["total_pnl_usd"],
                    "total_return_pct": summ["total_return_pct"],
                    "realised_pnl": summ["realised_pnl"],
                    "unrealised_pnl": summ["unrealised_pnl"],
                    "open_positions_count": summ["open_positions_count"],
                    "closed_sells": len(sells),
                    "closed_trades_count": len(sells),
                    "total_fills": len(led),
                    "total_fills_count": len(led),
                    "win_rate_pct": round(wr, 1),
                    "profit_factor": round(pf, 2),
                    "current_drawdown_pct": summ["current_drawdown_pct"],
                }
            )
        return rows

    def reset_account_to_starting_capital(self, reset_strategy_accounts: bool = True) -> Dict[str, Any]:
        """Reset paper account cash, positions, orders, snapshots, and alerts to a clean $100,000 state."""
        self.settings.validate_trading_mode()
        now_iso = utc_now_iso()
        if self.account_id == self.DEFAULT_ACCOUNT_ID and reset_strategy_accounts:
            self.db.execute("DELETE FROM paper_positions WHERE account_id LIKE 'paper_%'")
            self.db.execute("DELETE FROM paper_orders WHERE account_id LIKE 'paper_%'")
            self.db.execute("DELETE FROM trade_ledger WHERE account_id LIKE 'paper_%'")
            self.db.execute("DELETE FROM portfolio_snapshots WHERE account_id LIKE 'paper_%'")
            self.db.execute("DELETE FROM risk_alerts WHERE account_id LIKE 'paper_%'")
            self.db.execute("DELETE FROM job_executions WHERE job_name = 'daily_market_execution'")
            self.db.execute(
                """
                UPDATE paper_accounts
                SET cash_balance = ?, realised_pnl = 0.0, peak_equity = ?,
                    kill_switch_engaged = 0, kill_switch_reason = NULL, updated_at = ?
                WHERE account_id LIKE 'paper_%'
                """,
                (
                    self.settings.initial_capital_usd,
                    self.settings.initial_capital_usd,
                    now_iso,
                ),
            )
            return self.get_account_summary()

        self.db.execute("DELETE FROM paper_positions WHERE account_id = ?", (self.account_id,))
        self.db.execute("DELETE FROM paper_orders WHERE account_id = ?", (self.account_id,))
        self.db.execute("DELETE FROM trade_ledger WHERE account_id = ?", (self.account_id,))
        self.db.execute("DELETE FROM portfolio_snapshots WHERE account_id = ?", (self.account_id,))
        self.db.execute("DELETE FROM risk_alerts WHERE account_id = ?", (self.account_id,))
        self.db.execute(
            """
            UPDATE paper_accounts
            SET cash_balance = ?, realised_pnl = 0.0, peak_equity = ?,
                kill_switch_engaged = 0, kill_switch_reason = NULL, updated_at = ?
            WHERE account_id = ?
            """,
            (
                self.settings.initial_capital_usd,
                self.settings.initial_capital_usd,
                now_iso,
                self.account_id,
            ),
        )
        return self.get_account_summary()

    def submit_and_execute_order(
        self,
        strategy_id: str,
        strategy_version: int,
        strategy_family: str,
        ticker: str,
        side: str,  # BUY | SELL
        requested_qty: int,
        signal_date: str,
        execution_bar: DailyBar,
        sector: str = "Technology",
        order_type: str = "MARKET",  # MARKET | LIMIT | STOP_LOSS | TAKE_PROFIT
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        stop_loss_target: Optional[float] = None,
        take_profit_target: Optional[float] = None,
        atr_14: float = 2.0,
        idempotency_key: Optional[str] = None,
        max_volume_participation_pct: float = 0.05,
        notes: str = "",
        avg_daily_dollar_volume_20d: Optional[float] = None,
        upcoming_earnings_days: Optional[int] = None,
        candidate_returns_20d: Optional[Sequence[float]] = None,
        open_positions_returns_20d: Optional[Dict[str, Sequence[float]]] = None,
        strategy_risk_pct: Optional[float] = None,
        strategy_max_exp_pct: Optional[float] = None,
    ) -> OrderSubmissionResult:
        """Submit and simulate an order with duplicate prevention, risk checks, and ledger accounting."""
        self.settings.validate_trading_mode()
        side_u = side.upper()
        order_type_u = order_type.upper()

        idem_key = idempotency_key or self.build_idempotency_key(
            self.account_id, strategy_id, strategy_version, ticker, side_u, signal_date, order_type_u
        )

        # 1. Duplicate Order Check via Idempotency Key
        existing_order = self.db.fetch_one(
            "SELECT * FROM paper_orders WHERE idempotency_key = ?", (idem_key,)
        )
        if existing_order is not None:
            logger.info(f"Duplicate order prevented via idempotency_key={idem_key}")
            return OrderSubmissionResult(
                order_id=existing_order["order_id"],
                idempotency_key=idem_key,
                status="DUPLICATE_IGNORED",
                filled_qty=int(existing_order["filled_qty"]),
                avg_fill_price=float(existing_order["avg_fill_price"]) if existing_order["avg_fill_price"] else None,
                commission_usd=float(existing_order["commission_usd"]),
                slippage_usd=float(existing_order["slippage_usd"]),
                rejection_reason="Duplicate order prevented by idempotency key",
            )

        order_id = f"ord_{uuid.uuid4().hex[:12]}"
        now_iso = utc_now_iso()

        # 2. Determine base trigger/execution price according to order_type
        raw_price = execution_bar.adj_open
        if order_type_u == "LIMIT":
            if limit_price is None:
                return self._record_rejected_order(
                    order_id, idem_key, strategy_id, strategy_version, ticker, side_u,
                    order_type_u, requested_qty, limit_price, stop_price, signal_date,
                    "Limit order missing limit_price",
                )
            if side_u == "BUY":
                if execution_bar.adj_low > limit_price:
                    return self._record_pending_order(
                        order_id, idem_key, strategy_id, strategy_version, ticker, side_u,
                        order_type_u, requested_qty, limit_price, stop_price, signal_date,
                    )
                raw_price = min(execution_bar.adj_open, limit_price)
            else:
                if execution_bar.adj_high < limit_price:
                    return self._record_pending_order(
                        order_id, idem_key, strategy_id, strategy_version, ticker, side_u,
                        order_type_u, requested_qty, limit_price, stop_price, signal_date,
                    )
                raw_price = max(execution_bar.adj_open, limit_price)

        elif order_type_u == "STOP_LOSS":
            if stop_price is None or execution_bar.adj_low > stop_price:
                return self._record_pending_order(
                    order_id, idem_key, strategy_id, strategy_version, ticker, side_u,
                    order_type_u, requested_qty, limit_price, stop_price, signal_date,
                )
            raw_price = min(execution_bar.adj_open, stop_price)

        elif order_type_u == "TAKE_PROFIT":
            target_p = limit_price or stop_price
            if target_p is None or execution_bar.adj_high < target_p:
                return self._record_pending_order(
                    order_id, idem_key, strategy_id, strategy_version, ticker, side_u,
                    order_type_u, requested_qty, limit_price, stop_price, signal_date,
                )
            raw_price = max(execution_bar.adj_open, target_p)

        # 3. For BUY orders, run authoritative PortfolioRiskManager validation
        summary = self.get_account_summary()
        open_pos_map = {p["ticker"]: p for p in self.get_open_positions()}

        if side_u == "BUY":
            if requested_qty <= 0:
                return self._record_rejected_order(
                    order_id, idem_key, strategy_id, strategy_version, ticker, side_u,
                    order_type_u, requested_qty, limit_price, stop_price, signal_date,
                    "Requested BUY quantity must be positive",
                )
            decision = self.risk_manager.evaluate_proposed_entry(
                account_id=self.account_id,
                eval_date=execution_bar.bar_date,
                ticker=ticker,
                sector=sector,
                strategy_id=strategy_id,
                strategy_family=strategy_family,
                entry_price=raw_price,
                stop_loss_price=stop_loss_target,
                atr_14=atr_14,
                portfolio_equity=summary["total_equity"],
                peak_equity=summary["peak_equity"],
                available_cash=summary["cash_balance"],
                open_positions=open_pos_map,
                avg_daily_dollar_volume_20d=avg_daily_dollar_volume_20d,
                upcoming_earnings_days=upcoming_earnings_days,
                candidate_returns_20d=candidate_returns_20d,
                open_positions_returns_20d=open_positions_returns_20d,
                kill_switch_engaged=summary["kill_switch_engaged"],
                strategy_risk_pct=strategy_risk_pct,
                strategy_max_exp_pct=strategy_max_exp_pct,
            )
            if not decision.approved:
                if decision.rule_triggered == "MAX_DRAWDOWN_SUSPENSION":
                    self.set_kill_switch(True, decision.veto_reason or "Max drawdown breached")
                return self._record_rejected_order(
                    order_id, idem_key, strategy_id, strategy_version, ticker, side_u,
                    order_type_u, requested_qty, limit_price, stop_price, signal_date,
                    decision.veto_reason or "Rejected by PortfolioRiskManager",
                )
            # Cap quantity to risk-approved shares if caller requested more
            approved_qty = min(requested_qty, decision.recommended_shares)
        else:
            if ticker not in open_pos_map:
                return self._record_rejected_order(
                    order_id, idem_key, strategy_id, strategy_version, ticker, side_u,
                    order_type_u, requested_qty, limit_price, stop_price, signal_date,
                    f"Cannot SELL {ticker}: no open position found",
                )
            approved_qty = min(requested_qty, int(open_pos_map[ticker]["quantity"]))

        # 4. Partial fill check against daily volume participation limit
        max_liquidity_shares = max(1, int(execution_bar.adj_volume * max_volume_participation_pct))
        filled_qty = min(approved_qty, max_liquidity_shares)
        order_status = "FILLED" if filled_qty == approved_qty else "PARTIALLY_FILLED"

        # 5. Compute realistic spread, slippage, and commission
        half_spread_pct = self.settings.costs.default_half_spread_bps / 10_000.0
        slippage_pct = self.settings.costs.default_slippage_bps / 10_000.0
        friction_pct = half_spread_pct + slippage_pct

        if side_u == "BUY":
            fill_price = round(raw_price * (1.0 + friction_pct), 4)
        else:
            fill_price = round(max(0.01, raw_price * (1.0 - friction_pct)), 4)

        slippage_usd = round(abs(fill_price - raw_price) * filled_qty, 2)
        commission_usd = max(
            self.settings.costs.min_commission_per_order,
            filled_qty * self.settings.costs.commission_per_share,
        )
        if side_u == "SELL":
            commission_usd += (filled_qty * fill_price) * self.settings.costs.sec_fee_per_dollar_sold
        commission_usd = round(commission_usd, 2)

        gross_amount = round(filled_qty * fill_price, 2)
        cash_before = float(summary["cash_balance"])
        realised_pnl_delta = 0.0

        if side_u == "BUY":
            total_Cost = gross_amount + commission_usd
            if total_Cost > cash_before:
                filled_qty = int((cash_before - commission_usd) // fill_price)
                if filled_qty <= 0:
                    return self._record_rejected_order(
                        order_id, idem_key, strategy_id, strategy_version, ticker, side_u,
                        order_type_u, requested_qty, limit_price, stop_price, signal_date,
                        "Insufficient cash after transaction costs",
                    )
                gross_amount = round(filled_qty * fill_price, 2)
                total_Cost = gross_amount + commission_usd
            cash_after = round(cash_before - total_Cost, 2)

            self.db.execute(
                """
                INSERT INTO paper_positions (
                    account_id, ticker, strategy_id, strategy_version,
                    quantity, avg_entry_price, current_price,
                    stop_loss_price, take_profit_price, highest_price_since_entry,
                    opened_date, holding_days, sector, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(account_id, ticker) DO UPDATE SET
                    avg_entry_price = ROUND(
                        ((paper_positions.quantity * paper_positions.avg_entry_price) + (excluded.quantity * excluded.avg_entry_price))
                        / (paper_positions.quantity + excluded.quantity),
                        4
                    ),
                    quantity = paper_positions.quantity + excluded.quantity,
                    current_price = excluded.current_price,
                    stop_loss_price = COALESCE(excluded.stop_loss_price, paper_positions.stop_loss_price),
                    take_profit_price = COALESCE(excluded.take_profit_price, paper_positions.take_profit_price),
                    highest_price_since_entry = MAX(paper_positions.highest_price_since_entry, excluded.highest_price_since_entry),
                    updated_at = excluded.updated_at
                """,
                (
                    self.account_id,
                    ticker,
                    strategy_id,
                    strategy_version,
                    filled_qty,
                    fill_price,
                    execution_bar.adj_close,
                    stop_loss_target,
                    take_profit_target,
                    max(fill_price, execution_bar.adj_high),
                    execution_bar.bar_date,
                    sector,
                    now_iso,
                ),
            )
        else:
            pos = open_pos_map[ticker]
            entry_price = float(pos["avg_entry_price"])
            net_proceeds = gross_amount - commission_usd
            cash_after = round(cash_before + net_proceeds, 2)
            realised_pnl_delta = round(
                (fill_price - entry_price) * filled_qty - commission_usd, 2
            )
            remaining_qty = int(pos["quantity"]) - filled_qty
            if remaining_qty <= 0:
                self.db.execute(
                    "DELETE FROM paper_positions WHERE account_id = ? AND ticker = ?",
                    (self.account_id, ticker),
                )
            else:
                self.db.execute(
                    """
                    UPDATE paper_positions
                    SET quantity = ?, current_price = ?, updated_at = ?
                    WHERE account_id = ? AND ticker = ?
                    """,
                    (remaining_qty, execution_bar.adj_close, now_iso, self.account_id, ticker),
                )

        # 6. Update Paper Account Cash & Realised PnL
        new_realised = round(float(summary["realised_pnl"]) + realised_pnl_delta, 2)
        self.db.execute(
            """
            UPDATE paper_accounts
            SET cash_balance = ?, realised_pnl = ?, updated_at = ?
            WHERE account_id = ?
            """,
            (cash_after, new_realised, now_iso, self.account_id),
        )

        # 7. Record Order and Permanent Trade Ledger Entry
        self.db.execute(
            """
            INSERT INTO paper_orders (
                order_id, idempotency_key, account_id, strategy_id, strategy_version,
                ticker, side, order_type, requested_qty, filled_qty,
                limit_price, stop_price, avg_fill_price, commission_usd, slippage_usd,
                status, rejection_reason, signal_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                order_id,
                idem_key,
                self.account_id,
                strategy_id,
                strategy_version,
                ticker,
                side_u,
                order_type_u,
                requested_qty,
                filled_qty,
                limit_price,
                stop_price,
                fill_price,
                commission_usd,
                slippage_usd,
                order_status,
                signal_date,
                now_iso,
                now_iso,
            ),
        )

        ledger_id = f"led_{uuid.uuid4().hex[:12]}"
        self.db.execute(
            """
            INSERT INTO trade_ledger (
                ledger_id, order_id, account_id, strategy_id, strategy_version,
                ticker, side, fill_date, quantity, fill_price, gross_amount,
                commission_usd, slippage_usd, realised_pnl, cash_after, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ledger_id,
                order_id,
                self.account_id,
                strategy_id,
                strategy_version,
                ticker,
                side_u,
                execution_bar.bar_date,
                filled_qty,
                fill_price,
                gross_amount,
                commission_usd,
                slippage_usd,
                realised_pnl_delta,
                cash_after,
                notes or f"{side_u} {filled_qty} {ticker} @ ${fill_price:.2f}",
                now_iso,
            ),
        )

        # 8. Optional Alpaca Paper Brokerage Order Mirroring (when ALPACA_API_KEY is configured, Master account only)
        if (
            self.account_id == self.DEFAULT_ACCOUNT_ID
            and self.settings.alpaca_api_key
            and self.settings.alpaca_secret_key
        ):
            self._mirror_order_to_alpaca_paper(
                ticker=ticker,
                side=side_u,
                qty=filled_qty,
                order_type=order_type_u,
                limit_price=limit_price,
                stop_price=stop_price,
                client_order_id=idem_key,
            )

        return OrderSubmissionResult(
            order_id=order_id,
            idempotency_key=idem_key,
            status=order_status,
            filled_qty=filled_qty,
            avg_fill_price=fill_price,
            commission_usd=commission_usd,
            slippage_usd=slippage_usd,
        )

    def _mirror_order_to_alpaca_paper(
        self,
        ticker: str,
        side: str,
        qty: int,
        order_type: str,
        limit_price: Optional[float],
        stop_price: Optional[float],
        client_order_id: str,
    ) -> None:
        """Mirror approved paper orders to Alpaca's paper-api.alpaca.markets endpoint when credentials exist."""
        import urllib.request
        base_url = self.settings.alpaca_paper_base_url.rstrip("/")
        if base_url.endswith("/v2"):
            base_url = base_url[:-3]
        if "paper-api.alpaca.markets" not in base_url:
            raise LiveTradingProhibitedError(
                f"Refusing to mirror order to non-paper Alpaca URL: {base_url}"
            )
        url = f"{base_url}/v2/orders"
        type_map = {
            "MARKET": "market",
            "LIMIT": "limit",
            "STOP_LOSS": "stop",
            "TAKE_PROFIT": "limit",
        }
        payload: Dict[str, Any] = {
            "symbol": ticker,
            "qty": str(qty),
            "side": side.lower(),
            "type": type_map.get(order_type, "market"),
            "time_in_force": "day",
            "client_order_id": client_order_id[:48],
        }
        if payload["type"] == "limit" and limit_price is not None:
            payload["limit_price"] = str(round(limit_price, 2))
        if payload["type"] == "stop" and stop_price is not None:
            payload["stop_price"] = str(round(stop_price, 2))
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "APCA-API-KEY-ID": self.settings.alpaca_api_key,
                    "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except Exception as exc:
            logger.warning(f"Alpaca paper order mirror skipped/failed ({exc}); internal paper ledger remains authoritative.")

    def mark_to_market_and_snapshot(self, trading_date: str) -> Dict[str, Any]:
        """Mark all open positions to live quote (or `trading_date` market close), process dividends, and save snapshot."""
        live_prices = self.refresh_live_positions_mark_to_market(cache_ttl_seconds=30)
        positions = self.get_open_positions()
        acc = self.ensure_account_initialized()
        cash = float(acc["cash_balance"])
        now_iso = utc_now_iso()

        for pos in positions:
            ticker = pos["ticker"]
            tkr_u = str(ticker).upper()
            bars = self.market_data.get_bars(ticker, start_date=trading_date, end_date=trading_date)
            bar = bars[-1] if bars else None
            if tkr_u in live_prices:
                curr_p = live_prices[tkr_u]
                new_high = max(float(pos["highest_price_since_entry"]), curr_p, bar.adj_high if bar else curr_p)
            elif bar is not None:
                curr_p = bar.adj_close
                new_high = max(float(pos["highest_price_since_entry"]), bar.adj_high)
            else:
                continue
            new_days = int(pos["holding_days"]) + (1 if trading_date > pos["opened_date"] else 0)
            if bar is not None and bar.dividend_amount > 0:
                div_cash = int(pos["quantity"]) * bar.dividend_amount
                cash = round(cash + div_cash, 2)

            self.db.execute(
                """
                UPDATE paper_positions
                SET current_price = ?, highest_price_since_entry = ?, holding_days = ?, updated_at = ?
                WHERE account_id = ? AND ticker = ?
                """,
                (curr_p, new_high, new_days, now_iso, self.account_id, ticker),
            )

        self.db.execute(
            "UPDATE paper_accounts SET cash_balance = ?, updated_at = ? WHERE account_id = ?",
            (cash, now_iso, self.account_id),
        )

        summary = self.get_account_summary()
        total_eq = summary["total_equity"]
        peak_eq = max(float(acc["peak_equity"]), total_eq)
        if peak_eq > float(acc["peak_equity"]):
            self.db.execute(
                "UPDATE paper_accounts SET peak_equity = ? WHERE account_id = ?",
                (peak_eq, self.account_id),
            )

        dd_pct = ((peak_eq - total_eq) / peak_eq) * 100.0 if peak_eq > 0 else 0.0
        if dd_pct >= self.settings.risk.drawdown_suspension_threshold_pct * 100.0:
            self.set_kill_switch(
                True,
                f"Portfolio drawdown {dd_pct:.2f}% reached suspension threshold "
                f"{self.settings.risk.drawdown_suspension_threshold_pct * 100:.1f}%",
            )

        # Previous snapshot for daily return calculation
        prev_snaps = self.db.fetch_all(
            """
            SELECT total_equity FROM portfolio_snapshots
            WHERE account_id = ? AND snapshot_date < ?
            ORDER BY snapshot_date DESC LIMIT 1
            """,
            (self.account_id, trading_date),
        )
        prev_eq = float(prev_snaps[0]["total_equity"]) if prev_snaps else float(acc["starting_cash"])
        daily_ret_pct = ((total_eq / prev_eq) - 1.0) * 100.0 if prev_eq > 0 else 0.0

        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker, end_date=trading_date)
        spy_price = spy_bars[-1].adj_close if spy_bars else None
        spy_cum_ret = (
            ((spy_bars[-1].adj_close / spy_bars[0].adj_close) - 1.0) * 100.0
            if len(spy_bars) >= 2
            else 0.0
        )

        self.db.execute(
            """
            INSERT INTO portfolio_snapshots (
                account_id, snapshot_date, cash_balance, positions_market_value,
                total_equity, daily_return_pct, cumulative_return_pct, drawdown_pct,
                benchmark_price, benchmark_cum_return_pct, open_positions_count,
                realised_pnl, unrealised_pnl, sector_exposures_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, snapshot_date) DO UPDATE SET
                cash_balance=excluded.cash_balance,
                positions_market_value=excluded.positions_market_value,
                total_equity=excluded.total_equity,
                daily_return_pct=excluded.daily_return_pct,
                cumulative_return_pct=excluded.cumulative_return_pct,
                drawdown_pct=excluded.drawdown_pct,
                open_positions_count=excluded.open_positions_count,
                realised_pnl=excluded.realised_pnl,
                unrealised_pnl=excluded.unrealised_pnl,
                sector_exposures_json=excluded.sector_exposures_json
            """,
            (
                self.account_id,
                trading_date,
                summary["cash_balance"],
                summary["positions_market_value"],
                total_eq,
                round(daily_ret_pct, 3),
                summary["total_return_pct"],
                round(dd_pct, 2),
                spy_price,
                round(spy_cum_ret, 2),
                summary["open_positions_count"],
                summary["realised_pnl"],
                summary["unrealised_pnl"],
                json.dumps(summary["sector_exposures_pct"]),
                now_iso,
            ),
        )
        return self.get_account_summary()

    def run_trading_session_for_strategies(
        self,
        active_strategies: Sequence[StrategyConfig],
        trading_date: str,
        allow_historical_simulation: bool = False,
    ) -> Dict[str, Any]:
        """Run one trading session across approved `PAPER_TRADING` strategies.

        Strict Market Hours & Live Price Invariants:
        - In live operation (outside unit tests / explicit historical replay), orders
          ONLY execute when `USTradingCalendar.is_market_open()` is True (9:30 AM – 4:00 PM ET,
          which is 10:30 PM – 5:00 AM SGT during EST or 9:30 PM – 4:00 AM SGT during EDT).
        - If the US market is currently closed, no paper trades are executed and status
          `MARKET_CLOSED_DEFERRED` is returned.
        - During open market hours, signals are evaluated from the latest completed daily
          close and executed against real-time live market quotes (`fetch_live_quote_snapshots`).
        """
        import sys as _sys

        self.settings.validate_trading_mode()
        is_test_or_sim = allow_historical_simulation or ("unittest" in _sys.modules)

        if not is_test_or_sim:
            if not USTradingCalendar.is_market_open():
                self.refresh_live_positions_mark_to_market(cache_ttl_seconds=30)
                open_sgt = USTradingCalendar.market_open_sgt()
                close_sgt = USTradingCalendar.market_close_sgt()
                return {
                    "trading_date": trading_date,
                    "status": "MARKET_CLOSED_DEFERRED",
                    "message": (
                        f"NYSE/NASDAQ regular market session is currently closed "
                        f"(Regular hours: {open_sgt} – {close_sgt} / 9:30 AM – 4:00 PM ET). "
                        f"Paper trade execution is strictly restricted to open market hours."
                    ),
                    "exits_executed": [],
                    "entries_executed": [],
                    "vetoed_orders": [],
                    "account_summary": self.get_account_summary(),
                }
            # Market is currently open: execute for today's active US session date using live prices
            effective_trading_date = USTradingCalendar.current_et_datetime().date().isoformat()
        else:
            effective_trading_date = trading_date

        universe_meta = self.market_data.get_universe_metadata(include_delisted=True)

        # Fetch live quotes when running in live market hours
        live_quotes: Dict[str, Dict[str, Any]] = {}
        if not is_test_or_sim and hasattr(self.market_data, "fetch_live_quote_snapshots"):
            try:
                uni_tickers = sorted(
                    {str(t).upper() for s in active_strategies for t in s.universe}
                    | {str(p["ticker"]).upper() for p in self.get_open_positions()}
                    | {self.settings.benchmark_ticker}
                )
                live_quotes = self.market_data.fetch_live_quote_snapshots(uni_tickers, cache_ttl_seconds=15) or {}
            except Exception as exc:
                logger.warning(f"Live quote fetch failed ({exc}).")

        now_iso = utc_now_iso()

        def _build_live_bar(ticker: str, fallback_bar: Optional[DailyBar] = None) -> Optional[DailyBar]:
            """Construct a DailyBar for today's active session using real-time live market quotes."""
            quote = live_quotes.get(ticker.upper())
            if not quote:
                return None
            live_p = float(quote.get("latest_trade_price") or quote.get("indicative_price") or 0.0)
            if live_p <= 0:
                return None
            live_p = round(live_p, 4)
            has_today_dbar = quote.get("daily_bar_date") == effective_trading_date
            d_open = round(float(quote.get("daily_open") or live_p), 4) if has_today_dbar else live_p
            d_high = round(max(float(quote.get("daily_high") or live_p), live_p, d_open), 4) if has_today_dbar else live_p
            d_low_raw = float(quote.get("daily_low") or 0.0) if has_today_dbar else 0.0
            d_low = round(min(d_low_raw, live_p, d_open), 4) if d_low_raw > 0 else round(min(live_p, d_open), 4)
            d_vol = float(quote.get("daily_volume") or (fallback_bar.volume if fallback_bar else 1_000_000.0))
            return DailyBar(
                ticker=ticker.upper(),
                bar_date=effective_trading_date,
                open=d_open,
                high=d_high,
                low=d_low,
                close=live_p,
                volume=d_vol,
                adj_open=live_p,  # Fill paper orders at the actual live market price
                adj_high=d_high,
                adj_low=d_low,
                adj_close=live_p,
                adj_volume=d_vol,
                split_factor=1.0,
                dividend_amount=0.0,
                provider_source="alpaca_live",
                retrieved_at=now_iso,
            )

        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker, end_date=effective_trading_date)
        if not is_test_or_sim and spy_bars and spy_bars[-1].bar_date < effective_trading_date:
            spy_live_bar = _build_live_bar(self.settings.benchmark_ticker, fallback_bar=spy_bars[-1])
            spy_bars_with_live = list(spy_bars) + ([spy_live_bar] if spy_live_bar else [])
        else:
            spy_bars_with_live = list(spy_bars)
        spy_inds = compute_indicator_series(spy_bars_with_live)

        exits_executed: List[Dict[str, Any]] = []
        entries_executed: List[Dict[str, Any]] = []
        vetoed_orders: List[Dict[str, Any]] = []

        strat_by_id = {(s.strategy_id, s.version): s for s in active_strategies}
        fallback_strat = active_strategies[0] if active_strategies else None

        # Load latest point-in-time AI / news catalyst sentiment per ticker.
        try:
            td_dt = date.fromisoformat(effective_trading_date[:10])
            is_live_window = abs((date.today() - td_dt).days) <= 4
        except ValueError:
            is_live_window = False
        cat_cutoff = max(effective_trading_date, date.today().isoformat()) if is_live_window else effective_trading_date
        catalyst_rows = self.db.fetch_all(
            """
            SELECT ticker, headline, summary, sentiment_score, source_name, catalyst_type, published_date
            FROM market_catalysts
            WHERE published_date <= ?
            ORDER BY published_date DESC, id DESC
            LIMIT 250
            """,
            (cat_cutoff,),
        )
        latest_cat_info: Dict[str, Dict[str, Any]] = {}
        latest_cat_sent: Dict[str, float] = {}
        for crow in catalyst_rows:
            tk = str(crow["ticker"]).upper()
            if tk not in latest_cat_info:
                latest_cat_info[tk] = dict(crow)
                if crow.get("sentiment_score") is not None:
                    latest_cat_sent[tk] = float(crow["sentiment_score"])

        # 1. Evaluate exits on existing open positions (Technical Exit + Emergency AI Bearish Catalyst Exit <= -0.50)
        for pos in self.get_open_positions():
            ticker = pos["ticker"]
            bars = self.market_data.get_bars(ticker, end_date=effective_trading_date)
            if not bars:
                continue
            if not is_test_or_sim:
                live_b = _build_live_bar(ticker, fallback_bar=bars[-1])
                if live_b is None:
                    continue
                today_bar = live_b
                bars_for_exit = (list(bars[:-1]) + [today_bar]) if bars[-1].bar_date == effective_trading_date else (list(bars) + [today_bar])
            else:
                if bars[-1].bar_date != effective_trading_date:
                    continue
                today_bar = bars[-1]
                bars_for_exit = bars

            inds = compute_indicator_series(bars_for_exit, spy_bars=spy_bars_with_live)
            ind_today = inds.get(effective_trading_date)
            if ind_today is None:
                continue

            strat = strat_by_id.get((pos["strategy_id"], int(pos["strategy_version"])), fallback_strat)
            if strat is None:
                continue

            exit_sig = StrategySignalEngine.evaluate_exit(
                config=strat,
                ind=ind_today,
                entry_price=float(pos["avg_entry_price"]),
                highest_price_since_entry=float(pos["highest_price_since_entry"]),
                holding_days=int(pos["holding_days"]) + 1,
                stop_loss_price=float(pos["stop_loss_price"]) if pos["stop_loss_price"] else None,
                take_profit_price=float(pos["take_profit_price"]) if pos["take_profit_price"] else None,
            )
            pos_cat = latest_cat_info.get(ticker.upper())
            pos_ai_sent = float(pos_cat["sentiment_score"]) if (pos_cat and pos_cat.get("sentiment_score") is not None) else 0.0
            pos_ai_note = str(pos_cat.get("headline") or pos_cat.get("summary") or "") if pos_cat else ""
            ai_exit_reason = (
                f"AI Bearish Catalyst Protection (Sentiment {pos_ai_sent:+.2f}): {pos_ai_note[:95]}"
                if (pos_cat and pos_ai_sent <= -0.50 and str(pos_cat.get("catalyst_type") or "") == "IDE_AI_RESEARCH")
                else None
            )
            eff_exit_reason = exit_sig.reason if exit_sig is not None else ai_exit_reason
            if eff_exit_reason is not None:
                res = self.submit_and_execute_order(
                    strategy_id=strat.strategy_id,
                    strategy_version=strat.version,
                    strategy_family=strat.strategy_family,
                    ticker=ticker,
                    side="SELL",
                    requested_qty=int(pos["quantity"]),
                    signal_date=effective_trading_date,
                    execution_bar=today_bar,
                    sector=pos["sector"],
                    notes=eff_exit_reason,
                )
                exits_executed.append(res.to_dict())

        # 2. Evaluate new entry signals across active strategies with fair multi-strategy allocation
        # Deduplicate active strategies by strategy_id (keep highest promoted version)
        latest_active_by_id: Dict[str, StrategyConfig] = {}
        for s in active_strategies:
            prev = latest_active_by_id.get(s.strategy_id)
            if prev is None or s.version > prev.version:
                latest_active_by_id[s.strategy_id] = s
        deduped_strategies = list(latest_active_by_id.values())

        # Precompute bars & causal indicators up to prior close once per ticker
        all_tickers = sorted({t for s in deduped_strategies for t in s.universe if t != self.settings.benchmark_ticker})
        ticker_context: Dict[str, Tuple[DailyBar, DailyBar, Any, List[Any]]] = {}
        sector_rs_lists: Dict[str, List[float]] = {}
        for ticker in all_tickers:
            bars = self.market_data.get_bars(ticker, end_date=effective_trading_date)
            if len(bars) < 25:
                continue
            if not is_test_or_sim:
                live_b = _build_live_bar(ticker, fallback_bar=bars[-1])
                if live_b is None:
                    continue
                today_bar = live_b
                if bars[-1].bar_date < effective_trading_date:
                    prev_bar = bars[-1]
                    inds = compute_indicator_series(bars, spy_bars=spy_bars)
                else:
                    prev_bar = bars[-2]
                    inds = compute_indicator_series(bars[:-1], spy_bars=spy_bars)
            else:
                if bars[-1].bar_date != effective_trading_date:
                    continue
                today_bar = bars[-1]
                prev_bar = bars[-2]
                inds = compute_indicator_series(bars[:-1], spy_bars=spy_bars)

            ind_prev = inds.get(prev_bar.bar_date)
            if ind_prev is None:
                continue
            recent_ev = self.market_data.get_point_in_time_earnings(
                ticker, prev_bar.bar_date, lookback_days=95
            )
            ticker_context[ticker] = (today_bar, prev_bar, ind_prev, recent_ev)
            t_meta = universe_meta.get(ticker)
            if t_meta is not None and ind_prev.rs_vs_spy_20d is not None:
                sector_rs_lists.setdefault(t_meta.sector, []).append(float(ind_prev.rs_vs_spy_20d))

        sorted_sectors = sorted(
            sector_rs_lists.keys(),
            key=lambda s: sum(sorted(sector_rs_lists[s], reverse=True)[:2]) / min(2, len(sector_rs_lists[s])),
            reverse=True,
        )
        sector_rank_map = {sec_name: idx + 1 for idx, sec_name in enumerate(sorted_sectors)}

        # Collect signals per strategy and sort by conviction_score descending
        signals_by_strategy: Dict[str, List[Tuple[StrategyConfig, str, DailyBar, DailyBar, Any]]] = {}
        for strat in deduped_strategies:
            strat_sigs: List[Tuple[StrategyConfig, str, DailyBar, DailyBar, Any]] = []
            pead_lookback = max(20, int(strat.entry_rules.get("max_days_since_earnings", 10)) + 5)
            for ticker in strat.universe:
                ctx = ticker_context.get(ticker)
                if ctx is None:
                    continue
                today_bar, prev_bar, ind_prev, _ = ctx
                recent_ev = self.market_data.get_point_in_time_earnings(
                    ticker, prev_bar.bar_date, lookback_days=pead_lookback
                )
                t_meta = universe_meta.get(ticker)
                sec_rank = sector_rank_map.get(t_meta.sector) if t_meta else None
                sig = StrategySignalEngine.evaluate_entry(
                    config=strat,
                    ind=ind_prev,
                    spy_ind=spy_inds.get(prev_bar.bar_date),
                    recent_earnings=recent_ev,
                    sector_rs_rank=sec_rank,
                )
                if sig is not None:
                    strat_sigs.append((strat, ticker, today_bar, prev_bar, sig))
            strat_sigs.sort(key=lambda item: float(item[4].conviction_score), reverse=True)
            if strat_sigs:
                signals_by_strategy[strat.strategy_id] = strat_sigs

        # Interleave signals round-robin across strategies so no single strategy monopolizes capital/sector caps
        ordered_candidates: List[Tuple[StrategyConfig, str, DailyBar, DailyBar, Any]] = []
        # Order strategies so rarer breakout/catalyst strategies get first pick before broad trend-following
        strat_order = sorted(
            signals_by_strategy.keys(),
            key=lambda sid: (0 if "breakout" in sid or "pead" in sid else 1, sid),
        )
        max_len = max((len(v) for v in signals_by_strategy.values()), default=0)
        for idx in range(max_len):
            for sid in strat_order:
                bucket = signals_by_strategy[sid]
                if idx < len(bucket):
                    ordered_candidates.append(bucket[idx])

        def _paper_candidate_conviction(item: Tuple[StrategyConfig, str, DailyBar, DailyBar, Any]) -> float:
            tk_u = str(item[1]).upper()
            sent_v = latest_cat_sent.get(tk_u, 0.0)
            base_c = float(item[4].conviction_score) * 100.0
            if sent_v >= 0.25:
                base_c = min(99.0, base_c + min(8.0, sent_v * 12.0))
            elif sent_v < 0.0:
                base_c = max(1.0, base_c + sent_v * 10.0)
            return base_c

        ordered_candidates.sort(key=_paper_candidate_conviction, reverse=True)

        seen_paper_candidates: set[str] = set()
        for strat, ticker, today_bar, prev_bar, sig in ordered_candidates:
            if ticker in seen_paper_candidates:
                continue
            seen_paper_candidates.add(ticker)

            # Prevent cross-strategy position overwrite on the same ticker in the Master combined account
            open_tickers_now = {p["ticker"] for p in self.get_open_positions()}
            if ticker in open_tickers_now:
                continue

            # AI Bearish Catalyst Veto (<= -0.35)
            cat_row = latest_cat_info.get(ticker.upper())
            ai_sent_val = latest_cat_sent.get(ticker.upper(), 0.0)
            ai_note_str = str(cat_row.get("headline") or cat_row.get("summary") or "") if cat_row else ""
            if ai_sent_val <= -0.35:
                veto_reason_str = f"Removed by AI Catalyst Filter (Sentiment {ai_sent_val:+.2f}): {ai_note_str[:95]}"
                vetoed_orders.append(
                    {
                        "ticker": ticker,
                        "strategy_id": strat.strategy_id,
                        "strategy_version": strat.version,
                        "side": "BUY",
                        "status": "REJECTED",
                        "rejection_reason": veto_reason_str,
                    }
                )
                continue

            summary_now = self.get_account_summary()
            open_gap = today_bar.adj_open - sig.close_at_signal
            max_gap_atr = float(strat.entry_rules.get("max_entry_gap_atr", 1.25))
            if sig.atr_at_signal and sig.atr_at_signal > 0:
                if open_gap > max_gap_atr * sig.atr_at_signal:
                    continue
                if not is_test_or_sim and open_gap < -0.75 * sig.atr_at_signal:
                    continue
            adj_stop = (
                round(max(0.01, sig.stop_loss_price + open_gap), 2)
                if sig.stop_loss_price is not None
                else None
            )
            adj_tp = (
                round(sig.take_profit_price + open_gap, 2)
                if sig.take_profit_price is not None
                else None
            )
            rec_shares = self.risk_manager.calculate_atr_position_size(
                portfolio_equity=summary_now["total_equity"],
                available_cash=summary_now["cash_balance"],
                entry_price=today_bar.adj_open,
                stop_loss_price=adj_stop,
                atr_14=sig.atr_at_signal,
                strategy_risk_per_trade_pct=strat.risk_params.get("risk_per_trade_pct"),
                strategy_max_exposure_pct=strat.risk_params.get("max_position_exposure_pct"),
            )
            if rec_shares <= 0:
                continue

            meta = universe_meta.get(ticker)
            sector = meta.sector if meta else "Technology"
            ctx = ticker_context.get(ticker)
            ind_prev_obj = ctx[2] if ctx else None
            upcoming_ev = self.market_data.get_upcoming_earnings_within_days(ticker, effective_trading_date, 3)
            days_to_earn = 1 if upcoming_ev else None

            entry_note = sig.reason
            if ai_sent_val >= 0.25 and ai_note_str:
                entry_note = f"{sig.reason} · [AI Catalyst {ai_sent_val:+.2f}: {ai_note_str[:55]}]"

            res = self.submit_and_execute_order(
                strategy_id=strat.strategy_id,
                strategy_version=strat.version,
                strategy_family=strat.strategy_family,
                ticker=ticker,
                side="BUY",
                requested_qty=rec_shares,
                signal_date=prev_bar.bar_date,
                execution_bar=today_bar,
                sector=sector,
                stop_loss_target=adj_stop,
                take_profit_target=adj_tp,
                atr_14=sig.atr_at_signal,
                notes=entry_note,
                avg_daily_dollar_volume_20d=ind_prev_obj.avg_dollar_volume_20d if ind_prev_obj else None,
                upcoming_earnings_days=days_to_earn,
                strategy_risk_pct=strat.risk_params.get("risk_per_trade_pct"),
                strategy_max_exp_pct=strat.risk_params.get("max_position_exposure_pct"),
            )
            if res.status in ("FILLED", "PARTIALLY_FILLED"):
                entries_executed.append(res.to_dict())
            elif res.status == "REJECTED":
                vetoed_orders.append(res.to_dict())

        # 3. End-of-day mark-to-market & snapshot for this account
        updated_summary = self.mark_to_market_and_snapshot(effective_trading_date)

        # 4. When running on the Master Account, also update each strategy's dedicated $100k Paper Account sleeve
        if self.account_id == self.DEFAULT_ACCOUNT_ID and deduped_strategies:
            for strat in deduped_strategies:
                strat_engine = self.get_strategy_account_engine(strat.strategy_id)
                strat_engine.run_trading_session_for_strategies(
                    active_strategies=[strat],
                    trading_date=effective_trading_date,
                    allow_historical_simulation=allow_historical_simulation,
                )

        return {
            "trading_date": effective_trading_date,
            "exits_executed": exits_executed,
            "entries_executed": entries_executed,
            "vetoed_orders": vetoed_orders,
            "account_summary": updated_summary,
        }

    def sync_ai_catalysts_to_paper_accounts(
        self,
        active_strategies: Sequence[StrategyConfig],
        session_date: str,
    ) -> Dict[str, Any]:
        """Synchronize latest IDE AI catalyst findings (`run`) to Master & Per-Strategy Paper Accounts."""
        import sys as _sys

        if "unittest" not in _sys.modules and not USTradingCalendar.is_market_open():
            self.refresh_live_positions_mark_to_market(cache_ttl_seconds=30)
            return {
                "session_date": session_date,
                "status": "MARKET_CLOSED_DEFERRED",
                "ai_paper_exits_triggered": [],
            }

        cat_cutoff = max(session_date, date.today().isoformat())
        catalyst_rows = self.db.fetch_all(
            """
            SELECT ticker, headline, summary, sentiment_score, source_name, catalyst_type, published_date
            FROM market_catalysts
            WHERE published_date <= ? AND catalyst_type = 'IDE_AI_RESEARCH'
            ORDER BY published_date DESC, id DESC
            LIMIT 100
            """,
            (cat_cutoff,),
        )
        ai_cat_by_tkr: Dict[str, Dict[str, Any]] = {}
        for crow in catalyst_rows:
            tk = str(crow["ticker"]).upper()
            if tk not in ai_cat_by_tkr:
                ai_cat_by_tkr[tk] = dict(crow)

        strat_by_id = {(s.strategy_id, s.version): s for s in active_strategies}
        fallback_strat = active_strategies[0] if active_strategies else None
        all_engines = [self]
        if self.account_id == self.DEFAULT_ACCOUNT_ID:
            seen_sids: set[str] = set()
            for s in active_strategies:
                if s.strategy_id not in seen_sids:
                    seen_sids.add(s.strategy_id)
                    all_engines.append(self.get_strategy_account_engine(s.strategy_id))

        live_quotes: Dict[str, Dict[str, Any]] = {}
        if "unittest" not in _sys.modules and hasattr(self.market_data, "fetch_live_quote_snapshots"):
            open_tkrs = sorted({str(p["ticker"]).upper() for eng in all_engines for p in eng.get_open_positions()})
            if open_tkrs:
                live_quotes = self.market_data.fetch_live_quote_snapshots(open_tkrs, cache_ttl_seconds=15) or {}

        live_dt = USTradingCalendar.current_et_datetime().date().isoformat() if "unittest" not in _sys.modules else session_date
        now_iso = utc_now_iso()

        ai_exits: List[Dict[str, Any]] = []
        for eng in all_engines:
            for pos in eng.get_open_positions():
                tkr = pos["ticker"].upper()
                c_info = ai_cat_by_tkr.get(tkr)
                if not c_info or c_info.get("sentiment_score") is None:
                    continue
                sent = float(c_info["sentiment_score"])
                note = str(c_info.get("headline") or c_info.get("summary") or "")
                should_exit = (sent <= -0.50) or (sent <= -0.35 and str(pos.get("opened_date")) in (session_date, live_dt))
                if not should_exit:
                    continue
                bars = eng.market_data.get_bars(tkr, end_date=session_date)
                if not bars:
                    continue
                exec_bar = bars[-1]
                q = live_quotes.get(tkr)
                if q:
                    lp = float(q.get("latest_trade_price") or q.get("indicative_price") or 0.0)
                    if lp > 0:
                        lp = round(lp, 4)
                        exec_bar = DailyBar(
                            ticker=tkr,
                            bar_date=live_dt,
                            open=lp,
                            high=max(exec_bar.high, lp),
                            low=min(exec_bar.low, lp),
                            close=lp,
                            volume=exec_bar.volume,
                            adj_open=lp,
                            adj_high=max(exec_bar.adj_high, lp),
                            adj_low=min(exec_bar.adj_low, lp),
                            adj_close=lp,
                            adj_volume=exec_bar.adj_volume,
                            provider_source="alpaca_live",
                            retrieved_at=now_iso,
                        )
                strat = strat_by_id.get((pos["strategy_id"], int(pos["strategy_version"])), fallback_strat)
                if strat is None:
                    continue
                res = eng.submit_and_execute_order(
                    strategy_id=strat.strategy_id,
                    strategy_version=strat.version,
                    strategy_family=strat.strategy_family,
                    ticker=tkr,
                    side="SELL",
                    requested_qty=int(pos["quantity"]),
                    signal_date=exec_bar.bar_date,
                    execution_bar=exec_bar,
                    sector=pos["sector"],
                    notes=f"AI Catalyst Exit ({sent:+.2f}): {note[:90]}",
                )
                if res.status in ("FILLED", "PARTIALLY_FILLED"):
                    ai_exits.append({"account_id": eng.account_id, **res.to_dict()})
            eng.mark_to_market_and_snapshot(live_dt)

        return {"session_date": session_date, "ai_paper_exits_triggered": ai_exits}

    def _record_rejected_order(
        self,
        order_id: str,
        idem_key: str,
        strategy_id: str,
        strategy_version: int,
        ticker: str,
        side: str,
        order_type: str,
        requested_qty: int,
        limit_price: Optional[float],
        stop_price: Optional[float],
        signal_date: str,
        reason: str,
    ) -> OrderSubmissionResult:
        now_iso = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO paper_orders (
                order_id, idempotency_key, account_id, strategy_id, strategy_version,
                ticker, side, order_type, requested_qty, filled_qty,
                limit_price, stop_price, avg_fill_price, commission_usd, slippage_usd,
                status, rejection_reason, signal_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, 0.0, 0.0, 'REJECTED', ?, ?, ?, ?)
            """,
            (
                order_id,
                idem_key,
                self.account_id,
                strategy_id,
                strategy_version,
                ticker,
                side,
                order_type,
                requested_qty,
                limit_price,
                stop_price,
                reason,
                signal_date,
                now_iso,
                now_iso,
            ),
        )
        return OrderSubmissionResult(
            order_id=order_id,
            idempotency_key=idem_key,
            status="REJECTED",
            filled_qty=0,
            avg_fill_price=None,
            commission_usd=0.0,
            slippage_usd=0.0,
            rejection_reason=reason,
        )

    def _record_pending_order(
        self,
        order_id: str,
        idem_key: str,
        strategy_id: str,
        strategy_version: int,
        ticker: str,
        side: str,
        order_type: str,
        requested_qty: int,
        limit_price: Optional[float],
        stop_price: Optional[float],
        signal_date: str,
    ) -> OrderSubmissionResult:
        now_iso = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO paper_orders (
                order_id, idempotency_key, account_id, strategy_id, strategy_version,
                ticker, side, order_type, requested_qty, filled_qty,
                limit_price, stop_price, avg_fill_price, commission_usd, slippage_usd,
                status, rejection_reason, signal_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, 0.0, 0.0, 'PENDING', NULL, ?, ?, ?)
            """,
            (
                order_id,
                idem_key,
                self.account_id,
                strategy_id,
                strategy_version,
                ticker,
                side,
                order_type,
                requested_qty,
                limit_price,
                stop_price,
                signal_date,
                now_iso,
                now_iso,
            ),
        )
        return OrderSubmissionResult(
            order_id=order_id,
            idempotency_key=idem_key,
            status="PENDING",
            filled_qty=0,
            avg_fill_price=None,
            commission_usd=0.0,
            slippage_usd=0.0,
        )


class LiveTradingCopilotEngine:
    """Air-Gapped Live Trading Copilot & Shadow Portfolio Engine.

    Generates daily step-by-step BUY and SELL instructions sized specifically to the user's
    real-account cash and confirmed holdings WITHOUT ever connecting to a live brokerage account
    or assuming a trade was taken until the user explicitly confirms or edits it.
    """

    def __init__(
        self,
        settings: Settings,
        db: DatabaseManager,
        market_data: MarketDataService,
        risk_manager: PortfolioRiskManager,
        registry: Any,
        account_id: str = "real_shadow_default",
        default_starting_cash: float = 25_000.0,
    ) -> None:
        self.settings = settings
        self.db = db
        self.market_data = market_data
        self.risk_manager = risk_manager
        self.registry = registry
        self.account_id = account_id
        self.default_starting_cash = default_starting_cash
        self.ensure_initialized()

    def ensure_initialized(self) -> Dict[str, Any]:
        row = self.db.fetch_one(
            "SELECT * FROM shadow_accounts WHERE account_id = ?", (self.account_id,)
        )
        if row is None:
            now_iso = utc_now_iso()
            self.db.execute(
                """
                INSERT INTO shadow_accounts (
                    account_id, starting_cash, cash_balance, realised_pnl, enabled_strategies_json, updated_at
                ) VALUES (?, ?, ?, 0.0, '[]', ?)
                """,
                (self.account_id, self.default_starting_cash, self.default_starting_cash, now_iso),
            )
            row = self.db.fetch_one(
                "SELECT * FROM shadow_accounts WHERE account_id = ?", (self.account_id,)
            )
        assert row is not None
        return dict(row)

    def sync_market_prices(self, as_of_date: Optional[str] = None) -> None:
        """Mark all confirmed real positions to the latest live or closing price and update holding days."""
        rows = self.db.fetch_all(
            "SELECT * FROM shadow_positions WHERE account_id = ? ORDER BY ticker ASC",
            (self.account_id,),
        )
        if not rows:
            return
        now_iso = utc_now_iso()
        if as_of_date is None and hasattr(self.market_data, "ensure_latest_market_data"):
            self.market_data.ensure_latest_market_data()

        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker, end_date=as_of_date)
        latest_session_date = spy_bars[-1].bar_date if spy_bars else None
        use_live_quotes = (
            "unittest" not in sys.modules
            and hasattr(self.market_data, "fetch_live_quote_snapshots")
            and (as_of_date is None or (latest_session_date is not None and as_of_date >= latest_session_date))
        )
        live_snapshots: Dict[str, Dict[str, Any]] = {}
        if use_live_quotes:
            try:
                live_snapshots = self.market_data.fetch_live_quote_snapshots([str(r["ticker"]) for r in rows])
            except Exception:
                live_snapshots = {}

        for r in rows:
            ticker = r["ticker"]
            opened_dt = str(r["opened_date"])
            bars = self.market_data.get_bars(ticker, end_date=as_of_date)
            snap = live_snapshots.get(str(ticker).upper()) or {}
            live_px = float(snap.get("indicative_price") or 0.0)
            live_high = float(snap.get("daily_high") or live_px or 0.0)
            if bars:
                latest_bar = bars[-1]
                curr_price = round(live_px, 2) if live_px > 0 else float(latest_bar.adj_close)
                high_since = max(
                    float(r["highest_price_since_entry"]),
                    float(latest_bar.adj_high),
                    curr_price,
                    live_high,
                )
                hold_days = sum(1 for b in bars if b.bar_date > opened_dt)
            else:
                curr_price = round(live_px, 2) if live_px > 0 else float(r["current_price"])
                high_since = max(float(r["highest_price_since_entry"]), curr_price, live_high)
                hold_days = sum(1 for b in spy_bars if b.bar_date > opened_dt) if spy_bars else int(r["holding_days"])
            self.db.execute(
                """
                UPDATE shadow_positions
                SET current_price = ?, highest_price_since_entry = ?, holding_days = ?, updated_at = ?
                WHERE account_id = ? AND ticker = ?
                """,
                (curr_price, high_since, hold_days, now_iso, self.account_id, ticker),
            )

    def get_open_positions(self) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM shadow_positions WHERE account_id = ? ORDER BY ticker ASC",
            (self.account_id,),
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            qty = int(r["quantity"])
            avg_p = float(r["avg_entry_price"])
            curr_p = float(r["current_price"])
            mv = round(qty * curr_p, 2)
            upnl = round(qty * (curr_p - avg_p), 2)
            uret = round(((curr_p / avg_p) - 1.0) * 100.0, 2) if avg_p > 0 else 0.0
            item = dict(r)
            item["market_value"] = mv
            item["unrealised_pnl"] = upnl
            item["unrealised_return_pct"] = uret
            out.append(item)
        return out

    def get_trade_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM shadow_trade_history WHERE account_id = ? ORDER BY created_at DESC LIMIT ?",
            (self.account_id, limit),
        )
        return [dict(r) for r in rows]

    def get_account_summary(self, as_of_date: Optional[str] = None) -> Dict[str, Any]:
        self.sync_market_prices(as_of_date=as_of_date)
        acc = self.ensure_initialized()
        positions = self.get_open_positions()
        cash = round(float(acc["cash_balance"]), 2)
        start_cash = round(float(acc["starting_cash"]), 2)
        realised = round(float(acc["realised_pnl"]), 2)
        pos_mv = round(sum(p["market_value"] for p in positions), 2)
        unrealised = round(sum(p["unrealised_pnl"] for p in positions), 2)
        total_eq = round(cash + pos_mv, 2)
        total_ret_pct = round(((total_eq / start_cash) - 1.0) * 100.0, 2) if start_cash > 0 else 0.0

        sector_mv: Dict[str, float] = {}
        for p in positions:
            sec = p.get("sector") or "Technology"
            sector_mv[sec] = sector_mv.get(sec, 0.0) + p["market_value"]
        sector_exp_pct = {
            sec: round((mv / total_eq) * 100.0, 2) if total_eq > 0 else 0.0
            for sec, mv in sector_mv.items()
        }

        enabled_strats = json.loads(acc.get("enabled_strategies_json") or "[]")
        return {
            "account_id": self.account_id,
            "starting_cash": start_cash,
            "cash_balance": cash,
            "positions_market_value": pos_mv,
            "total_equity": total_eq,
            "realised_pnl": realised,
            "unrealised_pnl": unrealised,
            "total_return_pct": total_ret_pct,
            "open_positions_count": len(positions),
            "sector_exposures_pct": sector_exp_pct,
            "enabled_strategies": enabled_strats,
        }

    def update_cash_balance(
        self,
        new_cash_balance: float,
        update_starting_baseline: bool = False,
    ) -> Dict[str, Any]:
        """Update the user's real cash balance (and optionally reset the starting capital baseline)."""
        if new_cash_balance < 0:
            raise ValueError("Cash balance cannot be negative.")
        acc = self.ensure_initialized()
        positions = self.get_open_positions()
        pos_cost = sum(int(p["quantity"]) * float(p["avg_entry_price"]) for p in positions)
        new_start = round(new_cash_balance + pos_cost, 2) if update_starting_baseline else float(acc["starting_cash"])
        self.db.execute(
            """
            UPDATE shadow_accounts
            SET cash_balance = ?, starting_cash = ?, updated_at = ?
            WHERE account_id = ?
            """,
            (round(new_cash_balance, 2), new_start, utc_now_iso(), self.account_id),
        )
        return self.get_account_summary()

    def adjust_cash_deposit_withdrawal(self, delta_cash: float) -> Dict[str, Any]:
        """Deposit (>0) or withdraw (<0) cash, shifting both cash_balance and starting_cash so P&L is preserved."""
        acc = self.ensure_initialized()
        cur_cash = float(acc["cash_balance"])
        cur_start = float(acc["starting_cash"])
        new_cash = round(cur_cash + delta_cash, 2)
        if new_cash < 0:
            raise ValueError(f"Cannot withdraw ${abs(delta_cash):,.2f}: only ${cur_cash:,.2f} uninvested cash available.")
        new_start = max(1.0, round(cur_start + delta_cash, 2))
        self.db.execute(
            """
            UPDATE shadow_accounts
            SET cash_balance = ?, starting_cash = ?, updated_at = ?
            WHERE account_id = ?
            """,
            (new_cash, new_start, utc_now_iso(), self.account_id),
        )
        return self.get_account_summary()

    def set_enabled_strategies(self, strategy_keys: List[str]) -> None:
        """Save user's preferred active strategy IDs (e.g. ['strat_momentum_trend:1', 'strat_volatility_breakout:2'])."""
        self.db.execute(
            "UPDATE shadow_accounts SET enabled_strategies_json = ?, updated_at = ? WHERE account_id = ?",
            (json.dumps(strategy_keys), utc_now_iso(), self.account_id),
        )

    def dismiss_signal(self, signal_date: str, strategy_id: str, ticker: str, action: str) -> None:
        """Record that the user chose to skip a recommended signal today."""
        self.db.execute(
            """
            INSERT INTO shadow_dismissed_signals (account_id, signal_date, strategy_id, ticker, action, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, signal_date, strategy_id, ticker, action) DO NOTHING
            """,
            (self.account_id, signal_date, strategy_id, ticker.upper(), action.upper(), utc_now_iso()),
        )

    def restore_dismissed_signals(self, signal_date: Optional[str] = None) -> int:
        """Restore any skipped/held signals for the given session date (or all dates if None)."""
        if signal_date:
            rows = self.db.fetch_all(
                "SELECT 1 FROM shadow_dismissed_signals WHERE account_id = ? AND signal_date = ?",
                (self.account_id, signal_date),
            )
            self.db.execute(
                "DELETE FROM shadow_dismissed_signals WHERE account_id = ? AND signal_date = ?",
                (self.account_id, signal_date),
            )
        else:
            rows = self.db.fetch_all(
                "SELECT 1 FROM shadow_dismissed_signals WHERE account_id = ?",
                (self.account_id,),
            )
            self.db.execute(
                "DELETE FROM shadow_dismissed_signals WHERE account_id = ?",
                (self.account_id,),
            )
        return len(rows)

    def confirm_buy_execution(
        self,
        ticker: str,
        strategy_id: str,
        strategy_version: int,
        quantity: int,
        fill_price: float,
        fees_usd: float = 0.0,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        reference_entry_price: Optional[float] = None,
        fill_date: Optional[str] = None,
        sector: str = "Technology",
        notes: str = "",
    ) -> Dict[str, Any]:
        """Record a user-confirmed real-account BUY execution and update cash & open positions."""
        if quantity <= 0 or fill_price <= 0:
            raise ValueError("Quantity and fill price must be positive.")
        ticker_u = ticker.strip().upper()
        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker)
        dt_str = fill_date or (spy_bars[-1].bar_date if spy_bars else utc_now_iso()[:10])
        now_iso = utc_now_iso()

        acc = self.ensure_initialized()
        cur_cash = float(acc["cash_balance"])
        cur_start = float(acc["starting_cash"])
        cost = round(quantity * fill_price + fees_usd, 2)
        if cost > cur_cash:
            # User bought using external broker cash beyond previously logged cash_balance:
            # auto-credit the shortfall to starting_cash so P&L is never artificially negative!
            shortfall = round(cost - cur_cash, 2)
            new_cash = 0.0
            new_start = round(cur_start + shortfall, 2)
        else:
            new_cash = round(cur_cash - cost, 2)
            new_start = cur_start

        # Shift Stop-Loss and Take-Profit proportionally if user's actual fill_price differs from reference_entry_price
        if reference_entry_price is not None and reference_entry_price > 0 and abs(fill_price - reference_entry_price) > 1e-4:
            price_shift = fill_price - reference_entry_price
            if stop_loss_price is not None:
                stop_loss_price = round(max(0.01, stop_loss_price + price_shift), 2)
            if take_profit_price is not None:
                take_profit_price = round(max(fill_price + 0.01, take_profit_price + price_shift), 2)

        # Auto-compute default ATR stop/target if omitted (e.g. when logging via + Log Trade)
        if stop_loss_price is None or take_profit_price is None:
            t_bars = self.market_data.get_bars(ticker_u)
            if len(t_bars) >= 20:
                t_inds = compute_indicator_series(t_bars)
                t_ind_last = t_inds.get(t_bars[-1].bar_date)
                atr_est = float(t_ind_last.atr_14) if (t_ind_last and t_ind_last.atr_14) else fill_price * 0.025
            else:
                atr_est = fill_price * 0.025
            if stop_loss_price is None:
                stop_loss_price = round(max(0.01, fill_price - 2.0 * atr_est), 2)
            if take_profit_price is None:
                take_profit_price = round(fill_price + 3.5 * atr_est, 2)

        # Ensure stop-loss is strictly below fill_price and take-profit is strictly above fill_price
        if stop_loss_price is not None and stop_loss_price >= fill_price:
            stop_loss_price = round(max(0.01, fill_price * 0.95), 2)
        if take_profit_price is not None and take_profit_price <= fill_price:
            take_profit_price = round(fill_price * 1.08, 2)

        existing = self.db.fetch_one(
            "SELECT * FROM shadow_positions WHERE account_id = ? AND ticker = ?",
            (self.account_id, ticker_u),
        )
        if existing is not None:
            old_q = int(existing["quantity"])
            old_p = float(existing["avg_entry_price"])
            new_q = old_q + quantity
            new_avg = round(((old_q * old_p) + (quantity * fill_price)) / new_q, 4)
            high_p = max(float(existing["highest_price_since_entry"]), fill_price)
            self.db.execute(
                """
                UPDATE shadow_positions
                SET quantity = ?, avg_entry_price = ?, current_price = ?, highest_price_since_entry = ?,
                    stop_loss_price = COALESCE(?, stop_loss_price),
                    take_profit_price = COALESCE(?, take_profit_price),
                    updated_at = ?
                WHERE account_id = ? AND ticker = ?
                """,
                (new_q, new_avg, fill_price, high_p, stop_loss_price, take_profit_price, now_iso, self.account_id, ticker_u),
            )
        else:
            meta = self.market_data.get_universe_metadata(include_delisted=True).get(ticker_u)
            sec = meta.sector if meta else sector
            self.db.execute(
                """
                INSERT INTO shadow_positions (
                    account_id, ticker, strategy_id, strategy_version, sector,
                    quantity, avg_entry_price, current_price, highest_price_since_entry,
                    stop_loss_price, take_profit_price, opened_date, holding_days, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    self.account_id,
                    ticker_u,
                    strategy_id,
                    int(strategy_version),
                    sec,
                    int(quantity),
                    round(fill_price, 4),
                    round(fill_price, 4),
                    round(fill_price, 4),
                    round(stop_loss_price, 2) if stop_loss_price else None,
                    round(take_profit_price, 2) if take_profit_price else None,
                    dt_str,
                    notes or "Confirmed via Live Trading Copilot",
                    now_iso,
                ),
            )

        self.db.execute(
            "UPDATE shadow_accounts SET cash_balance = ?, starting_cash = ?, updated_at = ? WHERE account_id = ?",
            (new_cash, new_start, now_iso, self.account_id),
        )
        self.db.execute(
            """
            INSERT INTO shadow_trade_history (
                trade_id, account_id, strategy_id, strategy_version, ticker, side,
                fill_date, quantity, fill_price, fees_usd, realised_pnl, cash_after, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, 'BUY', ?, ?, ?, ?, 0.0, ?, ?, ?)
            """,
            (
                f"shd_{uuid.uuid4().hex[:12]}",
                self.account_id,
                strategy_id,
                int(strategy_version),
                ticker_u,
                dt_str,
                int(quantity),
                round(fill_price, 4),
                round(fees_usd, 2),
                new_cash,
                notes or f"Confirmed BUY {quantity} {ticker_u} @ ${fill_price:.2f}",
                now_iso,
            ),
        )
        return self.get_account_summary()

    def confirm_sell_execution(
        self,
        ticker: str,
        quantity: int,
        fill_price: float,
        fees_usd: float = 0.0,
        fill_date: Optional[str] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Record a user-confirmed real-account SELL execution, lock in realised P&L, and update cash."""
        ticker_u = ticker.strip().upper()
        existing = self.db.fetch_one(
            "SELECT * FROM shadow_positions WHERE account_id = ? AND ticker = ?",
            (self.account_id, ticker_u),
        )
        if existing is None:
            raise KeyError(f"Position {ticker_u} not found in real portfolio.")

        held_qty = int(existing["quantity"])
        sell_qty = min(held_qty, max(1, int(quantity)))
        avg_entry = float(existing["avg_entry_price"])
        proceeds = round(sell_qty * fill_price - fees_usd, 2)
        realised_delta = round((fill_price - avg_entry) * sell_qty - fees_usd, 2)

        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker)
        dt_str = fill_date or (spy_bars[-1].bar_date if spy_bars else utc_now_iso()[:10])
        now_iso = utc_now_iso()

        acc = self.ensure_initialized()
        new_cash = round(float(acc["cash_balance"]) + proceeds, 2)
        new_realised = round(float(acc["realised_pnl"]) + realised_delta, 2)

        if sell_qty >= held_qty:
            self.db.execute(
                "DELETE FROM shadow_positions WHERE account_id = ? AND ticker = ?",
                (self.account_id, ticker_u),
            )
        else:
            self.db.execute(
                "UPDATE shadow_positions SET quantity = ?, current_price = ?, updated_at = ? WHERE account_id = ? AND ticker = ?",
                (held_qty - sell_qty, round(fill_price, 4), now_iso, self.account_id, ticker_u),
            )

        self.db.execute(
            "UPDATE shadow_accounts SET cash_balance = ?, realised_pnl = ?, updated_at = ? WHERE account_id = ?",
            (new_cash, new_realised, now_iso, self.account_id),
        )
        self.db.execute(
            """
            INSERT INTO shadow_trade_history (
                trade_id, account_id, strategy_id, strategy_version, ticker, side,
                fill_date, quantity, fill_price, fees_usd, realised_pnl, cash_after, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, 'SELL', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"shd_{uuid.uuid4().hex[:12]}",
                self.account_id,
                existing["strategy_id"],
                int(existing["strategy_version"]),
                ticker_u,
                dt_str,
                sell_qty,
                round(fill_price, 4),
                round(fees_usd, 2),
                realised_delta,
                new_cash,
                notes or f"Confirmed SELL {sell_qty} {ticker_u} @ ${fill_price:.2f}",
                now_iso,
            ),
        )
        return self.get_account_summary()

    def edit_or_add_position(
        self,
        ticker: str,
        quantity: int,
        avg_entry_price: float,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        strategy_id: Optional[str] = None,
        strategy_version: Optional[int] = None,
        opened_date: Optional[str] = None,
        deduct_from_cash: bool = False,
    ) -> Dict[str, Any]:
        """Manually add, edit, or delete (quantity=0) a position in the user's real shadow ledger."""
        ticker_u = ticker.strip().upper()
        if not ticker_u:
            raise ValueError("Ticker cannot be empty.")
        now_iso = utc_now_iso()
        existing = self.db.fetch_one(
            "SELECT * FROM shadow_positions WHERE account_id = ? AND ticker = ?",
            (self.account_id, ticker_u),
        )
        old_cost = (int(existing["quantity"]) * float(existing["avg_entry_price"])) if existing is not None else 0.0
        eff_strat_id = str(strategy_id or (existing["strategy_id"] if existing is not None else "strat_momentum_trend"))
        eff_strat_ver = int(strategy_version if strategy_version is not None else (existing["strategy_version"] if existing is not None else 1))

        if quantity <= 0:
            self.db.execute(
                "DELETE FROM shadow_positions WHERE account_id = ? AND ticker = ?",
                (self.account_id, ticker_u),
            )
            if deduct_from_cash and old_cost > 0:
                acc = self.ensure_initialized()
                new_cash = round(float(acc["cash_balance"]) + old_cost, 2)
                self.db.execute(
                    "UPDATE shadow_accounts SET cash_balance = ?, updated_at = ? WHERE account_id = ?",
                    (new_cash, now_iso, self.account_id),
                )
            return self.get_account_summary()

        bars = self.market_data.get_bars(ticker_u)
        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker)
        latest_close = float(bars[-1].adj_close) if bars else avg_entry_price
        default_dt = (
            str(existing["opened_date"])
            if existing is not None
            else (bars[-1].bar_date if bars else (spy_bars[-1].bar_date if spy_bars else now_iso[:10]))
        )
        dt_str = opened_date or default_dt
        meta = self.market_data.get_universe_metadata(include_delisted=True).get(ticker_u)
        sec = meta.sector if meta else (str(existing["sector"]) if existing is not None else "Technology")

        ref_bars = bars if bars else spy_bars
        hold_days = sum(1 for b in ref_bars if b.bar_date > dt_str) if ref_bars else 0

        # Auto-compute default ATR stop/target if omitted
        if stop_loss_price is None or take_profit_price is None:
            if len(bars) >= 20:
                inds = compute_indicator_series(bars)
                ind_last = inds.get(bars[-1].bar_date)
                atr = float(ind_last.atr_14) if (ind_last and ind_last.atr_14) else avg_entry_price * 0.025
            else:
                atr = avg_entry_price * 0.025
            if stop_loss_price is None:
                stop_loss_price = round(max(0.01, avg_entry_price - 2.0 * atr), 2)
            if take_profit_price is None:
                take_profit_price = round(avg_entry_price + 3.5 * atr, 2)

        high_since = max(
            round(avg_entry_price, 4),
            round(latest_close, 4),
            float(existing["highest_price_since_entry"]) if existing is not None else 0.0,
        )
        self.db.execute(
            """
            INSERT INTO shadow_positions (
                account_id, ticker, strategy_id, strategy_version, sector,
                quantity, avg_entry_price, current_price, highest_price_since_entry,
                stop_loss_price, take_profit_price, opened_date, holding_days, notes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Manual position edit/entry', ?)
            ON CONFLICT(account_id, ticker) DO UPDATE SET
                strategy_id=excluded.strategy_id,
                strategy_version=excluded.strategy_version,
                quantity=excluded.quantity,
                avg_entry_price=excluded.avg_entry_price,
                current_price=excluded.current_price,
                highest_price_since_entry=excluded.highest_price_since_entry,
                stop_loss_price=excluded.stop_loss_price,
                take_profit_price=excluded.take_profit_price,
                opened_date=excluded.opened_date,
                holding_days=excluded.holding_days,
                updated_at=excluded.updated_at
            """,
            (
                self.account_id,
                ticker_u,
                eff_strat_id,
                eff_strat_ver,
                sec,
                int(quantity),
                round(avg_entry_price, 4),
                round(latest_close, 4),
                high_since,
                round(stop_loss_price, 2) if stop_loss_price else None,
                round(take_profit_price, 2) if take_profit_price else None,
                dt_str,
                int(hold_days),
                now_iso,
            ),
        )
        if deduct_from_cash:
            acc = self.ensure_initialized()
            cur_cash = float(acc["cash_balance"])
            cur_start = float(acc["starting_cash"])
            new_cost = round(quantity * avg_entry_price, 2)
            cost_delta = round(new_cost - old_cost, 2)
            if cost_delta > cur_cash:
                shortfall = round(cost_delta - cur_cash, 2)
                new_cash = 0.0
                new_start = round(cur_start + shortfall, 2)
            else:
                new_cash = max(0.0, round(cur_cash - cost_delta, 2))
                new_start = cur_start
            self.db.execute(
                "UPDATE shadow_accounts SET cash_balance = ?, starting_cash = ?, updated_at = ? WHERE account_id = ?",
                (new_cash, new_start, now_iso, self.account_id),
            )
        return self.get_account_summary()

    def undo_last_trade(self) -> Dict[str, Any]:
        """Reverse the most recently confirmed BUY or SELL fill in the user's real shadow ledger."""
        last_trade = self.db.fetch_one(
            "SELECT * FROM shadow_trade_history WHERE account_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (self.account_id,),
        )
        if last_trade is None:
            return self.get_account_summary()

        trade_id = str(last_trade["trade_id"])
        ticker_u = str(last_trade["ticker"]).upper()
        side = str(last_trade["side"]).upper()
        qty = int(last_trade["quantity"])
        fill_price = float(last_trade["fill_price"])
        fees_usd = float(last_trade["fees_usd"])
        realised_delta = float(last_trade["realised_pnl"])
        strat_id = str(last_trade["strategy_id"])
        strat_ver = int(last_trade["strategy_version"])
        fill_date = str(last_trade["fill_date"])
        now_iso = utc_now_iso()

        acc = self.ensure_initialized()
        cur_cash = float(acc["cash_balance"])
        cur_realised = float(acc["realised_pnl"])
        existing = self.db.fetch_one(
            "SELECT * FROM shadow_positions WHERE account_id = ? AND ticker = ?",
            (self.account_id, ticker_u),
        )

        if side == "BUY":
            cost_refund = round(qty * fill_price + fees_usd, 2)
            new_cash = round(cur_cash + cost_refund, 2)
            if existing is not None:
                rem_qty = int(existing["quantity"]) - qty
                if rem_qty <= 0:
                    self.db.execute(
                        "DELETE FROM shadow_positions WHERE account_id = ? AND ticker = ?",
                        (self.account_id, ticker_u),
                    )
                else:
                    old_total = int(existing["quantity"]) * float(existing["avg_entry_price"])
                    restored_avg = max(0.01, round((old_total - (qty * fill_price)) / rem_qty, 4))
                    self.db.execute(
                        "UPDATE shadow_positions SET quantity = ?, avg_entry_price = ?, updated_at = ? WHERE account_id = ? AND ticker = ?",
                        (rem_qty, restored_avg, now_iso, self.account_id, ticker_u),
                    )
            self.db.execute(
                "UPDATE shadow_accounts SET cash_balance = ?, updated_at = ? WHERE account_id = ?",
                (new_cash, now_iso, self.account_id),
            )
        elif side == "SELL":
            proceeds = round(qty * fill_price - fees_usd, 2)
            new_cash = max(0.0, round(cur_cash - proceeds, 2))
            new_realised = round(cur_realised - realised_delta, 2)
            inferred_entry = round(fill_price - ((realised_delta + fees_usd) / max(1, qty)), 4)
            if existing is not None:
                new_q = int(existing["quantity"]) + qty
                self.db.execute(
                    "UPDATE shadow_positions SET quantity = ?, updated_at = ? WHERE account_id = ? AND ticker = ?",
                    (new_q, now_iso, self.account_id, ticker_u),
                )
            else:
                meta = self.market_data.get_universe_metadata(include_delisted=True).get(ticker_u)
                sec = meta.sector if meta else "Technology"
                t_bars = self.market_data.get_bars(ticker_u)
                if len(t_bars) >= 20:
                    t_inds = compute_indicator_series(t_bars)
                    t_ind_last = t_inds.get(t_bars[-1].bar_date)
                    atr_est = float(t_ind_last.atr_14) if (t_ind_last and t_ind_last.atr_14) else inferred_entry * 0.025
                else:
                    atr_est = inferred_entry * 0.025
                rest_sl = round(max(0.01, inferred_entry - 2.0 * atr_est), 2)
                rest_tp = round(inferred_entry + 3.5 * atr_est, 2)
                self.db.execute(
                    """
                    INSERT INTO shadow_positions (
                        account_id, ticker, strategy_id, strategy_version, sector,
                        quantity, avg_entry_price, current_price, highest_price_since_entry,
                        stop_loss_price, take_profit_price, opened_date, holding_days, notes, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'Restored via Undo Last Trade', ?)
                    """,
                    (
                        self.account_id,
                        ticker_u,
                        strat_id,
                        strat_ver,
                        sec,
                        qty,
                        inferred_entry,
                        fill_price,
                        max(inferred_entry, fill_price),
                        rest_sl,
                        rest_tp,
                        fill_date,
                        now_iso,
                    ),
                )
            self.db.execute(
                "UPDATE shadow_accounts SET cash_balance = ?, realised_pnl = ?, updated_at = ? WHERE account_id = ?",
                (new_cash, new_realised, now_iso, self.account_id),
            )

        self.db.execute(
            "DELETE FROM shadow_trade_history WHERE account_id = ? AND trade_id = ?",
            (self.account_id, trade_id),
        )
        return self.get_account_summary()

    def update_position_brackets(
        self,
        ticker: str,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update only the stop-loss and take-profit bracket prices on an existing open holding without altering cash or shares."""
        ticker_u = ticker.strip().upper()
        self.db.execute(
            """
            UPDATE shadow_positions
            SET stop_loss_price = COALESCE(?, stop_loss_price),
                take_profit_price = COALESCE(?, take_profit_price),
                updated_at = ?
            WHERE account_id = ? AND ticker = ?
            """,
            (
                round(float(stop_loss_price), 2) if stop_loss_price and stop_loss_price > 0 else None,
                round(float(take_profit_price), 2) if take_profit_price and take_profit_price > 0 else None,
                utc_now_iso(),
                self.account_id,
                ticker_u,
            ),
        )
        return self.get_account_summary()

    def reconcile_from_trade_ledger(self) -> Dict[str, Any]:
        """Deterministically recompute cash_balance, open shadow_positions, and realised_pnl by replaying all trades from starting_cash."""
        acc = self.ensure_initialized()
        start_cash = round(float(acc["starting_cash"]), 2)
        now_iso = utc_now_iso()

        # Preserve any custom stop-loss / take-profit brackets set on existing positions
        existing_pos_rows = self.db.fetch_all(
            "SELECT * FROM shadow_positions WHERE account_id = ?",
            (self.account_id,),
        )
        saved_brackets: Dict[str, Tuple[Optional[float], Optional[float], str]] = {
            str(r["ticker"]).upper(): (
                float(r["stop_loss_price"]) if r.get("stop_loss_price") is not None else None,
                float(r["take_profit_price"]) if r.get("take_profit_price") is not None else None,
                str(r.get("sector") or "Technology"),
            )
            for r in existing_pos_rows
        }

        trades = self.db.fetch_all(
            """
            SELECT * FROM shadow_trade_history
            WHERE account_id = ?
            ORDER BY fill_date ASC, created_at ASC, rowid ASC
            """,
            (self.account_id,),
        )

        cash = start_cash
        total_realised = 0.0
        holdings: Dict[str, Dict[str, Any]] = {}

        for tr in trades:
            tid = str(tr["trade_id"])
            tkr = str(tr["ticker"]).strip().upper()
            side = str(tr["side"]).strip().upper()
            qty = max(1, int(tr["quantity"]))
            px = round(float(tr["fill_price"]), 4)
            fees = round(float(tr.get("fees_usd") or 0.0), 2)
            fdate = str(tr["fill_date"])
            sid = str(tr.get("strategy_id") or "strat_volatility_breakout")
            sver = int(tr.get("strategy_version") or 1)

            if side == "BUY":
                cost = round(qty * px + fees, 2)
                if cost > cash:
                    shortfall = round(cost - cash, 2)
                    start_cash = round(start_cash + shortfall, 2)
                    cash = 0.0
                else:
                    cash = round(cash - cost, 2)

                if tkr in holdings:
                    h = holdings[tkr]
                    old_q = int(h["quantity"])
                    old_p = float(h["avg_entry_price"])
                    new_q = old_q + qty
                    h["avg_entry_price"] = round(((old_q * old_p) + (qty * px)) / new_q, 4)
                    h["quantity"] = new_q
                    h["highest_price"] = max(float(h["highest_price"]), px)
                else:
                    holdings[tkr] = {
                        "ticker": tkr,
                        "strategy_id": sid,
                        "strategy_version": sver,
                        "quantity": qty,
                        "avg_entry_price": px,
                        "highest_price": px,
                        "opened_date": fdate,
                    }
                self.db.execute(
                    "UPDATE shadow_trade_history SET realised_pnl = 0.0, cash_after = ? WHERE account_id = ? AND trade_id = ?",
                    (cash, self.account_id, tid),
                )
            elif side == "SELL":
                h = holdings.get(tkr)
                avg_entry = float(h["avg_entry_price"]) if h is not None else px
                sell_qty = min(int(h["quantity"]), qty) if h is not None else qty
                proceeds = round(sell_qty * px - fees, 2)
                realised_delta = round((px - avg_entry) * sell_qty - fees, 2)
                cash = round(cash + proceeds, 2)
                total_realised = round(total_realised + realised_delta, 2)
                if h is not None:
                    rem = int(h["quantity"]) - sell_qty
                    if rem <= 0:
                        del holdings[tkr]
                    else:
                        h["quantity"] = rem
                self.db.execute(
                    "UPDATE shadow_trade_history SET quantity = ?, realised_pnl = ?, cash_after = ? WHERE account_id = ? AND trade_id = ?",
                    (sell_qty, realised_delta, cash, self.account_id, tid),
                )

        # Rebuild shadow_positions from replayed holdings
        self.db.execute("DELETE FROM shadow_positions WHERE account_id = ?", (self.account_id,))
        universe_meta = self.market_data.get_universe_metadata(include_delisted=True)
        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker)

        for tkr, h in holdings.items():
            bars = self.market_data.get_bars(tkr)
            latest_close = float(bars[-1].adj_close) if bars else float(h["avg_entry_price"])
            ref_bars = bars if bars else spy_bars
            hold_days = sum(1 for b in ref_bars if b.bar_date > h["opened_date"]) if ref_bars else 0
            high_since = max(
                float(h["highest_price"]),
                latest_close,
                max((float(b.adj_high) for b in bars if b.bar_date >= h["opened_date"]), default=latest_close),
            )
            saved_sl, saved_tp, saved_sec = saved_brackets.get(tkr, (None, None, "Technology"))
            meta = universe_meta.get(tkr)
            sec = meta.sector if meta else saved_sec

            avg_entry_val = float(h["avg_entry_price"])
            if saved_sl is None or saved_tp is None or saved_sl >= avg_entry_val or saved_tp <= avg_entry_val:
                if len(bars) >= 20:
                    inds = compute_indicator_series(bars)
                    ind_last = inds.get(bars[-1].bar_date)
                    atr = float(ind_last.atr_14) if (ind_last and ind_last.atr_14) else avg_entry_val * 0.025
                else:
                    atr = avg_entry_val * 0.025
                if saved_sl is None or saved_sl >= avg_entry_val:
                    saved_sl = round(max(0.01, avg_entry_val - 2.0 * atr), 2)
                if saved_tp is None or saved_tp <= avg_entry_val:
                    saved_tp = round(avg_entry_val + 3.5 * atr, 2)

            self.db.execute(
                """
                INSERT INTO shadow_positions (
                    account_id, ticker, strategy_id, strategy_version, sector,
                    quantity, avg_entry_price, current_price, highest_price_since_entry,
                    stop_loss_price, take_profit_price, opened_date, holding_days, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Reconciled from Trade Ledger', ?)
                """,
                (
                    self.account_id,
                    tkr,
                    h["strategy_id"],
                    int(h["strategy_version"]),
                    sec,
                    int(h["quantity"]),
                    round(float(h["avg_entry_price"]), 4),
                    round(latest_close, 4),
                    round(high_since, 4),
                    round(saved_sl, 2) if saved_sl else None,
                    round(saved_tp, 2) if saved_tp else None,
                    h["opened_date"],
                    int(hold_days),
                    now_iso,
                ),
            )

        self.db.execute(
            """
            UPDATE shadow_accounts
            SET starting_cash = ?, cash_balance = ?, realised_pnl = ?, updated_at = ?
            WHERE account_id = ?
            """,
            (start_cash, cash, total_realised, now_iso, self.account_id),
        )
        return self.get_account_summary()

    def edit_trade(
        self,
        trade_id: str,
        ticker: str,
        side: str,
        quantity: int,
        fill_price: float,
        fees_usd: float = 0.0,
        fill_date: Optional[str] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Edit an existing trade in shadow_trade_history (or delete if quantity <= 0) and reconcile cash, positions, and P&L."""
        if int(quantity) <= 0:
            return self.delete_trade(trade_id)
        if float(fill_price) <= 0:
            raise ValueError("Fill price must be positive.")
        ticker_u = ticker.strip().upper()
        side_u = side.strip().upper()
        if side_u not in ("BUY", "SELL"):
            raise ValueError("Side must be BUY or SELL.")

        existing = self.db.fetch_one(
            "SELECT * FROM shadow_trade_history WHERE account_id = ? AND trade_id = ?",
            (self.account_id, trade_id),
        )
        if existing is None:
            raise KeyError(f"Trade {trade_id} not found.")

        dt_str = (fill_date or str(existing["fill_date"])).strip()
        new_notes = notes if notes is not None else f"Edited {side_u} {int(quantity)} {ticker_u} @ ${float(fill_price):.2f}"
        self.db.execute(
            """
            UPDATE shadow_trade_history
            SET ticker = ?, side = ?, quantity = ?, fill_price = ?, fees_usd = ?, fill_date = ?, notes = ?
            WHERE account_id = ? AND trade_id = ?
            """,
            (
                ticker_u,
                side_u,
                int(quantity),
                round(float(fill_price), 4),
                round(float(fees_usd), 2),
                dt_str,
                new_notes,
                self.account_id,
                trade_id,
            ),
        )
        summary = self.reconcile_from_trade_ledger()
        if side_u == "BUY" and (stop_loss_price or take_profit_price):
            summary = self.update_position_brackets(ticker_u, stop_loss_price, take_profit_price)
        return summary

    def delete_trade(self, trade_id: str) -> Dict[str, Any]:
        """Remove a trade from shadow_trade_history and reconcile cash_balance, open positions, and realised_pnl."""
        self.db.execute(
            "DELETE FROM shadow_trade_history WHERE account_id = ? AND trade_id = ?",
            (self.account_id, trade_id),
        )
        return self.reconcile_from_trade_ledger()

    def reset_copilot_account(self, starting_cash: Optional[float] = None) -> Dict[str, Any]:
        """Clear all shadow positions, trade history, and dismissed signals, resetting cash to starting_cash."""
        acc = self.ensure_initialized()
        base_cash = round(float(starting_cash if starting_cash is not None else acc["starting_cash"]), 2)
        now_iso = utc_now_iso()
        self.db.execute("DELETE FROM shadow_positions WHERE account_id = ?", (self.account_id,))
        self.db.execute("DELETE FROM shadow_trade_history WHERE account_id = ?", (self.account_id,))
        self.db.execute("DELETE FROM shadow_dismissed_signals WHERE account_id = ?", (self.account_id,))
        self.db.execute(
            """
            UPDATE shadow_accounts
            SET starting_cash = ?, cash_balance = ?, realised_pnl = 0.0, enabled_strategies_json = '[]', updated_at = ?
            WHERE account_id = ?
            """,
            (base_cash, base_cash, now_iso, self.account_id),
        )
        return self.get_account_summary()

    def get_daily_action_plan(
        self,
        as_of_date: Optional[str] = None,
        check_calendar_today: bool = False,
        custom_account_summary: Optional[Dict[str, Any]] = None,
        custom_open_positions: Optional[List[Dict[str, Any]]] = None,
        custom_strategies: Optional[Sequence[StrategyConfig]] = None,
    ) -> Dict[str, Any]:
        """Compute step-by-step SELL and BUY recommendations tailored to a real or paper account."""
        calendar_today_str = as_of_date or date.today().isoformat()
        try:
            calendar_today_dt = date.fromisoformat(calendar_today_str[:10])
        except ValueError:
            calendar_today_dt = date.today()
            calendar_today_str = calendar_today_dt.isoformat()

        is_today_trading_day = USTradingCalendar.is_trading_day(calendar_today_dt)
        market_status_reason = USTradingCalendar.non_trading_reason(calendar_today_dt)
        next_open_session = USTradingCalendar.next_trading_day(
            calendar_today_dt, include_same_day=is_today_trading_day
        )

        if as_of_date is None and hasattr(self.market_data, "ensure_latest_market_data"):
            self.market_data.ensure_latest_market_data()

        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker, end_date=as_of_date)
        session_date = spy_bars[-1].bar_date if spy_bars else calendar_today_str
        spy_inds = compute_indicator_series(spy_bars) if spy_bars else {}

        summary = dict(custom_account_summary) if custom_account_summary is not None else self.get_account_summary(as_of_date=session_date)
        open_positions = list(custom_open_positions) if custom_open_positions is not None else self.get_open_positions()
        open_by_ticker = {p["ticker"]: p for p in open_positions}

        if custom_account_summary is not None:
            dismissed_set: set[Tuple[str, str, str]] = set()
        else:
            dismissed_rows = self.db.fetch_all(
                "SELECT strategy_id, ticker, action FROM shadow_dismissed_signals WHERE account_id = ? AND signal_date = ?",
                (self.account_id, session_date),
            )
            dismissed_set = {(r["strategy_id"], r["ticker"], r["action"]) for r in dismissed_rows}

        all_strats = self.registry.list_strategies()
        strat_by_key = {f"{s.strategy_id}:{s.version}": s for s in all_strats}
        strat_by_id_latest: Dict[str, StrategyConfig] = {}
        for s in all_strats:
            prev = strat_by_id_latest.get(s.strategy_id)
            if prev is None or (s.status == "PAPER_TRADING" and prev.status != "PAPER_TRADING") or s.version > prev.version:
                strat_by_id_latest[s.strategy_id] = s

        def _champion_score(s: StrategyConfig) -> float:
            bs = s.backtest_summary or {}
            sqn = float(bs.get("sqn_score") or bs.get("sharpe_ratio") or 0.0)
            r6m = float(bs.get("recent_6m_return_pct") or 0.0)
            wr6m = float(bs.get("recent_6m_win_rate_pct") or bs.get("win_rate_pct") or 0.0)
            tot = float(bs.get("total_return_pct") or 0.0)
            return round(sqn * 10.0 + r6m * 1.0 + wr6m * 0.2 + tot * 0.1, 4)

        paper_strats = [s for s in strat_by_id_latest.values() if s.status in ("PAPER_TRADING", "APPROVED_FOR_REVIEW")]
        if not paper_strats:
            paper_strats = list(strat_by_id_latest.values())
        ranked_champions = sorted(paper_strats, key=_champion_score, reverse=True)
        best_champion = ranked_champions[0] if ranked_champions else (all_strats[0] if all_strats else None)

        enabled_keys = summary.get("enabled_strategies") or []
        if custom_strategies is not None:
            active_strats = list(custom_strategies)
        elif enabled_keys:
            active_strats = [strat_by_key[k] for k in enabled_keys if k in strat_by_key]
        else:
            # Default: Stick to the #1 Best Champion Strategy (with automatic fallback to #2 only if #1 has 0 signals today)
            active_strats = [best_champion] if best_champion is not None else []

        # Deduplicate by strategy_id (keep highest version) and preserve champion ranking order
        deduped_strats: List[StrategyConfig] = []
        seen_active_ids: set[str] = set()
        for s in sorted(active_strats, key=_champion_score, reverse=True):
            if s.strategy_id not in seen_active_ids:
                seen_active_ids.add(s.strategy_id)
                deduped_strats.append(s)
        if not deduped_strats and best_champion is not None:
            deduped_strats = [best_champion]
        fallback_strat = best_champion or (deduped_strats[0] if deduped_strats else None)

        active_champion_info: Dict[str, Any] = {}
        if best_champion is not None:
            bs = best_champion.backtest_summary or {}
            active_champion_info = {
                "strategy_id": best_champion.strategy_id,
                "version": best_champion.version,
                "name": best_champion.name,
                "sqn_score": round(float(bs.get("sqn_score") or 0.0), 2),
                "recent_6m_return_pct": round(float(bs.get("recent_6m_return_pct") or 0.0), 2),
                "recent_6m_win_rate_pct": round(float(bs.get("recent_6m_win_rate_pct") or bs.get("win_rate_pct") or 0.0), 1),
                "total_return_pct": round(float(bs.get("total_return_pct") or 0.0), 2),
            }

        # Load latest point-in-time AI / news catalyst sentiment per ticker.
        # In live/pre-open mode (as_of_date is None), include catalysts published up to today (weekend/pre-market AI runs).
        catalyst_cutoff_date = max(session_date, calendar_today_str) if as_of_date is None else session_date
        catalyst_rows = self.db.fetch_all(
            """
            SELECT ticker, headline, summary, sentiment_score, source_name, catalyst_type, published_date
            FROM market_catalysts
            WHERE published_date <= ?
            ORDER BY published_date DESC, id DESC
            LIMIT 250
            """,
            (catalyst_cutoff_date,),
        )
        latest_catalyst_by_tkr: Dict[str, Dict[str, Any]] = {}
        for crow in catalyst_rows:
            t_key = str(crow["ticker"]).upper()
            if t_key not in latest_catalyst_by_tkr:
                latest_catalyst_by_tkr[t_key] = dict(crow)

        # 1. Evaluate SELL / HOLD status for every confirmed position the user actually holds
        #    Always uses the exact strategy (pos['strategy_id'] v{pos['strategy_version']}) that opened the position,
        #    plus Emergency AI Bearish Catalyst Exit (sentiment <= -0.50 from IDE AI research).
        use_live_quotes_plan = (
            "unittest" not in sys.modules
            and hasattr(self.market_data, "fetch_live_quote_snapshots")
            and (as_of_date is None or as_of_date >= session_date)
        )
        pos_live_snapshots: Dict[str, Dict[str, Any]] = {}
        if use_live_quotes_plan and open_positions:
            try:
                pos_live_snapshots = self.market_data.fetch_live_quote_snapshots([str(p["ticker"]) for p in open_positions])
            except Exception:
                pos_live_snapshots = {}

        open_window_35_sgt = (
            USTradingCalendar.market_open_window_sgt(35, calendar_today_dt)
            if hasattr(USTradingCalendar, "market_open_window_sgt")
            else "10:30–10:35 PM SGT"
        )
        open_window_45_sgt = (
            USTradingCalendar.market_open_window_sgt(45, calendar_today_dt)
            if hasattr(USTradingCalendar, "market_open_window_sgt")
            else "10:30–10:45 PM SGT"
        )
        open_time_sgt = (
            USTradingCalendar.market_open_sgt(calendar_today_dt)
            if hasattr(USTradingCalendar, "market_open_sgt")
            else "10:30 PM SGT"
        )

        sell_actions: List[Dict[str, Any]] = []
        hold_updates: List[Dict[str, Any]] = []
        for pos in open_positions:
            ticker = pos["ticker"]
            if (pos["strategy_id"], ticker, "SELL") in dismissed_set:
                continue
            bars = self.market_data.get_bars(ticker, end_date=session_date)
            if not bars:
                continue
            inds = compute_indicator_series(bars, spy_bars=spy_bars)
            ind_today = inds.get(bars[-1].bar_date)
            if ind_today is None:
                continue
            strat = (
                strat_by_key.get(f"{pos['strategy_id']}:{pos['strategy_version']}")
                or strat_by_id_latest.get(str(pos["strategy_id"]))
                or fallback_strat
            )
            if strat is None:
                continue

            exit_sig = StrategySignalEngine.evaluate_exit(
                config=strat,
                ind=ind_today,
                entry_price=float(pos["avg_entry_price"]),
                highest_price_since_entry=float(pos["highest_price_since_entry"]),
                holding_days=int(pos["holding_days"]),
                stop_loss_price=float(pos["stop_loss_price"]) if pos.get("stop_loss_price") else None,
                take_profit_price=float(pos["take_profit_price"]) if pos.get("take_profit_price") else None,
            )
            pos_cat = latest_catalyst_by_tkr.get(ticker.upper())
            pos_ai_sent = float(pos_cat["sentiment_score"]) if (pos_cat and pos_cat.get("sentiment_score") is not None) else 0.0
            pos_ai_note = str(pos_cat.get("headline") or pos_cat.get("summary") or "") if pos_cat else ""
            ai_emergency_exit_reason = (
                f"AI Bearish Catalyst Protection (Sentiment {pos_ai_sent:+.2f}): {pos_ai_note[:95]}"
                if (pos_cat and pos_ai_sent <= -0.50 and str(pos_cat.get("catalyst_type") or "") == "IDE_AI_RESEARCH")
                else None
            )
            effective_exit_reason = exit_sig.reason if exit_sig is not None else ai_emergency_exit_reason
            pos_snap = pos_live_snapshots.get(str(ticker).upper()) or {}
            ref_exit_px = round(
                float(pos_snap.get("indicative_price") or pos.get("current_price") or bars[-1].adj_close),
                2,
            )

            if effective_exit_reason is not None and not (check_calendar_today and not is_today_trading_day):
                est_pnl_val = round(
                    (ref_exit_px - float(pos["avg_entry_price"])) * int(pos["quantity"]), 2
                )
                sell_factors = [
                    f"Exit Trigger: {effective_exit_reason}",
                    f"Entry Strategy Rule: Bound to {pos['strategy_id']} v{pos['strategy_version']} ({int(pos['holding_days'])}d held)",
                    f"P&L Outcome: Entry ${float(pos['avg_entry_price']):.2f} → Ref Exit ${ref_exit_px:.2f} ({est_pnl_val:+,.2f})",
                ]
                sell_actions.append(
                    {
                        "action": "SELL",
                        "ticker": ticker,
                        "sector": pos["sector"],
                        "strategy_id": pos["strategy_id"],
                        "strategy_version": pos["strategy_version"],
                        "quantity_to_sell": int(pos["quantity"]),
                        "avg_entry_price": float(pos["avg_entry_price"]),
                        "reference_exit_price": ref_exit_px,
                        "estimated_realised_pnl": est_pnl_val,
                        "holding_days": int(pos["holding_days"]),
                        "reason": effective_exit_reason,
                        "why_summary": f"Close {int(pos['quantity'])} {ticker}: {effective_exit_reason}",
                        "factors_considered": sell_factors,
                        "order_timing_guidance": f"Execute Market or Limit-at-Bid Order at Market Open ({open_window_35_sgt} / 9:30–9:35 AM ET)",
                        "signal_date": session_date,
                    }
                )
            else:
                max_hold = strat.holding_period_max_days
                days_left = max(0, max_hold - int(pos["holding_days"]))
                eff_stop, stop_mode = StrategySignalEngine.compute_effective_stop_price(
                    config=strat,
                    entry_price=float(pos["avg_entry_price"]),
                    highest_price_since_entry=float(pos["highest_price_since_entry"]),
                    holding_days=int(pos["holding_days"]),
                    initial_stop_price=float(pos["stop_loss_price"]) if pos.get("stop_loss_price") else None,
                    atr_14=float(ind_today.atr_14) if (ind_today and ind_today.atr_14) else float(pos["avg_entry_price"]) * 0.02,
                )
                stop_note = ""
                if stop_mode != "Initial ATR Stop" and eff_stop is not None:
                    stop_note = f" · Raise Stop → ${eff_stop:.2f} ({stop_mode})"
                hold_updates.append(
                    {
                        "ticker": ticker,
                        "strategy": f"{pos['strategy_id']} v{pos['strategy_version']}",
                        "strategy_name": strat.name,
                        "quantity": int(pos["quantity"]),
                        "avg_entry_price": float(pos["avg_entry_price"]),
                        "current_price": float(pos["current_price"]),
                        "unrealised_pnl": float(pos["unrealised_pnl"]),
                        "stop_loss_price": eff_stop if eff_stop is not None else pos.get("stop_loss_price"),
                        "initial_stop_price": pos.get("stop_loss_price"),
                        "stop_mode": stop_mode,
                        "take_profit_price": pos.get("take_profit_price"),
                        "status": f"HOLD ({days_left}d left{stop_note})",
                    }
                )

        # If check_calendar_today=True and today is a weekend or market holiday, do not suggest new trades today
        if check_calendar_today and not is_today_trading_day:
            return {
                "calendar_date": calendar_today_str,
                "is_trading_day": False,
                "market_status_reason": market_status_reason,
                "next_trading_day": next_open_session,
                "session_date": session_date,
                "account_summary": summary,
                "active_champion": active_champion_info,
                "sell_actions": [],
                "buy_actions": [],
                "hold_updates": hold_updates,
                "vetoed_signals": [],
                "dismissed_count": len(dismissed_set),
            }

        # 2. Evaluate BUY signals sized to the user's real account equity & cash
        buy_actions: List[Dict[str, Any]] = []
        vetoed_signals: List[Dict[str, Any]] = []
        universe_meta = self.market_data.get_universe_metadata(include_delisted=True)

        # Compute sector momentum rank map for SECTOR_ROTATION strategies
        candidate_strats_for_scan = list(deduped_strats)
        if not enabled_keys:
            existing_ids = {s.strategy_id for s in candidate_strats_for_scan}
            for rc in ranked_champions[1:]:
                if rc.strategy_id not in existing_ids:
                    candidate_strats_for_scan.append(rc)
                    existing_ids.add(rc.strategy_id)
        all_universe_tickers = sorted({t for s in candidate_strats_for_scan for t in s.universe if t != self.settings.benchmark_ticker})
        bars_by_tkr: Dict[str, List[DailyBar]] = {}
        inds_by_tkr: Dict[str, Dict[str, Any]] = {}
        sector_rs_buckets: Dict[str, List[float]] = {}
        for tkr in all_universe_tickers:
            b_list = self.market_data.get_bars(tkr, end_date=session_date)
            if len(b_list) < 25:
                continue
            bars_by_tkr[tkr] = b_list
            ind_map = compute_indicator_series(b_list, spy_bars=spy_bars)
            inds_by_tkr[tkr] = ind_map
            ind_dt = ind_map.get(b_list[-1].bar_date)
            if ind_dt and ind_dt.rs_vs_spy_20d is not None:
                m_meta = universe_meta.get(tkr)
                sec_name = m_meta.sector if m_meta else "Technology"
                sector_rs_buckets.setdefault(sec_name, []).append(float(ind_dt.rs_vs_spy_20d))
        sector_avg = {
            sec: (sum(sorted(vals, reverse=True)[:2]) / min(2, len(vals)))
            for sec, vals in sector_rs_buckets.items()
            if vals
        }
        sorted_secs = sorted(sector_avg.items(), key=lambda kv: kv[1], reverse=True)
        sector_rank_map = {sec: idx + 1 for idx, (sec, _) in enumerate(sorted_secs)}

        # Simulate remaining cash/exposure as recommendations are queued so total recommendations respect user's caps.
        # Credit proceeds and free sector/heat slots from any positions scheduled to be sold first in Step 2A.
        sim_cash = float(summary["cash_balance"])
        sim_open_map = dict(open_by_ticker)
        exiting_tickers: set[str] = set()
        for sa_item in sell_actions:
            ex_tkr = str(sa_item["ticker"])
            exiting_tickers.add(ex_tkr)
            sim_cash = round(sim_cash + float(sa_item["quantity_to_sell"]) * float(sa_item["reference_exit_price"]), 2)
            sim_open_map.pop(ex_tkr, None)
        total_eq = max(1.0, float(summary["total_equity"]))

        # Collect signals from primary active strategy(s); if in auto-champion mode and #1 Champion has 0 signals today,
        # automatically fallback to #2 Uncorrelated Champion (e.g. Mean Reversion on market pullback days)
        signals_by_strat: Dict[str, List[Tuple[StrategyConfig, str, DailyBar, Any]]] = {}
        for strat in deduped_strats:
            bucket: List[Tuple[StrategyConfig, str, DailyBar, Any]] = []
            for ticker in strat.universe:
                if ticker == self.settings.benchmark_ticker or ticker in sim_open_map or ticker in exiting_tickers:
                    continue
                if (strat.strategy_id, ticker, "BUY") in dismissed_set:
                    continue
                bars = bars_by_tkr.get(ticker)
                if not bars or len(bars) < 25:
                    continue
                latest_bar = bars[-1]
                inds = inds_by_tkr.get(ticker) or {}
                ind_latest = inds.get(latest_bar.bar_date)
                if ind_latest is None:
                    continue
                pead_lookback = max(20, int(strat.entry_rules.get("max_days_since_earnings", 10)) + 5)
                recent_ev = self.market_data.get_point_in_time_earnings(
                    ticker, latest_bar.bar_date, lookback_days=pead_lookback
                )
                m_meta = universe_meta.get(ticker)
                sec_name = m_meta.sector if m_meta else "Technology"
                sec_rank = sector_rank_map.get(sec_name, 1)
                sig = StrategySignalEngine.evaluate_entry(
                    config=strat,
                    ind=ind_latest,
                    spy_ind=spy_inds.get(latest_bar.bar_date),
                    recent_earnings=recent_ev,
                    sector_rs_rank=sec_rank,
                )
                if sig is not None:
                    bucket.append((strat, ticker, latest_bar, sig))
            bucket.sort(key=lambda item: float(item[3].conviction_score), reverse=True)
            if bucket:
                signals_by_strat[strat.strategy_id] = bucket

        # Automatic Regime Fallback: if #1 Champion has 0 signals today (e.g. market pullback), prioritize MEAN_REVERSION then remaining champions
        # Only trigger when in auto-champion mode (custom_strategies is None and no manual enabled_keys override)
        if not signals_by_strat and not enabled_keys and custom_strategies is None and len(ranked_champions) >= 2:
            fallback_candidates = sorted(
                ranked_champions[1:],
                key=lambda s: (0 if s.strategy_family == "MEAN_REVERSION" else 1, -_champion_score(s)),
            )
            for fallback_runner in fallback_candidates:
                bucket_fb: List[Tuple[StrategyConfig, str, DailyBar, Any]] = []
                for ticker in fallback_runner.universe:
                    if ticker == self.settings.benchmark_ticker or ticker in sim_open_map or ticker in exiting_tickers:
                        continue
                    if (fallback_runner.strategy_id, ticker, "BUY") in dismissed_set:
                        continue
                    bars = bars_by_tkr.get(ticker)
                    if not bars or len(bars) < 25:
                        continue
                    latest_bar = bars[-1]
                    inds = inds_by_tkr.get(ticker) or {}
                    ind_latest = inds.get(latest_bar.bar_date)
                    if ind_latest is None:
                        continue
                    pead_lookback = max(20, int(fallback_runner.entry_rules.get("max_days_since_earnings", 10)) + 5)
                    recent_ev = self.market_data.get_point_in_time_earnings(
                        ticker, latest_bar.bar_date, lookback_days=pead_lookback
                    )
                    m_meta = universe_meta.get(ticker)
                    sec_name = m_meta.sector if m_meta else "Technology"
                    sec_rank = sector_rank_map.get(sec_name, 1)
                    sig = StrategySignalEngine.evaluate_entry(
                        config=fallback_runner,
                        ind=ind_latest,
                        spy_ind=spy_inds.get(latest_bar.bar_date),
                        recent_earnings=recent_ev,
                        sector_rs_rank=sec_rank,
                    )
                    if sig is not None:
                        bucket_fb.append((fallback_runner, ticker, latest_bar, sig))
                bucket_fb.sort(key=lambda item: float(item[3].conviction_score), reverse=True)
                if bucket_fb:
                    signals_by_strat[fallback_runner.strategy_id] = bucket_fb
                    active_champion_info["fallback_triggered"] = True
                    active_champion_info["fallback_strategy"] = f"{fallback_runner.name} ({fallback_runner.strategy_id} v{fallback_runner.version})"
                    break

        strat_order = sorted(
            signals_by_strat.keys(),
            key=lambda sid: (0 if "breakout" in sid or "pead" in sid else 1, sid),
        )
        max_len = max((len(v) for v in signals_by_strat.values()), default=0)
        interleaved: List[Tuple[StrategyConfig, str, DailyBar, Any]] = []
        for idx in range(max_len):
            for sid in strat_order:
                if idx < len(signals_by_strat[sid]):
                    interleaved.append(signals_by_strat[sid][idx])

        def _effective_candidate_conviction(item: Tuple[StrategyConfig, str, DailyBar, Any]) -> float:
            tkr_u = str(item[1]).upper()
            c_row = latest_catalyst_by_tkr.get(tkr_u)
            sent_v = float(c_row["sentiment_score"]) if (c_row and c_row.get("sentiment_score") is not None) else 0.0
            base_c = float(item[3].conviction_score) * 100.0
            if sent_v >= 0.25:
                base_c = min(99.0, base_c + min(8.0, sent_v * 12.0))
            elif sent_v < 0.0:
                base_c = max(1.0, base_c + sent_v * 10.0)
            return base_c

        interleaved.sort(key=_effective_candidate_conviction, reverse=True)

        # Fetch live extended-hours / pre-market / intraday quotes when running in live / preview mode
        live_snapshots: Dict[str, Dict[str, Any]] = dict(pos_live_snapshots)
        if use_live_quotes_plan:
            snap_tickers = sorted({item[1] for item in interleaved} | {p["ticker"] for p in open_positions})
            if snap_tickers:
                try:
                    live_snapshots = self.market_data.fetch_live_quote_snapshots(snap_tickers)
                except Exception:
                    pass

        seen_buy_candidates: set[str] = set()
        for strat, ticker, latest_bar, sig in interleaved:
            if ticker in seen_buy_candidates or ticker in sim_open_map or ticker in exiting_tickers:
                continue
            seen_buy_candidates.add(ticker)
            meta = universe_meta.get(ticker)
            sector = meta.sector if meta else "Technology"
            ref_price = round(float(latest_bar.adj_close), 2)
            atr_val = float(sig.atr_at_signal) if (sig.atr_at_signal and sig.atr_at_signal > 0) else round(ref_price * 0.02, 2)
            buy_zone_low = round(max(0.01, ref_price - 0.25 * atr_val), 2)
            max_chase_p = round(ref_price + 0.50 * atr_val, 2)

            # AI / News Catalyst Veto & Conviction Booster
            cat_info = latest_catalyst_by_tkr.get(ticker.upper())
            ai_sent = float(cat_info["sentiment_score"]) if cat_info and cat_info.get("sentiment_score") is not None else 0.0
            ai_note = str(cat_info.get("headline") or cat_info.get("summary") or "") if cat_info else ""
            ai_source = str(cat_info.get("source_name") or "") if cat_info else ""
            if cat_info and ai_sent <= -0.35:
                vetoed_signals.append(
                    {
                        "ticker": ticker,
                        "strategy": f"{strat.strategy_id} v{strat.version}",
                        "reference_price": ref_price,
                        "veto_rule": "AI_BEARISH_CATALYST_VETO",
                        "removed_by": "Latest AI Findings",
                        "technical_trigger": sig.reason,
                        "reason": f"Removed by Latest AI Findings (Sentiment {ai_sent:+.2f} <= -0.35): {ai_note[:110]}",
                    }
                )
                continue

            # Pre-Open / Extended-Hours / Live Intraday Quote & Gap Gate
            snap_info = live_snapshots.get(ticker.upper()) or {}
            indicative_px = float(snap_info.get("indicative_price") or ref_price)
            gap_usd = round(indicative_px - ref_price, 2)
            gap_pct = round((gap_usd / ref_price) * 100.0, 2) if ref_price > 0 else 0.0
            gap_atr = round(gap_usd / atr_val, 2) if atr_val > 0 else 0.0
            if gap_atr <= -0.75:
                vetoed_signals.append(
                    {
                        "ticker": ticker,
                        "strategy": f"{strat.strategy_id} v{strat.version}",
                        "reference_price": ref_price,
                        "veto_rule": "PRE_OPEN_GAP_BREAKDOWN",
                        "removed_by": "Pre-Open Gap Filter",
                        "technical_trigger": sig.reason,
                        "reason": (
                            f"Removed by Pre-Open Gap Filter: Live/extended-hours quote ${indicative_px:.2f} ({gap_pct:+.2f}%, {gap_atr:+.2f} ATR) "
                            f"broke below Buy-Zone Low (${buy_zone_low:.2f})."
                        ),
                    }
                )
                continue
            if gap_atr > self.settings.risk.max_overnight_gap_atr_multiple:
                vetoed_signals.append(
                    {
                        "ticker": ticker,
                        "strategy": f"{strat.strategy_id} v{strat.version}",
                        "reference_price": ref_price,
                        "veto_rule": "OVERNIGHT_EXTREME_GAP_UP",
                        "removed_by": "Pre-Open Gap Filter",
                        "technical_trigger": sig.reason,
                        "reason": (
                            f"Removed by Pre-Open Gap Filter: Live/extended-hours quote ${indicative_px:.2f} ({gap_pct:+.2f}%, {gap_atr:+.2f} ATR) "
                            f"exceeds max overnight gap ({self.settings.risk.max_overnight_gap_atr_multiple:.1f}x ATR)."
                        ),
                    }
                )
                continue

            if indicative_px > max_chase_p:
                pre_open_status = "EXTENDED_ABOVE_MAX_CHASE"
                pre_open_guidance = (
                    f"Live/extended-hours ${indicative_px:.2f} ({gap_pct:+.2f}%) > Max Chase ${max_chase_p:.2f}: "
                    f"DO NOT CHASE at open; place Day Limit <= ${max_chase_p:.2f} in case of pullback."
                )
            elif indicative_px < buy_zone_low:
                pre_open_status = "DIPPED_BELOW_BUY_ZONE"
                pre_open_guidance = (
                    f"Live/extended-hours ${indicative_px:.2f} ({gap_pct:+.2f}%) < Buy-Zone Low ${buy_zone_low:.2f}: "
                    f"Wait for {open_time_sgt} (9:30 AM ET) reclaim of ${buy_zone_low:.2f} before entering."
                )
            else:
                pre_open_status = "READY_IN_BUY_ZONE"
                pre_open_guidance = (
                    f"Inside Buy-Zone (${buy_zone_low:.2f} – ${max_chase_p:.2f}) · "
                    f"Place Day Limit Order <= ${max_chase_p:.2f} for {open_window_45_sgt} (9:30–9:45 AM ET)."
                )

            # Use Temporary RiskManager without DB alert logging so previewing recommendations doesn't spam paper risk_alerts.
            # For small accounts (<= $15k, e.g. $10k starter account), allow up to 25% single-stock ($2,500) and 50% sector
            # exposure while keeping 1.0% stop-loss risk ($100) unchanged, preventing whole-share quantization truncation on $400-$800 stocks.
            if total_eq <= 15_000.0:
                import dataclasses as _dc
                eff_risk_cfg = _dc.replace(
                    self.settings.risk,
                    max_single_stock_exposure_pct=max(self.settings.risk.max_single_stock_exposure_pct, 0.25),
                    max_sector_exposure_pct=max(self.settings.risk.max_sector_exposure_pct, 0.50),
                )
                strat_max_exp = max(float(strat.risk_params.get("max_position_exposure_pct") or 0.15), 0.25)
            else:
                eff_risk_cfg = self.settings.risk
                strat_max_exp = strat.risk_params.get("max_position_exposure_pct")
            ind_latest_obj = (inds_by_tkr.get(ticker) or {}).get(latest_bar.bar_date)
            upcoming_ev = self.market_data.get_upcoming_earnings_within_days(ticker, session_date, 3)
            days_to_earn = 1 if upcoming_ev else None

            preview_rm = PortfolioRiskManager(eff_risk_cfg, db=None)
            decision = preview_rm.evaluate_proposed_entry(
                account_id=self.account_id,
                eval_date=session_date,
                ticker=ticker,
                sector=sector,
                strategy_id=strat.strategy_id,
                strategy_family=strat.strategy_family,
                entry_price=ref_price,
                stop_loss_price=sig.stop_loss_price,
                atr_14=sig.atr_at_signal,
                portfolio_equity=total_eq,
                peak_equity=total_eq,
                available_cash=sim_cash,
                open_positions=sim_open_map,
                avg_daily_dollar_volume_20d=ind_latest_obj.avg_dollar_volume_20d if ind_latest_obj else None,
                upcoming_earnings_days=days_to_earn,
                strategy_risk_pct=strat.risk_params.get("risk_per_trade_pct"),
                strategy_max_exp_pct=strat_max_exp,
            )
            if decision.approved and decision.recommended_shares > 0:
                shares = decision.recommended_shares
                est_cost = round(shares * ref_price, 2)
                weight_pct = round((est_cost / total_eq) * 100.0, 2)
                atr_val = float(sig.atr_at_signal) if (sig.atr_at_signal and sig.atr_at_signal > 0) else round(ref_price * 0.02, 2)
                stop_p = round(float(sig.stop_loss_price), 2) if sig.stop_loss_price else round(ref_price - 2.0 * atr_val, 2)
                tp_p = round(float(sig.take_profit_price), 2) if sig.take_profit_price else round(ref_price + 3.5 * atr_val, 2)
                buy_zone_low = round(max(0.01, ref_price - 0.25 * atr_val), 2)
                max_chase_p = round(ref_price + 0.50 * atr_val, 2)
                risk_per_sh = max(0.01, ref_price - stop_p)
                ratchet_1r_p = round(ref_price + 1.0 * risk_per_sh, 2)

                base_conv = float(sig.conviction_score) * 100.0
                if ai_sent >= 0.25:
                    base_conv = min(99.0, base_conv + min(8.0, ai_sent * 12.0))

                spy_ind_dt = spy_inds.get(latest_bar.bar_date)
                spy_regime_str = (
                    f"SPY ${float(spy_ind_dt.close):.2f} > 200d MA ${float(spy_ind_dt.sma_200):.2f} (Primary Bull Trend)"
                    if (spy_ind_dt and spy_ind_dt.sma_200 and spy_ind_dt.close >= spy_ind_dt.sma_200)
                    else f"SPY ${float(spy_ind_dt.close):.2f}" if spy_ind_dt else "US Large-Cap Benchmark"
                )
                sec_rank_val = sector_rank_map.get(sector, 1)
                if ai_sent >= 0.20 and ai_note:
                    ai_factor_str = f"AI Catalyst Boost ({ai_sent:+.2f}): {ai_note[:90]}"
                elif ai_note:
                    ai_factor_str = f"AI / Catalyst Check ({ai_sent:+.2f} Neutral — No Bearish Flags): {ai_note[:80]}"
                else:
                    ai_factor_str = "AI / News Check: Clear (No bearish catalyst flags or upcoming 2d earnings blackout)"
                reward_per_sh = max(0.01, tp_p - ref_price)
                rr_ratio = round(reward_per_sh / risk_per_sh, 2)
                buy_factors = [
                    f"Market & Sector: {spy_regime_str} · {sector} (Sector RS Rank #{sec_rank_val})",
                    f"Technical Setup ({strat.name}): {sig.reason}",
                    f"AI & Catalyst Check: {ai_factor_str}",
                    f"Risk & Sizing Math: Max Stop Risk -${decision.estimated_risk_usd:,.0f} ({round((decision.estimated_risk_usd / total_eq) * 100.0, 2):.2f}% of account) · Target +${round(reward_per_sh * shares, 0):,.0f} ({rr_ratio:.1f}x Reward/Risk)",
                ]

                buy_actions.append(
                    {
                        "action": "BUY",
                        "ticker": ticker,
                        "sector": sector,
                        "strategy_id": strat.strategy_id,
                        "strategy_version": strat.version,
                        "strategy_name": strat.name,
                        "recommended_shares": shares,
                        "reference_entry_price": ref_price,
                        "indicative_price": round(indicative_px, 2),
                        "overnight_gap_pct": gap_pct,
                        "overnight_gap_atr": gap_atr,
                        "pre_open_status": pre_open_status,
                        "pre_open_guidance": pre_open_guidance,
                        "entry_buy_zone_low": buy_zone_low,
                        "max_chase_price": max_chase_p,
                        "entry_buy_zone_str": f"${buy_zone_low:.2f} – ${max_chase_p:.2f}",
                        "breakeven_ratchet_price": ratchet_1r_p,
                        "estimated_cost_usd": est_cost,
                        "portfolio_weight_pct": weight_pct,
                        "stop_loss_price": stop_p,
                        "take_profit_price": tp_p,
                        "estimated_risk_usd": decision.estimated_risk_usd,
                        "risk_pct_of_equity": round((decision.estimated_risk_usd / total_eq) * 100.0, 2),
                        "holding_horizon_days": f"{strat.holding_period_min_days}–{strat.holding_period_max_days} trading days",
                        "conviction_score": round(base_conv, 0),
                        "ai_catalyst_sentiment": round(ai_sent, 2),
                        "ai_catalyst_note": ai_note,
                        "ai_catalyst_source": ai_source,
                        "why_summary": f"{strat.name}: {sig.reason} ({rr_ratio:.1f}x Reward/Risk · -${decision.estimated_risk_usd:,.0f} max stop risk)",
                        "factors_considered": buy_factors,
                        "order_timing_guidance": f"Place Limit Order for Market Open ({open_window_45_sgt} / 9:30–9:45 AM ET); NEVER trade illiquid pre-market/after-hours.",
                        "if_entry_not_hit_rule": f"Cancel/Skip if open gaps above Max Chase (${max_chase_p:.2f}) or breaks below ${buy_zone_low:.2f}.",
                        "if_target_not_hit_rule": f"At +1.0R (${ratchet_1r_p:.2f}), raise Stop to Breakeven (${ref_price:.2f}); exit on Day {strat.holding_period_max_days} (Time-Stop) if Target (${tp_p:.2f}) not hit.",
                        "reason": sig.reason,
                        "signal_date": session_date,
                    }
                )
                sim_cash = max(0.0, sim_cash - est_cost)
                sim_open_map[ticker] = {
                    "ticker": ticker,
                    "sector": sector,
                    "quantity": shares,
                    "current_price": ref_price,
                    "avg_entry_price": ref_price,
                    "stop_loss_price": sig.stop_loss_price,
                }
            else:
                vetoed_signals.append(
                    {
                        "ticker": ticker,
                        "strategy": f"{strat.strategy_id} v{strat.version}",
                        "reference_price": ref_price,
                        "veto_rule": decision.rule_triggered,
                        "removed_by": "Portfolio Risk / Cash Cap",
                        "technical_trigger": sig.reason,
                        "reason": decision.veto_reason,
                    }
                )

        return {
            "calendar_date": calendar_today_str,
            "is_trading_day": is_today_trading_day,
            "market_status_reason": market_status_reason,
            "next_trading_day": next_open_session,
            "session_date": session_date,
            "account_summary": summary,
            "active_champion": active_champion_info,
            "sell_actions": sell_actions,
            "buy_actions": buy_actions,
            "hold_updates": hold_updates,
            "vetoed_signals": vetoed_signals,
            "dismissed_count": len(dismissed_set),
        }

    def export_state(self) -> Dict[str, Any]:
        return {
            "account": self.get_account_summary(),
            "positions": self.get_open_positions(),
            "trade_history": self.get_trade_history(limit=500),
        }


