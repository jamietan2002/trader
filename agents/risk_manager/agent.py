"""Risk Manager Agent (`risk_manager`).

Wraps the deterministic `PortfolioRiskManager` with structured risk audit reporting,
alert inspection, and emergency kill-switch governance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from core.execution.paper_broker import PaperTradingEngine
from core.risk.manager import PortfolioRiskManager
from infrastructure.configuration.settings import Settings
from infrastructure.database.db import DatabaseManager


class RiskManagerAgent(BaseAgent):
    """Autonomous Risk Governance Agent with order veto power and kill-switch authority."""

    role_name = "risk_manager"

    def __init__(
        self,
        settings: Settings,
        db: DatabaseManager,
        risk_manager: PortfolioRiskManager,
        paper_engine: PaperTradingEngine,
    ) -> None:
        super().__init__(settings)
        self.db = db
        self.risk_manager = risk_manager
        self.paper_engine = paper_engine

    def audit_portfolio_health(self, eval_date: str) -> Dict[str, Any]:
        """Inspect current paper account risk metrics, sector concentration, and drawdown state."""
        self.assert_permission("read_paper_account")
        summary = self.paper_engine.get_account_summary()
        dd_pct = float(summary["current_drawdown_pct"]) / 100.0

        if dd_pct >= self.settings.risk.drawdown_suspension_threshold_pct:
            self.assert_permission("trigger_kill_switch")
            self.paper_engine.set_kill_switch(
                True,
                f"Portfolio drawdown {dd_pct * 100:.2f}% exceeded suspension limit "
                f"{self.settings.risk.drawdown_suspension_threshold_pct * 100:.1f}% on {eval_date}.",
            )
            summary = self.paper_engine.get_account_summary()

        recent_alerts = self.get_recent_alerts(limit=25)
        return {
            "eval_date": eval_date,
            "kill_switch_engaged": summary["kill_switch_engaged"],
            "kill_switch_reason": summary["kill_switch_reason"],
            "current_drawdown_pct": summary["current_drawdown_pct"],
            "open_positions_count": summary["open_positions_count"],
            "max_simultaneous_positions": self.settings.risk.max_simultaneous_positions,
            "sector_exposures_pct": summary["sector_exposures_pct"],
            "max_sector_exposure_pct": self.settings.risk.max_sector_exposure_pct * 100.0,
            "recent_alerts": recent_alerts,
        }

    def get_recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.db.fetch_all(
            "SELECT * FROM risk_alerts ORDER BY created_at DESC LIMIT ?", (limit,)
        )

