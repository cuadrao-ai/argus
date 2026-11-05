from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from argus.domain.owner_scope import PERSONAL


class _RecordingCursor:
    def __init__(self, result_sets: list[list[dict[str, Any]]]) -> None:
        self._result_sets = result_sets
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
    try:
        from argus.domain.postgres_history_reader import (
            HistoryCursorError,
            PostgresHistoryReader,
        )
    except ModuleNotFoundError:
        pytest.fail("bounded Postgres History reader is not implemented")
    return HistoryCursorError, PostgresHistoryReader


def test_history_first_page_uses_one_bounded_query_and_preserves_raw_groups() -> None:
    _, reader_type = _reader_types()
    pool = _RecordingPool(
        [
            [
                {
                    "source_type": "chat",
                    "payload": {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "title": "AAPL idea",
                        "title_source": "ai_generated",
                        "last_message_preview": "Test AAPL",
                        "pinned": True,
                        "updated_at": "2026-07-01T00:00:00+00:00",
                    },
                },
                {
                    "source_type": "collection",
                    "payload": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "name": "Watch next",
                        "pinned": False,
                        "strategy_count": 3,
                        "updated_at": "2026-06-30T00:00:00+00:00",
                    },
                },
            ]
        ]
    )

    rows = reader_type(pool).list_rows(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        limit=3,
        archived=False,
        deleted=False,
    )

    assert rows == {
        "runs": [],
        "conversations": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "title": "AAPL idea",
                "title_source": "ai_generated",
                "last_message_preview": "Test AAPL",
                "pinned": True,
                "updated_at": "2026-07-01T00:00:00+00:00",
            }
        ],
        "strategies": [],
        "collections": [
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "Watch next",
                "pinned": False,
                "strategy_count": 3,
                "updated_at": "2026-06-30T00:00:00+00:00",
            }
        ],
    }
    assert len(pool.cursor.executions) == 1
    assert pool.acquisition_timeouts == [2.0]


def test_history_cursor_uses_one_pivot_query_and_one_candidate_query() -> None:
    _, reader_type = _reader_types()
    cursor_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    pool = _RecordingPool(
        [
            [
                {
                    "source_type": "strategy",
                    "pinned": True,
                    "type_rank": 3,
                    "activity_at": cursor_at,
                }
            ],
            [],
        ]
    )

    rows = reader_type(pool).list_rows(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        limit=4,
        archived=False,
        deleted=False,
        cursor_activity_at=cursor_at,
        cursor_id="11111111-1111-1111-1111-111111111111",
    )

    assert rows == {
        "runs": [],
        "conversations": [],
        "strategies": [],
        "collections": [],
    }
    assert len(pool.cursor.executions) == 2
    candidate_params = pool.cursor.executions[1][1]
    assert candidate_params == {
        "user_id": UUID("00000000-0000-0000-0000-000000000001"),
        "owner_space_id": None,
        "cursor_activity_at": cursor_at,
        "cursor_id": UUID("11111111-1111-1111-1111-111111111111"),
        "source_limit": 4,
    }


def test_history_legacy_cursor_rejects_changed_pivot_activity() -> None:
    cursor_error, reader_type = _reader_types()
    cursor_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    pool = _RecordingPool(
        [
            [
                {
                    "source_type": "strategy",
                    "pinned": True,
                    "type_rank": 3,
                    "activity_at": cursor_at.replace(day=2),
                }
            ],
            [],
        ]
    )

    with pytest.raises(cursor_error, match="pivot changed"):
        reader_type(pool).list_rows(
            scope=PERSONAL,
            user_id="00000000-0000-0000-0000-000000000001",
            limit=4,
            archived=False,
            deleted=False,
            cursor_activity_at=cursor_at,
            cursor_id="11111111-1111-1111-1111-111111111111",
        )

    assert len(pool.cursor.executions) == 1


def test_history_ranked_cursor_rejects_source_rank_mismatch() -> None:
    cursor_error, reader_type = _reader_types()
    cursor_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    pool = _RecordingPool(
        [
            [
                {
                    "source_type": "strategy",
                    "pinned": False,
                    "type_rank": 3,
                    "activity_at": cursor_at,
                }
            ]
        ]
    )

    with pytest.raises(cursor_error, match="pivot rank"):
        reader_type(pool).list_rows(
            scope=PERSONAL,
            user_id="00000000-0000-0000-0000-000000000001",
            limit=4,
            archived=False,
            deleted=False,
            cursor_activity_at=cursor_at,
            cursor_id="11111111-1111-1111-1111-111111111111",
            cursor_pinned=False,
            cursor_type_rank=2,
        )

    assert len(pool.cursor.executions) == 1


def test_history_cursor_rejects_timezone_naive_timestamp_before_pool_acquisition() -> (
    None
):
    cursor_error, reader_type = _reader_types()
    pool = _RecordingPool([])

    with pytest.raises(cursor_error):
        reader_type(pool).list_rows(
            scope=PERSONAL,
            user_id="00000000-0000-0000-0000-000000000001",
            limit=4,
            archived=False,
            deleted=False,
            cursor_activity_at=datetime(2026, 7, 1),
            cursor_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        )

    assert pool.acquisition_timeouts == []
    assert pool.cursor.executions == []


@pytest.mark.parametrize(
    "cursor_id",
    [
        "{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}",
        "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
    ],
)
def test_history_cursor_rejects_noncanonical_uuid_before_pool_acquisition(
    cursor_id: str,
) -> None:
    cursor_error, reader_type = _reader_types()
    pool = _RecordingPool([])

    with pytest.raises(cursor_error):
        reader_type(pool).list_rows(
            scope=PERSONAL,
            user_id="00000000-0000-0000-0000-000000000001",
            limit=4,
            archived=False,
            deleted=False,
            cursor_activity_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            cursor_id=cursor_id,
        )

    assert pool.acquisition_timeouts == []
    assert pool.cursor.executions == []


def _source_sql(sql: str, source: str, next_source: str) -> str:
    start = sql.index(f"{source}_candidates as (")
    end = sql.index(f"{next_source}_candidates as (", start)
    return sql[start:end]


def test_history_candidate_sql_uses_cached_specialized_variants() -> None:
    from argus.domain.postgres_history_reader import _candidate_sql

    _candidate_sql.cache_clear()
    sql = _candidate_sql(
        business=False,
        archived=False,
        deleted=False,
        has_cursor=False,
        pivot_pinned=False,
        pivot_type_rank=0,
    )
    repeated = _candidate_sql(
        business=False,
        archived=False,
        deleted=False,
        has_cursor=False,
        pivot_pinned=False,
        pivot_type_rank=0,
    )

    assert sql == repeated
    assert _candidate_sql.cache_info().hits == 1
    assert "with input as" not in sql.lower()
    assert "input." not in sql
    assert "not has_cursor" not in sql
    assert "chat.archived is false" in sql
    assert "chat.deleted_at is null" in sql
    assert "strategy.deleted_at is null" in sql
    assert "collection.deleted_at is null" in sql
    assert "%(user_id)s" in sql
    assert "%(source_limit)s" in sql


def test_history_first_page_splits_pin_tiers_before_each_source_limit() -> None:
    from argus.domain.postgres_history_reader import _candidate_sql

    sql = _candidate_sql(
        business=False,
        archived=False,
        deleted=True,
        has_cursor=False,
        pivot_pinned=False,
        pivot_type_rank=0,
    )
    chat_sql = _source_sql(sql, "chat", "strategy")
    strategy_sql = _source_sql(sql, "strategy", "collection")
    collection_sql = sql[sql.index("collection_candidates as (") :]

    for source_sql in (chat_sql, strategy_sql, collection_sql):
        assert ".pinned is true" in source_sql
        assert ".pinned is false" in source_sql
        assert "union all" in source_sql.lower()


@pytest.mark.parametrize(
    (
        "pivot_type_rank",
        "run_predicate",
        "chat_predicate",
        "strategy_predicate",
        "collection_predicate",
    ),
    [
        (
            1,
            "row(run.created_at, run.id) < row(%(cursor_activity_at)s, %(cursor_id)s)",
            "chat.updated_at < %(cursor_activity_at)s",
            "strategy.updated_at < %(cursor_activity_at)s",
            "collection.updated_at < %(cursor_activity_at)s",
        ),
        (
            2,
            "run.created_at <= %(cursor_activity_at)s",
            "chat.updated_at < %(cursor_activity_at)s",
            "strategy.updated_at < %(cursor_activity_at)s",
            "row(collection.updated_at, collection.id) < row(%(cursor_activity_at)s, %(cursor_id)s)",
        ),
        (
            3,
            "run.created_at <= %(cursor_activity_at)s",
            "chat.updated_at < %(cursor_activity_at)s",
            "row(strategy.updated_at, strategy.id) < row(%(cursor_activity_at)s, %(cursor_id)s)",
            "collection.updated_at <= %(cursor_activity_at)s",
        ),
        (
            4,
            "run.created_at <= %(cursor_activity_at)s",
            "row(chat.updated_at, chat.id) < row(%(cursor_activity_at)s, %(cursor_id)s)",
            "strategy.updated_at <= %(cursor_activity_at)s",
            "collection.updated_at <= %(cursor_activity_at)s",
        ),
    ],
)
def test_history_unpinned_cursor_specializes_each_source_rank(
    pivot_type_rank: int,
    run_predicate: str,
    chat_predicate: str,
    strategy_predicate: str,
    collection_predicate: str,
) -> None:
    from argus.domain.postgres_history_reader import _candidate_sql

    sql = _candidate_sql(
        business=False,
        archived=False,
        deleted=False,
        has_cursor=True,
        pivot_pinned=False,
        pivot_type_rank=pivot_type_rank,
    )
    run_sql = _source_sql(sql, "run", "chat")
    chat_sql = _source_sql(sql, "chat", "strategy")
    strategy_sql = _source_sql(sql, "strategy", "collection")
    collection_sql = sql[sql.index("collection_candidates as (") :]

    assert run_predicate in run_sql
    assert chat_predicate in chat_sql
    assert strategy_predicate in strategy_sql
    assert collection_predicate in collection_sql
    for source_sql in (chat_sql, strategy_sql, collection_sql):
        assert ".pinned is false" in source_sql
        assert ".pinned is true" not in source_sql


@pytest.mark.parametrize("pivot_type_rank", [1, 2, 3, 4])
def test_history_pinned_cursor_splits_same_and_lower_pin_tiers(
    pivot_type_rank: int,
) -> None:
    from argus.domain.postgres_history_reader import _candidate_sql

    sql = _candidate_sql(
        business=False,
        archived=True,
        deleted=True,
        has_cursor=True,
        pivot_pinned=True,
        pivot_type_rank=pivot_type_rank,
    )
    run_sql = _source_sql(sql, "run", "chat")
    chat_sql = _source_sql(sql, "chat", "strategy")
    strategy_sql = _source_sql(sql, "strategy", "collection")
    collection_sql = sql[sql.index("collection_candidates as (") :]

    assert "run.created_at < %(cursor_activity_at)s" not in run_sql
    assert "run.created_at <= %(cursor_activity_at)s" not in run_sql
    assert "row(run.created_at, run.id)" not in run_sql
    assert "parent.archived is true" in run_sql
    assert "parent.deleted_at is not null" in run_sql
    assert "chat.archived is true" in chat_sql
    for source_sql in (chat_sql, strategy_sql, collection_sql):
        assert ".pinned is true" in source_sql
        assert ".pinned is false" in source_sql
        assert "union all" in source_sql.lower()


@pytest.mark.parametrize(
    "pivot_rows",
    [
        [],
        [
            {"source_type": "strategy", "pinned": False, "type_rank": 3},
            {"source_type": "collection", "pinned": False, "type_rank": 2},
        ],
    ],
)
def test_history_cursor_missing_or_ambiguous_pivot_fails_closed(
    pivot_rows: list[dict[str, Any]],
) -> None:
    cursor_error, reader_type = _reader_types()
    pool = _RecordingPool([pivot_rows])

    with pytest.raises(cursor_error):
        reader_type(pool).list_rows(
            scope=PERSONAL,
            user_id="00000000-0000-0000-0000-000000000001",
            limit=4,
            archived=False,
            deleted=False,
            cursor_activity_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            cursor_id="11111111-1111-1111-1111-111111111111",
        )

    assert len(pool.cursor.executions) == 1


def test_history_pool_bounds_connections_and_statement_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        from argus.domain import postgres_history_reader
    except ImportError:
        pytest.fail("bounded Postgres History reader is not implemented")
    captured: dict[str, Any] = {}

    class _Pool:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def close(self) -> None:
            return None

    postgres_history_reader.history_reader_for_database_url.cache_clear()
    monkeypatch.setattr(postgres_history_reader, "ConnectionPool", _Pool)

    postgres_history_reader.history_reader_for_database_url(
        "postgresql://history-pool/argus"
    )

    assert captured["min_size"] == 0
    assert captured["max_size"] == 5
    assert (
        f"statement_timeout={postgres_history_reader._HISTORY_STATEMENT_TIMEOUT_MS}"
        in captured["kwargs"]["options"]
    )
    postgres_history_reader.history_reader_for_database_url.cache_clear()


def test_supabase_persistence_requires_and_injects_history_database_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain import supabase_gateway

    monkeypatch.setenv("SUPABASE_URL", "https://argus.local")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        supabase_gateway.SupabaseGateway.from_env()

    reader = MagicMock()
    monkeypatch.setenv("DATABASE_URL", "postgresql://history-pool/argus")
    monkeypatch.setattr(supabase_gateway, "create_client", MagicMock())
    reader_factory = MagicMock(return_value=reader)
    monkeypatch.setattr(
        supabase_gateway,
        "history_reader_for_database_url",
        reader_factory,
    )
    search_reader = MagicMock()
    search_reader_factory = MagicMock(return_value=search_reader)
    monkeypatch.setattr(
        supabase_gateway,
        "PostgresSearchReader",
        search_reader_factory,
    )
    keyset_reader = MagicMock()
    keyset_reader_factory = MagicMock(return_value=keyset_reader)
    monkeypatch.setattr(
        supabase_gateway,
        "PostgresKeysetReader",
        keyset_reader_factory,
    )

    gateway = supabase_gateway.SupabaseGateway.from_env()

    assert gateway.history_reader is reader
    assert gateway.search_reader is search_reader
    assert gateway.keyset_reader is keyset_reader
    reader_factory.assert_called_once_with("postgresql://history-pool/argus")
    search_reader_factory.assert_called_once_with(reader.pool)
    keyset_reader_factory.assert_called_once_with(reader.pool)
