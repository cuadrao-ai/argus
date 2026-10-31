"""Argus never converts between currencies: no plan offers a market test in
dollars, the interpreter never sends a rate to research, and a request to
convert gets one fixed reply."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from argus.agent_runtime import answer_calculation
from argus.agent_runtime import calculated_answer as ca
from argus.agent_runtime.capabilities.contract import build_default_capability_contract
from argus.agent_runtime.llm_interpreter import OpenRouterStructuredInterpreter
from argus.agent_runtime.research_query import ResearchQueryExtraction
from argus.agent_runtime.stages.interpret import interpret_stage_async
from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
from argus.agent_runtime.state.models import RunState, StrategySummary, UserState
from argus.domain.calculations.answer_request import AnswerCalculation

NO_CONVERSION_ES = (
    "No convierto entre monedas. Cada monto se queda en la moneda en que lo "
    "pagaste o lo cobraste."
)


def _read(**query: Any) -> StructuredInterpretation:
    return StructuredInterpretation(
        intent="conversation_followup",
        task_relation="new_task",
        user_goal_summary="money question",
        semantic_turn_act="educational_question",
        candidate_strategy_draft=StrategySummary(),
        research_query=ResearchQueryExtraction(**query),
    )


@pytest.mark.parametrize("currency", ["USD", "EUR", "DOP"])
def test_no_plan_offers_a_market_test_or_looks_up_a_rate(monkeypatch, currency) -> None:
    def no_lookup(symbol: str):
        raise AssertionError(f"looked up a close for {symbol}")

    monkeypatch.setattr(answer_calculation, "latest_market_close", no_lookup)
    voiced = ca.CalculatedVoicedAnswer(
        lead="In {{periods}} years it grows to **{{end_value}}**.",
        calculations=[
            AnswerCalculation.model_validate(
                {
                    "kind": "growth_projection",
                    "solve_for": "end_value",
                    "inputs": [
                        {
                            "name": "start_value",
                            "value": 10000,
                            "source": "user",
                            "currency": currency,
                        },
                        {"name": "annual_rate_pct", "value": 7, "source": "user"},
                        {"name": "periods", "value": 10, "source": "user"},
                        {"name": "periods_per_year", "value": 1, "source": "user"},
                    ],
                }
            )
        ],
    )
    monkeypatch.setattr(ca, "resolve_openrouter_api_key", lambda: "k")
    monkeypatch.setattr(ca, "openrouter_structured_model_candidates", lambda: ["model"])
    monkeypatch.setattr(ca, "invoke_openrouter_json_schema_sync", lambda **_: voiced)
    result = asyncio.run(
        ca.calculated_answer_stage_result(
            interpretation=_read(question_kind="none", scenario_question=True),
            state=RunState.new(
                current_user_message=f"What do 10,000 {currency} at 7% become in 10 years?",
                recent_thread_history=[],
            ),
            user=UserState(user_id="u1", language_preference="es-419", currency=currency),
        )
    )
    assert result is not None and result.outcome == "ready_to_respond"
    card = result.patch["final_response_payload"]["tool_result_cards"][0]
    assert card["outcome"]["status"] == "succeeded"
    assert not (result.patch.get("next_experiments") or {}).get("rows")
    assert not (result.patch.get("next_steps") or {}).get("items")


def test_the_interpreter_prompt_never_sends_a_rate_to_research() -> None:
    prompt = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )._system_prompt()
    assert "exchange rate" not in prompt.lower()
    assert "Argus never converts between currencies" in prompt
    assert "research_query.currency_conversion=true" in prompt


class _Interpreter:
    def __init__(self, read: StructuredInterpretation) -> None:
        self.read = read

    async def ainvoke(self, request):
        return self.read


def test_a_request_to_convert_gets_the_fixed_reply_and_its_offer(monkeypatch) -> None:
    monkeypatch.setattr(ca, "resolve_openrouter_api_key", lambda: None)
    reply = asyncio.run(
        interpret_stage_async(
            state=RunState.new(
                current_user_message="¿Cuánto son 50,000 pesos en dólares?",
                recent_thread_history=[],
            ),
            user=UserState(user_id="u1", language_preference="es-419", currency="DOP"),
            latest_task_snapshot=None,
            selected_thread_metadata={},
            structured_interpreter=_Interpreter(
                _read(question_kind="none", currency_conversion=True)
            ),
        )
    )
    assert reply.outcome == "ready_to_respond"
    text = reply.patch["assistant_response"]
    assert text.startswith(NO_CONVERSION_ES)
    assert "por moneda" in text and "una moneda a la vez" in text
    lowered = text.lower()
    for word in ("tasa", "cambio", "mercado", "dólar", "usd", "rate", "market"):
        assert word not in lowered
    assert not any(ch.isdigit() for ch in text)
    assert "final_response_payload" not in reply.patch
    assert "research" not in reply.patch
