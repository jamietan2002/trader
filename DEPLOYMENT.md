# Deployment Guide

## 1. Local Standalone Execution (Recommended for Development)

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

