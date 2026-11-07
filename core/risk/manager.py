"""Portfolio Risk Manager with Veto Authority and Kill Switch.

Enforces:
- Maximum risk per trade: 1% of portfolio equity (ATR-based sizing).
- Maximum simultaneous positions: 10.
- Maximum single-stock exposure: 15% of portfolio equity.
- Maximum sector exposure: 30% of portfolio equity.
- Maximum portfolio drawdown threshold: 10% warning and 15% trading suspension (kill switch).
- Liquidity checks (minimum 20-day average daily dollar volume).
- Pairwise return correlation checks against existing portfolio positions.
- Earnings event risk check (blocks non-PEAD entries right before scheduled earnings).
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence

from infrastructure.configuration.settings import RiskParametersConfig
from infrastructure.database.db import DatabaseManager, utc_now_iso
from infrastructure.logging.logger import get_logger

logger = get_logger("core.risk")


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    veto_reason: Optional[str]
    recommended_shares: int
    estimated_position_value: float
    estimated_risk_usd: float
    warnings: List[str]
    rule_triggered: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_return_correlation(returns_a: Sequence[float], returns_b: Sequence[float]) -> float:
    """Compute Pearson correlation coefficient between two return series."""
    n = min(len(returns_a), len(returns_b))
    if n < 5:
        return 0.0
    a = returns_a[-n:]
    b = returns_b[-n:]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    denom = math.sqrt(var_a * var_b)
    if denom <= 1e-12:
        return 0.0
    return cov / denom


class PortfolioRiskManager:
    """Authoritative Portfolio Risk Manager with trade veto power and emergency kill switch."""

    def __init__(
        self,
        risk_config: RiskParametersConfig,
        db: Optional[DatabaseManager] = None,
    ) -> None:
        self.config = risk_config
        self.db = db

    def calculate_atr_position_size(
        self,
        portfolio_equity: float,
        available_cash: float,
        entry_price: float,
        stop_loss_price: Optional[float],
        atr_14: float,
        strategy_risk_per_trade_pct: Optional[float] = None,
        strategy_max_exposure_pct: Optional[float] = None,
    ) -> int:
        """Calculate deterministic ATR-based position size subject to risk and exposure caps."""
        if portfolio_equity <= 0 or available_cash <= 0 or entry_price <= 0:
            return 0

        effective_risk_pct = min(
            self.config.max_risk_per_trade_pct,
            strategy_risk_per_trade_pct or self.config.max_risk_per_trade_pct,
        )
        max_risk_dollars = portfolio_equity * effective_risk_pct

        # Risk per share is distance from entry to stop-loss (or 2.0 * ATR fallback)
        if stop_loss_price is not None and 0 < stop_loss_price < entry_price:
            risk_per_share = entry_price - stop_loss_price
        else:
            risk_per_share = max(entry_price * 0.015, 2.0 * max(atr_14, entry_price * 0.01))

        shares_by_risk = int(max_risk_dollars // risk_per_share)

        effective_max_exp_pct = min(
            self.config.max_single_stock_exposure_pct,
            strategy_max_exposure_pct or self.config.max_single_stock_exposure_pct,
        )
        max_position_dollars = min(portfolio_equity * effective_max_exp_pct, available_cash * 0.98)
        shares_by_exposure = int(max_position_dollars // entry_price)

        return max(0, min(shares_by_risk, shares_by_exposure))

    def evaluate_proposed_entry(
        self,
        account_id: str,
        eval_date: str,
        ticker: str,
        sector: str,
        strategy_id: str,
        strategy_family: str,
        entry_price: float,
        stop_loss_price: Optional[float],
        atr_14: float,
        portfolio_equity: float,
        peak_equity: float,
        available_cash: float,
        open_positions: Dict[str, Dict[str, Any]],
        avg_daily_dollar_volume_20d: Optional[float] = None,
        upcoming_earnings_days: Optional[int] = None,
        candidate_returns_20d: Optional[Sequence[float]] = None,
        open_positions_returns_20d: Optional[Dict[str, Sequence[float]]] = None,
        kill_switch_engaged: bool = False,
        strategy_risk_pct: Optional[float] = None,
        strategy_max_exp_pct: Optional[float] = None,
    ) -> RiskDecision:
        """Evaluate all portfolio, drawdown, sector, correlation, liquidity, and event risk constraints."""
        warnings: List[str] = []

        # 0. Emergency Kill Switch Check
        if kill_switch_engaged:
            return self._veto(
                account_id,
                eval_date,
                ticker,
                strategy_id,
                "KILL_SWITCH_ACTIVE",
                "Emergency kill switch is engaged; all new entries are suspended.",
            )

        # 1. Portfolio Drawdown Check (10% Warning, 15% Suspension)
        current_dd = (
            max(0.0, (peak_equity - portfolio_equity) / peak_equity)
            if peak_equity > 0
            else 0.0
        )
        if current_dd >= self.config.drawdown_suspension_threshold_pct:
            return self._veto(
                account_id,
                eval_date,
                ticker,
                strategy_id,
                "MAX_DRAWDOWN_SUSPENSION",
                f"Portfolio drawdown {current_dd * 100:.2f}% exceeds suspension threshold "
                f"{self.config.drawdown_suspension_threshold_pct * 100:.1f}%.",
                severity="KILL_SWITCH",
            )
        if current_dd >= self.config.drawdown_warning_threshold_pct:
            warn_msg = (
                f"Portfolio drawdown warning: {current_dd * 100:.2f}% >= "
                f"{self.config.drawdown_warning_threshold_pct * 100:.1f}% threshold."
            )
            warnings.append(warn_msg)
            self._log_alert(account_id, eval_date, "WARNING", "DRAWDOWN_WARNING", ticker, strategy_id, warn_msg)

        # 2. Duplicate Position Check
        if ticker in open_positions:
            return self._veto(
                account_id,
                eval_date,
                ticker,
                strategy_id,
                "DUPLICATE_POSITION",
                f"Position in {ticker} is already open.",
            )

        # 3. Maximum Simultaneous Positions Check
        if len(open_positions) >= self.config.max_simultaneous_positions:
            return self._veto(
                account_id,
                eval_date,
                ticker,
                strategy_id,
                "MAX_SIMULTANEOUS_POSITIONS",
                f"Open positions ({len(open_positions)}) at maximum limit ({self.config.max_simultaneous_positions}).",
            )

        # 4. Liquidity Check
        if (
            avg_daily_dollar_volume_20d is not None
            and avg_daily_dollar_volume_20d < self.config.min_avg_daily_dollar_volume
        ):
            return self._veto(
                account_id,
                eval_date,
                ticker,
                strategy_id,
                "INSUFFICIENT_LIQUIDITY",
                f"{ticker} 20d avg dollar volume (${avg_daily_dollar_volume_20d:,.0f}) below "
                f"minimum (${self.config.min_avg_daily_dollar_volume:,.0f}).",
            )

        # 5. Earnings Blackout Check (for non-PEAD strategies)
        if (
            strategy_family != "PEAD"
            and upcoming_earnings_days is not None
            and 0 <= upcoming_earnings_days <= self.config.earnings_blackout_days_before
        ):
            return self._veto(
                account_id,
                eval_date,
                ticker,
                strategy_id,
                "EARNINGS_EVENT_BLACKOUT",
                f"{ticker} has earnings scheduled in {upcoming_earnings_days} day(s); "
                f"non-PEAD entries blocked within {self.config.earnings_blackout_days_before} days.",
            )

        # 6. Calculate ATR Position Size
        shares = self.calculate_atr_position_size(
            portfolio_equity=portfolio_equity,
            available_cash=available_cash,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            atr_14=atr_14,
            strategy_risk_per_trade_pct=strategy_risk_pct,
            strategy_max_exposure_pct=strategy_max_exp_pct,
        )
        if shares <= 0:
            return self._veto(
                account_id,
                eval_date,
                ticker,
                strategy_id,
                "INSUFFICIENT_BUYING_POWER_OR_SIZE",
                f"Calculated share size is 0 for {ticker} at ${entry_price:.2f} (cash=${available_cash:,.2f}).",
            )

        proposed_value = shares * entry_price

        # 7. Single-Stock Exposure Check (15% cap)
        stock_exposure_pct = proposed_value / portfolio_equity if portfolio_equity > 0 else 1.0
        if stock_exposure_pct > self.config.max_single_stock_exposure_pct + 1e-6:
            return self._veto(
                account_id,
                eval_date,
                ticker,
                strategy_id,
                "MAX_SINGLE_STOCK_EXPOSURE",
                f"Proposed {ticker} exposure {stock_exposure_pct * 100:.2f}% exceeds "
                f"{self.config.max_single_stock_exposure_pct * 100:.1f}% limit.",
            )

        # 8. Sector Concentration Check (30% cap)
        existing_sector_val = sum(
            float(pos.get("quantity", 0)) * float(pos.get("current_price", pos.get("avg_entry_price", 0.0)))
            for pos in open_positions.values()
            if pos.get("sector") == sector
        )
        new_sector_exposure_pct = (
            (existing_sector_val + proposed_value) / portfolio_equity
            if portfolio_equity > 0
            else 1.0
        )
        if new_sector_exposure_pct > self.config.max_sector_exposure_pct:
            # Try scaling down shares to fit remaining sector room
            remaining_sector_dollars = max(
                0.0, (self.config.max_sector_exposure_pct * portfolio_equity) - existing_sector_val
            )
            adjusted_shares = int(remaining_sector_dollars // entry_price)
            if adjusted_shares <= 0:
                return self._veto(
                    account_id,
                    eval_date,
                    ticker,
                    strategy_id,
                    "MAX_SECTOR_EXPOSURE",
                    f"Sector '{sector}' exposure would reach {new_sector_exposure_pct * 100:.2f}%, "
                    f"exceeding {self.config.max_sector_exposure_pct * 100:.1f}% limit.",
                )
            shares = adjusted_shares
            proposed_value = shares * entry_price
            warnings.append(
                f"Scaled down {ticker} shares to {shares} to respect {self.config.max_sector_exposure_pct * 100:.0f}% '{sector}' sector cap."
            )

        # 9. Pairwise Correlation Check
        if candidate_returns_20d and open_positions_returns_20d:
            for existing_ticker, existing_rets in open_positions_returns_20d.items():
                corr = compute_return_correlation(candidate_returns_20d, existing_rets)
                if corr > self.config.max_pairwise_correlation:
                    return self._veto(
                        account_id,
                        eval_date,
                        ticker,
                        strategy_id,
                        "HIGH_PORTFOLIO_CORRELATION",
                        f"{ticker} 20d return correlation with open position {existing_ticker} "
                        f"is {corr:.2f} > {self.config.max_pairwise_correlation:.2f} limit.",
                    )

        risk_per_share = (
            (entry_price - stop_loss_price)
            if (stop_loss_price is not None and stop_loss_price < entry_price)
            else 2.0 * atr_14
        )
        est_risk_usd = round(shares * max(0.0, risk_per_share), 2)

        # 10. Portfolio Heat Cap (Maximum Total Open Stop-Loss Risk Across All Positions)
        existing_open_risk_usd = 0.0
        for pos in open_positions.values():
            pos_qty = float(pos.get("quantity", 0))
            pos_curr = float(pos.get("current_price", pos.get("avg_entry_price", 0.0)))
            pos_stop = pos.get("stop_loss_price")
            if pos_stop is not None and float(pos_stop) < pos_curr:
                existing_open_risk_usd += pos_qty * (pos_curr - float(pos_stop))
            else:
                existing_open_risk_usd += pos_qty * pos_curr * 0.03

        max_open_risk_usd = portfolio_equity * getattr(self.config, "max_total_open_risk_pct", 0.05)
        if existing_open_risk_usd + est_risk_usd > max_open_risk_usd + 1e-6:
            return self._veto(
                account_id,
                eval_date,
                ticker,
                strategy_id,
                "MAX_TOTAL_OPEN_RISK",
                f"Total open portfolio stop-loss risk (${existing_open_risk_usd + est_risk_usd:,.2f}) "
                f"would exceed {getattr(self.config, 'max_total_open_risk_pct', 0.05) * 100:.1f}% limit (${max_open_risk_usd:,.2f}).",
            )

        return RiskDecision(
            approved=True,
            veto_reason=None,
            recommended_shares=shares,
            estimated_position_value=round(proposed_value, 2),
            estimated_risk_usd=est_risk_usd,
            warnings=warnings,
            rule_triggered=None,
        )

    def _veto(
        self,
        account_id: str,
        eval_date: str,
        ticker: str,
        strategy_id: str,
        rule_name: str,
        message: str,
        severity: str = "CRITICAL_VETO",
    ) -> RiskDecision:
        self._log_alert(account_id, eval_date, severity, rule_name, ticker, strategy_id, message)
        return RiskDecision(
            approved=False,
            veto_reason=message,
            recommended_shares=0,
            estimated_position_value=0.0,
            estimated_risk_usd=0.0,
            warnings=[],
            rule_triggered=rule_name,
        )

    def _log_alert(
        self,
        account_id: str,
        alert_date: str,
        severity: str,
        rule_name: str,
        ticker: Optional[str],
        strategy_id: Optional[str],
        message: str,
    ) -> None:
        if self.db is None:
            return
        self.db.execute(
            """
            INSERT INTO risk_alerts (
                alert_id, account_id, alert_date, severity,
                rule_name, ticker, strategy_id, message, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"alert_{uuid.uuid4().hex[:12]}",
                account_id,
                alert_date,
                severity,
                rule_name,
                ticker,
                strategy_id,
                message,
                json.dumps({"rule": rule_name, "ticker": ticker, "strategy_id": strategy_id}),
                utc_now_iso(),
            ),
        )

