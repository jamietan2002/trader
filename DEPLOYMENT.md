# Deployment & Zero-Cost Autonomous Hosting Guide

## 1. Zero-Cost On-Time Autonomous Cloud Architecture (`$0/month` — Option A)

To eliminate GitHub Actions' native `on: schedule` queue delays (2–8+ hours) and dropped runs, `jamietan2002/trader` uses its own dedicated **External Edge Cron (`Cloudflare Workers` or `cron-job.org`) -> GitHub `workflow_dispatch` REST API** dispatcher (`jamietan2002/spy-daytrader` has its own independent dispatcher in `spy-daytrader/infrastructure/cloudflare_cron/`):

1. **External Edge Cron Dispatcher (`infrastructure/cloudflare_cron/`)**:
   - Evaluates exact **`America/New_York`** wall-clock time (automatically handling `EDT <-> EST` Daylight Saving Time transitions with zero manual cron edits) and triggers GitHub's instant `workflow_dispatch` runner queue (~10s boot):
     - **Mon–Fri `09:00 ET`** -> `stage=pre_open` (final bars for previous session, catch-up reviews, research, pod sync)
     - **Mon–Fri `09:35 ET`** (+ `10:00 ET` backstop) -> `stage=market_open` (paper session + Alpaca pod execution)
     - **Mon–Fri `16:30 ET`** (+ `18:00 ET` backstop) -> `stage=post_close` (waits for today's FINAL bar, then post-close review)
     - **Saturday `02:00 UTC`** (`10:00 AM SGT`) -> `stage=weekly` 9-Gate Strategy Tournament
   - **Reliability guarantees** (`main.py scheduled`): target session derived from the ET clock + exchange calendar; recent bars always fetched live (no cache) and in-progress bars discarded; hard final-bar gate raises `StaleMarketDataError` (red run + GitHub email) instead of skipping; every stage back-fills missed post-close reviews from the last 5 sessions; backstops are idempotent no-ops when the primary succeeded.
2. **GitHub Actions Compute (`.github/workflows/autonomous_trading.yml`)**:
   - Native `on: schedule` is intentionally disabled so late GitHub crons never double-fire or cancel active sessions.
   - Executes on free unlimited public-repo `ubuntu-latest` runners via `workflow_dispatch` and commits updated `data/swing_trader.db` back to `main`.
3. **Streamlit Community Cloud (`dashboard/streamlit_app.py`)**:
   - Connects directly to `jamietan2002/trader` and hosts the Minimalist Dark 3-Tab Autonomous Paper Portfolio Hub (`Overview & Open Trades`, `Daily Journal`, `Performance & System`) 24/7 for `$0/month`.

---

### One-Time External Cron Activation (~3 Minutes, `$0/month`)

#### Step 1: Create a Fine-Grained GitHub Personal Access Token (`GITHUB_PAT`)
1. Go to **GitHub -> Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens -> Generate new token**.
2. **Repository access**: Select **Only select repositories** -> pick **`jamietan2002/trader`** *(or both `trader` and `spy-daytrader` if sharing one token across both Workers)*.
3. **Repository permissions**: Set **`Actions` -> `Read and write`** (leave all other permissions as No access).
4. Copy the generated token (`github_pat_...`).

#### Step 2A (Recommended): Connect Cloudflare Workers Directly to GitHub
1. Sign in to the free [Cloudflare Dashboard](https://dash.cloudflare.com) -> **Workers & Pages -> Create -> Import a repository** (GitHub).
2. Select **`jamietan2002/trader`**, set **Root directory** to **`infrastructure/cloudflare_cron`**, leave Build command empty, and set Deploy command to `npx wrangler deploy`.
   - Cloudflare auto-deploys `worker.js` and `wrangler.toml` (including the `*/5 * * * *` Cron Trigger) on every push to `main`.
3. Go to the Worker's **Settings -> Variables and Secrets -> Add**:
   - Type: **Secret**, Name: `GITHUB_PAT`, Value: `<your-fine-grained-token>`.
   *(Repeat in a second Worker connected to `jamietan2002/spy-daytrader` with Root directory `infrastructure/cloudflare_cron`.)*

#### Step 2B (Alternative — Zero Cloudflare Account): Auto-Provision on `cron-job.org`
1. Create a free account at [https://console.cron-job.org](https://console.cron-job.org) -> **Settings -> API Keys -> Create API Key**.
2. Run the zero-dependency provisioning script locally to create/update all 4 `trader` jobs in one command:
   ```bash
   # Preview scrubbed job definitions (no secrets required):
   .venv/bin/python infrastructure/cloudflare_cron/setup_cronjob_org.py --dry-run

   # Create or update all 4 schedules on cron-job.org:
   CRONJOB_API_KEY="<your-cronjob-api-key>" GITHUB_PAT="<your-github-pat>" \
     .venv/bin/python infrastructure/cloudflare_cron/setup_cronjob_org.py
   ```

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

## 3. Scheduled CLI Workflows

All workflows are idempotent and US market holiday aware (`America/New_York` trading sessions with `Asia/Singapore` operator reporting timestamps):

```bash
# Run Daily Pre-Market + Paper Execution + Post-Close Review
.venv/bin/python main.py daily --date 2025-06-27

# Run Weekly AI Strategy Discovery + Walk-Forward Validation
.venv/bin/python main.py weekly --date 2025-06-27
```

---

## 4. Docker Compose & Streamlit Dashboard

```bash
# Docker Compose (PostgreSQL + App Container)
docker compose up --build -d

# Local Minimalist Dark 3-Tab Streamlit Hub
streamlit run dashboard/streamlit_app.py
```

Configured via `.streamlit/config.toml` (`#0c0e12` matte dark canvas, full-width no-sidebar header, and 3 beginner-friendly tabs: `Overview & Open Trades`, `Daily Journal`, and `Performance & System`).
