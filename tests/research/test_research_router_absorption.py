"""Section 11b locks: one router, one cache, one meter, one provider layer.

Discovery's asset-finding is an operation of the rail. These tests pin the
absorption: the rail classifier owns question shape for both entries, a
comparison of named assets reaches grounded research from a typed discovery
act, find turns cache and meter through the research scheme, and the routing
classification can never be starved by the turn-call corridor.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest
from argus.agent_runtime import research_answer as ra
from argus.agent_runtime import research_grounded as grounded
from argus.agent_runtime import turn_execution
from argus.agent_runtime.discovery import composer as composer_module
from argus.agent_runtime.discovery.contracts import (
    DiscoveryExtraction,
    ExtractedCandidate,
)
from argus.agent_runtime.stages.interpret_types import (
    AssetDiscoveryRequest,
    InterpretDecision,
    StructuredInterpretation,
)
from argus.agent_runtime.state.models import (
    ResponseProfile,
    RunState,
    StrategySummary,
    UserState,
)
from argus.domain.research.admission import (
    ResearchAttemptAdmission,
    research_attempt_admission_context,
)
from argus.domain.research.perplexity_agent import PerplexityAgentClient
from argus.domain.research.search import (
    SearchResultPacket,
    sanitize_search_result,
)
from argus.domain.research.search import selection as selection_module

from tests.research.conftest import RecordingTransport, agent_response, set_research_query

USER = UserState(user_id="rail-user", language_preference="en")


@dataclass(frozen=True)
class _Asset:
    canonical_symbol: str
    asset_class: str
    name: str = ""


def _interpretation() -> StructuredInterpretation:
    return StructuredInterpretation(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        user_goal_summary="question",
        semantic_turn_act="asset_discovery",
        requires_clarification=False,
        candidate_strategy_draft=StrategySummary(),
    )


def _decision(
    *,
    relationship: str = "comparison",
    category_description: str | None = None,
    anchor_symbols: list[str] | None = None,
    needs_current_facts: bool = True,
) -> InterpretDecision:
    return InterpretDecision(
        intent="conversation_followup",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="discovery",
        confidence=0.9,
        effective_response_profile=ResponseProfile(
            effective_tone="friendly",
            effective_verbosity="medium",
            effective_expertise_mode="beginner",
        ),
        semantic_turn_act="asset_discovery",
        asset_discovery=AssetDiscoveryRequest(
            relationship=relationship,
            category_description=category_description,
            anchor_symbols=anchor_symbols or [],
            asset_class_hint="equity",
            needs_current_facts=needs_current_facts,
        ),
    )


def _state(message: str) -> RunState:
    return RunState.new(current_user_message=message, recent_thread_history=[])


def _search_packet() -> SearchResultPacket:
    results = [
        sanitize_search_result(
            title=f"Streaming rivals {index}",
            url=f"https://example.com/{index}",
            snippet="CrowdStrike leads the segment.",
            source_date="2026-08-01",
        )
        for index in range(3)
    ]
    return SearchResultPacket(
        results=[result for result in results if result is not None],
        retrieved_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        latency_ms=640,
        provider_id="perplexity_direct",
        cost_usd=0.005,
    )


class _FakeSearchProvider:
    def __init__(self, packet: SearchResultPacket) -> None:
        self._packet = packet
        self.calls: list[str] = []

    def search(self, query: str, *, max_results: int, timeout_seconds: float):
        self.calls.append(query)
        return self._packet


def _wire_find(
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider: _FakeSearchProvider | None = None,
) -> None:
    if provider is not None:
        monkeypatch.setattr(
            selection_module,
            "search_provider_for_config",
            lambda **kwargs: provider,
            raising=True,
        )

    async def _fake_extract(**kwargs: Any) -> DiscoveryExtraction:
        return DiscoveryExtraction(
            candidates=[
                ExtractedCandidate(
                    name="CrowdStrike",
                    symbol_guess="CRWD",
                    reason_text="Named as a leading vendor.",
                    source_indices=[0],
                )
            ]
        )

    monkeypatch.setattr(composer_module, "extract_candidates", _fake_extract)
    monkeypatch.setattr(composer_module, "name_candidates", _fake_extract)

    async def _fake_voice(**kwargs: Any) -> str:
        return "Here is what I verified."

    monkeypatch.setattr(composer_module, "_voiced_discovery_response", _fake_voice)

    def _resolve(symbol: str, **_: Any) -> _Asset:
        cleaned = symbol.strip().upper()
        if cleaned != "CRWD":
            raise ValueError(f"unknown symbol {cleaned}")
        return _Asset("CRWD", "equity", name="CrowdStrike Holdings")

    monkeypatch.setattr(composer_module, "resolve_asset", _resolve)


def test_named_comparison_on_a_discovery_act_reaches_grounded_research(
    monkeypatch,
) -> None:
    """The defect section 11b names: 'Compare Costco against Walmart and
    Target' arrives as a typed discovery act, and the rail classifier, not
    the act taxonomy, decides it is grounded cross-company research."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="cross_company",
        symbols=["NFLX", "AAPL"],
    )
    result = asyncio.run(
        ra.discovery_turn_stage_result(
            interpretation=_interpretation(),
            decision=_decision(anchor_symbols=["NFLX"]),
            state=_state("Compare Netflix against Apple"),
            user=USER,
        )
    )
    assert result is not None
    # A thorough job request is the grounded-research artifact; the discovery
    # sidecar never appears because the find operation never ran.
    assert "research_job_request" in result.stage_patch
    assert "discovery" not in result.stage_patch


def test_discovery_shaped_turn_runs_the_find_operation_with_the_typed_request(
    monkeypatch,
) -> None:
    set_research_query(monkeypatch, globals(), question_kind="find_assets", symbols=[])
    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)

    result = asyncio.run(
        ra.discovery_turn_stage_result(
            interpretation=_interpretation(),
            decision=_decision(
                relationship="category",
                category_description="cybersecurity stocks",
            ),
            state=_state("Find me cybersecurity stocks"),
            user=USER,
        )
    )
    assert result is not None
    assert provider.calls, "the find operation must run the search"
    discovery = result.stage_patch["discovery"]
    assert [c["symbol"] for c in discovery["candidates"]] == ["CRWD"]
    research = result.stage_patch["research"]
    assert research["shape"] == "find"
    assert research["capability_class"] == "screening"
    assert research["usage"]["cache_status"] == "miss"
    assert research["peers"][0]["symbol"] == "CRWD"
    assert research["follow_up"]["open_thread"]["category"] == "cybersecurity stocks"


def test_screening_classification_keeps_a_typed_discovery_turn_on_the_find_op(
    monkeypatch,
) -> None:
    """Issue #344: 'find me stocks that recently IPO'ed' states a condition,
    so the classifier reads screening; the turn is still an ask for candidate
    assets and must keep the discovery surface, not become a narrative."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="screening",
        symbols=[],
        screening_criteria=["recently IPO'ed"],
    )
    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)

    result = asyncio.run(
        ra.discovery_turn_stage_result(
            interpretation=_interpretation(),
            decision=_decision(
                relationship="category",
                category_description="stocks that recently IPO'ed",
            ),
            state=_state("find me stocks that have recently IPO'ed"),
            user=USER,
        )
    )
    assert result is not None
    assert provider.calls, "the find operation must run the search"
    assert result.stage_patch["discovery"]["candidates"]
    patch = result.patch
    assert patch["semantic_turn_act"] == "asset_discovery"
    assert patch["asset_discovery"] is not None


def test_diverted_discovery_turn_keeps_its_typed_identity(monkeypatch) -> None:
    """A legitimate diversion (named comparison) may serve grounded research,
    but the patch keeps the typed act and payload instead of relabeling the
    turn educational_question (#344 macro class)."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="cross_company",
        symbols=["NFLX", "AAPL"],
    )
    result = asyncio.run(
        ra.discovery_turn_stage_result(
            interpretation=_interpretation(),
            decision=_decision(anchor_symbols=["NFLX"]),
            state=_state("Compare Netflix against Apple"),
            user=USER,
        )
    )
    assert result is not None
    assert "research_job_request" in result.stage_patch
    patch = result.patch
    assert patch["semantic_turn_act"] == "asset_discovery"
    assert patch["asset_discovery"] is not None
    assert any(
        code.startswith("research_answer_") for code in patch["reason_codes"]
    ), patch["reason_codes"]


def test_filled_payload_enters_the_rail_with_a_non_discovery_act(monkeypatch) -> None:
    """Issue #344: the typed payload is the rail's discovery gate; an
    educational act label on the same turn does not lose it."""
    set_research_query(monkeypatch, globals(), question_kind="find_assets", symbols=[])
    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)

    decision = _decision(
        relationship="category",
        category_description="cybersecurity stocks",
    ).model_copy(update={"semantic_turn_act": "educational_question"})
    result = asyncio.run(
        ra.discovery_turn_stage_result(
            interpretation=_interpretation(),
            decision=decision,
            state=_state("Find me cybersecurity stocks"),
            user=USER,
        )
    )
    assert result is not None
    assert provider.calls, "the find operation must run the search"
    assert result.stage_patch["discovery"]["candidates"]


def test_missing_primary_question_shape_never_loses_a_typed_discovery_turn(
    monkeypatch,
) -> None:
    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)

    result = asyncio.run(
        ra.discovery_turn_stage_result(
            interpretation=_interpretation(),
            decision=_decision(
                relationship="category",
                category_description="cybersecurity stocks",
            ),
            state=_state("Find me cybersecurity stocks"),
            user=USER,
        )
    )
    assert result is not None
    assert result.stage_patch["discovery"]["candidates"]


def test_find_turns_share_the_research_cache_across_users(monkeypatch) -> None:
    """One cache: the second identical find question consumes no provider
    search, whoever asks it."""
    set_research_query(monkeypatch, globals(), question_kind="find_assets", symbols=[])
    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)
    decision = _decision(relationship="comparison", anchor_symbols=["AAPL"])

    first = asyncio.run(
        ra.discovery_turn_stage_result(
            interpretation=_interpretation(),
            decision=decision,
            state=_state("Find peers of AAPL"),
            user=USER,
        )
    )
    second = asyncio.run(
        ra.discovery_turn_stage_result(
            interpretation=_interpretation(),
            decision=decision,
            state=_state("Find peers of AAPL"),
            user=UserState(user_id="someone-else", language_preference="en"),
        )
    )
    assert first is not None and second is not None
    assert len(provider.calls) == 1, "the shared cache must absorb the second search"
    assert second.stage_patch["research"]["usage"]["cache_status"] == "hit"
    assert second.stage_patch["research"]["usage"]["invocations"] == 0
    # The rendered discovery experience is unchanged on a hit.
    assert [c["symbol"] for c in second.stage_patch["discovery"]["candidates"]] == [
        "CRWD"
    ]


def test_exhausted_research_ceiling_degrades_find_to_cheap_verified_rows(
    monkeypatch,
) -> None:
    """One meter: the shared research ceiling gates the search; exhaustion
    still answers with resolver-verified rows, never a dead end."""
    set_research_query(monkeypatch, globals(), question_kind="find_assets", symbols=[])
    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)

    with research_attempt_admission_context(
        lambda: ResearchAttemptAdmission(available=False)
    ):
        result = asyncio.run(
            ra.discovery_turn_stage_result(
                interpretation=_interpretation(),
                decision=_decision(
                    relationship="category",
                    category_description="cybersecurity stocks",
                ),
                state=_state("Find me cybersecurity stocks"),
                user=USER,
            )
        )
    assert result is not None
    assert provider.calls == [], "an exhausted ceiling must not search"
    research = result.stage_patch["research"]
    assert research["usage"]["cache_status"] == "bypass"
    assert research["usage"]["invocations"] == 0
    assert result.stage_patch["discovery"]["candidates"]
    answer = result.stage_patch["assistant_response"].lower()
    assert "shared research capacity" in answer
    assert "free research" not in answer


def test_atomic_claim_denial_stops_a_find_provider_call(monkeypatch) -> None:
    """A late denial after the cache miss still serves cheap verified rows."""
    set_research_query(monkeypatch, globals(), question_kind="find_assets", symbols=[])
    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)

    with research_attempt_admission_context(
        lambda: ResearchAttemptAdmission(available=False, guest_exhausted=True)
    ):
        result = asyncio.run(
            ra.discovery_turn_stage_result(
                interpretation=_interpretation(),
                decision=_decision(
                    relationship="category",
                    category_description="cybersecurity stocks",
                ),
                state=_state("Find me cybersecurity stocks"),
                user=USER,
            )
        )

    assert result is not None
    assert provider.calls == []
    research = result.stage_patch["research"]
    assert research["usage"]["cache_status"] == "bypass"
    assert research["degraded"] == {"code": "research_capacity_exhausted"}
    assert result.stage_patch["discovery"]["candidates"]
    answer = result.stage_patch["assistant_response"].lower()
    assert "free research" in answer
    assert "shared research capacity" not in answer


@pytest.mark.parametrize(
    "provider_id",
    ["perplexity_direct", "openrouter_web_search"],
)
def test_unconfigured_find_provider_never_claims_capacity(
    monkeypatch, provider_id
) -> None:
    set_research_query(monkeypatch, globals(), question_kind="find_assets", symbols=[])
    monkeypatch.setenv("ARGUS_DISCOVERY_SEARCH_PROVIDER", provider_id)
    monkeypatch.setenv("PERPLEXITY_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("ARGUS_DISCOVERY_OPENROUTER_SEARCH_MODEL", "")
    _wire_find(monkeypatch)

    def reject_claim() -> ResearchAttemptAdmission:
        raise AssertionError("an unconfigured provider must not claim capacity")

    with research_attempt_admission_context(reject_claim):
        result = asyncio.run(
            ra.discovery_turn_stage_result(
                interpretation=_interpretation(),
                decision=_decision(
                    relationship="category",
                    category_description="cybersecurity stocks",
                ),
                state=_state("Find me cybersecurity stocks"),
                user=USER,
            )
        )

    assert result is not None
    assert result.stage_patch["research"]["degraded"] == {"code": "search_not_configured"}


def test_knowledge_entry_find_shape_uses_primary_discovery_request(
    monkeypatch,
) -> None:
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="find_assets",
        symbols=["AAPL"],
        discovery_category="AI stocks",
    )
    provider = _FakeSearchProvider(_search_packet())
    _wire_find(monkeypatch, provider=provider)

    result = asyncio.run(
        ra.research_answer_stage_result(
            interpretation=_interpretation().model_copy(
                update={
                    "asset_discovery": AssetDiscoveryRequest(
                        relationship="peer",
                        anchor_symbols=["AAPL"],
                        category_description="AI stocks",
                        needs_current_facts=False,
                    ),
                }
            ),
            state=_state("What are some AI stocks like Apple?"),
            user=USER,
        )
    )
    assert result is not None
    # Cheap verified rows are the default for knowledge-entry finds: no
    # search unless the interpreter said current facts are required.
    assert provider.calls == []
    research = result.stage_patch["research"]
    assert research["capability_class"] == "peer_expansion"
    assert research["anchor_symbols"] == ["AAPL"]


def test_flag_off_discovery_turns_take_the_pre_rail_composer_path(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "false")

    async def explode(**_kwargs: Any):
        raise AssertionError("the rail classifier must not run with the flag off")

    monkeypatch.setattr(ra, "_dispatch", explode)
    seen: dict[str, Any] = {}

    async def legacy(**kwargs: Any):
        seen.update(kwargs)
        return None

    import argus.agent_runtime.discovery as discovery_package

    monkeypatch.setattr(discovery_package, "discovery_stage_result_for", legacy)

    result = asyncio.run(
        ra.discovery_turn_stage_result(
            interpretation=_interpretation(),
            decision=_decision(),
            state=_state("Find me cybersecurity stocks"),
            user=USER,
        )
    )
    assert result is None
    assert seen, "flag off must delegate to the pre-rail composer wrapper"


def test_routing_classification_holds_a_reserved_permit(monkeypatch) -> None:
    """Trigger reliability at default configuration: with the corridor fully
    consumed by interpreter audits, the routing call still gets a permit;
    only the first one, and only with the rail on."""
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    with turn_execution.turn_execution_scope(entry_state={}) as execution:
        for _ in range(execution.call_allowance):
            assert turn_execution.reserve_provider_call("interpretation") is not None
        assert turn_execution.reserve_provider_call("interpretation") is None
        permit = turn_execution.reserve_provider_call("knowledge_route")
        assert permit is not None, "routing must never be starved by audits"
        assert (
            turn_execution.reserve_provider_call("knowledge_route") is None
        ), "the reservation is one-shot; repeats compete in the corridor"
        execution.terminal = "finished"

    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "false")
    with turn_execution.turn_execution_scope(entry_state={}) as execution:
        for _ in range(execution.call_allowance):
            assert turn_execution.reserve_provider_call("interpretation") is not None
        assert (
            turn_execution.reserve_provider_call("knowledge_route") is None
        ), "flag off keeps the exact pre-rail competition"
        execution.terminal = "finished"


def test_etf_constituents_shape_grounds_and_offers_holdings(monkeypatch) -> None:
    """Section 2's ETF constituents ability: the holdings table becomes
    resolver-verified pairs, so top constituents are offerable and exposure
    vehicles ground through the table instead of being dropped."""
    set_research_query(
        monkeypatch, globals(), question_kind="etf_constituents", symbols=["SPY"]
    )
    holdings_table = (
        "## SPY ETF Holdings\n\n"
        "| etf | symbol | name | shares | weight | market_value |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| SPY | NVDA | NVIDIA CORP | 294,018,439 | 7.99 | 64,889,541,926 |\n"
        "| SPY | AAPL | APPLE INC | 178,303,413 | 6.88 | 55,826,450,339 |\n"
        "| SPY | MSFT | MICROSOFT CORP | 90,179,261 | 5.45 | 44,255,335,196 |\n"
    )
    document = agent_response(
        text="SPY's top holdings are NVDA, AAPL, and MSFT.", tickers=["SPY"]
    )
    document["output"][1]["results"][0] = {
        "category": "etf_holdings",
        "content": holdings_table,
        "sources": [],
        "tickers": ["SPY"],
    }
    document["output"][1]["categories"] = ["etf_holdings"]
    transport = RecordingTransport([document])
    monkeypatch.setattr(
        grounded, "_client", lambda: PerplexityAgentClient("k", transport=transport)
    )

    result = asyncio.run(
        ra.research_answer_stage_result(
            interpretation=_interpretation(),
            state=_state("What are the top holdings inside SPY?"),
            user=USER,
        )
    )
    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["shape"] == "balanced"
    assert sidecar["capability_class"] == "balanced_lookup"
    # Weight order survives the parse; the resolver verified each holding.
    offered = [p["symbol"] for p in sidecar["peers"]]
    assert offered[:2] == ["NVDA", "AAPL"]
    rows = result.stage_patch["next_experiments"]["rows"]
    assert rows, "top constituents must be runnable"


def test_follow_up_producer_block_rides_every_research_sidecar(monkeypatch) -> None:
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="cross_company",
        symbols=["NFLX", "AAPL"],
        period_of_interest="last three years",
    )
    transport = RecordingTransport([])
    monkeypatch.setattr(
        grounded, "_client", lambda: PerplexityAgentClient("k", transport=transport)
    )
    first = asyncio.run(
        ra.research_answer_stage_result(
            interpretation=_interpretation(),
            state=_state("Compare Netflix and Apple over three years"),
            user=USER,
        )
    )
    assert first is not None
    job_request = first.stage_patch["research_job_request"]

    from argus.domain.research.perplexity_agent import _packet_from_response

    packet = _packet_from_response(agent_response(text="Compared."), latency_ms=900)
    composed = ra.compose_completed_research(job_request=job_request, packet=packet)
    follow_up = composed["research"]["follow_up"]
    assert follow_up["schema_version"] == "argus_research_follow_up/v1"
    assert [s["symbol"] for s in follow_up["subjects"]] == ["NFLX", "AAPL"]
    assert follow_up["comparison_set"] == ["NFLX", "AAPL"]
    assert follow_up["open_thread"]["shape"] == "thorough"
    assert follow_up["open_thread"]["period_of_interest"] == "last three years"


def test_grounded_holdings_and_quotes_never_enter_shared_cache(monkeypatch) -> None:
    """The packet data class does not make a freeform answer safe to share."""
    from argus.domain.research.cache import cache_stats

    set_research_query(
        monkeypatch, globals(), question_kind="etf_constituents", symbols=["SPY"]
    )
    holdings_document = agent_response(text="SPY top holdings.", tickers=["SPY"])
    holdings_document["output"][1]["results"][0] = {
        "category": "etf_holdings",
        "content": (
            "| etf | symbol | name | weight |\n| --- | --- | --- | --- |\n"
            "| SPY | NVDA | NVIDIA CORP | 7.99 |\n"
        ),
        "sources": [],
        "tickers": ["SPY"],
    }
    holdings_document["output"][1]["categories"] = ["etf_holdings"]
    transport = RecordingTransport([holdings_document])
    monkeypatch.setattr(
        grounded, "_client", lambda: PerplexityAgentClient("k", transport=transport)
    )
    result = asyncio.run(
        ra.research_answer_stage_result(
            interpretation=_interpretation(),
            state=_state("What are the top holdings inside SPY?"),
            user=USER,
        )
    )
    assert result is not None
    assert cache_stats()["entries"] == 0

    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    quote_transport = RecordingTransport([agent_response()])
    monkeypatch.setattr(
        grounded,
        "_client",
        lambda: PerplexityAgentClient("k", transport=quote_transport),
    )
    result = asyncio.run(
        ra.research_answer_stage_result(
            interpretation=_interpretation(),
            state=_state("What is Apple trading at right now?"),
            user=USER,
        )
    )
    assert result is not None
    assert cache_stats()["entries"] == 0
