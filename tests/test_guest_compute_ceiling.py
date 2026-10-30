"""The silent anti-abuse ceiling on guest compute turns.

Conversation is free and reports no limit; a guest's turns still count
against daily ceilings that are never rendered. These tests prove the
atomic entry claim, the silence in ``GET /me/usage``, and that the
refusal-log observer still fires on the terminal after the claim.
"""

from __future__ import annotations

from datetime import timedelta
from threading import Lock
from types import SimpleNamespace
from typing import Any

import pytest
from argus.api.chat import refusal_evidence
from argus.api.chat.guest_compute_ceiling import guest_compute_settlement
from argus.api.guest_access import (
    AccountContext,
    guest_capabilities,
    registered_account_context,
)
from argus.domain.store import utcnow
from argus.domain.usage_limits import (
    GUEST_COMPUTE_CEILING_RESOURCE,
    guest_session_daily_turn_ceiling,
)

from tests.test_allowance_accounting import (
    _assistant_settlements,
    _configure_guest_account,
    client,
    mock_gateway,
)

__all__ = ["mock_gateway"]

GUEST_HEADERS = {"Authorization": "Bearer guest-token"}
TURN = {"conversation_id": "conv-1", "message": "Test TSLA dip idea"}


class _FakeComputeClaimClient:
    """Thread-safe stub for claim_guest_compute_usage plus leftover reads."""

    def __init__(
        self,
        *,
        visitor_used: int = 0,
        session_used: int = 0,
    ) -> None:
        self.visitor_used = visitor_used
        self.session_used = session_used
        self.claims = 0
        self._lock = Lock()
        self._resource: str | None = None

    def table(self, name: str) -> "_FakeComputeClaimClient":
        assert name == "visitor_usage_counters"
        return self

    def select(self, *_args: Any) -> "_FakeComputeClaimClient":
        return self

    def eq(self, column: str, value: Any) -> "_FakeComputeClaimClient":
        if column == "resource":
            self._resource = str(value)
        return self

    def limit(self, *_args: Any) -> "_FakeComputeClaimClient":
        return self

    def rpc(self, name: str, params: dict[str, Any]) -> SimpleNamespace:
        assert name == "claim_guest_compute_usage"
        with self._lock:
            visitor_limit = int(params["p_visitor_limit"])
            session_limit = int(params["p_session_limit"])
            visitor_exhausted = self.visitor_used >= visitor_limit
            session_exhausted = self.session_used >= session_limit
            if visitor_exhausted or session_exhausted:
                data = {
                    "available": False,
                    "visitor_exhausted": visitor_exhausted,
                    "session_exhausted": session_exhausted,
                }
            else:
                self.visitor_used += 1
                self.session_used += 1
                self.claims += 1
                data = {
                    "available": True,
                    "visitor_exhausted": False,
                    "session_exhausted": False,
                }
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))

    def execute(self) -> Any:
        used = self.visitor_used if self._resource else 0
        rows = [{"used_count": used}] if used else []
        return SimpleNamespace(data=rows)


def _guest(
    mock_gateway,
    monkeypatch: pytest.MonkeyPatch,
    *,
    turns_today: int,
    session_used: int | None = None,
) -> _FakeComputeClaimClient:
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    _configure_guest_account(mock_gateway)
    fake = _FakeComputeClaimClient(
        visitor_used=turns_today,
        session_used=turns_today if session_used is None else session_used,
    )
    mock_gateway.client = fake
    return fake


def _terminal_message_ids(mock_gateway) -> set[str]:
    ids: set[str] = set()
    for call in mock_gateway.finalize_chat_turn.call_args_list:
        ids.add(call.kwargs["message"].id)
    for call in mock_gateway.create_message.call_args_list:
        if call.kwargs.get("role") == "assistant":
            ids.add("msg-1")
    return ids


def test_session_ceiling_reads_env_or_the_code_owned_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING", raising=False)
    assert guest_session_daily_turn_ceiling() == 100
    monkeypatch.setenv("CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING", "25")
    assert guest_session_daily_turn_ceiling() == 25
    monkeypatch.setenv("CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING", "0")
    assert guest_session_daily_turn_ceiling() == 100
    monkeypatch.setenv("CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING", "nope")
    assert guest_session_daily_turn_ceiling() == 100


def test_guest_turn_claims_one_ceiling_unit_at_entry(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
):
    fake = _guest(mock_gateway, monkeypatch, turns_today=5)

    response = client.post("/api/v1/chat/stream", json=TURN, headers=GUEST_HEADERS)

    assert response.status_code == 200, response.text
    assert fake.claims == 1
    assert fake.visitor_used == 6
    assert _assistant_settlements(mock_gateway) == []
    mock_gateway.check_usage_limits.assert_not_called()


def test_claim_error_is_503_not_the_daily_cap(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")
    fake = _guest(mock_gateway, monkeypatch, turns_today=0)

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("rpc missing")

    fake.rpc = boom  # type: ignore[method-assign]

    response = client.post("/api/v1/chat/stream", json=TURN, headers=GUEST_HEADERS)

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "guest_compute_claim_unavailable"
    assert body["detail"] == "Argus could not start this turn. Please try again."
    assert response.headers["Retry-After"] == "15"
    assert "Too many conversation turns today." not in response.text
    mock_gateway.create_message.assert_not_called()


def test_guest_at_the_ceiling_is_refused_at_entry_without_charging(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
):
    from argus.domain.usage_limits import GUEST_COMPUTE_DAILY_CEILING

    fake = _guest(
        mock_gateway, monkeypatch, turns_today=GUEST_COMPUTE_DAILY_CEILING
    )

    response = client.post("/api/v1/chat/stream", json=TURN, headers=GUEST_HEADERS)

    assert response.status_code == 429
    assert response.json()["code"] == "too_many_requests"
    assert response.json()["detail"] == "Too many conversation turns today."
    assert int(response.headers["Retry-After"]) >= 1
    assert fake.claims == 0
    mock_gateway.create_message.assert_not_called()
    assert _assistant_settlements(mock_gateway) == []


def test_ceiling_never_appears_in_usage(mock_gateway, monkeypatch: pytest.MonkeyPatch):
    from argus.domain.usage_limits import GUEST_COMPUTE_DAILY_CEILING

    _guest(mock_gateway, monkeypatch, turns_today=GUEST_COMPUTE_DAILY_CEILING - 1)
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")

    response = client.get("/api/v1/me/usage", headers=GUEST_HEADERS)

    assert response.status_code == 200
    assert GUEST_COMPUTE_CEILING_RESOURCE not in response.text
    compute = response.json()["allowances"]["compute"]
    assert compute["available_now"] is True
    assert compute["limiting_window"] is None


def test_registered_accounts_and_run_actions_settle_nothing_against_the_ceiling():
    registered = registered_account_context("00000000-0000-0000-0000-000000000052")
    guest = AccountContext(
        kind="guest",
        user_id="00000000-0000-0000-0000-000000000051",
        expires_at=utcnow() + timedelta(days=7),
        capabilities=guest_capabilities(),
    )

    assert (
        guest_compute_settlement(
            registered, is_run_backtest_turn=False, visitor_key="visitor:x"
        )
        is None
    )
    assert (
        guest_compute_settlement(
            guest, is_run_backtest_turn=True, visitor_key="visitor:x"
        )
        is None
    )
    assert (
        guest_compute_settlement(
            guest, is_run_backtest_turn=False, visitor_key="visitor:x"
        )
        is None
    )


def test_refusal_observer_fires_after_the_entry_claim(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
):
    observed: list[Any] = []
    monkeypatch.setattr(
        refusal_evidence,
        "persist_refusal_observation",
        lambda *, gateway, observation: observed.append(observation),
    )
    fake = _guest(mock_gateway, monkeypatch, turns_today=0)

    response = client.post("/api/v1/chat/stream", json=TURN, headers=GUEST_HEADERS)

    assert response.status_code == 200, response.text
    assert fake.claims == 1
    assert _assistant_settlements(mock_gateway) == []
    assert len(observed) == 1
    assert observed[0].response_message_id in _terminal_message_ids(mock_gateway)
    assert observed[0].request_message_id != observed[0].response_message_id


SPENT_CONFIRMATION_REPLAY = {
    "conversation_id": "conv-1",
    "action": {
        "type": "change_dates",
        "label": "Change dates",
        "presentation": "confirmation",
        "payload": {"confirmation_id": "confirmation-spent"},
    },
}
REPLAY_HEADERS = {"Idempotency-Key": "replay-key-1"}


def test_replayed_idempotency_key_does_not_consume_a_guest_unit(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
):
    """A replay the server rejects before model work is not a question.

    Ordinary turns have no stored idempotency record, so the replay the
    route can recognize is one whose card is no longer active (409).
    """
    fake = _guest(mock_gateway, monkeypatch, turns_today=5)

    first = client.post(
        "/api/v1/chat/stream",
        json=SPENT_CONFIRMATION_REPLAY,
        headers={**GUEST_HEADERS, **REPLAY_HEADERS},
    )
    replay = client.post(
        "/api/v1/chat/stream",
        json=SPENT_CONFIRMATION_REPLAY,
        headers={**GUEST_HEADERS, **REPLAY_HEADERS},
    )

    assert first.status_code == replay.status_code == 409, replay.text
    assert fake.claims == 0
    assert fake.visitor_used == 5
    assert fake.session_used == 5
    mock_gateway.create_message.assert_not_called()


def test_unknown_conversation_404_does_not_consume_a_guest_unit(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
):
    fake = _guest(mock_gateway, monkeypatch, turns_today=5)
    mock_gateway.get_conversation.return_value = None

    response = client.post(
        "/api/v1/chat/stream",
        json={**TURN, "conversation_id": "conv-unknown"},
        headers=GUEST_HEADERS,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert fake.claims == 0
    assert fake.visitor_used == 5
    assert fake.session_used == 5


def test_unknown_conversation_404_wins_over_the_guest_daily_cap(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
):
    from argus.domain.usage_limits import GUEST_COMPUTE_DAILY_CEILING

    fake = _guest(
        mock_gateway, monkeypatch, turns_today=GUEST_COMPUTE_DAILY_CEILING
    )
    mock_gateway.get_conversation.return_value = None

    response = client.post(
        "/api/v1/chat/stream",
        json={**TURN, "conversation_id": "conv-unknown"},
        headers=GUEST_HEADERS,
    )

    assert response.status_code == 404
    assert fake.claims == 0
