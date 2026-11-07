---
name: run-ai-cycle
description: >-
  Activate this skill immediately whenever the user types "run", "run daily", "run weekly",
  or asks to execute the daily/weekly AI trading workflow from this IDE. Uses the Antigravity
  IDE's built-in LLM and live web search (`search_web`) to enrich stock research with real-time
  news catalysts, design P&L-maximizing strategy parameter candidates, evaluate them in a
  9-gate Out-of-Sample & Walk-Forward tournament (`ide-apply`), sync the database to GitHub,
  and present a concise daily action plan for the user's real account.
---

# IDE-Native AI Trading & Alpha Optimization Workflow (`run`)

This skill turns the **Antigravity IDE LLM** into the platform's Chief Quantitative Strategist & News Catalyst Analyst—requiring **zero external OpenAI/Gemini API keys** in `.env`.

While the deterministic core (`core/`, `evaluation/`) handles exact price adjustments, technical indicators, ATR position sizing, and order accounting, **you (the IDE AI Agent)** provide:
1. **Real-Time Qualitative Catalyst & News Intelligence (`search_web`)** on top technical setups and open holdings.
2. **Regime-Adaptive Strategy Hypothesis Generation** to maximize Out-of-Sample Net P&L and Deflated Sharpe Ratio (`DSR`).

---

## Step-by-Step Execution Runbook (Triggered by typing `"run"`)

Whenever the user types **`run`** (or `run daily` / `run weekly`), execute all 4 steps below automatically without asking for confirmation:

### Step 1: Sync State & Export Deterministic Market Context
Run the deterministic daily pipeline and export the compact JSON state packet:
```bash
git pull --rebase origin main || true
.venv/bin/python main.py ide-context
```
Inspect the JSON output:
- `session_date` and `market_regime` (`SPY` trend, RSI, 20-day return, 20-day annualized volatility).
- `top_research_candidates`: Top ranked US equities (`ticker`, `rs_20d_vs_spy_pct`, `volume_ratio_20`, `rsi_14`, `consolidation_10d_pct`, `suggested_strategy_family`).
- `active_paper_strategies`: Current `PAPER_TRADING` versions, their `entry_rules`, `exit_rules`, and `backtest_metrics` (`total_return_pct`, `sharpe_ratio`, `deflated_sharpe_pct`, `profit_factor`, `max_drawdown_pct`).
- `live_copilot_action_plan`: Current `SELL`, `HOLD` (with $+1.25\text{R}$ Breakeven / $+1.5\text{R}$ Chandelier ratcheted stops), and `BUY` recommendations for the user's real account.

### Step 2: Live Web Search for Real-Time News & Catalysts (`search_web`)
Call `search_web` on the top 2–3 ranked candidates (and any stocks with pending `BUY` signals in `live_copilot_action_plan`):
- Check for **earnings call reactions, guidance upgrades/downgrades, product/FDA/contract catalysts, regulatory risks, or macro sector headwinds**.
- Synthesize concise, factual `bullish_thesis`, `bearish_thesis`, `catalyst_assessment`, `main_risks`, and an updated `research_confidence_score` (`0.50` to `0.95`) for each searched ticker.

### Step 3: Design & Run the AI Strategy Alpha Tournament (`ide-apply`)
Based on the detected `market_regime`, recent closed trade attribution (`recent_closed_paper_trades`), and active strategy parameters, design **2 to 3 targeted `candidate_strategies`** aimed at increasing risk-adjusted Net P&L and Deflated Sharpe Ratio:
- **Valid `entry_rules_patch` keys**:
  - `rs_20d_min` (e.g., `0.015` to `0.045`), `volume_ratio_min` (e.g., `1.05` to `1.45`), `rsi_min` / `rsi_max` (e.g., `48` to `74`), `max_10d_range_pct` (for `strat_volatility_breakout`, e.g., `0.055` to `0.085`), `min_eps_surprise_pct` (for `strat_pead_earnings`, e.g., `3.0` to `6.0`).
- **Valid `exit_rules_patch` keys**:
  - `stop_loss_atr_mult` (e.g., `1.6` to `2.4`), `take_profit_atr_mult` (e.g., `3.0` to `4.5`), `trailing_stop_atr_mult` (e.g., `2.0` to `2.8`).
- **Valid `holding_period_max_days`**: Integer between `5` and `18`.

Apply both your qualitative research updates (including `sentiment_score` from `-1.0` to `+1.0`) and your strategy tournament candidates using `main.py ide-apply` (which also persists `IDE_AI_RESEARCH` catalyst records to `market_catalysts` and logs `ide_ai_cycle` in `job_executions` so the dashboard's **IDE AI Reminder Checklist** turns green):
```bash
.venv/bin/python main.py ide-apply --json '{
  "research_updates": [
    {
      "ticker": "NVDA",
      "bullish_thesis": "...",
      "bearish_thesis": "...",
      "catalyst_assessment": "...",
      "main_risks": ["...", "..."],
      "sentiment_score": 0.78,
      "research_confidence_score": 0.88
    }
  ],
  "analyst_proposal": {
    "target_strategy_id": "strat_momentum_trend",
    "market_regime": "BULL_LOW_VOL",
    "diagnosis_summary": "...",
    "proposed_hypothesis": "...",
    "parameter_adjustments": {"entry_rules_patch": {...}, "exit_rules_patch": {...}}
  },
  "candidate_strategies": [
    {
      "target_strategy_id": "strat_momentum_trend",
      "name": "Momentum & Relative Strength Leader (AI Regime-Tuned)",
      "hypothesis": "...",
      "entry_rules_patch": {"rs_20d_min": 0.025, "volume_ratio_min": 1.15},
      "exit_rules_patch": {"stop_loss_atr_mult": 1.9, "take_profit_atr_mult": 3.8},
      "holding_period_max_days": 12
    }
  ]
}'
```
> **Note on Safety & Incumbent Protection**: `ide-apply` runs every candidate through the full chronological In-Sample / Validation / Out-of-Sample / 4-Window Walk-Forward / 2x Cost Stress-Test pipeline. The `StrategyEvaluationAgent` will **only** promote a candidate to `PAPER_TRADING` if it passes all 9 validation gates **and** matches or beats the incumbent champion version's Sharpe/Return/Calmar metrics.

### Step 4: Push Updated Database to Cloud & Present Executive Briefing
1. Commit and push the updated `data/swing_trader.db` so the 24/7 Streamlit Cloud dashboard immediately reflects the AI research and any promoted strategy versions:
   ```bash
   git add data/swing_trader.db
   git diff --cached --quiet || git commit -m "IDE AI Cycle: enrich research catalysts & run strategy optimization tournament"
   git push origin main || true
   ```
2. Present a concise **Executive AI Trading Briefing** to the user in chat:
   - **Market Regime & Macro Pulse**: Current `SPY` regime and key takeaways.
   - **AI Catalyst Research Highlights**: What live news/catalysts were found on top candidates.
   - **AI Strategy Tournament Verdict**: Which candidate hypotheses were tested, their Out-of-Sample Return / Sharpe / Deflated Sharpe (`DSR %`), and whether a new version beat the incumbent champion.
   - **Today's Real-Account Copilot Checklist**: Any `SELL` exits, `HOLD` stop-loss ratchets ($+1.25\text{R}$ Breakeven or $+1.5\text{R}$ Chandelier trail), and `BUY` setups with exact share counts and bracket stop/target prices.

