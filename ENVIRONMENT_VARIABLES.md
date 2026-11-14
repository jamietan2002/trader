# Environment Variables Reference

All environment variables are loaded via `infrastructure/configuration/settings.py` (with automatic secret redaction in `infrastructure/logging/logger.py`).

| Variable | Default | Description |
|---|---|---|
| `TRADING_MODE` | `paper` | **Strictly enforced**. Must be `paper`. Any other value raises `LiveTradingProhibitedError`. |
| `INITIAL_CAPITAL_USD` | `100000.0` | Starting cash balance for the paper brokerage account (`$100,000 USD`). |
| `BASE_CURRENCY` | `USD` | Account base currency. |
| `BENCHMARK_TICKER` | `SPY` | Market benchmark ticker for Relative Strength and performance comparison. |
| `HOLDING_PERIOD_MIN_DAYS` | `3` | Default minimum swing holding period (trading days). |
| `HOLDING_PERIOD_MAX_DAYS` | `15` | Default maximum swing holding period (trading days). |
| `MARKET_TIMEZONE` | `America/New_York` | US equity market timezone (`NYSE`/`NASDAQ`). |
| `OPERATOR_TIMEZONE` | `Asia/Singapore` | Operator reporting timezone. |
| `DATABASE_URL` | `sqlite:///data/swing_trader.db` | Relational database connection URL (SQLite or PostgreSQL). |
| `MARKET_DATA_PROVIDER` | `alpaca` | Active provider: `alpaca` (with automatic `local_seeded` fallback), `local_seeded`, `polygon`, `fmp`, or `finnhub`. |
| `ALPACA_API_KEY` | *(empty)* | Alpaca Paper Pod #1 (`pod_1_breakout`) API key ID (redacted in logs). |
| `ALPACA_SECRET_KEY` | *(empty)* | Alpaca Paper Pod #1 (`pod_1_breakout`) secret key (redacted in logs). |
| `ALPACA_API_KEY_2` | *(empty)* | Alpaca Paper Pod #2 (`pod_2_mean_reversion`) API key ID (redacted in logs). |
| `ALPACA_SECRET_KEY_2` | *(empty)* | Alpaca Paper Pod #2 (`pod_2_mean_reversion`) secret key (redacted in logs). |
| `ALPACA_API_KEY_3` | *(empty)* | Alpaca Paper Pod #3 (`pod_3_momentum`) API key ID (redacted in logs). |
| `ALPACA_SECRET_KEY_3` | *(empty)* | Alpaca Paper Pod #3 (`pod_3_momentum`) secret key (redacted in logs). |
| `ALPACA_PAPER_BASE_URL` | `https://paper-api.alpaca.markets` | Alpaca paper trading endpoint. |
| `POLYGON_API_KEY` | *(empty)* | Polygon.io / Massive API key. |
| `FMP_API_KEY` | *(empty)* | Financial Modeling Prep API key. |
| `FINNHUB_API_KEY` | *(empty)* | Finnhub API key. |
| `SEC_EDGAR_USER_AGENT` | `SwingTradingResearchPlatform research@example.com` | Required `User-Agent` header for SEC EDGAR requests. |
| `LLM_PROVIDER` | `deterministic_research` | Active AI reasoning provider: `deterministic_research`, `gemini`, or `openai`. |
| `LLM_MODEL` | `gemini-2.5-pro` | Model identifier for LLM provider. |
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API key (redacted in logs). |
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key (redacted in logs). |
| `API_HOST` | `127.0.0.1` | Host interface for the web dashboard and REST API server. |
| `API_PORT` | `8080` | Port for the web dashboard and REST API server. |

