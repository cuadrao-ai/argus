"""Forced-reject proofs for signed-in daily compute and research caps."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest
from argus.api import state as api_state
from argus.api.chat.registered_compute_ceiling import claim_registered_compute_turn
from argus.api.chat.research_evidence import (
    RESEARCH_USAGE_RESOURCE,
    claim_research_provider_attempt,
)
from argus.domain.usage_limits import REGISTERED_COMPUTE_CEILING_RESOURCE
from argus.domain.visitor_usage import (
    read_memory_visitor_used,
    registered_account_usage_key,
)

from tests.test_allowance_accounting import client, mock_gateway
from tests.test_guest_compute_ceiling import TURN
from tests.test_registered_compute_ceiling import (
    REGISTERED_HEADERS,
    _registered,
)

__all__ = ["mock_gateway"]

ACCOUNT_KEY = registered_account_usage_key("00000000-0000-0000-0000-000000000001")


def test_concurrent_signed_in_claims_at_one_remaining_accept_exactly_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.visitor_usage_counters.clear()
    monkeypatch.setenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", "2")
    first = claim_registered_compute_turn(account_key=ACCOUNT_KEY)
    assert first.available is True

    barrier = Barrier(8)
    results: list[bool] = []
    results_lock = Lock()

    def _race() -> None:
        barrier.wait(timeout=5)
        admission = claim_registered_compute_turn(account_key=ACCOUNT_KEY)
        with results_lock:
            results.append(admission.available)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: _race(), range(8)))

    assert results.count(True) == 1
    assert results.count(False) == 7
    used = read_memory_visitor_used(
        api_state.store.visitor_usage_counters,
        visitor_key=ACCOUNT_KEY,
        resource=REGISTERED_COMPUTE_CEILING_RESOURCE,
        period="day",
    )
    assert used == 2
    api_state.store.visitor_usage_counters.clear()


def test_concurrent_signed_in_endpoint_claims_reject_the_overshoot(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", "1")
    fake = _registered(mock_gateway, monkeypatch, turns_today=0)
    barrier = Barrier(6)

    def _turn(_: int) -> int:
        barrier.wait(timeout=5)
        response = client.post(
            "/api/v1/chat/stream",
            json=TURN,
            headers=REGISTERED_HEADERS,
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=6) as executor:
        statuses = list(executor.map(_turn, range(6)))

    assert statuses.count(200) == 1
    assert statuses.count(429) == 5
    assert fake.claims == 1
    assert fake.used == 1


def test_concurrent_signed_in_research_claims_at_one_remaining_accept_exactly_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.usage_counters.clear()
    api_state.store.visitor_usage_counters.clear()
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    monkeypatch.setenv("ARGUS_REGISTERED_DAILY_RESEARCH_CEILING", "2")
    first = claim_research_provider_attempt(guest_visitor_key=ACCOUNT_KEY)
    assert first.available is True

    barrier = Barrier(8)
    results: list[bool] = []
    results_lock = Lock()

    def _race() -> None:
        barrier.wait(timeout=5)
        admission = claim_research_provider_attempt(guest_visitor_key=ACCOUNT_KEY)
        with results_lock:
            results.append(admission.available)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: _race(), range(8)))

    assert results.count(True) == 1
    assert results.count(False) == 7
    used = read_memory_visitor_used(
        api_state.store.visitor_usage_counters,
        visitor_key=ACCOUNT_KEY,
        resource=RESEARCH_USAGE_RESOURCE,
        period="day",
    )
    assert used == 2
    api_state.store.usage_counters.clear()
    api_state.store.visitor_usage_counters.clear()
