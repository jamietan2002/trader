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
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.indicators.technical import compute_indicator_series
from core.market_data.models import DailyBar
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
        total_return_pct = ((total_equity / starting_cash) - 1.0) * 100.0 if starting_cash > 0 else 0.0

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
            "total_return_pct": round(total_return_pct, 2),
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

    def get_open_positions(self) -> List[Dict[str, Any]]:
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

    def reset_account_to_starting_capital(self) -> Dict[str, Any]:
        """Reset paper account cash, positions, orders, snapshots, and alerts to a clean $100,000 state."""
        self.settings.validate_trading_mode()
        now_iso = utc_now_iso()
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

        # 8. Optional Alpaca Paper Brokerage Order Mirroring (when ALPACA_API_KEY is configured)
        if self.settings.alpaca_api_key and self.settings.alpaca_secret_key:
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
        """Mark all open positions to `trading_date` market close, process dividends, and save snapshot."""
        positions = self.get_open_positions()
        acc = self.ensure_account_initialized()
        cash = float(acc["cash_balance"])
        now_iso = utc_now_iso()

        for pos in positions:
            ticker = pos["ticker"]
            bars = self.market_data.get_bars(ticker, start_date=trading_date, end_date=trading_date)
            if not bars:
                continue
            bar = bars[-1]
            new_high = max(float(pos["highest_price_since_entry"]), bar.adj_high)
            new_days = int(pos["holding_days"]) + (1 if trading_date > pos["opened_date"] else 0)
            if bar.dividend_amount > 0:
                div_cash = int(pos["quantity"]) * bar.dividend_amount
                cash = round(cash + div_cash, 2)

            self.db.execute(
                """
                UPDATE paper_positions
                SET current_price = ?, highest_price_since_entry = ?, holding_days = ?, updated_at = ?
                WHERE account_id = ? AND ticker = ?
                """,
                (bar.adj_close, new_high, new_days, now_iso, self.account_id, ticker),
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
    ) -> Dict[str, Any]:
        """Run one full trading day across approved `PAPER_TRADING` strategies."""
        self.settings.validate_trading_mode()
        universe_meta = self.market_data.get_universe_metadata(include_delisted=True)
        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker, end_date=trading_date)
        spy_inds = compute_indicator_series(spy_bars)
        spy_ind_today = spy_inds.get(trading_date)

        exits_executed: List[Dict[str, Any]] = []
        entries_executed: List[Dict[str, Any]] = []
        vetoed_orders: List[Dict[str, Any]] = []

        strat_by_id = {(s.strategy_id, s.version): s for s in active_strategies}
        fallback_strat = active_strategies[0] if active_strategies else None

        # 1. Evaluate exits on existing open positions
        for pos in self.get_open_positions():
            ticker = pos["ticker"]
            bars = self.market_data.get_bars(ticker, end_date=trading_date)
            if not bars or bars[-1].bar_date != trading_date:
                continue
            today_bar = bars[-1]
            inds = compute_indicator_series(bars, spy_bars=spy_bars)
            ind_today = inds.get(trading_date)
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
            if exit_sig is not None:
                res = self.submit_and_execute_order(
                    strategy_id=strat.strategy_id,
                    strategy_version=strat.version,
                    strategy_family=strat.strategy_family,
                    ticker=ticker,
                    side="SELL",
                    requested_qty=int(pos["quantity"]),
                    signal_date=trading_date,
                    execution_bar=today_bar,
                    sector=pos["sector"],
                    notes=exit_sig.reason,
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
            bars = self.market_data.get_bars(ticker, end_date=trading_date)
            if len(bars) < 25 or bars[-1].bar_date != trading_date:
                continue
            today_bar = bars[-1]
            prev_bar = bars[-2]
            inds = compute_indicator_series(bars[:-1], spy_bars=spy_bars)
            ind_prev = inds.get(prev_bar.bar_date)
            if ind_prev is None:
                continue
            recent_ev = self.market_data.get_point_in_time_earnings(
                ticker, prev_bar.bar_date, lookback_days=10
            )
            ticker_context[ticker] = (today_bar, prev_bar, ind_prev, recent_ev)
            t_meta = universe_meta.get(ticker)
            if t_meta is not None and ind_prev.rs_vs_spy_20d is not None:
                sector_rs_lists.setdefault(t_meta.sector, []).append(float(ind_prev.rs_vs_spy_20d))

        sorted_sectors = sorted(
            sector_rs_lists.keys(),
            key=lambda s: sum(sector_rs_lists[s]) / len(sector_rs_lists[s]),
            reverse=True,
        )
        sector_rank_map = {sec_name: idx + 1 for idx, sec_name in enumerate(sorted_sectors)}

        # Collect signals per strategy and sort by conviction_score descending
        signals_by_strategy: Dict[str, List[Tuple[StrategyConfig, str, DailyBar, DailyBar, Any]]] = {}
        for strat in deduped_strategies:
            strat_sigs: List[Tuple[StrategyConfig, str, DailyBar, DailyBar, Any]] = []
            for ticker in strat.universe:
                ctx = ticker_context.get(ticker)
                if ctx is None:
                    continue
                today_bar, prev_bar, ind_prev, recent_ev = ctx
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

        for strat, ticker, today_bar, prev_bar, sig in ordered_candidates:
            summary_now = self.get_account_summary()
            open_gap = today_bar.adj_open - sig.close_at_signal
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
            upcoming_ev = self.market_data.get_upcoming_earnings_within_days(ticker, trading_date, 3)
            days_to_earn = 1 if upcoming_ev else None

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
                notes=sig.reason,
                avg_daily_dollar_volume_20d=ind_prev_obj.avg_dollar_volume_20d if ind_prev_obj else None,
                upcoming_earnings_days=days_to_earn,
                strategy_risk_pct=strat.risk_params.get("risk_per_trade_pct"),
                strategy_max_exp_pct=strat.risk_params.get("max_position_exposure_pct"),
            )
            if res.status in ("FILLED", "PARTIALLY_FILLED"):
                entries_executed.append(res.to_dict())
            elif res.status == "REJECTED":
                vetoed_orders.append(res.to_dict())

        # 3. End-of-day mark-to-market & snapshot
        updated_summary = self.mark_to_market_and_snapshot(trading_date)
        return {
            "trading_date": trading_date,
            "exits_executed": exits_executed,
            "entries_executed": entries_executed,
            "vetoed_orders": vetoed_orders,
            "account_summary": updated_summary,
        }

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
        """Mark all confirmed real positions to the latest closing price and update holding days."""
        rows = self.db.fetch_all(
            "SELECT * FROM shadow_positions WHERE account_id = ? ORDER BY ticker ASC",
            (self.account_id,),
        )
        if not rows:
            return
        now_iso = utc_now_iso()
        for r in rows:
            ticker = r["ticker"]
            bars = self.market_data.get_bars(ticker, end_date=as_of_date)
            if not bars:
                continue
            latest_bar = bars[-1]
            curr_price = float(latest_bar.adj_close)
            high_since = max(float(r["highest_price_since_entry"]), float(latest_bar.adj_high), curr_price)
            opened_dt = str(r["opened_date"])
            hold_days = sum(1 for b in bars if b.bar_date > opened_dt)
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
        cost = round(quantity * fill_price + fees_usd, 2)
        new_cash = max(0.0, round(float(acc["cash_balance"]) - cost, 2))

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
            self.db.execute(
                """
                UPDATE shadow_positions
                SET quantity = ?, avg_entry_price = ?, current_price = ?,
                    stop_loss_price = COALESCE(?, stop_loss_price),
                    take_profit_price = COALESCE(?, take_profit_price),
                    updated_at = ?
                WHERE account_id = ? AND ticker = ?
                """,
                (new_q, new_avg, fill_price, stop_loss_price, take_profit_price, now_iso, self.account_id, ticker_u),
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
            "UPDATE shadow_accounts SET cash_balance = ?, updated_at = ? WHERE account_id = ?",
            (new_cash, now_iso, self.account_id),
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
        strategy_id: str = "strat_momentum_trend",
        strategy_version: int = 1,
        opened_date: Optional[str] = None,
        deduct_from_cash: bool = False,
    ) -> Dict[str, Any]:
        """Manually add, edit, or delete (quantity=0) a position in the user's real shadow ledger."""
        ticker_u = ticker.strip().upper()
        now_iso = utc_now_iso()
        if quantity <= 0:
            self.db.execute(
                "DELETE FROM shadow_positions WHERE account_id = ? AND ticker = ?",
                (self.account_id, ticker_u),
            )
            return self.get_account_summary()

        bars = self.market_data.get_bars(ticker_u)
        latest_close = float(bars[-1].adj_close) if bars else avg_entry_price
        dt_str = opened_date or (bars[-1].bar_date if bars else now_iso[:10])
        meta = self.market_data.get_universe_metadata(include_delisted=True).get(ticker_u)
        sec = meta.sector if meta else "Technology"

        # Auto-compute default ATR stop/target if omitted
        if (stop_loss_price is None or take_profit_price is None) and len(bars) >= 20:
            inds = compute_indicator_series(bars)
            ind_last = inds.get(bars[-1].bar_date)
            atr = float(ind_last.atr_14) if (ind_last and ind_last.atr_14) else avg_entry_price * 0.025
            if stop_loss_price is None:
                stop_loss_price = round(avg_entry_price - 2.0 * atr, 2)
            if take_profit_price is None:
                take_profit_price = round(avg_entry_price + 3.5 * atr, 2)

        self.db.execute(
            """
            INSERT INTO shadow_positions (
                account_id, ticker, strategy_id, strategy_version, sector,
                quantity, avg_entry_price, current_price, highest_price_since_entry,
                stop_loss_price, take_profit_price, opened_date, holding_days, notes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'Manual position edit/entry', ?)
            ON CONFLICT(account_id, ticker) DO UPDATE SET
                strategy_id=excluded.strategy_id,
                strategy_version=excluded.strategy_version,
                quantity=excluded.quantity,
                avg_entry_price=excluded.avg_entry_price,
                current_price=excluded.current_price,
                stop_loss_price=excluded.stop_loss_price,
                take_profit_price=excluded.take_profit_price,
                updated_at=excluded.updated_at
            """,
            (
                self.account_id,
                ticker_u,
                strategy_id,
                int(strategy_version),
                sec,
                int(quantity),
                round(avg_entry_price, 4),
                round(latest_close, 4),
                max(round(avg_entry_price, 4), round(latest_close, 4)),
                round(stop_loss_price, 2) if stop_loss_price else None,
                round(take_profit_price, 2) if take_profit_price else None,
                dt_str,
                now_iso,
            ),
        )
        if deduct_from_cash:
            acc = self.ensure_initialized()
            new_cash = max(0.0, round(float(acc["cash_balance"]) - (quantity * avg_entry_price), 2))
            self.db.execute(
                "UPDATE shadow_accounts SET cash_balance = ?, updated_at = ? WHERE account_id = ?",
                (new_cash, now_iso, self.account_id),
            )
        return self.get_account_summary()

    def get_daily_action_plan(self, as_of_date: Optional[str] = None) -> Dict[str, Any]:
        """Compute step-by-step SELL and BUY recommendations tailored to the user's real account."""
        spy_bars = self.market_data.get_bars(self.settings.benchmark_ticker, end_date=as_of_date)
        session_date = spy_bars[-1].bar_date if spy_bars else (as_of_date or utc_now_iso()[:10])
        spy_inds = compute_indicator_series(spy_bars) if spy_bars else {}

        summary = self.get_account_summary(as_of_date=session_date)
        open_positions = self.get_open_positions()
        open_by_ticker = {p["ticker"]: p for p in open_positions}

        dismissed_rows = self.db.fetch_all(
            "SELECT strategy_id, ticker, action FROM shadow_dismissed_signals WHERE account_id = ? AND signal_date = ?",
            (self.account_id, session_date),
        )
        dismissed_set = {(r["strategy_id"], r["ticker"], r["action"]) for r in dismissed_rows}

        all_strats = self.registry.list_strategies()
        strat_by_key = {f"{s.strategy_id}:{s.version}": s for s in all_strats}
        enabled_keys = summary.get("enabled_strategies") or []
        if enabled_keys:
            active_strats = [strat_by_key[k] for k in enabled_keys if k in strat_by_key]
        else:
            active_strats = [s for s in all_strats if s.status == "PAPER_TRADING"]

        # Deduplicate by strategy_id (keep highest version)
        latest_by_id: Dict[str, StrategyConfig] = {}
        for s in active_strats:
            prev = latest_by_id.get(s.strategy_id)
            if prev is None or s.version > prev.version:
                latest_by_id[s.strategy_id] = s
        deduped_strats = list(latest_by_id.values())
        fallback_strat = deduped_strats[0] if deduped_strats else (all_strats[0] if all_strats else None)

        # 1. Evaluate SELL / HOLD status for every confirmed position the user actually holds
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
            strat = strat_by_key.get(f"{pos['strategy_id']}:{pos['strategy_version']}", fallback_strat)
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
            if exit_sig is not None:
                sell_actions.append(
                    {
                        "action": "SELL",
                        "ticker": ticker,
                        "sector": pos["sector"],
                        "strategy_id": pos["strategy_id"],
                        "strategy_version": pos["strategy_version"],
                        "quantity_to_sell": int(pos["quantity"]),
                        "avg_entry_price": float(pos["avg_entry_price"]),
                        "reference_exit_price": round(float(bars[-1].adj_close), 2),
                        "estimated_realised_pnl": round(
                            (float(bars[-1].adj_close) - float(pos["avg_entry_price"])) * int(pos["quantity"]), 2
                        ),
                        "holding_days": int(pos["holding_days"]),
                        "reason": exit_sig.reason,
                        "signal_date": session_date,
                    }
                )
            else:
                max_hold = strat.holding_period_max_days
                days_left = max(0, max_hold - int(pos["holding_days"]))
                hold_updates.append(
                    {
                        "ticker": ticker,
                        "strategy": f"{pos['strategy_id']} v{pos['strategy_version']}",
                        "quantity": int(pos["quantity"]),
                        "avg_entry_price": float(pos["avg_entry_price"]),
                        "current_price": float(pos["current_price"]),
                        "unrealised_pnl": float(pos["unrealised_pnl"]),
                        "stop_loss_price": pos.get("stop_loss_price"),
                        "take_profit_price": pos.get("take_profit_price"),
                        "status": f"HOLD ({days_left} trading days until max time-exit)",
                    }
                )

        # 2. Evaluate BUY signals sized to the user's real account equity & cash
        buy_actions: List[Dict[str, Any]] = []
        vetoed_signals: List[Dict[str, Any]] = []
        universe_meta = self.market_data.get_universe_metadata(include_delisted=True)

        # Simulate remaining cash/exposure as recommendations are queued so total recommendations respect user's caps
        sim_cash = float(summary["cash_balance"])
        sim_open_map = dict(open_by_ticker)
        total_eq = max(1.0, float(summary["total_equity"]))

        # Collect signals across all active strategies and interleave by strategy family
        signals_by_strat: Dict[str, List[Tuple[StrategyConfig, str, DailyBar, Any]]] = {}
        for strat in deduped_strats:
            bucket: List[Tuple[StrategyConfig, str, DailyBar, Any]] = []
            for ticker in strat.universe:
                if ticker == self.settings.benchmark_ticker or ticker in sim_open_map:
                    continue
                if (strat.strategy_id, ticker, "BUY") in dismissed_set:
                    continue
                bars = self.market_data.get_bars(ticker, end_date=session_date)
                if len(bars) < 25:
                    continue
                latest_bar = bars[-1]
                inds = compute_indicator_series(bars, spy_bars=spy_bars)
                ind_latest = inds.get(latest_bar.bar_date)
                if ind_latest is None:
                    continue
                recent_ev = self.market_data.get_point_in_time_earnings(
                    ticker, latest_bar.bar_date, lookback_days=10
                )
                sig = StrategySignalEngine.evaluate_entry(
                    config=strat,
                    ind=ind_latest,
                    spy_ind=spy_inds.get(latest_bar.bar_date),
                    recent_earnings=recent_ev,
                )
                if sig is not None:
                    bucket.append((strat, ticker, latest_bar, sig))
            bucket.sort(key=lambda item: float(item[3].conviction_score), reverse=True)
            if bucket:
                signals_by_strat[strat.strategy_id] = bucket

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

        for strat, ticker, latest_bar, sig in interleaved:
            if ticker in sim_open_map:
                continue
            meta = universe_meta.get(ticker)
            sector = meta.sector if meta else "Technology"
            ref_price = round(float(latest_bar.adj_close), 2)

            # Use Temporary RiskManager without DB alert logging so previewing recommendations doesn't spam paper risk_alerts
            preview_rm = PortfolioRiskManager(self.settings.risk, db=None)
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
                strategy_risk_pct=strat.risk_params.get("risk_per_trade_pct"),
                strategy_max_exp_pct=strat.risk_params.get("max_position_exposure_pct"),
            )
            if decision.approved and decision.recommended_shares > 0:
                shares = decision.recommended_shares
                est_cost = round(shares * ref_price, 2)
                weight_pct = round((est_cost / total_eq) * 100.0, 2)
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
                        "estimated_cost_usd": est_cost,
                        "portfolio_weight_pct": weight_pct,
                        "stop_loss_price": round(float(sig.stop_loss_price), 2) if sig.stop_loss_price else None,
                        "take_profit_price": round(float(sig.take_profit_price), 2) if sig.take_profit_price else None,
                        "estimated_risk_usd": decision.estimated_risk_usd,
                        "risk_pct_of_equity": round((decision.estimated_risk_usd / total_eq) * 100.0, 2),
                        "holding_horizon_days": f"{strat.holding_period_min_days}–{strat.holding_period_max_days} trading days",
                        "conviction_score": round(float(sig.conviction_score) * 100.0, 0),
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
                        "reason": decision.veto_reason,
                    }
                )

        return {
            "session_date": session_date,
            "account_summary": summary,
            "sell_actions": sell_actions,
            "buy_actions": buy_actions,
            "hold_updates": hold_updates,
            "vetoed_signals": vetoed_signals,
        }

    def export_state(self) -> Dict[str, Any]:
        return {
            "account": self.get_account_summary(),
            "positions": self.get_open_positions(),
            "trade_history": self.get_trade_history(limit=500),
        }


