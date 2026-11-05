from __future__ import annotations

import asyncio
from typing import Any

import pytest
from argus.agent_runtime.capabilities.contract import build_default_capability_contract
from argus.agent_runtime.graph.workflow import build_workflow
from argus.agent_runtime.llm_interpreter import (
    AssetAnswerCandidateAudit,
    AssetGroundingAudit,
    DcaContractAudit,
    FocusedDateWindowExtraction,
    FocusedStrategyExtraction,
    LLMAmbiguousField,
    LLMInterpretationResponse,
    LLMStrategyDraft,
    OpenRouterStructuredInterpreter,
    StatedRunFieldFidelityAudit,
    SupportedStrategyCapabilityConflictAudit,
)
from argus.agent_runtime.runtime import run_agent_turn
from argus.agent_runtime.stages.interpret import InterpretationRequest
from argus.agent_runtime.state.models import (
    ConversationMessage,
    StrategySummary,
    TaskSnapshot,
    UserState,
)
from argus.domain.market_data import clear_asset_cache
from argus.domain.market_data.new_york_clock import new_york_today
from argus.domain.research.contracts import ResearchUsage
from argus.domain.research.perplexity_agent import StructuredAgentResult
from argus.llm import openrouter
from argus.llm.openrouter import (
    log_openrouter_failure,
    openrouter_profile_for_task,
    openrouter_structured_model_candidates,
)
from argus.llm.openrouter_key_policy import (
    openrouter_traffic_class,
    resolve_openrouter_api_key,
)
from fastapi import FastAPI
from langgraph.checkpoint.memory import MemorySaver

from tests.result_readout_fixtures import readout_draft


@pytest.fixture(autouse=True)
def _provider_fixture_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "synthetic_unit_fixture")
    clear_asset_cache()
    yield
    clear_asset_cache()


def test_local_openrouter_uses_dev_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dev-key")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "hosted-registered")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "hosted-guest")

    assert resolve_openrouter_api_key("registered") == "dev-key"
    assert resolve_openrouter_api_key("guest") == "dev-key"


def test_hosted_registered_uses_registered_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dev-only")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "registered-key")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "guest-key")

    assert resolve_openrouter_api_key("registered") == "registered-key"


def test_hosted_guest_uses_guest_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "preview")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dev-only")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "registered-key")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "guest-key")

    assert resolve_openrouter_api_key("guest") == "guest-key"


def test_hosted_registered_never_falls_back_to_dev_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dev-only")
    monkeypatch.delenv("CUADRAO_PROD_OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="CUADRAO_PROD_OPENROUTER_API_KEY"):
        resolve_openrouter_api_key("registered")


def test_hosted_guest_never_falls_back_to_dev_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dev-only")
    monkeypatch.delenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", raising=False)

    with pytest.raises(
        RuntimeError,
        match="CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY",
    ):
        resolve_openrouter_api_key("guest")


def test_hosted_configuration_rejects_shared_traffic_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.llm.openrouter_key_policy import (
        validate_hosted_openrouter_configuration,
    )

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "shared-secret")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "shared-secret")

    with pytest.raises(RuntimeError) as exc_info:
        validate_hosted_openrouter_configuration()

    message = str(exc_info.value)
    assert "CUADRAO_PROD_OPENROUTER_API_KEY" in message
    assert "CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY" in message
    assert "shared-secret" not in message


def test_openrouter_traffic_class_nested_scope_resets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "registered-key")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "guest-key")

    with openrouter_traffic_class("guest"):
        assert resolve_openrouter_api_key() == "guest-key"
        with openrouter_traffic_class("registered"):
            assert resolve_openrouter_api_key() == "registered-key"
        assert resolve_openrouter_api_key() == "guest-key"

    with pytest.raises(RuntimeError, match="traffic class"):
        resolve_openrouter_api_key()


def test_openrouter_factory_uses_hosted_traffic_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeChatOpenRouter.calls.clear()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dev-only")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "registered-key")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "guest-key")
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "test/model")
    monkeypatch.setattr(openrouter, "ChatOpenRouter", FakeChatOpenRouter)

    with openrouter_traffic_class("guest"):
        model = openrouter.build_openrouter_model("interpretation")

    assert model is not None
    assert FakeChatOpenRouter.calls[-1]["openrouter_api_key"] == "guest-key"


def test_provider_asset_preflight_uses_hosted_traffic_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.interpreter.asset_resolution_context import (
        _provider_asset_context_preflight_enabled,
    )

    def invoke_schema() -> None:
        return None

    invoke_schema.__module__ = "argus.llm.openrouter"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "registered-key")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "guest-key")

    with openrouter_traffic_class("guest"):
        assert _provider_asset_context_preflight_enabled(
            "test/model",
            invoke_schema=invoke_schema,
        )


@pytest.mark.asyncio
async def test_api_lifespan_validates_openrouter_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import app_setup
    from argus.api import state as api_state

    events: list[str] = []
    monkeypatch.setattr(
        app_setup,
        "validate_hosted_openrouter_configuration",
        lambda: events.append("validate"),
        raising=False,
    )
    monkeypatch.setattr(api_state, "CHECKPOINTER_MODE", "memory")
    monkeypatch.setattr(api_state, "PERSISTENCE_MODE", "memory")
    monkeypatch.setattr(
        api_state,
        "build_agent_runtime_checkpointer",
        lambda: events.append("persistence") or object(),
    )
    app = FastAPI()

    async with app_setup.lifespan(app):
        pass

    assert events == ["validate", "persistence"]


def _structured_model_candidates(*_: Any, **__: Any) -> list[str]:
    return ["primary/model"]


def _structured_model_candidates_with_fallback(*_: Any, **__: Any) -> list[str]:
    return ["primary/model", "fallback/model"]


def _neutral_repair_schema_response(schema_model: object) -> object | None:
    schema_name = getattr(schema_model, "__name__", "")
    if schema_name == "DcaContractAudit":
        return DcaContractAudit(
            is_recurring_buy_request=False,
            confidence=0.95,
        )
    if schema_name == "FocusedDateWindowExtraction":
        return FocusedDateWindowExtraction(
            has_date_window=False,
            confidence=0.35,
            evidence="",
        )
    if schema_name == "StatedRunFieldFidelityAudit":
        return StatedRunFieldFidelityAudit()
    if schema_name == "SupportedStrategyCapabilityConflictAudit":
        return SupportedStrategyCapabilityConflictAudit(
            selected_strategy_type=None,
            drop_unsupported_strategy_logic=False,
            keep_unsupported_strategy_logic=True,
            confidence=0.95,
        )
    return None


class FakeChatOpenRouter:
    calls: list[dict[str, Any]] = []
    invoked_messages: list[list[dict[str, str]]] = []
    structured_invoked_messages: list[list[dict[str, str]]] = []
    structured_response: object | None = None
    invoke_content: str | None = None

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls.append(kwargs)

    def with_structured_output(self, schema: object) -> "FakeStructuredModel":
        return FakeStructuredModel(schema)

    def invoke(self, messages: list[dict[str, str]]) -> object:
        self.invoked_messages.append(messages)
        return type(
            "FakeMessage",
            (),
            {
                "content": self.invoke_content
                or (
                    "This breakdown explains the stored metrics, benchmark, assumptions, "
                    "and caveats without inventing data. It is not a prediction."
                )
            },
        )()


class FakeStructuredModel:
    def __init__(self, schema: object | None = None) -> None:
        self.schema = schema

    def invoke(self, messages: list[dict[str, str]]) -> object:
        FakeChatOpenRouter.structured_invoked_messages.append(messages)
        if FakeChatOpenRouter.structured_response is not None:
            return FakeChatOpenRouter.structured_response
        return LLMInterpretationResponse(
            intent="conversation_followup",
            task_relation="new_task",
            user_goal_summary="User asked what Argus can do.",
            assistant_response="Argus can explain ideas and help test them.",
        )

    async def ainvoke(self, _messages: list[object]) -> object:
        return self.invoke([])


class FakeBreakdownAgentClient:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []
        self.usage = ResearchUsage(model="openai/gpt-5.6-luna")

    def run_structured(self, prompt, spec, **kwargs) -> StructuredAgentResult:
        self.calls.append({"prompt": prompt, "spec": spec, **kwargs})
        draft = (
            self.response
            if self.response is not None
            else readout_draft(
                "The stored result is grounded in the completed backtest and its historical-simulation caveat."
            )
        )
        return StructuredAgentResult(
            draft=draft,
            sources=(),
            usage=self.usage,
            tool_results=(),
            provider_response_id=None,
        )


class SlowStructuredInterpreterModel:
    def with_structured_output(self, _schema: object) -> "SlowStructuredInterpreterModel":
        return self

    async def ainvoke(self, _messages: list[object]) -> object:
        await asyncio.sleep(0.2)
        return LLMInterpretationResponse(
            intent="conversation_followup",
            task_relation="new_task",
            user_goal_summary="Slow response",
            assistant_response="This should time out.",
        )


def test_openrouter_factory_applies_task_token_budget(
    monkeypatch,
) -> None:
    FakeChatOpenRouter.calls.clear()
    FakeChatOpenRouter.structured_response = None
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "test/model")
    monkeypatch.setattr(openrouter, "ChatOpenRouter", FakeChatOpenRouter)

    model = openrouter.build_openrouter_model("interpretation")

    assert model is not None
    assert FakeChatOpenRouter.calls == [
        {
            "model_name": "test/model",
            "temperature": 0,
            "max_tokens": 3200,
            "timeout": 20,
            "max_retries": 1,
            "openrouter_api_key": "test-key",
            "openrouter_provider": openrouter.openrouter_provider_policy(),
        }
    ]


def test_interpretation_profile_has_bounded_reasoning_for_semantic_repair() -> None:
    profile = openrouter_profile_for_task("interpretation")

    assert profile.temperature == 0
    assert profile.reasoning_effort == "medium"


def test_structured_reasoning_effort_can_be_overridden_for_dev_eval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_STRUCTURED_REASONING_EFFORT", "low")

    profile = openrouter_profile_for_task("interpretation")

    assert profile.reasoning_effort == "low"


def test_capability_reasoning_effort_can_be_overridden_for_dev_eval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_CAPABILITY_REASONING_EFFORT", "none")

    profile = openrouter_profile_for_task("capability_conflict")

    assert profile.reasoning_effort == "none"


def test_invalid_reasoning_effort_override_preserves_profile_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_STRUCTURED_REASONING_EFFORT", "cheap")

    profile = openrouter_profile_for_task("interpretation")

    assert profile.reasoning_effort == "medium"


@pytest.mark.parametrize(
    ("task", "env_name", "effort"),
    [
        ("interpretation", "CUADRAO_STRUCTURED_REASONING_EFFORT", "low"),
        ("capability_conflict", "CUADRAO_CAPABILITY_REASONING_EFFORT", "none"),
    ],
)
def test_reasoning_effort_override_is_sent_in_json_schema_payload(
    monkeypatch: pytest.MonkeyPatch,
    task: openrouter.OpenRouterTask,
    env_name: str,
    effort: openrouter.OpenRouterReasoningEffort,
) -> None:
    from argus.agent_runtime.llm_interpreter_types import LLMDateRangeIntent

    monkeypatch.setenv(env_name, effort)

    payload = openrouter._json_schema_payload(
        model="qwen/qwen3.5-9b",
        messages=[{"role": "user", "content": "hello"}],
        schema_model=LLMDateRangeIntent,
        schema_name="LLMDateRangeIntent",
        profile=openrouter_profile_for_task(task),
    )

    assert payload["reasoning"] == {"effort": effort}


@pytest.mark.parametrize("task", openrouter.OPENROUTER_TASK_MODEL_TIERS)
@pytest.mark.parametrize("model", ["openai/gpt-5.6-luna", "anthropic/test-model"])
def test_json_schema_payload_omits_temperature_for_readout_and_openai_documents(
    task: openrouter.OpenRouterTask,
    model: str,
) -> None:
    from argus.agent_runtime.llm_interpreter_types import LLMDateRangeIntent

    profile = openrouter_profile_for_task(task)
    payload = openrouter._json_schema_payload(
        model=model,
        messages=[{"role": "user", "content": "hello"}],
        schema_model=LLMDateRangeIntent,
        schema_name="LLMDateRangeIntent",
        profile=profile,
    )

    if openrouter.openrouter_model_tier_for_task(task) == "readout" or (
        task == "document_extraction" and model.startswith("openai/")
    ):
        assert "temperature" not in payload
    else:
        assert payload["temperature"] == profile.temperature
    if not model.startswith("anthropic/"):
        assert payload["provider"]["require_parameters"] is True


def test_interpretation_repair_uses_structured_tier_without_reasoning() -> None:
    profile = openrouter_profile_for_task("interpretation_repair")

    assert (
        openrouter.openrouter_model_tier_for_task("interpretation_repair") == "structured"
    )
    assert profile.temperature == 0
    assert profile.reasoning_effort == "none"
    assert profile.timeout_seconds == 20


def test_asset_mention_preflight_uses_structured_tier_without_reasoning() -> None:
    profile = openrouter_profile_for_task("asset_mention_preflight")

    assert (
        openrouter.openrouter_model_tier_for_task("asset_mention_preflight")
        == "structured"
    )
    assert profile.temperature == 0
    assert profile.max_tokens == 2200
    assert profile.reasoning_effort == "none"
    assert profile.timeout_seconds == 20


def test_result_summary_timeout_budget_is_safe_for_render_workflows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeChatOpenRouter.calls.clear()
    FakeChatOpenRouter.structured_response = None
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_READOUT_MODEL", "openai/gpt-5.6-luna")
    monkeypatch.setattr(openrouter, "ChatOpenRouter", FakeChatOpenRouter)

    model = openrouter.build_openrouter_model("result_summary")

    assert model is not None
    assert FakeChatOpenRouter.calls[-1]["timeout"] == 30
    assert openrouter.openrouter_task_timeout_seconds("result_summary") == 30


def test_openrouter_task_timeout_budget_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeChatOpenRouter.calls.clear()
    FakeChatOpenRouter.structured_response = None
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_READOUT_MODEL", "openai/gpt-5.6-luna")
    monkeypatch.setenv("CUADRAO_OPENROUTER_RESULT_SUMMARY_TIMEOUT_SECONDS", "27")
    monkeypatch.setattr(openrouter, "ChatOpenRouter", FakeChatOpenRouter)

    model = openrouter.build_openrouter_model("result_summary")

    assert model is not None
    assert FakeChatOpenRouter.calls[-1]["timeout"] == 27
    assert openrouter.openrouter_task_timeout_seconds("result_summary") == 27


def test_openrouter_model_routing_uses_task_specific_tiers(monkeypatch) -> None:
    monkeypatch.setenv("CUADRAO_UTILITY_MODEL", "utility/primary")
    monkeypatch.setenv("CUADRAO_UTILITY_FALLBACK_MODEL", "utility/fallback")
    monkeypatch.setenv("CUADRAO_CHAT_MODEL", "chat/primary")
    monkeypatch.setenv("CUADRAO_CHAT_FALLBACK_MODEL", "chat/fallback")
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "structured/primary")
    monkeypatch.setenv("CUADRAO_STRUCTURED_FALLBACK_MODEL", "structured/fallback")
    monkeypatch.setenv("CUADRAO_CONTEXT_MODEL", "context/primary")
    monkeypatch.setenv("CUADRAO_CONTEXT_FALLBACK_MODEL", "context/fallback")
    monkeypatch.setenv("CUADRAO_READOUT_MODEL", "openai/gpt-5.6-luna")
    monkeypatch.setenv("CUADRAO_READOUT_FALLBACK_MODEL", "openai/gpt-5.6-luna")

    assert openrouter.resolve_openrouter_model(task="name_suggestion") == (
        "utility/primary"
    )
    assert (
        openrouter.resolve_openrouter_model(
            task="name_suggestion",
            fallback=True,
        )
        == "utility/fallback"
    )
    assert openrouter.resolve_openrouter_model(task="clarification") == "chat/primary"
    assert (
        openrouter.resolve_openrouter_model(
            task="clarification",
            fallback=True,
        )
        == "chat/fallback"
    )
    assert openrouter.resolve_openrouter_model(task="interpretation") == (
        "structured/primary"
    )
    assert (
        openrouter.resolve_openrouter_model(
            task="interpretation",
            fallback=True,
        )
        == "structured/fallback"
    )
    assert openrouter.resolve_openrouter_model(task="capability_conflict") == (
        "context/primary"
    )
    assert (
        openrouter.resolve_openrouter_model(
            task="capability_conflict",
            fallback=True,
        )
        == "context/fallback"
    )
    assert openrouter.openrouter_model_tier_for_task("result_summary") == "readout"
    assert openrouter.resolve_openrouter_model(task="result_summary") == (
        "openai/gpt-5.6-luna"
    )
    assert openrouter.resolve_openrouter_model(task="result_summary", fallback=True) == (
        "openai/gpt-5.6-luna"
    )
    assert openrouter_structured_model_candidates(task="result_summary") == [
        "openai/gpt-5.6-luna"
    ]


def test_openrouter_structured_candidates_follow_task_tier(monkeypatch) -> None:
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "structured/primary")
    monkeypatch.setenv("CUADRAO_STRUCTURED_FALLBACK_MODEL", "structured/fallback")
    monkeypatch.setenv("CUADRAO_CONTEXT_MODEL", "context/primary")
    monkeypatch.setenv("CUADRAO_CONTEXT_FALLBACK_MODEL", "context/fallback")

    assert openrouter_structured_model_candidates(task="interpretation") == [
        "structured/primary",
        "structured/fallback",
    ]
    assert openrouter_structured_model_candidates(task="capability_conflict") == [
        "context/primary",
        "context/fallback",
    ]


def test_openrouter_factory_uses_context_model_for_capability_conflict(
    monkeypatch,
) -> None:
    FakeChatOpenRouter.calls.clear()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_CONTEXT_MODEL", "context/primary")
    monkeypatch.setattr(openrouter, "ChatOpenRouter", FakeChatOpenRouter)

    model = openrouter.build_openrouter_model("capability_conflict")

    assert model is not None
    assert FakeChatOpenRouter.calls[0]["model_name"] == "context/primary"


def test_openrouter_factory_returns_none_without_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    assert openrouter.build_openrouter_model("capability_conflict") is None


def test_structured_model_uses_argus_tier_models_unless_explicitly_overridden(
    monkeypatch,
) -> None:
    monkeypatch.delenv("CUADRAO_STRUCTURED_MODEL", raising=False)
    monkeypatch.delenv("CUADRAO_STRUCTURED_FALLBACK_MODEL", raising=False)

    assert openrouter_structured_model_candidates() == []

    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "argus/structured")

    assert openrouter_structured_model_candidates() == ["argus/structured"]


def test_structured_interpreter_uses_bounded_interpretation_profile(
    monkeypatch,
) -> None:
    FakeChatOpenRouter.calls.clear()
    FakeChatOpenRouter.structured_response = None
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter, "ChatOpenRouter", FakeChatOpenRouter)

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract(),
        model_name="custom/model",
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="what can you do?",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert interpreter.last_status == "used"
    assert FakeChatOpenRouter.calls[0] == {
        "model_name": "custom/model",
        "temperature": 0,
        "max_tokens": 3200,
        "timeout": 20,
        "max_retries": 1,
        "openrouter_api_key": "test-key",
            "openrouter_provider": openrouter.openrouter_provider_policy(),
    }


def test_result_breakdown_schema_requires_complete_text_language_and_figures() -> None:
    from argus.domain.result_readout_sources import ResultBreakdownDraft
    from pydantic import ValidationError

    schema = ResultBreakdownDraft.model_json_schema()

    assert set(schema["required"]) == {
        "language",
        "text",
        "figures",
    }
    assert set(schema["properties"]) == {
        "language",
        "text",
        "figures",
    }
    with pytest.raises(ValidationError):
        ResultBreakdownDraft.model_validate({})
    with pytest.raises(ValidationError):
        ResultBreakdownDraft.model_validate({"text": None})


def test_default_interpreter_uses_direct_schema_client(monkeypatch) -> None:
    from argus.agent_runtime import llm_interpreter

    calls: list[dict[str, Any]] = []

    async def fake_direct_schema(**kwargs: Any) -> LLMInterpretationResponse:
        calls.append(kwargs)
        return LLMInterpretationResponse(
            intent="backtest_execution",
            task_relation="new_task",
            user_goal_summary="Backtest TSLA with RSI thresholds.",
            semantic_turn_act="new_idea",
            candidate_strategy_draft=LLMStrategyDraft(
                raw_user_phrasing=(
                    "Backtest TSLA using RSI entry at 20 or lower and exit at 60 "
                    "or higher over the last 3 months."
                ),
                strategy_type="rsi_mean_reversion",
                strategy_thesis="Use RSI thresholds on TSLA.",
                asset_universe=["TSLA"],
                date_range="last 3 months",
                indicator="rsi",
                entry_threshold=20,
                exit_threshold=60,
            ),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message=(
                "Backtest TSLA using RSI entry at 20 or lower and exit at 60 "
                "or higher over the last 3 months."
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert calls[0]["task"] == "interpretation"
    assert calls[0]["schema_model"] is LLMInterpretationResponse
    assert result.candidate_strategy_draft.asset_universe == ["TSLA"]
    assert result.candidate_strategy_draft.extra_parameters["indicator"] == "rsi"
    assert (
        result.candidate_strategy_draft.extra_parameters["indicator_parameters"][
            "entry_threshold"
        ]
        == 20
    )
    assert calls[0]["model_name"] == "primary/model"


@pytest.mark.parametrize(
    ("answer", "candidate_symbols", "expected_symbol", "primary_turn_act"),
    [
        ("google", ["GOOGL", "GOOG"], "GOOGL", "unsupported_request"),
        ("microsoft", ["MSFT"], "MSFT", "answer_pending_need"),
    ],
)
def test_requested_asset_answer_uses_semantic_candidate_audit_before_provider_validation(
    monkeypatch,
    answer: str,
    candidate_symbols: list[str],
    expected_symbol: str,
    primary_turn_act: str,
) -> None:
    from argus.agent_runtime import llm_interpreter

    calls: list[str] = []

    async def fake_direct_schema(**kwargs: Any):
        schema_model = kwargs["schema_model"]
        calls.append(schema_model.__name__)
        if schema_model is LLMInterpretationResponse:
            return LLMInterpretationResponse(
                intent=(
                    "unsupported_or_out_of_scope"
                    if primary_turn_act == "unsupported_request"
                    else "backtest_execution"
                ),
                task_relation="continue",
                user_goal_summary="User supplied a replacement asset.",
                semantic_turn_act=primary_turn_act,
                candidate_strategy_draft=LLMStrategyDraft(
                    asset_universe=["TSLA"],
                    asset_class="equity",
                ),
            )
        if schema_model is AssetAnswerCandidateAudit:
            return AssetAnswerCandidateAudit(
                candidate_symbols=candidate_symbols,
                confidence=0.86,
            )
        raise AssertionError(f"unexpected schema model {schema_model}")

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    pending = StrategySummary(
        strategy_type="indicator_threshold",
        strategy_thesis="RSI threshold on TSLA.",
        asset_universe=["TSLA"],
        asset_class="equity",
        date_range={"start": "2025-11-30", "end": "2026-05-31"},
        capital_amount=1000,
        entry_logic="Buy when RSI(14) drops to 30 or below",
        exit_logic="Sell when RSI(14) rises to 55 or above",
    )
    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )

    result = interpreter(
        InterpretationRequest(
            current_user_message=answer,
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(pending_strategy_summary=pending),
            selected_thread_metadata={
                "last_stage_outcome": "await_user_reply",
                "requested_field": "asset_universe",
            },
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert "AssetAnswerCandidateAudit" in calls
    assert result.candidate_strategy_draft.asset_universe == [expected_symbol]
    assert result.candidate_strategy_draft.asset_class == "equity"
    assert "requested_asset_answer_candidate_audit" in result.reason_codes


def test_default_interpreter_retries_configured_structured_model_when_first_is_incomplete(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    calls: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        model_name = str(kwargs.get("model_name", "<task-default>"))
        schema_model = kwargs["schema_model"]
        calls.append(model_name)
        if schema_model is not LLMInterpretationResponse:
            neutral_response = _neutral_repair_schema_response(schema_model)
            if neutral_response is not None:
                return neutral_response
        if model_name == "primary/model":
            return LLMInterpretationResponse(
                intent="backtest_execution",
                task_relation="new_task",
                user_goal_summary="Backtest TSLA with RSI thresholds.",
                semantic_turn_act="new_idea",
            )
        return LLMInterpretationResponse(
            intent="backtest_execution",
            task_relation="new_task",
            user_goal_summary="Backtest TSLA with RSI thresholds.",
            semantic_turn_act="new_idea",
            candidate_strategy_draft=LLMStrategyDraft(
                raw_user_phrasing=(
                    "Backtest TSLA using RSI entry at 20 or lower and exit at 60 "
                    "or higher over the last 3 months."
                ),
                strategy_type="rsi_mean_reversion",
                strategy_thesis="Use RSI thresholds on TSLA.",
                asset_universe=["TSLA"],
                date_range="last 3 months",
                indicator="rsi",
                entry_threshold=20,
                exit_threshold=60,
            ),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates_with_fallback,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message=(
                "Backtest TSLA using RSI entry at 20 or lower and exit at 60 "
                "or higher over the last 3 months."
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert calls[:3] == ["primary/model", "primary/model", "fallback/model"]
    assert "fallback/model" in calls
    assert calls.count("<task-default>") >= 1
    assert interpreter.last_status == "fallback_used"
    assert result.candidate_strategy_draft.asset_universe == ["TSLA"]
    assert result.candidate_strategy_draft.extra_parameters["indicator"] == "rsi"


def test_default_interpreter_repairs_underfilled_indicator_threshold_parameters(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    seen_schema_names: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        seen_schema_names.append(kwargs["schema_name"])
        schema_model = kwargs["schema_model"]
        if schema_model is LLMInterpretationResponse:
            return LLMInterpretationResponse(
                intent="backtest_execution",
                task_relation="new_task",
                user_goal_summary=(
                    "User wants to test TSLA with RSI below 20 and sell above 60."
                ),
                semantic_turn_act="new_idea",
                candidate_strategy_draft=LLMStrategyDraft(
                    raw_user_phrasing=(
                        "test tsla rsi below 20 and sell above 60 over the last 5 years"
                    ),
                    strategy_type="indicator_threshold",
                    strategy_thesis=(
                        "Buy TSLA when RSI is below 20 and sell when RSI rises above 60."
                    ),
                    asset_universe=["TSLA"],
                    date_range="last 5 years",
                    indicator="rsi",
                ),
            )
        if schema_model is AssetGroundingAudit:
            return AssetGroundingAudit(
                grounded_symbols=["TSLA"],
                confidence=0.9,
            )
        assert schema_model is FocusedStrategyExtraction
        return FocusedStrategyExtraction(
            is_testable_strategy=True,
            user_goal_summary="Backtest TSLA with RSI 20/60 thresholds.",
            strategy_type="indicator_threshold",
            indicator="rsi",
            entry_threshold=20,
            exit_threshold=60,
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message=(
                "test tsla rsi below 20 and sell above 60 over the last 5 years"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert seen_schema_names[:3] == [
        "LLMInterpretationResponse",
        "AssetGroundingAudit",
        "FocusedStrategyExtraction",
    ]
    parameters = result.candidate_strategy_draft.extra_parameters["indicator_parameters"]
    assert parameters["indicator"] == "rsi"
    assert parameters["entry_threshold"] == 20
    assert parameters["exit_threshold"] == 60
    assert result.candidate_strategy_draft.asset_universe == ["TSLA"]
    assert result.candidate_strategy_draft.date_range == "last 5 years"


def test_default_interpreter_repairs_underfilled_new_signal_idea(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    seen_schema_names: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        seen_schema_names.append(kwargs["schema_name"])
        schema_model = kwargs["schema_model"]
        if schema_model is LLMInterpretationResponse:
            return LLMInterpretationResponse(
                intent="backtest_execution",
                task_relation="new_task",
                user_goal_summary=(
                    "Backtest Nvidia using a 50/200-day moving average crossover."
                ),
                semantic_turn_act="new_idea",
            )
        assert schema_model is FocusedStrategyExtraction
        return FocusedStrategyExtraction(
            is_testable_strategy=True,
            user_goal_summary=(
                "Backtest NVDA using a 50-day SMA crossing above a 200-day SMA."
            ),
            strategy_type="moving_average_crossover",
            asset_universe=["NVDA"],
            date_range="past 2 years",
            entry_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bullish",
            },
            exit_logic="Use the opposite crossover as the exit.",
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message=(
                "Test Nvidia when the 50-day moving average crosses above the "
                "200-day moving average over the past two years."
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert seen_schema_names[:2] == [
        "LLMInterpretationResponse",
        "FocusedStrategyExtraction",
    ]
    assert result.candidate_strategy_draft.asset_universe == ["NVDA"]
    assert result.candidate_strategy_draft.date_range == "past 2 years"
    assert result.candidate_strategy_draft.entry_rule == {
        "type": "moving_average_crossover",
        "fast_indicator": "sma",
        "fast_period": 50,
        "slow_indicator": "sma",
        "slow_period": 200,
        "direction": "bullish",
    }


def test_default_interpreter_repairs_partial_signal_idea_without_rule_payload(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    seen_schema_names: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        seen_schema_names.append(kwargs["schema_name"])
        schema_model = kwargs["schema_model"]
        if schema_model is LLMInterpretationResponse:
            return LLMInterpretationResponse(
                intent="backtest_execution",
                task_relation="new_task",
                user_goal_summary="Backtest NVDA with a moving average crossover.",
                semantic_turn_act="new_idea",
                candidate_strategy_draft=LLMStrategyDraft(
                    strategy_type="moving_average_crossover",
                    asset_universe=["NVDA"],
                    date_range="past two years",
                ),
            )
        assert schema_model is FocusedStrategyExtraction
        return FocusedStrategyExtraction(
            is_testable_strategy=True,
            user_goal_summary="Backtest NVDA with a 50/200 SMA bullish crossover.",
            strategy_type="signal_strategy",
            asset_universe=["NVDA"],
            date_range="past 2 years",
            entry_rule={
                "type": "moving_average_crossover",
                "fast_indicator": "sma",
                "fast_period": 50,
                "slow_indicator": "sma",
                "slow_period": 200,
                "direction": "bullish",
            },
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message=(
                "Test Nvidia when the 50-day moving average crosses above the "
                "200-day moving average over the past two years."
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert seen_schema_names[:2] == [
        "LLMInterpretationResponse",
        "FocusedStrategyExtraction",
    ]
    assert result.candidate_strategy_draft.entry_rule == {
        "type": "moving_average_crossover",
        "fast_indicator": "sma",
        "fast_period": 50,
        "slow_indicator": "sma",
        "slow_period": 200,
        "direction": "bullish",
    }


def test_default_interpreter_repairs_capability_misroute_for_buy_curiosity(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    seen_schema_names: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        seen_schema_names.append(kwargs["schema_name"])
        schema_model = kwargs["schema_model"]
        if schema_model is LLMInterpretationResponse:
            return LLMInterpretationResponse(
                intent="unsupported_or_out_of_scope",
                task_relation="new_task",
                user_goal_summary="User asks to trade based on Reddit sentiment.",
                candidate_strategy_draft=LLMStrategyDraft(
                    raw_user_phrasing="trade based on Reddit sentiment",
                    strategy_thesis="Trade based on Reddit sentiment.",
                ),
                semantic_turn_act="unsupported_request",
                capability_question_focus="limits",
            )
        neutral_response = _neutral_repair_schema_response(schema_model)
        if neutral_response is not None:
            return neutral_response
        assert schema_model is FocusedStrategyExtraction
        return FocusedStrategyExtraction(
            is_testable_strategy=True,
            user_goal_summary="Test a buy-and-hold Tesla idea.",
            strategy_type="buy_and_hold",
            asset_universe=["TSLA"],
            date_range="past year",
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="what if I bought Tesla when it looked cheap?",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert seen_schema_names[0] == "LLMInterpretationResponse"
    assert "DcaContractAudit" in seen_schema_names
    assert "FocusedStrategyExtraction" in seen_schema_names
    assert result.semantic_turn_act == "new_idea"
    assert result.candidate_strategy_draft.strategy_type == "buy_and_hold"
    assert result.candidate_strategy_draft.asset_universe == ["TSLA"]
    assert result.candidate_strategy_draft.date_range == "past year"


def _sentiment_misroute_schema(
    seen_schema_names: list[str], *, asset_universe: list[str]
):
    async def fake_direct_schema(**kwargs: Any) -> object:
        seen_schema_names.append(kwargs["schema_name"])
        schema_model = kwargs["schema_model"]
        if schema_model is LLMInterpretationResponse:
            return LLMInterpretationResponse(
                intent="conversation_followup",
                task_relation="new_task",
                user_goal_summary="User asks about executable indicators.",
                assistant_response="Executable indicators right now are RSI and SMA.",
                semantic_turn_act="educational_question",
                capability_question_focus="supported_indicators",
            )
        if schema_model is FocusedStrategyExtraction:
            return FocusedStrategyExtraction(
                is_testable_strategy=True,
                user_goal_summary="Trade based on Reddit sentiment.",
                strategy_type="reddit_sentiment",
                strategy_thesis="Use Reddit sentiment as the trade signal.",
                asset_universe=asset_universe,
                entry_logic="Reddit sentiment turns positive",
                assistant_response="Reddit sentiment is not executable yet.",
            )
        neutral_response = _neutral_repair_schema_response(schema_model)
        assert neutral_response is not None, schema_model
        return neutral_response

    return fake_direct_schema


def _interpret_sentiment_misroute(
    monkeypatch, *, message: str, asset_universe: list[str]
):
    from argus.agent_runtime import llm_interpreter

    seen_schema_names: list[str] = []
    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        _sentiment_misroute_schema(seen_schema_names, asset_universe=asset_universe),
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )
    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message=message,
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )
    assert result is not None
    return result, seen_schema_names


def test_default_interpreter_keeps_primary_read_on_factless_sentiment_misroute(
    monkeypatch,
) -> None:
    # No asset and no number in the message: the focused strategy repair has
    # nothing to work with, so the primary read's capability answer stands.
    result, seen_schema_names = _interpret_sentiment_misroute(
        monkeypatch, message="trade based on Reddit sentiment", asset_universe=[]
    )

    assert seen_schema_names == ["LLMInterpretationResponse"]
    assert result.semantic_turn_act == "educational_question"
    assert result.capability_question_focus == "supported_indicators"
    assert result.unsupported_constraints == []


def test_default_interpreter_repairs_social_sentiment_trade_misroute(
    monkeypatch,
) -> None:
    # A named asset is a current-turn fact: the same misroute still repairs
    # to a typed refusal that keeps the idea.
    result, seen_schema_names = _interpret_sentiment_misroute(
        monkeypatch,
        message="trade Tesla based on Reddit sentiment",
        asset_universe=["TSLA"],
    )

    assert seen_schema_names[:2] == [
        "LLMInterpretationResponse",
        "FocusedStrategyExtraction",
    ]
    assert result.semantic_turn_act == "unsupported_request"
    assert result.unsupported_constraints[0].category == "unsupported_strategy_logic"
    assert "Reddit sentiment" in result.unsupported_constraints[0].raw_value


def test_default_interpreter_repairs_empty_unsupported_request_into_contract_recovery(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    seen_schema_names: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        seen_schema_names.append(kwargs["schema_name"])
        schema_model = kwargs["schema_model"]
        if schema_model is LLMInterpretationResponse:
            return LLMInterpretationResponse(
                intent="unsupported_or_out_of_scope",
                task_relation="new_task",
                requires_clarification=True,
                user_goal_summary="Trade based on Reddit sentiment.",
                assistant_response=(
                    "Reddit sentiment is not available as a trading rule."
                ),
                candidate_strategy_draft=LLMStrategyDraft(
                    raw_user_phrasing="trade based on Reddit sentiment",
                    strategy_thesis="Trade based on Reddit sentiment.",
                ),
                semantic_turn_act="unsupported_request",
            )
        assert schema_model is FocusedStrategyExtraction
        return FocusedStrategyExtraction(
            is_testable_strategy=True,
            user_goal_summary="Trade based on Reddit sentiment.",
            strategy_type="reddit_sentiment",
            strategy_thesis="Use Reddit sentiment as the trade signal.",
            entry_logic="Reddit sentiment turns positive",
            assistant_response="Reddit sentiment is not executable yet.",
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="trade based on Reddit sentiment",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert seen_schema_names == [
        "LLMInterpretationResponse",
        "FocusedStrategyExtraction",
    ]
    assert result.assistant_response is None
    assert result.semantic_turn_act == "unsupported_request"
    assert result.unsupported_constraints
    assert result.unsupported_constraints[0].category == "unsupported_strategy_logic"
    labels = [
        option.label
        for option in result.unsupported_constraints[0].simplification_options
    ]
    assert labels == [
        "Use a supported RSI threshold rule",
        "Compare with buy and hold",
        "Use a supported moving-average crossover",
    ]


def test_default_interpreter_does_not_repair_without_a_typed_test_read(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    seen_schema_names: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        seen_schema_names.append(kwargs["schema_name"])
        schema_model = kwargs["schema_model"]
        if schema_model is LLMInterpretationResponse:
            raise ValueError("general schema failed")
        raise AssertionError("Unread turns cannot enter strategy repair")

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message=(
                "buy when the 50 crosses the 200 for Tesla from January 2022 "
                "to today with 10k"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is None
    assert seen_schema_names == ["LLMInterpretationResponse"]


def test_default_interpreter_audits_stated_fields_after_focused_repair_defaults(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    seen_schema_names: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        seen_schema_names.append(kwargs["schema_name"])
        schema_model = kwargs["schema_model"]
        if schema_model is LLMInterpretationResponse:
            return LLMInterpretationResponse(
                intent="strategy_drafting",
                task_relation="new_task",
                requires_clarification=True,
                semantic_turn_act="new_idea",
                user_goal_summary="Test Tesla crossover",
                candidate_strategy_draft=LLMStrategyDraft(
                    raw_user_phrasing="buy when the 50 crosses the 200 for Tesla from January 2022 to today with 10k",
                    strategy_thesis="Test Tesla crossover",
                    asset_universe=["TSLA"],
                ),
            )
        if schema_model is FocusedStrategyExtraction:
            return FocusedStrategyExtraction(
                is_testable_strategy=True,
                user_goal_summary="Backtest a TSLA 50/200 crossover.",
                strategy_type="signal_strategy",
                strategy_thesis=(
                    "Backtest TSLA when the 50 SMA crosses the 200 SMA from "
                    "January 2022 to today with 10k."
                ),
                asset_universe=["TSLA"],
                date_range="past year",
                entry_rule={
                    "type": "moving_average_crossover",
                    "fast_indicator": "sma",
                    "fast_period": 50,
                    "slow_indicator": "sma",
                    "slow_period": 200,
                    "direction": "bullish",
                },
            )
        if schema_model is StatedRunFieldFidelityAudit:
            return StatedRunFieldFidelityAudit(
                date_range={"start": "2022-01-01", "end": "today"},
                capital_amount=10000,
            )
        neutral_response = _neutral_repair_schema_response(schema_model)
        if neutral_response is not None:
            return neutral_response
        raise AssertionError(f"unexpected schema model {schema_model}")

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message=(
                "buy when the 50 crosses the 200 for Tesla from January 2022 "
                "to today with 10k"
            ),
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert seen_schema_names[:3] == [
        "LLMInterpretationResponse",
        "FocusedStrategyExtraction",
        "StatedRunFieldFidelityAudit",
    ]
    assert "FocusedDateWindowExtraction" in seen_schema_names
    draft = result.candidate_strategy_draft
    assert draft.date_range == {
        "start": "2022-01-01",
        "end": new_york_today().isoformat(),
    }
    assert draft.capital_amount == 10000
    assert "stated_run_field_fidelity_audit" in result.reason_codes


def test_default_interpreter_blocks_auto_simplified_buy_hold_for_ambiguous_rule(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    async def fake_direct_schema(**kwargs: Any) -> object:
        assert kwargs["schema_model"] is LLMInterpretationResponse
        return LLMInterpretationResponse(
            intent="strategy_drafting",
            task_relation="new_task",
            requires_clarification=False,
            user_goal_summary="Buy and sell when the asset goes up.",
            candidate_strategy_draft=LLMStrategyDraft(
                raw_user_phrasing="buy and sell when it goes up",
                strategy_type="buy_and_hold",
                strategy_thesis=(
                    "Defaulting to buy-and-hold even though the entry and exit "
                    "rules are vague."
                ),
            ),
            ambiguous_fields=[
                LLMAmbiguousField(
                    field_name="entry_logic",
                    raw_value="when it goes up",
                    reason_code="vague_momentum_language",
                ),
                LLMAmbiguousField(
                    field_name="exit_logic",
                    raw_value="when it goes up",
                    reason_code="vague_momentum_language",
                ),
            ],
            semantic_turn_act="new_idea",
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="buy and sell when it goes up",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert result.requires_clarification is True
    assert result.candidate_strategy_draft.strategy_type is None
    assert len(result.ambiguous_fields) == 2
    assert "blocked_auto_simplification_for_ambiguous_rule" in result.reason_codes


def test_default_interpreter_retries_empty_unsupported_clarification(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    calls: list[tuple[str, str]] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        model_name = str(kwargs.get("model_name", "<task-default>"))
        schema_name = str(kwargs["schema_name"])
        schema_model = kwargs["schema_model"]
        calls.append((model_name, schema_name))
        if model_name == "primary/model" and schema_name == "LLMInterpretationResponse":
            return LLMInterpretationResponse(
                intent="unsupported_or_out_of_scope",
                task_relation="new_task",
                requires_clarification=True,
                user_goal_summary="Buy Tesla after big drops.",
                assistant_response=("Could you clarify what you mean by big drops?"),
            )
        if schema_name == "FocusedStrategyExtraction":
            if model_name == "fallback/model":
                return FocusedStrategyExtraction(
                    is_testable_strategy=True,
                    user_goal_summary="Backtest Tesla after big drops.",
                    strategy_type="indicator_threshold",
                    strategy_thesis="Buy Tesla after large price declines.",
                    asset_universe=["TSLA"],
                    date_range="last 1 year",
                    indicator="rsi",
                    entry_threshold=30,
                    exit_threshold=55,
                )
            return FocusedStrategyExtraction(
                is_testable_strategy=True,
                user_goal_summary="Buy Tesla after big drops.",
            )
        if schema_name == "FocusedDateWindowExtraction":
            return llm_interpreter.FocusedDateWindowExtraction(
                has_date_window=False,
                confidence=0.35,
                evidence="",
            )
        neutral_response = _neutral_repair_schema_response(schema_model)
        if neutral_response is not None:
            return neutral_response
        return LLMInterpretationResponse(
            intent="strategy_drafting",
            task_relation="new_task",
            requires_clarification=True,
            user_goal_summary="Buy Tesla after big drops.",
            semantic_turn_act="new_idea",
            candidate_strategy_draft=LLMStrategyDraft(
                strategy_type="indicator_threshold",
                strategy_thesis="Buy Tesla after large price declines.",
                asset_universe=["TSLA"],
            ),
            missing_required_fields=["date_range", "entry_threshold", "exit_threshold"],
            assistant_response=(
                "I understand you want to buy Tesla after big drops. "
                "What period and threshold should I use?"
            ),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates_with_fallback,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="What if I bought Tesla after big drops?",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert calls[:3] == [
        ("primary/model", "LLMInterpretationResponse"),
        ("primary/model", "FocusedStrategyExtraction"),
        ("fallback/model", "FocusedStrategyExtraction"),
    ]
    assert result.candidate_strategy_draft.asset_universe == ["TSLA"]
    assert result.candidate_strategy_draft.extra_parameters["indicator"] == "rsi"


def test_default_interpreter_keeps_artifact_context_for_vague_signal_clarification(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    seen_schema_names: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        seen_schema_names.append(str(kwargs["schema_name"]))
        schema_model = kwargs["schema_model"]
        if schema_model is LLMInterpretationResponse:
            return LLMInterpretationResponse(
                intent="unsupported_or_out_of_scope",
                task_relation="new_task",
                requires_clarification=True,
                user_goal_summary="Test buying SPY when it starts rising.",
                assistant_response=(
                    "I understand the direction, but starts rising needs a concrete "
                    "trigger such as a moving-average crossover or RSI threshold."
                ),
            )
        neutral_response = _neutral_repair_schema_response(schema_model)
        if neutral_response is not None:
            return neutral_response
        assert schema_model is FocusedStrategyExtraction
        return FocusedStrategyExtraction(
            is_testable_strategy=True,
            requires_clarification=True,
            user_goal_summary="Test buying SPY when it starts rising.",
            strategy_type="signal_strategy",
            strategy_thesis="Buy SPY when it starts rising.",
            asset_universe=["SPY"],
            entry_logic="Buy SPY when it starts rising.",
            missing_required_fields=["date_range", "entry_rule"],
            assistant_response=("What concrete trigger and date range should I use?"),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="Test buying SPY when it starts rising.",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert seen_schema_names[:2] == [
        "LLMInterpretationResponse",
        "FocusedStrategyExtraction",
    ]
    assert "SupportedStrategyCapabilityConflictAudit" in seen_schema_names
    assert result.candidate_strategy_draft.asset_universe == ["SPY"]
    assert result.candidate_strategy_draft.entry_logic == (
        "Buy SPY when it starts rising."
    )
    assert result.requires_clarification is True


def test_default_interpreter_retries_empty_refinement_candidate(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    calls: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> LLMInterpretationResponse:
        model_name = str(kwargs["model_name"])
        calls.append(model_name)
        if model_name == "primary/model":
            return LLMInterpretationResponse(
                intent="strategy_drafting",
                task_relation="refine",
                user_goal_summary="Change the date range.",
                semantic_turn_act="refine_current_idea",
                candidate_strategy_draft=LLMStrategyDraft(),
            )
        return LLMInterpretationResponse(
            intent="strategy_drafting",
            task_relation="refine",
            user_goal_summary="Change the date range.",
            semantic_turn_act="refine_current_idea",
            candidate_strategy_draft=LLMStrategyDraft(date_range="last 6 months"),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates_with_fallback,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="Use the last 6 months instead.",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="buy_and_hold",
                    asset_universe=["NVDA"],
                    asset_class="equity",
                    date_range="past year",
                )
            ),
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    # The primary tier gets its own bounded self-correction pass before the
    # fallback tier is tried, so an empty refinement is re-asked in place first.
    assert calls == [
        "primary/model",
        "primary/model",
        "primary/model",
        "primary/model",
        "fallback/model",
    ]
    assert result.candidate_strategy_draft.date_range == "last 6 months"


def test_default_interpreter_retries_stale_prior_strategy_replay(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    calls: list[tuple[str, str]] = []

    async def fake_direct_schema(**kwargs: Any) -> LLMInterpretationResponse:
        model_name = str(kwargs["model_name"])
        calls.append((model_name, str(kwargs["schema_name"])))
        if model_name == "primary/model":
            return LLMInterpretationResponse(
                intent="backtest_execution",
                task_relation="refine",
                user_goal_summary="Change the asset to Nvidia.",
                candidate_strategy_draft=LLMStrategyDraft(
                    raw_user_phrasing="Test buying and holding Apple over the past year.",
                    strategy_type="buy_and_hold",
                    strategy_thesis=("Test buying and holding Apple over the past year."),
                    asset_universe=["AAPL"],
                    date_range="past year",
                ),
            )
        return LLMInterpretationResponse(
            intent="backtest_execution",
            task_relation="refine",
            user_goal_summary="Change the asset to Nvidia.",
            semantic_turn_act="refine_current_idea",
            candidate_strategy_draft=LLMStrategyDraft(asset_universe=["NVDA"]),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates_with_fallback,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="Actually make it Nvidia.",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    raw_user_phrasing="Test buying and holding Apple over the past year.",
                    strategy_type="buy_and_hold",
                    strategy_thesis="Test buying and holding Apple over the past year.",
                    asset_universe=["AAPL"],
                    asset_class="equity",
                    date_range="last 1 year",
                )
            ),
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert calls[:2] == [
        ("primary/model", "LLMInterpretationResponse"),
        ("primary/model", "AssetGroundingAudit"),
    ]
    assert calls[-1] == ("fallback/model", "LLMInterpretationResponse")
    assert result.candidate_strategy_draft.asset_universe == ["NVDA"]


def test_default_interpreter_plans_stale_artifact_edit_before_fallback(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    calls: list[tuple[str, str]] = []

    async def fake_direct_schema(**kwargs: Any) -> LLMInterpretationResponse:
        model_name = str(kwargs["model_name"])
        calls.append((model_name, str(kwargs["schema_name"])))
        wire_text = "\n".join(message["content"] for message in kwargs["messages"])
        if "Focused artifact edit planning" not in wire_text:
            return LLMInterpretationResponse(
                intent="backtest_execution",
                task_relation="refine",
                user_goal_summary="Change the asset to Nvidia.",
                semantic_turn_act="refine_current_idea",
                candidate_strategy_draft=LLMStrategyDraft(
                    raw_user_phrasing="Test buying and holding Apple over the past year.",
                    strategy_type="buy_and_hold",
                    strategy_thesis=("Test buying and holding Apple over the past year."),
                    asset_universe=["AAPL"],
                    date_range="past year",
                ),
            )
        return LLMInterpretationResponse(
            intent="backtest_execution",
            task_relation="refine",
            user_goal_summary="Change the asset to Nvidia.",
            semantic_turn_act="refine_current_idea",
            candidate_strategy_draft=LLMStrategyDraft(asset_universe=["NVDA"]),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates_with_fallback,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="Actually make it Nvidia.",
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    raw_user_phrasing="Test buying and holding Apple over the past year.",
                    strategy_type="buy_and_hold",
                    strategy_thesis="Test buying and holding Apple over the past year.",
                    asset_universe=["AAPL"],
                    asset_class="equity",
                    date_range="last 1 year",
                )
            ),
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert calls[:2] == [
        ("primary/model", "LLMInterpretationResponse"),
        ("primary/model", "AssetGroundingAudit"),
    ]
    assert calls[2:] == [("primary/model", "LLMInterpretationResponse")]
    assert all(model_name != "fallback/model" for model_name, _schema_name in calls)
    assert interpreter.last_status == "used"
    assert result.candidate_strategy_draft.asset_universe == ["NVDA"]


def test_explicit_model_interpreter_plans_result_refinement_before_accepting_prose(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    FakeChatOpenRouter.calls.clear()
    FakeChatOpenRouter.structured_response = LLMInterpretationResponse(
        intent="conversation_followup",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="User wants to refine the latest result.",
        assistant_response=(
            "I've updated the strategy to use biweekly recurring buys of $500."
        ),
        semantic_turn_act="educational_question",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter, "ChatOpenRouter", FakeChatOpenRouter)

    calls: list[str] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        schema_model = kwargs["schema_model"]
        calls.append(str(kwargs.get("model_name", "<task-default>")))
        if schema_model is not LLMInterpretationResponse:
            neutral_response = _neutral_repair_schema_response(schema_model)
            if neutral_response is not None:
                return neutral_response
        wire_text = "\n".join(message["content"] for message in kwargs["messages"])
        assert "Focused artifact edit planning" in wire_text
        return LLMInterpretationResponse(
            intent="strategy_drafting",
            task_relation="refine",
            requires_clarification=False,
            user_goal_summary="Refine AAPL into recurring biweekly buys.",
            semantic_turn_act="refine_current_idea",
            candidate_strategy_draft=LLMStrategyDraft(
                raw_user_phrasing=(
                    "i want to do recurrent biweekly buys of 500 bucks instead"
                ),
                strategy_type="dca_accumulation",
                asset_universe=["AAPL"],
                asset_class="equity",
                date_range="past year",
                cadence="biweekly",
                capital_amount=500,
                field_provenance={
                    "capital_amount": "recurring_contribution",
                    "cadence": "explicit_user",
                },
            ),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract(),
        model_name="custom/model",
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message=(
                "i want to do recurrent biweekly buys of 500 bucks instead"
            ),
            recent_thread_history=[],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    raw_user_phrasing="Backtest buy and hold Apple over the past year.",
                    strategy_type="buy_and_hold",
                    strategy_thesis="Buy and hold Apple.",
                    asset_universe=["AAPL"],
                    asset_class="equity",
                    date_range="past year",
                )
            ),
            selected_thread_metadata={
                "requested_field": "refinement",
                "source_result_run_id": "run_123",
            },
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert interpreter.last_status == "used"
    assert calls[0] == "custom/model"
    assert result.assistant_response is None
    assert result.candidate_strategy_draft.strategy_type == "dca_accumulation"
    assert result.candidate_strategy_draft.asset_universe == ["AAPL"]
    assert result.candidate_strategy_draft.cadence == "biweekly"
    assert result.candidate_strategy_draft.capital_amount == 500


def test_interpreter_uses_artifact_snapshot_instead_of_raw_history_for_refinements(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    seen_messages: list[dict[str, str]] = []

    async def fake_direct_schema(**kwargs: Any) -> LLMInterpretationResponse:
        seen_messages.extend(kwargs["messages"])
        return LLMInterpretationResponse(
            intent="strategy_drafting",
            task_relation="refine",
            user_goal_summary="Change the asset to Nvidia.",
            candidate_strategy_draft=LLMStrategyDraft(
                raw_user_phrasing="Actually make it Nvidia.",
                strategy_type="buy_and_hold",
                asset_universe=["NVDA"],
            ),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="Actually make it Nvidia.",
            recent_thread_history=[
                ConversationMessage(
                    role="user",
                    content="Test buying and holding Apple over the past year.",
                ),
                ConversationMessage(
                    role="assistant",
                    content=(
                        "I read this as AAPL using a buy and hold approach over "
                        "past year."
                    ),
                ),
            ],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="buy_and_hold",
                    asset_universe=["AAPL"],
                    asset_class="equity",
                    date_range="last 1 year",
                )
            ),
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    wire_text = "\n".join(message["content"] for message in seen_messages)
    assert "Prior strategy JSON" in wire_text
    assert "I read this as AAPL" not in wire_text
    assert "Test buying and holding Apple over the past year." not in wire_text


def test_interpreter_sends_pending_field_metadata_with_artifact_context(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    seen_messages: list[dict[str, str]] = []

    async def fake_direct_schema(**kwargs: Any) -> LLMInterpretationResponse:
        seen_messages.extend(kwargs["messages"])
        return LLMInterpretationResponse(
            intent="strategy_drafting",
            task_relation="continue",
            user_goal_summary="User answered the pending asset field.",
            candidate_strategy_draft=LLMStrategyDraft(
                raw_user_phrasing="google",
                asset_universe=["GOOGL"],
            ),
            semantic_turn_act="answer_pending_need",
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="google",
            recent_thread_history=[
                ConversationMessage(
                    role="assistant",
                    content="What asset should I use instead?",
                ),
            ],
            latest_task_snapshot=TaskSnapshot(
                pending_strategy_summary=StrategySummary(
                    strategy_type="indicator_threshold",
                    asset_universe=["TSLA"],
                    asset_class="equity",
                    date_range={"start": "2025-11-30", "end": "2026-05-31"},
                    entry_logic="Buy when RSI(14) drops to 30 or below",
                    exit_logic="Sell when RSI(14) rises to 55 or above",
                )
            ),
            selected_thread_metadata={
                "last_stage_outcome": "await_user_reply",
                "requested_field": "asset_universe",
            },
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert result.candidate_strategy_draft.strategy_type == "indicator_threshold"
    assert result.candidate_strategy_draft.asset_universe == ["GOOGL"]
    assert result.candidate_strategy_draft.asset_class == "equity"
    assert "requested_asset_answer_provider_resolution" in result.reason_codes
    wire_text = "\n".join(message["content"] for message in seen_messages)
    assert "Selected thread metadata JSON" in wire_text
    assert '"requested_field": "asset_universe"' in wire_text
    assert "What asset should I use instead?" not in wire_text


def test_default_interpreter_rejects_result_explanation_without_latest_result(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    calls: list[tuple[str, str]] = []

    async def fake_direct_schema(**kwargs: Any) -> object:
        model_name = str(kwargs.get("model_name", "<task-default>"))
        schema_name = str(kwargs["schema_name"])
        schema_model = kwargs["schema_model"]
        calls.append((model_name, schema_name))
        if schema_name == "StatedRunFieldFidelityAudit":
            return StatedRunFieldFidelityAudit(
                comparison_baseline="SPY",
                date_range="last year",
            )
        if schema_model is FocusedStrategyExtraction:
            return FocusedStrategyExtraction(
                is_testable_strategy=True,
                user_goal_summary="Backtest Microsoft buy and hold.",
                strategy_type="buy_and_hold",
                strategy_thesis="Hold Microsoft for the last year.",
                asset_universe=["MSFT"],
                date_range="last year",
                comparison_baseline="SPY",
            )
        neutral_response = _neutral_repair_schema_response(schema_model)
        if neutral_response is not None:
            return neutral_response
        if model_name == "primary/model":
            return LLMInterpretationResponse(
                intent="results_explanation",
                task_relation="new_task",
                user_goal_summary="Claims a run result without a run.",
                semantic_turn_act="answer_pending_need",
                assistant_response="Microsoft beat SPY by 10.2%.",
            )
        return LLMInterpretationResponse(
            intent="backtest_execution",
            task_relation="new_task",
            user_goal_summary="Backtest Microsoft buy and hold.",
            semantic_turn_act="new_idea",
            candidate_strategy_draft=LLMStrategyDraft(
                raw_user_phrasing="Did Microsoft beat SPY last year if I held it?",
                strategy_type="buy_and_hold",
                strategy_thesis="Hold Microsoft for the last year.",
                asset_universe=["MSFT"],
                date_range="last year",
            ),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates_with_fallback,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="Did Microsoft beat SPY last year if I held it?",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert calls[:3] == [
        ("primary/model", "LLMInterpretationResponse"),
        ("primary/model", "FocusedStrategyExtraction"),
        ("<task-default>", "StatedRunFieldFidelityAudit"),
    ]
    assert result is not None
    assert result.intent == "backtest_execution"
    assert result.candidate_strategy_draft.asset_universe == ["MSFT"]
    assert result.candidate_strategy_draft.comparison_baseline == "SPY"


def test_default_interpreter_coerces_strategy_draft_mislabeled_as_result_context(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    async def fake_direct_schema(**_kwargs: Any) -> LLMInterpretationResponse:
        return LLMInterpretationResponse(
            intent="results_explanation",
            task_relation="new_task",
            user_goal_summary="Backtest Microsoft buy and hold.",
            semantic_turn_act="result_followup",
            candidate_strategy_draft=LLMStrategyDraft(
                raw_user_phrasing="Did Microsoft beat SPY last year if I held it?",
                strategy_type="buy_and_hold",
                strategy_thesis="Hold Microsoft for the last year.",
                asset_universe=["MSFT"],
                date_range="last year",
            ),
        )

    monkeypatch.setattr(
        llm_interpreter,
        "invoke_openrouter_json_schema",
        fake_direct_schema,
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    result = interpreter(
        InterpretationRequest(
            current_user_message="Did Microsoft beat SPY last year if I held it?",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is not None
    assert result.intent == "strategy_drafting"
    assert result.semantic_turn_act == "new_idea"
    assert "coerced_result_explanation_to_strategy_draft" in result.reason_codes
    assert result.candidate_strategy_draft.asset_universe == ["MSFT"]


def test_interpretation_llm_has_hard_turn_budget(monkeypatch) -> None:
    from argus.agent_runtime import llm_interpreter

    monkeypatch.setattr(
        llm_interpreter,
        "build_openrouter_model",
        lambda *_args, **_kwargs: SlowStructuredInterpreterModel(),
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_task_timeout_seconds",
        lambda _task: 0.01,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract(),
        model_name="primary/model",
    )

    result = interpreter(
        InterpretationRequest(
            current_user_message="what strategies can I test?",
            recent_thread_history=[],
            latest_task_snapshot=None,
            user=UserState(user_id="u1"),
        )
    )

    assert result is None
    assert interpreter.last_status == "failed"


@pytest.mark.asyncio
async def test_agent_runtime_turn_uses_interpretation_profile_without_legacy_composer(
    monkeypatch,
) -> None:
    FakeChatOpenRouter.calls.clear()
    FakeChatOpenRouter.structured_response = LLMInterpretationResponse(
        intent="conversation_followup",
        task_relation="new_task",
        user_goal_summary="User asked what Argus can do.",
        assistant_response="Argus can help shape and test investing ideas.",
        semantic_turn_act="educational_question",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter, "ChatOpenRouter", FakeChatOpenRouter)

    contract = build_default_capability_contract()
    workflow = build_workflow(
        structured_interpreter=OpenRouterStructuredInterpreter(
            contract=contract,
            model_name="custom/model",
        ),
        checkpointer=MemorySaver(),
    )
    result = await run_agent_turn(
        workflow=workflow,
        user=UserState(user_id="u1"),
        thread_id="thread-policy",
        message="what can you do?",
    )

    assert result["assistant_response"] == (
        "Argus can help shape and test investing ideas."
    )
    assert FakeChatOpenRouter.calls == [
        {
            "model_name": "custom/model",
            "temperature": 0,
            "max_tokens": 3200,
            "timeout": 20,
            "max_retries": 1,
            "openrouter_api_key": "test-key",
            "openrouter_provider": openrouter.openrouter_provider_policy(),
        }
    ]


def test_openrouter_failure_log_includes_visible_diagnostics(monkeypatch) -> None:
    observed: list[tuple[str, dict[str, object]]] = []

    def warning_stub(message: str, **kwargs: object) -> None:
        observed.append((message, kwargs))

    monkeypatch.setattr("argus.llm.openrouter.logger.warning", warning_stub)

    log_openrouter_failure(
        task="interpretation",
        model_name="test/model",
        exc=RuntimeError("provider rejected request"),
        message="LLM interpretation failed; falling back",
    )

    message, kwargs = observed[0]
    assert "task=interpretation" in message
    assert "model=test/model" in message
    assert "max_tokens=3200" in message
    assert "error_type=RuntimeError" in message
    assert "provider rejected request" not in message
    assert kwargs["error_type"] == "RuntimeError"
    assert "error" not in kwargs


def _captured_failure_log(monkeypatch, exc: Exception) -> str:
    observed: list[str] = []
    monkeypatch.setattr(
        "argus.llm.openrouter.logger.warning",
        lambda message, **_kwargs: observed.append(message),
    )
    log_openrouter_failure(
        task="interpretation",
        model_name="test/model",
        exc=exc,
        message="LLM interpretation failed",
    )
    return observed[0]


def test_openrouter_failure_log_reports_raising_origin(monkeypatch) -> None:
    def _raise_local_rejection() -> None:
        raise ValueError(
            "OpenRouter interpretation returned an incomplete strategy draft"
        )

    # The logger selects Argus frames; a checkout's directory name is incidental.
    # Give this isolated raising fixture a module path inside that package.
    _raise_local_rejection.__code__ = _raise_local_rejection.__code__.replace(
        co_filename="/fixture/argus/test_openrouter_policy.py"
    )

    try:
        _raise_local_rejection()
    except ValueError as exc:
        message = _captured_failure_log(monkeypatch, exc)

    assert "error_type=ValueError" in message
    assert (
        "OpenRouter interpretation returned an incomplete strategy draft" not in message
    )
    # Points at the raising line so a deterministic local rejection is
    # distinguishable from a provider transport failure.
    assert "error_origin=test_openrouter_policy.py:" in message


def test_openrouter_failure_log_survives_braces_in_detail() -> None:
    # Real loguru here: a stubbed warning would not exercise its formatting.
    try:
        raise ValueError('provider said {"error": {"code": 400}}')
    except ValueError as exc:
        log_openrouter_failure(
            task="interpretation",
            model_name="test/model",
            exc=exc,
            message="LLM interpretation failed",
        )


def test_openrouter_failure_log_omits_long_provider_detail(monkeypatch) -> None:
    try:
        raise RuntimeError("x" * 5000)
    except RuntimeError as exc:
        message = _captured_failure_log(monkeypatch, exc)

    assert "xxx" not in message
    assert "error_detail" not in message
    assert len(message) < 1000


def test_direct_json_schema_payload_uses_interpretation_profile_reasoning(
    monkeypatch,
) -> None:
    observed_payloads: list[dict[str, Any]] = []
    openrouter.clear_openrouter_route_receipts()

    class FakeAsyncClient:
        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, _url: str, **kwargs: Any) -> object:
            observed_payloads.append(kwargs["json"])

            class FakeResponse:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict[str, Any]:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"intent":"conversation_followup","task_relation":"new_task","requires_clarification":false,"user_goal_summary":"hi","candidate_strategy_draft":{},"missing_required_fields":[],"assistant_response":"Hi.","uses_latest_result_context":false,"confidence":0.8,"reason_codes":[],"ambiguous_fields":[],"unsupported_constraints":[],"response_profile_overrides":{},"semantic_turn_act":"educational_question","result_followup_focus":null}'
                                }
                            }
                        ]
                    }

            return FakeResponse()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "qwen/qwen3.5-9b")
    monkeypatch.setattr(
        openrouter.httpx, "AsyncClient", lambda **_kwargs: FakeAsyncClient()
    )

    result = asyncio.run(
        openrouter.invoke_openrouter_json_schema(
            task="interpretation",
            messages=[{"role": "user", "content": "hello"}],
            schema_model=LLMInterpretationResponse,
            schema_name="LLMInterpretationResponse",
        )
    )

    assert result is not None
    assert observed_payloads[0]["reasoning"] == {"effort": "medium"}
    assert observed_payloads[0]["provider"] == openrouter.openrouter_provider_policy()
    receipts = openrouter.get_openrouter_route_receipts()
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.task == "interpretation"
    assert receipt.tier == "structured"
    assert receipt.model == "qwen/qwen3.5-9b"
    assert receipt.schema_name == "LLMInterpretationResponse"
    assert receipt.outcome == "succeeded"
    assert receipt.failure_mode is None


def test_field_fidelity_json_schema_uses_structured_route_without_reasoning(
    monkeypatch,
) -> None:
    observed_payloads: list[dict[str, Any]] = []
    openrouter.clear_openrouter_route_receipts()

    class FakeAsyncClient:
        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, _url: str, **kwargs: Any) -> object:
            observed_payloads.append(kwargs["json"])

            class FakeResponse:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict[str, Any]:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"capital_amount":100000,"recurring_contribution_amount":null,"cadence":null,"timeframe":null,"date_range":null,"comparison_baseline":null,"confidence":0.95}'
                                }
                            }
                        ]
                    }

            return FakeResponse()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "qwen/qwen3.5-9b")
    monkeypatch.setattr(
        openrouter.httpx, "AsyncClient", lambda **_kwargs: FakeAsyncClient()
    )

    result = asyncio.run(
        openrouter.invoke_openrouter_json_schema(
            task="field_fidelity",
            messages=[{"role": "user", "content": "con 100000"}],
            schema_model=StatedRunFieldFidelityAudit,
            schema_name="StatedRunFieldFidelityAudit",
        )
    )

    assert result is not None
    assert result.capital_amount == 100000
    assert observed_payloads[0]["model"] == "qwen/qwen3.5-9b"
    assert observed_payloads[0]["reasoning"] == {"effort": "none"}
    assert observed_payloads[0]["provider"] == openrouter.openrouter_provider_policy()
    receipts = openrouter.get_openrouter_route_receipts()
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.task == "field_fidelity"
    assert receipt.tier == "structured"
    assert receipt.model == "qwen/qwen3.5-9b"
    assert receipt.schema_name == "StatedRunFieldFidelityAudit"
    assert receipt.outcome == "succeeded"


def test_capability_conflict_json_schema_uses_context_route_with_reasoning(
    monkeypatch,
) -> None:
    observed_payloads: list[dict[str, Any]] = []
    openrouter.clear_openrouter_route_receipts()

    class FakeAsyncClient:
        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, _url: str, **kwargs: Any) -> object:
            observed_payloads.append(kwargs["json"])

            class FakeResponse:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict[str, Any]:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"drop_unsupported_strategy_logic":true,"keep_unsupported_strategy_logic":false,"confidence":0.94}'
                                }
                            }
                        ]
                    }

            return FakeResponse()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_CONTEXT_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setattr(
        openrouter.httpx, "AsyncClient", lambda **_kwargs: FakeAsyncClient()
    )

    result = asyncio.run(
        openrouter.invoke_openrouter_json_schema(
            task="capability_conflict",
            messages=[{"role": "user", "content": "Compra y mantén ETH"}],
            schema_model=SupportedStrategyCapabilityConflictAudit,
            schema_name="SupportedStrategyCapabilityConflictAudit",
        )
    )

    assert result is not None
    assert result.drop_unsupported_strategy_logic is True
    assert observed_payloads[0]["model"] == "openai/gpt-oss-120b"
    assert observed_payloads[0]["reasoning"] == {"effort": "medium"}
    assert observed_payloads[0]["provider"] == openrouter.openrouter_provider_policy()
    receipts = openrouter.get_openrouter_route_receipts()
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.task == "capability_conflict"
    assert receipt.tier == "context"
    assert receipt.model == "openai/gpt-oss-120b"
    assert receipt.schema_name == "SupportedStrategyCapabilityConflictAudit"
    assert receipt.outcome == "succeeded"


@pytest.mark.parametrize(
    "task",
    [
        "interpretation",
        "interpretation_repair",
        "field_fidelity",
        "capability_conflict",
    ],
)
def test_structured_artifact_payload_marks_stable_system_prefix_for_prompt_cache(
    task: openrouter.OpenRouterTask,
) -> None:
    from argus.agent_runtime.llm_interpreter_types import LLMDateRangeIntent

    payload = openrouter._json_schema_payload(
        model="qwen/qwen3.5-9b",
        messages=[
            {"role": "system", "content": "stable Argus interpreter policy"},
            {"role": "system", "content": "dynamic turn context"},
            {"role": "user", "content": "dynamic user request"},
        ],
        schema_model=LLMDateRangeIntent,
        schema_name="LLMDateRangeIntent",
        profile=openrouter_profile_for_task(task),
    )

    system_message = payload["messages"][0]
    assert system_message["role"] == "system"
    assert system_message["content"] == [
        {
            "type": "text",
            "text": "stable Argus interpreter policy",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    assert payload["messages"][1] == {"role": "system", "content": "dynamic turn context"}
    assert payload["messages"][2] == {
        "role": "user",
        "content": "dynamic user request",
    }


def test_gemini_payload_skips_prompt_cache_when_later_system_context_is_dynamic() -> None:
    from argus.agent_runtime.llm_interpreter_types import LLMDateRangeIntent

    payload = openrouter._json_schema_payload(
        model="google/gemini-2.5-flash-lite",
        messages=[
            {"role": "system", "content": "stable Argus interpreter policy"},
            {"role": "system", "content": "dynamic turn context"},
            {"role": "user", "content": "dynamic user request"},
        ],
        schema_model=LLMDateRangeIntent,
        schema_name="LLMDateRangeIntent",
        profile=openrouter_profile_for_task("interpretation"),
    )

    assert payload["messages"][0] == {
        "role": "system",
        "content": "stable Argus interpreter policy",
    }
    assert payload["messages"][1] == {
        "role": "system",
        "content": "dynamic turn context",
    }


def test_non_target_json_schema_payload_does_not_add_prompt_cache_marker() -> None:
    from argus.agent_runtime.llm_interpreter_types import LLMDateRangeIntent

    payload = openrouter._json_schema_payload(
        model="qwen/qwen3.5-9b",
        messages=[
            {"role": "system", "content": "stable naming policy"},
            {"role": "user", "content": "dynamic user request"},
        ],
        schema_model=LLMDateRangeIntent,
        schema_name="LLMDateRangeIntent",
        profile=openrouter_profile_for_task("name_suggestion"),
    )

    assert payload["messages"][0] == {
        "role": "system",
        "content": "stable naming policy",
    }


def test_direct_json_schema_records_missing_key_route_receipt(monkeypatch) -> None:
    openrouter.clear_openrouter_route_receipts()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "structured/primary")
    monkeypatch.setenv("CUADRAO_STRUCTURED_FALLBACK_MODEL", "structured/fallback")

    result = asyncio.run(
        openrouter.invoke_openrouter_json_schema(
            task="interpretation",
            messages=[{"role": "user", "content": "hello"}],
            schema_model=LLMInterpretationResponse,
            schema_name="LLMInterpretationResponse",
        )
    )

    assert result is None
    receipts = openrouter.get_openrouter_route_receipts()
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.task == "interpretation"
    assert receipt.tier == "structured"
    assert receipt.model == "structured/primary"
    assert receipt.fallback_model == "structured/fallback"
    assert receipt.outcome == "skipped"
    assert receipt.failure_mode == "missing_api_key"


def test_route_receipt_capture_collects_current_runtime_calls() -> None:
    token = openrouter.begin_openrouter_route_receipt_capture()
    openrouter.record_openrouter_route_receipt(
        task="result_summary",
        model_name="openai/gpt-5.6-luna",
        mode="chat_model",
        schema_name=None,
        latency_ms=42,
        outcome="failed",
        failure_mode="TimeoutError",
        token_usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        context_packet_ids=["packet-1"],
    )
    captured = openrouter.end_openrouter_route_receipt_capture(token)

    assert len(captured) == 1
    assert captured[0].task == "result_summary"
    assert captured[0].failure_mode == "TimeoutError"
    assert captured[0].token_usage == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
    }
    assert captured[0].context_packet_ids == ["packet-1"]
    assert captured[0].as_dict()["context_packet_ids"] == ["packet-1"]


def test_direct_json_schema_route_receipt_preserves_provider_usage_cost(
    monkeypatch,
) -> None:
    openrouter.clear_openrouter_route_receipts()

    class FakeAsyncClient:
        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, _url: str, **_kwargs: Any) -> object:
            class FakeResponse:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict[str, Any]:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": LLMInterpretationResponse(
                                        intent="conversation_followup",
                                        task_relation="new_task",
                                        requires_clarification=False,
                                        user_goal_summary="what Argus supports",
                                        assistant_response=(
                                            "I can help test supported ideas."
                                        ),
                                        uses_latest_result_context=False,
                                        confidence=0.91,
                                        semantic_turn_act="educational_question",
                                    ).model_dump_json()
                                }
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 12,
                            "completion_tokens": 6,
                            "total_tokens": 18,
                            "cost": 0.00054,
                        },
                    }

            return FakeResponse()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "structured/primary")
    monkeypatch.setattr(
        openrouter.httpx, "AsyncClient", lambda **_kwargs: FakeAsyncClient()
    )

    result = asyncio.run(
        openrouter.invoke_openrouter_json_schema(
            task="interpretation",
            messages=[{"role": "user", "content": "what can you do?"}],
            schema_model=LLMInterpretationResponse,
            schema_name="LLMInterpretationResponse",
        )
    )

    assert result is not None
    receipt = openrouter.get_openrouter_route_receipts()[0]
    assert receipt.token_usage == {
        "prompt_tokens": 12,
        "completion_tokens": 6,
        "total_tokens": 18,
    }
    assert receipt.usage_cost_usd == 0.00054
    assert receipt.as_dict()["usage_cost_usd"] == 0.00054


def test_route_receipt_latency_summary_keeps_failure_and_context_evidence() -> None:
    openrouter.clear_openrouter_route_receipts()
    openrouter.record_openrouter_route_receipt(
        task="interpretation",
        model_name="structured/primary",
        mode="json_schema",
        schema_name="LLMInterpretationResponse",
        latency_ms=1200,
        outcome="succeeded",
        token_usage={"prompt_tokens": 50, "completion_tokens": 20},
    )
    openrouter.record_openrouter_route_receipt(
        task="clarification",
        model_name="chat/fallback",
        mode="json_schema",
        schema_name="ClarificationResponse",
        latency_ms=4100,
        outcome="failed",
        failure_mode="TimeoutError",
        token_usage={"total_tokens": 30},
    )
    openrouter.record_openrouter_route_receipt(
        task="capability_conflict",
        model_name="context/primary",
        mode="json_schema",
        schema_name="SupportedStrategyCapabilityConflictAudit",
        latency_ms=2400,
        outcome="succeeded",
        context_packet_ids=["packet-2", "packet-1"],
    )

    summary = openrouter.summarize_openrouter_route_receipts()

    assert summary["receipt_count"] == 3
    assert summary["total_latency_ms"] == 7700
    assert summary["failure_count"] == 1
    assert summary["slowest_task"] == "clarification"
    assert summary["slowest_latency_ms"] == 4100
    assert summary["context_packet_ids"] == ["packet-2", "packet-1"]
    assert summary["token_usage"] == {
        "prompt_tokens": 50,
        "completion_tokens": 20,
        "total_tokens": 30,
    }
    assert summary["route_waterfall"][1]["failure_mode"] == "TimeoutError"


def test_direct_json_schema_records_openrouter_token_usage(monkeypatch) -> None:
    from argus.agent_runtime.llm_interpreter_types import LLMInterpretationResponse

    openrouter.clear_openrouter_route_receipts()

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": LLMInterpretationResponse(
                                intent="conversation_followup",
                                task_relation="new_task",
                                user_goal_summary="User asked what Argus can do.",
                            ).model_dump_json()
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 44,
                    "completion_tokens": 21,
                    "total_tokens": 65,
                    "prompt_tokens_details": {
                        "cached_tokens": 32,
                        "cache_write_tokens": 12,
                    },
                },
            }

    class FakeAsyncClient:
        def __init__(self, **_kwargs: object) -> None:
            return None

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "structured/primary")
    monkeypatch.setattr(
        openrouter.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient(**kwargs)
    )

    result = asyncio.run(
        openrouter.invoke_openrouter_json_schema(
            task="interpretation",
            messages=[{"role": "user", "content": "hello"}],
            schema_model=LLMInterpretationResponse,
            schema_name="LLMInterpretationResponse",
        )
    )

    assert result is not None
    receipt = openrouter.get_openrouter_route_receipts()[0]
    assert receipt.token_usage == {
        "prompt_tokens": 44,
        "completion_tokens": 21,
        "total_tokens": 65,
        "cached_tokens": 32,
        "cache_write_tokens": 12,
    }


def test_direct_json_schema_enforces_wall_clock_task_budget(monkeypatch) -> None:
    from argus.agent_runtime.llm_interpreter_types import LLMInterpretationResponse

    openrouter.clear_openrouter_route_receipts()

    class SlowAsyncClient:
        def __init__(self, **_kwargs: object) -> None:
            return None

        async def __aenter__(self) -> "SlowAsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> object:
            await asyncio.sleep(10)
            raise AssertionError("the task budget should cancel this request")

    profile = openrouter.OpenRouterProfile(
        "interpretation",
        temperature=0,
        max_tokens=200,
        timeout_seconds=0.01,
    )

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "structured/primary")
    monkeypatch.setenv("CUADRAO_STRUCTURED_FALLBACK_MODEL", "")
    monkeypatch.setattr(openrouter, "openrouter_profile_for_task", lambda _task: profile)
    monkeypatch.setattr(
        openrouter.httpx, "AsyncClient", lambda **kwargs: SlowAsyncClient(**kwargs)
    )

    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        asyncio.run(
            asyncio.wait_for(
                openrouter.invoke_openrouter_json_schema(
                    task="interpretation",
                    messages=[{"role": "user", "content": "hello"}],
                    schema_model=LLMInterpretationResponse,
                    schema_name="LLMInterpretationResponse",
                ),
                timeout=0.2,
            )
        )

    receipts = openrouter.get_openrouter_route_receipts()
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.task == "interpretation"
    assert receipt.model == "structured/primary"
    assert receipt.outcome == "failed"
    assert receipt.failure_mode == "TimeoutError"
    assert receipt.latency_ms < 200


def test_direct_json_schema_sync_tries_configured_fallback_for_utility_titles(
    monkeypatch,
) -> None:
    from argus.api.naming import NameSuggestion

    openrouter.clear_openrouter_route_receipts()
    attempted_models: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [{"message": {"content": '{"name":"Tesla Dip Test"}'}}],
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 4,
                    "total_tokens": 12,
                },
            }

    class FakeSyncClient:
        def __init__(self, **_kwargs: object) -> None:
            return None

        def __enter__(self) -> "FakeSyncClient":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, *_args: object, **kwargs: object) -> FakeResponse:
            payload = kwargs["json"]
            assert isinstance(payload, dict)
            model = str(payload["model"])
            attempted_models.append(model)
            if model == "utility/primary":
                raise openrouter.httpx.TimeoutException("slow utility model")
            return FakeResponse()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_UTILITY_MODEL", "utility/primary")
    monkeypatch.setenv("CUADRAO_UTILITY_FALLBACK_MODEL", "utility/fallback")
    monkeypatch.setattr(
        openrouter.httpx, "Client", lambda **kwargs: FakeSyncClient(**kwargs)
    )

    result = openrouter.invoke_openrouter_json_schema_sync(
        task="name_suggestion",
        messages=[{"role": "user", "content": "Tesla dip-buying idea"}],
        schema_model=NameSuggestion,
        schema_name="name_suggestion",
    )

    assert result is not None
    assert result.name == "Tesla Dip Test"
    assert attempted_models == ["utility/primary", "utility/fallback"]
    receipts = openrouter.get_openrouter_route_receipts()
    assert [receipt.outcome for receipt in receipts] == ["failed", "succeeded"]
    assert receipts[0].failure_mode == "TimeoutException"
    assert receipts[1].fallback_used is True
    assert receipts[1].tier == "utility"
    assert receipts[1].token_usage == {
        "prompt_tokens": 8,
        "completion_tokens": 4,
        "total_tokens": 12,
    }


def test_direct_chat_completion_tries_configured_fallback_and_records_usage(
    monkeypatch,
) -> None:
    openrouter.clear_openrouter_route_receipts()
    attempted_models: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [{"message": {"content": "Plain-English result summary."}}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 7,
                    "total_tokens": 19,
                },
            }

    class FakeAsyncClient:
        def __init__(self, **_kwargs: object) -> None:
            return None

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **kwargs: object) -> FakeResponse:
            payload = kwargs["json"]
            assert isinstance(payload, dict)
            model = str(payload["model"])
            attempted_models.append(model)
            if model == "chat/primary":
                raise openrouter.httpx.TimeoutException("slow primary")
            return FakeResponse()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CUADRAO_CHAT_MODEL", "chat/primary")
    monkeypatch.setenv("CUADRAO_CHAT_FALLBACK_MODEL", "chat/fallback")
    monkeypatch.setattr(
        openrouter.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient(**kwargs)
    )

    result = asyncio.run(
        openrouter.invoke_openrouter_chat_completion(
            task="chat_composer",
            messages=[{"role": "user", "content": "summarize"}],
            context_packet_ids=["packet-1"],
        )
    )

    assert result == "Plain-English result summary."
    assert attempted_models == ["chat/primary", "chat/fallback"]
    receipts = openrouter.get_openrouter_route_receipts()
    assert [receipt.outcome for receipt in receipts] == ["failed", "succeeded"]
    assert receipts[0].failure_mode == "TimeoutException"
    assert receipts[1].fallback_used is True
    assert receipts[1].token_usage == {
        "prompt_tokens": 12,
        "completion_tokens": 7,
        "total_tokens": 19,
    }
    assert receipts[1].context_packet_ids == ["packet-1"]


def test_anthropic_structured_calls_use_schema_in_prompt_not_response_format() -> None:
    """Anthropic strict structured outputs reject core shapes of our schemas
    (numeric bounds, any-typed values, open objects like extra_parameters), so
    every native json_schema call to anthropic/* returned 400 and the
    interpretation fallback never worked. Anthropic models get the schema
    embedded in a system message instead; tolerant providers keep the native
    strict response_format. Client-side pydantic validation enforces the
    schema either way.
    """

    import json as _json

    from argus.agent_runtime.llm_interpreter_types import LLMDateRangeIntent

    def _payload(model: str) -> dict:
        return openrouter._json_schema_payload(
            model=model,
            messages=[{"role": "user", "content": "probe"}],
            schema_model=LLMDateRangeIntent,
            schema_name="LLMDateRangeIntent",
            profile=openrouter_profile_for_task("interpretation"),
        )

    anthropic_payload = _payload("anthropic/claude-haiku-4.5")
    grok_payload = _payload("x-ai/grok-4.3")

    assert "response_format" not in anthropic_payload
    assert anthropic_payload["provider"] == openrouter.openrouter_provider_policy()
    schema_message = anthropic_payload["messages"][0]
    assert schema_message["role"] == "system"
    schema_content = schema_message["content"]
    assert schema_content[0]["cache_control"] == {"type": "ephemeral"}
    assert '"same_as_latest_result"' in schema_content[0]["text"]
    assert anthropic_payload["messages"][-1]["content"] == "probe"

    grok_schema = grok_payload["response_format"]["json_schema"]
    assert grok_schema["strict"] is True
    assert "minimum" in _json.dumps(grok_schema["schema"])
    assert grok_payload["provider"] == openrouter.openrouter_provider_policy()

    # Client-side enforcement stays the real gate for both providers.
    with pytest.raises(ValueError):
        LLMDateRangeIntent(kind="explicit_range", confidence=5.0)


def test_json_content_code_fence_stripping_is_safe() -> None:
    fenced = '```json\n{"ok": true}\n```'
    plain = '{"ok": true}'
    assert openrouter._json_content_without_code_fences(fenced) == '{"ok": true}'
    assert openrouter._json_content_without_code_fences(plain) == plain
    # Degenerate fence-only content stays unusable either way; it must simply
    # not crash and not fabricate JSON.
    assert openrouter._json_content_without_code_fences("```") == ""


def test_json_content_code_fence_stripping_handles_provider_variants() -> None:
    """Schema-in-prompt providers fence on one line, skip the language tag,
    or wrap the fence in prose on either side; all must still yield the body."""

    single_line = '```json {"ok": true}```'
    no_language_tag = '```\n{"ok": true}\n```'
    inline_no_tag = '```{"ok": true}```'
    trailing_prose = '```json\n{"ok": true}\n```\nThis JSON matches the schema.'
    leading_prose = 'Here is the JSON:\n```json\n{"ok": true}\n```'
    unterminated = '```json\n{"ok": true}'
    for content in (
        single_line,
        no_language_tag,
        inline_no_tag,
        trailing_prose,
        leading_prose,
        unterminated,
    ):
        assert (
            openrouter._json_content_without_code_fences(content) == '{"ok": true}'
        ), content
    # Bare JSON that happens to contain a fence inside a string stays intact.
    bare_json_with_fence = '{"note": "wrap code in ``` blocks"}'
    assert (
        openrouter._json_content_without_code_fences(bare_json_with_fence)
        == bare_json_with_fence
    )


def test_json_content_fence_inside_json_string_value_is_not_a_fence() -> None:
    """A ``` inside a JSON string value is content, not a fence: when a JSON
    value opens before the first ``` and parses past it, that value is
    extracted instead of being truncated at the embedded fence."""

    prose_then_json = 'Note: {"note": "wrap code in ``` blocks", "ok": true}'
    assert (
        openrouter._json_content_without_code_fences(prose_then_json)
        == '{"note": "wrap code in ``` blocks", "ok": true}'
    )
    prose_then_array = 'Result: ["keep ``` intact", "ok"]'
    assert (
        openrouter._json_content_without_code_fences(prose_then_array)
        == '["keep ``` intact", "ok"]'
    )


def test_json_content_prose_brace_before_real_fence_still_yields_body() -> None:
    """A brace inside leading prose does not demote a real fenced body: junk
    braces and prose JSON that closes before the fence both defer to it."""

    junk_brace = 'Here is the schema {...}: ```json\n{"ok": true}\n```'
    schema_mention = (
        'Matching {"type": "object"} as requested: ```json\n{"ok": true}\n```'
    )
    for content in (junk_brace, schema_mention):
        assert (
            openrouter._json_content_without_code_fences(content) == '{"ok": true}'
        ), content


def _empty_refine_response() -> LLMInterpretationResponse:
    return LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="refine",
        user_goal_summary="Change the date range.",
        semantic_turn_act="refine_current_idea",
        candidate_strategy_draft=LLMStrategyDraft(),
    )


def _active_card_request(message: str) -> InterpretationRequest:
    return InterpretationRequest(
        current_user_message=message,
        recent_thread_history=[],
        latest_task_snapshot=TaskSnapshot(
            pending_strategy_summary=StrategySummary(
                strategy_type="buy_and_hold",
                asset_universe=["NVDA"],
                asset_class="equity",
                date_range="past year",
            )
        ),
        user=UserState(user_id="u1"),
    )


def test_contract_rejection_is_recorded_as_a_distinct_route_receipt(
    monkeypatch,
) -> None:
    from argus.agent_runtime import llm_interpreter

    async def fake_direct_schema(**kwargs: Any) -> LLMInterpretationResponse:
        return _empty_refine_response()

    monkeypatch.setattr(
        llm_interpreter, "invoke_openrouter_json_schema", fake_direct_schema
    )
    monkeypatch.setattr(
        llm_interpreter,
        "openrouter_structured_model_candidates",
        _structured_model_candidates_with_fallback,
    )

    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    token = openrouter.begin_openrouter_route_receipt_capture()
    try:
        result = interpreter(_active_card_request("Use the last 6 months instead."))
    finally:
        receipts = openrouter.end_openrouter_route_receipt_capture(token)

    assert result is None
    rejected = [
        receipt
        for receipt in receipts
        if receipt.failure_mode == "interpretation_contract_rejected"
    ]
    # Both tiers rejected, and neither is invisible in telemetry any more.
    assert {receipt.model for receipt in rejected} == {
        "primary/model",
        "fallback/model",
    }
    assert all(receipt.outcome == "failed" for receipt in rejected)
    assert interpreter.last_failure_kind == "contract_rejected"


@pytest.mark.parametrize("sync", [False, True])
@pytest.mark.parametrize("invalid_date", [False, True])
def test_gemini_document_native_wire_keeps_privacy_and_local_validation(
    monkeypatch, respx_mock, sync, invalid_date
) -> None:
    import json

    import httpx
    from argus.domain.ingestion.documents.models import ExtractionResult
    from pydantic import ValidationError

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "synthetic-document-key")
    monkeypatch.setenv("ARGUS_VISION_MODEL", "google/gemini-3.8-flash")
    output = ExtractionResult.model_validate(
        {
            "complete": True,
            "readable": True,
            "pages_read": [1],
            "observations": [
                {
                    "page": 1,
                    "row": 1,
                    "evidence": "due_notice",
                    "amount": "73.64",
                    "currency": "USD",
                }
            ],
        }
    ).model_dump(mode="json")
    if invalid_date:
        output["observations"][0]["occurred_on"] = "not-a-date"
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(output)}}
                ]
            },
        )
    )
    arguments = dict(
        task="document_extraction",
        model_name="google/gemini-3.8-flash",
        messages=[{"role": "user", "content": "Synthetic unknown document"}],
        schema_model=ExtractionResult,
        schema_name="document_observations",
    )

    def invoke():
        with openrouter_traffic_class("registered"):
            if sync:
                return openrouter.invoke_openrouter_json_schema_sync(**arguments)
            return asyncio.run(openrouter.invoke_openrouter_json_schema(**arguments))

    if invalid_date:
        with pytest.raises(ValidationError):
            invoke()
    else:
        parsed = invoke()
        assert parsed.model_dump(mode="json") == output
        assert parsed.receipt is None
        assert parsed.observations[0].direction == "unknown"
        assert parsed.observations[0].status == "unknown"
    assert route.call_count == 1
    payload = json.loads(route.calls[0].request.content)
    assert "temperature" not in payload
    assert payload["max_tokens"] == 12000
    assert payload["provider"] == {
        "require_parameters": True,
        "data_collection": "deny",
        "zdr": True,
        "allow_fallbacks": False,
    }
    assert payload["messages"] == arguments["messages"]
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "document_observations",
            "strict": True,
            "schema": openrouter._document_wire_schema(
                ExtractionResult.model_json_schema()
            ),
        },
    }
    profile = openrouter_profile_for_task("document_extraction")
    assert (profile.timeout_seconds, profile.max_retries) == (90, 0)


@pytest.mark.parametrize(
    "model",
    [
        "google/gemini-3.8-flash",
        "google/gemini-3.8-flash-preview",
        "google/gemini-2.5-flash",
        "google/gemini-3.8-flash:nitro",
    ],
)
def test_every_google_document_route_gets_the_projected_payload(model):
    from argus.domain.ingestion.documents.models import ExtractionResult

    profile = openrouter_profile_for_task("document_extraction")
    payload = openrouter._json_schema_payload(
        model=model,
        messages=[{"role": "user", "content": "Synthetic unknown document"}],
        schema_model=ExtractionResult,
        schema_name="ExtractionResult",
        profile=profile,
    )
    assert "temperature" not in payload
    assert payload["max_tokens"] == profile.max_tokens
    assert "max_completion_tokens" not in payload
    assert payload["response_format"]["json_schema"][
        "schema"
    ] == openrouter._document_wire_schema(ExtractionResult.model_json_schema())


@pytest.mark.parametrize(
    "model,task",
    [
        ("x-ai/grok-4.3", "document_extraction"),
        ("google/gemini-3.8-flash", "interpretation"),
    ],
)
def test_gemini_document_projection_does_not_change_other_native_routes(model, task):
    from argus.domain.ingestion.documents.models import ExtractionResult

    profile = openrouter_profile_for_task(task)
    payload = openrouter._json_schema_payload(
        model=model,
        messages=[{"role": "user", "content": "Synthetic unknown document"}],
        schema_model=ExtractionResult,
        schema_name="ExtractionResult",
        profile=profile,
    )
    assert payload["temperature"] == profile.temperature
    assert (
        payload["response_format"]["json_schema"]["schema"]
        == ExtractionResult.model_json_schema()
    )
