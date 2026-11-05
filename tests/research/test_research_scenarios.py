"""Decision 10: forward-looking and valuation questions answered as scenarios.

Router and composition locks for the scenario contract: the typed signal
selects the scenario instructions and the balanced shape on every kind, the
answer publishes only on cited inputs on the inline, background and repeated-turn
paths, a claim about crypto is grounded on public pages, and a failed
scenario is recorded under the shape it was selected for.
"""

from __future__ import annotations

import asyncio

import pytest
from argus.agent_runtime import research_answer as ra
from argus.agent_runtime import research_calculation
from argus.agent_runtime import research_grounded as grounded
from argus.agent_runtime.answer_calculation import figure_text
from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
from argus.agent_runtime.state.models import RunState, StrategySummary, UserState
from argus.domain.research.config import RESEARCH_CONFIG_SPECS
from argus.domain.research.perplexity_agent import PerplexityAgentClient
from argus.domain.tool_contracts import ToolFact

from tests.research.conftest import (
    RecordingTransport,
    agent_response,
    set_research_query,
    typed_answer_text,
)

USER = UserState(user_id="research-user", language_preference="en")


def _interpretation() -> StructuredInterpretation:
    return StructuredInterpretation(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        user_goal_summary="question",
        semantic_turn_act="educational_question",
        requires_clarification=False,
        candidate_strategy_draft=StrategySummary(),
    )


def _state(message: str) -> RunState:
    return RunState.new(current_user_message=message, recent_thread_history=[])


def _wire_client(monkeypatch: pytest.MonkeyPatch, documents) -> RecordingTransport:
    transport = RecordingTransport(documents)
    monkeypatch.setattr(
        grounded, "_client", lambda: PerplexityAgentClient("k", transport=transport)
    )
    return transport


def _run(message: str, *, user=USER):
    return asyncio.run(
        ra.research_answer_stage_result(
            interpretation=_interpretation(),
            state=_state(message),
            user=user,
        )
    )


OUTLOOK_PAGE = "https://www.reuters.com/markets/nvidia-outlook/"


@pytest.fixture(autouse=True)
def _market_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """Argus's own market data supplies the current price in every scenario."""
    monkeypatch.setattr(
        research_calculation, "latest_market_close", lambda symbol: (218.36, "2026-09-10")
    )


def _scenario_calculation(*, cited: bool, page: str = OUTLOOK_PAGE) -> dict:
    """The answer's calculation: the price from market data, the per-share figure
    and growth forecast from the retrieved page when ``cited``, otherwise from a
    page this answer never read, and the user's amount and horizon."""
    source_url = page if cited else "https://example.com/not-retrieved"
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
                "source_url": source_url,
                "as_of": "2026-09-03",
                "currency": "USD",
            },
            {
                "name": "growth_base_pct",
                "value": 25.0,
                "source": "page",
                "source_url": source_url,
                "as_of": "2026-09-03",
            },
            {"name": "amount", "value": 10000, "source": "user", "currency": "USD"},
            {"name": "horizon_years", "value": 10, "source": "user"},
        ],
    }


def _scenario_card(result) -> dict:
    cards = result.stage_patch["final_response_payload"]["tool_result_cards"]
    assert len(cards) == 1
    return cards[0]


def _run_scenario(monkeypatch, *, cited: bool, source_urls: list[str] | None = None):
    from tests.research.conftest import typed_answer_text

    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NVDA"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    "NVIDIA trades at {{price}}; consensus growth is {{growth_base_pct}} a year.",
                    [],
                    _scenario_calculation(cited=cited),
                    source_urls=source_urls,
                ),
                sources=["https://www.reuters.com/markets/nvidia-outlook/"],
                tickers=["NVDA"],
            )
        ],
    )
    return _run("what will $10,000 in NVDA be worth in ten years?")


def test_a_scenario_publishes_its_calculation_and_argus_computes_it(
    monkeypatch,
) -> None:
    """The answer returns its calculation with each input's source; the
    valuation math computes the scenario figures, the prose states them from
    the card, and the card carries each input's true source."""
    result = _run_scenario(monkeypatch, cited=True)
    assert result is not None
    sidecar = result.stage_patch["research"]
    assert "degraded" not in sidecar
    answer = result.stage_patch["assistant_response"]
    assert "{{" not in answer
    card = _scenario_card(result)
    assert figure_text(ToolFact.model_validate(card["presentation"]["answer"])) in answer
    assert card["tool_name"] == "valuation_scenarios"
    assert card["outcome"]["status"] == "succeeded"
    assert card["arguments"]["price"] == 218.36
    assert card["arguments"]["growth_base_pct"] == 25.0
    assert card["arguments"]["symbol"] == "NVDA"
    growth = card["arguments"]["sources"]["growth_base_pct"]
    assert (growth["kind"], growth["url"], growth["date"]) == (
        "page",
        OUTLOOK_PAGE,
        "2026-09-03",
    )
    assert card["arguments"]["sources"]["price"] == {
        "kind": "market_data",
        "date": "2026-09-10",
    }
    rows = {fact["name"]: fact for fact in card["presentation"]["rows"]}
    assert rows["price_at_horizon_base"]["value"] > 218.36
    assert rows["price_at_horizon_base"]["source"] == {"kind": "computed"}
    assert (
        result.stage_patch["tool_call_records"][0]["tool_name"] == "valuation_scenarios"
    )


def test_a_scenario_citing_pages_it_never_read_renders_no_blank_card(
    monkeypatch,
) -> None:
    """Decision 10: the arithmetic is only as grounded as its inputs. A page
    the answer never retrieved feeds nothing, so the calculation is not
    computed and no card with blank inputs renders; without a model to answer
    from market data and assumptions, the honest note says what happened."""
    result = _run_scenario(monkeypatch, cited=False, source_urls=[OUTLOOK_PAGE])
    assert result is not None
    sidecar = result.stage_patch["research"]
    assert "degraded" not in sidecar
    assert "couldn't look up every figure" in result.stage_patch["assistant_response"]
    # The subject the user named stays testable.
    assert result.stage_patch["next_experiments"]["rows"]
    assert "final_response_payload" not in result.stage_patch


def test_the_background_scenario_preserves_research_without_a_calculation() -> None:
    from argus.domain.research.contracts import (
        ResearchPacket,
        ResearchSource,
        ResearchUsage,
    )

    packet = ResearchPacket(
        answer_markdown="Bear to bull ranges written from memory.",
        sources=(ResearchSource(url="https://www.reuters.com/markets/nvidia-outlook/"),),
        usage=ResearchUsage(web_search_invocations=1),
    )
    job_request = {
        "capability_class": "thorough_research",
        "language": "en",
        "question_kind": "cross_company",
        "scenario_question": True,
        "requires_publisher_sources": True,
        "subjects": [{"symbol": "NVDA", "name": "NVIDIA", "asset_class": "equity"}],
    }
    composed = grounded.compose_completed_research(job_request=job_request, packet=packet)
    assert "degraded" not in composed["research"]
    assert packet.answer_markdown in composed["answer"]


def test_a_comparison_scenario_preserves_research_on_an_uncached_repeat(
    monkeypatch,
) -> None:
    """A scenario computes from retrieved inputs on the balanced path, so a
    named comparison asked as a scenario never takes the thorough job. A
    repeat retrieves its own answer and preserves its research prose even
    when the calculation inputs are unusable."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="cross_company",
        symbols=["NVDA", "AMD"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    "NVDA ranges written from memory.",
                    [],
                    _scenario_calculation(cited=False),
                    source_urls=[OUTLOOK_PAGE],
                ),
                sources=["https://www.reuters.com/markets/nvidia-outlook/"],
                tickers=["NVDA", "AMD"],
            )
        ]
        * 2,
    )

    first = _run("Which of NVDA or AMD will be worth more in ten years?")
    assert first is not None
    assert "research_job_request" not in first.stage_patch
    assert "degraded" not in first.stage_patch["research"]
    assert "calculation_inputs_not_found" in first.decision.reason_codes
    assert len(transport.requests) == 1

    repeat = _run("Which of NVDA or AMD will be worth more in ten years?")
    assert repeat is not None
    assert len(transport.requests) == 2, "the repeated scenario retrieves fresh inputs"
    sidecar = repeat.stage_patch["research"]
    assert sidecar["usage"]["cache_status"] == "miss"
    assert "degraded" not in sidecar
    assert "written from memory" in repeat.stage_patch["assistant_response"]
    assert "calculation_inputs_not_found" in repeat.decision.reason_codes
    assert "final_response_payload" not in repeat.stage_patch


def test_a_typed_horizon_alone_selects_the_scenario_contract(monkeypatch) -> None:
    """The interpreter typed the future horizon on the draft but left the
    scenario bit unset: the scenario contract still applies, so the request
    carries the scenario instructions and the answer needs a cited input."""
    from argus.domain.research.config import SCENARIO_RETRIEVAL_INSTRUCTIONS

    from tests.research.conftest import typed_answer_text

    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NVDA"],
        period_of_interest="ten years",
    )
    original = globals()["_interpretation"]

    def with_horizon(*args, **kwargs):
        read = original(*args, **kwargs)
        return read.model_copy(
            update={
                "candidate_strategy_draft": StrategySummary(
                    extra_parameters={
                        "date_range_intent": {
                            "kind": "future_window",
                            "count": 10,
                            "unit": "year",
                            "anchor": "today",
                            "confidence": 0.9,
                            "evidence": "in ten years",
                        }
                    }
                )
            }
        )

    monkeypatch.setitem(globals(), "_interpretation", with_horizon)
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    "A range written from memory.",
                    [],
                    _scenario_calculation(cited=False),
                    source_urls=[OUTLOOK_PAGE],
                ),
                sources=["https://www.reuters.com/markets/nvidia-outlook/"],
                tickers=["NVDA"],
            )
        ],
    )

    result = _run("what will $10,000 in NVDA be worth in ten years?")

    assert result is not None
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert body["instructions"] == SCENARIO_RETRIEVAL_INSTRUCTIONS
    assert "degraded" not in result.stage_patch["research"]
    assert "calculation_inputs_not_found" in result.decision.reason_codes
    # The compensation reaches the persisted turn through the decision.
    from argus.agent_runtime.research_grounded import SCENARIO_FROM_HORIZON_REASON_CODE

    assert SCENARIO_FROM_HORIZON_REASON_CODE in result.decision.reason_codes


def test_a_crypto_scenario_typed_only_by_its_horizon_is_grounded(monkeypatch) -> None:
    """The off-coverage branch reads the shared scenario owner: a crypto
    comparison with a typed future horizon and no scenario bit is grounded on
    public pages under the scenario contract, never answered with closes."""
    from argus.domain.research.config import SCENARIO_RETRIEVAL_INSTRUCTIONS

    from tests.research.conftest import typed_answer_text

    set_research_query(
        monkeypatch,
        globals(),
        question_kind="cross_company",
        symbols=["BTC", "ETH"],
        asset_class_hint="crypto",
        period_of_interest="ten years",
    )
    original = globals()["_interpretation"]

    def with_horizon(*args, **kwargs):
        return original(*args, **kwargs).model_copy(
            update={
                "candidate_strategy_draft": StrategySummary(
                    extra_parameters={
                        "date_range_intent": {
                            "kind": "future_window",
                            "count": 10,
                            "unit": "year",
                            "anchor": "today",
                            "confidence": 0.9,
                            "evidence": "in ten years",
                        }
                    }
                )
            }
        )

    monkeypatch.setitem(globals(), "_interpretation", with_horizon)
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    "Bear to bull ranges.", [], _scenario_calculation(cited=True)
                ),
                sources=["https://www.reuters.com/markets/nvidia-outlook/"],
                tickers=["BTC"],
            )
        ],
    )

    result = _run("Which of BTC or ETH will be worth more in ten years?")

    assert result is not None
    assert len(transport.requests) == 1
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert body["instructions"] == SCENARIO_RETRIEVAL_INSTRUCTIONS
    assert "finance_search" not in [tool["type"] for tool in body["tools"]]
    assert result.stage_patch["research"].get("degraded") != {
        "code": "asset_class_not_covered"
    }


def test_a_failed_scenario_records_the_shape_it_was_selected_for(monkeypatch) -> None:
    """A crypto scenario forced onto the balanced shape that then fails on the
    provider is recorded as the balanced lookup it attempted, not as the
    thorough research its question kind would map to."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="cross_company",
        symbols=["BTC", "ETH"],
        asset_class_hint="crypto",
        period_of_interest="ten years",
        scenario_question=True,
    )
    _wire_client(monkeypatch, [])  # the transport answers 500 to every call

    result = _run("Which of BTC or ETH will be worth more in ten years?")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"]["code"].startswith("research_unavailable_")
    assert sidecar["shape"] == "balanced"
    assert sidecar["capability_class"] == "balanced_lookup"


def test_a_scenario_typed_as_market_stats_is_grounded_not_voiced_from_history(
    monkeypatch,
) -> None:
    """A forward question the interpreter typed as market_stats still takes the
    scenario contract: the legacy statistics path would default the future
    window to the past year and voice history as the answer."""
    from argus.domain.research.config import SCENARIO_RETRIEVAL_INSTRUCTIONS

    from tests.research.conftest import typed_answer_text

    set_research_query(
        monkeypatch,
        globals(),
        question_kind="market_stats",
        symbols=["NVDA"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    "Bear to bull ranges.", [], _scenario_calculation(cited=True)
                ),
                sources=["https://www.reuters.com/markets/nvidia-outlook/"],
                tickers=["NVDA"],
            )
        ],
    )

    result = _run("what return will NVDA have in ten years?")

    assert result is not None
    assert len(transport.requests) == 1, "the scenario must reach the provider"
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert body["instructions"] == SCENARIO_RETRIEVAL_INSTRUCTIONS
    assert result.stage_patch["research"]["shape"] == "balanced"
    assert (
        figure_text(
            ToolFact.model_validate(_scenario_card(result)["presentation"]["answer"])
        )
        in result.stage_patch["assistant_response"]
    )


def test_a_scenario_about_named_subjects_is_a_fact_question_whatever_its_kind(
    monkeypatch,
) -> None:
    """The scenario bit on a read left at kind none still reaches the
    scenario owner when it names its subjects; without subjects it is a
    projection on the user's own numbers and stays arithmetic."""
    from argus.domain.research.config import SCENARIO_RETRIEVAL_INSTRUCTIONS

    from tests.research.conftest import typed_answer_text

    set_research_query(
        monkeypatch,
        globals(),
        question_kind="none",
        symbols=["NVDA"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    "Bear to bull ranges.", [], _scenario_calculation(cited=True)
                ),
                sources=["https://www.reuters.com/markets/nvidia-outlook/"],
                tickers=["NVDA"],
            )
        ],
    )

    result = _run("what will $10,000 in NVDA be worth in ten years?")

    assert result is not None
    assert len(transport.requests) == 1
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert body["instructions"] == SCENARIO_RETRIEVAL_INSTRUCTIONS
    assert result.stage_patch["research"]["shape"] == "balanced"

    set_research_query(
        monkeypatch, globals(), question_kind="none", symbols=[], scenario_question=True
    )
    assert _run("If I save $500 a month at 5%, how much will I have in 20 years?") is None


def test_a_scenario_question_sends_the_scenario_contract(monkeypatch) -> None:
    """Decision 10: the typed scenario signal swaps the provider instructions
    for the variant that lets computed figures through; a plain company read
    keeps the recorded contract."""
    from argus.domain.research.config import (
        RETRIEVAL_INSTRUCTIONS,
        SCENARIO_RETRIEVAL_INSTRUCTIONS,
    )

    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NVDA"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text="Bear $2,300 to $5,500; base $29,000 to $38,000; bull higher.",
                sources=["https://www.reuters.com/markets/nvidia-outlook/"],
                tickers=["NVDA"],
            )
        ],
    )

    result = _run("what will $10,000 in NVDA be worth in ten years?")

    assert result is not None
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert body["instructions"] == SCENARIO_RETRIEVAL_INSTRUCTIONS
    assert "Argus computes the answer from the calculation you return" in body["input"]
    assert "calculations" in body["response_format"]["json_schema"]["schema"]["required"]
    assert body["instructions"] != RETRIEVAL_INSTRUCTIONS


def test_a_crypto_claim_is_grounded_on_public_pages_without_the_finance_tool(
    monkeypatch,
) -> None:
    """Decision 10: a forecast about Bitcoin is a claim, not a figure Argus's
    own data can answer, so it is grounded on publishers with the finance tool
    (which never covered crypto) left out of the request."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["BTC"],
        asset_class_hint="crypto",
        requires_publisher_sources=True,
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text="Analyst targets for Bitcoin range widely; base case shown.",
                sources=["https://www.reuters.com/markets/bitcoin-outlook/"],
                tickers=["BTC"],
            )
        ],
    )

    result = _run("How has Bitcoin's adoption changed over the last year?")

    assert result is not None
    assert len(transport.requests) == 1
    body = __import__("json").loads(transport.requests[0].content.decode())
    tools = [tool["type"] for tool in body["tools"]]
    assert "finance_search" not in tools
    assert "web_search" in tools
    assert body["max_steps"] == RESEARCH_CONFIG_SPECS["balanced"].max_steps
    sidecar = result.stage_patch["research"]
    assert sidecar.get("degraded") != {"code": "asset_class_not_covered"}
    assert sidecar["capability_class"] == "balanced_lookup"


def test_a_scenario_typed_as_a_survey_is_not_handled_as_one(monkeypatch) -> None:
    """A scenario typed as a survey kind gets no survey guidance, no screening
    class and no verified-ticker withhold: the stale kind reclassifies nothing
    downstream of the scenario owner."""
    from argus.domain.research.config import SCENARIO_RETRIEVAL_INSTRUCTIONS

    from tests.research.conftest import typed_answer_text

    set_research_query(
        monkeypatch,
        globals(),
        question_kind="sector_radar",
        symbols=["NVDA"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    "Bear to bull ranges with no ticker named in the prose.",
                    [],
                    _scenario_calculation(cited=True),
                ),
                sources=["https://www.reuters.com/markets/nvidia-outlook/"],
                tickers=["NVDA"],
            )
        ],
    )

    result = _run("what will $10,000 in NVDA be worth in ten years?")

    assert result is not None
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert body["instructions"] == SCENARIO_RETRIEVAL_INSTRUCTIONS
    assert "Retrieve these figures from current market data" not in body["input"]
    sidecar = result.stage_patch["research"]
    assert sidecar["capability_class"] == "balanced_lookup"
    assert "degraded" not in sidecar
    assert (
        figure_text(
            ToolFact.model_validate(_scenario_card(result)["presentation"]["answer"])
        )
        in result.stage_patch["assistant_response"]
    )


def test_a_subjectless_scenario_reaches_research_only_when_a_page_supplies_a_figure(
    monkeypatch,
) -> None:
    """A scenario with no subject typed with nothing to look up is the user's
    own numbers: the no-search answer computes it and no retrieval runs. Typed
    with a kind that names a published figure, it is a research question."""
    message = "If I save $500 a month at 5%, how much will I have in 20 years?"
    set_research_query(
        monkeypatch, globals(), question_kind="none", symbols=[], scenario_question=True
    )
    transport = _wire_client(monkeypatch, [agent_response()])
    assert _run(message) is None
    assert transport.requests == []

    set_research_query(
        monkeypatch,
        globals(),
        question_kind="market_stats",
        symbols=[],
        scenario_question=True,
    )
    transport = _wire_client(monkeypatch, [agent_response()])
    assert _run(message) is not None
    # Reached research: the scenario's publisher retry may follow the first ask.
    assert transport.requests


def test_a_failed_survey_typed_scenario_is_not_filed_as_screening(monkeypatch) -> None:
    """The derived survey fact reaches the failure paths too: a scenario
    typed as a survey kind whose provider fails is recorded as the balanced
    lookup it attempted, never as screening."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="screening",
        symbols=["NVDA"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    _wire_client(monkeypatch, [])  # the transport answers 500 to every call

    result = _run("what will $10,000 in NVDA be worth in ten years?")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"]["code"].startswith("research_unavailable_")
    assert sidecar["shape"] == "balanced"
    assert sidecar["capability_class"] == "balanced_lookup"


def test_a_discovery_act_with_a_named_scenario_is_dispatched_not_found(
    monkeypatch,
) -> None:
    """The discovery entry reads the scenario owner before its kind diversion:
    a discovery act carrying a screening-typed scenario about a named subject
    is a scenario, never the find operation."""
    from argus.domain.research.config import SCENARIO_RETRIEVAL_INSTRUCTIONS

    from tests.research.conftest import typed_answer_text

    set_research_query(
        monkeypatch,
        globals(),
        question_kind="screening",
        symbols=["NVDA"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    "Bear to bull ranges.", [], _scenario_calculation(cited=True)
                ),
                sources=["https://www.reuters.com/markets/nvidia-outlook/"],
                tickers=["NVDA"],
            )
        ],
    )
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    interpretation = _interpretation().model_copy(
        update={"semantic_turn_act": "asset_discovery"}
    )
    decision = grounded.research_decision(interpretation, USER, "test").model_copy(
        update={"semantic_turn_act": "asset_discovery"}
    )

    result = asyncio.run(
        ra.discovery_turn_stage_result(
            interpretation=interpretation,
            decision=decision,
            state=_state("what will $10,000 in NVDA be worth in ten years?"),
            user=USER,
        )
    )

    assert result is not None
    assert len(transport.requests) == 1
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert body["instructions"] == SCENARIO_RETRIEVAL_INSTRUCTIONS
    assert result.stage_patch["research"]["shape"] == "balanced"


def _dated_scenario_document(page: str, page_date: str) -> dict:
    """A typed scenario answer whose only public page carries an explicit
    date, with the inputs rowed to that page."""
    from tests.research.conftest import (
        retrieved_row,
        search_results_item,
        typed_answer_text,
    )

    rows = [
        retrieved_row(
            subject="NVIDIA",
            symbol="NVDA",
            label="average twelve-month analyst price target",
            value=327.18,
            kind="currency",
            unit="USD",
            source_url=page,
        )
    ]
    document = agent_response(
        text=typed_answer_text(
            "Bear to bull ranges.", rows, _scenario_calculation(cited=True, page=page)
        ),
        tickers=["NVDA"],
        web_search_invocations=1,
    )
    document["output"].insert(
        1, search_results_item({"url": page, "title": "NVDA outlook", "date": page_date})
    )
    return document


def test_a_survey_typed_scenario_keeps_a_dated_analyst_page(monkeypatch) -> None:
    """Source freshness reads the derived survey fact. The only public page is
    dated before the question day: a scenario typed as market_pulse keeps it
    and publishes, while the same document under a genuine market_pulse
    survey drops it under the survey's same-day bound."""
    old_page = "https://www.reuters.com/markets/nvidia-outlook/"
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="market_pulse",
        symbols=["NVDA"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    _wire_client(monkeypatch, [_dated_scenario_document(old_page, "2026-09-04")])

    scenario = _run("what will $10,000 in NVDA be worth in ten years?")

    assert scenario is not None
    sidecar = scenario.stage_patch["research"]
    assert "degraded" not in sidecar
    assert [source["url"] for source in sidecar["sources"]] == [old_page]

    set_research_query(
        monkeypatch, globals(), question_kind="market_pulse", symbols=["NVDA"]
    )
    _wire_client(monkeypatch, [_dated_scenario_document(old_page, "2026-09-04")])

    survey = _run("what is moving in the market today?")

    assert survey is not None
    assert survey.stage_patch["research"]["sources"] == []


def test_a_scenario_with_the_users_amount_offers_that_amount_in_the_asset_first(
    monkeypatch,
) -> None:
    """The counterfactual goes through the one owner of rows after an answer:
    what the user's own amount did in the same asset over the same years,
    offered first and never run."""
    from argus.agent_runtime.calculation_rows import MARKET_COUNTERFACTUAL_KIND

    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NVDA"],
        period_of_interest="ten years",
        scenario_question=True,
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    "NVIDIA trades at {{price}}; consensus growth is {{growth_base_pct}} a year.",
                    [],
                    _scenario_calculation(cited=True),
                ),
                sources=["https://www.reuters.com/markets/nvidia-outlook/"],
                tickers=["NVDA"],
            )
        ],
    )
    result = _run("what will $10,000 in NVDA be worth in ten years?")
    assert result is not None
    assert len(transport.requests) == 1
    card = _scenario_card(result)
    assert card["arguments"]["amount"] == 10000
    rows = result.stage_patch["next_experiments"]["rows"]
    assert rows[0]["kind"] == MARKET_COUNTERFACTUAL_KIND
    assert rows[0]["send_text"] == (
        "Test buying and holding NVDA with 10000 USD over the last 10 years"
    )
    assert len(rows) <= 3
    assert result.stage_patch["next_steps"]["items"][0] == {
        "type": "test",
        "kind": MARKET_COUNTERFACTUAL_KIND,
    }
    assert [
        record["tool_name"] for record in result.stage_patch["tool_call_records"]
    ] == ["valuation_scenarios"]


def test_a_background_answer_that_needs_a_figure_the_kind_requires_offers_the_calculation() -> (
    None
):
    from argus.agent_runtime.calculated_answer import CALCULATION_OFFER_KEY
    from argus.domain.research.contracts import (
        ResearchPacket,
        ResearchSource,
        ResearchUsage,
    )

    calculation = _scenario_calculation(cited=True)
    # Earnings per share is a figure the valuation needs; an optional invested
    # amount left blank would keep its default and compute instead.
    calculation["inputs"] = [
        {"name": "per_share", "value": None, "source": "user"}
        if item["name"] == "per_share"
        else item
        for item in calculation["inputs"]
    ]
    prose = "What an investment in NVIDIA becomes depends on its earnings growth."
    packet = ResearchPacket(
        answer_markdown=prose,
        sources=(ResearchSource(url=OUTLOOK_PAGE),),
        usage=ResearchUsage(web_search_invocations=1),
        calculations=(calculation,),
    )
    job_request = {
        "capability_class": "thorough_research",
        "language": "en",
        "question_kind": "cross_company",
        "scenario_question": True,
        "subjects": [{"symbol": "NVDA", "name": "NVIDIA", "asset_class": "equity"}],
        "currency": "USD",
    }
    composed = grounded.compose_completed_research(job_request=job_request, packet=packet)
    assert composed["answer"] == prose
    assert composed["computed"] is None
    assert composed[CALCULATION_OFFER_KEY]["requested_field"] == "per_share"
    assert (
        composed[CALCULATION_OFFER_KEY]["calculations"][0]["kind"]
        == "valuation_scenarios"
    )
    assert composed["next_steps"]["items"][0] == {
        "type": "test",
        "kind": "calculation_offer",
    }
    assert "degraded" not in composed["research"]
