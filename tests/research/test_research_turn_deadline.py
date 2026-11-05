"""The Q2 slow lookup leaves time for an answer, inside the real turn guard."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import httpx
import pytest
from argus.agent_runtime import (
    calculated_answer,
    llm_interpreter,
    research_grounded,
    turn_execution,
)
from argus.agent_runtime.capabilities.contract import build_default_capability_contract
from argus.agent_runtime.research_query import ResearchQueryExtraction
from argus.agent_runtime.stages.interpret import interpret_stage_async
from argus.agent_runtime.state.models import RunState, UserState
from argus.domain.calculations.answer_request import AnswerCalculation
from argus.domain.research.cache import cache_stats
from argus.domain.research.config import RESEARCH_CONFIG_SPECS
from argus.domain.research.contracts import ResearchPacket, ResearchUnavailableError
from argus.llm import openrouter
from argus.llm.openrouter import openrouter_task_timeout_seconds

from tests.research.conftest import educational_interpretation
from tests.research.test_research_claim_release import _Turn


@pytest.mark.asyncio
async def test_q2_slow_sync_lookup_answers_before_runtime_turn_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()
    completed = threading.Event()
    received_timeouts: list[float] = []
    fallback_remaining: list[float] = []
    admission = _Turn()
    deadline_seconds = 4.0
    monkeypatch.setenv("CUADRAO_TURN_DEADLINE_SECONDS", str(deadline_seconds))
    monkeypatch.delenv("CUADRAO_TURN_CALL_ALLOWANCE", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "stub")
    monkeypatch.setenv("CUADRAO_STRUCTURED_MODEL", "structured/primary")
    monkeypatch.setenv("CUADRAO_STRUCTURED_FALLBACK_MODEL", "structured/fallback")
    interpreter_posts: list[tuple[str, str, bool]] = []

    class SlowProvider:
        def run_research(self, _prompt: str, spec: Any) -> ResearchPacket:
            received_timeouts.append(spec.timeout_seconds)
            try:
                assert (
                    len(interpreter_posts) == turn_execution.DEFAULT_TURN_CALL_ALLOWANCE
                )
                assert release.wait(timeout=10), "test did not release provider"
                return ResearchPacket(answer_markdown="Late response")
            finally:
                completed.set()

    question = "¿Cuánto necesito ganar para comprarme un Porsche?"
    payment, ratio_pct = 2000, 20
    user = UserState(user_id="deadline-test", language_preference="es-419")
    voiced_inputs = [
        {"monthly_debt_payments": None, "ratio_pct": None},
        {"monthly_debt_payments": payment, "ratio_pct": ratio_pct},
    ]
    seen_messages: list[list[dict[str, str]]] = []

    def voice(payload: dict[str, Any]):
        execution = turn_execution.active_turn_execution()
        assert execution is not None
        fallback_remaining.append(execution.remaining_deadline_seconds())
        seen_messages.append(payload["messages"])
        return calculated_answer.CalculatedVoicedAnswer(
            lead=(
                "¿Qué pago mensual quieres comparar y qué porcentaje de tus ingresos representaría?"
                if len(voiced_inputs) == 2
                else "Con un pago de {{monthly_debt_payments}} al {{ratio_pct}}, los ingresos serían {{monthly_income}}."
            ),
            calculations=[
                AnswerCalculation.model_validate(
                    {
                        "kind": "debt_to_income",
                        "solve_for": "monthly_income",
                        "inputs": [
                            {"name": name, "value": value, "source": "user"}
                            for name, value in voiced_inputs.pop(0).items()
                        ],
                    }
                )
            ],
        )

    monkeypatch.setattr(research_grounded, "_client", SlowProvider)
    query = ResearchQueryExtraction(
        question_kind="current_external", scenario_question=True
    )
    interpretation = educational_interpretation().model_copy(
        update={"research_query": query}
    )

    raw_read = llm_interpreter.LLMInterpretationResponse(
        intent="conversation_followup",
        task_relation="new_task",
        semantic_turn_act="educational_question",
        user_goal_summary=question,
        research_query=query,
    )

    def response(url: str, content: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
            request=httpx.Request("POST", url),
        )

    class AsyncProvider:
        def __init__(self, **_: Any):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: Any):
            return None

        async def post(self, url: str, **kwargs: Any):
            payload = kwargs["json"]
            schema = payload["response_format"]["json_schema"]["name"]
            model = payload["model"]
            has_reasoning = "reasoning" in payload
            interpreter_posts.append((schema, model, has_reasoning))
            # Four preflight attempts, then three interpretation attempts:
            # ordinary compatibility retries and model fallback consume all seven.
            if has_reasoning and (
                schema == "LLMAssetMentionExtraction" or model == "structured/primary"
            ):
                return httpx.Response(
                    400,
                    json={"error": {"message": "reasoning unsupported"}},
                    request=httpx.Request("POST", url),
                )
            if model == "structured/primary":
                return response(url, "{}")
            if schema == "LLMAssetMentionExtraction":
                return response(
                    url,
                    json.dumps(
                        {"asset_mentions": [], "all_traded_asset_mentions_included": True}
                    ),
                )
            assert schema == "LLMInterpretationResponse"
            return response(url, raw_read.model_dump_json())

    class SyncProvider:
        def __init__(self, **_: Any):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_: Any):
            return None

        def post(self, url: str, **kwargs: Any):
            payload = kwargs["json"]
            assert (
                payload["response_format"]["json_schema"]["name"]
                == "CalculatedVoicedAnswer"
            )
            return response(url, voice(payload).model_dump_json())

    monkeypatch.setattr(openrouter.httpx, "AsyncClient", AsyncProvider)
    monkeypatch.setattr(openrouter.httpx, "Client", SyncProvider)
    interpreter = llm_interpreter.OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )

    async def runtime_events():
        result = await interpret_stage_async(
            state=RunState.new(current_user_message=question, recent_thread_history=[]),
            user=user,
            latest_task_snapshot=None,
            structured_interpreter=interpreter,
        )
        assert result is not None
        yield {"type": "final", "payload": result.stage_patch}

    try:
        with (
            admission.scope(),
            turn_execution.turn_execution_scope(entry_state={}) as execution,
        ):
            events = [
                event
                async for event in turn_execution.runtime_events_with_keepalive(
                    runtime_events(),
                    runtime_timeout_seconds=5,
                    runtime_keepalive_seconds=0.02,
                )
                if event is not None
            ]
        assert execution.calls_reserved == turn_execution.DEFAULT_TURN_CALL_ALLOWANCE
        assert len(events) == 1
        patch = events[0]["payload"]
        assert patch["assistant_prompt"] == calculated_answer.missing_inputs_lead(
            user.language_preference
        )
        assert patch["missing_required_fields"] == ["monthly_debt_payments", "ratio_pct"]
        assert patch["clarification"]["reason_code"] == "calculation_input_missing"
        assert "recovery" not in patch
        assert "final_response_payload" not in patch
        assert seen_messages[0][-1]["content"] == question
        assert (
            events[0]["payload"]["research"]["degraded"]["code"]
            == "research_unavailable_timeout"
        )
        assert len(fallback_remaining) == 1 and fallback_remaining[0] > 0
        assert len(received_timeouts) == 1 and 0 < received_timeouts[0] < deadline_seconds
        assert not completed.is_set(), "fallback must not wait for sync worker completion"
        assert admission.claims == 1 and admission.released == []
    finally:
        release.set()
        assert await asyncio.to_thread(completed.wait, 2)
    assert cache_stats()["entries"] == 0, "an abandoned response must never be shared"

    # Their reply computes the income through the real declaration, card, and prose.
    with turn_execution.turn_execution_scope(entry_state={}):
        followup = await calculated_answer.calculated_answer_stage_result(
            interpretation=interpretation.model_copy(
                update={
                    "research_query": ResearchQueryExtraction(
                        question_kind="none", scenario_question=True
                    )
                }
            ),
            state=RunState.new(
                current_user_message=f"Un pago mensual de {payment} al {ratio_pct}% de mis ingresos.",
                recent_thread_history=[],
            ),
            user=user,
            pending=patch["clarification"]["payload"],
        )
    assert followup is not None and followup.outcome == "ready_to_respond"
    card = followup.stage_patch["final_response_payload"]["tool_result_cards"][0]
    assert card["tool_name"] == "debt_to_income"
    assert card["outcome"]["status"] == "succeeded"
    assert card["presentation"]["answer"]["value"] == pytest.approx(
        payment / (ratio_pct / 100)
    )
    assert "{{" not in followup.stage_patch["assistant_response"]
    assert (
        "pending_strategy" not in patch and "pending_strategy" not in followup.stage_patch
    )
    assert len(received_timeouts) == 1


@pytest.mark.asyncio
async def test_research_attempts_share_remaining_budget_and_preserve_answer_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    monkeypatch.setattr(turn_execution, "_monotonic", lambda: now[0])
    monkeypatch.setenv("CUADRAO_TURN_DEADLINE_SECONDS", "180")
    received: list[float] = []
    answer_timeout = openrouter_task_timeout_seconds("knowledge_voicing")

    class Provider:
        def run_research(self, _prompt: str, spec: Any) -> ResearchPacket:
            received.append(spec.timeout_seconds)
            now[0] += 5
            return ResearchPacket(answer_markdown="Recorded answer")

    with turn_execution.turn_execution_scope(entry_state={}):
        now[0] = 140
        spend = research_grounded._TurnSpend()
        for _ in range(2):
            await spend.run(Provider(), "question", RESEARCH_CONFIG_SPECS["balanced"])
        assert received == pytest.approx([40 - answer_timeout, 35 - answer_timeout])
        now[0] = 180 - answer_timeout
        with pytest.raises(ResearchUnavailableError, match="timeout"):
            await spend.run(Provider(), "question", RESEARCH_CONFIG_SPECS["balanced"])
    assert len(received) == 2


@pytest.mark.asyncio
async def test_expired_research_budget_releases_an_unused_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain.research.admission import claim_current_research_attempt

    now = [0.0]
    monkeypatch.setattr(turn_execution, "_monotonic", lambda: now[0])
    monkeypatch.setenv("CUADRAO_TURN_DEADLINE_SECONDS", "180")
    admission = _Turn()
    calls: list[str] = []

    class Provider:
        def run_research(self, prompt: str, spec: Any) -> ResearchPacket:
            calls.append(prompt)
            return ResearchPacket(answer_markdown="Should not have run")

    with admission.scope(), turn_execution.turn_execution_scope(entry_state={}):
        spend = research_grounded._TurnSpend()
        claim_current_research_attempt()
        now[0] = 180
        with pytest.raises(ResearchUnavailableError, match="timeout"):
            await spend.run(Provider(), "question", RESEARCH_CONFIG_SPECS["balanced"])
    assert calls == []
    assert admission.released == [admission.admission]
