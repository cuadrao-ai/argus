"""Registered research calls retain one provider, cache and source boundary."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, get_args
from unittest.mock import AsyncMock

import pytest
from argus.agent_runtime import research_grounded as grounded
from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRelationship
from argus.agent_runtime.state.models import RunState, UserState
from argus.domain.research.admission import (
    ResearchAttemptAdmission,
    research_attempt_admission_context,
)
from argus.domain.research.contracts import (
    ResearchPacket,
    ResearchSource,
    ResearchUsage,
    RetrievedRow,
)
from faker import Faker
from pydantic import ValidationError

FAKE = Faker()


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        state=RunState.new(
            current_user_message=FAKE.sentence(), recent_thread_history=[]
        ),
        user=UserState(user_id=FAKE.uuid4(), language_preference="en"),
        stage_result=None,
    )


def _packet(symbol: str = "AAPL") -> ResearchPacket:
    publisher_url = "https://www.reuters.com/markets/company-data"
    observed = datetime.now(timezone.utc)
    value = float(FAKE.pydecimal(left_digits=3, right_digits=2, positive=True))
    row = RetrievedRow(
        subject=symbol,
        symbol=symbol,
        label="share price",
        value=value,
        kind="currency",
        unit="USD",
        as_of=observed.date().isoformat(),
        source_url=publisher_url,
    )
    return ResearchPacket(
        answer_markdown=f"{symbol} is {value} USD.",
        rows=(row,),
        typed_answer=True,
        categories=("quote",),
        sources=(ResearchSource(url=publisher_url, source_date=row.as_of),),
        usage=ResearchUsage(invocations=1, finance_search_invocations=1),
        retrieved_at=observed,
    )


class _ResearchClient:
    def __init__(self, *packets: ResearchPacket) -> None:
        self.packets = iter(packets)
        self.calls: list[tuple[str, Any]] = []

    def run_research(self, prompt: str, spec: Any) -> ResearchPacket:
        self.calls.append((prompt, spec))
        return next(self.packets)


def _wire(monkeypatch: pytest.MonkeyPatch, *packets: ResearchPacket) -> _ResearchClient:
    client = _ResearchClient(*packets)
    monkeypatch.setattr(grounded, "_client", lambda: client)
    # Coverage/runnable-row suggestions are outside this provider-call contract.
    monkeypatch.setattr(grounded, "research_next_experiment_rows", lambda **_: None)
    return client


def test_repeated_tool_calls_use_their_arguments_without_sharing_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.research_tools import FastQuoteArguments, fast_quote

    first_packet, second_packet = _packet("AAPL"), _packet("MSFT")
    client = _wire(monkeypatch, first_packet, second_packet, first_packet)
    first = FastQuoteArguments(
        request="Read AAPL's current share price", symbols=["AAPL"]
    )
    second = FastQuoteArguments(
        request="Read MSFT's current share price", symbols=["MSFT"]
    )
    context = _context()
    claims: list[bool] = []

    def claim() -> ResearchAttemptAdmission:
        claims.append(True)
        return ResearchAttemptAdmission(available=True)

    async def invoke():
        with research_attempt_admission_context(claim):
            a = await fast_quote(first, context=context)
            b = await fast_quote(second, context=context)
            repeated = await fast_quote(first, context=context)
        return a, b, repeated

    a, b, repeated = asyncio.run(invoke())
    assert a.rows == repeated.rows == first_packet.rows
    assert b.rows == second_packet.rows
    assert len(client.calls) == 3
    # The allowance counts one research question/turn. Existing admission
    # owns that grain even when the model needs three retrieval operations.
    assert len(claims) == 1
    assert first.request in client.calls[0][0]
    assert second.request not in client.calls[0][0]
    assert context.state.current_user_message not in client.calls[0][0]
    assert context.stage_result.stage_patch["research"]["usage"]["cache_status"] == "miss"
    assert "candidate_strategy_draft" not in context.stage_result.stage_patch
    assert "confirmed_strategy_summary" not in context.stage_result.stage_patch


@pytest.mark.parametrize("closed_window", [False, True])
def test_balanced_call_preserves_the_existing_service_period_policy(
    monkeypatch: pytest.MonkeyPatch,
    closed_window: bool,
) -> None:
    from argus.agent_runtime.research_tools import (
        BalancedLookupArguments,
        ResearchPeriod,
        balanced_lookup,
    )
    from argus.domain.research.config import retrieval_spec

    client = _wire(monkeypatch, _packet())
    context = _context()
    args = BalancedLookupArguments(
        request="Read the latest source-backed figures",
        symbols=["AAPL"],
        period=ResearchPeriod(
            description="The requested period", closed_window=closed_window
        ),
    )
    result = asyncio.run(balanced_lookup(args, context=context))
    assert result.sources
    assert client.calls[0][1].shape == "balanced"
    expected = retrieval_spec(
        "balanced",
        question_kind="current_external",
        closed_period=closed_window,
        country=None,
    )
    assert client.calls[0][1].recency == expected.recency
    assert "question_kind" not in args.model_dump()
    assert (
        context.stage_result.stage_patch["research"]["capability_class"]
        == "balanced_lookup"
    )


def test_missing_publisher_sources_is_failure_without_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.research_tools import (
        BalancedLookupArguments,
        balanced_lookup,
    )
    from argus.domain.tool_declaration import ToolInvocationError

    no_sources = _packet().model_copy(update={"sources": ()})
    client = _wire(monkeypatch, no_sources, no_sources)
    context = _context()
    with pytest.raises(ToolInvocationError) as failure:
        asyncio.run(
            balanced_lookup(
                BalancedLookupArguments(
                    request="Read company growth drivers", symbols=["AAPL"]
                ),
                context=context,
            )
        )
    assert (
        failure.value.outcome.failure.code
        == "research_unavailable_missing_public_sources"
    )
    assert len(client.calls) == 2
    assert context.stage_result.stage_patch["research"]["rows"] == []
    assert (
        no_sources.answer_markdown
        not in context.stage_result.stage_patch["assistant_response"]
    )


def test_thorough_call_retains_job_lifecycle_without_inline_provider_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.research_tools import (
        ThoroughResearchArguments,
        thorough_research,
    )

    client = _wire(monkeypatch)
    context = _context()
    args = ThoroughResearchArguments(
        request="Read the source-backed financial comparison",
        symbols=["AAPL", "MSFT"],
    )
    result = asyncio.run(thorough_research(args, context=context))
    payload = result.model_dump(mode="json")
    assert payload["status"] == "pending"
    assert payload["answer"] is None and not payload["rows"]
    assert client.calls == []
    job = context.stage_result.stage_patch["research_job_request"]
    assert job["question"] == args.request
    assert "data_class" not in job
    assert job["capability_class"] == "thorough_research"
    from argus.domain.research.config import retrieval_spec

    assert grounded.retrieval_spec_for_job(job) == retrieval_spec(
        "thorough",
        question_kind=job["question_kind"],
        language_tag=job["language"],
        country=job["country"],
    )


def test_screening_keeps_every_explicit_condition_in_the_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.research_tools import ScreeningArguments, screening

    client = _wire(monkeypatch, _packet())
    context = _context()
    conditions = ["P/E below 20", "positive operating cash flow"]
    args = ScreeningArguments(
        request="Read companies meeting these conditions", criteria=conditions
    )
    asyncio.run(screening(args, context=context))
    prompt, spec = client.calls[0]
    assert all(condition in prompt for condition in conditions)
    assert spec.shape == "balanced" and spec.recency == "week"
    assert context.stage_result.stage_patch["research"]["capability_class"] == "screening"


def test_peer_expansion_requires_a_typed_anchor_or_category() -> None:
    from argus.agent_runtime.research_tools import PeerExpansionArguments

    with pytest.raises(ValidationError):
        PeerExpansionArguments(request="Find alternatives", relationship="peer")
    args = PeerExpansionArguments(
        request="Find related assets", relationship="peer", anchor_symbols=["AAPL"]
    )
    assert "question_kind" not in args.model_json_schema()["properties"]


@pytest.mark.parametrize(
    "argument_type", ["BalancedLookupArguments", "ThoroughResearchArguments"]
)
def test_unknown_freshness_override_is_rejected(argument_type: str) -> None:
    from argus.agent_runtime import research_tools

    with pytest.raises(ValidationError, match="data_class"):
        getattr(research_tools, argument_type)(
            request="Read sourced facts", data_class="analyst_estimates"
        )


def test_pending_research_card_has_no_answer() -> None:
    from argus.agent_runtime.research_tools import (
        ResearchToolResult,
        ThoroughResearchArguments,
        research_card_presentation,
    )
    from argus.domain.tool_contracts import ToolOutcome

    presentation = research_card_presentation(
        ThoroughResearchArguments(request="Read public reports"),
        ToolOutcome(
            status="succeeded",
            result=ResearchToolResult(status="pending").model_dump(mode="json"),
        ),
    )
    assert presentation.answer is None
    assert presentation.rows == []
    assert presentation.narrative is None
    assert presentation.sources == []
    assert presentation.notes


def test_completed_research_presentation_keeps_cited_narrative_and_typed_figures() -> (
    None
):
    from argus.agent_runtime.research_tools import (
        FastQuoteArguments,
        ResearchToolResult,
        research_card_presentation,
    )
    from argus.domain.tool_contracts import ToolOutcome

    packet = _packet()
    result = ResearchToolResult(
        answer=packet.answer_markdown, rows=packet.rows, sources=packet.sources
    )
    presentation = research_card_presentation(
        FastQuoteArguments(request="Read the latest share price", symbols=["AAPL"]),
        ToolOutcome(status="succeeded", result=result.model_dump(mode="json")),
    )
    assert presentation.answer.value == packet.rows[0].value
    assert presentation.narrative == packet.answer_markdown
    assert presentation.sources == list(packet.sources)


@pytest.mark.parametrize("relationship", get_args(AssetDiscoveryRelationship))
def test_peer_expansion_calls_existing_discovery_and_returns_verified_rows(
    monkeypatch: pytest.MonkeyPatch, relationship: AssetDiscoveryRelationship
) -> None:
    from argus.agent_runtime.research_tools import PeerExpansionArguments, peer_expansion

    from tests.research.test_research_router_absorption import (
        _FakeSearchProvider,
        _search_packet,
        _wire_find,
    )

    packet = _search_packet()
    provider = _FakeSearchProvider(packet)
    _wire_find(monkeypatch, provider=provider)
    context = _context()
    result = asyncio.run(
        peer_expansion(
            PeerExpansionArguments(
                request="Find cybersecurity companies",
                relationship=relationship,
                anchor_symbols=[] if relationship == "category" else ["PANW"],
                category_description="cybersecurity",
                needs_current_facts=True,
            ),
            context=context,
        )
    )
    assert [peer.symbol for peer in result.peers] == ["CRWD"]
    assert context.stage_result.stage_patch["research"]["shape"] == "find"
    assert context.stage_result.stage_patch["discovery"]["relationship"] == relationship
    assert result.relationship == relationship
    assert provider.calls
    assert [source.url for source in result.sources] == [
        source.url for source in packet.results
    ]
    assert "candidate_strategy_draft" not in context.stage_result.stage_patch


def test_peer_expansion_reuses_the_existing_cache_for_a_repeated_call(
    monkeypatch,
) -> None:
    from argus.agent_runtime.research_tools import PeerExpansionArguments, peer_expansion

    from tests.research.test_research_router_absorption import (
        _FakeSearchProvider,
        _search_packet,
        _wire_find,
    )

    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)
    context = _context()
    common = {
        "request": "Find candidate assets around this business",
        "anchor_symbols": ["AAPL"],
        "needs_current_facts": True,
    }

    async def invoke():
        results = []
        for relationship in ("comparison", "comparison"):
            result = await peer_expansion(
                PeerExpansionArguments(relationship=relationship, **common),
                context=context,
            )
            results.append(
                (
                    result.relationship,
                    context.stage_result.stage_patch["research"]["usage"]["cache_status"],
                )
            )
        return results

    results = asyncio.run(invoke())
    assert len(provider.calls) == 1
    assert results == [("comparison", "miss"), ("comparison", "hit")]


def test_disabled_research_fails_before_provider_or_quota_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.research_tools import get_research_declarations

    client = _wire(monkeypatch)
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "false")
    tool = next(item for item in get_research_declarations() if item.name == "fast_quote")
    outcome = asyncio.run(
        tool.invoke(
            {"request": "Read the price", "symbols": ["AAPL"]},
            context=_context(),
        )
    )
    assert outcome.status == "unavailable"
    assert outcome.result is None
    assert client.calls == []


def test_pending_result_cannot_carry_completed_facts() -> None:
    from argus.agent_runtime.research_tools import ResearchToolResult

    with pytest.raises(ValidationError):
        ResearchToolResult(status="pending", answer=FAKE.sentence(), rows=_packet().rows)


@pytest.mark.parametrize(
    ("discovery_enabled", "naming_available", "code", "retryable"),
    [
        (True, True, "discovery_no_verified_candidates", False),
        (True, False, "discovery_suggestions_unavailable", True),
        (False, False, "discovery_unavailable", False),
    ],
    ids=["no_verified_candidates", "naming_unavailable", "disabled"],
)
def test_discovery_recovery_is_an_unavailable_tool_outcome(
    monkeypatch: pytest.MonkeyPatch,
    discovery_enabled: bool,
    naming_available: bool,
    code: str,
    retryable: bool,
) -> None:
    from argus.agent_runtime.discovery import composer
    from argus.agent_runtime.discovery.contracts import DiscoveryExtraction
    from argus.agent_runtime.research_tools import (
        get_research_declarations,
        research_outcome_from_patch,
    )
    from argus.agent_runtime.stages.tool_execution import execute_tool_calls_async
    from argus.domain.tool_contracts import ToolCall
    from argus.domain.tool_declaration import ToolCatalog

    monkeypatch.setenv("ARGUS_GROUNDED_DISCOVERY_ENABLED", str(discovery_enabled).lower())
    naming = AsyncMock(return_value=DiscoveryExtraction() if naming_available else None)
    recovery_response = FAKE.sentence()
    monkeypatch.setattr(composer, "name_candidates", naming)
    monkeypatch.setattr(
        composer,
        "_voiced_discovery_recovery",
        AsyncMock(return_value=recovery_response),
    )
    context = _context()
    call = ToolCall(
        call_id=FAKE.uuid4(),
        tool_name="peer_expansion",
        arguments={
            "request": "Find verified companies in this sector",
            "relationship": "category",
            "category_description": "cybersecurity",
            "needs_current_facts": False,
        },
    )
    state = context.state.model_copy(update={"tool_calls": [call]})

    result = asyncio.run(
        execute_tool_calls_async(
            state=state,
            tool=None,
            user=context.user,
            catalog=ToolCatalog(get_research_declarations()),
        )
    )

    effect = result.stage_patch["tool_effects"][0]["stage_patch"]
    assert effect["recovery"]["code"] == code
    assert effect["recovery"]["retryable"] is retryable
    assert naming.await_count == int(discovery_enabled)
    record = result.stage_patch["tool_call_records"][0]
    assert record["outcome"] == "unavailable"
    assert record["tool_outcome"]["failure"]["code"] == code
    assert record["tool_outcome"]["result"] is None
    # The same projection owns a persisted job's terminal tool outcome.
    assert (
        research_outcome_from_patch(effect).model_dump(mode="json")
        == record["tool_outcome"]
    )
    card = result.stage_patch["final_response_payload"]["tool_result_cards"][0]
    assert card["outcome"] == record["tool_outcome"]
    assert card["presentation"]["answer"] is None
    assert card["presentation"]["narrative"] is None
    assert card["presentation"]["sources"] == []
    assert result.stage_patch["assistant_response"] == recovery_response
