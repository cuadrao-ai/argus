from __future__ import annotations

import os
from contextlib import suppress
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from argus.api.schemas import Message
from argus.domain.owner_scope import PERSONAL
from argus.domain.supabase_gateway import ConversationCursorError, SupabaseGateway

from supabase import create_client


def _conversation_id(idx: int) -> str:
    return f"00000000-0000-0000-0000-{idx:012d}"


def _message_id(idx: int) -> str:
    return f"10000000-0000-0000-0000-{idx:012d}"


def _conversation_row(
    idx: int,
    *,
    pinned: bool = False,
    deleted_at: str | None = None,
    updated_at: str = "2026-04-27T00:00:00+00:00",
) -> dict[str, object]:
    return {
        "id": _conversation_id(idx),
        "title": f"Conversation {idx}",
        "title_source": "system_default",
        "language": "en",
        "pinned": pinned,
        "archived": False,
        "last_message_preview": None,
        "deleted_at": deleted_at,
        "created_at": "2026-04-27T00:00:00+00:00",
        "updated_at": updated_at,
    }


def _message_row(
    idx: int,
    *,
    created_at: str = "2026-04-27T00:00:00+00:00",
    role: str = "user",
    content: str | None = None,
) -> dict[str, object]:
    return {
        "id": _message_id(idx),
        "conversation_id": _conversation_id(1),
        "role": role,
        "content": content or f"Message {idx}",
        "metadata": {},
        "created_at": created_at,
    }


class _RecordingQuery:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.operations: list[tuple[str, tuple[object, ...]]] = []

    @property
    def not_(self) -> _RecordingQuery:
        return self

    def select(self, *args: object) -> _RecordingQuery:
        self.operations.append(("select", args))
        return self

    def eq(self, *args: object) -> _RecordingQuery:
        self.operations.append(("eq", args))
        return self

    def neq(self, *args: object) -> _RecordingQuery:
        self.operations.append(("neq", args))
        return self

    def like(self, *args: object) -> _RecordingQuery:
        self.operations.append(("like", args))
        return self

    def is_(self, *args: object) -> _RecordingQuery:
        self.operations.append(("is_", args))
        return self

    def order(self, *args: object, **kwargs: object) -> _RecordingQuery:
        self.operations.append(("order", args + tuple(kwargs.items())))
        return self

    def or_(self, *args: object) -> _RecordingQuery:
        self.operations.append(("or_", args))
        return self

    def limit(self, *args: object) -> _RecordingQuery:
        self.operations.append(("limit", args))
        return self

    def range(self, *args: object) -> _RecordingQuery:
        self.operations.append(("range", args))
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.rows)


class _RecordingClient:
    def __init__(self, *row_sets: list[dict[str, object]]) -> None:
        self._row_sets = list(row_sets)
        self.table_names: list[str] = []
        self.queries: list[_RecordingQuery] = []

    def table(self, table_name: str) -> _RecordingQuery:
        self.table_names.append(table_name)
        query = _RecordingQuery(self._row_sets.pop(0))
        self.queries.append(query)
        return query


def _operation_names(query: _RecordingQuery) -> list[str]:
    return [name for name, _ in query.operations]


def test_gateway_fetches_all_conversations_in_batches_when_limit_is_none() -> None:
    client = MagicMock()
    gateway = SupabaseGateway(client=client)

    table = client.table.return_value
    select = table.select.return_value
    eq = select.eq.return_value
    eq.is_.return_value = eq
    ordered = eq.order.return_value
    ordered.order.return_value = ordered
    ordered.limit.return_value.execute.return_value.data = []

    def _range_side_effect(start: int, end: int) -> MagicMock:  # noqa: ARG001
        query = MagicMock()
        if start == 0:
            query.execute.return_value.data = [_conversation_row(i) for i in range(500)]
        elif start == 500:
            query.execute.return_value.data = [
                _conversation_row(i) for i in range(500, 750)
            ]
        else:
            query.execute.return_value.data = []
        return query

    ordered.range.side_effect = _range_side_effect

    rows = gateway.list_conversations(scope=PERSONAL, user_id="user-1", limit=None)

    assert len(rows) == 750
    ordered.range.assert_any_call(0, 499)
    ordered.range.assert_any_call(500, 999)
    ordered.limit.assert_not_called()


def test_conversation_page_fetches_only_limit_plus_one() -> None:
    client = _RecordingClient([_conversation_row(idx) for idx in range(3)])
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    rows = gateway.list_conversations(scope=PERSONAL, user_id="user-1", limit=2)

    assert [row.id for row in rows] == [
        _conversation_id(0),
        _conversation_id(1),
        _conversation_id(2),
    ]
    assert ("limit", (3,)) in client.queries[0].operations
    assert "range" not in _operation_names(client.queries[0])


def test_conversation_page_delegates_to_injected_postgres_keyset_reader() -> None:
    reader = MagicMock()
    reader.list_conversation_rows.return_value = [
        _conversation_row(0),
        _conversation_row(1),
        _conversation_row(2),
    ]
    client = MagicMock()
    client.table.side_effect = AssertionError("PostgREST must not read page candidates")
    gateway = SupabaseGateway(client=client, keyset_reader=reader)

    rows = gateway.list_conversations(
        scope=PERSONAL,
        user_id="30000000-0000-0000-0000-000000000001",
        limit=2,
        archived=False,
        deleted=False,
    )

    assert [row.id for row in rows] == [
        _conversation_id(0),
        _conversation_id(1),
        _conversation_id(2),
    ]
    reader.list_conversation_rows.assert_called_once_with(
        scope=PERSONAL,
        user_id="30000000-0000-0000-0000-000000000001",
        limit=2,
        archived=False,
        deleted=False,
        cursor_updated_at=None,
        cursor_id=None,
    )
    client.table.assert_not_called()


def test_conversation_page_uses_pinned_updated_at_id_desc() -> None:
    client = _RecordingClient([])
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    gateway.list_conversations(scope=PERSONAL, user_id="user-1", limit=20)

    orders = [
        operation for operation in client.queries[0].operations if operation[0] == "order"
    ]
    assert orders == [
        ("order", ("pinned", ("desc", True))),
        ("order", ("updated_at", ("desc", True))),
        ("order", ("id", ("desc", True))),
    ]


def test_conversation_equal_timestamps_are_stable() -> None:
    timestamp = datetime(2026, 4, 27, tzinfo=timezone.utc)
    pivot = _conversation_row(2, updated_at=timestamp.isoformat())
    page = [
        _conversation_row(1, updated_at=timestamp.isoformat()),
        _conversation_row(0, updated_at=timestamp.isoformat()),
    ]
    client = _RecordingClient([pivot], page)
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    rows = gateway.list_conversations(
        scope=PERSONAL,
        user_id="user-1",
        limit=2,
        cursor_updated_at=timestamp,
        cursor_id=_conversation_id(2),
    )

    assert [row.id for row in rows] == [_conversation_id(1), _conversation_id(0)]
    keyset_filter = next(
        args[0] for name, args in client.queries[1].operations if name == "or_"
    )
    assert f"updated_at.eq.{timestamp.isoformat()}" in keyset_filter
    assert f"id.lt.{_conversation_id(2)}" in keyset_filter


def test_conversation_soft_deleted_pivot_does_not_skip_or_duplicate() -> None:
    timestamp = datetime(2026, 4, 27, tzinfo=timezone.utc)
    deleted_pivot = _conversation_row(
        2,
        pinned=True,
        deleted_at="2026-04-28T00:00:00+00:00",
        updated_at="2026-04-28T00:00:00+00:00",
    )
    page = [
        _conversation_row(1, pinned=True, updated_at=timestamp.isoformat()),
        _conversation_row(9, pinned=False, updated_at=timestamp.isoformat()),
    ]
    client = _RecordingClient([deleted_pivot], page)
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    rows = gateway.list_conversations(
        scope=PERSONAL,
        user_id="user-1",
        limit=2,
        cursor_updated_at=timestamp,
        cursor_id=_conversation_id(2),
    )

    assert [row.id for row in rows] == [_conversation_id(1), _conversation_id(9)]
    assert ("is_", ("deleted_at", "null")) not in client.queries[0].operations
    assert ("is_", ("deleted_at", "null")) in client.queries[1].operations
    keyset_filter = next(
        args[0] for name, args in client.queries[1].operations if name == "or_"
    )
    assert "pinned.eq.false" in keyset_filter
    assert "pinned.eq.true" in keyset_filter
    assert f"updated_at.lt.{timestamp.isoformat()}" in keyset_filter


@pytest.mark.parametrize(
    "pivot_rows",
    [
        [],
        [_conversation_row(1), _conversation_row(1)],
    ],
    ids=["missing-or-foreign", "ambiguous"],
)
def test_conversation_foreign_or_missing_pivot_fails_closed(
    pivot_rows: list[dict[str, object]],
) -> None:
    client = _RecordingClient(pivot_rows)
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="conversation cursor"):
        gateway.list_conversations(
            scope=PERSONAL,
            user_id="user-1",
            limit=2,
            cursor_updated_at=datetime(2026, 4, 27, tzinfo=timezone.utc),
            cursor_id=_conversation_id(2),
        )


def test_conversation_malformed_cursor_id_fails_before_postgrest() -> None:
    client = MagicMock()
    client.table.side_effect = AssertionError("PostgREST must not be called")
    gateway = SupabaseGateway(client=client)

    with pytest.raises(ConversationCursorError, match="conversation cursor"):
        gateway.list_conversations(
            scope=PERSONAL,
            user_id="user-1",
            limit=2,
            cursor_updated_at=datetime(2026, 4, 27, tzinfo=timezone.utc),
            cursor_id="missing-conversation",
        )


def test_conversation_owner_scope_is_present_in_every_query() -> None:
    pivot = _conversation_row(2)
    client = _RecordingClient([pivot], [])
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    gateway.list_conversations(
        scope=PERSONAL,
        user_id="user-1",
        limit=2,
        cursor_updated_at=datetime(2026, 4, 27, tzinfo=timezone.utc),
        cursor_id=_conversation_id(2),
    )

    assert len(client.queries) == 2
    assert all(
        ("eq", ("user_id", "user-1")) in query.operations for query in client.queries
    )


def test_message_page_fetches_only_limit_plus_one() -> None:
    client = _RecordingClient([_message_row(idx) for idx in range(3)])
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    rows = gateway.list_messages(
        user_id="user-1",
        conversation_id=_conversation_id(1),
        limit=2,
        page=True,
    )

    assert [row.id for row in rows] == [
        _message_id(0),
        _message_id(1),
        _message_id(2),
    ]
    assert client.table_names == ["messages"]
    assert ("limit", (3,)) in client.queries[0].operations
    assert "range" not in _operation_names(client.queries[0])


def test_message_page_delegates_then_preserves_batched_hydration() -> None:
    reader = MagicMock()
    reader.list_message_rows.return_value = [
        _message_row(0),
        _message_row(1),
        _message_row(2),
    ]
    client = MagicMock()
    client.table.side_effect = AssertionError("PostgREST must not read page candidates")
    gateway = SupabaseGateway(client=client, keyset_reader=reader)
    gateway.get_backtest_jobs_by_ids = MagicMock(return_value={})  # type: ignore[method-assign]
    gateway.get_backtest_runs_by_ids = MagicMock(return_value={})  # type: ignore[method-assign]

    rows = gateway.list_messages(
        user_id="30000000-0000-0000-0000-000000000001",
        conversation_id=_conversation_id(1),
        limit=2,
        page=True,
    )

    assert [row.id for row in rows] == [
        _message_id(0),
        _message_id(1),
        _message_id(2),
    ]
    reader.list_message_rows.assert_called_once_with(
        user_id="30000000-0000-0000-0000-000000000001",
        conversation_id=_conversation_id(1),
        limit=2,
        cursor_created_at=None,
        cursor_id=None,
    )
    gateway.get_backtest_jobs_by_ids.assert_called_once_with(
        user_id="30000000-0000-0000-0000-000000000001",
        conversation_id=_conversation_id(1),
        job_ids=[],
    )
    gateway.get_backtest_runs_by_ids.assert_called_once_with(
        user_id="30000000-0000-0000-0000-000000000001",
        conversation_id=_conversation_id(1),
        run_ids=[],
    )
    client.table.assert_not_called()


def test_message_page_uses_created_at_id_asc_after_cursor() -> None:
    timestamp = datetime(2026, 4, 27, tzinfo=timezone.utc)
    client = _RecordingClient([])
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    gateway.list_messages(
        user_id="user-1",
        conversation_id=_conversation_id(1),
        limit=20,
        cursor_created_at=timestamp,
        cursor_id=_message_id(2),
        page=True,
    )

    orders = [
        operation for operation in client.queries[0].operations if operation[0] == "order"
    ]
    assert orders == [
        ("order", ("created_at", ("desc", False))),
        ("order", ("id", ("desc", False))),
    ]
    keyset_filter = next(
        args[0]
        for name, args in client.queries[0].operations
        if name == "or_" and "created_at.gt" in str(args[0])
    )
    assert f"created_at.gt.{timestamp.isoformat()}" in keyset_filter
    assert f"created_at.eq.{timestamp.isoformat()}" in keyset_filter
    assert f"id.gt.{_message_id(2)}" in keyset_filter


def test_message_equal_timestamps_and_deleted_pivot_are_stable() -> None:
    timestamp = datetime(2026, 4, 27, tzinfo=timezone.utc)
    page = [_message_row(idx, created_at=timestamp.isoformat()) for idx in range(3, 6)]
    client = _RecordingClient(page)
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    rows = gateway.list_messages(
        user_id="user-1",
        conversation_id=_conversation_id(1),
        limit=2,
        cursor_created_at=timestamp,
        cursor_id=_message_id(2),
        page=True,
    )

    assert [row.id for row in rows] == [
        _message_id(3),
        _message_id(4),
        _message_id(5),
    ]
    assert client.table_names == ["messages"]


def test_message_owner_and_conversation_scope_are_present() -> None:
    client = _RecordingClient([])
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    gateway.list_messages(
        user_id="user-1",
        conversation_id=_conversation_id(1),
        limit=20,
        page=True,
    )

    assert ("eq", ("user_id", "user-1")) in client.queries[0].operations
    assert (
        "eq",
        ("conversation_id", _conversation_id(1)),
    ) in client.queries[0].operations


def test_message_page_excludes_retired_markers_before_database_limit() -> None:
    client = _RecordingClient([])
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    gateway.list_messages(
        user_id="user-1",
        conversation_id=_conversation_id(1),
        limit=20,
        page=True,
    )

    visibility_filter = next(
        args[0]
        for name, args in client.queries[0].operations
        if name == "or_" and "role.neq.user" in str(args[0])
    )
    assert "role.neq.user" in visibility_filter
    assert "content.neq.__ONBOARDING_SKIP__" in visibility_filter
    assert r"content.not.like.\_\_ONBOARDING\_GOAL\_\_:*" in visibility_filter
    filter_index = _operation_names(client.queries[0]).index("or_")
    limit_index = _operation_names(client.queries[0]).index("limit")
    assert filter_index < limit_index


def test_message_malformed_cursor_id_fails_before_postgrest() -> None:
    client = MagicMock()
    client.table.side_effect = AssertionError("PostgREST must not be called")
    gateway = SupabaseGateway(client=client)

    with pytest.raises(ValueError, match="message cursor"):
        gateway.list_messages(
            user_id="user-1",
            conversation_id=_conversation_id(1),
            limit=20,
            cursor_created_at=datetime(2026, 4, 27, tzinfo=timezone.utc),
            cursor_id="missing-message",
            page=True,
        )


def test_message_page_context_uses_bounded_owner_scoped_witness_queries() -> None:
    timestamp = datetime(2026, 4, 27, tzinfo=timezone.utc)
    page_messages = [
        {
            **_message_row(1, created_at=timestamp.isoformat()),
            "metadata": {
                "chat_action": {
                    "type": "run_backtest",
                    "payload": {"confirmation_id": "confirmation-1"},
                }
            },
        },
        {
            **_message_row(
                2,
                created_at=(timestamp.replace(microsecond=1)).isoformat(),
                role="assistant",
            ),
            "metadata": {
                "agent_runtime_turn": {"request_id": "request-1"},
                "agent_runtime_stage_outcome": "agent_runtime_failure",
                "conversation_mode": "recovery",
                "recovery": {"code": "runtime_failure", "retryable": True},
            },
        },
    ]
    later_user = _message_row(
        3,
        created_at=timestamp.replace(microsecond=2).isoformat(),
    )
    later_artifact = {
        **_message_row(
            4,
            created_at=timestamp.replace(microsecond=3).isoformat(),
            role="assistant",
        ),
        "metadata": {"confirmation_card": {"status": "ready_to_run"}},
    }
    represented = {
        **_message_row(
            5,
            created_at=timestamp.replace(microsecond=4).isoformat(),
            role="assistant",
        ),
        "metadata": {
            "backtest_job": {
                "id": "job-1",
                "request_message_id": _message_id(1),
            }
        },
    }
    client = _RecordingClient(
        [later_user],
        [later_artifact],
        [later_artifact],
        [later_artifact],
        [represented],
    )
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    later_work, represented_request_ids = gateway.list_message_page_context(
        user_id="user-1",
        conversation_id=_conversation_id(1),
        page_messages=[Message.model_validate(row) for row in page_messages],
    )

    assert [message.id for message in later_work] == [
        _message_id(3),
        _message_id(4),
        _message_id(5),
    ]
    assert represented_request_ids == {_message_id(1)}
    assert len(client.queries) == 5
    for query in client.queries:
        assert ("eq", ("user_id", "user-1")) in query.operations
        assert (
            "eq",
            ("conversation_id", _conversation_id(1)),
        ) in query.operations
        assert ("limit", (1,)) in query.operations
        assert any(
            name == "or_" and "created_at.gt" in str(args[0])
            for name, args in query.operations
        )


def test_message_page_context_skips_keyed_queries_for_non_failure_messages() -> None:
    timestamp = datetime(2026, 4, 27, tzinfo=timezone.utc)
    message = Message.model_validate(
        {
            **_message_row(
                1,
                created_at=timestamp.isoformat(),
                role="assistant",
            ),
            "metadata": {
                "agent_runtime_turn": {"request_id": "ordinary-request"},
            },
        }
    )
    client = _RecordingClient([], [], [])
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    assert gateway.list_message_page_context(
        user_id="user-1",
        conversation_id=_conversation_id(1),
        page_messages=[message],
    ) == ([], set())
    assert len(client.queries) == 3


def test_message_page_context_keeps_distinct_reload_and_lifecycle_artifacts() -> None:
    timestamp = datetime(2026, 4, 27, tzinfo=timezone.utc)
    page_message = Message.model_validate(
        _message_row(1, created_at=timestamp.isoformat())
    )
    broader_reload_artifact = {
        **_message_row(
            2,
            created_at=timestamp.replace(microsecond=1).isoformat(),
            role="assistant",
        ),
        "metadata": {"confirmation_payload": {"strategy": {"symbols": ["AAPL"]}}},
    }
    lifecycle_artifact = {
        **_message_row(
            3,
            created_at=timestamp.replace(microsecond=2).isoformat(),
            role="assistant",
        ),
        "metadata": {"result_card": {"run_id": "run-1"}},
    }
    client = _RecordingClient(
        [],
        [broader_reload_artifact],
        [lifecycle_artifact],
    )
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    later_work, represented_request_ids = gateway.list_message_page_context(
        user_id="user-1",
        conversation_id=_conversation_id(1),
        page_messages=[page_message],
    )

    assert [message.id for message in later_work] == [
        _message_id(2),
        _message_id(3),
    ]
    assert represented_request_ids == set()
    assert len(client.queries) == 3


def test_message_page_context_artifact_filters_exclude_empty_values() -> None:
    timestamp = datetime(2026, 4, 27, tzinfo=timezone.utc)
    page_message = Message.model_validate(
        _message_row(1, created_at=timestamp.isoformat())
    )
    real_artifact = {
        **_message_row(
            3,
            created_at=timestamp.replace(microsecond=2).isoformat(),
            role="assistant",
        ),
        "metadata": {"result_card": {"run_id": "run-1"}},
    }
    client = _RecordingClient([], [real_artifact], [real_artifact])
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]

    later_work, _ = gateway.list_message_page_context(
        user_id="user-1",
        conversation_id=_conversation_id(1),
        page_messages=[page_message],
    )

    assert [message.id for message in later_work] == [_message_id(3)]
    reload_filter = next(
        args[0] for name, args in client.queries[1].operations if name == "or_"
    )
    lifecycle_filter = next(
        args[0] for name, args in client.queries[2].operations if name == "or_"
    )
    assert "metadata->>confirmation_payload.neq." in reload_filter
    assert "metadata->confirmation_payload.neq.{}" in reload_filter
    assert "confirmation_payload" not in lifecycle_filter
    assert "metadata->>result_card.neq." in lifecycle_filter
    assert "metadata->result_card.neq.{}" in lifecycle_filter


@pytest.mark.skipif(
    not all(
        (
            os.getenv("ARGUS_LOCAL_SUPABASE_URL", "").strip(),
            os.getenv("ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        )
    ),
    reason="local Supabase pagination proof is not configured",
)
def test_conversation_soft_deleted_pivot_is_stable_in_real_postgres() -> None:
    local_url = os.environ["ARGUS_LOCAL_SUPABASE_URL"].strip()
    service_key = os.environ["ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY"].strip()
    client = create_client(local_url, service_key)
    gateway = SupabaseGateway(client=client)
    email = f"conversation-pagination-{uuid4()}@argus.local"
    created = client.auth.admin.create_user(
        {
            "email": email,
            "password": f"Local-{uuid4()}",
            "email_confirm": True,
        }
    )
    assert created.user is not None
    user_id = str(created.user.id)
    timestamp = datetime(2026, 4, 27, tzinfo=timezone.utc)
    conversation_ids = [f"00000000-0000-0000-0000-{value:012d}" for value in range(1, 7)]

    try:
        gateway.get_or_create_profile_for_auth_user(
            {"id": user_id, "email": email, "user_metadata": {}}
        )
        client.table("conversations").insert(
            [
                {
                    "id": conversation_id,
                    "user_id": user_id,
                    "title": f"Conversation {idx}",
                    "title_source": "system_default",
                    "language": "en",
                    "pinned": idx >= 3,
                    "archived": False,
                    "created_at": timestamp.isoformat(),
                    "updated_at": timestamp.isoformat(),
                }
                for idx, conversation_id in enumerate(conversation_ids)
            ]
        ).execute()

        first_candidates = gateway.list_conversations(
            scope=PERSONAL, user_id=user_id, limit=2
        )
        first_page = first_candidates[:2]
        assert [item.id for item in first_candidates] == [
            conversation_ids[5],
            conversation_ids[4],
            conversation_ids[3],
        ]

        pivot = first_page[-1]
        assert gateway.soft_delete_conversation(
            user_id=user_id,
            conversation_id=pivot.id,
        )
        second_candidates = gateway.list_conversations(
            scope=PERSONAL,
            user_id=user_id,
            limit=2,
            cursor_updated_at=timestamp,
            cursor_id=pivot.id,
        )

        assert [item.id for item in second_candidates] == [
            conversation_ids[3],
            conversation_ids[2],
            conversation_ids[1],
        ]
        assert {item.id for item in first_page}.isdisjoint(
            item.id for item in second_candidates[:2]
        )
    finally:
        with suppress(Exception):
            gateway.delete_auth_user(user_id)


@pytest.mark.skipif(
    not all(
        (
            os.getenv("ARGUS_LOCAL_SUPABASE_URL", "").strip(),
            os.getenv("ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        )
    ),
    reason="local Supabase pagination proof is not configured",
)
def test_message_page_is_stable_and_filters_markers_in_real_postgres() -> None:
    local_url = os.environ["ARGUS_LOCAL_SUPABASE_URL"].strip()
    service_key = os.environ["ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY"].strip()
    client = create_client(local_url, service_key)
    gateway = SupabaseGateway(client=client)
    email = f"message-pagination-{uuid4()}@argus.local"
    created = client.auth.admin.create_user(
        {
            "email": email,
            "password": f"Local-{uuid4()}",
            "email_confirm": True,
        }
    )
    assert created.user is not None
    user_id = str(created.user.id)
    timestamp = datetime(2026, 4, 27, tzinfo=timezone.utc)
    conversation_id = _conversation_id(900)
    message_ids = [_message_id(value) for value in range(1, 7)]
    contents = [
        "First public message",
        "__ONBOARDING_SKIP__",
        "__ONBOARDING_SKIP__",
        "__ONBOARDING_GOAL__:test_stock_idea",
        "Second public user message",
        "Third public user message",
    ]
    roles = ["user", "user", "assistant", "user", "user", "user"]

    try:
        gateway.get_or_create_profile_for_auth_user(
            {"id": user_id, "email": email, "user_metadata": {}}
        )
        client.table("conversations").insert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "title": "Message pagination",
                "title_source": "system_default",
                "language": "en",
                "created_at": timestamp.isoformat(),
                "updated_at": timestamp.isoformat(),
            }
        ).execute()
        client.table("messages").insert(
            [
                {
                    "id": message_id,
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "content": content,
                    "metadata": {},
                    "created_at": timestamp.isoformat(),
                }
                for message_id, role, content in zip(
                    message_ids,
                    roles,
                    contents,
                    strict=True,
                )
            ]
        ).execute()

        first_candidates = gateway.list_messages(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=2,
            page=True,
        )
        assert [message.id for message in first_candidates] == [
            message_ids[0],
            message_ids[2],
            message_ids[4],
        ]
        later_work, represented_request_ids = gateway.list_message_page_context(
            user_id=user_id,
            conversation_id=conversation_id,
            page_messages=first_candidates,
        )
        assert [message.id for message in later_work] == [message_ids[5]]
        assert represented_request_ids == set()
        pivot = first_candidates[1]
        client.table("messages").delete().eq("user_id", user_id).eq(
            "conversation_id",
            conversation_id,
        ).eq("id", pivot.id).execute()

        second_candidates = gateway.list_messages(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=2,
            cursor_created_at=timestamp,
            cursor_id=pivot.id,
            page=True,
        )

        assert [message.id for message in second_candidates] == [
            message_ids[4],
            message_ids[5],
        ]
        assert {message.id for message in first_candidates[:2]}.isdisjoint(
            message.id for message in second_candidates
        )

        context_rows = [
            {
                "id": _message_id(101),
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": "user",
                "content": "Context page A",
                "metadata": {},
                "created_at": timestamp.replace(microsecond=1).isoformat(),
            },
            {
                "id": _message_id(102),
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": "Broader reload artifact",
                "metadata": {"confirmation_payload": {"strategy": {"symbols": ["AAPL"]}}},
                "created_at": timestamp.replace(microsecond=2).isoformat(),
            },
            {
                "id": _message_id(103),
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": "Lifecycle artifact",
                "metadata": {"result_card": {"run_id": "run-1"}},
                "created_at": timestamp.replace(microsecond=3).isoformat(),
            },
            {
                "id": _message_id(104),
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": "user",
                "content": "Context page B",
                "metadata": {},
                "created_at": timestamp.replace(microsecond=4).isoformat(),
            },
            {
                "id": _message_id(105),
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": "Empty artifact",
                "metadata": {"confirmation_card": {}},
                "created_at": timestamp.replace(microsecond=5).isoformat(),
            },
            {
                "id": _message_id(106),
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": "Real artifact",
                "metadata": {"result_card": {"run_id": "run-2"}},
                "created_at": timestamp.replace(microsecond=6).isoformat(),
            },
        ]
        client.table("messages").insert(context_rows).execute()

        first_context, _ = gateway.list_message_page_context(
            user_id=user_id,
            conversation_id=conversation_id,
            page_messages=[Message.model_validate(context_rows[0])],
        )
        assert [message.id for message in first_context] == [
            _message_id(102),
            _message_id(103),
            _message_id(104),
        ]

        empty_context, _ = gateway.list_message_page_context(
            user_id=user_id,
            conversation_id=conversation_id,
            page_messages=[Message.model_validate(context_rows[3])],
        )
        assert [message.id for message in empty_context] == [_message_id(106)]
    finally:
        with suppress(Exception):
            gateway.delete_auth_user(user_id)
