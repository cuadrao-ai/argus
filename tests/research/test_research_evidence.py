"""Metering locks: flat turn meter, classed ledger rows, honest ceiling."""

from __future__ import annotations

from typing import Any

import pytest
from argus.api import state as api_state
from argus.api.chat import research_evidence as evidence
from argus.domain.usage_limits import GUEST_RESEARCH_ALLOWANCE

GUEST = "visitor:guest-under-test"


class _LedgerGateway:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def create_cost_ledger_entry(self, *, entry: dict[str, Any]) -> dict[str, Any]:
        self.entries.append(entry)
        return entry


@pytest.fixture
def memory_store(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.usage_counters.clear()
    yield api_state.store
    api_state.store.usage_counters.clear()


def _research(
    capability_class: str = "fast_quote", cache_status: str = "miss"
) -> dict[str, Any]:
    return {
        "capability_class": capability_class,
        "shape": "fast",
        "usage": {
            "cache_status": cache_status,
            "cost_usd": 0.005,
            "invocations": 1,
            "latency_ms": 640,
        },
    }


def test_flag_off_never_claims_the_ceiling(monkeypatch, memory_store) -> None:
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "false")
    assert evidence.claim_research_provider_attempt().available is True


def test_ceiling_trips_after_the_configured_daily_limit(
    monkeypatch, memory_store
) -> None:
    monkeypatch.setenv("ARGUS_RESEARCH_GLOBAL_DAILY_CEILING", "2")
    assert evidence.claim_research_provider_attempt().available is True
    assert evidence.claim_research_provider_attempt().available is True
    # The ceiling is shared: a third user meets the honest limit.
    assert evidence.claim_research_provider_attempt().available is False


def test_provider_attempts_charge_and_cache_hits_do_not(
    monkeypatch, memory_store
) -> None:
    monkeypatch.setenv("ARGUS_RESEARCH_GLOBAL_DAILY_CEILING", "1")
    evidence.record_research_turn_evidence(
        research=_research(cache_status="hit"),
        user_id="user-1",
        conversation_id="c1",
        message_id="m1",
        request_id="r1",
    )
    assert memory_store.usage_counters == {}
    assert evidence.claim_research_provider_attempt().available is True
    evidence.record_research_turn_evidence(
        research=_research(cache_status="miss"),
        user_id="user-2",
        conversation_id="c2",
        message_id="m2",
        request_id="r2",
    )
    assert evidence.claim_research_provider_attempt().available is False


def test_every_research_turn_records_its_capability_class(monkeypatch) -> None:
    gateway = _LedgerGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    for capability_class, cache_status in (
        ("fast_quote", "miss"),
        ("balanced_lookup", "hit"),
        ("thorough_research", "miss"),
        ("screening", "miss"),
        ("peer_expansion", "bypass"),
    ):
        evidence.record_research_turn_evidence(
            research=_research(capability_class, cache_status),
            user_id="user-1",
            conversation_id="c1",
            message_id=f"m-{capability_class}",
            request_id="r1",
        )

    recorded = [
        (e["task"], e["usage_metadata"]["capability_class"]) for e in gateway.entries
    ]
    assert recorded == [
        ("fast_quote", "fast_quote"),
        ("balanced_lookup", "balanced_lookup"),
        ("thorough_research", "thorough_research"),
        ("screening", "screening"),
        ("peer_expansion", "peer_expansion"),
    ]
    for entry in gateway.entries:
        assert entry["feature_area"] == "research_rail"
        assert entry["source"] == "research"
    # Cache hits and bypasses record class truth with zero billable quantity.
    by_message = {e["message_id"]: e for e in gateway.entries}
    assert by_message["m-balanced_lookup"]["billable_quantity"] == 0
    assert by_message["m-peer_expansion"]["billable_quantity"] == 0
    assert by_message["m-fast_quote"]["billable_quantity"] == 1


def test_ceiling_claim_failure_fails_closed(monkeypatch) -> None:
    class ExplodingGateway:
        @property
        def client(self):
            raise RuntimeError("no database")

    monkeypatch.setattr(api_state, "supabase_gateway", ExplodingGateway())
    assert evidence.claim_research_provider_attempt().available is False


@pytest.mark.parametrize("invocations", [0, 1])
def test_repeated_tool_calls_keep_distinct_cost_correlations(
    monkeypatch, invocations: int
) -> None:
    from faker import Faker

    fake = Faker()
    gateway = _LedgerGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    request_id, user_id, conversation_id, message_id = [fake.uuid4() for _ in range(4)]
    call_ids = [fake.uuid4(), fake.uuid4()]
    for call_id in call_ids:
        research = _research()
        research["usage"]["invocations"] = invocations
        evidence.record_research_turn_evidence(
            research=research,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=request_id,
            tool_call_id=call_id,
        )
    assert [entry["request_id"] for entry in gateway.entries] == [request_id] * 2
    assert [
        entry["usage_metadata"]["tool_call_id"] for entry in gateway.entries
    ] == call_ids
    assert len({entry["correlation_id"] for entry in gateway.entries}) == 2
    assert all(entry["billable_quantity"] == 1 for entry in gateway.entries)
    assert all(entry["cost_amount"] == 0.005 for entry in gateway.entries)


def test_supabase_claims_global_and_guest_capacity_in_one_rpc(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class Result:
        data = {"available": True, "guest_exhausted": False}

        def execute(self):
            return self

    class Client:
        def rpc(self, name: str, params: dict[str, Any]):
            calls.append((name, params))
            return Result()

    class Gateway:
        client = Client()

    monkeypatch.setenv("ARGUS_RESEARCH_GLOBAL_DAILY_CEILING", "5000")
    monkeypatch.setattr(api_state, "supabase_gateway", Gateway())

    allowance = evidence.claim_research_provider_attempt(
        guest_visitor_key=GUEST,
    )

    assert allowance.available is True
    assert calls == [
        (
            "claim_research_usage",
            {
                "p_guest_visitor_key": GUEST,
                "p_resource": "research_searches",
                "p_global_visitor_key": "global:research",
                "p_global_limit": 5000,
                "p_guest_limit": 3,
            },
        )
    ]


# --- the guest research allowance (3/day, one ceiling for every shape) ------


@pytest.fixture
def guest_store(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.usage_counters.clear()
    api_state.store.visitor_usage_counters.clear()
    yield api_state.store
    api_state.store.usage_counters.clear()
    api_state.store.visitor_usage_counters.clear()


def _spend(times: int, *, guest_visitor_key: str | None = GUEST) -> None:
    for _ in range(times):
        allowance = evidence.claim_research_provider_attempt(
            guest_visitor_key=guest_visitor_key,
        )
        assert allowance.available


def test_a_guest_gets_three_research_questions_a_day(guest_store) -> None:
    for spent in range(GUEST_RESEARCH_ALLOWANCE):
        assert evidence.claim_research_provider_attempt(
            guest_visitor_key=GUEST
        ).available, f"a guest must still have research after {spent} of it"
    assert not evidence.claim_research_provider_attempt(guest_visitor_key=GUEST).available


def test_the_exhausted_guest_is_told_it_was_their_own_allowance(guest_store) -> None:
    """The honesty lock: a guest who spent their three must not be told the
    shared capacity ran out, because it did not."""
    _spend(GUEST_RESEARCH_ALLOWANCE)
    allowance = evidence.claim_research_provider_attempt(guest_visitor_key=GUEST)
    assert allowance.available is False
    assert allowance.guest_exhausted is True


def test_a_shared_outage_is_never_blamed_on_the_guest(guest_store, monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_RESEARCH_GLOBAL_DAILY_CEILING", "1")
    _spend(1)
    allowance = evidence.claim_research_provider_attempt(guest_visitor_key=GUEST)
    assert allowance.available is False
    assert allowance.guest_exhausted is False


def test_one_guest_never_spends_another_guests_allowance(guest_store) -> None:
    _spend(GUEST_RESEARCH_ALLOWANCE)
    assert not evidence.claim_research_provider_attempt(guest_visitor_key=GUEST).available
    assert evidence.claim_research_provider_attempt(
        guest_visitor_key="visitor:someone-else"
    ).available


def test_a_signed_in_user_has_a_daily_research_ceiling(guest_store, monkeypatch) -> None:
    from argus.domain.usage_limits import registered_daily_research_ceiling
    from argus.domain.visitor_usage import registered_account_usage_key

    monkeypatch.delenv("ARGUS_REGISTERED_DAILY_RESEARCH_CEILING", raising=False)
    assert registered_daily_research_ceiling() == 15
    key = registered_account_usage_key("00000000-0000-0000-0000-000000000099")
    for _ in range(15):
        assert evidence.claim_research_provider_attempt(
            guest_visitor_key=key
        ).available
    sixteenth = evidence.claim_research_provider_attempt(guest_visitor_key=key)
    assert sixteenth.available is False
    assert sixteenth.registered_exhausted is True
    assert sixteenth.guest_exhausted is False


def test_a_cache_hit_costs_a_guest_nothing(guest_store) -> None:
    for _ in range(GUEST_RESEARCH_ALLOWANCE * 2):
        evidence.record_research_turn_evidence(
            research=_research(cache_status="hit"),
            user_id="g",
            conversation_id=None,
            message_id=None,
            request_id=None,
        )
    assert guest_store.visitor_usage_counters == {}
    assert evidence.claim_research_provider_attempt(guest_visitor_key=GUEST).available


def test_every_shape_draws_on_the_same_guest_allowance(guest_store) -> None:
    """One ceiling, not one per tier: a stranger cannot tell a fast lookup
    from a thorough comparison, so the rail's own tiering must not decide how
    much research they get."""
    for capability_class in ("fast_quote", "thorough_research", "screening"):
        assert evidence.claim_research_provider_attempt(guest_visitor_key=GUEST).available
        evidence.record_research_turn_evidence(
            research=_research(capability_class=capability_class),
            user_id="g",
            conversation_id=None,
            message_id=None,
            request_id=None,
        )
    assert not evidence.claim_research_provider_attempt(guest_visitor_key=GUEST).available


def test_flag_off_leaves_a_guest_unmetered(monkeypatch, guest_store) -> None:
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "false")
    _spend(GUEST_RESEARCH_ALLOWANCE * 3)
    assert evidence.claim_research_provider_attempt(guest_visitor_key=GUEST).available


def test_the_visitor_key_is_a_digest_not_an_address() -> None:
    key = evidence.guest_research_visitor_key(
        is_guest=True, client_identity="203.0.113.42"
    )
    assert key is not None
    assert "203.0.113.42" not in key
    assert evidence.guest_research_visitor_key(
        is_guest=False,
        client_identity="203.0.113.42",
        user_id="00000000-0000-0000-0000-000000000099",
    ) == "user:00000000-0000-0000-0000-000000000099"
