"""Shared-cache privacy and collision regressions with synthetic provider data."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from argus.agent_runtime import research_grounded as grounded
from argus.agent_runtime.research_query import ResearchQueryExtraction
from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
from argus.agent_runtime.state.models import RunState
from argus.domain.research.cache import cache_stats
from faker import Faker

from tests.research.test_registered_research_tools import _context, _packet, _wire

FAKE = Faker()


@pytest.mark.parametrize(
    "changed",
    [
        {"screening_criteria": ["revenue growth above 20%"]},
        {"sector_of_interest": "healthcare"},
        {"period_of_interest": "2025"},
        {"period_is_closed_window": True},
        {"period_start_date": date(2025, 1, 2)},
        {"requires_publisher_sources": True},
        {"currency": "DOP"},
        {},
    ],
)
def test_freeform_requests_do_not_reuse_or_store_answers(monkeypatch, changed) -> None:
    """Identical prose is not proof that carried criteria or private facts agree."""
    context = _context()
    user = context.user.model_copy(update={"country": "DO", "currency": "USD"})
    query = ResearchQueryExtraction(
        question_kind="screening",
        screening_criteria=["revenue growth above 10%"],
        sector_of_interest="technology",
    )
    packets = [_packet(), _packet()]
    client = _wire(monkeypatch, *packets)
    interpretation = StructuredInterpretation(
        intent="conversation_followup",
        task_relation="continue",
        user_goal_summary="research",
        semantic_turn_act="educational_question",
    )
    state = RunState.new(
        current_user_message="Find matches for my criteria", recent_thread_history=[]
    )

    async def run(query, user):
        return await grounded.grounded_result(
            query=query,
            subjects=[],
            shape="balanced",
            interpretation=interpretation,
            state=state,
            user=user,
        )

    first = asyncio.run(run(query, user))
    second = asyncio.run(
        run(
            query.model_copy(
                update={k: v for k, v in changed.items() if k != "currency"}
            ),
            user.model_copy(update={"currency": changed.get("currency", user.currency)}),
        )
    )
    assert first is not None and second is not None
    assert len(client.calls) == 2
    assert (
        second.stage_patch["assistant_response"]
        != first.stage_patch["assistant_response"]
    )
    assert cache_stats()["entries"] == 0


@pytest.mark.parametrize("field", ["message", "screening_criteria", "sector_of_interest"])
def test_private_context_never_enters_shared_storage(monkeypatch, field) -> None:
    private = f"Private account {FAKE.uuid4()} balance {FAKE.pyint()}"
    context = _context()
    query = ResearchQueryExtraction(question_kind="company_lookup")
    message = "Explain these public market figures"
    if field == "message":
        message = private
    else:
        query = query.model_copy(
            update={field: [private] if field == "screening_criteria" else private}
        )
    packet = _packet().model_copy(update={"answer_markdown": private})
    client = _wire(monkeypatch, packet, packet)
    interpretation = StructuredInterpretation(
        intent="conversation_followup",
        task_relation="continue",
        user_goal_summary="research",
    )
    for _ in range(2):
        result = asyncio.run(
            grounded.grounded_result(
                query=query,
                subjects=[],
                shape="balanced",
                interpretation=interpretation,
                state=RunState.new(
                    current_user_message=message, recent_thread_history=[]
                ),
                user=context.user,
            )
        )
        assert result.stage_patch["research"]["usage"]["cache_status"] == "miss"
    assert len(client.calls) == 2
    assert private in client.calls[0][0]
    assert cache_stats() == {"entries": 0, "hits": 0, "misses": 0}


def _empty_decision(request):
    """The production discovery decision: anchors on the request, draft proof empty."""
    from argus.agent_runtime.stages.interpret_types import InterpretDecision
    from argus.agent_runtime.state.models import ResponseProfile

    return InterpretDecision(
        intent="conversation_followup",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="research",
        confidence=0.9,
        effective_response_profile=ResponseProfile(
            effective_tone="friendly",
            effective_verbosity="medium",
            effective_expertise_mode="beginner",
        ),
        semantic_turn_act="asset_discovery",
        asset_discovery=request,
    )


def _find(monkeypatch, requests):
    """Run find the way interpret does: empty draft provenance, anchors on the request.

    State is planted with provider-catalog rows for those same anchors. That
    planting must not decide eligibility.
    """
    from argus.agent_runtime.research_find import find_assets_stage_result
    from argus.agent_runtime.state.models import ResolutionProvenance

    from tests.research.test_research_router_absorption import (
        _FakeSearchProvider,
        _search_packet,
        _wire_find,
    )

    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)
    results = []
    for request in requests:
        state = RunState.new(
            current_user_message=FAKE.sentence(), recent_thread_history=[]
        )
        state.resolution_provenance = [
            ResolutionProvenance(
                field="asset_universe",
                raw_text=symbol,
                source="llm_extraction",
                candidate_kind="asset",
                canonical_symbol=symbol.strip().upper(),
                asset_class=request.asset_class_hint or "equity",
                validated_by="provider_catalog",
            )
            for symbol in request.anchor_symbols
            if symbol.strip()
        ]
        results.append(
            asyncio.run(
                find_assets_stage_result(
                    request=request,
                    interpretation=StructuredInterpretation(
                        intent="conversation_followup",
                        task_relation="continue",
                        user_goal_summary="research",
                        semantic_turn_act="asset_discovery",
                    ),
                    decision=_empty_decision(request),
                    state=state,
                    user=_context().user,
                )
            )
        )
    return provider, results


def test_verified_public_search_reuses_normalized_inputs_across_users(
    monkeypatch,
) -> None:
    from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRequest

    request = AssetDiscoveryRequest(
        relationship="peer", anchor_symbols=["AAPL"], needs_current_facts=True
    )
    provider, results = _find(
        monkeypatch,
        [request, request.model_copy(update={"anchor_symbols": [" aapl ", " "]})],
    )
    assert len(provider.calls) == 1
    assert [r.stage_patch["research"]["usage"]["cache_status"] for r in results] == [
        "miss",
        "hit",
    ]
    assert cache_stats()["entries"] == 1


def test_catalog_validation_runs_off_the_event_loop(monkeypatch) -> None:
    """Catalog proof for cache eligibility must not block the chat event loop."""
    import threading

    from argus.agent_runtime import resolution
    from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRequest

    caller = threading.get_ident()
    seen: list[int] = []
    real = resolution.resolve_asset_candidate

    def spy(*args, **kwargs):
        seen.append(threading.get_ident())
        return real(*args, **kwargs)

    monkeypatch.setattr(resolution, "resolve_asset_candidate", spy)
    request = AssetDiscoveryRequest(
        relationship="peer", anchor_symbols=["AAPL"], needs_current_facts=True
    )
    provider, results = _find(monkeypatch, [request])
    assert seen
    assert all(thread_id != caller for thread_id in seen)
    assert len(provider.calls) == 1
    assert results[0].stage_patch["research"]["usage"]["cache_status"] == "miss"


@pytest.mark.parametrize(
    "change",
    [
        {"relationship": "comparison"},
        {"anchor_symbols": ["MSFT"]},
        {"asset_class_hint": "crypto"},
        {"anchor_symbols": ["MSFT", "AAPL"]},
    ],
)
def test_material_public_search_dimensions_do_not_collide(monkeypatch, change) -> None:
    from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRequest

    request = AssetDiscoveryRequest(
        relationship="peer", anchor_symbols=["AAPL", "MSFT"], needs_current_facts=True
    )
    second = request.model_copy(update=change)
    provider, results = _find(monkeypatch, [request, second])
    assert len(provider.calls) == 2
    assert all(
        r.stage_patch["research"]["usage"]["cache_status"] == "miss" for r in results
    )


@pytest.mark.parametrize(
    "kind",
    ["category", "private", "unvalidated", "conflicting"],
)
def test_unproven_discovery_context_bypasses_shared_cache(monkeypatch, kind) -> None:
    """Unvalidated, conflicting, category, and private context stay uncached.

    Planted provider-catalog rows must not admit an anchor the catalog rejects.
    """
    from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRequest

    request = AssetDiscoveryRequest(
        relationship="peer", anchor_symbols=["AAPL"], needs_current_facts=True
    )
    if kind == "category":
        request.relationship = "category"
        request.category_description = "cybersecurity"
    elif kind == "private":
        request.category_description = f"My private holdings {FAKE.uuid4()}"
    elif kind == "unvalidated":
        request.anchor_symbols = ["PANW"]
    else:
        request.asset_class_hint = "crypto"
    provider, results = _find(monkeypatch, [request, request])
    assert len(provider.calls) == 2
    assert all(
        r.stage_patch["research"]["usage"]["cache_status"] == "miss" for r in results
    )
    assert cache_stats()["entries"] == 0


def test_legacy_job_key_cannot_reenable_shared_answer_storage() -> None:
    from argus.domain.research.cache import research_cache_key

    for key in (
        FAKE.sha256(),
        research_cache_key(query="public query", provider_id="test", max_results=5),
    ):
        job = {"cache_key": key, "question": FAKE.sentence()}
        grounded.store_research_packet_for_job(job, _packet(), {"research": {}})
    assert cache_stats()["entries"] == 0


def test_model_backed_search_with_unmodeled_configuration_does_not_share(
    monkeypatch,
) -> None:
    from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRequest

    monkeypatch.setenv("ARGUS_DISCOVERY_SEARCH_PROVIDER", "openrouter_web_search")
    request = AssetDiscoveryRequest(
        relationship="peer", anchor_symbols=["AAPL"], needs_current_facts=True
    )
    provider, _ = _find(monkeypatch, [request, request])
    assert len(provider.calls) == 2
    assert cache_stats()["entries"] == 0


def test_interpret_discovery_reuses_current_decision_provenance_before_state_updates(
    monkeypatch,
) -> None:
    """Empty pre-interpret state still shares once the decision has certified the anchors."""
    from argus.agent_runtime import research_find
    from argus.agent_runtime.stages.interpret import interpret_stage_async
    from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRequest
    from argus.agent_runtime.state.models import StrategySummary, UserState

    from tests.research.test_research_router_absorption import (
        _FakeSearchProvider,
        _search_packet,
        _wire_find,
    )

    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)
    observed: list[tuple[list[str | None], list[str | None]]] = []
    original = research_find.find_assets_stage_result

    async def _observe(**kwargs):
        observed.append(
            (
                [item.canonical_symbol for item in kwargs["state"].resolution_provenance],
                [
                    item.canonical_symbol
                    for item in kwargs["decision"].resolution_provenance
                ],
            )
        )
        return await original(**kwargs)

    monkeypatch.setattr(research_find, "find_assets_stage_result", _observe)
    user = UserState(user_id=FAKE.uuid4(), language_preference="en")

    def interpretation(anchors: list[str], *, relationship: str = "peer"):
        return StructuredInterpretation(
            intent="conversation_followup",
            task_relation="continue",
            user_goal_summary="Find public peers",
            semantic_turn_act="asset_discovery",
            candidate_strategy_draft=StrategySummary(),
            asset_discovery=AssetDiscoveryRequest(
                relationship=relationship,
                anchor_symbols=anchors,
                needs_current_facts=True,
            ),
        )

    class _Interpreter:
        def __init__(self, response: StructuredInterpretation) -> None:
            self.response = response

        async def ainvoke(self, _request):
            return self.response

    async def turn(anchors: list[str], *, relationship: str = "peer"):
        return await interpret_stage_async(
            state=RunState.new(
                current_user_message="Which public companies sit near this one?",
                recent_thread_history=[],
            ),
            user=user,
            latest_task_snapshot=None,
            selected_thread_metadata={},
            structured_interpreter=_Interpreter(
                interpretation(anchors, relationship=relationship)
            ),
        )

    async def run():
        first = await turn(["AAPL"])
        second = await turn([" aapl ", " "])
        changed = await turn(["AAPL"], relationship="comparison")
        return first, second, changed

    first, second, changed = asyncio.run(run())
    assert observed == [([], [])] * 3
    assert len(provider.calls) == 2
    assert provider.calls[0] != provider.calls[1]
    assert [
        result.stage_patch["research"]["usage"]["cache_status"]
        for result in (first, second, changed)
    ] == ["miss", "hit", "miss"]
    assert cache_stats()["entries"] == 2


def test_registered_tool_does_not_share_an_unvalidated_anchor(monkeypatch) -> None:
    """A tool call has no decision. Catalog proof, not planted state, admits it."""
    from argus.agent_runtime.research_tools import PeerExpansionArguments, peer_expansion
    from argus.agent_runtime.state.models import ResolutionProvenance

    from tests.research.test_research_router_absorption import (
        _FakeSearchProvider,
        _search_packet,
        _wire_find,
    )

    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)
    context = _context()
    context.state.resolution_provenance = [
        ResolutionProvenance(
            field="asset_universe",
            raw_text="PANW",
            source="llm_extraction",
            candidate_kind="asset",
            canonical_symbol="PANW",
            asset_class="equity",
            validated_by="provider_catalog",
        )
    ]

    async def invoke():
        return await peer_expansion(
            PeerExpansionArguments(
                request="Find candidate assets around this business",
                relationship="peer",
                anchor_symbols=["PANW"],
                needs_current_facts=True,
            ),
            context=context,
        )

    asyncio.run(invoke())
    asyncio.run(invoke())
    assert len(provider.calls) == 2
    assert context.stage_result.stage_patch["research"]["usage"]["cache_status"] == "miss"
    assert cache_stats()["entries"] == 0


def test_shared_storage_rejects_freeform_packet_even_under_a_current_key() -> None:
    from argus.domain.research.cache import cache_get, cache_put, research_cache_key

    key = research_cache_key(
        query="public", provider_id="perplexity_direct", max_results=5
    )
    cache_put(key, _packet(), ttl_seconds=120.0)
    assert cache_get(key) is None
    assert cache_stats()["entries"] == 0
