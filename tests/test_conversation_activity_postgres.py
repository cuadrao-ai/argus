"""Disposable-Postgres proof for durable conversation activity/read truth.

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` only to an isolated Supabase Postgres
database with all checked-in migrations applied.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from tests.conversation_activity_job_scenarios import (
    JOB_SETTLEMENT_SCENARIOS,
    JobSettlementScenario,
)

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)
psycopg = pytest.importorskip("psycopg")


def _id() -> str:
    return str(uuid4())


def _connect(*, autocommit: bool = True):
    return psycopg.connect(DSN, autocommit=autocommit)


def _seed_identity(connection, *, anonymous: bool = False) -> str:
    user_id = _id()
    email = None if anonymous else f"activity-{user_id[:8]}@example.test"
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into auth.users (id, email, is_anonymous) values (%s, %s, %s)",
            (user_id, email, anonymous),
        )
        cursor.execute(
            "insert into public.profiles (id, email) values (%s, %s)",
            (user_id, email),
        )
    return user_id


def _seed_conversation(connection, *, user_id: str) -> str:
    conversation_id = _id()
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into public.conversations (id, user_id, title)"
            " values (%s, %s, 'Activity proof')",
            (conversation_id, user_id),
        )
    return conversation_id


def _seed_terminal_turn(
    connection,
    *,
    user_id: str,
    conversation_id: str,
    occurred_at: datetime,
    stage_outcome: str = "ready_to_respond",
    status: str = "completed",
) -> str:
    turn_id = _id()
    assistant_id = _id()
    request_id = f"request-{turn_id}"
    lifecycle_status = status
    reconciled_outcome = None
    failure_code = None
    retryable = False
    if status.startswith("reconciled:"):
        lifecycle_status, reconciled_outcome = status.split(":", 1)
    if status in {"recoverable_failed", "reconciled:recoverable_failed"}:
        failure_code = "runtime_failure"
        retryable = True
    runtime_status = reconciled_outcome or status
    metadata = {
        "agent_runtime_stage_outcome": stage_outcome,
        "agent_runtime_turn": {
            "turn_id": turn_id,
            "request_id": request_id,
            "terminal": True,
            "status": runtime_status,
            "failure_code": failure_code,
            "retryable": retryable,
        },
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into public.messages"
            " (id, conversation_id, user_id, role, content, created_at)"
            " values (%s, %s, %s, 'user', 'Test the idea', %s),"
            "        (%s, %s, %s, 'assistant', 'Typed result', %s)",
            (
                turn_id,
                conversation_id,
                user_id,
                occurred_at - timedelta(microseconds=1),
                assistant_id,
                conversation_id,
                user_id,
                occurred_at,
            ),
        )
        cursor.execute(
            "update public.messages set metadata = %s::jsonb where id = %s",
            (json.dumps(metadata), assistant_id),
        )
        cursor.execute(
            "insert into public.chat_turn_lifecycles"
            " (turn_id, user_id, conversation_id, assistant_message_id,"
            "  request_id, status, reconciled_outcome, failure_code, retryable,"
            "  accepted_at, terminal_at, reconciled_at, created_at, updated_at)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                turn_id,
                user_id,
                conversation_id,
                None if lifecycle_status == "abandoned" else assistant_id,
                request_id,
                lifecycle_status,
                reconciled_outcome,
                "turn_abandoned" if lifecycle_status == "abandoned" else failure_code,
                True if lifecycle_status == "abandoned" else retryable,
                occurred_at - timedelta(seconds=1),
                occurred_at,
                occurred_at if lifecycle_status == "reconciled" else None,
                occurred_at - timedelta(seconds=1),
                occurred_at,
            ),
        )
    return turn_id


def _mutate(
    connection,
    *,
    user_id: str,
    conversation_id: str,
    action: str,
    source_kind: str | None = None,
    source_id: str | None = None,
) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select public.mutate_conversation_activity_read_state("
            " %s, %s, %s, %s, %s)",
            (user_id, conversation_id, action, source_kind, source_id),
        )
        row = cursor.fetchone()
    assert row is not None
    assert isinstance(row[0], dict)
    return row[0]


def _read_sources(
    connection,
    *,
    user_id: str,
    conversation_ids: list[str],
) -> list[tuple[object, object, object]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select * from public.read_conversation_activity_sources(%s, %s)",
            (user_id, conversation_ids),
        )
        return cursor.fetchall()


def _delete_identity(connection, user_id: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("delete from auth.users where id = %s", (user_id,))


def test_owner_selects_read_state_but_foreign_anon_and_writes_are_denied() -> None:
    with _connect() as connection:
        owner_id = _seed_identity(connection)
        foreign_id = _seed_identity(connection)
        conversation_id = _seed_conversation(connection, user_id=owner_id)
        _mutate(
            connection,
            user_id=owner_id,
            conversation_id=conversation_id,
            action="mark_unread",
        )
        try:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("set local role authenticated")
                    cursor.execute(
                        "select set_config('request.jwt.claim.sub', %s, true)",
                        (owner_id,),
                    )
                    cursor.execute(
                        "select count(*) from public.conversation_read_states"
                        " where conversation_id = %s",
                        (conversation_id,),
                    )
                    assert cursor.fetchone()[0] == 1
                    cursor.execute(
                        "select set_config('request.jwt.claim.sub', %s, true)",
                        (foreign_id,),
                    )
                    cursor.execute(
                        "select count(*) from public.conversation_read_states"
                        " where conversation_id = %s",
                        (conversation_id,),
                    )
                    assert cursor.fetchone()[0] == 0

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction():
                    with connection.cursor() as cursor:
                        cursor.execute("set local role authenticated")
                        cursor.execute(
                            "update public.conversation_read_states"
                            " set manual_unread_at = null"
                            " where conversation_id = %s",
                            (conversation_id,),
                        )

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction():
                    with connection.cursor() as cursor:
                        cursor.execute("set local role anon")
                        cursor.execute(
                            "select * from public.conversation_read_states"
                            " where conversation_id = %s",
                            (conversation_id,),
                        )

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction():
                    with connection.cursor() as cursor:
                        cursor.execute("set local role authenticated")
                        cursor.execute(
                            "select public.mutate_conversation_activity_read_state("
                            " %s, %s, 'mark_read', null, null)",
                            (owner_id, conversation_id),
                        )
        finally:
            _delete_identity(connection, owner_id)
            _delete_identity(connection, foreign_id)


def test_stale_read_cursor_cannot_consume_a_newer_completion() -> None:
    with _connect() as connection:
        user_id = _seed_identity(connection)
        conversation_id = _seed_conversation(connection, user_id=user_id)
        now = datetime.now(timezone.utc)
        older_id = _seed_terminal_turn(
            connection,
            user_id=user_id,
            conversation_id=conversation_id,
            occurred_at=now,
        )
        newer_id = _seed_terminal_turn(
            connection,
            user_id=user_id,
            conversation_id=conversation_id,
            occurred_at=now + timedelta(seconds=1),
            stage_outcome="await_user_reply",
        )
        try:
            result = _mutate(
                connection,
                user_id=user_id,
                conversation_id=conversation_id,
                action="mark_read",
                source_kind="chat_turn",
                source_id=older_id,
            )
            assert result["outcome"] == "applied"

            rows = _read_sources(
                connection,
                user_id=user_id,
                conversation_ids=[conversation_id],
            )
            assert len(rows) == 1
            sources = rows[0][1]
            read_state = rows[0][2]
            assert sources[-1]["source_id"] == newer_id
            assert sources[-1]["stage_outcome"] == "await_user_reply"
            assert read_state["read_through_source_id"] == older_id
        finally:
            _delete_identity(connection, user_id)


def test_deleted_list_source_read_remains_available_to_owner_batch() -> None:
    with _connect() as connection:
        user_id = _seed_identity(connection)
        conversation_id = _seed_conversation(connection, user_id=user_id)
        terminal_id = _seed_terminal_turn(
            connection,
            user_id=user_id,
            conversation_id=conversation_id,
            occurred_at=datetime.now(timezone.utc),
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "update public.conversations set deleted_at = now() where id = %s",
                    (conversation_id,),
                )

            rows = _read_sources(
                connection,
                user_id=user_id,
                conversation_ids=[conversation_id],
            )

            assert len(rows) == 1
            assert rows[0][1][-1]["source_id"] == terminal_id
            assert (
                _mutate(
                    connection,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    action="mark_unread",
                )["outcome"]
                == "missing"
            )
        finally:
            _delete_identity(connection, user_id)


def test_manual_unread_is_idempotent_and_null_mark_read_preserves_boundary() -> None:
    with _connect() as connection:
        user_id = _seed_identity(connection)
        conversation_id = _seed_conversation(connection, user_id=user_id)
        terminal_id = _seed_terminal_turn(
            connection,
            user_id=user_id,
            conversation_id=conversation_id,
            occurred_at=datetime.now(timezone.utc),
        )
        try:
            _mutate(
                connection,
                user_id=user_id,
                conversation_id=conversation_id,
                action="mark_read",
                source_kind="chat_turn",
                source_id=terminal_id,
            )
            first = _mutate(
                connection,
                user_id=user_id,
                conversation_id=conversation_id,
                action="mark_unread",
            )
            second = _mutate(
                connection,
                user_id=user_id,
                conversation_id=conversation_id,
                action="mark_unread",
            )
            assert first["outcome"] == "applied"
            assert second["outcome"] == "noop"
            assert (
                first["read_state"]["manual_unread_at"]
                == second["read_state"]["manual_unread_at"]
            )

            cleared = _mutate(
                connection,
                user_id=user_id,
                conversation_id=conversation_id,
                action="mark_read",
            )
            assert cleared["read_state"]["manual_unread_at"] is None
            assert cleared["read_state"]["read_through_source_id"] == terminal_id
        finally:
            _delete_identity(connection, user_id)


def test_nonterminal_source_conflicts_without_mutating_read_state() -> None:
    with _connect() as connection:
        user_id = _seed_identity(connection)
        conversation_id = _seed_conversation(connection, user_id=user_id)
        turn_id = _id()
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into public.messages"
                " (id, conversation_id, user_id, role, content)"
                " values (%s, %s, %s, 'user', 'Still working')",
                (turn_id, conversation_id, user_id),
            )
            cursor.execute(
                "insert into public.chat_turn_lifecycles"
                " (turn_id, user_id, conversation_id, request_id, status)"
                " values (%s, %s, %s, %s, 'accepted')",
                (turn_id, user_id, conversation_id, f"request-{turn_id}"),
            )
        try:
            result = _mutate(
                connection,
                user_id=user_id,
                conversation_id=conversation_id,
                action="mark_read",
                source_kind="chat_turn",
                source_id=turn_id,
            )
            assert result == {"outcome": "conflict", "read_state": None}
            with connection.cursor() as cursor:
                cursor.execute(
                    "select count(*) from public.conversation_read_states"
                    " where conversation_id = %s",
                    (conversation_id,),
                )
                assert cursor.fetchone()[0] == 0
        finally:
            _delete_identity(connection, user_id)


def test_conversation_owner_update_and_delete_cascade_read_state() -> None:
    with _connect() as connection:
        source_id = _seed_identity(connection, anonymous=True)
        destination_id = _seed_identity(connection)
        conversation_id = _seed_conversation(connection, user_id=source_id)
        _mutate(
            connection,
            user_id=source_id,
            conversation_id=conversation_id,
            action="mark_unread",
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "update public.conversations set user_id = %s"
                    " where id = %s and user_id = %s",
                    (destination_id, conversation_id, source_id),
                )
                cursor.execute(
                    "select user_id from public.conversation_read_states"
                    " where conversation_id = %s",
                    (conversation_id,),
                )
                assert str(cursor.fetchone()[0]) == destination_id
                cursor.execute(
                    "delete from public.conversations where id = %s",
                    (conversation_id,),
                )
                cursor.execute(
                    "select count(*) from public.conversation_read_states"
                    " where conversation_id = %s",
                    (conversation_id,),
                )
                assert cursor.fetchone()[0] == 0
        finally:
            _delete_identity(connection, source_id)
            _delete_identity(connection, destination_id)


def _seed_job(
    connection,
    *,
    user_id: str,
    conversation_id: str,
    operation_scope: str,
    status: str,
    occurred_at: datetime,
    answer_id: str,
) -> str:
    job_id = _id()
    finished_at = occurred_at if status == "succeeded" else None
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into public.backtest_jobs"
            " (id, user_id, conversation_id, payload_hash, launch_payload,"
            "  status, operation_scope, queued_at, started_at, finished_at,"
            "  execution_metadata, created_at, updated_at)"
            " values (%s, %s, %s, 'sha256:test', '{}'::jsonb, %s,"
            "  %s, %s, %s, %s, %s::jsonb, %s, %s)",
            (
                job_id,
                user_id,
                conversation_id,
                status,
                operation_scope,
                occurred_at - timedelta(seconds=30),
                occurred_at - timedelta(seconds=20),
                finished_at,
                json.dumps({"research_result_message_id": answer_id}),
                occurred_at - timedelta(seconds=30),
                occurred_at,
            ),
        )
    return job_id


def _projected(connection, *, user_id: str, conversation_id: str):
    from argus.api.conversation_activity import source_from_row
    from argus.domain.conversation_activity import project_conversation_activity

    rows = _read_sources(connection, user_id=user_id, conversation_ids=[conversation_id])
    sources = [source_from_row(raw) for raw in rows[0][1]]
    return sources, project_conversation_activity(
        conversation_id=conversation_id,
        sources=sources,
        read_state=None,
    )


@pytest.mark.parametrize(
    "scenario",
    JOB_SETTLEMENT_SCENARIOS,
    ids=[scenario.id for scenario in JOB_SETTLEMENT_SCENARIOS],
)
def test_sql_job_settlement_follows_the_shared_scenario_table(
    scenario: JobSettlementScenario,
) -> None:
    # SQL owner predicate backtest_job_result_hydrateable; the memory suite
    # runs the same table. A research job has no run: its result is the
    # message named by execution_metadata, and only a succeeded row may settle.
    with _connect() as connection:
        user_id = _seed_identity(connection)
        try:
            conversation_id = _seed_conversation(connection, user_id=user_id)
            occurred_at = datetime.now(timezone.utc)
            answer_id = _id()
            job_id = _seed_job(
                connection,
                user_id=user_id,
                conversation_id=conversation_id,
                operation_scope=scenario.operation_scope,
                status=scenario.status,
                occurred_at=occurred_at,
                answer_id=answer_id,
            )
            if scenario.answer_present:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "insert into public.messages"
                        " (id, conversation_id, user_id, role, content, created_at)"
                        " values (%s, %s, %s, 'assistant', 'Research answer', %s)",
                        (answer_id, conversation_id, user_id, occurred_at),
                    )

            sources, activity = _projected(
                connection, user_id=user_id, conversation_id=conversation_id
            )
            job_source = next(s for s in sources if s.source_kind == "backtest_job")
            assert job_source.source_id == job_id
            assert job_source.status == scenario.status
            assert job_source.result_hydrateable is scenario.expected_hydrateable
            assert activity.operation.status == scenario.expected_operation
            assert activity.attention.status == scenario.expected_attention

            # The read-state mutation revalidates with the same owner, so the
            # cursor applies exactly when the projection offers it.
            outcome = _mutate(
                connection,
                user_id=user_id,
                conversation_id=conversation_id,
                action="mark_read",
                source_kind="backtest_job",
                source_id=job_id,
            )
            if scenario.expected_attention == "new_activity":
                assert outcome["outcome"] == "applied"
                assert outcome["read_state"]["read_through_source_id"] == job_id
            else:
                assert outcome["outcome"] == "conflict"
        finally:
            _delete_identity(connection, user_id)


def test_batch_read_is_one_call_for_volume_and_rejects_more_than_100_ids() -> None:
    with _connect() as connection:
        user_id = _seed_identity(connection)
        conversation_ids = [
            _seed_conversation(connection, user_id=user_id) for _ in range(100)
        ]
        try:
            rows = _read_sources(
                connection,
                user_id=user_id,
                conversation_ids=conversation_ids,
            )
            assert len(rows) == 100

            with pytest.raises(psycopg.errors.InvalidParameterValue):
                _read_sources(
                    connection,
                    user_id=user_id,
                    conversation_ids=conversation_ids + [_id()],
                )
        finally:
            _delete_identity(connection, user_id)
