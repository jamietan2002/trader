"""LLM Provider Abstraction, Structured Schema Validation, and Agent Permission Guardrails.

Enforces:
- Separation of AI reasoning from deterministic quantitative calculations.
- Restricted tool permissions per agent role (`market_researcher`, `strategy_architect`,
  `strategy_evaluator`, `performance_analyst`, `risk_manager`).
- Strict schema validation on all agent inputs and outputs.
- Pluggable LLM provider interface (`DeterministicQuantReasoningProvider`, `OpenAIProvider`,
  `GeminiProvider`).
"""

from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Set, Type, TypeVar

from infrastructure.configuration.settings import Settings
from infrastructure.logging.logger import get_logger

logger = get_logger("agents.base")

T = TypeVar("T")


class AgentPermissionError(PermissionError):
    """Raised when an AI agent attempts an action outside its permitted tool scope."""


AGENT_PERMISSIONS: Dict[str, Set[str]] = {
    "market_researcher": {
        "read_market_data",
        "read_indicators",
        "read_earnings_and_catalysts",
        "write_research_report",
    },
    "strategy_architect": {
        "read_research_reports",
        "read_strategy_registry",
        "register_draft_strategy",
    },
    "strategy_evaluator": {
        "read_backtest_results",
        "read_walk_forward_results",
        "evaluate_and_transition_strategy_status",
    },
    "performance_analyst": {
        "read_paper_account",
        "read_trade_ledger",
        "read_strategy_performance",
        "write_experiment_proposal",
    },
    "risk_manager": {
        "read_paper_account",
        "veto_order",
        "trigger_kill_switch",
    },
}

FORBIDDEN_AGENT_TOOLS: Dict[str, Set[str]] = {
    "market_researcher": {"execute_order", "modify_portfolio", "promote_strategy"},
    "strategy_architect": {"execute_order", "modify_portfolio", "promote_strategy"},
    "strategy_evaluator": {"execute_order", "modify_portfolio"},
    "performance_analyst": {"execute_order", "modify_portfolio", "overwrite_active_strategy"},
}


class SchemaValidationError(ValueError):
    """Raised when an agent's structured output fails schema validation."""


def validate_required_fields(
    payload: Dict[str, Any], required_types: Dict[str, Any], schema_name: str = "AgentOutput"
) -> None:
    """Validate that all required keys exist and match expected types (like Pydantic validation)."""
    if not isinstance(payload, dict):
        raise SchemaValidationError(f"{schema_name} must be a JSON object/dict, got {type(payload).__name__}")
    for field_name, expected_type in required_types.items():
        if field_name not in payload or payload[field_name] is None:
            raise SchemaValidationError(f"{schema_name} missing required field '{field_name}'")
        if not isinstance(payload[field_name], expected_type):
            raise SchemaValidationError(
                f"{schema_name}.{field_name} expected {expected_type}, got {type(payload[field_name]).__name__}"
            )


class LLMProvider(ABC):
    """Abstract interface for structured LLM completion calls."""

    provider_name: str = "abstract"

    @abstractmethod
    def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return structured JSON dictionary conforming to the requested schema."""


class DeterministicQuantReasoningProvider(LLMProvider):
    """Deterministic quantitative synthesis provider (works 100% offline with zero hallucination)."""

    provider_name = "deterministic_research"

    def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return fallback_payload


class GeminiLLMProvider(LLMProvider):
    """Google Gemini API structured JSON provider with deterministic fallback."""

    provider_name = "gemini"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.settings.gemini_api_key:
            return fallback_payload
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.llm_model}:generateContent"
            f"?key={self.settings.gemini_api_key}"
        )
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except Exception as exc:
            logger.warning(f"Gemini API call failed ({exc}); using deterministic quantitative synthesis.")
            return fallback_payload


class OpenAILLMProvider(LLMProvider):
    """OpenAI Chat Completions structured JSON provider with deterministic fallback."""

    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.settings.openai_api_key:
            return fallback_payload
        url = "https://api.openai.com/v1/chat/completions"
        body = {
            "model": "gpt-4o",
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return json.loads(data["choices"][0]["message"]["content"])
        except Exception as exc:
            logger.warning(f"OpenAI API call failed ({exc}); using deterministic quantitative synthesis.")
            return fallback_payload


def create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "gemini":
        return GeminiLLMProvider(settings)
    if settings.llm_provider == "openai":
        return OpenAILLMProvider(settings)
    return DeterministicQuantReasoningProvider()


class BaseAgent:
    """Base class for all AI Agents with role permission enforcement."""

    role_name: str = "base"

    def __init__(self, settings: Settings, llm: Optional[LLMProvider] = None) -> None:
        self.settings = settings
        self.llm = llm or create_llm_provider(settings)

    def assert_permission(self, action_name: str) -> None:
        forbidden = FORBIDDEN_AGENT_TOOLS.get(self.role_name, set())
        allowed = AGENT_PERMISSIONS.get(self.role_name, set())
        if action_name in forbidden or action_name not in allowed:
            raise AgentPermissionError(
                f"Agent '{self.role_name}' is strictly prohibited from invoking tool/action '{action_name}'."
            )

