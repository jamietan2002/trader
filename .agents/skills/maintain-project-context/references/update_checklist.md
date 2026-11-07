# Detailed Context & Documentation Update Checklist

When updating documentation as part of the `maintain-project-context` skill, check each item below:

## 1. Adding a New Technical Indicator (`core/indicators/technical.py`)
- [ ] Add the new field to the `IndicatorSnapshot` dataclass.
- [ ] Compute the indicator causally (using only `bars[0 : i + 1]`) inside `compute_indicator_series()`.
- [ ] Add a unit test in `TestSwingTradingPlatform.test_02_indicator_calculations` (`tests/test_platform.py`).
- [ ] Document the indicator formula and lookback period in `STRATEGY_GUIDE.md` and `core/AGENTS.md`.

## 2. Adding or Modifying a Strategy Family (`core/strategies/registry.py`)
- [ ] Add the enum value to `StrategyFamily` if introducing a new family.
- [ ] Implement deterministic entry/exit evaluation in `StrategySignalEngine.evaluate_entry()` / `evaluate_exit()`.
- [ ] Add template generation support in `StrategyDiscoveryAgent._build_family_template()` (`agents/strategy_architect/agent.py`).
- [ ] Document the observable phenomenon, hypothesis, entry rules, exit rules, and holding period in `STRATEGY_GUIDE.md`.
- [ ] Add entry/exit test coverage in `TestSwingTradingPlatform.test_03_entry_and_exit_rules`.

## 3. Adding or Modifying a Market Data Provider (`core/market_data/providers.py`)
- [ ] Subclass `MarketDataProvider` and implement `get_universe()`, `fetch_daily_bars()`, `fetch_earnings_events()`, and `fetch_catalysts()`.
- [ ] Use `HttpRateLimitedClient` for caching and HTTP `429` exponential backoff.
- [ ] Register the provider key in `MarketDataService.__init__()` and `.env.example`.
- [ ] Document rate limits, point-in-time coverage, and environment variables in `DATA_SOURCES.md` and `ENVIRONMENT_VARIABLES.md`.

## 4. Modifying Risk Limits or Promotion Criteria (`infrastructure/configuration/settings.py`)
- [ ] Update `RiskParametersConfig` or `PromotionCriteriaConfig`.
- [ ] Ensure `PortfolioRiskManager` (`core/risk/manager.py`) or `StrategyEvaluationAgent` (`agents/strategy_evaluator/agent.py`) enforces the updated threshold.
- [ ] Update `BACKTESTING_METHODOLOGY.md` and `AGENTS.md`.

## 5. Adding or Modifying an AI Agent (`agents/`)
- [ ] Subclass `BaseAgent` and register permitted and forbidden actions in `AGENT_PERMISSIONS` / `FORBIDDEN_AGENT_TOOLS` (`agents/base.py`).
- [ ] Define a strict schema dictionary (`*_SCHEMA`) and call `validate_required_fields()` on every output.
- [ ] Update `agents/AGENTS.md`, `USER_GUIDE.md`, and the Role Permission Matrix in `ARCHITECTURE.md`.

## 6. Updating Operator User Guide (`USER_GUIDE.md`)
- [ ] Whenever any workflow, strategy, risk limit, UI tab, or engine component changes, update both **Part 1 (High-Level User Guide)** and **Part 2 (Technical Appendix)** in `USER_GUIDE.md` so the operator documentation remains 100% synchronized with the live implementation.

