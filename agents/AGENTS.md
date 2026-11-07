# agents/AGENTS.md — AI Agent Layer Engineering Rules

Rules for modifying or adding AI agents inside `agents/` (`market_researcher`, `strategy_architect`, `strategy_evaluator`, `performance_analyst`, `risk_manager`):

1. **Role Permission Enforcement (`agents/base.py`)**:
   - Every agent class must inherit from `BaseAgent` and define a unique `role_name`.
   - Every public agent workflow method must call `self.assert_permission("<action_name>")` before reading or writing state.
   - Allowed and forbidden actions are defined in `AGENT_PERMISSIONS` and `FORBIDDEN_AGENT_TOOLS` in `agents/base.py`.
2. **Strict Separation of Duties**:
   - `MarketResearchAgent` (`market_researcher`) must **never** execute orders, modify the portfolio, or promote strategies. Furthermore, `research_confidence_score` must always include a disclaimer stating it measures point-in-time evidence completeness rather than a calibrated probability of profit.
   - `StrategyDiscoveryAgent` (`strategy_architect`) must **never** bypass `StrategyConfig` validation or directly promote strategies; it may only register strategies in `DRAFT` status.
   - `StrategyEvaluationAgent` (`strategy_evaluator`) must **never** promote a strategy based solely on positive headline return; all 9 statistical & risk-adjusted gates in `PromotionCriteriaConfig` must be checked.
   - `PerformanceAnalystAgent` (`performance_analyst`) must **never** directly overwrite an active `PAPER_TRADING` strategy; it must emit an `ExperimentProposal` stored in `experiment_proposals`.
3. **Structured Output Validation**:
   - All LLM responses must go through `self.llm.generate_structured_json(system_prompt, user_prompt, fallback_payload)` so the system degrades gracefully and deterministically when offline or when external LLM API keys are not set.
   - All returned dictionaries/dataclasses must be validated via `validate_required_fields(payload, SCHEMA_TYPES, schema_name)`.

