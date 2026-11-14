# Deployment & Zero-Cost Autonomous Hosting Guide

## 1. Zero-Cost Autonomous Cloud Architecture (Recommended)

This repository is pre-configured for **100% free, zero-maintenance autonomous operation** combining:
1. **GitHub Actions (`.github/workflows/autonomous_trading.yml`)**:
   - **Daily Run (Mon–Fri, 21:30 UTC / after US Market Close)**: Automatically ingests daily market bars (via Alpaca Markets or built-in fallback), scans the US equity universe (`MarketResearchAgent`), executes approved `PAPER_TRADING` strategy signals in your `$100,000` paper account (`PaperTradingEngine`), reconciles P&L, runs the `PerformanceAnalystAgent`, and commits the updated SQLite state (`data/swing_trader.db`) back to the repository.
   - **Weekly Self-Improvement Loop (Saturday, 02:00 UTC / 10:00 AM SGT)**: Reviews post-session attribution and weaknesses, generates new falsifiable `StrategyConfig` hypotheses (`StrategyDiscoveryAgent`), runs the 3-split Backtest + 4-Window Walk-Forward + Cost Stress Test pipeline, and automatically promotes or rejects candidates via the 9-gate `StrategyEvaluationAgent`.
2. **Streamlit Community Cloud (`dashboard/streamlit_app.py`)**:
   - Connects directly to your GitHub repo (`jamietan2002/trader`) and hosts your **v2.2 4-Tab Autonomous Paper Hub** (Day-by-Day Pod Decision Journal, Numbers-First Entry & 4-Step Exit Plans, 3-Pod Strategy Rules Cheat-Sheet, and Post-Trade Mistake Analyzer) 24/7 for free. Every time GitHub Actions commits updated state to `data/swing_trader.db` (or when you click `Sync All 3 Alpaca Pods & News Now`), your live dashboard refreshes automatically.

### One-Time Setup Steps (Takes ~3 Minutes)
1. **Merge PR #1 into `main`** on GitHub (`https://github.com/jamietan2002/trader/pull/1`).
2. **Add Your Free Alpaca Paper API Keys (Optional but Recommended)**:
   - Sign up for a free Paper Trading account at [https://app.alpaca.markets](https://app.alpaca.markets).
   - Generate your **Paper API Key ID** and **Secret Key**.
   - In your GitHub repo, go to **Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions $\rightarrow$ New repository secret** and add:
     - `ALPACA_API_KEY`
     - `ALPACA_SECRET_KEY`
   - *(Note: Even before you add these secrets, the workflow runs seamlessly using the deterministic `local_seeded` fallback dataset.)*
3. **Connect Streamlit Community Cloud (Free 24/7 Dashboard)**:
   - Go to [https://share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
   - Click **Create app**:
     - **Repository**: `jamietan2002/trader`
     - **Branch**: `main`
     - **Main file path**: `dashboard/streamlit_app.py`
   - Click **Deploy**. You will get a permanent public/private URL where you can check your portfolio once a week.

---

## 2. Local Standalone Execution (Development)

```bash
# 1. Create virtual environment
/Library/GoogleCorpSupport/Python/3.11/bin/python3 -m venv .venv

# 2. Configure environment variables
cp .env.example .env

# 3. Bootstrap database, baseline strategies, and run end-to-end demo
.venv/bin/python main.py demo

# 4. Start the REST API & 7-Tab Web Dashboard
.venv/bin/python main.py serve --host 127.0.0.1 --port 8080
```

Access the dashboard at **`http://127.0.0.1:8080`** and health check at **`http://127.0.0.1:8080/api/health`**.

---

## 2. Scheduled CLI Workflows (Cron / APScheduler)

All workflows are idempotent and US market holiday aware (`America/New_York` trading sessions with `Asia/Singapore` operator reporting timestamps):

```bash
# Run Daily Pre-Market + Paper Execution + Post-Close Review
.venv/bin/python main.py daily --date 2025-06-27

# Run Weekly AI Strategy Discovery + Walk-Forward Validation
.venv/bin/python main.py weekly --date 2025-06-27
```

---

## 3. Docker Compose Deployment (PostgreSQL + App Container)

```bash
docker compose up --build -d
```
- **Web Dashboard & REST API**: `http://localhost:8080`
- **PostgreSQL 16**: `localhost:5432` (`swing_trader` database)

---

## 4. Streamlit Dashboard (When `streamlit` is installed)

```bash
streamlit run dashboard/streamlit_app.py
```

