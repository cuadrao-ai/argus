"""A choice that turns on a future figure nobody can cite is answered with the
recent past: the research instructions ask for it, and an answer that follows
them publishes Argus's computation over cited, dated figures as history. A
forward-valuation question never carries that line and keeps its computed
scenarios (decision 10)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from argus.agent_runtime import research_answer as ra
from argus.agent_runtime import research_calculation
from argus.agent_runtime import research_grounded as grounded
from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
from argus.agent_runtime.state.models import RunState, StrategySummary, UserState
from argus.domain.research.config import (
    RETRIEVAL_INSTRUCTIONS,
    SCENARIO_RETRIEVAL_INSTRUCTIONS,
)
from argus.domain.research.perplexity_agent import PerplexityAgentClient

from tests.research.conftest import (
    RecordingTransport,
    agent_response,
    set_research_query,
    typed_answer_text,
)

HISTORY_LINE = (
    "When a choice turns on a future figure nobody can cite, such as an exchange "
    "rate or a price, do not project it; show what the recent past did with cited "
    "figures, computed by Argus and labeled as history, not a forecast."
)
READER = UserState(
    user_id="research-do", language_preference="es-419", country="DO", currency="DOP"
)
YEAR_AGO = "https://www.example.com.do/tasas/2025-09-10"
TODAY = "https://www.example.com.do/tasas/2026-09-10"
QUESTION = "¿Guardo mis ahorros en pesos o en euros?"
PROSE = (
    "Nadie puede citar el tipo de cambio del próximo año. **Como historia, no como "
    "pronóstico:** el euro pasó de {{start_value}} a {{end_value}} en un año, un "
    "cambio de {{annual_rate_pct}}."
)


def _history() -> dict[str, Any]:
    """The past year of a rate from two dated pages, its change left to Argus."""
    return {
        "name": "euro_last_year",
        "kind": "growth_projection",
        "solve_for": "annual_rate_pct",
        "inputs": [
            {
                "name": "start_value",
                "value": 64.10,
                "source": "page",
                "source_url": YEAR_AGO,
                "as_of": "2025-09-10",
                "currency": "DOP",
            },
            {
                "name": "end_value",
                "value": 68.90,
                "source": "page",
                "source_url": TODAY,
                "as_of": "2026-09-10",
                "currency": "DOP",
            },
            {"name": "periods", "value": 1, "source": "assumption"},
            {"name": "periods_per_year", "value": 1, "source": "assumption"},
        ],
    }


def _interpretation() -> StructuredInterpretation:
    return StructuredInterpretation(
        intent="conversation_followup",
        task_relation="new_task",
        user_goal_summary="currency choice",
        semantic_turn_act="educational_question",
        candidate_strategy_draft=StrategySummary(),
    )


def test_only_answers_that_are_not_scenarios_ask_for_the_recent_past() -> None:
    assert RETRIEVAL_INSTRUCTIONS.count(HISTORY_LINE) == 1
    assert SCENARIO_RETRIEVAL_INSTRUCTIONS.count(HISTORY_LINE) == 0


def test_a_choice_on_a_rate_nobody_can_cite_publishes_the_past_year_argus_computed(
    monkeypatch,
) -> None:
    set_research_query(monkeypatch, globals(), question_kind="concept", symbols=[])
    transport = RecordingTransport(
        [
            agent_response(
                text=typed_answer_text(
                    PROSE, [], _history(), source_urls=[YEAR_AGO, TODAY]
                ),
                sources=[YEAR_AGO, TODAY],
                tickers=[],
            )
        ]
    )
    monkeypatch.setattr(
        grounded, "_client", lambda: PerplexityAgentClient("k", transport=transport)
    )

    result = asyncio.run(
        ra.research_answer_stage_result(
            interpretation=_interpretation(),
            state=RunState.new(current_user_message=QUESTION, recent_thread_history=[]),
            user=READER,
        )
    )

    assert result is not None
    sent = json.loads(transport.requests[0].content.decode())
    assert sent["instructions"] == RETRIEVAL_INSTRUCTIONS
    card = result.stage_patch["final_response_payload"]["tool_result_cards"][0]
    assert card["tool_name"] == "growth_projection"
    assert card["outcome"]["status"] == "succeeded"
    sources = card["arguments"]["sources"]
    assert (sources["start_value"]["url"], sources["start_value"]["date"]) == (
        YEAR_AGO,
        "2025-09-10",
    )
    assert (sources["end_value"]["url"], sources["end_value"]["date"]) == (
        TODAY,
        "2026-09-10",
    )
    assert card["presentation"]["answer"]["value"] == pytest.approx(
        (68.90 / 64.10 - 1) * 100, rel=1e-3
    )
    answer = result.stage_patch["assistant_response"]
    assert "Como historia, no como pronóstico" in answer
    assert "{{" not in answer
    assert "degraded" not in result.stage_patch["research"]


OUTLOOK_PAGE = "https://www.reuters.com/markets/nvidia-outlook/"


def _valuation() -> dict[str, Any]:
    """A forward valuation: today's price from market data, the per-share figure
    and growth forecast from the page the answer read, the user's amount and
    horizon."""
    return {
        "kind": "valuation_scenarios",
        "solve_for": None,
        "inputs": [
            {"name": "symbol", "value": "NVDA", "source": "user"},
            {"name": "price", "value": None, "source": "market_data"},
            {
                "name": "per_share",
                "value": 4.5,
                "source": "page",
                "source_url": OUTLOOK_PAGE,
                "as_of": "2026-09-03",
                "currency": "USD",
            },
            {
                "name": "growth_base_pct",
                "value": 25.0,
                "source": "page",
                "source_url": OUTLOOK_PAGE,
                "as_of": "2026-09-03",
            },
            {"name": "amount", "value": 10000, "source": "user", "currency": "USD"},
            {"name": "horizon_years", "value": 10, "source": "user"},
        ],
    }


def test_a_forward_valuation_keeps_its_scenarios_without_the_history_line(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        research_calculation, "latest_market_close", lambda symbol: (218.36, "2026-09-10")
    )
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NVDA"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    transport = RecordingTransport(
        [
            agent_response(
                text=typed_answer_text(
                    "NVIDIA trades at {{price}}; consensus growth is {{growth_base_pct}} a year.",
                    [],
                    _valuation(),
                ),
                sources=[OUTLOOK_PAGE],
                tickers=["NVDA"],
            )
        ]
    )
    monkeypatch.setattr(
        grounded, "_client", lambda: PerplexityAgentClient("k", transport=transport)
    )

    result = asyncio.run(
        ra.research_answer_stage_result(
            interpretation=_interpretation(),
            state=RunState.new(
                current_user_message="what will $10,000 in NVDA be worth in ten years?",
                recent_thread_history=[],
            ),
            user=UserState(user_id="research-user", language_preference="en"),
        )
    )

    assert result is not None
    sent = json.loads(transport.requests[0].content.decode())
    assert sent["instructions"] == SCENARIO_RETRIEVAL_INSTRUCTIONS
    assert HISTORY_LINE not in sent["instructions"]
    card = result.stage_patch["final_response_payload"]["tool_result_cards"][0]
    assert card["tool_name"] == "valuation_scenarios"
    assert card["outcome"]["status"] == "succeeded"
    rows = {fact["name"]: fact for fact in card["presentation"]["rows"]}
    assert rows["price_at_horizon_base"]["value"] > 218.36
    assert rows["price_at_horizon_base"]["source"] == {"kind": "computed"}
    assert "degraded" not in result.stage_patch["research"]
