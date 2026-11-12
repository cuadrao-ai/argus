from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from argus.api import state as api_state
from argus.api.business_spaces import business_spaces, configure_business_spaces
from argus.api.conversation_activity import _as_datetime
from argus.api.dependencies import current_user
from argus.api.guest_access import guest_account_context, store_account_context
from argus.api.main import app
from argus.api.message_store import memory_message
from argus.api.schemas import BacktestRun, ConversationActivity, EvidenceArtifact
from argus.domain.business.spaces import InMemorySpaceStore
from argus.domain.conversation_activity import (
    ActivityReadState,
    ActivitySource,
    Boundary,
    CursorShapeError,
    decode_attention_cursor,
    encode_attention_cursor,
    project_conversation_activity,
)
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.supabase_conversation_activity import (
    SupabaseConversationActivityMixin,
)
from faker import Faker
from fastapi import Request
from fastapi.testclient import TestClient

from tests.conversation_activity_job_scenarios import (
    JOB_SETTLEMENT_SCENARIOS,
    JobSettlementScenario,
)

fake = Faker()
Faker.seed(20260801)


def _moment() -> datetime:
    return fake.date_time(tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("value", "microsecond"),
    [
        ("2026-08-03T03:31:24.1+00:00", 100_000),
        ("2026-08-03T03:31:24.12+00:00", 120_000),
        ("2026-08-03T03:31:24.123+00:00", 123_000),
        ("2026-08-03T03:31:24.1234+00:00", 123_400),
        ("2026-08-03T03:31:24.02766+00:00", 27_660),
    ],
)
def test_activity_datetime_accepts_postgres_trimmed_fractional_seconds(
    value: str,
    microsecond: int,
) -> None:
    assert _as_datetime(value, field="occurred_at") == datetime(
        2026,
        8,
        3,
        3,
        31,
        24,
        microsecond=microsecond,
        tzinfo=timezone.utc,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "2026-08-03T03:30:18+00:00",
            datetime(2026, 8, 3, 3, 30, 18, tzinfo=timezone.utc),
        ),
        (
            "2026-08-03T03:31:24.02766Z",
            datetime(2026, 8, 3, 3, 31, 24, 27_660, tzinfo=timezone.utc),
        ),
        (
            "2026-08-03T03:30:18Z",
            datetime(2026, 8, 3, 3, 30, 18, tzinfo=timezone.utc),
        ),
    ],
)
def test_activity_datetime_accepts_fractionless_and_z_timestamps(
    value: str,
    expected: datetime,
) -> None:
    assert _as_datetime(value, field="occurred_at") == expected


def _source(
    *,
    conversation_id: str,
    source_kind: str = "chat_turn",
    status: str = "completed",
    occurred_at: datetime | None = None,
    stage_outcome: str | None = None,
    result_hydrateable: bool = False,
) -> ActivitySource:
    return ActivitySource(
        conversation_id=conversation_id,
        source_kind=source_kind,
        source_id=fake.uuid4(),
        status=status,
        occurred_at=occurred_at or _moment(),
        stage_outcome=stage_outcome,
        result_hydrateable=result_hydrateable,
    )


@pytest.mark.parametrize(
    ("source_kind", "status", "result_hydrateable", "expected"),
    [
        ("chat_turn", "accepted", False, "queued"),
        ("chat_turn", "running", False, "running"),
        ("backtest_job", "queued", False, "queued"),
        ("backtest_job", "running", False, "running"),
        ("backtest_job", "succeeded", False, "checking"),
    ],
)
def test_projects_operation_from_canonical_source_status(
    source_kind: str,
    status: str,
    result_hydrateable: bool,
    expected: str,
) -> None:
    conversation_id = fake.uuid4()
    source = _source(
        conversation_id=conversation_id,
        source_kind=source_kind,
        status=status,
        result_hydrateable=result_hydrateable,
    )

    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=[source],
        read_state=None,
    )

    assert isinstance(activity, ConversationActivity)
    assert activity.operation.status == expected
    assert activity.operation.kind == source_kind
    assert activity.operation.updated_at == source.occurred_at


def test_operation_precedence_beats_recency() -> None:
    conversation_id = fake.uuid4()
    now = _moment()
    sources = [
        _source(
            conversation_id=conversation_id,
            source_kind="chat_turn",
            status="running",
            occurred_at=now,
        ),
        _source(
            conversation_id=conversation_id,
            source_kind="backtest_job",
            status="queued",
            occurred_at=now + timedelta(minutes=2),
        ),
        _source(
            conversation_id=conversation_id,
            source_kind="backtest_job",
            status="succeeded",
            occurred_at=now + timedelta(minutes=3),
        ),
    ]

    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=sources,
        read_state=None,
    )

    assert activity.operation.status == "running"
    assert activity.operation.kind == "chat_turn"
    assert activity.operation.updated_at == now


def test_operation_ties_use_newest_then_backtest_job() -> None:
    conversation_id = fake.uuid4()
    now = _moment()
    older_job = _source(
        conversation_id=conversation_id,
        source_kind="backtest_job",
        status="running",
        occurred_at=now,
    )
    newest_turn = _source(
        conversation_id=conversation_id,
        source_kind="chat_turn",
        status="running",
        occurred_at=now + timedelta(seconds=1),
    )
    newest_job = _source(
        conversation_id=conversation_id,
        source_kind="backtest_job",
        status="running",
        occurred_at=newest_turn.occurred_at,
    )

    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=[older_job, newest_turn, newest_job],
        read_state=None,
    )

    assert activity.operation.status == "running"
    assert activity.operation.kind == "backtest_job"
    assert activity.operation.updated_at == newest_job.occurred_at


@pytest.mark.parametrize(
    ("source_kind", "status", "stage_outcome", "hydrateable", "expected"),
    [
        ("chat_turn", "completed", None, False, "new_activity"),
        ("chat_turn", "completed", "await_user_reply", False, "needs_input"),
        (
            "chat_turn",
            "completed",
            "needs_clarification",
            False,
            "needs_input",
        ),
        ("chat_turn", "completed", "await_approval", False, "needs_input"),
        (
            "chat_turn",
            "recoverable_failed",
            None,
            False,
            "needs_attention",
        ),
        ("chat_turn", "abandoned", None, False, "needs_attention"),
        ("backtest_job", "succeeded", None, True, "new_activity"),
        ("backtest_job", "failed", None, False, "needs_attention"),
        ("backtest_job", "canceled", None, False, "needs_attention"),
        ("backtest_job", "expired", None, False, "needs_attention"),
    ],
)
def test_projects_latest_unread_terminal_attention(
    source_kind: str,
    status: str,
    stage_outcome: str | None,
    hydrateable: bool,
    expected: str,
) -> None:
    conversation_id = fake.uuid4()
    source = _source(
        conversation_id=conversation_id,
        source_kind=source_kind,
        status=status,
        stage_outcome=stage_outcome,
        result_hydrateable=hydrateable,
    )

    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=[source],
        read_state=None,
    )

    assert activity.attention.status == expected
    assert activity.attention.cursor == encode_attention_cursor(source.boundary)


def test_reconciled_turn_uses_typed_outcome() -> None:
    conversation_id = fake.uuid4()
    failure = _source(
        conversation_id=conversation_id,
        status="reconciled:recoverable_failed",
    )
    completion = _source(
        conversation_id=conversation_id,
        status="reconciled:completed",
        occurred_at=failure.occurred_at + timedelta(seconds=1),
    )

    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=[failure, completion],
        read_state=None,
    )

    assert activity.attention.status == "new_activity"
    assert activity.attention.cursor == encode_attention_cursor(completion.boundary)


def test_unhydrateable_succeeded_job_stays_checking_and_not_ready() -> None:
    conversation_id = fake.uuid4()
    source = _source(
        conversation_id=conversation_id,
        source_kind="backtest_job",
        status="succeeded",
        result_hydrateable=False,
    )

    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=[source],
        read_state=None,
    )

    assert activity.operation.status == "checking"
    assert activity.attention.status == "none"
    assert activity.attention.cursor is None


def test_read_through_boundary_hides_only_consumed_terminal_activity() -> None:
    conversation_id = fake.uuid4()
    now = _moment()
    consumed = _source(conversation_id=conversation_id, occurred_at=now)
    newer = _source(
        conversation_id=conversation_id,
        occurred_at=now + timedelta(seconds=1),
        stage_outcome="await_user_reply",
    )

    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=[consumed, newer],
        read_state=ActivityReadState(read_through=consumed.boundary),
    )

    assert activity.attention.status == "needs_input"
    assert activity.attention.cursor == encode_attention_cursor(newer.boundary)


def test_manual_unread_is_independent_of_read_through() -> None:
    conversation_id = fake.uuid4()
    source = _source(conversation_id=conversation_id)

    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=[source],
        read_state=ActivityReadState(
            read_through=source.boundary,
            manual_unread_at=source.occurred_at + timedelta(seconds=1),
        ),
    )

    assert activity.attention.status == "manual_unread"
    assert activity.attention.cursor == encode_attention_cursor(source.boundary)


def test_new_terminal_state_wins_over_manual_unread() -> None:
    conversation_id = fake.uuid4()
    now = _moment()
    consumed = _source(conversation_id=conversation_id, occurred_at=now)
    failure = _source(
        conversation_id=conversation_id,
        status="recoverable_failed",
        occurred_at=now + timedelta(seconds=2),
    )

    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=[consumed, failure],
        read_state=ActivityReadState(
            read_through=consumed.boundary,
            manual_unread_at=now + timedelta(seconds=1),
        ),
    )

    assert activity.attention.status == "needs_attention"
    assert activity.attention.cursor == encode_attention_cursor(failure.boundary)


def test_projection_isolated_by_conversation() -> None:
    conversation_id = fake.uuid4()
    other_conversation_id = fake.uuid4()

    activity = project_conversation_activity(
        conversation_id=conversation_id,
        sources=[
            _source(
                conversation_id=other_conversation_id,
                source_kind="backtest_job",
                status="running",
            )
        ],
        read_state=None,
    )

    assert activity.operation.status == "idle"
    assert activity.operation.kind is None
    assert activity.operation.updated_at is None
    assert activity.attention.status == "none"
    assert activity.attention.cursor is None


def test_boundary_order_is_time_then_kind_then_source_id() -> None:
    occurred_at = _moment()
    chat_id = "00000000-0000-0000-0000-000000000002"
    job_id = "00000000-0000-0000-0000-000000000001"
    chat = Boundary("chat_turn", chat_id, occurred_at)
    job = Boundary("backtest_job", job_id, occurred_at)

    assert chat < job

    later_chat = Boundary(
        "chat_turn",
        "00000000-0000-0000-0000-000000000001",
        occurred_at + timedelta(microseconds=1),
    )
    assert job < later_chat


def test_attention_cursor_round_trips_only_version_kind_and_uuid() -> None:
    boundary = Boundary("backtest_job", fake.uuid4(), _moment())

    cursor = encode_attention_cursor(boundary)
    decoded = decode_attention_cursor(cursor)

    assert decoded.source_kind == boundary.source_kind
    assert decoded.source_id == boundary.source_id
    assert not hasattr(decoded, "occurred_at")


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64",
        "e30",
        "eyJ2IjoyLCJrIjoiY2hhdF90dXJuIiwiaSI6ImJhZCJ9",
    ],
)
def test_attention_cursor_rejects_malformed_shapes(cursor: str) -> None:
    with pytest.raises(CursorShapeError):
        decode_attention_cursor(cursor)


def test_supabase_activity_gateway_reads_one_bounded_batch() -> None:
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [
        {"conversation_id": fake.uuid4(), "sources": [], "read_state": None}
    ]
    gateway = SupabaseConversationActivityMixin()
    gateway.client = client
    user_id = fake.uuid4()
    conversation_ids = [fake.uuid4() for _ in range(100)]

    rows = gateway.read_conversation_activity_batch(
        user_id=user_id,
        conversation_ids=conversation_ids,
    )

    assert len(rows) == 1
    client.rpc.assert_called_once_with(
        "read_conversation_activity_sources",
        {
            "p_user_id": user_id,
            "p_conversation_ids": conversation_ids,
        },
    )


def test_supabase_activity_gateway_reconciles_one_bounded_batch() -> None:
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = []
    gateway = SupabaseConversationActivityMixin()
    gateway.client = client
    user_id = fake.uuid4()
    conversation_ids = [fake.uuid4() for _ in range(5)]

    assert gateway.reconcile_conversation_activity_turns(
        user_id=user_id,
        conversation_ids=conversation_ids,
    ) == []

    client.rpc.assert_called_once_with(
        "reconcile_stale_conversation_activity_turns",
        {"p_user_id": user_id, "p_conversation_ids": conversation_ids},
    )


def test_supabase_activity_gateway_mutation_passes_verified_source_identity() -> None:
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = {
        "outcome": "applied",
        "read_state": {},
    }
    gateway = SupabaseConversationActivityMixin()
    gateway.client = client
    user_id = fake.uuid4()
    conversation_id = fake.uuid4()
    source_id = fake.uuid4()

    result = gateway.mutate_conversation_activity_read_state(
        user_id=user_id,
        conversation_id=conversation_id,
        action="mark_read",
        source_kind="backtest_job",
        source_id=source_id,
    )

    assert result["outcome"] == "applied"
    client.rpc.assert_called_once_with(
        "mutate_conversation_activity_read_state",
        {
            "p_user_id": user_id,
            "p_conversation_id": conversation_id,
            "p_action": "mark_read",
            "p_source_kind": "backtest_job",
            "p_source_id": source_id,
        },
    )


@pytest.fixture(autouse=True)
def business_conversation_scope(monkeypatch):
    monkeypatch.setenv("CUADRAO_BUSINESS_PILOT_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_BUSINESS_CHAT_ENABLED", "true")
    previous = business_spaces()
    configure_business_spaces(InMemorySpaceStore())
    yield
    configure_business_spaces(previous)


def _api_client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    spaces = business_spaces()
    assert spaces is not None
    spaces.create(api_state.store.get_or_create_dev_user().id, "Business")
    return client


def _store_terminal_turn(
    *,
    conversation_id: str,
    user_id: str,
    status: str = "completed",
    stage_outcome: str = "ready_to_respond",
) -> tuple[str, datetime]:
    terminal_at = datetime.now(timezone.utc)
    turn_id = fake.uuid4()
    assistant = memory_message(
        conversation_id=conversation_id,
        role="assistant",
        content="Stored terminal response",
        metadata={"agent_runtime_stage_outcome": stage_outcome},
    )
    api_state.store.messages.setdefault(conversation_id, []).append(assistant)
    api_state.store.chat_turn_lifecycles[turn_id] = {
        "turn_id": turn_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "assistant_message_id": assistant.id,
        "request_id": fake.uuid4(),
        "status": status,
        "reconciled_outcome": None,
        "failure_code": None,
        "retryable": False,
        "accepted_at": (terminal_at - timedelta(seconds=2)).isoformat(),
        "running_at": (terminal_at - timedelta(seconds=1)).isoformat(),
        "terminal_at": terminal_at.isoformat(),
        "reconciled_at": None,
        "created_at": (terminal_at - timedelta(seconds=2)).isoformat(),
        "updated_at": terminal_at.isoformat(),
    }
    return turn_id, terminal_at


def _assert_idle(activity: dict[str, Any]) -> None:
    assert activity == {
        "latest_message_id": None,
        "operation": {"status": "idle", "kind": None, "updated_at": None},
        "attention": {"status": "none", "cursor": None},
    }


def test_memory_api_emits_activity_on_create_patch_list_and_chat_history() -> None:
    client = _api_client()

    created = client.post("/api/v1/conversations", json={"title": "Activity task"})

    assert created.status_code == 200
    conversation = created.json()["conversation"]
    _assert_idle(conversation["activity"])

    patched = client.patch(
        f"/api/v1/conversations/{conversation['id']}",
        json={"pinned": True},
    )
    assert patched.status_code == 200
    _assert_idle(patched.json()["conversation"]["activity"])

    listed = client.get("/api/v1/conversations")
    assert listed.status_code == 200
    _assert_idle(listed.json()["items"][0]["activity"])

    history = client.get("/api/v1/history")
    assert history.status_code == 200
    chat = next(item for item in history.json()["items"] if item["type"] == "chat")
    _assert_idle(chat["activity"])


def test_memory_activity_endpoints_mark_unread_then_read_through_cursor() -> None:
    client = _api_client()
    conversation = client.post("/api/v1/conversations", json={}).json()[
        "conversation"
    ]
    user_id = api_state.store.get_or_create_dev_user().id
    _store_terminal_turn(conversation_id=conversation["id"], user_id=user_id)

    current = client.get(f"/api/v1/conversations/{conversation['id']}/activity")

    assert current.status_code == 200
    current_activity = current.json()
    assert current_activity["attention"]["status"] == "new_activity"
    cursor = current_activity["attention"]["cursor"]
    assert cursor

    manual = client.patch(
        f"/api/v1/conversations/{conversation['id']}/activity",
        json={"action": "mark_unread"},
    )
    assert manual.status_code == 200
    # A genuinely new terminal boundary remains more important than the manual flag.
    assert manual.json()["attention"]["status"] == "new_activity"

    read = client.patch(
        f"/api/v1/conversations/{conversation['id']}/activity",
        json={"action": "mark_read", "through_attention_cursor": cursor},
    )
    assert read.status_code == 200
    assert read.json()["attention"] == {"status": "none", "cursor": None}

    marked_again = client.patch(
        f"/api/v1/conversations/{conversation['id']}/activity",
        json={"action": "mark_unread"},
    )
    assert marked_again.status_code == 200
    assert marked_again.json()["attention"]["status"] == "manual_unread"
    assert marked_again.json()["attention"]["cursor"] == cursor

    cleared_only = client.patch(
        f"/api/v1/conversations/{conversation['id']}/activity",
        json={"action": "mark_read", "through_attention_cursor": None},
    )
    assert cleared_only.status_code == 200
    assert cleared_only.json()["attention"] == {"status": "none", "cursor": None}


def test_memory_mark_unread_is_idempotent_without_a_terminal_boundary() -> None:
    client = _api_client()
    conversation_id = client.post("/api/v1/conversations", json={}).json()[
        "conversation"
    ]["id"]

    first = client.patch(
        f"/api/v1/conversations/{conversation_id}/activity",
        json={"action": "mark_unread"},
    )
    second = client.patch(
        f"/api/v1/conversations/{conversation_id}/activity",
        json={"action": "mark_unread"},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["attention"] == {
        "status": "manual_unread",
        "cursor": None,
    }
    assert second.json() == first.json()


def test_memory_mark_read_revalidates_cursor_and_does_not_consume_newer_activity() -> None:
    client = _api_client()
    conversation = client.post("/api/v1/conversations", json={}).json()[
        "conversation"
    ]
    user_id = api_state.store.get_or_create_dev_user().id
    first_id, first_at = _store_terminal_turn(
        conversation_id=conversation["id"], user_id=user_id
    )
    first_cursor = encode_attention_cursor(
        Boundary("chat_turn", first_id, first_at)
    )
    _, newer_at = _store_terminal_turn(
        conversation_id=conversation["id"],
        user_id=user_id,
        stage_outcome="await_user_reply",
    )
    assert newer_at >= first_at

    response = client.patch(
        f"/api/v1/conversations/{conversation['id']}/activity",
        json={
            "action": "mark_read",
            "through_attention_cursor": first_cursor,
        },
    )

    assert response.status_code == 200
    assert response.json()["attention"]["status"] == "needs_input"


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"action": "mark_read", "through_attention_cursor": "not-base64"}, 422),
        (
            {
                "action": "mark_read",
                "through_attention_cursor": encode_attention_cursor(
                    Boundary("chat_turn", fake.uuid4(), _moment())
                ),
            },
            409,
        ),
        ({"action": "unknown"}, 422),
    ],
)
def test_memory_activity_patch_rejects_malformed_or_stale_sources(
    payload: dict[str, Any], expected_status: int
) -> None:
    client = _api_client()
    conversation_id = client.post("/api/v1/conversations", json={}).json()[
        "conversation"
    ]["id"]

    response = client.patch(
        f"/api/v1/conversations/{conversation_id}/activity", json=payload
    )

    assert response.status_code == expected_status


def test_activity_endpoints_hide_deleted_foreign_and_unowned_memory_tasks() -> None:
    client = _api_client()
    owned = client.post("/api/v1/conversations", json={}).json()["conversation"]
    foreign = client.post("/api/v1/conversations", json={}).json()["conversation"]
    api_state.store.conversation_owners[foreign["id"]] = fake.uuid4()
    deleted = client.delete(f"/api/v1/conversations/{owned['id']}")
    assert deleted.status_code == 200

    for conversation_id in (owned["id"], foreign["id"], fake.uuid4()):
        response = client.get(f"/api/v1/conversations/{conversation_id}/activity")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


def test_guest_cannot_mark_unread() -> None:
    client = _api_client()
    conversation = client.post("/api/v1/conversations", json={}).json()[
        "conversation"
    ]
    user = api_state.store.get_or_create_dev_user()
    workspace = GuestWorkspace(
        user_id=user.id,
        conversation_id=conversation["id"],
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    def _guest_user(request: Request):
        store_account_context(request, guest_account_context(workspace))
        return user

    app.dependency_overrides[current_user] = _guest_user
    try:
        allowed = client.patch(
            f"/api/v1/conversations/{conversation['id']}/activity",
            json={"action": "mark_read", "through_attention_cursor": None},
        )
        response = client.patch(
            f"/api/v1/conversations/{conversation['id']}/activity",
            json={"action": "mark_unread"},
        )
    finally:
        app.dependency_overrides.pop(current_user, None)

    assert allowed.status_code == 200
    assert response.status_code == 403


def test_memory_succeeded_job_checks_until_finalized_run_can_hydrate() -> None:
    client = _api_client()
    conversation = client.post("/api/v1/conversations", json={}).json()[
        "conversation"
    ]
    user_id = api_state.store.get_or_create_dev_user().id
    now = datetime.now(timezone.utc)
    job_id = fake.uuid4()
    run_id = fake.uuid4()
    api_state.store.backtest_jobs[job_id] = {
        "id": job_id,
        "user_id": user_id,
        "conversation_id": conversation["id"],
        "status": "succeeded",
        "result_run_id": run_id,
        "finished_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    checking = client.get(f"/api/v1/conversations/{conversation['id']}/activity")

    assert checking.status_code == 200
    assert checking.json()["operation"]["status"] == "checking"
    assert checking.json()["attention"]["status"] == "none"

    idea_id = fake.uuid4()
    version_id = fake.uuid4()
    artifact_id = fake.uuid4()
    card = {
        "title": "Final result",
        "rows": [{"label": "Return", "value": "+1%"}],
        "idea_id": idea_id,
        "idea_version_id": version_id,
        "evidence_artifact_id": artifact_id,
    }
    api_state.store.backtest_runs[run_id] = BacktestRun(
        id=run_id,
        conversation_id=conversation["id"],
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={},
        config_snapshot={},
        conversation_result_card=card,
        created_at=now,
    )
    api_state.store.backtest_run_owners[run_id] = user_id
    api_state.store.evidence_artifacts[artifact_id] = EvidenceArtifact(
        id=artifact_id,
        idea_id=idea_id,
        idea_version_id=version_id,
        source_conversation_id=conversation["id"],
        source_run_id=run_id,
        title="Evidence",
        digest="Canonical run evidence",
        payload={},
        created_at=now,
        updated_at=now,
    )
    api_state.store.evidence_artifact_owners[artifact_id] = user_id

    ready = client.get(f"/api/v1/conversations/{conversation['id']}/activity")

    assert ready.status_code == 200
    assert ready.json()["operation"]["status"] == "idle"
    assert ready.json()["attention"]["status"] == "new_activity"


@pytest.mark.parametrize(
    "scenario",
    JOB_SETTLEMENT_SCENARIOS,
    ids=[scenario.id for scenario in JOB_SETTLEMENT_SCENARIOS],
)
def test_memory_job_settlement_follows_the_shared_scenario_table(
    scenario: JobSettlementScenario,
) -> None:
    # Memory twin of the SQL owner predicate; the Postgres suite runs the same
    # table. Production cb7b326d (2026-08-21): a research job with no run
    # projected "checking" forever, which the client treats as locked.
    client = _api_client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    user_id = api_state.store.get_or_create_dev_user().id
    now = datetime.now(timezone.utc)
    job_id = fake.uuid4()
    answer_id = fake.uuid4()
    api_state.store.backtest_jobs[job_id] = {
        "id": job_id,
        "user_id": user_id,
        "conversation_id": conversation["id"],
        "operation_scope": scenario.operation_scope,
        "status": scenario.status,
        "result_run_id": None,
        "execution_metadata": {"research_result_message_id": answer_id},
        "started_at": (now - timedelta(seconds=20)).isoformat(),
        "finished_at": now.isoformat() if scenario.status == "succeeded" else None,
        "updated_at": now.isoformat(),
    }
    if scenario.answer_present:
        answer = memory_message(
            conversation_id=conversation["id"],
            role="assistant",
            content="HOOD vs. JPM vs. SCHW",
            metadata={"conversation_mode": "guide"},
        )
        api_state.store.messages.setdefault(conversation["id"], []).append(
            answer.model_copy(update={"id": answer_id})
        )

    response = client.get(f"/api/v1/conversations/{conversation['id']}/activity")

    assert response.status_code == 200
    activity = response.json()
    assert activity["operation"]["status"] == scenario.expected_operation
    assert activity["attention"]["status"] == scenario.expected_attention
    if scenario.expected_attention == "new_activity":
        assert (
            decode_attention_cursor(activity["attention"]["cursor"]).source_id == job_id
        )


def test_history_omits_activity_from_non_chat_items() -> None:
    client = _api_client()
    conversation = client.post("/api/v1/conversations", json={}).json()[
        "conversation"
    ]
    now = datetime.now(timezone.utc)
    run_id = fake.uuid4()
    api_state.store.backtest_runs[run_id] = BacktestRun(
        id=run_id,
        conversation_id=conversation["id"],
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={},
        config_snapshot={},
        conversation_result_card={
            "title": "Result",
            "rows": [{"label": "Return", "value": "+1%"}],
        },
        created_at=now,
    )
    api_state.store.backtest_run_owners[run_id] = api_state.store.get_or_create_dev_user().id

    response = client.get("/api/v1/history")

    assert response.status_code == 200
    non_chat = [item for item in response.json()["items"] if item["type"] != "chat"]
    assert non_chat
    assert all("activity" not in item for item in non_chat)
