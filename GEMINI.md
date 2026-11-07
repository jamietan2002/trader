# GEMINI.md — Workspace Rules & Context Pointer

@[AGENTS.md](./AGENTS.md)

## Quick Verification & Maintenance Checklist
1. **Always keep deterministic quantitative logic (`core/`, `evaluation/`) separate from AI agent reasoning (`agents/`).**
2. **Never weaken `TRADING_MODE=paper` or log secrets.**
3. **For every code change or new feature, activate and follow the `maintain-project-context` skill (`.agents/skills/maintain-project-context/SKILL.md`)** to keep `AGENTS.md`, `USER_GUIDE.md`, `docs/AGENT_CHANGELOG.md`, tests, and architecture documentation synchronized.

