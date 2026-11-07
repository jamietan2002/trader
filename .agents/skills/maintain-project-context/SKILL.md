---
name: maintain-project-context
description: >-
  Use this skill on every code implementation, feature addition, refactor, bug fix,
  strategy/indicator/agent update, or schema change in the Swing Trading AI repository.
  Ensures AGENTS.md, GEMINI.md, topical documentation, automated tests, and the
  agent changelog stay strictly synchronized with the codebase.
---

# Maintain Project Context & Documentation Skill

Activate and execute this skill **whenever** you implement a feature, modify code, add an indicator/strategy/agent/data provider, or alter schemas/configurations in the `trader` repository.

## Why This Skill Exists
To keep the Swing Trading AI platform maintainable across multi-agent sessions and future engineering work, no implementation is complete until its context files, architecture docs, changelog, and automated tests are updated and verified.

---

## Step-by-Step Maintenance Workflow

### Step 1: Review Affected Architectural Boundaries
Before finalizing any code changes, verify that your implementation respects the core invariants in [AGENTS.md](../../../AGENTS.md):
1. **Deterministic vs. AI Firewall**: Did any LLM call leak into `core/` or `evaluation/`? (Strictly prohibited).
2. **Safety Guardrail**: Is `TRADING_MODE=paper` still enforced in `infrastructure/configuration/settings.py`?
3. **Bias Prevention**: Are new indicators strictly causal (`bars[0 : i + 1]`)? Do backtest signals on Day `T` fill at Day `T + 1` open?
4. **Strategy Immutability**: Does `StrategyRegistry` still block overwriting `PAPER_TRADING` versions?

### Step 2: Update the Relevant Context & Documentation Files
Use the mapping table in [update_checklist.md](./references/update_checklist.md) to determine which files must be updated based on the directories you touched:

| If You Modified... | You MUST Update... |
|---|---|
| New/changed module, class, or CLI command | `AGENTS.md` (Codebase Map table) & `ARCHITECTURE.md` |
| `core/indicators/` or `core/strategies/` | `STRATEGY_GUIDE.md` & `core/AGENTS.md` |
| `core/market_data/` | `DATA_SOURCES.md` & `core/AGENTS.md` |
| `core/backtesting/`, `core/risk/`, or `evaluation/` | `BACKTESTING_METHODOLOGY.md` & `core/AGENTS.md` |
| `agents/` | `agents/AGENTS.md` & `ARCHITECTURE.md` (Role Permission Matrix) |
| `infrastructure/configuration/settings.py` or `.env.example` | `ENVIRONMENT_VARIABLES.md` & `.env.example` |
| `api/`, `dashboard/`, `Dockerfile`, or `docker-compose.yml` | `DEPLOYMENT.md` & `README.md` |

### Step 3: Add or Update Automated Tests
Every new indicator, strategy rule, risk check, data provider, or agent schema must have a corresponding test assertion in `tests/test_platform.py`.

### Step 4: Append an Entry to `docs/AGENT_CHANGELOG.md`
Add a dated section at the top of `docs/AGENT_CHANGELOG.md` summarizing:
- **Summary**: 1–3 bullets explaining what was implemented or fixed and why.
- **Modules Added / Modified**: Exact file paths and key symbols changed.
- **Verification**: Output of the test and context verification script.

### Step 5: Run the Automated Context & Test Verification Script
Execute the helper script [verify_context.py](./scripts/verify_context.py) to validate that:
1. All required context and documentation files exist and are non-empty.
2. Every core Python package and module is documented in `AGENTS.md`.
3. `TRADING_MODE=paper` safety guardrail is intact.
4. All unit and integration tests pass (`OK`).

```bash
.venv/bin/python .agents/skills/maintain-project-context/scripts/verify_context.py
```

Do not mark an implementation task as complete or push a PR until `verify_context.py` exits with code `0`.

