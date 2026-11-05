"""Operational diagnostics must never retain private request/provider contents."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from argus.agent_runtime import answer_calculation as calculation
from argus.agent_runtime import knowledge_answer
from argus.agent_runtime import research_grounded as grounded
from argus.agent_runtime.interpreter import discovery_focused_read
from argus.agent_runtime.interpreter.research_routing import primary_research_query
from argus.agent_runtime.llm_interpreter import LLMInterpretationResponse
from argus.agent_runtime.research_query import ResearchQueryExtraction
from argus.agent_runtime.stages.interpret_types import (
    InterpretationRequest,
    StructuredInterpretation,
)
from argus.agent_runtime.state.models import RunState, StrategySummary, UserState
from argus.domain.calculations.answer_request import AnswerCalculation
from argus.domain.capability_registry import get_tool_catalog
from argus.domain.research.contracts import ResearchUnavailableError
from argus.llm import openrouter
from faker import Faker
from loguru import logger
from pydantic import BaseModel, ValidationError

fake = Faker()


@pytest.fixture
def private_text():
    return f"PRIVATE-{fake.uuid4()} {fake.sentence()}"


@pytest.fixture
def emitted():
    lines = []
    sink = logger.add(lines.append, serialize=True, level="DEBUG")
    try:
        yield lines
    finally:
        logger.remove(sink)


def assert_safe(lines, secret, diagnostic):
    assert lines
    rendered = "".join(lines)
    assert secret.split()[0] not in rendered
    assert "PRIVATE-" not in rendered
    assert diagnostic in rendered
    assert all(json.loads(line)["record"]["exception"] is None for line in lines)


class NumericResponse(BaseModel):
    value: int


@pytest.mark.parametrize("failure", ["validation", "provider"])
def test_openrouter_fallback_logs_safe_diagnostics(
    monkeypatch, emitted, private_text, failure
):
    monkeypatch.setattr(openrouter, "resolve_openrouter_api_key", lambda: "synthetic-key")
    monkeypatch.setattr(
        openrouter,
        "openrouter_structured_model_candidates",
        lambda *a, **k: ["test/first", "test/second"],
    )
    calls = []

    async def post(**kwargs):
        calls.append(kwargs["payload"])
        if len(calls) == 1 and failure == "provider":
            raise RuntimeError(private_text)
        content = {"value": private_text if len(calls) == 1 else 7}
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(content)}}]}
        )

    monkeypatch.setattr(openrouter, "_post_openrouter_json_schema", post)
    result = asyncio.run(
        openrouter.invoke_openrouter_json_schema(
            task="interpretation",
            messages=[{"role": "user", "content": private_text}],
            schema_model=NumericResponse,
            schema_name="numeric",
            model_name="test/first",
        )
    )
    assert result.value == 7
    assert len(calls) == 2
    assert_safe(
        emitted,
        private_text,
        "ValidationError" if failure == "validation" else "RuntimeError",
    )
    assert "error_origin=" in "".join(emitted)


def test_validation_locations_and_values_are_not_logged(emitted, private_text):
    class MappingResponse(BaseModel):
        values: dict[str, int]

    with pytest.raises(ValidationError) as caught:
        MappingResponse.model_validate({"values": {private_text: private_text}})
    openrouter.log_openrouter_failure(
        task="interpretation",
        model_name="test/model",
        exc=caught.value,
        message="Structured response failed",
    )
    assert_safe(emitted, private_text, "ValidationError")


@pytest.mark.parametrize("scenario_bit", [False, True])
def test_horizon_route_preserves_evidence_without_logging_it(
    emitted, private_text, scenario_bit
):
    query = ResearchQueryExtraction(
        question_kind="company_lookup", symbols=["AAPL"], scenario_question=scenario_bit
    )
    interpretation = StructuredInterpretation(
        intent="strategy_drafting",
        task_relation="new_task",
        user_goal_summary=private_text,
        semantic_turn_act="educational_question",
        research_query=query,
        candidate_strategy_draft=StrategySummary(
            asset_universe=["AAPL"],
            extra_parameters={
                "date_range_intent": {
                    "kind": "future_window",
                    "count": 10,
                    "unit": "year",
                    "anchor": "today",
                    "confidence": 0.9,
                    "evidence": private_text,
                },
            },
        ),
    )
    assert primary_research_query(interpretation) == query
    assert grounded.scenario_contract_applies(query, interpretation)
    assert (
        interpretation.candidate_strategy_draft.extra_parameters["date_range_intent"][
            "evidence"
        ]
        == private_text
    )
    assert_safe(emitted, private_text, "research_answers_future_horizon_question")
    if not scenario_bit:
        assert grounded.SCENARIO_FROM_HORIZON_REASON_CODE in interpretation.reason_codes


def test_unsourced_figures_emit_count_only(emitted, private_text):
    figure = fake.random_int(min=100000, max=999999)
    notes = []
    assert (
        calculation.record_unsourced_figures(
            f"Balance: {figure}.", cited=[], cards=[], notes=notes, message=private_text
        )
        == 1
    )
    assert notes == [calculation.UNSOURCED_FIGURE_REASON_CODE]
    assert_safe(emitted, private_text, "count=1")
    assert str(figure) not in "".join(emitted)


@pytest.mark.parametrize("field", ["kind", "solve_for", "input"])
def test_calculation_guards_do_not_log_model_supplied_context(
    emitted, private_text, field
):
    request = AnswerCalculation.model_validate(
        {
            "kind": private_text if field == "kind" else "time_value",
            "solve_for": private_text if field == "solve_for" else None,
            "inputs": [{"name": private_text, "value": 123, "source": "user"}]
            if field == "input"
            else [],
        }
    )
    notes = []
    calculation.resolve_calculation(
        request,
        catalog=get_tool_catalog(),
        retrieved=[],
        currency="USD",
        subject_symbol=None,
        market_close=lambda _: None,
        notes=notes,
    )
    assert notes
    assert_safe(emitted, private_text, notes[0])


@pytest.mark.parametrize("path", ["calculation", "research"])
def test_market_errors_omit_provider_detail(monkeypatch, emitted, private_text, path):
    def fail(*args, **kwargs):
        raise RuntimeError(private_text)

    monkeypatch.setattr("argus.domain.market_data.provider.fetch_price_series", fail)
    if path == "calculation":
        assert calculation.latest_market_close("AAPL") is None
    else:
        assert asyncio.run(grounded._latest_close("AAPL", "equity")) is None
    assert_safe(emitted, private_text, "RuntimeError")


def test_research_provider_failure_omits_detail(monkeypatch, emitted, private_text):
    from argus.domain.research.cache import cache_clear

    cache_clear()
    monkeypatch.setattr(grounded, "_client", lambda: object())

    async def fail(*args, **kwargs):
        raise ResearchUnavailableError("timeout", private_text, status=504)

    monkeypatch.setattr(grounded._TurnSpend, "run", fail)
    query = ResearchQueryExtraction(question_kind="company_lookup", symbols=["AAPL"])
    interpretation = StructuredInterpretation(
        intent="conversation_followup",
        task_relation="new_task",
        user_goal_summary=private_text,
        semantic_turn_act="educational_question",
        research_query=query,
    )
    result = asyncio.run(
        grounded.grounded_result(
            query=query,
            subjects=[],
            shape="fast",
            interpretation=interpretation,
            state=RunState.new(
                current_user_message=private_text, recent_thread_history=[]
            ),
            user=UserState(user_id=fake.uuid4()),
        )
    )
    assert result is not None
    assert_safe(emitted, private_text, "status=504")
    cache_clear()


@pytest.mark.parametrize("caller", ["discovery", "knowledge"])
@pytest.mark.parametrize("failure", ["provider", "validation"])
def test_debug_catchers_omit_exception_text_from_serialized_sink(
    monkeypatch, emitted, caller, failure
):
    secret = f"PRIVATE-{fake.hexify(text='^^^^^^^^')}"

    async def fail(**_kwargs: object) -> None:
        if failure == "provider":
            raise RuntimeError(secret)
        NumericResponse.model_validate({"value": secret})

    if caller == "discovery":
        monkeypatch.setattr(discovery_focused_read, "invoke_openrouter_json_schema", fail)
        result = asyncio.run(
            discovery_focused_read.focused_discovery_payload_response(
                response=LLMInterpretationResponse(
                    intent="conversation_followup",
                    task_relation="new_task",
                    user_goal_summary="find trending cryptos",
                    semantic_turn_act="educational_question",
                    research_query=ResearchQueryExtraction(question_kind="find_assets"),
                ),
                request=InterpretationRequest(
                    current_user_message="find me cryptos that are trending",
                    recent_thread_history=[],
                    latest_task_snapshot=None,
                    user=UserState(user_id=fake.uuid4()),
                ),
            )
        )
        label = "Focused discovery read failed"
    else:
        monkeypatch.setattr(knowledge_answer, "invoke_openrouter_json_schema", fail)
        result = asyncio.run(
            knowledge_answer._classify_question(
                message="what is a drawdown", language="en"
            )
        )
        label = "Knowledge route classification failed"

    assert result is None
    expected = "RuntimeError" if failure == "provider" else "ValidationError"
    assert_safe(emitted, secret, expected)
    rendered = "".join(emitted)
    assert label in rendered
    assert "error_origin=" in rendered


def test_malformed_research_response_does_not_log_exception_chain(emitted, private_text):
    from argus.domain.research.perplexity_agent import _packet_from_response

    from tests.research.conftest import agent_response

    document = agent_response()
    document["output"].append(
        {"type": "search_results", "results": [{"url": f"https://[{private_text}]/"}]}
    )
    with pytest.raises(ResearchUnavailableError) as caught:
        _packet_from_response(document, latency_ms=1)
    assert caught.value.reason == "malformed_response"
    assert caught.value.usage is not None
    assert_safe(emitted, private_text, "ValueError")
