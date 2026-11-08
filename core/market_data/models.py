"""Market data domain models and US trading calendar utilities."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class EquityMetadata:
    ticker: str
    company_name: str
    exchange: str  # NYSE | NASDAQ
    sector: str
    industry: str
    market_cap_usd: float
    is_active: bool = True
    delisted_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DailyBar:
    ticker: str
    bar_date: str  # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float
    adj_open: float
    adj_high: float
    adj_low: float
    adj_close: float
    adj_volume: float
    split_factor: float = 1.0
    dividend_amount: float = 0.0
    provider_source: str = "local_seeded"
    retrieved_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EarningsEvent:
    ticker: str
    report_date: str  # YYYY-MM-DD
    fiscal_period: str
    announcement_session: str  # BMO | AMC
    eps_estimate: float
    eps_actual: float
    eps_surprise_pct: float
    revenue_estimate_M: float
    revenue_actual_M: float
    revenue_growth_yoy_pct: float
    guidance_delta_pct: float
    public_release_timestamp: str  # Point-in-time availability timestamp
    provider_source: str = "local_seeded"

    def is_publicly_available_as_of(self, eval_date: str) -> bool:
        """Prevent look-ahead bias: AMC earnings on date T are only tradable starting T+1."""
        if self.announcement_session.upper() == "BMO":
            return eval_date >= self.report_date
        # AMC (After Market Close) is only actionable on the next trading day strictly after report_date
        return eval_date > self.report_date

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketCatalyst:
    ticker: str
    published_date: str
    published_timestamp: str
    catalyst_type: str  # NEWS | SEC_10K | SEC_10Q | SEC_8K | ANALYST
    headline: str
    summary: str
    sentiment_score: float  # -1.0 to +1.0
    source_name: str
    url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class USTradingCalendar:
    """US Equities (NYSE/NASDAQ) trading calendar and holiday calculator."""

    FIXED_HOLIDAYS = {
        (1, 1),   # New Year's Day
        (6, 19),  # Juneteenth
        (7, 4),   # Independence Day
        (12, 25), # Christmas Day
    }

    @classmethod
    def is_trading_day(cls, d: date) -> bool:
        if d.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        if (d.month, d.day) in cls.FIXED_HOLIDAYS:
            return False
        # Observe Friday if fixed holiday falls on Saturday, Monday if Sunday
        for m, day_num in cls.FIXED_HOLIDAYS:
            try:
                hol = date(d.year, m, day_num)
                if hol.weekday() == 5 and d == hol - timedelta(days=1):
                    return False
                if hol.weekday() == 6 and d == hol + timedelta(days=1):
                    return False
            except ValueError:
                pass
        # Thanksgiving (4th Thursday of November)
        if d.month == 11 and d.weekday() == 3 and 22 <= d.day <= 28:
            return False
        # Memorial Day (Last Monday of May)
        if d.month == 5 and d.weekday() == 0 and d.day >= 25:
            return False
        # Labor Day (1st Monday of September)
        if d.month == 9 and d.weekday() == 0 and d.day <= 7:
            return False
        # MLK Day (3rd Monday of January)
        if d.month == 1 and d.weekday() == 0 and 15 <= d.day <= 21:
            return False
        # Presidents' Day (3rd Monday of February)
        if d.month == 2 and d.weekday() == 0 and 15 <= d.day <= 21:
            return False
        return True

    @classmethod
    def get_trading_days(cls, start_date: str | date, end_date: str | date) -> List[str]:
        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)
        days: List[str] = []
        curr = start_date
        while curr <= end_date:
            if cls.is_trading_day(curr):
                days.append(curr.isoformat())
            curr += timedelta(days=1)
        return days

    @classmethod
    def next_trading_day(cls, from_date: str | date, include_same_day: bool = False) -> str:
        if isinstance(from_date, str):
            from_date = date.fromisoformat(from_date)
        curr = from_date if include_same_day else (from_date + timedelta(days=1))
        while not cls.is_trading_day(curr):
            curr += timedelta(days=1)
        return curr.isoformat()

    @classmethod
    def previous_trading_day(cls, from_date: str | date, include_same_day: bool = True) -> str:
        if isinstance(from_date, str):
            from_date = date.fromisoformat(from_date)
        curr = from_date if include_same_day else (from_date - timedelta(days=1))
        while not cls.is_trading_day(curr):
            curr -= timedelta(days=1)
        return curr.isoformat()

    @classmethod
    def non_trading_reason(cls, d: str | date) -> str:
        if isinstance(d, str):
            d = date.fromisoformat(d)
        if cls.is_trading_day(d):
            return "Open Trading Session"
        if d.weekday() == 5:
            return "Weekend (Saturday — US Markets Closed)"
        if d.weekday() == 6:
            return "Weekend (Sunday — US Markets Closed)"
        return "NYSE / NASDAQ Market Holiday (US Markets Closed)"

