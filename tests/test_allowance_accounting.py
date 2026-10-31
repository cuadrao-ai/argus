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
from argus.api.schemas import BacktestRun, Conversation, Message, User
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


def test_direct_run_admits_durably_and_never_uses_legacy_increment(
    monkeypatch: pytest.MonkeyPatch,
    mock_gateway,
):
    import pandas as pd
    from argus.domain import engine as domain_engine

    def _fetch(symbol: str, **_: object) -> pd.DataFrame:
        index = pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"], utc=True
        )
        close = pd.Series(range(100, 100 + len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(domain_engine, "fetch_ohlcv", _fetch)

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "template": "buy_and_hold",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
        },
        headers={
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "direct-admission-truth",
        },
    )

    assert response.status_code == 200
    mock_gateway.check_and_increment_usage_limits.assert_not_called()
    mock_gateway.admit_backtest_job.assert_called_once()
    admission = mock_gateway.admit_backtest_job.call_args.kwargs
    assert admission["operation_scope"] == "backtests.run"
    assert admission["idempotency_key"] == "direct-admission-truth"
    mock_gateway.finalize_direct_backtest_success.assert_called_once()
    success = mock_gateway.finalize_direct_backtest_success.call_args.kwargs
    assert success["job_id"] == "job-admitted-1"
    mock_gateway.finalize_direct_backtest_job.assert_not_called()


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


def test_dated_direct_request_survives_wire_serialization_of_the_payload(
    monkeypatch: pytest.MonkeyPatch,
    mock_gateway,
):
    import pandas as pd
    from argus.domain import engine as domain_engine

    def _fetch(symbol: str, **_: object) -> pd.DataFrame:
        index = pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"], utc=True
        )
        close = pd.Series(range(100, 100 + len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(domain_engine, "fetch_ohlcv", _fetch)

    def _admit_serializing(**kwargs: Any) -> dict[str, Any]:
        # The PostgREST client JSON-encodes the launch payload on the wire.
        json.dumps(kwargs["launch_payload"])
        return {
            "decision": "admitted",
            "job": {"id": "job-admitted-1", "status": "running"},
        }

    mock_gateway.admit_backtest_job.side_effect = _admit_serializing

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "template": "buy_and_hold",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
        },
        headers={
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "dated-wire-serialization",
        },
    )

    assert response.status_code == 200
    admitted = mock_gateway.admit_backtest_job.call_args.kwargs["launch_payload"]
    assert admitted["start_date"] == "2024-01-02"
    assert admitted["end_date"] == "2024-01-05"


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


def test_late_direct_success_cannot_rewrite_reconciled_failure(
    monkeypatch: pytest.MonkeyPatch,
    mock_gateway,
):
    import pandas as pd
    from argus.domain import engine as domain_engine

    def _fetch(symbol: str, **_: object) -> pd.DataFrame:
        index = pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"], utc=True
        )
        close = pd.Series(range(100, 100 + len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(domain_engine, "fetch_ohlcv", _fetch)
    # The reconciler already settled this job while the slow execution was
    # still running: the serialized finalize finds no running row.
    mock_gateway.finalize_direct_backtest_success.side_effect = None
    mock_gateway.finalize_direct_backtest_success.return_value = None

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "template": "buy_and_hold",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
        },
        headers={
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "late-finalization-race",
        },
    )

    assert response.status_code == 503
    assert response.json()["code"] == "direct_execution_abandoned"
    assert "run" not in response.json()
    mock_gateway.finalize_direct_backtest_job.assert_not_called()


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


def test_exhausted_precheck_still_replays_a_just_admitted_reservation(
    monkeypatch: pytest.MonkeyPatch,
    mock_gateway,
):
    import pandas as pd
    from argus.api.schemas import BacktestRun
    from argus.domain import engine as domain_engine
    from argus.domain.supabase_gateway import QuotaExceededError

    def _fetch(symbol: str, **_: object) -> pd.DataFrame:
        index = pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"], utc=True
        )
        close = pd.Series(range(100, 100 + len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(domain_engine, "fetch_ohlcv", _fetch)

    body = {
        "template": "buy_and_hold",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "start_date": "2024-01-02",
        "end_date": "2024-01-05",
    }
    first = client.post(
        "/api/v1/backtests/run",
        json=body,
        headers={
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "race-last-unit",
        },
    )
    assert first.status_code == 200
    created_run = first.json()["run"]

    # The duplicate's pre-read misses, the winner fills the last unit, and
    # only then does the duplicate reach the non-consuming precheck.
    mock_gateway.get_backtest_job_reservation.side_effect = [
        None,
        {"id": "job-admitted-1"},
    ]
    mock_gateway.check_usage_limits.side_effect = QuotaExceededError(
        "Quota exceeded for backtest_runs (hour)"
    )
    mock_gateway.admit_backtest_job.reset_mock()
    mock_gateway.admit_backtest_job.return_value = {
        "decision": "replay",
        "job": {
            "id": "job-admitted-1",
            "status": "succeeded",
            "result_run_id": created_run["id"],
        },
    }
    mock_gateway.get_backtest_run.return_value = BacktestRun.model_validate(created_run)

    duplicate = client.post(
        "/api/v1/backtests/run",
        json=body,
        headers={
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "race-last-unit",
        },
    )

    assert duplicate.status_code == 200
    assert duplicate.json()["run"]["id"] == created_run["id"]
    mock_gateway.admit_backtest_job.assert_called_once()


def test_exhausted_precheck_still_reports_same_key_collisions(
    mock_gateway,
):
    from argus.domain.supabase_gateway import QuotaExceededError

    mock_gateway.get_backtest_job_reservation.side_effect = [
        None,
        {"id": "job-other"},
    ]
    mock_gateway.check_usage_limits.side_effect = QuotaExceededError(
        "Quota exceeded for backtest_runs (hour)"
    )
    mock_gateway.admit_backtest_job.return_value = {"decision": "conflict"}

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "template": "buy_and_hold",
            "asset_class": "equity",
            "symbols": ["NVDA"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
        },
        headers={
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "race-collision-key",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_conflict"


def test_guest_third_direct_run_requires_conversion_before_provider_access(
    mock_gateway,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    _configure_guest_account(mock_gateway)
    # The visitor already spent today's two runs; renewal must not help.
    mock_gateway.client = _FakeVisitorClient({"backtest_runs": 2})

    with patch("argus.api.backtest_service.prepare_run_from_payload") as prepare_run:
        response = client.post(
            "/api/v1/backtests/run",
            json={
                "template": "buy_and_hold",
                "asset_class": "equity",
                "symbols": ["AAPL"],
                "start_date": "2024-01-02",
                "end_date": "2024-01-05",
            },
            headers={
                "Authorization": "Bearer guest-token",
                "Idempotency-Key": "guest-third-run",
            },
        )

    assert response.status_code == 403
    assert response.json()["code"] == "account_conversion_required"
    prepare_run.assert_not_called()
    mock_gateway.admit_backtest_job.assert_not_called()
    mock_gateway.check_and_increment_usage_limits.assert_not_called()


def test_exhausted_guest_direct_exact_replay_returns_prior_result(
    mock_gateway,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    _configure_guest_account(mock_gateway)
    now = utcnow()
    prior_run = BacktestRun(
        id="guest-prior-run",
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={},
        config_snapshot={},
        conversation_result_card={},
        created_at=now,
    )
    mock_gateway.get_backtest_job_reservation.return_value = {"id": "guest-job"}
    mock_gateway.admit_backtest_job.return_value = {
        "decision": "replay",
        "job": {
            "id": "guest-job",
            "status": "succeeded",
            "result_run_id": prior_run.id,
        },
    }
    mock_gateway.get_backtest_run.return_value = prior_run

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "template": "buy_and_hold",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
        },
        headers={
            "Authorization": "Bearer guest-token",
            "Idempotency-Key": "guest-replay",
        },
    )

    assert response.status_code == 200
    assert response.json()["run"]["id"] == prior_run.id
    mock_gateway.check_allowance_windows.assert_not_called()


def test_exhausted_guest_direct_identity_collision_remains_conflict(
    mock_gateway,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    _configure_guest_account(mock_gateway)
    mock_gateway.get_backtest_job_reservation.return_value = {"id": "guest-job"}
    mock_gateway.admit_backtest_job.return_value = {"decision": "conflict"}

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "template": "buy_and_hold",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
        },
        headers={
            "Authorization": "Bearer guest-token",
            "Idempotency-Key": "guest-collision",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_conflict"
    mock_gateway.check_allowance_windows.assert_not_called()


def test_unexpected_direct_failure_still_settles_the_job_terminally(
    monkeypatch: pytest.MonkeyPatch,
    mock_gateway,
):
    import pandas as pd
    from argus.api import backtest_service
    from argus.domain import engine as domain_engine

    def _fetch(symbol: str, **_: object) -> pd.DataFrame:
        index = pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"], utc=True
        )
        close = pd.Series(range(100, 100 + len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(domain_engine, "fetch_ohlcv", _fetch)

    def _explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError("engine crashed mid-run")

    monkeypatch.setattr(backtest_service, "create_run_from_payload", _explode)

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "template": "buy_and_hold",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
        },
        headers={
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "unexpected-crash",
            "X-Request-Id": "direct-unexpected-crash",
        },
    )

    assert response.status_code == 500
    assert response.json() == {
        "type": "https://api.argus.app/problems/internal-error",
        "title": "Internal Error",
        "status": 500,
        "detail": "An unexpected error occurred. Please try again.",
        "code": "internal_error",
        "request_id": "direct-unexpected-crash",
    }
    assert response.headers["X-Request-Id"] == "direct-unexpected-crash"
    assert "engine crashed mid-run" not in response.text

    mock_gateway.finalize_direct_backtest_job.assert_called_once()
    settled = mock_gateway.finalize_direct_backtest_job.call_args.kwargs
    assert settled["job_id"] == "job-admitted-1"
    assert settled["status"] == "failed"
    assert settled["failure_code"] == "execution_failed"
    assert settled["failure_detail"] == "unexpected_error"
    assert settled["retryable"] is False
    mock_gateway.finalize_direct_backtest_success.assert_not_called()


def test_backtest_job_contract_allows_direct_jobs_without_a_conversation(
    mock_gateway,
):
    mock_gateway.get_backtest_job.return_value = {
        "id": "9f0a3f31-6f57-49f8-b8f5-2ff8e6b0b0aa",
        "conversation_id": None,
        "status": "failed",
        "failure_code": "direct_execution_abandoned",
        "failure_detail": "direct_execution_abandoned",
        "retryable": True,
    }

    response = client.get(
        "/api/v1/backtest-jobs/9f0a3f31-6f57-49f8-b8f5-2ff8e6b0b0aa",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    body = response.json()["job"]
    assert body["conversation_id"] is None
    assert body["status"] == "failed"
