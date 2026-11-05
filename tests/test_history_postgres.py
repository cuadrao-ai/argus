"""Real-Postgres proofs for bounded merged History reads."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.postgres_history_reader import (
    HistoryCursorError,
    PostgresHistoryReader,
    _candidate_sql,
)
from psycopg.types.json import Jsonb

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)

_RANK = {"chat": 4, "strategy": 3, "collection": 2, "run": 1}


class _TrackingCursor:
    def __init__(self, cursor: Any, tracker: dict[str, Any]) -> None:
        self._cursor = cursor
        self._tracker = tracker

    def __enter__(self) -> _TrackingCursor:
        self._cursor.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._cursor.__exit__(*args)

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self._tracker["query_count"] += 1
        self._cursor.execute(query, params)

    def fetchall(self) -> list[dict[str, Any]]:
        rows = self._cursor.fetchall()
        self._tracker["row_counts"].append(len(rows))
        return rows


class _TrackingConnection:
    def __init__(self, connection: Any, tracker: dict[str, Any]) -> None:
        self._connection = connection
        self._tracker = tracker

    def cursor(self, **kwargs: Any) -> _TrackingCursor:
        return _TrackingCursor(self._connection.cursor(**kwargs), self._tracker)


class _TrackingPool:
    def __init__(self) -> None:
        self.tracker: dict[str, Any] = {"query_count": 0, "row_counts": []}

    @contextmanager
    def connection(self, *, timeout: float):
        assert timeout == 2.0
        with psycopg.connect(DSN, autocommit=True) as connection:
            yield _TrackingConnection(connection, self.tracker)


@pytest.fixture
def history_identities():
    owner_id = uuid4()
    other_id = uuid4()
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            for user_id, label in ((owner_id, "owner"), (other_id, "other")):
                email = f"history-{label}-{user_id}@argus.local"
                cursor.execute(
                    "insert into auth.users (id, email, is_anonymous)"
                    " values (%s, %s, false)",
                    (user_id, email),
                )
                cursor.execute(
                    "insert into public.profiles (id, email) values (%s, %s)",
                    (user_id, email),
                )
    try:
        yield {"owner": owner_id, "other": other_id}
    finally:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from auth.users where id = any(%s::uuid[])",
                    ([owner_id, other_id],),
                )


@pytest.fixture(scope="module")
def history_plan_scale_rows():
    small_owner_id = uuid4()
    large_owner_id = uuid4()
    base = datetime(2026, 7, 27, tzinfo=timezone.utc)
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            for owner_id, label, row_count in (
                (small_owner_id, "small", 64),
                (large_owner_id, "large", 12_000),
            ):
                email = f"history-plan-{label}-{owner_id}@argus.local"
                cursor.execute(
                    "insert into auth.users (id, email, is_anonymous)"
                    " values (%s, %s, false)",
                    (owner_id, email),
                )
                cursor.execute(
                    "insert into public.profiles (id, email) values (%s, %s)",
                    (owner_id, email),
                )
                cursor.execute(
                    """
                    insert into public.conversations (
                        id, user_id, title, title_source, language, pinned,
                        archived, last_message_preview, created_at, updated_at
                    )
                    select
                        md5(%s || value::text)::uuid,
                        %s,
                        'History plan conversation ' || value::text,
                        'system_default',
                        'en',
                        value <= 8,
                        false,
                        'Fixture preview',
                        %s::timestamptz + value * interval '1 millisecond',
                        %s::timestamptz + value * interval '1 millisecond'
                    from generate_series(1, %s) as value
                    """,
                    (
                        f"history-plan-{label}-conversation-",
                        owner_id,
                        base,
                        base,
                        row_count,
                    ),
                )
                cursor.execute(
                    """
                    insert into public.messages (
                        id, conversation_id, user_id, role, content, metadata,
                        created_at
                    )
                    select
                        md5(%s || value::text)::uuid,
                        md5(%s || value::text)::uuid,
                        %s,
                        'user',
                        'History plan message',
                        '{}'::jsonb,
                        %s::timestamptz + value * interval '1 millisecond'
                    from generate_series(1, %s) as value
                    """,
                    (
                        f"history-plan-{label}-message-",
                        f"history-plan-{label}-conversation-",
                        owner_id,
                        base,
                        row_count,
                    ),
                )
                cursor.execute(
                    """
                    insert into public.backtest_runs (
                        id, user_id, conversation_id, status, asset_class,
                        symbols, allocation_method, benchmark_symbol,
                        config_snapshot, metrics, conversation_result_card,
                        created_at, updated_at
                    )
                    select
                        md5(%s || value::text)::uuid,
                        %s,
                        md5(%s || value::text)::uuid,
                        'completed',
                        'equity',
                        array['AAPL'],
                        'equal_weight',
                        'SPY',
                        '{}'::jsonb,
                        '{}'::jsonb,
                        '{}'::jsonb,
                        %s::timestamptz + value * interval '1 millisecond',
                        %s::timestamptz + value * interval '1 millisecond'
                    from generate_series(1, %s) as value
                    """,
                    (
                        f"history-plan-{label}-run-",
                        owner_id,
                        f"history-plan-{label}-conversation-",
                        base,
                        base,
                        row_count,
                    ),
                )
                cursor.execute(
                    """
                    insert into public.strategies (
                        id, user_id, name, name_source, template, asset_class,
                        symbols, parameters, metrics_preferences,
                        benchmark_symbol, pinned, created_at, updated_at
                    )
                    select
                        md5(%s || value::text)::uuid,
                        %s,
                        'History plan strategy ' || value::text,
                        'system_default',
                        'buy_hold',
                        'equity',
                        array['AAPL'],
                        '{}'::jsonb,
                        array['total_return_pct'],
                        'SPY',
                        value <= 8,
                        %s::timestamptz + value * interval '1 millisecond',
                        %s::timestamptz + value * interval '1 millisecond'
                    from generate_series(1, %s) as value
                    """,
                    (
                        f"history-plan-{label}-strategy-",
                        owner_id,
                        base,
                        base,
                        row_count,
                    ),
                )
                cursor.execute(
                    """
                    insert into public.collections (
                        id, user_id, name, name_source, pinned,
                        created_at, updated_at
                    )
                    select
                        md5(%s || value::text)::uuid,
                        %s,
                        'History plan collection ' || value::text,
                        'system_default',
                        value <= 8,
                        %s::timestamptz + value * interval '1 millisecond',
                        %s::timestamptz + value * interval '1 millisecond'
                    from generate_series(1, %s) as value
                    """,
                    (
                        f"history-plan-{label}-collection-",
                        owner_id,
                        base,
                        base,
                        row_count,
                    ),
                )
            # Whole-database analyze: the query touches relations beyond the
            # seeded five, and a fresh cluster has no stats for them.
            cursor.execute("analyze")
    try:
        yield {
            "small_owner_id": small_owner_id,
            "large_owner_id": large_owner_id,
            "base": base,
        }
    finally:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from auth.users where id = any(%s::uuid[])",
                    ([small_owner_id, large_owner_id],),
                )


def _connect():
    return psycopg.connect(DSN, autocommit=True)


def _reader() -> tuple[PostgresHistoryReader, _TrackingPool]:
    pool = _TrackingPool()
    return PostgresHistoryReader(pool), pool


def _walk_plan(plan: dict[str, Any]):
    yield plan
    for child in plan.get("Plans", []):
        yield from _walk_plan(child)


def _physical_rows(node: dict[str, Any]) -> int:
    loops = max(1, int(node.get("Actual Loops", 1)))
    return (
        int(node.get("Actual Rows", 0))
        + int(node.get("Rows Removed by Filter", 0))
        + int(node.get("Rows Removed by Join Filter", 0))
        + int(node.get("Rows Removed by Index Recheck", 0))
    ) * loops


def _insert_conversation(
    cursor: Any,
    *,
    user_id: UUID,
    timestamp: datetime,
    pinned: bool = False,
    archived: bool = False,
    deleted: bool = False,
    with_message: bool = True,
    conversation_id: UUID | None = None,
) -> UUID:
    conversation_id = conversation_id or uuid4()
    cursor.execute(
        """
        insert into public.conversations (
            id, user_id, title, title_source, language, pinned, archived,
            deleted_at, last_message_preview, created_at, updated_at
        )
        values (
            %s, %s, %s, 'ai_generated', 'en', %s, %s, %s, %s, %s, %s
        )
        """,
        (
            conversation_id,
            user_id,
            f"Chat {conversation_id}",
            pinned,
            archived,
            timestamp if deleted else None,
            "A visible message",
            timestamp,
            timestamp,
        ),
    )
    if with_message:
        cursor.execute(
            """
            insert into public.messages (
                id, conversation_id, user_id, role, content, metadata, created_at
            )
            values (%s, %s, %s, 'user', 'Test this idea', '{}'::jsonb, %s)
            """,
            (uuid4(), conversation_id, user_id, timestamp),
        )
    return conversation_id


def _insert_strategy(
    cursor: Any,
    *,
    user_id: UUID,
    timestamp: datetime,
    pinned: bool = False,
    deleted: bool = False,
    strategy_id: UUID | None = None,
) -> UUID:
    strategy_id = strategy_id or uuid4()
    cursor.execute(
        """
        insert into public.strategies (
            id, user_id, name, name_source, template, asset_class, symbols,
            parameters, metrics_preferences, benchmark_symbol, pinned,
            deleted_at, created_at, updated_at
        )
        values (
            %s, %s, %s, 'ai_generated', 'buy_hold', 'equity', array['AAPL'],
            '{}'::jsonb, array['total_return_pct'], 'SPY', %s, %s, %s, %s
        )
        """,
        (
            strategy_id,
            user_id,
            f"Strategy {strategy_id}",
            pinned,
            timestamp if deleted else None,
            timestamp,
            timestamp,
        ),
    )
    return strategy_id


def _insert_collection(
    cursor: Any,
    *,
    user_id: UUID,
    timestamp: datetime,
    pinned: bool = False,
    deleted: bool = False,
    collection_id: UUID | None = None,
) -> UUID:
    collection_id = collection_id or uuid4()
    cursor.execute(
        """
        insert into public.collections (
            id, user_id, name, name_source, pinned, deleted_at, created_at, updated_at
        )
        values (%s, %s, %s, 'ai_generated', %s, %s, %s, %s)
        """,
        (
            collection_id,
            user_id,
            f"Collection {collection_id}",
            pinned,
            timestamp if deleted else None,
            timestamp,
            timestamp,
        ),
    )
    return collection_id


def _insert_run(
    cursor: Any,
    *,
    user_id: UUID,
    timestamp: datetime,
    conversation_id: UUID | None = None,
    status: str = "completed",
    run_id: UUID | None = None,
) -> UUID:
    run_id = run_id or uuid4()
    cursor.execute(
        """
        insert into public.backtest_runs (
            id, user_id, conversation_id, status, asset_class, symbols,
            allocation_method, benchmark_symbol, config_snapshot, metrics,
            conversation_result_card, created_at, updated_at
        )
        values (
            %s, %s, %s, %s, 'equity', array['AAPL'], 'equal_weight', 'SPY',
            '{}'::jsonb, '{}'::jsonb, %s, %s, %s
        )
        """,
        (
            run_id,
            user_id,
            conversation_id,
            status,
            Jsonb(
                {
                    "title": f"Run {run_id}",
                    "rows": [{"value": "10%"}],
                }
            ),
            timestamp,
            timestamp,
        ),
    )
    return run_id


def _flatten(
    rows: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    source_groups = (
        ("run", "runs", "created_at"),
        ("chat", "conversations", "updated_at"),
        ("strategy", "strategies", "updated_at"),
        ("collection", "collections", "updated_at"),
    )
    flattened = [
        (source_type, row)
        for source_type, group, _activity_field in source_groups
        for row in rows[group]
    ]

    def key(item: tuple[str, dict[str, Any]]):
        source_type, row = item
        activity_field = "created_at" if source_type == "run" else "updated_at"
        activity_at = row[activity_field]
        if isinstance(activity_at, str):
            activity_at = datetime.fromisoformat(activity_at)
        return (
            int(bool(row.get("pinned", False))),
            activity_at,
            _RANK[source_type],
            str(row["id"]),
        )

    return sorted(flattened, key=key, reverse=True)


def _read(
    reader: PostgresHistoryReader,
    *,
    owner_id: UUID,
    source_limit: int,
    cursor_item: tuple[str, dict[str, Any]] | None = None,
    archived: bool = False,
    deleted: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    cursor_activity_at = None
    cursor_id = None
    if cursor_item is not None:
        source_type, row = cursor_item
        activity_field = "created_at" if source_type == "run" else "updated_at"
        cursor_activity_at = row[activity_field]
        if isinstance(cursor_activity_at, str):
            cursor_activity_at = datetime.fromisoformat(cursor_activity_at)
        cursor_id = str(row["id"])
    return reader.list_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        limit=source_limit,
        archived=archived,
        deleted=deleted,
        cursor_activity_at=cursor_activity_at,
        cursor_id=cursor_id,
    )


def test_history_each_source_returns_at_most_limit_plus_one(
    history_identities,
) -> None:
    timestamp = datetime(2026, 7, 1, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(6):
            item_at = timestamp - timedelta(minutes=offset)
            conversation_id = _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=item_at,
            )
            _insert_run(
                cursor,
                user_id=owner_id,
                conversation_id=conversation_id,
                timestamp=item_at,
                status=("queued", "running", "completed", "failed")[offset % 4],
            )
            _insert_strategy(cursor, user_id=owner_id, timestamp=item_at)
            _insert_collection(cursor, user_id=owner_id, timestamp=item_at)

    reader, pool = _reader()
    rows = _read(reader, owner_id=owner_id, source_limit=4)

    assert {group: len(group_rows) for group, group_rows in rows.items()} == {
        "runs": 4,
        "conversations": 4,
        "strategies": 4,
        "collections": 4,
    }
    assert {"title_source", "deleted_at", "archived"} <= rows["conversations"][0].keys()
    assert "deleted_at" in rows["strategies"][0]
    assert {"deleted_at", "strategy_count"} <= rows["collections"][0].keys()
    assert pool.tracker == {"query_count": 1, "row_counts": [16]}


def test_history_first_middle_final_and_empty_pages(history_identities) -> None:
    timestamp = datetime(2026, 7, 2, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    inserted: set[str] = set()
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(7):
            inserted.add(
                str(
                    _insert_strategy(
                        cursor,
                        user_id=owner_id,
                        timestamp=timestamp - timedelta(minutes=offset),
                    )
                )
            )

    reader, _ = _reader()
    seen: list[str] = []
    pivot = None
    for expected_count in (3, 3, 1, 0):
        candidates = _flatten(
            _read(
                reader,
                owner_id=owner_id,
                source_limit=4,
                cursor_item=pivot,
            )
        )
        page = candidates[:3]
        assert len(page) == expected_count
        seen.extend(str(row["id"]) for _, row in page)
        pivot = page[-1] if page else pivot

    assert len(seen) == len(set(seen))
    assert set(seen) == inserted


def test_history_equal_timestamps_use_type_rank_then_id(history_identities) -> None:
    timestamp = datetime(2026, 7, 3, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    lower_strategy_id = UUID("10000000-0000-0000-0000-000000000001")
    higher_strategy_id = UUID("f0000000-0000-0000-0000-000000000001")
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
        )
        _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
            strategy_id=lower_strategy_id,
        )
        _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
            strategy_id=higher_strategy_id,
        )
        _insert_collection(cursor, user_id=owner_id, timestamp=timestamp)
        _insert_run(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=timestamp,
        )

    reader, _ = _reader()
    ordered = _flatten(_read(reader, owner_id=owner_id, source_limit=10))

    assert [source_type for source_type, _ in ordered] == [
        "chat",
        "strategy",
        "strategy",
        "collection",
        "run",
    ]
    strategy_ids = [
        str(row["id"]) for source_type, row in ordered if source_type == "strategy"
    ]
    assert strategy_ids == [str(higher_strategy_id), str(lower_strategy_id)]


def test_history_pinned_cursor_executes_split_pin_tiers(history_identities) -> None:
    timestamp = datetime(2026, 7, 3, 12, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    with _connect() as connection, connection.cursor() as cursor:
        pivot_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
            pinned=True,
        )
        collection_id = _insert_collection(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
            pinned=True,
        )
        unpinned_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp + timedelta(minutes=1),
            pinned=False,
        )

    reader, _ = _reader()
    rows = _read(
        reader,
        owner_id=owner_id,
        source_limit=4,
        cursor_item=(
            "strategy",
            {"id": pivot_id, "updated_at": timestamp, "pinned": True},
        ),
    )
    visible_ids = {str(row["id"]) for _, row in _flatten(rows)}

    assert str(collection_id) in visible_ids
    assert str(unpinned_id) in visible_ids
    assert str(pivot_id) not in visible_ids


def test_history_cursor_retains_unpinned_rank_after_pivot_is_pinned(
    history_identities,
) -> None:
    timestamp = datetime(2026, 7, 3, 13, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    with _connect() as connection, connection.cursor() as cursor:
        already_seen_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp + timedelta(minutes=3),
        )
        pivot_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp + timedelta(minutes=2),
        )
        next_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp + timedelta(minutes=1),
        )
        final_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
        )

    reader, _ = _reader()
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            update public.strategies
            set pinned = true, updated_at = %s
            where user_id = %s and id = %s
            """,
            (timestamp + timedelta(days=1), owner_id, pivot_id),
        )

    rows = reader.list_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        limit=3,
        archived=False,
        deleted=False,
        cursor_activity_at=timestamp + timedelta(minutes=2),
        cursor_id=str(pivot_id),
        cursor_pinned=False,
        cursor_type_rank=3,
    )
    visible_ids = [str(row["id"]) for _, row in _flatten(rows)]

    assert visible_ids == [str(next_id), str(final_id)]
    assert str(already_seen_id) not in visible_ids
    assert str(pivot_id) not in visible_ids


def test_history_cursor_retains_pinned_rank_after_pivot_is_unpinned(
    history_identities,
) -> None:
    timestamp = datetime(2026, 7, 3, 14, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    with _connect() as connection, connection.cursor() as cursor:
        _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp + timedelta(minutes=3),
            pinned=True,
        )
        pivot_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp + timedelta(minutes=2),
            pinned=True,
        )
        newer_unpinned_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp + timedelta(minutes=4),
        )
        lower_unpinned_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp + timedelta(minutes=1),
        )

    reader, _ = _reader()
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            update public.strategies
            set pinned = false, updated_at = %s
            where user_id = %s and id = %s
            """,
            (timestamp + timedelta(days=1), owner_id, pivot_id),
        )

    rows = reader.list_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        limit=3,
        archived=False,
        deleted=False,
        cursor_activity_at=timestamp + timedelta(minutes=2),
        cursor_id=str(pivot_id),
        cursor_pinned=True,
        cursor_type_rank=3,
    )
    visible_ids = [str(row["id"]) for _, row in _flatten(rows)]

    assert visible_ids == [str(newer_unpinned_id), str(lower_unpinned_id)]
    assert str(pivot_id) not in visible_ids


def test_history_all_specialized_sql_variants_prepare(history_identities) -> None:
    owner_id = history_identities["owner"]
    timestamp = datetime(2026, 7, 3, 15, tzinfo=timezone.utc)
    executed = 0
    with _connect() as connection, connection.cursor() as cursor:
        for archived in (False, True):
            for deleted in (False, True):
                variants = [(False, False, 0)]
                variants.extend(
                    (True, pivot_pinned, pivot_type_rank)
                    for pivot_pinned in (False, True)
                    for pivot_type_rank in (1, 2, 3, 4)
                )
                for has_cursor, pivot_pinned, pivot_type_rank in variants:
                    cursor.execute(
                        "explain "
                        + _candidate_sql(
                            business=False,
                            archived=archived,
                            deleted=deleted,
                            has_cursor=has_cursor,
                            pivot_pinned=pivot_pinned,
                            pivot_type_rank=pivot_type_rank,
                        ),
                        {
                            "user_id": owner_id,
                            "owner_space_id": None,
                            "cursor_activity_at": (timestamp if has_cursor else None),
                            "cursor_id": uuid4() if has_cursor else None,
                            "source_limit": 4,
                        },
                    )
                    assert cursor.fetchall()
                    executed += 1

    assert executed == 36


def test_history_soft_deleted_pivot_preserves_legacy_cursor_boundary(
    history_identities,
) -> None:
    timestamp = datetime(2026, 7, 4, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    with _connect() as connection, connection.cursor() as cursor:
        pivot_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
        )
        lower_id = _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp - timedelta(minutes=1),
        )

    reader, _ = _reader()
    first = _flatten(_read(reader, owner_id=owner_id, source_limit=2))
    pivot = next(item for item in first if str(item[1]["id"]) == str(pivot_id))
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "update public.strategies set deleted_at = now()"
            " where user_id = %s and id = %s",
            (owner_id, pivot_id),
        )

    second = _flatten(
        _read(
            reader,
            owner_id=owner_id,
            source_limit=2,
            cursor_item=pivot,
        )
    )

    assert [str(row["id"]) for _, row in second] == [str(lower_id)]


def test_history_pages_have_no_skip_or_duplicate_after_deletion(
    history_identities,
) -> None:
    timestamp = datetime(2026, 7, 5, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(6):
            _insert_strategy(
                cursor,
                user_id=owner_id,
                timestamp=timestamp - timedelta(minutes=offset),
            )

    reader, _ = _reader()
    first_candidates = _flatten(_read(reader, owner_id=owner_id, source_limit=3))
    first_page = first_candidates[:2]
    pivot = first_page[-1]
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "update public.strategies set deleted_at = now()"
            " where user_id = %s and id = %s",
            (owner_id, pivot[1]["id"]),
        )
    second_candidates = _flatten(
        _read(
            reader,
            owner_id=owner_id,
            source_limit=3,
            cursor_item=pivot,
        )
    )
    second_page = second_candidates[:2]

    first_ids = {str(row["id"]) for _, row in first_page}
    second_ids = {str(row["id"]) for _, row in second_page}
    assert first_ids.isdisjoint(second_ids)
    assert [str(row["id"]) for _, row in second_page] == [
        str(first_candidates[2][1]["id"]),
        str(
            _flatten(
                _read(
                    reader,
                    owner_id=owner_id,
                    source_limit=6,
                    cursor_item=first_candidates[2],
                )
            )[0][1]["id"]
        ),
    ]


def test_history_chat_requires_message_exists_before_limit(
    history_identities,
) -> None:
    timestamp = datetime(2026, 7, 6, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(5):
            _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=timestamp + timedelta(minutes=offset),
                pinned=True,
                with_message=False,
            )
        visible_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=timestamp - timedelta(minutes=1),
            with_message=True,
        )

    reader, _ = _reader()
    rows = _read(reader, owner_id=owner_id, source_limit=1)

    assert [str(row["id"]) for row in rows["conversations"]] == [str(visible_id)]


def test_history_run_parent_archive_delete_filter_applies_before_limit(
    history_identities,
) -> None:
    timestamp = datetime(2026, 7, 7, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    with _connect() as connection, connection.cursor() as cursor:
        archived_parent = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
            archived=True,
        )
        deleted_parent = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
            deleted=True,
        )
        active_parent = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
        )
        archived_run = _insert_run(
            cursor,
            user_id=owner_id,
            conversation_id=archived_parent,
            timestamp=timestamp + timedelta(minutes=3),
        )
        deleted_run = _insert_run(
            cursor,
            user_id=owner_id,
            conversation_id=deleted_parent,
            timestamp=timestamp + timedelta(minutes=2),
        )
        active_run = _insert_run(
            cursor,
            user_id=owner_id,
            conversation_id=active_parent,
            timestamp=timestamp + timedelta(minutes=1),
        )
        orphan_run = _insert_run(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
        )

    reader, _ = _reader()
    default_rows = _read(reader, owner_id=owner_id, source_limit=2)
    archived_rows = _read(
        reader,
        owner_id=owner_id,
        source_limit=1,
        archived=True,
    )
    deleted_rows = _read(
        reader,
        owner_id=owner_id,
        source_limit=1,
        deleted=True,
    )

    assert [str(row["id"]) for row in default_rows["runs"]] == [
        str(active_run),
        str(orphan_run),
    ]
    assert [str(row["id"]) for row in archived_rows["runs"]] == [str(archived_run)]
    assert [str(row["id"]) for row in deleted_rows["runs"]] == [str(deleted_run)]


def test_history_run_statuses_remain_eligible(history_identities) -> None:
    timestamp = datetime(2026, 7, 8, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    expected: set[str] = set()
    with _connect() as connection, connection.cursor() as cursor:
        for offset, status in enumerate(("queued", "running", "completed", "failed")):
            expected.add(
                str(
                    _insert_run(
                        cursor,
                        user_id=owner_id,
                        timestamp=timestamp - timedelta(minutes=offset),
                        status=status,
                    )
                )
            )

    reader, _ = _reader()
    rows = _read(reader, owner_id=owner_id, source_limit=10)

    assert {str(row["id"]) for row in rows["runs"]} == expected


def test_history_collection_strategy_count_is_exact_after_source_limit(
    history_identities,
) -> None:
    timestamp = datetime(2026, 7, 8, 12, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    with _connect() as connection, connection.cursor() as cursor:
        strategy_ids = [
            _insert_strategy(
                cursor,
                user_id=owner_id,
                timestamp=timestamp,
            )
            for _ in range(2)
        ]
        collection_id = _insert_collection(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
        )
        _insert_collection(
            cursor,
            user_id=owner_id,
            timestamp=timestamp - timedelta(minutes=1),
        )
        for strategy_id in strategy_ids:
            cursor.execute(
                """
                insert into public.collection_strategies (
                    id, collection_id, strategy_id, user_id, created_at
                )
                values (%s, %s, %s, %s, %s)
                """,
                (uuid4(), collection_id, strategy_id, owner_id, timestamp),
            )

    reader, _ = _reader()
    rows = _read(reader, owner_id=owner_id, source_limit=1)

    assert len(rows["collections"]) == 1
    assert str(rows["collections"][0]["id"]) == str(collection_id)
    assert rows["collections"][0]["strategy_count"] == 2


def test_history_owner_scope_is_present_in_every_source(history_identities) -> None:
    timestamp = datetime(2026, 7, 9, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    other_id = history_identities["other"]
    owner_rows: set[str] = set()
    foreign_rows: set[str] = set()
    with _connect() as connection, connection.cursor() as cursor:
        for user_id, target in ((owner_id, owner_rows), (other_id, foreign_rows)):
            conversation_id = _insert_conversation(
                cursor,
                user_id=user_id,
                timestamp=timestamp,
            )
            target.add(str(conversation_id))
            target.add(
                str(
                    _insert_run(
                        cursor,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        timestamp=timestamp,
                    )
                )
            )
            target.add(
                str(
                    _insert_strategy(
                        cursor,
                        user_id=user_id,
                        timestamp=timestamp,
                    )
                )
            )
            target.add(
                str(
                    _insert_collection(
                        cursor,
                        user_id=user_id,
                        timestamp=timestamp,
                    )
                )
            )

    reader, _ = _reader()
    visible = {
        str(row["id"])
        for _, row in _flatten(_read(reader, owner_id=owner_id, source_limit=10))
    }

    assert visible == owner_rows
    assert visible.isdisjoint(foreign_rows)
    foreign_pivot = next(iter(foreign_rows))
    with pytest.raises(HistoryCursorError):
        reader.list_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            limit=2,
            archived=False,
            deleted=False,
            cursor_activity_at=timestamp,
            cursor_id=foreign_pivot,
        )

    ambiguous_id = uuid4()
    with _connect() as connection, connection.cursor() as cursor:
        _insert_strategy(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
            strategy_id=ambiguous_id,
        )
        _insert_collection(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
            collection_id=ambiguous_id,
        )
    with pytest.raises(HistoryCursorError):
        reader.list_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            limit=2,
            archived=False,
            deleted=False,
            cursor_activity_at=timestamp,
            cursor_id=str(ambiguous_id),
        )


@pytest.mark.parametrize("initial_volume,larger_volume", [(40, 400)])
def test_history_query_and_row_budget_are_constant_as_volume_grows(
    history_identities,
    initial_volume: int,
    larger_volume: int,
) -> None:
    timestamp = datetime(2026, 7, 10, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]

    def insert_strategies(start: int, stop: int) -> None:
        with _connect() as connection, connection.cursor() as cursor:
            for offset in range(start, stop):
                _insert_strategy(
                    cursor,
                    user_id=owner_id,
                    timestamp=timestamp - timedelta(seconds=offset),
                )

    insert_strategies(0, initial_volume)
    first_reader, first_pool = _reader()
    first_rows = _read(first_reader, owner_id=owner_id, source_limit=6)
    insert_strategies(initial_volume, larger_volume)
    larger_reader, larger_pool = _reader()
    larger_rows = _read(larger_reader, owner_id=owner_id, source_limit=6)

    assert len(first_rows["strategies"]) == len(larger_rows["strategies"]) == 6
    assert first_pool.tracker == {"query_count": 1, "row_counts": [6]}
    assert larger_pool.tracker == {"query_count": 1, "row_counts": [6]}


def test_history_run_and_chat_plans_are_page_bounded_at_64_and_12k(
    history_plan_scale_rows: dict[str, Any],
) -> None:
    plans: list[dict[str, Any]] = []
    with _connect() as connection, connection.cursor() as cursor:
        # At fixture scale seq-vs-index is a cost coin flip; measure the
        # bounded index path, which is the product claim.
        cursor.execute("set enable_seqscan = off")
        for owner_key, position in (
            ("small_owner_id", 32),
            ("large_owner_id", 8_000),
        ):
            for has_cursor in (False, True):
                cursor.execute(
                    "explain (analyze, buffers, format json) "
                    + _candidate_sql(
                        business=False,
                        archived=False,
                        deleted=False,
                        has_cursor=has_cursor,
                        pivot_pinned=False,
                        pivot_type_rank=3 if has_cursor else 0,
                    ),
                    {
                        "user_id": history_plan_scale_rows[owner_key],
                        "owner_space_id": None,
                        "cursor_activity_at": (
                            history_plan_scale_rows["base"]
                            + timedelta(milliseconds=position)
                            if has_cursor
                            else None
                        ),
                        "cursor_id": (
                            UUID("70000000-0000-0000-0000-" f"{position:012d}")
                            if has_cursor
                            else None
                        ),
                        "source_limit": 21,
                    },
                )
                plans.append(cursor.fetchone()[0][0]["Plan"])

    for plan_index, plan in enumerate(plans):
        assert int(plan["Actual Rows"]) <= 84
        source_scans = [
            node
            for node in _walk_plan(plan)
            if node.get("Relation Name") in {"backtest_runs", "conversations", "messages"}
            and node.get("Node Type")
            in {"Index Scan", "Index Only Scan", "Bitmap Heap Scan", "Seq Scan"}
        ]
        assert source_scans
        assert all(_physical_rows(node) <= 84 for node in source_scans)

        index_names = {
            str(node["Index Name"]) for node in source_scans if node.get("Index Name")
        }
        assert "idx_backtest_runs_user_created" in index_names
        assert "idx_messages_conversation_created" in index_names
        if plan_index >= 2:
            assert "idx_conversations_active_page" in index_names


@pytest.mark.parametrize(
    ("archived", "deleted"),
    (
        (False, False),
        (True, False),
        (False, True),
        (True, True),
    ),
)
@pytest.mark.parametrize("has_cursor", (False, True))
@pytest.mark.parametrize("scale_label", ("small", "large"))
def test_history_state_partition_plans_stay_bounded_as_volume_grows(
    history_plan_scale_rows: dict[str, Any],
    *,
    archived: bool,
    deleted: bool,
    has_cursor: bool,
    scale_label: str,
) -> None:
    owner_id = history_plan_scale_rows[f"{scale_label}_owner_id"]
    source_limit = 21
    with psycopg.connect(DSN) as connection, connection.cursor() as cursor:
        # Measure the bounded index path, not the fixture-scale cost coin flip.
        cursor.execute("set enable_seqscan = off")
        cursor.execute(
            """
            with ranked as (
                select
                    id,
                    (row_number() over (order by updated_at, id) - 1) %% 4 as state
                from public.conversations
                where user_id = %s
            )
            update public.conversations as conversation
            set
                archived = ranked.state in (1, 3),
                deleted_at = case
                    when ranked.state in (2, 3) then conversation.updated_at
                    else null
                end
            from ranked
            where conversation.id = ranked.id
            """,
            (owner_id,),
        )
        for table_name in ("strategies", "collections"):
            cursor.execute(
                f"""
                with ranked as (
                    select
                        id,
                        (row_number() over (order by updated_at, id) - 1) %% 2 as state
                    from public.{table_name}
                    where user_id = %s
                )
                update public.{table_name} as item
                set deleted_at = case
                    when ranked.state = 1 then item.updated_at
                    else null
                end
                from ranked
                where item.id = ranked.id
                """,  # noqa: S608 - finite table names owned by the test
                (owner_id,),
            )
        # Whole-database analyze after the state repartition: the candidate
        # query also touches relations this test never seeds (for example
        # collection_strategies), and a fresh cluster has no statistics for
        # them, which left the asserted plan shapes unstable.
        cursor.execute("analyze")

        cursor.execute(
            "explain (analyze, buffers, format json) "
            + _candidate_sql(
                business=False,
                archived=archived,
                deleted=deleted,
                has_cursor=has_cursor,
                pivot_pinned=False,
                pivot_type_rank=3 if has_cursor else 0,
            ),
            {
                "user_id": owner_id,
                "owner_space_id": None,
                "cursor_activity_at": (
                    history_plan_scale_rows["base"] + timedelta(milliseconds=8_000)
                    if has_cursor
                    else None
                ),
                "cursor_id": (
                    UUID("70000000-0000-0000-0000-000000008000") if has_cursor else None
                ),
                "source_limit": source_limit,
            },
        )
        plan = cursor.fetchone()[0][0]["Plan"]
        connection.rollback()

    source_scans = [
        node
        for node in _walk_plan(plan)
        if node.get("Relation Name")
        in {
            "backtest_runs",
            "conversations",
            "messages",
            "strategies",
            "collections",
        }
        and node.get("Node Type")
        in {"Index Scan", "Index Only Scan", "Bitmap Heap Scan", "Seq Scan"}
    ]
    assert source_scans
    violations = [
        {
            "relation": node.get("Relation Name"),
            "alias": node.get("Alias"),
            "index": node.get("Index Name"),
            "physical_rows": _physical_rows(node),
        }
        for node in source_scans
        if _physical_rows(node) > 5 * source_limit
    ]
    assert not violations, violations
    assert int(plan["Actual Rows"]) <= 4 * source_limit


def test_history_candidate_plan_keeps_a_limit_inside_each_source(
    history_identities,
) -> None:
    timestamp = datetime(2026, 7, 11, tzinfo=timezone.utc)
    owner_id = history_identities["owner"]
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(40):
            item_at = timestamp - timedelta(seconds=offset)
            conversation_id = _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=item_at,
            )
            _insert_run(
                cursor,
                user_id=owner_id,
                conversation_id=conversation_id,
                timestamp=item_at,
            )
            _insert_strategy(cursor, user_id=owner_id, timestamp=item_at)
            _insert_collection(cursor, user_id=owner_id, timestamp=item_at)

        cursor.execute(
            "explain (analyze, buffers, format json) "
            + _candidate_sql(
                business=False,
                archived=False,
                deleted=False,
                has_cursor=False,
                pivot_pinned=False,
                pivot_type_rank=0,
            ),
            {
                "user_id": owner_id,
                "owner_space_id": None,
                "cursor_activity_at": None,
                "cursor_id": None,
                "source_limit": 6,
            },
        )
        explained = cursor.fetchone()[0][0]

    plan = explained["Plan"]
    nodes = list(_walk_plan(plan))
    limits = [node for node in nodes if node["Node Type"] == "Limit"]

    assert len(limits) >= 4
    assert all(node["Actual Rows"] <= 6 for node in limits)
    assert plan["Actual Rows"] <= 24
    assert explained["Execution Time"] < 2_000
