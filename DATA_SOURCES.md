# Market Data Infrastructure & Provider Evaluation

## 1. Provider Evaluation Matrix

| Provider | Historical Coverage | Point-in-Time Fundamentals & Earnings | Free Tier / Rate Limits | Licensing & Best Role in Platform |
|---|---|---|---|---|
| **Alpaca Markets** (`alpaca`) | 5+ years daily & intraday US equities (`NYSE`/`NASDAQ`) | Basic corporate actions & news; limited historical estimates | 200 req/min on free paper tier; IEX real-time / SIP delayed | Primary paper brokerage & daily OHLCV bar source |
| **Polygon.io / Massive** (`polygon`) | 10+ years full SIP history, splits, dividends, tickers | Reference financials & corporate actions | 5 req/min on free tier; unlimited on paid tiers | Institutional-grade historical OHLCV & delisted tickers |
| **Financial Modeling Prep** (`fmp`) | 10+ years financial statements, earnings calendar | Strong EPS/revenue consensus estimates & surprises | 250 req/day on free tier | Earnings surprise & fundamental ratios |
| **Finnhub** (`finnhub`) | Global & US equities, company news, insider filings | Good earnings surprises & sentiment | 60 req/min on free tier | Real-time news & earnings calendar |
| **SEC EDGAR** (`sec_edgar`) | Full history of `10-K`, `10-Q`, `8-K` filings | Authoritative point-in-time `acceptanceDateTime` | Free public access (10 req/sec with `User-Agent` header) | Authoritative filing timestamps to prevent look-ahead bias |
| **Local Seeded Provider** (`local_seeded`) | Multi-year multi-regime US equities + `SPY` + delisted security | Exact `BMO`/`AMC` timestamps, EPS/Rev surprises, `8-K` catalysts | Unlimited local deterministic execution | Default zero-key MVP dataset & deterministic CI testing |

---

## 2. Provider Abstraction & Caching (`core/market_data/providers.py`)

All providers implement the `MarketDataProvider` abstract base class:
- `get_universe() -> List[EquityMetadata]`
- `fetch_daily_bars(ticker, start_date, end_date) -> List[DailyBar]`
- `fetch_earnings_events(ticker, start_date, end_date) -> List[EarningsEvent]`
- `fetch_catalysts(ticker, start_date, end_date) -> List[MarketCatalyst]`

### Data Integrity & Bias Prevention
1. **Point-in-Time Earnings Timestamps**: Every `EarningsEvent` records `announcement_session` (`BMO` vs `AMC`) and `public_release_timestamp`. An `AMC` earnings report on date $T$ (e.g., `16:15 ET`) returns `is_publicly_available_as_of(T) == False` and only becomes actionable on date $T+1$.
2. **Survivorship Bias Protection**: `equities_universe` includes `is_active` and `delisted_date` (e.g., `FRC_DELIST` delisting on `2024-06-14`). Historical backtests include delisted securities up to their delisting bar.
3. **Split & Dividend Normalization**: `MarketDataService.normalize_and_deduplicate_bars` validates OHLC bounds, deduplicates dates, applies backward cumulative split adjustments, and tracks cash dividends.
4. **Rate Limiting & Persistent Caching**: `HttpRateLimitedClient` enforces minimum inter-request intervals, exponential backoff on HTTP `429`, and caches responses in the `api_cache` table.

