"""Issue #247 allowance-truth contracts.

Message allowance must settle exactly once at the durable terminal product
outcome, not at route entry. Simulation allowance must charge exactly once at
unique durable admission. ``GET /me/usage`` must return hourly and daily
backend truth, with backend-derived ``available_now`` and ``limiting_window``,
for both messages and simulations.
"""

from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.schemas import Conversation, Message, User
from argus.domain.backtest_finalization import MemoryBacktestFinalizationGateway
from argus.domain.chat_turn_lifecycle import TransitionResult
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.store import AlphaStore, utcnow
from argus.domain.supabase_gateway import SupabaseGateway
from fastapi.testclient import TestClient

client = TestClient(app)

USER_ID = "00000000-0000-0000-0000-000000000001"


def _profile() -> User:
    now = utcnow()
    return User(
        id=USER_ID,
        email="developer@argus.local",
        username="mock-developer",
        display_name="Mock Developer",
        language="en",
        locale="en-US",
        is_admin=True,
        created_at=now,
        updated_at=now,
    )


def _conversation(conversation_id: str = "conv-1") -> Conversation:
    now = utcnow()
    return Conversation(
        id=conversation_id,
        title="New conversation",
        title_source="system_default",
        language="en",
        pinned=False,
        archived=False,
        last_message_preview=None,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )


class _FakeVisitorClient:
    """Chainable stub for visitor_usage_counters reads, routed by resource."""

    def __init__(self, used_by_resource: dict[str, int]) -> None:
        self._used = used_by_resource
        self._resource: str | None = None

    def table(self, name: str) -> "_FakeVisitorClient":
        assert name == "visitor_usage_counters"
        return self

    def select(self, *_args: Any) -> "_FakeVisitorClient":
        return self

    def eq(self, column: str, value: Any) -> "_FakeVisitorClient":
        if column == "resource":
            self._resource = str(value)
        return self

    def limit(self, *_args: Any) -> "_FakeVisitorClient":
        return self

    def execute(self) -> Any:
        used = self._used.get(self._resource or "", 0)
        rows = [{"used_count": used}] if used else []
        return SimpleNamespace(data=rows)


@pytest.fixture
def mock_gateway():
    gateway = MagicMock(spec=SupabaseGateway)
    gateway.get_user.return_value = _profile()
    gateway.get_or_create_mock_user.return_value = _profile()
    gateway.get_auth_user_from_token.return_value = {
        "id": USER_ID,
        "email": "developer@argus.local",
    }
    gateway.private_alpha_email_allowed.return_value = True
    gateway.get_conversation.return_value = _conversation()
    gateway.list_messages.return_value = []
    gateway.reconcile_stale_chat_turns.return_value = []
    gateway.list_projectable_chat_turns.return_value = []
    gateway.count_completed_runs.return_value = 1
    gateway.get_latest_completed_run_for_conversation.return_value = None
    gateway.create_message.side_effect = lambda **kwargs: Message(
        id="msg-1",
        conversation_id=kwargs["conversation_id"],
        role=kwargs["role"],
        content=kwargs["content"],
        created_at=utcnow(),
        metadata=kwargs.get("metadata"),
    )
    gateway.accept_chat_turn.side_effect = lambda **kwargs: kwargs["message"]
    gateway.transition_chat_turn.return_value = TransitionResult(
        outcome="applied",
    )
    gateway.finalize_chat_turn.side_effect = lambda **kwargs: kwargs["message"]
    gateway.get_backtest_job_reservation.return_value = None
    gateway.admit_backtest_job.return_value = {
        "decision": "admitted",
        "job": {"id": "job-admitted-1", "status": "running"},
    }
    gateway.finalize_direct_backtest_job.return_value = {
        "id": "job-admitted-1",
        "status": "succeeded",
    }
    gateway.get_backtest_job.return_value = None
    finalization_store = AlphaStore()
    gateway.finalize_backtest_completion.side_effect = (
        lambda *, finalization: MemoryBacktestFinalizationGateway(
            finalization_store
        ).finalize_backtest_completion(finalization=finalization)
    )
    gateway.finalize_direct_backtest_success.side_effect = (
        lambda *, job_id, finalization: MemoryBacktestFinalizationGateway(
            finalization_store
        ).finalize_backtest_completion(finalization=finalization)
    )
    gateway.get_evidence_capture_by_run.return_value = None
    gateway.create_backtest_evidence_capture.side_effect = (
        lambda *, user_id, captured: captured
    )
    gateway.create_idea.side_effect = lambda *, user_id, idea: idea
    gateway.create_idea_version.side_effect = lambda *, user_id, version: version
    gateway.create_evidence_artifact.side_effect = lambda *, user_id, artifact: artifact
    gateway.get_decision_note_by_artifact.return_value = None
    gateway.update_backtest_run_result_card.side_effect = (
        lambda *,
        user_id,
        run_id,
        conversation_result_card: api_state.store.backtest_runs[run_id].model_copy(
            update={"conversation_result_card": conversation_result_card}
        )
    )
    gateway.mark_result_card_decision_for_run.return_value = None

    def _rpc(name: str, params: dict[str, Any] | None = None, **_kwargs: Any):
        if name in {
            "claim_registered_compute_usage",
            "claim_guest_compute_usage",
            "claim_research_usage",
        }:
            return SimpleNamespace(
                execute=lambda: SimpleNamespace(
                    data={
                        "available": True,
                        "guest_exhausted": False,
                        "visitor_exhausted": False,
                        "session_exhausted": False,
                    }
                )
            )
        return MagicMock()

    gateway.client = SimpleNamespace(rpc=_rpc)
    with (
        patch("argus.api.state.supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
    ):
        yield gateway


def _assistant_settlements(gateway: MagicMock) -> list[dict[str, Any]]:
    settlements: list[dict[str, Any]] = []
    for call in gateway.create_message.call_args_list:
        if call.kwargs.get("role") != "assistant":
            continue
        settle = call.kwargs.get("settle_usage")
        if settle is not None:
            settlements.append(dict(settle))
    for call in gateway.finalize_chat_turn.call_args_list:
        settle = call.kwargs.get("settle_usage")
        if settle is not None:
            settlements.append(dict(settle))
    return settlements


def _stream_events(stream: str, event_type: str) -> list[dict[str, Any]]:
    events = []
    for line in stream.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        event = json.loads(line.removeprefix("data: "))
        if event.get("type") == event_type:
            events.append(event["payload"])
    return events


def _configure_guest_account(mock_gateway: MagicMock) -> GuestWorkspace:
    profile = _profile().model_copy(
        update={
            "email": None,
            "username": None,
            "display_name": None,
            "is_admin": False,
        }
    )
    workspace = GuestWorkspace(
        user_id=profile.id,
        conversation_id="00000000-0000-0000-0000-000000000101",
        status="active",
        created_at=profile.created_at,
        expires_at=profile.created_at + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=profile.created_at,
    )
    mock_gateway.get_auth_user_from_token.return_value = {
        "id": profile.id,
        "email": None,
        "is_anonymous": True,
    }
    mock_gateway.get_or_create_profile_for_auth_user.return_value = profile
    mock_gateway.get_active_guest_workspace.return_value = workspace
    mock_gateway.get_user.return_value = profile
    return workspace


def test_chat_entry_reads_no_conversation_meter(mock_gateway):
    # Conversation is compute: entry neither checks nor charges a counter.
    response = client.post(
        "/api/v1/chat/stream",
        json={"conversation_id": "conv-1", "message": "Test TSLA dip idea"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200, response.text
    mock_gateway.check_and_increment_usage_limits.assert_not_called()
    mock_gateway.check_usage_limits.assert_not_called()


def test_chat_stream_rejects_malformed_idempotency_keys_before_admission(
    mock_gateway,
):
    for malformed in ("  padded-key  ", "inner space", "tab\tkey", "x" * 129):
        response = client.post(
            "/api/v1/chat/stream",
            json={"conversation_id": "conv-1", "message": "Test TSLA dip idea"},
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": malformed,
            },
        )
        assert response.status_code == 422, malformed
        assert response.json()["code"] == "validation_error"
    mock_gateway.admit_backtest_job.assert_not_called()


def test_completed_turn_settles_nothing(mock_gateway):
    # A compute operation decrements nothing, even at its durable terminal.
    response = client.post(
        "/api/v1/chat/stream",
        json={"conversation_id": "conv-1", "message": "Test TSLA dip idea"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert mock_gateway.finalize_chat_turn.call_count >= 1
    assert _assistant_settlements(mock_gateway) == []


def test_runtime_failure_before_terminal_outcome_consumes_zero_message_units(
    monkeypatch: pytest.MonkeyPatch,
    mock_gateway,
):
    from argus.api.routers import agent as agent_router

    async def _failing_stream_agent_turn_events(**_: Any):
        raise RuntimeError("forced runtime infrastructure failure")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _failing_stream_agent_turn_events,
    )

    response = client.post(
        "/api/v1/chat/stream",
        json={"conversation_id": "conv-1", "message": "Test TSLA dip idea"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert "agent_runtime_failure" in response.text
    mock_gateway.check_and_increment_usage_limits.assert_not_called()
    assert _assistant_settlements(mock_gateway) == []


def test_exhausted_counters_never_wall_conversation(mock_gateway):
    # Even a gateway that would refuse every window cannot 429 a turn: no
    # conversation meter is consulted.
    from argus.domain.supabase_gateway import QuotaExceededError

    mock_gateway.check_usage_limits.side_effect = QuotaExceededError(
        "Quota exceeded for chat_messages (hour)"
    )

    response = client.post(
        "/api/v1/chat/stream",
        json={"conversation_id": "conv-1", "message": "hello"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200, response.text
    mock_gateway.check_usage_limits.assert_not_called()
    mock_gateway.check_and_increment_usage_limits.assert_not_called()


def test_cancel_confirmation_settles_zero_units(mock_gateway):
    mock_gateway.list_messages.return_value = [
        Message(
            id="confirmation-message",
            conversation_id="conv-1",
            role="assistant",
            content="Ready to run.",
            metadata={
                "confirmation_payload": {
                    "strategy": {
                        "strategy_type": "buy_and_hold",
                        "strategy_thesis": "Buy and hold Apple.",
                        "asset_universe": ["AAPL"],
                        "asset_class": "equity",
                        "date_range": "past year",
                    },
                    "optional_parameters": {},
                    "launch_payload": {},
                    "validation": {"status": "ready_to_run", "executable": True},
                },
                "confirmation_card": {
                    "confirmation_id": "confirmation-limit-proof",
                },
            },
            created_at=utcnow(),
        )
    ]
    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": "conv-1",
            "action": {
                "type": "cancel_confirmation",
                "label": "Cancel",
                "presentation": "confirmation",
                "payload": {"confirmation_id": "confirmation-limit-proof"},
            },
            "language": "en",
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200, response.text
    assert "confirmation_cancelled" in response.text
    mock_gateway.check_usage_limits.assert_not_called()
    terminal_calls = [
        call
        for call in mock_gateway.finalize_chat_turn.call_args_list
        if call.kwargs.get("to_status") == "completed"
    ]
    assert len(terminal_calls) == 1
    assert terminal_calls[0].kwargs.get("settle_usage") is None


@pytest.mark.parametrize("confirmation_id", [None, "different-confirmation"])
def test_cancel_confirmation_rejects_unverified_identity_without_writing(
    mock_gateway,
    confirmation_id,
):
    mock_gateway.list_messages.return_value = [
        Message(
            id="confirmation-message",
            conversation_id="conv-1",
            role="assistant",
            content="Ready to run.",
            metadata={
                "confirmation_payload": {
                    "strategy": {
                        "strategy_type": "buy_and_hold",
                        "strategy_thesis": "Buy and hold Apple.",
                        "asset_universe": ["AAPL"],
                        "asset_class": "equity",
                        "date_range": "past year",
                    },
                    "optional_parameters": {},
                    "launch_payload": {},
                    "validation": {"status": "ready_to_run", "executable": True},
                },
                "confirmation_card": {
                    "confirmation_id": "active-confirmation",
                },
            },
            created_at=utcnow(),
        )
    ]
    action_payload = (
        {} if confirmation_id is None else {"confirmation_id": confirmation_id}
    )

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": "conv-1",
            "action": {
                "type": "cancel_confirmation",
                "label": "Cancel",
                "presentation": "confirmation",
                "payload": action_payload,
            },
            "language": "en",
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "confirmation_required"
    mock_gateway.create_message.assert_not_called()


def test_cancel_confirmation_replay_returns_the_existing_tombstone(mock_gateway):
    confirmation = Message(
        id="confirmation-message",
        conversation_id="conv-1",
        role="assistant",
        content="Ready to run.",
        metadata={
            "confirmation_payload": {
                "strategy": {
                    "strategy_type": "buy_and_hold",
                    "strategy_thesis": "Buy and hold Apple.",
                    "asset_universe": ["AAPL"],
                    "asset_class": "equity",
                    "date_range": "past year",
                },
                "optional_parameters": {},
                "launch_payload": {},
                "validation": {"status": "ready_to_run", "executable": True},
            },
            "confirmation_card": {
                "confirmation_id": "active-confirmation",
            },
        },
        created_at=utcnow(),
    )
    mock_gateway.list_messages.return_value = [confirmation]
    request = {
        "conversation_id": "conv-1",
        "action": {
            "type": "cancel_confirmation",
            "label": "Cancel",
            "presentation": "confirmation",
            "payload": {"confirmation_id": "active-confirmation"},
        },
        "language": "en",
    }

    first = client.post(
        "/api/v1/chat/stream",
        json=request,
        headers={"Authorization": "Bearer test-token"},
    )
    assert first.status_code == 200
    first_final = _stream_events(first.text, "final")[0]
    terminal_call = mock_gateway.finalize_chat_turn.call_args_list[-1]
    tombstone = terminal_call.kwargs["message"]
    mock_gateway.list_messages.return_value = [confirmation, tombstone]
    mock_gateway.finalize_chat_turn.reset_mock()

    replay = client.post(
        "/api/v1/chat/stream",
        json=request,
        headers={"Authorization": "Bearer test-token"},
    )

    assert replay.status_code == 200
    assert _stream_events(replay.text, "final")[0] == first_final
    mock_gateway.finalize_chat_turn.assert_not_called()


def test_gateway_owns_an_atomic_admission_operation():
    assert hasattr(SupabaseGateway, "admit_backtest_job"), (
        "Simulation charging must compose with one database-owned admission "
        "operation; a count-then-insert sequence plus a separate usage "
        "increment is not conforming admission."
    )


# ---------------------------------------------------------------------------
# Direct-run identity and terminal finalization.
# ---------------------------------------------------------------------------


def test_direct_identity_covers_every_execution_field():
    from argus.domain.backtest_admission import (
        direct_run_identity_hash,
        normalize_direct_launch_payload,
    )

    base = {
        "template": "buy_and_hold",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "start_date": "2024-01-02",
        "end_date": "2024-06-28",
    }

    def identity(payload):
        return direct_run_identity_hash(
            conversation_id=None,
            strategy_id=None,
            normalized_payload=normalize_direct_launch_payload(payload),
        )

    baseline = identity(base)
    for field, changed in (
        ("starting_capital", 250_000),
        ("side", "short"),
        ("allocation_method", "risk_parity"),
    ):
        assert identity({**base, field: changed}) != baseline, (
            f"{field} must participate in the direct-run identity; reusing a "
            "key with a changed execution field is a collision, not a replay."
        )


def test_direct_identity_stable_across_typed_and_string_dates():
    from datetime import date

    from argus.domain.backtest_admission import (
        direct_run_identity_hash,
        normalize_direct_launch_payload,
    )

    def identity(payload):
        return direct_run_identity_hash(
            conversation_id=None,
            strategy_id=None,
            normalized_payload=normalize_direct_launch_payload(payload),
        )

    typed = {
        "template": "buy_and_hold",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "start_date": date(2024, 1, 2),
        "end_date": date(2024, 6, 28),
    }
    stringly = {
        **typed,
        "start_date": "2024-01-02",
        "end_date": "2024-06-28",
    }
    assert identity(typed) == identity(stringly)


def test_direct_identity_treats_explicit_defaults_as_the_same_execution():
    from argus.domain.backtest_admission import (
        direct_run_identity_hash,
        normalize_direct_launch_payload,
    )

    base = {
        "template": "buy_and_hold",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "start_date": "2024-01-02",
        "end_date": "2024-06-28",
    }

    def identity(payload):
        return direct_run_identity_hash(
            conversation_id=None,
            strategy_id=None,
            normalized_payload=normalize_direct_launch_payload(payload),
        )

    baseline = identity(base)
    for field, explicit_default in (
        ("side", "long"),
        ("starting_capital", 1000),
        ("starting_capital", 1000.0),
        ("allocation_method", "equal_weight"),
        ("timeframe", "1D"),
        ("timeframe", "1d"),
    ):
        assert identity({**base, field: explicit_default}) == baseline, (
            f"Spelling out the executor default for {field} does not change "
            "what runs, so it must not mint a second chargeable identity."
        )
    assert identity({**base, "starting_capital": 2500}) == identity(
        {**base, "starting_capital": 2500.0}
    )


def test_memory_direct_finalization_requires_a_running_job():
    from argus.domain import backtest_admission

    store = AlphaStore()
    outcome = backtest_admission.admit_backtest_job_memory(
        store,
        user_id=USER_ID,
        operation_scope="backtests.run",
        idempotency_key="race-key",
        identity_hash=f"sha256:{'e' * 64}",
        payload_hash=f"sha256:{'f' * 64}",
        launch_payload={"kind": "proof"},
        initial_status="running",
        allowance_limits=[("hour", 10), ("day", 50)],
    )
    job_id = outcome.job["id"]
    store.backtest_jobs[job_id]["status"] = "failed"
    store.backtest_jobs[job_id]["failure_code"] = "direct_execution_abandoned"

    result = backtest_admission.finalize_direct_job_memory(
        store,
        job_id=job_id,
        status="succeeded",
        result_run_id="run-1",
    )

    assert result is None
    assert store.backtest_jobs[job_id]["status"] == "failed"
    assert store.backtest_jobs[job_id]["failure_code"] == "direct_execution_abandoned"
