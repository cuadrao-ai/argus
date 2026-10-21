"""Real-Postgres plan proofs for persistent Conversation and Message pages."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import md5
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from argus.domain.owner_scope import PERSONAL

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)


class _ExplainCursor:
    def __init__(self, cursor: Any, plans: list[dict[str, Any]]) -> None:
        self._cursor = cursor
        self._plans = plans
        self._is_candidate = False

    def __enter__(self) -> _ExplainCursor:
        self._cursor.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._cursor.__exit__(*args)

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self._is_candidate = "order by" in query.lower()
        if self._is_candidate:
            self._cursor.execute(
                "explain (analyze, buffers, format json) " + query,
                params,
            )
        else:
            self._cursor.execute(query, params)

    def fetchall(self) -> list[dict[str, Any]]:
        rows = self._cursor.fetchall()
        if not self._is_candidate:
            return rows
        payload = (
            next(iter(rows[0].values())) if isinstance(rows[0], dict) else rows[0][0]
        )
        self._plans.append(payload[0]["Plan"])
        return []


class _ExplainConnection:
    def __init__(self, connection: Any, plans: list[dict[str, Any]]) -> None:
        self._connection = connection
        self._plans = plans

    def cursor(self, **kwargs: Any) -> _ExplainCursor:
        return _ExplainCursor(self._connection.cursor(**kwargs), self._plans)


class _ExplainPool:
    def __init__(self) -> None:
        self.plans: list[dict[str, Any]] = []

    @contextmanager
    def connection(self, *, timeout: float):
        assert timeout == 2.0
        with psycopg.connect(DSN, autocommit=True) as connection:
            yield _ExplainConnection(connection, self.plans)


class _DirectPool:
    @contextmanager
    def connection(self, *, timeout: float):
        assert timeout == 2.0
        with psycopg.connect(DSN, autocommit=True) as connection:
            yield connection


def _walk_plan(node: dict[str, Any]):
    yield node
    for child in node.get("Plans", []):
        yield from _walk_plan(child)


def _scan_rows(plan: dict[str, Any]) -> int:
    return max(
        (
            int(node.get("Actual Rows", 0))
            + int(node.get("Rows Removed by Filter", 0))
            + int(node.get("Rows Removed by Index Recheck", 0))
            for node in _walk_plan(plan)
            if node.get("Node Type")
            in {
                "Index Scan",
                "Index Only Scan",
                "Bitmap Heap Scan",
                "Seq Scan",
            }
        ),
        default=0,
    )


def _buffer_blocks(plan: dict[str, Any]) -> int:
    return max(
        (
            sum(
                int(node.get(name, 0))
                for name in (
                    "Shared Hit Blocks",
                    "Shared Read Blocks",
                    "Shared Dirtied Blocks",
                    "Shared Written Blocks",
                )
            )
            for node in _walk_plan(plan)
        ),
        default=0,
    )


def _index_names(plan: dict[str, Any]) -> set[str]:
    return {
        str(node["Index Name"]) for node in _walk_plan(plan) if node.get("Index Name")
    }


@pytest.fixture(scope="module")
def keyset_scale_rows():
    owner_id = uuid4()
    other_id = uuid4()
    small_owner_id = uuid4()
    message_conversation_id = uuid4()
    small_message_conversation_id = uuid4()
    base = datetime(2026, 7, 27, tzinfo=timezone.utc)
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            for user_id, label in (
                (owner_id, "large"),
                (other_id, "other"),
                (small_owner_id, "small"),
            ):
                email = f"keyset-{label}-{user_id}@argus.local"
                cursor.execute(
                    "insert into auth.users (id,email,is_anonymous)"
                    " values (%s,%s,false)",
                    (user_id, email),
                )
                cursor.execute(
                    "insert into public.profiles (id,email) values (%s,%s)",
                    (user_id, email),
                )
            cursor.execute(
                """
                insert into public.conversations (
                    id,user_id,title,title_source,language,pinned,archived,
                    created_at,updated_at
                )
                select
                    md5('keyset-large-conversation-' || value::text)::uuid,
                    %s,
                    'Large conversation ' || value::text,
                    'system_default',
                    'en',
                    false,
                    false,
                    %s::timestamptz - value * interval '1 second',
                    %s::timestamptz - value * interval '1 second'
                from generate_series(1,12000) as value
                """,
                (owner_id, base, base),
            )
            cursor.execute(
                """
                insert into public.conversations (
                    id,user_id,title,title_source,language,pinned,archived,
                    created_at,updated_at
                )
                select
                    md5('keyset-small-conversation-' || value::text)::uuid,
                    %s,
                    'Small conversation ' || value::text,
                    'system_default',
                    'en',
                    false,
                    false,
                    %s::timestamptz - value * interval '1 second',
                    %s::timestamptz - value * interval '1 second'
                from generate_series(1,64) as value
                """,
                (small_owner_id, base, base),
            )
            cursor.execute(
                """
                insert into public.conversations (
                    id,user_id,title,title_source,language,pinned,archived,
                    created_at,updated_at
                )
                values
                    (%s,%s,'Large messages','system_default','en',false,false,%s,%s),
                    (%s,%s,'Small messages','system_default','en',false,false,%s,%s)
                """,
                (
                    message_conversation_id,
                    owner_id,
                    base,
                    base,
                    small_message_conversation_id,
                    small_owner_id,
                    base,
                    base,
                ),
            )
            cursor.execute(
                """
                insert into public.messages (
                    id,conversation_id,user_id,role,content,metadata,created_at
                )
                select
                    md5('keyset-large-message-' || value::text)::uuid,
                    %s,
                    %s,
                    'user',
                    'Large message ' || value::text,
                    '{}'::jsonb,
                    %s::timestamptz + value * interval '1 second'
                from generate_series(1,12000) as value
                """,
                (message_conversation_id, owner_id, base),
            )
            cursor.execute(
                """
                insert into public.messages (
                    id,conversation_id,user_id,role,content,metadata,created_at
                )
                select
                    md5('keyset-small-message-' || value::text)::uuid,
                    %s,
                    %s,
                    'user',
                    'Small message ' || value::text,
                    '{}'::jsonb,
                    %s::timestamptz + value * interval '1 second'
                from generate_series(1,64) as value
                """,
                (small_message_conversation_id, small_owner_id, base),
            )
            cursor.execute("analyze public.conversations")
            cursor.execute("analyze public.messages")
    try:
        yield {
            "owner_id": owner_id,
            "small_owner_id": small_owner_id,
            "message_conversation_id": message_conversation_id,
            "small_message_conversation_id": small_message_conversation_id,
            "base": base,
        }
    finally:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from auth.users where id = any(%s::uuid[])",
                    ([owner_id, other_id, small_owner_id],),
                )


def test_conversation_deep_page_uses_tuple_index_condition_at_64_and_12k(
    keyset_scale_rows: dict[str, Any],
) -> None:
    from argus.domain.postgres_keyset_reader import PostgresKeysetReader

    plans: list[dict[str, Any]] = []
    for owner_key, prefix, position in (
        ("small_owner_id", "keyset-small-conversation-", 32),
        ("owner_id", "keyset-large-conversation-", 8000),
    ):
        pool = _ExplainPool()
        PostgresKeysetReader(pool).list_conversation_rows(
            scope=PERSONAL,
            user_id=str(keyset_scale_rows[owner_key]),
            limit=20,
            archived=None,
            deleted=False,
            cursor_updated_at=keyset_scale_rows["base"] - timedelta(seconds=position),
            cursor_id=str(
                UUID(
                    bytes=bytes.fromhex(
                        md5(
                            f"{prefix}{position}".encode(),
                            usedforsecurity=False,
                        ).hexdigest()
                    )
                )
            ),
        )
        plans.append(pool.plans[-1])

    for plan in plans:
        assert "idx_conversations_active_page" in _index_names(plan)
        assert _scan_rows(plan) <= 84
        assert int(plan["Actual Rows"]) <= 21
    assert _buffer_blocks(plans[1]) <= _buffer_blocks(plans[0]) + 12


def test_deleted_conversation_deep_page_is_page_bounded_at_12k(
    keyset_scale_rows: dict[str, Any],
) -> None:
    from argus.domain.postgres_keyset_reader import _conversation_page_sql

    owner_id = keyset_scale_rows["owner_id"]
    with psycopg.connect(DSN) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            update public.conversations
            set deleted_at = updated_at
            where user_id = %s
            """,
            (owner_id,),
        )
        cursor.execute("analyze public.conversations")
        cursor.execute(
            """
            select pinned, updated_at, id
            from public.conversations
            where user_id = %s
              and deleted_at is not null
            order by pinned desc, updated_at desc, id desc
            offset 8000
            limit 1
            """,
            (owner_id,),
        )
        pivot_pinned, pivot_updated_at, pivot_id = cursor.fetchone()
        cursor.execute(
            "explain (analyze, buffers, format json) "
            + _conversation_page_sql(
                scope_condition="owner_space_id is null",
                archived=None,
                deleted=True,
                has_cursor=True,
            ),
            (
                owner_id,
                pivot_pinned,
                pivot_updated_at,
                pivot_id,
                21,
            ),
        )
        plan = cursor.fetchone()[0][0]["Plan"]
        connection.rollback()

    assert _scan_rows(plan) <= 84
    assert int(plan["Actual Rows"]) <= 21


def test_message_deep_page_uses_tuple_index_condition_at_64_and_12k(
    keyset_scale_rows: dict[str, Any],
) -> None:
    from argus.domain.postgres_keyset_reader import PostgresKeysetReader

    plans: list[dict[str, Any]] = []
    for owner_key, conversation_key, prefix, position in (
        (
            "small_owner_id",
            "small_message_conversation_id",
            "keyset-small-message-",
            32,
        ),
        (
            "owner_id",
            "message_conversation_id",
            "keyset-large-message-",
            8000,
        ),
    ):
        pool = _ExplainPool()
        PostgresKeysetReader(pool).list_message_rows(
            user_id=str(keyset_scale_rows[owner_key]),
            conversation_id=str(keyset_scale_rows[conversation_key]),
            limit=20,
            cursor_created_at=keyset_scale_rows["base"] + timedelta(seconds=position),
            cursor_id=str(
                UUID(
                    bytes=bytes.fromhex(
                        md5(
                            f"{prefix}{position}".encode(),
                            usedforsecurity=False,
                        ).hexdigest()
                    )
                )
            ),
        )
        plans.append(pool.plans[-1])

    for plan in plans:
        assert "idx_messages_conversation_created" in _index_names(plan)
        assert _scan_rows(plan) <= 84
        assert int(plan["Actual Rows"]) <= 21
    assert _buffer_blocks(plans[1]) <= _buffer_blocks(plans[0]) + 12


def test_keyset_reader_preserves_filters_deletion_stability_and_owner_scope() -> None:
    from argus.domain.postgres_keyset_reader import (
        ConversationKeysetCursorError,
        PostgresKeysetReader,
    )

    owner_id = uuid4()
    other_id = uuid4()
    conversation_id = UUID("40000000-0000-0000-0000-000000000001")
    other_conversation_id = UUID("40000000-0000-0000-0000-000000000002")
    timestamp = datetime(2026, 7, 27, tzinfo=timezone.utc)
    conversation_ids = [
        UUID(f"50000000-0000-0000-0000-{value:012d}") for value in range(1, 9)
    ]
    message_ids = [UUID(f"60000000-0000-0000-0000-{value:012d}") for value in range(1, 8)]
    reader = PostgresKeysetReader(_DirectPool())

    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            for user_id, label in ((owner_id, "owner"), (other_id, "other")):
                email = f"keyset-contract-{label}-{user_id}@argus.local"
                cursor.execute(
                    "insert into auth.users (id,email,is_anonymous)"
                    " values (%s,%s,false)",
                    (user_id, email),
                )
                cursor.execute(
                    "insert into public.profiles (id,email) values (%s,%s)",
                    (user_id, email),
                )
            cursor.executemany(
                """
                insert into public.conversations (
                    id,user_id,title,title_source,language,pinned,archived,
                    deleted_at,created_at,updated_at
                )
                values (%s,%s,%s,'system_default','en',%s,%s,%s,%s,%s)
                """,
                [
                    (
                        conversation_id_value,
                        owner_id,
                        f"Conversation {position}",
                        position <= 3,
                        position == 7,
                        timestamp if position == 8 else None,
                        timestamp,
                        timestamp,
                    )
                    for position, conversation_id_value in enumerate(
                        conversation_ids,
                        start=1,
                    )
                ],
            )
            cursor.execute(
                """
                insert into public.conversations (
                    id,user_id,title,title_source,language,pinned,archived,
                    created_at,updated_at
                )
                values
                    (%s,%s,'Message owner','system_default','en',false,false,%s,%s),
                    (%s,%s,'Foreign messages','system_default','en',false,false,%s,%s)
                """,
                (
                    conversation_id,
                    owner_id,
                    timestamp,
                    timestamp,
                    other_conversation_id,
                    other_id,
                    timestamp,
                    timestamp,
                ),
            )
            cursor.executemany(
                """
                insert into public.messages (
                    id,conversation_id,user_id,role,content,metadata,created_at
                )
                values (%s,%s,%s,%s,%s,'{}'::jsonb,%s)
                """,
                [
                    (
                        message_ids[0],
                        conversation_id,
                        owner_id,
                        "user",
                        "First visible",
                        timestamp,
                    ),
                    (
                        message_ids[1],
                        conversation_id,
                        owner_id,
                        "user",
                        "__ONBOARDING_SKIP__",
                        timestamp,
                    ),
                    (
                        message_ids[2],
                        conversation_id,
                        owner_id,
                        "assistant",
                        "__ONBOARDING_SKIP__",
                        timestamp,
                    ),
                    (
                        message_ids[3],
                        conversation_id,
                        owner_id,
                        "user",
                        "__ONBOARDING_GOAL__:test",
                        timestamp,
                    ),
                    (
                        message_ids[4],
                        conversation_id,
                        owner_id,
                        "user",
                        "Second visible",
                        timestamp,
                    ),
                    (
                        message_ids[5],
                        conversation_id,
                        owner_id,
                        "assistant",
                        "Third visible",
                        timestamp,
                    ),
                    (
                        message_ids[6],
                        other_conversation_id,
                        other_id,
                        "user",
                        "Foreign",
                        timestamp,
                    ),
                ],
            )

    try:
        first = reader.list_conversation_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            limit=2,
            archived=False,
            deleted=False,
        )
        assert [row["id"] for row in first] == [
            str(conversation_ids[2]),
            str(conversation_ids[1]),
            str(conversation_ids[0]),
        ]
        pivot_id = first[1]["id"]
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update public.conversations
                    set deleted_at = %s, updated_at = %s + interval '1 day'
                    where user_id = %s and id = %s
                    """,
                    (timestamp, timestamp, owner_id, pivot_id),
                )

        middle = reader.list_conversation_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            limit=2,
            archived=False,
            deleted=False,
            cursor_updated_at=timestamp,
            cursor_id=pivot_id,
        )
        assert [row["id"] for row in middle] == [
            str(conversation_ids[0]),
            str(conversation_ids[5]),
            str(conversation_ids[4]),
        ]
        assert not {row["id"] for row in first[:2]} & {row["id"] for row in middle[:2]}
        assert [
            row["id"]
            for row in reader.list_conversation_rows(
                scope=PERSONAL,
                user_id=str(owner_id),
                limit=20,
                archived=True,
                deleted=False,
            )
        ] == [str(conversation_ids[6])]
        assert {
            row["id"]
            for row in reader.list_conversation_rows(
                scope=PERSONAL,
                user_id=str(owner_id),
                limit=20,
                archived=None,
                deleted=True,
            )
        } == {str(conversation_ids[1]), str(conversation_ids[7])}
        with pytest.raises(ConversationKeysetCursorError):
            reader.list_conversation_rows(
                scope=PERSONAL,
                user_id=str(owner_id),
                limit=2,
                archived=False,
                deleted=False,
                cursor_updated_at=timestamp,
                cursor_id=str(other_conversation_id),
            )
        with pytest.raises(ConversationKeysetCursorError):
            reader.list_conversation_rows(
                scope=PERSONAL,
                user_id=str(owner_id),
                limit=2,
                archived=False,
                deleted=False,
                cursor_updated_at=timestamp,
                cursor_id=str(uuid4()),
            )

        first_messages = reader.list_message_rows(
            user_id=str(owner_id),
            conversation_id=str(conversation_id),
            limit=2,
        )
        assert [row["id"] for row in first_messages] == [
            str(message_ids[0]),
            str(message_ids[2]),
            str(message_ids[4]),
        ]
        deleted_message_pivot = first_messages[1]["id"]
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from public.messages"
                    " where user_id = %s and conversation_id = %s and id = %s",
                    (owner_id, conversation_id, deleted_message_pivot),
                )
        final_messages = reader.list_message_rows(
            user_id=str(owner_id),
            conversation_id=str(conversation_id),
            limit=2,
            cursor_created_at=timestamp,
            cursor_id=deleted_message_pivot,
        )
        assert [row["id"] for row in final_messages] == [
            str(message_ids[4]),
            str(message_ids[5]),
        ]
        assert (
            reader.list_message_rows(
                user_id=str(owner_id),
                conversation_id=str(conversation_id),
                limit=2,
                cursor_created_at=timestamp,
                cursor_id=str(message_ids[5]),
            )
            == []
        )
        # Freshness uses the last saved message, including an ordinary reply
        # with no lifecycle/job row. It shares the message-page ordering.
        latest = reader.read_conversation_preview_messages(
            user_id=str(owner_id), conversation_ids=[str(conversation_id)]
        )
        assert latest[0]["id"] == str(message_ids[5])
        reply_id = uuid4()
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.messages"
                    " (id, user_id, conversation_id, role, content, created_at)"
                    " values (%s, %s, %s, 'assistant', 'Saved reply', %s)",
                    (
                        reply_id,
                        owner_id,
                        conversation_id,
                        timestamp + timedelta(seconds=1),
                    ),
                )
        latest = reader.read_conversation_preview_messages(
            user_id=str(owner_id), conversation_ids=[str(conversation_id)]
        )
        assert latest[0]["id"] == str(reply_id)
        assert (
            reader.read_conversation_preview_messages(
                user_id=str(other_id), conversation_ids=[str(conversation_id)]
            )
            == []
        )
    finally:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from auth.users where id = any(%s::uuid[])",
                    ([owner_id, other_id],),
                )
