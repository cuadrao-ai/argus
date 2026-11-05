"""Disposable-Postgres proofs for the issue #232 forward indexes."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from argus.domain.search_sql_text import normalizer_expression
from psycopg import sql

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)

EXPECTED_INDEXES = {
    "idx_conversations_active_page",
    "idx_conversations_deleted_page",
    "idx_messages_reload_artifact_page",
    "idx_decision_notes_idea_latest",
    "idx_strategies_history_page",
    "idx_collections_history_page",
}
SEARCH_EXPECTED_INDEXES = {
    "idx_conversations_search_norm_trgm",
    "idx_strategies_search_norm_trgm",
    "idx_collections_search_norm_trgm",
    "idx_backtest_runs_search_norm_trgm",
    "idx_ideas_search_norm_trgm",
    "idx_evidence_search_norm_trgm",
    "idx_messages_user_content_norm_trgm",
    "idx_decision_notes_recall_norm_trgm",
    "idx_backtest_runs_owner_symbol_1_prefix",
    "idx_backtest_runs_owner_symbol_2_prefix",
    "idx_backtest_runs_owner_symbol_3_prefix",
    "idx_backtest_runs_owner_symbol_4_prefix",
    "idx_backtest_runs_owner_symbol_5_prefix",
}


def _plan_index_names(node: dict[str, Any]) -> set[str]:
    indexes = {str(node["Index Name"])} if node.get("Index Name") else set()
    for child in node.get("Plans", []):
        indexes.update(_plan_index_names(child))
    return indexes


def _insert_identity(cursor: Any, *, user_id: UUID, label: str) -> None:
    email = f"bounded-index-{label}-{user_id}@argus.local"
    cursor.execute(
        "insert into auth.users (id, email, is_anonymous) values (%s, %s, false)",
        (user_id, email),
    )
    cursor.execute(
        "insert into public.profiles (id, email) values (%s, %s)",
        (user_id, email),
    )


def _insert_p1_spine(cursor: Any, *, user_id: UUID) -> dict[str, UUID]:
    idea_id = uuid4()
    version_id = uuid4()
    artifact_id = uuid4()
    decision_id = uuid4()
    cursor.execute(
        """
        insert into public.ideas (
            id, user_id, title, summary, lifecycle
        )
        values (%s, %s, 'Fixture idea', 'Fixture summary', 'decided')
        """,
        (idea_id, user_id),
    )
    cursor.execute(
        """
        insert into public.idea_versions (
            id, idea_id, user_id, version_number, canonical_spec,
            strategy_snapshot, title, summary, lifecycle
        )
        values (
            %s, %s, %s, 1, '{}'::jsonb, '{}'::jsonb,
            'Fixture version', 'Fixture summary', 'decided'
        )
        """,
        (version_id, idea_id, user_id),
    )
    cursor.execute(
        "update public.ideas set active_version_id = %s where id = %s",
        (version_id, idea_id),
    )
    cursor.execute(
        """
        insert into public.evidence_artifacts (
            id, idea_id, idea_version_id, user_id, artifact_type,
            lifecycle, title, digest, payload
        )
        values (
            %s, %s, %s, %s, 'backtest', 'decided',
            'Fixture evidence', 'Fixture digest', '{}'::jsonb
        )
        """,
        (artifact_id, idea_id, version_id, user_id),
    )
    cursor.execute(
        """
        insert into public.decision_notes (
            id, idea_id, idea_version_id, evidence_artifact_id, user_id,
            decision_state, note
        )
        values (%s, %s, %s, %s, %s, 'watching', 'Fixture note')
        """,
        (decision_id, idea_id, version_id, artifact_id, user_id),
    )
    return {
        "idea_id": idea_id,
        "artifact_id": artifact_id,
        "decision_id": decision_id,
    }


def _insert_search_rows(
    cursor: Any,
    *,
    user_id: UUID,
    conversation_id: UUID,
) -> None:
    cursor.execute(
        """
        insert into public.strategies (
            id, user_id, conversation_id, name, name_source, template,
            asset_class, symbols, parameters, metrics_preferences,
            benchmark_symbol
        )
        values (
            %s, %s, %s, 'Fixture strategy', 'ai_generated', 'buy_hold',
            'equity', array['AAPL'], '{}'::jsonb,
            array['total_return_pct'], 'SPY'
        )
        """,
        (uuid4(), user_id, conversation_id),
    )
    cursor.execute(
        """
        insert into public.collections (id, user_id, name, name_source)
        values (%s, %s, 'Fixture collection', 'ai_generated')
        """,
        (uuid4(), user_id),
    )
    cursor.execute(
        """
        insert into public.backtest_runs (
            id, user_id, conversation_id, status, asset_class, symbols,
            allocation_method, benchmark_symbol, config_snapshot, metrics,
            conversation_result_card
        )
        values (
            %s, %s, %s, 'completed', 'equity', array['AAPL'],
            'equal_weight', 'SPY', '{}'::jsonb, '{}'::jsonb,
            '{"title":"Fixture run","symbols":["AAPL"]}'::jsonb
        )
        """,
        (uuid4(), user_id, conversation_id),
    )


@pytest.fixture
def bounded_index_rows() -> Iterator[dict[str, Any]]:
    owner_id = uuid4()
    other_id = uuid4()
    owner_conversation_id = uuid4()
    other_conversation_id = uuid4()
    owner_message_id = uuid4()
    owner_recall_message_id = uuid4()
    other_message_id = uuid4()
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            _insert_identity(cursor, user_id=owner_id, label="owner")
            _insert_identity(cursor, user_id=other_id, label="other")
            cursor.execute(
                """
                insert into public.conversations (
                    id, user_id, title, title_source, language, pinned, archived
                )
                values
                    (%s, %s, 'Owner fixture', 'system_default', 'en', false, false),
                    (%s, %s, 'Other fixture', 'system_default', 'en', false, false)
                """,
                (
                    owner_conversation_id,
                    owner_id,
                    other_conversation_id,
                    other_id,
                ),
            )
            cursor.execute(
                """
                insert into public.messages (
                    id, conversation_id, user_id, role, content, metadata
                )
                values
                    (
                        %s, %s, %s, 'assistant', 'Fixture',
                        '{"result_card":{"status":"complete"}}'::jsonb
                    ),
                    (%s, %s, %s, 'user', 'Copper lantern fixture', '{}'::jsonb),
                    (%s, %s, %s, 'assistant', 'Fixture', '{}'::jsonb)
                """,
                (
                    owner_message_id,
                    owner_conversation_id,
                    owner_id,
                    owner_recall_message_id,
                    owner_conversation_id,
                    owner_id,
                    other_message_id,
                    other_conversation_id,
                    other_id,
                ),
            )
            _insert_search_rows(
                cursor,
                user_id=owner_id,
                conversation_id=owner_conversation_id,
            )
            _insert_search_rows(
                cursor,
                user_id=other_id,
                conversation_id=other_conversation_id,
            )
            owner_spine = _insert_p1_spine(cursor, user_id=owner_id)
            other_spine = _insert_p1_spine(cursor, user_id=other_id)
    try:
        yield {
            "owner_id": owner_id,
            "other_id": other_id,
            "owner_conversation_id": owner_conversation_id,
            "owner_message_id": owner_message_id,
            "owner_recall_message_id": owner_recall_message_id,
            "owner_spine": owner_spine,
            "other_spine": other_spine,
        }
    finally:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from auth.users where id = any(%s::uuid[])",
                    ([owner_id, other_id],),
                )


def test_forward_indexes_exist_without_changing_rls() -> None:
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select indexname
                from pg_indexes
                where schemaname = 'public'
                  and indexname = any(%s)
                """,
                (list(EXPECTED_INDEXES | SEARCH_EXPECTED_INDEXES),),
            )
            assert {str(row[0]) for row in cursor.fetchall()} == (
                EXPECTED_INDEXES | SEARCH_EXPECTED_INDEXES
            )

            cursor.execute(
                """
                select relname, relrowsecurity
                from pg_class
                where relnamespace = 'public'::regnamespace
                  and relname = any(%s)
                """,
                (
                    [
                        "conversations",
                        "strategies",
                        "collections",
                        "backtest_runs",
                        "ideas",
                        "evidence_artifacts",
                        "messages",
                        "decision_notes",
                    ],
                ),
            )
            assert dict(cursor.fetchall()) == {
                "conversations": True,
                "strategies": True,
                "collections": True,
                "backtest_runs": True,
                "ideas": True,
                "evidence_artifacts": True,
                "decision_notes": True,
                "messages": True,
            }


def test_authenticated_claims_keep_both_owners_isolated(
    bounded_index_rows: dict[str, Any],
) -> None:
    for claim_name in ("owner_id", "other_id"):
        claim_id = bounded_index_rows[claim_name]
        connection = psycopg.connect(DSN)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "grant select on public.conversations, public.messages, "
                    "public.decision_notes, public.strategies, "
                    "public.collections, public.backtest_runs, public.ideas, "
                    "public.evidence_artifacts to authenticated"
                )
                cursor.execute("set local role authenticated")
                cursor.execute(
                    "select set_config('request.jwt.claims', %s, true)",
                    (
                        json.dumps(
                            {
                                "sub": str(claim_id),
                                "role": "authenticated",
                            }
                        ),
                    ),
                )
                for table_name in (
                    "conversations",
                    "strategies",
                    "collections",
                    "backtest_runs",
                    "ideas",
                    "evidence_artifacts",
                    "messages",
                    "decision_notes",
                ):
                    cursor.execute(
                        f"select user_id from public.{table_name}"  # noqa: S608
                    )
                    rows = cursor.fetchall()
                    assert rows
                    assert {row[0] for row in rows} == {claim_id}
        finally:
            connection.rollback()
            connection.close()


def test_current_read_predicates_select_each_forward_index(
    bounded_index_rows: dict[str, Any],
) -> None:
    owner_id = bounded_index_rows["owner_id"]
    conversation_id = bounded_index_rows["owner_conversation_id"]
    idea_id = bounded_index_rows["owner_spine"]["idea_id"]
    with psycopg.connect(DSN) as connection:
        with connection.cursor() as cursor:
            # Keep this tiny capability fixture deterministic; scale tests use
            # the normal planner against 12,000-row owners.
            cursor.execute("set local enable_seqscan = off")
            cursor.execute("set local enable_sort = off")
            cursor.execute("set local enable_incremental_sort = off")
            queries = {
                "idx_conversations_active_page": (
                    """
                    explain (format json)
                    select *
                    from public.conversations
                    where user_id = %s
                      and deleted_at is null
                    order by pinned desc, updated_at desc, id desc
                    limit 21
                    """,
                    (owner_id,),
                ),
                "idx_messages_reload_artifact_page": (
                    """
                    explain (format json)
                    select id
                    from public.messages
                    where user_id = %s
                      and conversation_id = %s
                      and role = 'assistant'
                      and metadata->>'result_card' <> ''
                      and metadata->'result_card' <> '{}'::jsonb
                      and metadata->'result_card' <> '[]'::jsonb
                      and metadata->'result_card' <> 'false'::jsonb
                      and metadata->'result_card' <> '0'::jsonb
                    order by created_at, id
                    limit 1
                    """,
                    (owner_id, conversation_id),
                ),
                "idx_messages_user_content_norm_trgm": (
                    sql.SQL(
                        """
                        explain (format json)
                        select id
                        from public.messages
                        where role = 'user'
                          and {} like %s
                        limit 21
                        """
                    ).format(normalizer_expression(sql.Identifier("content"))),
                    ("%copper%",),
                ),
                "idx_decision_notes_recall_norm_trgm": (
                    sql.SQL(
                        """
                        explain (format json)
                        select id
                        from public.decision_notes
                        where {} like %s
                        limit 21
                        """
                    ).format(
                        normalizer_expression(
                            sql.SQL("decision_state || ' ' || coalesce(note, '')")
                        )
                    ),
                    ("%fixture%",),
                ),
                "idx_decision_notes_idea_latest": (
                    """
                    explain (format json)
                    select decision_state
                    from public.decision_notes
                    where user_id = %s
                      and idea_id = %s
                    order by updated_at desc, id desc
                    limit 1
                    """,
                    (owner_id, idea_id),
                ),
                "idx_conversations_deleted_page": (
                    """
                    explain (format json)
                    select *
                    from public.conversations
                    where user_id = %s
                      and deleted_at is not null
                    order by pinned desc, updated_at desc, id desc
                    limit 21
                    """,
                    (owner_id,),
                ),
                "idx_strategies_history_page": (
                    """
                    explain (format json)
                    select *
                    from public.strategies
                    where user_id = %s
                      and deleted_at is null
                    order by pinned desc, updated_at desc, id desc
                    limit 21
                    """,
                    (owner_id,),
                ),
                "idx_collections_history_page": (
                    """
                    explain (format json)
                    select *
                    from public.collections
                    where user_id = %s
                      and deleted_at is null
                    order by pinned desc, updated_at desc, id desc
                    limit 21
                    """,
                    (owner_id,),
                ),
            }
            for expected_index, (query, params) in queries.items():
                cursor.execute(query, params)
                plan = cursor.fetchone()[0][0]["Plan"]
                assert expected_index in _plan_index_names(plan)

            for slot in range(1, 6):
                cursor.execute(
                    f"""
                    explain (format json)
                    select id
                    from public.backtest_runs
                    where user_id = %s
                      and status = 'completed'
                      and symbols[{slot}] is not null
                      and btrim(
                          public.argus_search_symbol_casefold(symbols[{slot}])
                      ) collate "C" >= %s collate "C"
                      and btrim(
                          public.argus_search_symbol_casefold(symbols[{slot}])
                      ) collate "C" < %s collate "C"
                    limit 2
                    """,  # noqa: S608
                    (owner_id, "aap", "aaq"),
                )
                plan = cursor.fetchone()[0][0]["Plan"]
                assert (
                    f"idx_backtest_runs_owner_symbol_{slot}_prefix"
                    in _plan_index_names(plan)
                )

                cursor.execute(
                    f"""
                    explain (format json)
                    select id
                    from public.backtest_runs
                    where user_id = %s
                      and status = 'completed'
                      and symbols[{slot}] is not null
                      and btrim(
                          public.argus_search_symbol_casefold(symbols[{slot}])
                      ) collate "C" = %s collate "C"
                    limit 2
                    """,  # noqa: S608
                    (owner_id, "aapl"),
                )
                exact_plan = cursor.fetchone()[0][0]["Plan"]
                assert (
                    f"idx_backtest_runs_owner_symbol_{slot}_prefix"
                    in _plan_index_names(exact_plan)
                )
