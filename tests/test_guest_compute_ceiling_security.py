"""Forced-reject proofs for unspoofable visitor keys and atomic claims.

These cases must fail on the pre-fix guest ceiling (X-Forwarded-For identity
and read-then-settle) and pass on this branch.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.chat.guest_compute_ceiling import claim_guest_compute_turn
from argus.api.client_ip import (
    reset_trusted_header_fallback_warning_for_tests,
    resolve_client_ip,
)
from argus.api.guest_access import client_identity, visitor_key_for_request
from argus.domain.usage_limits import GUEST_COMPUTE_CEILING_RESOURCE
from argus.domain.visitor_usage import (
    guest_session_compute_key,
    read_memory_visitor_used,
    visitor_key_for,
)

from tests.test_allowance_accounting import client
from tests.test_client_ip import _request
from tests.test_guest_compute_ceiling import (
    GUEST_HEADERS,
    TURN,
    _guest,
    mock_gateway,
)

__all__ = ["mock_gateway"]


def test_spoofed_xff_from_one_session_hits_the_same_cap(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING", "50")
    fake = _guest(mock_gateway, monkeypatch, turns_today=299, session_used=0)

    first = client.post(
        "/api/v1/chat/stream",
        json=TURN,
        headers={**GUEST_HEADERS, "X-Forwarded-For": "198.51.100.1"},
    )
    second = client.post(
        "/api/v1/chat/stream",
        json=TURN,
        headers={**GUEST_HEADERS, "X-Forwarded-For": "198.51.100.2"},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 429
    assert second.json()["code"] == "too_many_requests"
    assert second.json()["detail"] == "Too many conversation turns today."
    assert fake.claims == 1
    assert fake.visitor_used == 300


def test_session_cap_applies_when_the_trusted_ip_changes(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING", "1")
    fake = _guest(mock_gateway, monkeypatch, turns_today=0, session_used=0)

    first = client.post(
        "/api/v1/chat/stream",
        json=TURN,
        headers={**GUEST_HEADERS, "CF-Connecting-IP": "203.0.113.10"},
    )
    second = client.post(
        "/api/v1/chat/stream",
        json=TURN,
        headers={**GUEST_HEADERS, "CF-Connecting-IP": "203.0.113.20"},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 429
    assert second.json()["detail"] == "Too many conversation turns today."
    assert fake.claims == 1
    assert fake.session_used == 1


def test_concurrent_claims_at_one_remaining_accept_exactly_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.visitor_usage_counters.clear()
    monkeypatch.setenv("CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING", "2")
    visitor_key = visitor_key_for("203.0.113.80")
    session_key = guest_session_compute_key("guest-session-concurrent")
    first = claim_guest_compute_turn(
        visitor_key=visitor_key, session_key=session_key
    )
    assert first.available is True

    barrier = Barrier(8)
    results: list[bool] = []
    results_lock = Lock()

    def _race() -> None:
        barrier.wait(timeout=5)
        admission = claim_guest_compute_turn(
            visitor_key=visitor_key, session_key=session_key
        )
        with results_lock:
            results.append(admission.available)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: _race(), range(8)))

    assert results.count(True) == 1
    assert results.count(False) == 7
    used = read_memory_visitor_used(
        api_state.store.visitor_usage_counters,
        visitor_key=visitor_key,
        resource=GUEST_COMPUTE_CEILING_RESOURCE,
        period="day",
    )
    assert used == 2
    api_state.store.visitor_usage_counters.clear()


def test_concurrent_endpoint_claims_reject_the_overshoot(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING", "50")
    fake = _guest(mock_gateway, monkeypatch, turns_today=299, session_used=0)
    barrier = Barrier(6)

    def _turn(xff: str) -> int:
        barrier.wait(timeout=5)
        response = client.post(
            "/api/v1/chat/stream",
            json=TURN,
            headers={**GUEST_HEADERS, "X-Forwarded-For": xff},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=6) as executor:
        statuses = list(
            executor.map(_turn, [f"198.51.100.{index}" for index in range(6)])
        )

    assert statuses.count(200) == 1
    assert statuses.count(429) == 5
    assert fake.claims == 1
    assert fake.visitor_used == 300


def test_client_identity_is_stable_across_spoofed_xff() -> None:
    first = _request(
        headers={"X-Forwarded-For": "198.51.100.1"},
        peer="192.0.2.10",
    )
    second = _request(
        headers={"X-Forwarded-For": "198.51.100.2"},
        peer="192.0.2.10",
    )
    assert client_identity(first) == client_identity(second) == "192.0.2.10"
    assert visitor_key_for_request(first) == visitor_key_for_request(second)
    assert resolve_client_ip(first) == "192.0.2.10"


def _hosted_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUADRAO_PERSISTENCE_MODE", "supabase")
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")
    reset_trusted_header_fallback_warning_for_tests()


def test_trusted_header_ip_with_port_strips_port() -> None:
    with_port = _request(
        headers={"CF-Connecting-IP": "203.0.113.50:4711"}, peer="10.0.0.8"
    )
    without_port = _request(
        headers={"CF-Connecting-IP": "203.0.113.50"}, peer="10.0.0.9"
    )
    bracketed_v6 = _request(
        headers={"CF-Connecting-IP": "[2001:db8:1:2::1]:443"}, peer="10.0.0.8"
    )

    assert resolve_client_ip(with_port) == "203.0.113.50"
    assert visitor_key_for_request(with_port) == visitor_key_for_request(
        without_port
    )
    assert resolve_client_ip(bracketed_v6) == "2001:db8:1:2::/64"
    # A bare IPv6 address is never mistaken for host:port.
    bare_v6 = _request(headers={"CF-Connecting-IP": "2001:db8:1:2::1"})
    assert resolve_client_ip(bare_v6) == "2001:db8:1:2::/64"
    # A port that is not a port number keeps the value invalid.
    bad_port = _request(
        headers={"CF-Connecting-IP": "203.0.113.50:http"}, peer="10.0.0.8"
    )
    assert resolve_client_ip(bad_port) == "10.0.0.8"


def test_non_canonical_ipv4_falls_back_and_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hosted_env(monkeypatch)
    request = _request(
        headers={"CF-Connecting-IP": "203.000.113.050"}, peer="10.0.0.8"
    )
    with patch("argus.api.client_ip.logger.warning") as warning:
        assert resolve_client_ip(request) == "10.0.0.8"
        assert resolve_client_ip(request) == "10.0.0.8"
    warning.assert_called_once()
    assert warning.call_args.args[0] == "client_ip_rejected_non_canonical"
    assert warning.call_args.kwargs["header"] == "CF-Connecting-IP"
    assert warning.call_args.kwargs["peer"] == "10.0.0.8"
    # The raw header value never reaches the log.
    assert "203.000.113.050" not in str(warning.call_args)


def test_each_client_ip_warning_has_its_own_throttle_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hosted_env(monkeypatch)
    missing = _request(headers={}, peer="10.0.0.8")
    invalid = _request(headers={"CF-Connecting-IP": "garbage"}, peer="10.0.0.8")
    non_canonical = _request(
        headers={"CF-Connecting-IP": "010.0.0.1"}, peer="10.0.0.8"
    )
    with patch("argus.api.client_ip.logger.warning") as warning:
        for request in (missing, invalid, non_canonical) * 2:
            assert resolve_client_ip(request) == "10.0.0.8"
    assert [call.args[0] for call in warning.call_args_list] == [
        "Trusted client-IP header missing; using socket peer",
        "Trusted client-IP header present but invalid; using socket peer",
        "client_ip_rejected_non_canonical",
    ]
