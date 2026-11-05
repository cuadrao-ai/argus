"""Router locks: shape selection, honest degradation, one classifier call."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from argus.agent_runtime import research_answer as ra
from argus.agent_runtime import research_grounded as grounded
from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
from argus.agent_runtime.state.models import RunState, StrategySummary, UserState
from argus.domain.research.admission import (
    ResearchAttemptAdmission,
    research_attempt_admission_context,
)
from argus.domain.research.config import RESEARCH_CONFIG_SPECS
from argus.domain.research.contracts import ResearchUnavailableError
from argus.domain.research.perplexity_agent import PerplexityAgentClient

from tests.research.conftest import (
    RecordingTransport,
    agent_response,
    set_research_query,
    typed_answer_text,
)

USER = UserState(user_id="research-user", language_preference="en")
SPANISH_USER = UserState(user_id="research-es", language_preference="es")


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


def _classify(monkeypatch: pytest.MonkeyPatch, **fields: Any) -> None:
    """Inject the primary payload for research tests sharing this helper."""
    set_research_query(monkeypatch, globals(), **fields)


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


def test_flag_off_returns_none_before_any_classification(monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "false")

    async def explode(**_kwargs: Any):
        raise AssertionError("classifier must not run with the rail off")

    monkeypatch.setattr(ra, "_dispatch", explode)
    assert _run("What is Apple at?") is None


def test_primary_schema_marks_narrative_clauses_in_any_language() -> None:
    from argus.agent_runtime.llm_interpreter_types import LLMInterpretationResponse

    schema = LLMInterpretationResponse.model_json_schema()
    query = schema["$defs"]["ResearchQueryExtraction"]["properties"]
    assert "growth drivers" in query["question_kind"]["description"]
    assert "not live_quote in any language" in query["question_kind"]["description"]
    assert "publisher page" in query["requires_publisher_sources"]["description"]
    assert "period_start_date" in query


def test_classifier_rejects_a_malformed_period_start_date() -> None:
    with pytest.raises(ValueError):
        ra.ResearchQueryExtraction(
            question_kind="company_lookup",
            period_start_date="last quarter",
        )


def test_fast_quote_shape_grounds_and_classifies(monkeypatch) -> None:
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    transport = _wire_client(monkeypatch, [agent_response()])

    result = _run("What is Apple trading at right now?")

    assert result is not None
    assert transport.requests, "the fast shape must call the provider"
    sidecar = result.stage_patch["research"]
    assert sidecar["capability_class"] == "fast_quote"
    assert sidecar["shape"] == "fast"
    assert sidecar["usage"]["cache_status"] == "miss"
    assert result.stage_patch["assistant_response"].startswith("Apple closed")
    # The quote's prose states a figure with no typed row: recorded, never replaced.
    assert result.decision.reason_codes == [
        "answer_figures_unsourced",
        "research_answer_fast_quote",
    ]
    # Runnable rows ride along; the sidecar carries anchors and peers so the
    # persisted transcript can serve later confirmation cards.
    assert result.stage_patch["next_experiments"]["rows"]
    assert sidecar["anchor_symbols"] == ["AAPL"]
    assert "research_peers" not in result.stage_patch


def test_narrative_clause_can_never_use_the_fast_configuration(monkeypatch) -> None:
    """The semantic classifier owns language. The typed narrative fact is
    the deterministic guard if it ever returns a quote-shaped kind anyway."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="live_quote",
        symbols=["AAPL"],
        requires_publisher_sources=True,
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text="Services and iPhone sales drove Apple's growth.",
                sources=["https://www.apple.com/newsroom/earnings/"],
            )
        ],
    )

    result = _run("What were Apple's main growth drivers?")

    assert result is not None
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert [tool["type"] for tool in body["tools"]] == [
        "web_search",
        "finance_search",
        "fetch_url",
    ]
    assert body["max_steps"] == RESEARCH_CONFIG_SPECS["balanced"].max_steps
    assert result.stage_patch["research"]["shape"] == "balanced"
    assert result.stage_patch["research"]["capability_class"] == "balanced_lookup"
    assert result.stage_patch["research"]["sources"]


def test_second_identical_freeform_question_bypasses_shared_cache(monkeypatch) -> None:
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    transport = _wire_client(monkeypatch, [agent_response(), agent_response()])

    first = _run("What is Apple trading at right now?")
    second = _run("What is Apple trading at right now?")

    assert (
        len(transport.requests) == 2
    ), "freeform answers must be generated for each request"
    assert second is not None
    assert second.stage_patch["research"]["usage"]["cache_status"] == "miss"
    assert (
        second.stage_patch["assistant_response"]
        == first.stage_patch["assistant_response"]
    )


def test_company_lookup_uses_the_balanced_configuration(monkeypatch) -> None:
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NFLX"],
        period_of_interest="last fiscal year",
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text="Netflix revenue grew because membership and pricing rose.",
                sources=["https://ir.netflix.net/financials/quarterly-earnings/"],
            )
        ],
    )

    result = _run("How has Netflix's revenue changed?")

    assert result is not None
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert body["max_steps"] == RESEARCH_CONFIG_SPECS["balanced"].max_steps
    assert result.stage_patch["research"]["capability_class"] == "balanced_lookup"


def test_company_claims_fail_closed_when_no_publisher_source_survives(
    monkeypatch,
) -> None:
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NFLX"],
        requires_publisher_sources=True,
    )
    provider_only = agent_response(
        text="Advertising drove Netflix's growth.",
        sources=["https://www.perplexity.ai/finance/NFLX"],
    )
    transport = _wire_client(monkeypatch, [provider_only, provider_only])

    result = _run("What were Netflix's main growth drivers?")

    assert result is not None
    assert len(transport.requests) == 2
    sidecar = result.stage_patch["research"]
    assert sidecar["sources"] == []
    assert sidecar["degraded"] == {"code": "research_unavailable_missing_public_sources"}
    answer = result.stage_patch["assistant_response"]
    assert "Advertising drove" not in answer
    assert answer.startswith("I couldn't verify that explanation with a public source")


def test_company_claim_retries_without_the_provider_only_citation_channel(
    monkeypatch,
) -> None:
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["AAPL"],
        requires_publisher_sources=True,
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text="iPhone sales drove Apple's growth.",
                sources=["https://www.perplexity.ai/finance/AAPL"],
            ),
            agent_response(
                text="iPhone sales drove Apple's growth.",
                sources=["https://www.apple.com/newsroom/earnings/"],
            ),
        ],
    )

    result = _run("What were Apple's main growth drivers?")

    assert result is not None
    assert len(transport.requests) == 2
    retry_body = __import__("json").loads(transport.requests[1].content.decode())
    assert [tool["type"] for tool in retry_body["tools"]] == ["web_search", "fetch_url"]
    assert result.stage_patch["research"]["sources"] == [
        {
            "title": "www.apple.com",
            "domain": "www.apple.com",
            "url": "https://www.apple.com/newsroom/earnings/",
            "source_date": None,
        }
    ]
    assert result.stage_patch["assistant_response"].startswith("iPhone sales drove")


def test_cross_company_returns_a_background_job_request(monkeypatch) -> None:
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="cross_company",
        symbols=["NFLX", "AAPL"],
        period_start_date="2023-08-12",
        requires_publisher_sources=True,
    )
    transport = _wire_client(monkeypatch, [])

    result = _run("Compare Netflix and Apple over three years")

    assert result is not None
    assert transport.requests == [], "thorough runs never call in-turn"
    job_request = result.stage_patch["research_job_request"]
    assert job_request["shape"] == "thorough"
    assert job_request["capability_class"] == "thorough_research"
    assert job_request["question"] == "Compare Netflix and Apple over three years"
    assert [s["symbol"] for s in job_request["subjects"]] == ["NFLX", "AAPL"]
    assert job_request["period_start_date"] == "2023-08-12"
    assert job_request["requires_publisher_sources"] is True
    assert "cache_key" not in job_request
    assert "research" not in result.stage_patch


def test_completed_thorough_answer_is_not_shared_with_later_jobs(monkeypatch) -> None:
    """A finalized freeform answer remains scoped to its job."""
    set_research_query(
        monkeypatch, globals(), question_kind="cross_company", symbols=["NFLX", "AAPL"]
    )
    transport = _wire_client(monkeypatch, [])

    first = _run("Compare Netflix and Apple over three years")
    assert first is not None
    job_request = first.stage_patch["research_job_request"]

    from argus.domain.research.perplexity_agent import _packet_from_response

    packet = _packet_from_response(
        agent_response(
            text="Thorough comparison of NFLX and AAPL.",
            tickers=["NFLX", "AAPL"],
            lookup_rows=[("Microsoft", "MSFT", "Microsoft Corporation")],
        ),
        latency_ms=1200,
    )
    composed = ra.compose_completed_research(job_request=job_request, packet=packet)
    ra.store_research_packet_for_job(job_request, packet, composed)

    second = _run("Compare Netflix and Apple over three years", user=SPANISH_USER)
    assert second is not None
    # Each request gets its own job, regardless of language.
    assert "research_job_request" in second.stage_patch

    # A different user with the same question also gets a separate job.
    third = _run(
        "Compare Netflix and Apple over three years",
        user=UserState(user_id="another-user", language_preference="en"),
    )
    assert third is not None
    assert transport.requests == [], "thorough requests never run inline"
    assert "research_job_request" in third.stage_patch
    assert "cache_key" not in third.stage_patch["research_job_request"]
    assert "research" not in third.stage_patch
    # Composition still supplies the verified peers to the original job.
    assert composed["research"]["peers"][0]["symbol"] == "MSFT"


def test_screening_grounds_instead_of_queueing_a_background_job(monkeypatch) -> None:
    """A screen is a survey of current market data, so it grounds in the turn
    and comes back with names; it is not thorough multi-year research."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="screening",
        symbols=[],
        screening_criteria=["under a 20 P/E", "semiconductors"],
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text="Intel (INTC) trades under a 20 P/E.",
                tickers=["INTC"],
                lookup_rows=[("Intel", "INTC", "Intel Corporation")],
            )
        ],
    )

    result = _run("Show me semiconductor stocks under a 20 P/E")

    assert result is not None
    assert "research_job_request" not in result.stage_patch
    sidecar = result.stage_patch["research"]
    assert sidecar["capability_class"] == "screening"
    assert sidecar["usage"]["cache_status"] == "miss"
    # The stated conditions reach the provider verbatim, so the screen can
    # actually apply them instead of quietly ignoring them.
    body = __import__("json").loads(transport.requests[0].content.decode())
    prompt = body["input"] if isinstance(body.get("input"), str) else str(body)
    assert "under a 20 P/E" in prompt and "semiconductors" in prompt
    # A survey names no subject, so the verified name it found is runnable.
    assert result.stage_patch["next_experiments"]["rows"]


def test_crypto_never_reaches_finance_search(monkeypatch) -> None:
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="live_quote",
        symbols=["BTC"],
        asset_class_hint="crypto",
    )
    transport = _wire_client(monkeypatch, [agent_response()])

    async def voice(*, message, language, facts, fallback, user=None):
        return fallback

    from argus.agent_runtime import knowledge_answer as ka

    monkeypatch.setattr(ka, "_voiced_answer", voice)

    result = _run("What is Bitcoin trading at right now?")

    assert result is not None
    assert transport.requests == [], "crypto must not route to finance_search"
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "asset_class_not_covered"}
    text = result.stage_patch["assistant_response"]
    assert "BTC" in text
    # Honest coverage note plus a runnable next step, never a dead end.
    assert result.stage_patch["next_experiments"]["rows"]


def test_currency_pairs_degrade_honestly(monkeypatch) -> None:
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="live_quote",
        symbols=["EURUSD"],
        asset_class_hint="currency_pair",
    )
    transport = _wire_client(monkeypatch, [agent_response()])

    async def voice(*, message, language, facts, fallback, user=None):
        return fallback

    from argus.agent_runtime import knowledge_answer as ka

    monkeypatch.setattr(ka, "_voiced_answer", voice)

    result = _run("What is the euro dollar rate?")

    assert result is not None
    assert transport.requests == []
    assert result.stage_patch["research"]["degraded"]["code"] == "asset_class_not_covered"


def test_exhausted_ceiling_is_an_honest_note_not_a_disappearance(monkeypatch) -> None:
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    transport = _wire_client(monkeypatch, [agent_response()])

    async def voice(*, message, language, facts, fallback, user=None):
        return fallback

    from argus.agent_runtime import knowledge_answer as ka

    monkeypatch.setattr(ka, "_voiced_answer", voice)

    with research_attempt_admission_context(
        lambda: ResearchAttemptAdmission(available=False)
    ):
        result = _run("What is Apple at?")

    assert result is not None
    assert transport.requests == [], "an exhausted ceiling must not spend"
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "research_capacity_exhausted"}
    assert "capacity" in result.stage_patch["assistant_response"].lower()
    assert result.stage_patch["next_experiments"]["rows"]


def test_atomic_claim_denial_stops_an_inline_provider_call(monkeypatch) -> None:
    """A turn admitted before a rival spent the last slot must re-check at
    the billable boundary and degrade without touching the provider."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    transport = _wire_client(monkeypatch, [agent_response()])

    async def voice(*, message, language, facts, fallback, user=None):
        return fallback

    from argus.agent_runtime import knowledge_answer as ka

    monkeypatch.setattr(ka, "_voiced_answer", voice)
    with research_attempt_admission_context(
        lambda: ResearchAttemptAdmission(
            available=False,
            guest_exhausted=True,
        )
    ):
        result = _run("What is Apple at?")

    assert result is not None
    assert transport.requests == []
    assert "free research" in result.stage_patch["assistant_response"]
    assert result.stage_patch["research"]["usage"]["cache_status"] == "bypass"


def test_repeated_freeform_question_rechecks_research_capacity(monkeypatch) -> None:
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    transport = _wire_client(monkeypatch, [agent_response()])
    assert _run("What is Apple trading at right now?") is not None
    claims = []

    def reject_claim() -> ResearchAttemptAdmission:
        claims.append(True)
        return ResearchAttemptAdmission(available=False, guest_exhausted=True)

    with research_attempt_admission_context(reject_claim):
        result = _run("What is Apple trading at right now?")

    assert result is not None
    assert claims == [True]
    assert len(transport.requests) == 1
    assert result.stage_patch["research"]["usage"]["cache_status"] == "bypass"
    assert "free research" in result.stage_patch["assistant_response"]


def test_provider_failure_degrades_without_fabricating(monkeypatch) -> None:
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )

    class FailingClient:
        def run_research(self, prompt, spec):
            raise ResearchUnavailableError("timeout")

    monkeypatch.setattr(grounded, "_client", lambda: FailingClient())

    result = _run("What is Apple at?")

    assert result is not None
    patch = result.stage_patch
    # A timeout is transient: the turn offers the retry, never figures or rows.
    assert patch["recovery"] == {"code": "research_lookup_failed", "retryable": True}
    assert "next_experiments" not in patch
    assert patch["research"]["degraded"]["code"] == "research_unavailable_timeout"


def test_a_none_read_falls_through(monkeypatch) -> None:
    set_research_query(monkeypatch, globals(), question_kind="none", symbols=[])
    assert _run("Thanks, that helps.") is None


def test_a_concept_question_takes_the_grounded_balanced_path(monkeypatch) -> None:
    from argus.agent_runtime.interpreter.research_routing import (
        CONCEPT_QUESTION_REASON_CODE,
    )

    set_research_query(monkeypatch, globals(), question_kind="concept", symbols=[])
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text="A drawdown is the fall from a peak to the lowest point after it.",
                sources=["https://www.investor.gov/introduction-investing/drawdown"],
            )
        ],
    )

    result = _run("What is a drawdown?")

    assert result is not None
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert body["max_steps"] == RESEARCH_CONFIG_SPECS["balanced"].max_steps
    assert CONCEPT_QUESTION_REASON_CODE in result.decision.reason_codes


def test_an_out_of_scope_verdict_with_nothing_to_run_is_researched(monkeypatch) -> None:
    from argus.agent_runtime.interpreter.research_routing import (
        UNSUPPORTED_VERDICT_REASON_CODE,
    )

    original = globals()["_interpretation"]
    monkeypatch.setitem(
        globals(),
        "_interpretation",
        lambda: original().model_copy(
            update={"semantic_turn_act": "unsupported_request"}
        ),
    )
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text="Cards differ most by annual fee, rewards rate and APR.",
                sources=["https://www.consumerfinance.gov/consumer-tools/credit-cards/"],
            )
        ],
    )

    result = _run("Which credit card should I get?")

    assert result is not None and transport.requests
    assert UNSUPPORTED_VERDICT_REASON_CODE in result.decision.reason_codes


def test_an_out_of_scope_verdict_that_asks_or_can_run_keeps_its_route(
    monkeypatch,
) -> None:
    original = globals()["_interpretation"]
    monkeypatch.setitem(
        globals(),
        "_interpretation",
        lambda: original().model_copy(update={"requires_clarification": True}),
    )
    transport = _wire_client(monkeypatch, [agent_response()])

    assert _run("Buy it when it starts rising.") is None
    assert not transport.requests


def test_spanish_turn_carries_the_language_into_the_prompt(monkeypatch) -> None:
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    transport = _wire_client(monkeypatch, [agent_response(text="Apple cerró...")])

    result = _run("¿A cuánto está Apple?", user=SPANISH_USER)

    assert result is not None
    prompt = __import__("json").loads(transport.requests[0].content.decode())["input"]
    assert "es-419" in prompt


@pytest.mark.parametrize(
    ("user", "must_say", "must_not_say"),
    [
        (USER, "free research", "shared research capacity"),
        (SPANISH_USER, "gratis", "capacidad compartida"),
    ],
)
def test_a_guest_who_spent_their_own_allowance_is_told_so(
    monkeypatch, user, must_say, must_not_say
) -> None:
    """A guest's three are their own. Telling them the shared capacity ran out
    would be a more flattering story than the true one."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    _wire_client(monkeypatch, [agent_response()])

    async def voice(*, message, language, facts, fallback, user=None):
        return fallback

    from argus.agent_runtime import knowledge_answer as ka

    monkeypatch.setattr(ka, "_voiced_answer", voice)

    with research_attempt_admission_context(
        lambda: ResearchAttemptAdmission(available=False, guest_exhausted=True)
    ):
        result = _run("What is Apple at?", user=user)

    assert result is not None
    answer = result.stage_patch["assistant_response"].lower()
    assert must_say in answer
    assert must_not_say not in answer
    # Still ends somewhere runnable: an exhausted meter is not a dead end.
    assert result.stage_patch["next_experiments"]["rows"]


@pytest.mark.parametrize(
    ("user", "must_say"),
    [(USER, "shared research capacity"), (SPANISH_USER, "capacidad compartida")],
)
def test_a_shared_outage_still_says_shared(monkeypatch, user, must_say) -> None:
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    _wire_client(monkeypatch, [agent_response()])

    async def voice(*, message, language, facts, fallback, user=None):
        return fallback

    from argus.agent_runtime import knowledge_answer as ka

    monkeypatch.setattr(ka, "_voiced_answer", voice)

    with research_attempt_admission_context(
        lambda: ResearchAttemptAdmission(available=False)
    ):
        result = _run("What is Apple at?", user=user)

    assert result is not None
    assert must_say in result.stage_patch["assistant_response"].lower()


def test_a_research_answer_ends_with_the_questions_its_research_offered(
    monkeypatch,
) -> None:
    set_research_query(monkeypatch, globals(), question_kind="concept", symbols=[])
    questions = ["How is a drawdown measured?", "What is a maximum drawdown?"]
    _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    "A drawdown is the fall from a peak to the lowest point after it.",
                    [],
                    None,
                    questions,
                ),
                sources=["https://www.investor.gov/introduction-investing/drawdown"],
            )
        ],
    )

    result = _run("What is a drawdown?")

    assert result is not None
    assert result.stage_patch["research"]["follow_up"]["questions"] == questions
    assert result.stage_patch["next_steps"]["items"] == [
        {"type": "question", "text": text} for text in questions
    ]


def test_a_declined_request_keeps_its_plain_reply_and_offers_nothing(monkeypatch) -> None:
    from argus.agent_runtime.research_grounded import DECLINED_REASON_CODE

    set_research_query(
        monkeypatch, globals(), question_kind="current_external", symbols=[]
    )
    reply = "Argus does not place trades. It can test a trading idea on past data."
    _wire_client(
        monkeypatch,
        [agent_response(text=typed_answer_text(reply, [], None, [], declined=True))],
    )

    result = _run("Buy 10 shares of Apple for me right now.")

    assert result is not None
    assert result.stage_patch["assistant_response"] == reply
    assert "next_steps" not in result.stage_patch
    assert "degraded" not in result.stage_patch["research"]
    assert DECLINED_REASON_CODE in result.decision.reason_codes


def test_an_answer_stating_a_figure_with_no_source_is_recorded_not_replaced(
    monkeypatch,
) -> None:
    from argus.agent_runtime.answer_calculation import UNSOURCED_FIGURE_REASON_CODE

    set_research_query(monkeypatch, globals(), question_kind="concept", symbols=[])
    prose = "Savings accounts often pay about 4% while prices rose 3.1% last year."
    _wire_client(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(
                    prose,
                    [
                        {
                            "subject": "United States",
                            "symbol": None,
                            "label": "consumer price inflation 2025",
                            "value": 3.1,
                            "kind": "percent",
                            "unit": "%",
                            "as_of": "2026-01-15",
                            "source_url": "https://www.bls.gov/cpi/",
                        }
                    ],
                ),
                sources=["https://www.bls.gov/cpi/"],
            )
        ],
    )

    result = _run("Is my savings account actually losing money?")

    assert result is not None
    assert result.stage_patch["assistant_response"].startswith(prose)
    assert UNSOURCED_FIGURE_REASON_CODE in result.decision.reason_codes


@pytest.mark.parametrize("intent", ["conversation_followup", "beginner_guidance"])
def test_an_explicit_concept_question_is_researched_for_the_readers_country(
    monkeypatch, intent
) -> None:
    """An explicit query carries the reader's country and currency to research."""
    from argus.agent_runtime.interpreter.research_routing import (
        CONCEPT_QUESTION_REASON_CODE,
    )

    original = globals()["_interpretation"]
    monkeypatch.setitem(
        globals(),
        "_interpretation",
        lambda: original().model_copy(update={"intent": intent}),
    )
    set_research_query(monkeypatch, globals(), question_kind="concept", symbols=[])
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text="Ahorrar en dólares protege de la devaluación; en pesos, la tasa es mayor.",
                sources=["https://www.bancentral.gov.do/a/d/2532-tasas-de-interes"],
            )
        ],
    )
    reader = UserState(
        user_id="research-do", language_preference="es", country="DO", currency="DOP"
    )

    result = _run("¿Ahorro en pesos o en dólares?", user=reader)

    assert result is not None and len(transport.requests) == 1
    body = __import__("json").loads(transport.requests[0].content.decode())
    assert body["max_steps"] == RESEARCH_CONFIG_SPECS["balanced"].max_steps
    assert (
        "The reader lives in Dominican Republic (DO) and counts money in DOP. "
        "Answer for that country unless the question names another, and never ask "
        "where the reader lives."
    ) in body["input"]
    assert CONCEPT_QUESTION_REASON_CODE in result.decision.reason_codes


def test_a_reader_with_no_country_is_never_placed_in_one(monkeypatch) -> None:
    original = globals()["_interpretation"]
    monkeypatch.setitem(
        globals(),
        "_interpretation",
        lambda: original().model_copy(update={"intent": "conversation_followup"}),
    )
    set_research_query(monkeypatch, globals(), question_kind="concept", symbols=[])
    transport = _wire_client(
        monkeypatch,
        [
            agent_response(
                text="An emergency fund is money kept for sudden costs.",
                sources=["https://www.consumerfinance.gov/an-essential-guide/"],
            )
        ],
    )

    assert _run("Should I put my emergency fund in crypto?") is not None

    body = __import__("json").loads(transport.requests[0].content.decode())
    assert "The reader lives in" not in body["input"]


@pytest.mark.parametrize(
    "update",
    [
        {"capability_question_focus": "supported_indicators"},
        {"requires_clarification": True},
    ],
)
def test_an_unkinded_question_another_route_owns_keeps_that_route(
    monkeypatch, update
) -> None:
    original = globals()["_interpretation"]
    monkeypatch.setitem(
        globals(),
        "_interpretation",
        lambda: original().model_copy(
            update={"intent": "conversation_followup", **update}
        ),
    )
    transport = _wire_client(monkeypatch, [agent_response()])

    assert _run("Can I use Bollinger Bands in a rule?") is None
    assert not transport.requests


def test_a_read_typed_kind_none_keeps_the_interpreters_reply(monkeypatch) -> None:
    original = globals()["_interpretation"]
    monkeypatch.setitem(
        globals(),
        "_interpretation",
        lambda: original().model_copy(update={"intent": "conversation_followup"}),
    )
    set_research_query(monkeypatch, globals(), question_kind="none", symbols=[])
    transport = _wire_client(monkeypatch, [agent_response()])

    assert _run("Thanks, that helps.") is None
    assert not transport.requests
