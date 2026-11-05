"""Disposable-Postgres proofs for conversation-shaped Omnisearch reads."""

from __future__ import annotations

import os
import random
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from argus.api.search_assembly import scored_supabase_search_items
from argus.api.search_utils import search_rank_key
from argus.domain.owner_scope import PERSONAL
from argus.domain.search_text import normalize_search_text
from psycopg import sql
from psycopg.types.json import Jsonb

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)


def _search_components():
    try:
        from argus.domain.postgres_search_reader import (
            PostgresSearchReader,
            SearchCursorError,
        )
        from argus.domain.search_sql_text import normalizer_expression
    except ModuleNotFoundError:
        pytest.fail("bounded Postgres Search reader is not implemented")
    return PostgresSearchReader, SearchCursorError, normalizer_expression


class _TrackingCursor:
    def __init__(self, cursor: Any, tracker: dict[str, Any]) -> None:
        self._cursor = cursor
        self._tracker = tracker

    def __enter__(self) -> _TrackingCursor:
        self._cursor.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._cursor.__exit__(*args)

    def execute(self, query: Any, params: Any = None) -> None:
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
def search_identities():
    owner_id = uuid4()
    other_id = uuid4()
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            for user_id, label in ((owner_id, "owner"), (other_id, "other")):
                email = f"search-{label}-{user_id}@argus.local"
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


def _connect():
    return psycopg.connect(DSN, autocommit=True)


def _reader():
    reader_type, _, _ = _search_components()
    pool = _TrackingPool()
    return reader_type(pool), pool


def _insert_conversation(
    cursor: Any,
    *,
    user_id: UUID,
    timestamp: datetime,
    title: str,
    preview: str = "",
    pinned: bool = False,
    archived: bool = False,
    deleted: bool = False,
    conversation_id: UUID | None = None,
) -> UUID:
    conversation_id = conversation_id or uuid4()
    cursor.execute(
        """
        insert into public.conversations (
            id, user_id, title, title_source, language, pinned, archived,
            last_message_preview, deleted_at, created_at, updated_at
        )
        values (%s, %s, %s, 'ai_generated', 'en', %s, %s, %s, %s, %s, %s)
        """,
        (
            conversation_id,
            user_id,
            title,
            pinned,
            archived,
            preview,
            timestamp if deleted else None,
            timestamp,
            timestamp,
        ),
    )
    return conversation_id


def _insert_run(
    cursor: Any,
    *,
    user_id: UUID,
    timestamp: datetime,
    title: str,
    conversation_id: UUID,
    symbols: list[str] | None = None,
    status: str = "completed",
    run_id: UUID | None = None,
    template: str = "buy_and_hold",
    start_date: str = "2025-01-01",
    end_date: str = "2025-12-31",
) -> UUID:
    run_id = run_id or uuid4()
    run_symbols = symbols or ["AAPL"]
    cursor.execute(
        """
        insert into public.backtest_runs (
            id, user_id, conversation_id, status, asset_class, symbols,
            allocation_method, benchmark_symbol, config_snapshot, metrics,
            conversation_result_card, created_at, updated_at
        )
        values (
            %s, %s, %s, %s, 'equity', %s, 'equal_weight', 'SPY',
            %s, '{}'::jsonb, %s, %s, %s
        )
        """,
        (
            run_id,
            user_id,
            conversation_id,
            status,
            run_symbols,
            Jsonb(
                {
                    "template": template,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            ),
            Jsonb({"title": title, "symbols": run_symbols}),
            timestamp,
            timestamp,
        ),
    )
    return run_id


def _insert_message(
    cursor: Any,
    *,
    user_id: UUID,
    conversation_id: UUID,
    timestamp: datetime,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> UUID:
    message_id = uuid4()
    cursor.execute(
        """
        insert into public.messages (
            id, user_id, conversation_id, role, content, metadata, created_at
        )
        values (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            message_id,
            user_id,
            conversation_id,
            role,
            content,
            Jsonb(metadata or {}),
            timestamp,
        ),
    )
    return message_id


def _insert_idea_spine(
    cursor: Any,
    *,
    user_id: UUID,
    timestamp: datetime,
    title: str,
    summary: str,
    conversation_id: UUID,
    decision_state: str = "promising",
    decision_note: str | None = None,
    source_run_id: UUID | None = None,
    evidence_digest: str | None = None,
) -> dict[str, UUID]:
    idea_id = uuid4()
    version_id = uuid4()
    evidence_id = uuid4()
    decision_id = uuid4()
    cursor.execute(
        """
        insert into public.ideas (
            id, user_id, source_conversation_id, title, summary, lifecycle,
            created_at, updated_at
        )
        values (%s, %s, %s, %s, %s, 'decided', %s, %s)
        """,
        (idea_id, user_id, conversation_id, title, summary, timestamp, timestamp),
    )
    cursor.execute(
        """
        insert into public.idea_versions (
            id, user_id, idea_id, source_conversation_id, version_number,
            canonical_spec, strategy_snapshot, title, summary, lifecycle,
            created_at
        )
        values (
            %s, %s, %s, %s, 1, '{}'::jsonb, '{}'::jsonb, %s, %s,
            'decided', %s
        )
        """,
        (
            version_id,
            user_id,
            idea_id,
            conversation_id,
            title,
            summary,
            timestamp,
        ),
    )
    cursor.execute(
        "update public.ideas set active_version_id = %s where id = %s",
        (version_id, idea_id),
    )
    cursor.execute(
        """
        insert into public.evidence_artifacts (
            id, user_id, idea_id, idea_version_id, source_conversation_id,
            source_run_id, artifact_type, lifecycle, title, digest, payload,
            created_at, updated_at
        )
        values (
            %s, %s, %s, %s, %s, %s, 'backtest', 'decided', %s, %s,
            %s, %s, %s
        )
        """,
        (
            evidence_id,
            user_id,
            idea_id,
            version_id,
            conversation_id,
            source_run_id,
            f"{title} evidence",
            evidence_digest or f"{summary} evidence",
            Jsonb(
                {
                    "quick_take": evidence_digest or summary,
                    "provenance": {
                        "symbols": ["AAPL"],
                        "benchmark_symbol": "SPY",
                    },
                }
            ),
            timestamp,
            timestamp,
        ),
    )
    cursor.execute(
        """
        insert into public.decision_notes (
            id, user_id, idea_id, idea_version_id, evidence_artifact_id,
            source_conversation_id, decision_state, note, created_at, updated_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            decision_id,
            user_id,
            idea_id,
            version_id,
            evidence_id,
            conversation_id,
            decision_state,
            decision_note or f"{summary} decision",
            timestamp,
            timestamp,
        ),
    )
    return {
        "idea": idea_id,
        "version": version_id,
        "evidence": evidence_id,
        "decision": decision_id,
    }


def _ranked(raw: dict[str, list[dict[str, Any]]], query: str):
    scored = scored_supabase_search_items(raw=raw, query=query)
    return sorted(
        scored,
        key=lambda pair: search_rank_key(
            score=pair[0],
            kind=pair[1].type,
            updated_at=pair[1].updated_at,
            item_id=pair[1].id,
        ),
        reverse=True,
    )


def _random_text(randomizer: random.Random, length: int) -> str:
    characters: list[str] = []
    while len(characters) < length:
        codepoint = randomizer.randrange(1, sys.maxunicode + 1)
        if 0xD800 <= codepoint <= 0xDFFF:
            continue
        characters.append(chr(codepoint))
    return "".join(characters)


def test_sql_normalizer_matches_python_for_unicode_and_random_text() -> None:
    _, _, normalizer_expression = _search_components()
    randomizer = random.Random(232)
    values = [
        chr(codepoint)
        for codepoint in range(1, sys.maxunicode + 1)
        if not 0xD800 <= codepoint <= 0xDFFF
    ]
    values.extend(
        _random_text(randomizer, randomizer.randrange(1, 16)) for _ in range(2_000)
    )
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "create temporary table search_normalizer_probe "
            "(source_text text not null, expected text not null)"
        )
        with cursor.copy(
            "copy search_normalizer_probe (source_text, expected) from stdin"
        ) as copy:
            for value in values:
                copy.write_row((value, normalize_search_text(value)))
        cursor.execute(
            sql.SQL(
                "select count(*) from search_normalizer_probe where {} <> expected"
            ).format(normalizer_expression(sql.Identifier("source_text")))
        )
        assert cursor.fetchone()[0] == 0


def test_symbol_sql_normalizer_matches_raw_python_casefold_for_every_scalar() -> None:
    from argus.domain.search_sql_text import symbol_normalizer_expression

    values = [
        chr(codepoint)
        for codepoint in range(1, sys.maxunicode + 1)
        if not 0xD800 <= codepoint <= 0xDFFF
    ]
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "create temporary table symbol_normalizer_probe "
            "(source_text text not null, expected text not null)"
        )
        with cursor.copy(
            "copy symbol_normalizer_probe (source_text, expected) from stdin"
        ) as copy:
            for value in values:
                copy.write_row((value, value.casefold()))
        cursor.execute(
            sql.SQL(
                "select count(*) from symbol_normalizer_probe where {} <> expected"
            ).format(symbol_normalizer_expression(sql.Identifier("source_text")))
        )
        assert cursor.fetchone()[0] == 0


def test_search_groups_all_matching_layers_into_one_conversation(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 12, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Needle conversation",
            preview="Needle preview",
        )
        _insert_run(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Needle run",
            conversation_id=conversation_id,
        )
        _insert_idea_spine(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Needle idea",
            summary="Needle evidence",
            conversation_id=conversation_id,
        )
        first_message_id = _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now + timedelta(minutes=1),
            role="user",
            content="Needle in the first user turn.",
        )
        second_message_id = _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now + timedelta(minutes=2),
            role="user",
            content="Needle in the second user turn.",
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now + timedelta(minutes=3),
            role="assistant",
            content="Needle assistant copy must not count.",
        )

    reader, pool = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=4,
    )
    ranked = _ranked(result.rows, "needle")

    assert [item.id for _, item in ranked] == [str(conversation_id)]
    assert ranked[0][1].conversation_id == str(conversation_id)
    assert ranked[0][1].match.layer == "decision"
    assert ranked[0][1].match.message_id is None
    assert ranked[0][1].match.count >= 1
    assert first_message_id != second_message_id
    assert result.rows["strategies"] == []
    assert result.rows["collections"] == []
    assert pool.tracker == {"query_count": 2, "row_counts": [1, 1]}


def test_search_recalls_latest_user_message_with_count_and_archive_visibility(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 12, 5, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Archived ordinary notes",
            archived=True,
        )
        first = _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now + timedelta(minutes=1),
            role="user",
            content="My copper lantern threshold was conservative.",
        )
        latest = _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now + timedelta(minutes=2),
            role="user",
            content="I revised the copper lantern threshold.",
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now + timedelta(minutes=3),
            role="assistant",
            content="Assistant copper lantern threshold.",
        )

    reader, pool = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="copper lantern",
        source_limit=4,
    )
    ranked = _ranked(result.rows, "copper lantern")

    assert [item.id for _, item in ranked] == [str(conversation_id)]
    item = ranked[0][1]
    assert item.match.layer == "message"
    assert item.match.fragment == "I revised the copper lantern threshold."
    assert item.match.count == 2
    assert item.match.message_id == str(latest)
    assert item.match.message_id != str(first)
    assert pool.tracker == {"query_count": 2, "row_counts": [1, 1]}


def test_visible_id_recall_is_one_owner_scoped_hydration(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    other_id = search_identities["other"]
    now = datetime(2026, 7, 27, 12, 10, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        archived_target = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=30),
            title="Visible History target",
            archived=True,
        )
        deleted_target = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Deleted target",
            deleted=True,
        )
        foreign_target = _insert_conversation(
            cursor,
            user_id=other_id,
            timestamp=now,
            title="Foreign target",
        )

    reader, pool = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="",
        source_limit=3,
        conversation_ids=[
            str(archived_target),
            str(deleted_target),
            str(foreign_target),
        ],
    )

    assert [row["id"] for row in result.rows["conversations"]] == [str(archived_target)]
    assert pool.tracker == {"query_count": 1, "row_counts": [1]}


def test_search_projects_the_latest_run_result_message_anchor(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 12, 7, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="GLD suggestion history",
        )
        run_id = _insert_run(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now,
            title="GLD result",
            symbols=["GLD"],
        )
        _insert_idea_spine(
            cursor,
            user_id=owner_id,
            timestamp=now + timedelta(minutes=1),
            title="GLD idea",
            summary="GLD decision",
            conversation_id=conversation_id,
            source_run_id=run_id,
        )
        result_message_id = _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now + timedelta(minutes=2),
            role="assistant",
            content="GLD result.",
            metadata={
                "result_run_id": str(run_id),
                "result_card": {"title": "GLD result"},
            },
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now + timedelta(minutes=3),
            role="assistant",
            content="Here are supported next experiments.",
            metadata={
                "latest_run_id": str(run_id),
                "next_experiments": {
                    "version": "argus_next_experiments/v1",
                    "rows": [
                        {
                            "kind": "change_date_range",
                            "label": "Test a different date range",
                        }
                    ],
                },
            },
        )

    reader, _ = _reader()
    offered = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="GLD",
        source_limit=4,
    )
    [(_, offered_item)] = _ranked(offered.rows, "GLD")
    assert offered_item.dossier is not None
    assert offered_item.dossier.result_message_id == str(result_message_id)

    with _connect() as connection, connection.cursor() as cursor:
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now + timedelta(minutes=4),
            role="user",
            content="I will take a different path.",
        )

    followed_up = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="GLD",
        source_limit=4,
    )
    [(_, followed_up_item)] = _ranked(followed_up.rows, "GLD")
    assert followed_up_item.dossier is not None
    assert followed_up_item.dossier.result_message_id == str(result_message_id)


def test_search_centers_fragment_on_late_user_message_match(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 12, 10, tzinfo=timezone.utc)
    content = (
        ("Earlier copper-only context. " * 30)
        + "My copper lantern threshold was twelve percent."
        + (" Later unrelated context." * 20)
    )
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Ordinary allocation notes",
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now,
            role="user",
            content=content,
        )

    reader, _ = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="copper threshold",
        source_limit=4,
    )
    [(_, item)] = _ranked(result.rows, "copper threshold")

    assert item.id == str(conversation_id)
    assert item.match.layer == "message"
    assert len(item.match.fragment) <= 500
    assert item.match.fragment in content
    assert "copper lantern threshold" in item.match.fragment
    assert item.match.fragment != content[:500]
    assert item.matched_text == item.match.fragment


def test_search_title_match_returns_title_with_unrelated_preview(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 12, 15, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Needle conversation",
            preview="Review again later",
        )

    reader, pool = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=4,
    )
    ranked = _ranked(result.rows, "needle")

    assert [item.id for _, item in ranked] == [str(conversation_id)]
    assert ranked[0][1].matched_text == "Needle conversation"
    assert pool.tracker == {"query_count": 2, "row_counts": [1, 1]}


def test_search_preview_match_returns_preview_with_unrelated_title(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 12, 30, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Review again later",
            preview="Needle preview",
        )

    reader, pool = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=4,
    )
    ranked = _ranked(result.rows, "needle")

    assert [item.id for _, item in ranked] == [str(conversation_id)]
    assert ranked[0][1].matched_text == "Needle preview"
    assert pool.tracker == {"query_count": 2, "row_counts": [1, 1]}


@pytest.mark.parametrize(
    ("decision_note", "evidence_digest", "query"),
    [
        ("localtoken", "evidencetoken", "localtoken evidencetoken"),
        ("decisionlongtoken", "localtoken", "decisionlongtoken localtoken"),
    ],
)
def test_search_matches_all_tokens_across_decision_and_evidence_text(
    search_identities,
    decision_note: str,
    evidence_digest: str,
    query: str,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 13, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Ordinary research",
        )
        _insert_idea_spine(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Ordinary idea",
            summary="Ordinary summary",
            conversation_id=conversation_id,
            decision_note=decision_note,
            evidence_digest=evidence_digest,
        )

    reader, _ = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query=query,
        source_limit=3,
    )
    ranked = _ranked(result.rows, query)

    assert [item.id for _, item in ranked] == [str(conversation_id)]
    assert ranked[0][1].match is not None
    assert ranked[0][1].match.layer == "decision"
    assert result.rows["decisions"][0]["note"] == decision_note
    assert result.rows["decisions"][0]["artifact_digest"] == evidence_digest


@pytest.mark.parametrize("query", ["\x00needle\x00", "nee\x00dle"])
def test_search_nul_query_preserves_normalized_matching(
    search_identities,
    query: str,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 13, 15, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        expected = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Needle thesis",
        )

    reader, _ = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query=query,
        source_limit=2,
    )

    assert [item.id for _, item in _ranked(result.rows, query)] == [str(expected)]


def test_object_layer_precedes_recency_after_pinned_exact_and_symbol(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 14, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        object_conversation = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=2),
            title="Older research",
        )
        _insert_idea_spine(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=1),
            title="Gold evidence",
            summary="Gold evidence",
            conversation_id=object_conversation,
        )
        recent_conversation = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Recent allocation conversation",
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=recent_conversation,
            timestamp=now,
            role="user",
            content="Gold allocation message.",
        )

    reader, _ = _reader()
    ranked = _ranked(
        reader.search_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            query="gold",
            source_limit=5,
        ).rows,
        "gold",
    )

    assert [item.id for _, item in ranked] == [
        str(object_conversation),
        str(recent_conversation),
    ]
    assert [item.match.layer for _, item in ranked] == ["decision", "message"]


def test_conversation_cursor_pages_after_evidence_winner_without_gaps(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    timestamp = datetime(2026, 7, 27, 15, tzinfo=timezone.utc)
    inserted: set[str] = set()
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(7):
            conversation_id = _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=timestamp,
                title=f"Research {offset}",
            )
            inserted.add(str(conversation_id))
            _insert_idea_spine(
                cursor,
                user_id=owner_id,
                timestamp=timestamp,
                title=f"Evidence source {offset}",
                summary="Needle evidence",
                evidence_digest="Needle evidence",
                conversation_id=conversation_id,
            )

    reader, _ = _reader()
    seen: list[str] = []
    cursor_at = None
    cursor_id = None
    for expected_count in (3, 3, 1, 0):
        result = reader.search_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            query="needle",
            source_limit=4,
            cursor_updated_at=cursor_at,
            cursor_id=cursor_id,
        )
        page = _ranked(result.rows, "needle")[:3]
        assert len(page) == expected_count
        seen.extend(item.id for _, item in page)
        if page:
            cursor_at = page[-1][1].updated_at
            cursor_id = page[-1][1].id

    assert len(seen) == len(set(seen))
    assert set(seen) == inserted


def test_exact_two_character_symbol_pages_filter_and_ledger_are_owner_scoped(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    other_id = search_identities["other"]
    now = datetime(2026, 7, 27, 17, tzinfo=timezone.utc)
    expected_counts: dict[str, int] = {}
    promising_conversation_id: str | None = None
    with _connect() as connection, connection.cursor() as cursor:
        for offset, decision_state in enumerate(("promising", "rejected")):
            conversation_id = _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=now - timedelta(minutes=offset),
                title=f"BA owner research {offset}",
            )
            run_count = 2 if offset == 0 else 1
            expected_counts[str(conversation_id)] = run_count
            if decision_state == "promising":
                promising_conversation_id = str(conversation_id)
            newest_run_id = None
            for run_offset in range(run_count):
                newest_run_id = _insert_run(
                    cursor,
                    user_id=owner_id,
                    timestamp=(
                        now - timedelta(minutes=offset) - timedelta(seconds=run_offset)
                    ),
                    title=f"BA owner result {offset}-{run_offset}",
                    conversation_id=conversation_id,
                    symbols=["BA"],
                )
            _insert_idea_spine(
                cursor,
                user_id=owner_id,
                timestamp=now - timedelta(minutes=offset),
                title=f"BA owner idea {offset}",
                summary=f"BA owner summary {offset}",
                conversation_id=conversation_id,
                decision_state=decision_state,
                source_run_id=newest_run_id,
            )

        foreign_conversation = _insert_conversation(
            cursor,
            user_id=other_id,
            timestamp=now + timedelta(hours=1),
            title="BA foreign research",
        )
        _insert_run(
            cursor,
            user_id=other_id,
            timestamp=now + timedelta(hours=1),
            title="BA foreign result",
            conversation_id=foreign_conversation,
            symbols=["BA"],
        )

    reader, _ = _reader()
    first_result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="ba",
        source_limit=2,
        include_ledger_groups=True,
    )
    first_page = _ranked(first_result.rows, "ba")[:1]
    assert len(first_page) == 1
    assert first_result.asset_rollup is not None
    assert first_result.asset_rollup.run_count == 3
    assert first_result.ledger_counts == {
        "promising": 1,
        "watching": 0,
        "rejected": 1,
        "revisit_later": 0,
    }

    second_result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="ba",
        source_limit=2,
        cursor_updated_at=first_page[0][1].updated_at,
        cursor_id=first_page[0][1].id,
    )
    second_page = _ranked(second_result.rows, "ba")[:1]
    pages = [*first_page, *second_page]
    assert {item.id for _, item in pages} == set(expected_counts)
    assert {item.id: item.match.count for _, item in pages} == expected_counts
    assert str(foreign_conversation) not in {item.id for _, item in pages}

    promising = _ranked(
        reader.search_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            query="ba",
            source_limit=3,
            decision_state="promising",
        ).rows,
        "ba",
    )
    assert len(promising) == 1
    assert promising_conversation_id is not None
    assert promising[0][1].id == promising_conversation_id


def test_conversation_cursor_reaches_message_after_source_candidate_cap(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 18, tzinfo=timezone.utc)
    newer_pinned: list[str] = []
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(20):
            timestamp = now - timedelta(minutes=offset)
            conversation_id = _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=timestamp,
                title=f"Transcript research {offset}",
                pinned=True,
            )
            newer_pinned.append(str(conversation_id))
            _insert_message(
                cursor,
                user_id=owner_id,
                conversation_id=conversation_id,
                timestamp=timestamp,
                role="user",
                content="Needle source-cap transcript.",
            )
        unpinned_at = now - timedelta(minutes=20)
        unpinned_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=unpinned_at,
            title="Unpinned transcript research",
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=unpinned_id,
            timestamp=unpinned_at,
            role="user",
            content="Needle source-cap transcript.",
        )
        last_pinned_at = now - timedelta(minutes=21)
        last_pinned_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=last_pinned_at,
            title="Last pinned transcript research",
            pinned=True,
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=last_pinned_id,
            timestamp=last_pinned_at,
            role="user",
            content="Needle source-cap transcript.",
        )

    reader, _ = _reader()
    seen: list[str] = []
    cursor_at = None
    cursor_id = None
    while True:
        result = reader.search_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            query="needle",
            source_limit=2,
            cursor_updated_at=cursor_at,
            cursor_id=cursor_id,
        )
        page = _ranked(result.rows, "needle")[:1]
        if not page:
            break
        item = page[0][1]
        seen.append(item.id)
        cursor_at = item.updated_at
        cursor_id = item.id

    assert seen == [*newer_pinned, str(last_pinned_id), str(unpinned_id)]


def test_initial_source_cap_keeps_old_pinned_conversation_reachable(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 18, 15, tzinfo=timezone.utc)
    recent_unpinned: list[str] = []
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(10):
            conversation_id = _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=now - timedelta(minutes=offset),
                title=f"Recent unpinned conversation {offset}",
            )
            recent_unpinned.append(str(conversation_id))
        old_pinned_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=1),
            title="Old pinned conversation",
            pinned=True,
        )

    reader, _ = _reader()
    seen: list[str] = []
    cursor_at = None
    cursor_id = None
    for _ in range(12):
        result = reader.search_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            query="",
            source_limit=1,
            cursor_updated_at=cursor_at,
            cursor_id=cursor_id,
        )
        page = _ranked(result.rows, "")[:1]
        if not page:
            break
        item = page[0][1]
        seen.append(item.id)
        cursor_at = item.updated_at
        cursor_id = item.id

    assert seen == [str(old_pinned_id), *recent_unpinned]


def test_message_source_cap_collapses_conversation_before_limit(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 18, 30, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        dominant_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Dominant transcript",
        )
        for offset in range(21):
            _insert_message(
                cursor,
                user_id=owner_id,
                conversation_id=dominant_id,
                timestamp=now + timedelta(seconds=offset),
                role="user",
                content=f"Needle repeated transcript {offset}.",
            )
        remaining_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=1),
            title="Remaining transcript",
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=remaining_id,
            timestamp=now - timedelta(days=1),
            role="user",
            content="Needle only appears in this message.",
        )

    reader, _ = _reader()
    first_result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=2,
    )
    first_ranked = _ranked(first_result.rows, "needle")

    assert [item.id for _, item in first_ranked] == [
        str(dominant_id),
        str(remaining_id),
    ]
    assert first_ranked[0][1].match is not None
    assert first_ranked[0][1].match.count == 21

    page_one = first_ranked[:1]
    page_two = _ranked(
        reader.search_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            query="needle",
            source_limit=2,
            cursor_updated_at=page_one[-1][1].updated_at,
            cursor_id=page_one[-1][1].id,
        ).rows,
        "needle",
    )[:1]
    assert [item.id for _, item in page_two] == [str(remaining_id)]


def test_conversation_cursor_reaches_identical_rank_rows_after_source_cap(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    timestamp = datetime(2026, 7, 27, 19, tzinfo=timezone.utc)
    inserted: set[str] = set()
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(21):
            conversation_id = _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=timestamp,
                title=f"Identical-rank transcript {offset}",
            )
            inserted.add(str(conversation_id))
            _insert_message(
                cursor,
                user_id=owner_id,
                conversation_id=conversation_id,
                timestamp=timestamp,
                role="user",
                content="Needle identical-rank transcript.",
            )

    reader, _ = _reader()
    seen: list[str] = []
    cursor_at = None
    cursor_id = None
    for _ in range(22):
        result = reader.search_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            query="needle",
            source_limit=2,
            cursor_updated_at=cursor_at,
            cursor_id=cursor_id,
        )
        page = _ranked(result.rows, "needle")[:1]
        if not page:
            break
        item = page[0][1]
        seen.append(item.id)
        cursor_at = item.updated_at
        cursor_id = item.id

    assert len(seen) == len(set(seen))
    assert set(seen) == inserted


def test_conversation_source_cap_uses_conversation_wide_activity(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)
    expected: list[str] = []
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(20):
            timestamp = now - timedelta(minutes=offset)
            conversation_id = _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=timestamp,
                title=f"Source-cap filler {offset}",
            )
            expected.append(str(conversation_id))
            _insert_message(
                cursor,
                user_id=owner_id,
                conversation_id=conversation_id,
                timestamp=timestamp,
                role="user",
                content="Needle source-cap filler.",
            )

        old_match_at = now - timedelta(days=1)
        revived_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=old_match_at,
            title="Revived source-cap conversation",
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=revived_id,
            timestamp=old_match_at,
            role="user",
            content="Needle old matching source.",
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=revived_id,
            timestamp=now + timedelta(minutes=1),
            role="assistant",
            content="Recent unrelated activity.",
        )

    reader, _ = _reader()
    seen: list[str] = []
    cursor_at = None
    cursor_id = None
    for _ in range(22):
        result = reader.search_rows(
            scope=PERSONAL,
            user_id=str(owner_id),
            query="needle",
            source_limit=2,
            cursor_updated_at=cursor_at,
            cursor_id=cursor_id,
        )
        page = _ranked(result.rows, "needle")[:1]
        if not page:
            break
        item = page[0][1]
        seen.append(item.id)
        cursor_at = item.updated_at
        cursor_id = item.id

    assert seen == [str(revived_id), *expected]


def test_message_activity_cursor_from_page_one_is_accepted_on_page_two(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    boundary_at = datetime(2026, 7, 27, 15, 30, tzinfo=timezone.utc)
    message_at = boundary_at + timedelta(hours=1)
    following_at = boundary_at - timedelta(hours=1)
    with _connect() as connection, connection.cursor() as cursor:
        boundary_conversation = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=boundary_at,
            title="Needle boundary conversation",
        )
        _insert_message(
            cursor,
            user_id=owner_id,
            conversation_id=boundary_conversation,
            timestamp=message_at,
            role="assistant",
            content="Durable clarification without a preview update.",
        )
        following_conversation = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=following_at,
            title="Needle following conversation",
        )
        cursor.execute(
            "select updated_at from public.conversations where id = %s",
            (boundary_conversation,),
        )
        assert cursor.fetchone()[0] == boundary_at

    reader, _ = _reader()
    first_result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=2,
    )
    first_page = _ranked(first_result.rows, "needle")[:1]

    assert [item.id for _, item in first_page] == [str(boundary_conversation)]
    cursor_item = first_page[0][1]
    assert cursor_item.updated_at == message_at

    second_result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=2,
        cursor_updated_at=cursor_item.updated_at,
        cursor_id=cursor_item.id,
    )

    assert [item.id for _, item in _ranked(second_result.rows, "needle")] == [
        str(following_conversation)
    ]


def test_cursor_pivot_rejects_foreign_or_query_mismatched_conversation(
    search_identities,
) -> None:
    reader, _ = _reader()
    _, cursor_error, _ = _search_components()
    owner_id = search_identities["owner"]
    other_id = search_identities["other"]
    timestamp = datetime(2026, 7, 27, 16, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        owner_conversation = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=timestamp,
            title="Alpha pivot",
        )
        foreign_conversation = _insert_conversation(
            cursor,
            user_id=other_id,
            timestamp=timestamp,
            title="Alpha foreign",
        )

    for query, item_id in (
        ("beta", owner_conversation),
        ("alpha", foreign_conversation),
    ):
        with pytest.raises(cursor_error):
            reader.search_rows(
                scope=PERSONAL,
                user_id=str(owner_id),
                query=query,
                source_limit=3,
                cursor_updated_at=timestamp,
                cursor_id=str(item_id),
            )


def test_guest_scope_and_deleted_filter_apply_before_conversation_limit(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    timestamp = datetime(2026, 7, 27, 17, tzinfo=timezone.utc)
    workspace_id = uuid4()
    with _connect() as connection, connection.cursor() as cursor:
        _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=timestamp - timedelta(days=1),
            title="Workspace research",
            archived=True,
            conversation_id=workspace_id,
        )
        _insert_idea_spine(
            cursor,
            user_id=owner_id,
            timestamp=timestamp - timedelta(days=1),
            title="Workspace idea",
            summary="Needle workspace evidence",
            conversation_id=workspace_id,
        )
        for offset in range(6):
            deleted_id = _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=timestamp + timedelta(minutes=offset),
                title=f"Deleted research {offset}",
                deleted=True,
            )
            _insert_idea_spine(
                cursor,
                user_id=owner_id,
                timestamp=timestamp + timedelta(minutes=offset),
                title=f"Deleted idea {offset}",
                summary="Needle deleted evidence",
                conversation_id=deleted_id,
            )

    reader, _ = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=1,
        guest_scope=True,
        guest_conversation_id=str(workspace_id),
    )

    assert [item.id for _, item in _ranked(result.rows, "needle")] == [str(workspace_id)]


def test_full_lineage_aggregates_survive_more_than_five_children(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 18, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=10),
            title="Long-running research",
        )
        run_ids: list[UUID] = []
        for offset in range(7):
            run_id = _insert_run(
                cursor,
                user_id=owner_id,
                timestamp=now - timedelta(days=7 - offset),
                title=f"Run {offset}",
                conversation_id=conversation_id,
                symbols=[f"S{offset}", "AAPL"],
                start_date=f"20{19 + offset}-01-01",
                end_date=f"20{19 + offset}-12-31",
            )
            run_ids.append(run_id)
            spine = _insert_idea_spine(
                cursor,
                user_id=owner_id,
                timestamp=now - timedelta(days=7 - offset) + timedelta(minutes=1),
                title=f"Run {offset} evidence",
                summary=("Anchor decision" if offset == 0 else f"Run {offset} evidence"),
                decision_note=f"Decision {offset}",
                conversation_id=conversation_id,
                source_run_id=run_id,
                decision_state="watching",
            )
            if offset >= 5:
                cursor.execute(
                    "delete from public.decision_notes where id = %s",
                    (spine["decision"],),
                )

    reader, _ = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="anchor",
        source_limit=2,
    )
    item = _ranked(result.rows, "anchor")[0][1]

    assert item.total_runs == 7
    assert item.decided_runs == 5
    assert item.dossier is not None
    assert item.dossier.run_id == str(run_ids[6])
    assert str(item.dossier.tested.start_date) == "2025-01-01"
    assert str(item.dossier.tested.end_date) == "2025-12-31"
    assert item.decision_states == ("watching",)
    assert item.dossier.decision is None
    assert item.dossier.outcome.run_label == "Run 6"


def test_asset_rollup_exact_prefix_multi_asset_and_guest_scope_use_run_lineage(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    other_id = search_identities["other"]
    now = datetime(2026, 7, 29, 20, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        active = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=4),
            title="Active canonical history",
        )
        archived = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=3),
            title="Archived canonical history",
            archived=True,
        )
        deleted = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Deleted canonical history",
            deleted=True,
        )
        foreign = _insert_conversation(
            cursor,
            user_id=other_id,
            timestamp=now,
            title="Foreign canonical history",
        )
        active_run = _insert_run(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=3),
            title="Active multi-asset run",
            conversation_id=active,
            symbols=["TSLA", "AAPL"],
        )
        archived_run = _insert_run(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=2),
            title="Archived TSLA run",
            conversation_id=archived,
            symbols=["TSLA"],
        )
        _insert_run(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Deleted TSLA run",
            conversation_id=deleted,
            symbols=["TSLA"],
        )
        _insert_run(
            cursor,
            user_id=other_id,
            timestamp=now,
            title="Foreign TSLA run",
            conversation_id=foreign,
            symbols=["TSLA"],
        )
        _insert_idea_spine(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(days=1),
            title="Active decision",
            summary="Promising active run",
            conversation_id=active,
            source_run_id=active_run,
            decision_state="promising",
        )
        _insert_idea_spine(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Archived decision",
            summary="Watching archived run",
            conversation_id=archived,
            source_run_id=archived_run,
            decision_state="watching",
        )

    prefix_reader, prefix_pool = _reader()
    prefix = prefix_reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="tsl",
        source_limit=20,
    )
    exact = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="TSLA",
        source_limit=20,
    )
    multi_asset = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="AAPL",
        source_limit=20,
    )
    no_alias = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="Tesla",
        source_limit=20,
    )
    guest = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="TSLA",
        source_limit=20,
        guest_scope=True,
        guest_conversation_id=str(active),
    )

    for result in (prefix, exact):
        assert result.asset_rollup is not None
        assert result.asset_rollup.model_dump() == {
            "type": "asset_rollup",
            "symbol": "TSLA",
            "run_count": 2,
            "result_count": 2,
            "decision_counts": {
                "promising": 1,
                "watching": 1,
                "rejected": 0,
                "revisit_later": 0,
            },
            "last_touched_at": now,
        }
    assert multi_asset.asset_rollup is not None
    assert multi_asset.asset_rollup.symbol == "AAPL"
    assert multi_asset.asset_rollup.run_count == 1
    assert multi_asset.asset_rollup.decision_counts.promising == 1
    assert multi_asset.asset_rollup.last_touched_at == now - timedelta(days=1)
    assert no_alias.asset_rollup is None
    assert guest.asset_rollup is not None
    assert guest.asset_rollup.symbol == "TSLA"
    assert guest.asset_rollup.run_count == 1
    assert guest.asset_rollup.decision_counts.promising == 1
    assert guest.asset_rollup.decision_counts.watching == 0
    assert prefix_pool.tracker == {
        "query_count": 2,
        "row_counts": [3, 2],
    }


def test_asset_rollup_pair_symbol_normalization_matches_memory_contract(
    search_identities,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain import engine as domain_engine

    provider_calls: list[str] = []

    def fail_if_resolved(symbol: str) -> object:
        provider_calls.append(symbol)
        raise AssertionError("Omnisearch asset rollups must not resolve symbols")

    monkeypatch.setattr(domain_engine, "resolve_asset", fail_if_resolved)
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 29, 21, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Canonical pair and equity history",
        )
        for index, symbol in enumerate(("BTC/USD", "TSLA", "TSM", "ǰ/USD", "ẞ/EUR")):
            _insert_run(
                cursor,
                user_id=owner_id,
                timestamp=now - timedelta(minutes=index),
                title=f"{symbol} run",
                conversation_id=conversation_id,
                symbols=[symbol],
            )

    exact = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="  bTc/uSd  ",
        source_limit=20,
    )
    prefix = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="btc/",
        source_limit=20,
    )
    multi_symbol = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="BTC/USD TSLA",
        source_limit=20,
    )
    ambiguous = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="ts",
        source_limit=20,
    )
    combining = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="J\u030c/USD",
        source_limit=20,
    )
    expanding_reader, expanding_pool = _reader()
    expanding = expanding_reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="ss/e",
        source_limit=20,
    )

    for result in (exact, prefix):
        assert result.asset_rollup is not None
        assert result.asset_rollup.symbol == "BTC/USD"
        assert result.asset_rollup.run_count == 1
    assert multi_symbol.asset_rollup is None
    assert ambiguous.asset_rollup is None
    assert combining.asset_rollup is not None
    assert combining.asset_rollup.symbol == "ǰ/USD"
    assert expanding.asset_rollup is not None
    assert expanding.asset_rollup.symbol == "ẞ/EUR"
    assert all(not rows for rows in expanding.rows.values())
    assert expanding_pool.tracker == {"query_count": 1, "row_counts": [1]}
    assert provider_calls == []


def test_conversation_rank_casefolds_stored_symbols_like_memory(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 29, 22, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        symbol_conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Unrelated symbol conversation",
        )
        _insert_run(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Expanding casefold result",
            conversation_id=symbol_conversation_id,
            symbols=["ẞ/EUR"],
        )
        object_conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Unrelated object conversation",
        )
        _insert_idea_spine(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Ordinary evidence",
            summary="Ordinary object match",
            conversation_id=object_conversation_id,
            evidence_digest="Review ss/eur in this artifact.",
        )

    result = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="ss/eur",
        source_limit=2,
    )

    assert [item.id for _, item in _ranked(result.rows, "ss/eur")] == [
        str(symbol_conversation_id),
        str(object_conversation_id),
    ]


def test_ledger_counts_distinct_conversations_across_all_match_layers(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 19, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        promising_conversation = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Promising research",
        )
        for offset in range(2):
            _insert_idea_spine(
                cursor,
                user_id=owner_id,
                timestamp=now + timedelta(seconds=offset),
                title=f"Promising idea {offset}",
                summary="Needle evidence",
                conversation_id=promising_conversation,
                decision_state="promising",
            )
        watching_conversation = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Watching research",
        )
        _insert_idea_spine(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Watching idea",
            summary="Needle evidence",
            conversation_id=watching_conversation,
            decision_state="watching",
        )

    reader, _ = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=4,
        decision_state="promising",
        include_ledger_groups=True,
    )

    assert [item.id for _, item in _ranked(result.rows, "needle")] == [
        str(promising_conversation)
    ]
    assert result.ledger_counts == {
        "promising": 1,
        "watching": 1,
        "rejected": 0,
        "revisit_later": 0,
    }


def test_decision_filter_reaches_older_match_beyond_unfiltered_source_cap(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 20, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(10):
            _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=now - timedelta(seconds=offset),
                title=f"Needle without decision {offset}",
            )
        qualifying_conversation = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(minutes=1),
            title="Needle older watching decision",
        )
        _insert_idea_spine(
            cursor,
            user_id=owner_id,
            timestamp=now - timedelta(minutes=1),
            title="Older watching idea",
            summary="Separate judgment",
            conversation_id=qualifying_conversation,
            decision_state="watching",
        )

    result = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=1,
        decision_state="watching",
    )

    assert [item.id for _, item in _ranked(result.rows, "needle")] == [
        str(qualifying_conversation)
    ]


def test_ledger_counts_include_matches_beyond_presentation_source_cap(
    search_identities,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 7, 27, 21, tzinfo=timezone.utc)
    expected_count = 12
    with _connect() as connection, connection.cursor() as cursor:
        for offset in range(expected_count):
            conversation_id = _insert_conversation(
                cursor,
                user_id=owner_id,
                timestamp=now - timedelta(seconds=offset),
                title=f"Needle ledger {offset}",
            )
            _insert_idea_spine(
                cursor,
                user_id=owner_id,
                timestamp=now - timedelta(seconds=offset),
                title=f"Ledger idea {offset}",
                summary="Separate judgment",
                conversation_id=conversation_id,
                decision_state="watching",
            )

    result = _reader()[0].search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=1,
        include_ledger_groups=True,
    )

    assert len(result.rows["conversations"]) == 1
    assert result.ledger_counts == {
        "promising": 0,
        "watching": expected_count,
        "rejected": 0,
        "revisit_later": 0,
    }


@pytest.mark.parametrize("initial_volume,larger_volume", [(40, 400)])
def test_search_query_and_row_budget_are_constant_as_volume_grows(
    search_identities,
    initial_volume: int,
    larger_volume: int,
) -> None:
    owner_id = search_identities["owner"]
    timestamp = datetime(2026, 7, 27, 20, tzinfo=timezone.utc)

    def insert_conversations(start: int, stop: int) -> None:
        with _connect() as connection, connection.cursor() as cursor:
            for offset in range(start, stop):
                _insert_conversation(
                    cursor,
                    user_id=owner_id,
                    timestamp=timestamp - timedelta(seconds=offset),
                    title=f"Needle scale {offset}",
                )

    insert_conversations(0, initial_volume)
    first_reader, first_pool = _reader()
    first = first_reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=6,
    )
    insert_conversations(initial_volume, larger_volume)
    larger_reader, larger_pool = _reader()
    larger = larger_reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="needle",
        source_limit=6,
    )

    assert len(first.rows["conversations"]) == 6
    assert len(larger.rows["conversations"]) == 6
    expected_budget = {"query_count": 2, "row_counts": [6, 6]}
    assert first_pool.tracker == expected_budget
    assert larger_pool.tracker == expected_budget
