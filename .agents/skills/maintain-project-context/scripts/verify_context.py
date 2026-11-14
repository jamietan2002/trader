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

    # 4. Verify Headless Runtime Execution of dashboard/streamlit_app.py across all tabs & branches
    print("[INFO] Running headless multi-branch runtime check on dashboard/streamlit_app.py...")
    try:
        import types

        class _MockStContext:
            def __init__(self, root: "_MockStreamlit") -> None:
                self._root = root

            def __enter__(self) -> "_MockStContext":
                return self

            def __exit__(self, *args: object) -> bool:
                return False

            def __getattr__(self, name: str) -> object:
                return getattr(self._root, name)

        class _MockStreamlit(types.ModuleType):
            def __init__(self) -> None:
                super().__init__("streamlit")
                self.session_state: dict = {}
                self.sidebar = _MockStContext(self)

            def set_page_config(self, **kwargs: object) -> None: pass
            def title(self, *args: object, **kwargs: object) -> None: pass
            def header(self, *args: object, **kwargs: object) -> None: pass
            def subheader(self, *args: object, **kwargs: object) -> None: pass
            def markdown(self, *args: object, **kwargs: object) -> None: pass
            def caption(self, *args: object, **kwargs: object) -> None: pass
            def write(self, *args: object, **kwargs: object) -> None: pass
            def info(self, *args: object, **kwargs: object) -> None: pass
            def success(self, *args: object, **kwargs: object) -> None: pass
            def warning(self, *args: object, **kwargs: object) -> None: pass
            def error(self, *args: object, **kwargs: object) -> None: pass
            def metric(self, *args: object, **kwargs: object) -> None: pass
            def dataframe(self, *args: object, **kwargs: object) -> None: pass
            def table(self, *args: object, **kwargs: object) -> None: pass
            def json(self, *args: object, **kwargs: object) -> None: pass
            def line_chart(self, *args: object, **kwargs: object) -> None: pass
            def bar_chart(self, *args: object, **kwargs: object) -> None: pass
            def code(self, *args: object, **kwargs: object) -> None: pass
            def divider(self, *args: object, **kwargs: object) -> None: pass
            def progress(self, *args: object, **kwargs: object) -> None: pass
            def toast(self, *args: object, **kwargs: object) -> None: pass
            def rerun(self) -> None: pass
            def button(self, *args: object, **kwargs: object) -> bool: return False

            def slider(self, label: str, min_value: object = 0, max_value: object = 100, value: object = 25000, **kwargs: object) -> object:
                k = kwargs.get("key")
                return self.session_state.get(k, value) if k else value

            def select_slider(self, label: str, options: object = (), value: object = None, **kwargs: object) -> object:
                opts = list(options)  # type: ignore[call-overload]
                k = kwargs.get("key")
                default_val = value if value is not None else (opts[0] if opts else 1.0)
                return self.session_state.get(k, default_val) if k else default_val

            def checkbox(self, label: str, value: bool = False, **kwargs: object) -> bool:
                k = kwargs.get("key")
                return bool(self.session_state.get(k, value)) if k else value

            def radio(self, label: str, options: object, index: int = 0, **kwargs: object) -> object:
                opts = list(options)  # type: ignore[call-overload]
                k = kwargs.get("key")
                return self.session_state.get(k, opts[index] if opts else None)

            def selectbox(self, label: str, options: object, index: int = 0, format_func: object = None, **kwargs: object) -> object:
                opts = list(options)  # type: ignore[call-overload]
                k = kwargs.get("key")
                val = self.session_state.get(k, opts[index] if opts else None)
                if callable(format_func) and val is not None:
                    format_func(val)
                return val

            def multiselect(self, label: str, options: object, default: object = None, **kwargs: object) -> list:
                k = kwargs.get("key")
                return list(self.session_state.get(k, list(default or [])))  # type: ignore[arg-type]

            def number_input(self, label: str, min_value: object = None, max_value: object = None, value: object = 0.0, **kwargs: object) -> object:
                k = kwargs.get("key")
                return self.session_state.get(k, value) if k else value

            def text_input(self, label: str, value: str = "", **kwargs: object) -> str:
                k = kwargs.get("key")
                return str(self.session_state.get(k, value)) if k else value

            def text_area(self, label: str, value: str = "", **kwargs: object) -> str:
                k = kwargs.get("key")
                return str(self.session_state.get(k, value)) if k else value

            def columns(self, spec: object, **kwargs: object) -> list:
                n = spec if isinstance(spec, int) else len(spec)  # type: ignore[arg-type]
                return [_MockStContext(self) for _ in range(n)]

            def tabs(self, labels: object, **kwargs: object) -> list:
                return [_MockStContext(self) for _ in labels]  # type: ignore[attr-defined]

            def expander(self, *args: object, **kwargs: object) -> _MockStContext: return _MockStContext(self)
            def popover(self, *args: object, **kwargs: object) -> _MockStContext: return _MockStContext(self)
            def spinner(self, *args: object, **kwargs: object) -> _MockStContext: return _MockStContext(self)
            def container(self, *args: object, **kwargs: object) -> _MockStContext: return _MockStContext(self)
            def form(self, *args: object, **kwargs: object) -> _MockStContext: return _MockStContext(self)
            def form_submit_button(self, *args: object, **kwargs: object) -> bool: return False

        mock_st = _MockStreamlit()
        sys.modules["streamlit"] = mock_st
        import dashboard.streamlit_app as st_app

        # Branch 1: Default state (All 3 Pods Day-by-Day Journal)
        st_app.main()
        # Branch 2: Single Pod filtered + Days With New Orders Only in Day-by-Day Journal
        mock_st.session_state["journal_pod_filter"] = "pod_2_mean_reversion"
        mock_st.session_state["journal_activity_filter"] = "Days With New Orders Only"
        st_app.main()
        print("[PASS] Headless multi-branch runtime execution of dashboard/streamlit_app.py succeeded.")
    except Exception as exc:
        import traceback
        print(f"[FAIL] dashboard/streamlit_app.py raised a runtime error: {exc}")
        traceback.print_exc()
        return 1

    # 5. Run full automated unit & integration test suite
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

