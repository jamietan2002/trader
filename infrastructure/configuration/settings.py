"""Configuration and safety guardrails for the Swing Trading AI Platform."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any
from zoneinfo import ZoneInfo


class LiveTradingProhibitedError(PermissionError):
    """Raised whenever an unauthorized attempt is made to enable or execute real-money trades."""


@dataclass(frozen=True)
class RiskParametersConfig:
    """Default conservative portfolio risk limits."""

    max_risk_per_trade_pct: float = 0.01  # 1% of portfolio equity
    max_short_risk_per_trade_pct: float = 0.01  # 1.00% max equity risk per short trade
    max_total_open_risk_pct: float = 0.05  # 5% max aggregate open stop-loss risk across all positions
    max_simultaneous_positions: int = 10
    max_single_stock_exposure_pct: float = 0.15  # 15% of portfolio equity (long)
    max_single_short_exposure_pct: float = 0.12  # 12% max single-stock short exposure (anti-squeeze)
    max_gross_short_exposure_pct: float = 0.40  # 40% max aggregate gross short exposure
    max_sector_exposure_pct: float = 0.30  # 30% of portfolio equity
    drawdown_warning_threshold_pct: float = 0.10  # 10% warning
    drawdown_suspension_threshold_pct: float = 0.15  # 15% trading suspension (kill switch)
    max_pairwise_correlation: float = 0.80  # Max correlation with existing portfolio positions
    min_avg_daily_dollar_volume: float = 20_000_000.0  # Minimum $20M daily liquidity
    earnings_blackout_days_before: int = 2  # Avoid non-PEAD entries right before earnings
    max_overnight_gap_atr_multiple: float = 2.5


@dataclass(frozen=True)
class PromotionCriteriaConfig:
    """Configurable strategy promotion thresholds for Strategy Evaluation Agent."""

    min_oos_net_return: float = 0.0  # Positive net out-of-sample returns
    min_sharpe_ratio: float = 1.0  # Sharpe ratio > 1.0
    min_profit_factor: float = 1.3  # Profit factor > 1.3
    max_drawdown_pct: float = 0.15  # Max drawdown < 15%
    max_ulcer_index: float = 6.0  # Ulcer Index <= 6.0% (penalizes depth & duration of drawdowns)
    max_time_under_water_days: int = 252  # Max recovery duration <= 252 trading days (1 trading year)
    min_deflated_sharpe_pct: float = 70.0  # Deflated Sharpe Ratio >= 70% statistical confidence
    min_trade_count: int = 15  # Minimum trades for statistical evaluation
    min_walk_forward_consistency: float = 0.60  # At least 60% of walk-forward windows profitable
    require_positive_after_costs: bool = True
    require_beat_benchmark_risk_adjusted: bool = True


@dataclass(frozen=True)
class TransactionCostConfig:
    """Realistic transaction cost, spread, and slippage parameters."""

    commission_per_share: float = 0.005  # $0.005 per share
    min_commission_per_order: float = 1.00  # $1.00 minimum per order
    default_half_spread_bps: float = 2.5  # 2.5 bps half-spread (5 bps full spread)
    default_slippage_bps: float = 3.0  # 3.0 bps market impact / slippage
    sec_fee_per_dollar_sold: float = 0.0000278  # SEC regulatory fee on sells
    short_borrow_bps_annual: float = 50.0  # 50 bps/year annualized stock-borrow fee drag on shorts


@dataclass
class Settings:
    """Global platform settings loaded from environment variables with safe defaults."""

    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    trading_mode: str = "paper"
    live_trading_operator_approval_token: str = ""
    initial_capital_usd: float = 100_000.0
    base_currency: str = "USD"
    benchmark_ticker: str = "SPY"
    holding_period_min_days: int = 3
    holding_period_max_days: int = 15

    market_timezone: str = "America/New_York"
    operator_timezone: str = "Asia/Singapore"

    database_url: str = ""
    market_data_provider: str = "alpaca"  # alpaca | local_seeded | polygon | fmp | finnhub
    llm_provider: str = "deterministic_research"  # deterministic_research | openai | gemini | anthropic
    llm_model: str = "gemini-2.5-pro"

    # API Keys (never logged in plaintext)
    # Pod 1: strat_volatility_breakout (#1 Champion) -> ALPACA_API_KEY / ALPACA_SECRET_KEY
    # Pod 2: strat_mean_reversion_bb (#2 Pullback Specialist) -> ALPACA_API_KEY_2 / ALPACA_SECRET_KEY_2
    # Pod 3: strat_momentum_trend (#3 Momentum Leader) -> ALPACA_API_KEY_3 / ALPACA_SECRET_KEY_3
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_api_key_2: str = ""
    alpaca_secret_key_2: str = ""
    alpaca_api_key_3: str = ""
    alpaca_secret_key_3: str = ""
    alpaca_paper_base_url: str = "https://paper-api.alpaca.markets"
    polygon_api_key: str = ""
    fmp_api_key: str = ""
    finnhub_api_key: str = ""
    sec_edgar_user_agent: str = "SwingTradingResearchPlatform research@example.com"
    openai_api_key: str = ""
    gemini_api_key: str = ""

    api_host: str = "127.0.0.1"
    api_port: int = 8080

    risk: RiskParametersConfig = field(default_factory=RiskParametersConfig)
    promotion: PromotionCriteriaConfig = field(default_factory=PromotionCriteriaConfig)
    costs: TransactionCostConfig = field(default_factory=TransactionCostConfig)

    def __post_init__(self) -> None:
        if not self.database_url:
            db_path = self.project_root / "data" / "swing_trader.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.database_url = f"sqlite:///{db_path}"
        self.validate_trading_mode()

    def validate_trading_mode(self) -> None:
        """Enforce strict separation between paper trading and real-money execution."""
        mode = (self.trading_mode or "").strip().lower()
        if mode != "paper":
            raise LiveTradingProhibitedError(
                f"TRADING_MODE='{self.trading_mode}' is strictly prohibited. "
                "This platform is locked to TRADING_MODE=paper unless explicit human operator "
                "approval, separate live brokerage credentials, and per-order audit policies are verified."
            )

    @property
    def market_tz(self) -> ZoneInfo:
        return ZoneInfo(self.market_timezone)

    @property
    def operator_tz(self) -> ZoneInfo:
        return ZoneInfo(self.operator_timezone)

    @property
    def sqlite_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url.replace("sqlite:///", "", 1))
        return self.project_root / "data" / "swing_trader.db"

    def sanitized_dict(self) -> Dict[str, Any]:
        """Return configuration dictionary with all secrets redacted for safe logging."""
        return {
            "trading_mode": self.trading_mode,
            "initial_capital_usd": self.initial_capital_usd,
            "base_currency": self.base_currency,
            "benchmark_ticker": self.benchmark_ticker,
            "holding_period_days": [self.holding_period_min_days, self.holding_period_max_days],
            "market_timezone": self.market_timezone,
            "operator_timezone": self.operator_timezone,
            "database_url": self.database_url,
            "market_data_provider": self.market_data_provider,
            "llm_provider": self.llm_provider,
            "alpaca_api_key": "***REDACTED***" if self.alpaca_api_key else "(not set)",
            "alpaca_api_key_2": "***REDACTED***" if self.alpaca_api_key_2 else "(not set)",
            "alpaca_api_key_3": "***REDACTED***" if self.alpaca_api_key_3 else "(not set)",
            "polygon_api_key": "***REDACTED***" if self.polygon_api_key else "(not set)",
            "fmp_api_key": "***REDACTED***" if self.fmp_api_key else "(not set)",
            "finnhub_api_key": "***REDACTED***" if self.finnhub_api_key else "(not set)",
            "openai_api_key": "***REDACTED***" if self.openai_api_key else "(not set)",
            "gemini_api_key": "***REDACTED***" if self.gemini_api_key else "(not set)",
        }


def load_dotenv_file(env_path: Path) -> None:
    """Lightweight .env file loader."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def get_settings(env_path: Path | None = None) -> Settings:
    """Load settings from environment variables and optional .env file."""
    root = Path(__file__).resolve().parents[2]
    load_dotenv_file(env_path or (root / ".env"))

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    raw_llm_provider = os.environ.get("LLM_PROVIDER", "").strip()
    if raw_llm_provider:
        llm_provider = raw_llm_provider
    elif gemini_key:
        llm_provider = "gemini"
    elif openai_key:
        llm_provider = "openai"
    else:
        llm_provider = "deterministic_research"

    return Settings(
        project_root=root,
        trading_mode=os.environ.get("TRADING_MODE", "paper"),
        live_trading_operator_approval_token=os.environ.get("LIVE_TRADING_OPERATOR_APPROVAL_TOKEN", ""),
        initial_capital_usd=float(os.environ.get("INITIAL_CAPITAL_USD", "100000.0")),
        base_currency=os.environ.get("BASE_CURRENCY", "USD"),
        benchmark_ticker=os.environ.get("BENCHMARK_TICKER", "SPY"),
        holding_period_min_days=int(os.environ.get("HOLDING_PERIOD_MIN_DAYS", "3")),
        holding_period_max_days=int(os.environ.get("HOLDING_PERIOD_MAX_DAYS", "15")),
        market_timezone=os.environ.get("MARKET_TIMEZONE", "America/New_York"),
        operator_timezone=os.environ.get("OPERATOR_TIMEZONE", "Asia/Singapore"),
        database_url=os.environ.get("DATABASE_URL", ""),
        market_data_provider=os.environ.get("MARKET_DATA_PROVIDER", "alpaca"),
        llm_provider=llm_provider,
        llm_model=os.environ.get("LLM_MODEL", "gemini-2.5-pro"),
        alpaca_api_key=os.environ.get("ALPACA_API_KEY", ""),
        alpaca_secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
        alpaca_api_key_2=os.environ.get("ALPACA_API_KEY_2", ""),
        alpaca_secret_key_2=os.environ.get("ALPACA_SECRET_KEY_2", ""),
        alpaca_api_key_3=os.environ.get("ALPACA_API_KEY_3", ""),
        alpaca_secret_key_3=os.environ.get("ALPACA_SECRET_KEY_3", ""),
        alpaca_paper_base_url=os.environ.get("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets"),
        polygon_api_key=os.environ.get("POLYGON_API_KEY", ""),
        fmp_api_key=os.environ.get("FMP_API_KEY", ""),
        finnhub_api_key=os.environ.get("FINNHUB_API_KEY", ""),
        sec_edgar_user_agent=os.environ.get(
            "SEC_EDGAR_USER_AGENT", "SwingTradingResearchPlatform research@example.com"
        ),
        openai_api_key=openai_key,
        gemini_api_key=gemini_key,
        api_host=os.environ.get("API_HOST", "127.0.0.1"),
        api_port=int(os.environ.get("API_PORT", "8080")),
    )

