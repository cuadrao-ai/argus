from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from argus.domain.owner_scope import PERSONAL


class _RecordingCursor:
    def __init__(self, result_sets: list[list[dict[str, Any]]]) -> None:
        self._result_sets = list(result_sets)
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> _RecordingCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self.executions.append((query, params))

    def fetchall(self) -> list[dict[str, Any]]:
        return self._result_sets.pop(0)


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor

    def cursor(self, **_kwargs: Any) -> _RecordingCursor:
        return self._cursor


class _RecordingPool:
    def __init__(self, result_sets: list[list[dict[str, Any]]]) -> None:
        self.cursor = _RecordingCursor(result_sets)
        self.acquisition_timeouts: list[float] = []

    @contextmanager
    def connection(self, *, timeout: float):
        self.acquisition_timeouts.append(timeout)
        yield _RecordingConnection(self.cursor)


def _reader_types():
    from argus.domain.postgres_keyset_reader import (
        ConversationKeysetCursorError,
        PostgresKeysetReader,
    )

    return ConversationKeysetCursorError, PostgresKeysetReader


def test_preview_read_uses_one_owner_scoped_latest_message_query():
    _, reader_type = _reader_types()
    owner = "30000000-0000-0000-0000-000000000001"
    ids = ["20000000-0000-0000-0000-000000000001", "20000000-0000-0000-0000-000000000002"]
    pool = _RecordingPool(
        [
            [
                {
                    "conversation_id": UUID(ids[0]),
                    "id": UUID(ids[1]),
                    "metadata": {"result_card": {}},
                }
            ]
        ]
    )
    rows = reader_type(pool).read_conversation_preview_messages(
        user_id=owner, conversation_ids=ids
    )
    assert rows[0]["conversation_id"] == ids[0]
    assert rows[0]["id"] == ids[1]
    assert len(pool.cursor.executions) == 1
    sql, params = pool.cursor.executions[0]
    assert "left join lateral" in sql
    assert "m.user_id = c.user_id and m.conversation_id = c.id" in sql
    assert "where c.user_id = %s and c.id = any(%s)" in sql
    assert "order by m.created_at desc, m.id desc" in sql
    assert "limit 1" in sql
    assert params[-2:] == (UUID(owner), [UUID(value) for value in ids])
    assert pool.acquisition_timeouts == [2.0]


def _conversation_row(
    value: int,
    *,
    pinned: bool = False,
    archived: bool = False,
    deleted_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"00000000-0000-0000-0000-{value:012d}",
        "title": f"Conversation {value}",
        "title_source": "system_default",
        "language": "en",
        "pinned": pinned,
        "archived": archived,
        "last_message_preview": None,
        "deleted_at": deleted_at,
        "created_at": "2026-07-27T00:00:00+00:00",
        "updated_at": "2026-07-27T00:00:00+00:00",
    }


def _message_row(value: int, *, role: str = "user") -> dict[str, Any]:
    return {
        "id": f"10000000-0000-0000-0000-{value:012d}",
        "conversation_id": "20000000-0000-0000-0000-000000000001",
        "role": role,
        "content": f"Message {value}",
        "metadata": {},
        "created_at": "2026-07-27T00:00:00+00:00",
    }


def test_conversation_first_page_uses_owner_scoped_limit_plus_one_sql() -> None:
    _, reader_type = _reader_types()
    rows = [_conversation_row(1), _conversation_row(2), _conversation_row(3)]
    pool = _RecordingPool([rows])
    reader = reader_type(pool)

    assert (
        reader.list_conversation_rows(
            scope=PERSONAL,
            user_id="30000000-0000-0000-0000-000000000001",
            limit=2,
            archived=None,
            deleted=False,
        )
        == rows
    )

    assert pool.acquisition_timeouts == [2.0]
    assert len(pool.cursor.executions) == 1
    sql, params = pool.cursor.executions[0]
    assert "where user_id = %s" in sql
    assert "deleted_at is null" in sql
    assert "archived =" not in sql
    assert "order by pinned desc, updated_at desc, id desc" in sql
    assert "limit %s" in sql
    assert params == (
        UUID("30000000-0000-0000-0000-000000000001"),
        3,
    )


@pytest.mark.parametrize(
    ("archived", "deleted", "archive_sql", "delete_sql"),
    [
        (None, False, "archived =", "deleted_at is null"),
        (False, False, "archived = %s", "deleted_at is null"),
        (True, False, "archived = %s", "deleted_at is null"),
        (None, True, "archived =", "deleted_at is not null"),
    ],
)
def test_conversation_cursor_uses_exact_pivot_and_tuple_keyset_variants(
    archived: bool | None,
    deleted: bool,
    archive_sql: str,
    delete_sql: str,
) -> None:
    _, reader_type = _reader_types()
    cursor_at = datetime(2026, 7, 27, tzinfo=timezone.utc)
    cursor_id = "00000000-0000-0000-0000-000000000009"
    rows = [_conversation_row(8, pinned=True)]
    pool = _RecordingPool([[{"id": cursor_id, "pinned": True}], rows])

    assert (
        reader_type(pool).list_conversation_rows(
            scope=PERSONAL,
            user_id="30000000-0000-0000-0000-000000000001",
            limit=20,
            archived=archived,
            deleted=deleted,
            cursor_updated_at=cursor_at,
            cursor_id=cursor_id,
        )
        == rows
    )

    assert len(pool.cursor.executions) == 2
    pivot_sql, pivot_params = pool.cursor.executions[0]
    assert "select id, pinned" in pivot_sql
    assert "where user_id = %s" in pivot_sql
    assert "and id = %s" in pivot_sql
    assert "deleted_at" not in pivot_sql
    assert "archived" not in pivot_sql
    assert pivot_params == (
        UUID("30000000-0000-0000-0000-000000000001"),
        UUID(cursor_id),
    )

    candidate_sql, candidate_params = pool.cursor.executions[1]
    assert delete_sql in candidate_sql
    if archived is None:
        assert archive_sql not in candidate_sql
    else:
        assert archive_sql in candidate_sql
        assert archived in candidate_params
    assert "(pinned, updated_at, id) < (%s, %s, %s)" in candidate_sql
    assert True in candidate_params
    assert cursor_at in candidate_params
    assert UUID(cursor_id) in candidate_params
    assert candidate_params[-1] == 21


@pytest.mark.parametrize(
    "pivot_rows",
    [
        [],
        [
            {
                "id": "00000000-0000-0000-0000-000000000009",
                "pinned": True,
            },
            {
                "id": "00000000-0000-0000-0000-000000000009",
                "pinned": True,
            },
        ],
        [
            {
                "id": "00000000-0000-0000-0000-000000000008",
                "pinned": True,
            }
        ],
        [
            {
                "id": "00000000-0000-0000-0000-000000000009",
                "pinned": "true",
            }
        ],
    ],
    ids=["missing", "ambiguous", "wrong-id", "invalid-pinned"],
)
def test_conversation_missing_foreign_or_ambiguous_pivot_fails_closed(
    pivot_rows: list[dict[str, Any]],
) -> None:
    cursor_error, reader_type = _reader_types()
    pool = _RecordingPool([pivot_rows])

    with pytest.raises(cursor_error):
        reader_type(pool).list_conversation_rows(
            scope=PERSONAL,
            user_id="30000000-0000-0000-0000-000000000001",
            limit=20,
            archived=False,
            deleted=False,
            cursor_updated_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
            cursor_id="00000000-0000-0000-0000-000000000009",
        )

    assert len(pool.cursor.executions) == 1


def test_message_page_uses_tuple_keyset_and_filters_retired_user_markers() -> None:
    _, reader_type = _reader_types()
    cursor_at = datetime(2026, 7, 27, tzinfo=timezone.utc)
    cursor_id = "10000000-0000-0000-0000-000000000009"
    rows = [_message_row(10), _message_row(11), _message_row(12)]
    pool = _RecordingPool([rows])

    assert (
        reader_type(pool).list_message_rows(
            user_id="30000000-0000-0000-0000-000000000001",
            conversation_id="20000000-0000-0000-0000-000000000001",
            limit=2,
            cursor_created_at=cursor_at,
            cursor_id=cursor_id,
        )
        == rows
    )

    assert len(pool.cursor.executions) == 1
    sql, params = pool.cursor.executions[0]
    assert "where user_id = %s" in sql
    assert "and conversation_id = %s" in sql
    assert "role <> 'user'" in sql
    assert "content <> %s" in sql
    assert r"content not like %s escape '\'" in sql
    assert "(created_at, id) > (%s, %s)" in sql
    assert "order by created_at asc, id asc" in sql
    assert params == (
        UUID("30000000-0000-0000-0000-000000000001"),
        UUID("20000000-0000-0000-0000-000000000001"),
        "__ONBOARDING_SKIP__",
        r"\_\_ONBOARDING\_GOAL\_\_:%",
        cursor_at,
        UUID(cursor_id),
        3,
    )


def test_keyset_reader_rejects_invalid_or_incomplete_ids_before_acquiring_pool() -> None:
    cursor_error, reader_type = _reader_types()
    pool = _RecordingPool([])
    reader = reader_type(pool)

    with pytest.raises(ValueError, match="owner"):
        reader.list_conversation_rows(
            scope=PERSONAL,
            user_id="not-a-uuid",
            limit=20,
            archived=False,
            deleted=False,
        )
    with pytest.raises(cursor_error, match="incomplete"):
        reader.list_conversation_rows(
            scope=PERSONAL,
            user_id="30000000-0000-0000-0000-000000000001",
            limit=20,
            archived=False,
            deleted=False,
            cursor_updated_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="conversation"):
        reader.list_message_rows(
            user_id="30000000-0000-0000-0000-000000000001",
            conversation_id="not-a-uuid",
            limit=20,
        )

    assert pool.acquisition_timeouts == []
