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
from typing import Any, Dict, List, Optional, Sequence

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
                kill_switch_engaged=summary["kill_switch_engaged"],
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

        # 2. Evaluate new entry signals across active strategies
        for strat in active_strategies:
            for ticker in strat.universe:
                if ticker == self.settings.benchmark_ticker:
                    continue
                bars = self.market_data.get_bars(ticker, end_date=trading_date)
                if len(bars) < 25 or bars[-1].bar_date != trading_date:
                    continue
                today_bar = bars[-1]
                # Signal is evaluated on prior close (bars[-2]) and filled at today's open (today_bar)
                prev_bar = bars[-2]
                inds = compute_indicator_series(bars[:-1], spy_bars=spy_bars)
                ind_prev = inds.get(prev_bar.bar_date)
                if ind_prev is None:
                    continue
                recent_ev = self.market_data.get_point_in_time_earnings(
                    ticker, prev_bar.bar_date, lookback_days=10
                )
                sig = StrategySignalEngine.evaluate_entry(
                    config=strat,
                    ind=ind_prev,
                    spy_ind=spy_inds.get(prev_bar.bar_date),
                    recent_earnings=recent_ev,
                )
                if sig is None:
                    continue

                summary_now = self.get_account_summary()
                rec_shares = self.risk_manager.calculate_atr_position_size(
                    portfolio_equity=summary_now["total_equity"],
                    available_cash=summary_now["cash_balance"],
                    entry_price=today_bar.adj_open,
                    stop_loss_price=sig.stop_loss_price,
                    atr_14=sig.atr_at_signal,
                    strategy_risk_per_trade_pct=strat.risk_params.get("risk_per_trade_pct"),
                    strategy_max_exposure_pct=strat.risk_params.get("max_position_exposure_pct"),
                )
                if rec_shares <= 0:
                    continue

                meta = universe_meta.get(ticker)
                sector = meta.sector if meta else "Technology"
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
                    stop_loss_target=sig.stop_loss_price,
                    take_profit_target=sig.take_profit_price,
                    atr_14=sig.atr_at_signal,
                    notes=sig.reason,
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

