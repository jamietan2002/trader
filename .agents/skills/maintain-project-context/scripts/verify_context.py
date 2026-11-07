#!/usr/bin/env python3
"""Automated Project Context, Safety Invariant & Test Suite Verifier.

Run by AI agents before completing any implementation task per the
`maintain-project-context` skill.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REQUIRED_CONTEXT_FILES = [
    "AGENTS.md",
    "GEMINI.md",
    "USER_GUIDE.md",
    "core/AGENTS.md",
    "agents/AGENTS.md",
    "docs/AGENT_CHANGELOG.md",
    "README.md",
    "ARCHITECTURE.md",
    "STRATEGY_GUIDE.md",
    "DATA_SOURCES.md",
    "BACKTESTING_METHODOLOGY.md",
    "DEPLOYMENT.md",
    "ENVIRONMENT_VARIABLES.md",
    ".env.example",
    ".agents/skills/maintain-project-context/SKILL.md",
    ".agents/skills/maintain-project-context/references/update_checklist.md",
]

REQUIRED_AGENTS_MD_MODULES = [
    "main.py",
    "infrastructure/configuration/settings.py",
    "infrastructure/database/db.py",
    "infrastructure/logging/logger.py",
    "infrastructure/scheduler/orchestrator.py",
    "core/market_data/models.py",
    "core/market_data/providers.py",
    "core/indicators/technical.py",
    "core/strategies/registry.py",
    "core/backtesting/engine.py",
    "core/risk/manager.py",
    "core/execution/paper_broker.py",
    "evaluation/metrics/performance.py",
    "agents/base.py",
    "agents/market_researcher/agent.py",
    "agents/strategy_architect/agent.py",
    "agents/strategy_evaluator/agent.py",
    "agents/performance_analyst/agent.py",
    "agents/risk_manager/agent.py",
    "api/server.py",
    "dashboard/ui_template.py",
    "tests/test_platform.py",
]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(repo_root))

    print("=" * 76)
    print("MAINTAIN-PROJECT-CONTEXT: VERIFYING CONTEXT FILES, INVARIANTS & TEST SUITE")
    print("=" * 76)

    # 1. Verify all required context and documentation files exist and are non-empty
    missing_or_empty: list[str] = []
    for rel_path in REQUIRED_CONTEXT_FILES:
        p = repo_root / rel_path
        if not p.exists() or p.stat().st_size < 50:
            missing_or_empty.append(rel_path)

    if missing_or_empty:
        print(f"[FAIL] Missing or empty required context files: {missing_or_empty}")
        return 1
    print(f"[PASS] All {len(REQUIRED_CONTEXT_FILES)} context, skill, and documentation files present.")

    # 2. Verify AGENTS.md documents all core modules
    agents_md_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    undocumented = [m for m in REQUIRED_AGENTS_MD_MODULES if m not in agents_md_text]
    if undocumented:
        print(f"[FAIL] Modules missing from AGENTS.md Codebase Map: {undocumented}")
        return 1
    print(f"[PASS] All {len(REQUIRED_AGENTS_MD_MODULES)} core modules are indexed in AGENTS.md.")

    # 3. Verify TRADING_MODE=paper safety lock is active
    from infrastructure.configuration.settings import LiveTradingProhibitedError, Settings

    try:
        Settings(trading_mode="live")
        print("[FAIL] Settings(trading_mode='live') did NOT raise LiveTradingProhibitedError!")
        return 1
    except LiveTradingProhibitedError:
        print("[PASS] TRADING_MODE=paper safety lock verified (LiveTradingProhibitedError active).")

    # 4. Run full automated unit & integration test suite
    print("[INFO] Running automated unit and integration test suite...")
    res = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print("[FAIL] Unit/Integration tests failed:")
        print(res.stdout)
        print(res.stderr)
        return 1

    print("[PASS] All unit and integration tests passed.")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())

