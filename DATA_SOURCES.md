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
   - **Recent-bar cache bypass**: daily-bar requests whose window ends within `RECENT_BAR_NO_CACHE_DAYS = 7` of the last completed session are always fetched live (`use_cache=False`), so a 09:00 ET pre-market payload can never mask the final closing bar fetched at 16:30 ET.
   - **Completed bars only**: Alpaca/Polygon bars dated after `USTradingCalendar.last_completed_session()` (official close + 15 min settle; 13:15 ET on half-days) are dropped, so partial intraday OHLCV is never stored as a daily bar. Upserts refresh `retrieved_at` and `provider_source`.
   - **Freshness gate**: `MarketDataService.sync_session_bars(session)` re-fetches the trailing 21 days, verifies the benchmark bar for `session` was retrieved after that session's close, retries with backoff, and raises `StaleMarketDataError` if it never arrives.
5. **40-Stock Multi-Sector Core + Dynamic Catalyst Onboarding**: `AlpacaDataProvider.EXTENDED_UNIVERSE` covers 40 liquid US equities across 10 GICS sectors, while `MarketDataService.onboard_dynamic_tickers()` dynamically validates (`Price >= $15`, `20d ADV >= $50M/day`, NYSE/NASDAQ, Alpaca `tradable`/`shortable`/`easy_to_borrow`) and backfills emerging catalyst movers.
6. **24/7 Live Alpaca News & Movers Sentiment Scanner**: `MarketDataService.scan_live_alpaca_news_and_movers()` polls `/v1beta1/news` and `/v1beta1/screener/stocks/most-actives` to score real-time news sentiment into `market_catalysts` (`ALPACA_LIVE_NEWS`) without requiring external paid news keys.


