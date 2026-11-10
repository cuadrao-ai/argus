from pathlib import Path

from argus.domain.search_sql_text import normalizer_expression
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "supabase" / "migrations_archive" / "20260727000001_add_bounded_read_indexes.sql"
)
SEARCH_MIGRATION_GLOB = "*_add_search_trigram_indexes.sql"
HISTORY_STATE_MIGRATION_GLOB = "*_add_history_state_page_indexes.sql"
MESSAGE_RECALL_MIGRATION_GLOB = "*_add_message_recall_index.sql"
DECISION_RECALL_MIGRATION_GLOB = "*_add_decision_recall_index.sql"
ASSET_SYMBOL_MIGRATION_GLOB = "*_add_asset_symbol_prefix_indexes.sql"


def _migration_sql() -> str:
    assert MIGRATION.exists(), "bounded-read index migration is missing"
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_bounded_read_migration_adds_only_the_three_proven_indexes() -> None:
    migration = _migration_sql()

    assert (
        "create index if not exists idx_conversations_active_page "
        "on public.conversations "
        "(user_id, pinned desc, updated_at desc, id desc) "
        "where deleted_at is null"
    ) in migration
    assert (
        "create index if not exists idx_messages_reload_artifact_page "
        "on public.messages "
        "(user_id, conversation_id, created_at, id)"
    ) in migration
    assert (
        "create index if not exists idx_decision_notes_idea_latest "
        "on public.decision_notes "
        "(user_id, idea_id, updated_at desc, id desc)"
    ) in migration

    assert migration.count("create index if not exists") == 3
    assert "create unique index" not in migration
    assert "create function" not in migration
    assert "create view" not in migration
    assert "create materialized view" not in migration
    assert "generated always as" not in migration
    assert "grant " not in migration


def test_message_artifact_index_is_a_reload_superset_without_content() -> None:
    migration = _migration_sql()

    assert "where role = 'assistant'" in migration
    for field in (
        "active_confirmation_reference",
        "backtest_job",
        "backtest_job_id",
        "confirmation_card",
        "confirmation_payload",
        "latest_run_id",
        "result_card",
        "result_run_id",
    ):
        assert f"metadata->>'{field}'" in migration
    for artifact_kind in (
        "confirmation",
        "result",
        "backtest_result",
        "backtest_job",
    ):
        assert f'"artifact_kind": "{artifact_kind}"' in migration

    assert "content" not in migration
    assert "user_id, conversation_id, created_at, id" in migration


def test_bounded_read_migration_records_exact_index_rollback() -> None:
    migration = _migration_sql()

    for index_name in (
        "idx_conversations_active_page",
        "idx_messages_reload_artifact_page",
        "idx_decision_notes_idea_latest",
    ):
        assert f"drop index if exists public.{index_name}" in migration


def test_search_trigram_migration_is_private_and_index_only() -> None:
    migrations = sorted((ROOT / "supabase" / "migrations_archive").glob(SEARCH_MIGRATION_GLOB))
    assert len(migrations) == 1, "Search trigram migration is missing or ambiguous"
    migration = " ".join(migrations[0].read_text(encoding="utf-8").lower().split())

    assert "create extension if not exists pg_trgm with schema extensions" in migration
    for index_name in (
        "idx_conversations_search_norm_trgm",
        "idx_strategies_search_norm_trgm",
        "idx_collections_search_norm_trgm",
        "idx_backtest_runs_search_norm_trgm",
        "idx_ideas_search_norm_trgm",
        "idx_evidence_search_norm_trgm",
    ):
        assert f"create index if not exists {index_name}" in migration
        assert f"drop index if exists public.{index_name}" in migration

    assert migration.count("create index if not exists") == 6
    assert " extensions.gin_trgm_ops" in migration
    assert "create function" not in migration
    assert "create view" not in migration
    assert "create materialized view" not in migration
    assert "generated always as" not in migration
    assert "grant " not in migration


def test_history_state_page_migration_adds_only_plan_proven_indexes() -> None:
    migrations = sorted(
        (ROOT / "supabase" / "migrations_archive").glob(HISTORY_STATE_MIGRATION_GLOB)
    )
    assert len(migrations) == 1, "History state-page migration is missing or ambiguous"
    migration = " ".join(migrations[0].read_text(encoding="utf-8").lower().split())

    assert (
        "create index if not exists idx_conversations_deleted_page "
        "on public.conversations "
        "(user_id, pinned desc, updated_at desc, id desc) "
        "where deleted_at is not null"
    ) in migration
    for table_name in ("strategies", "collections"):
        assert (
            f"create index if not exists idx_{table_name}_history_page "
            f"on public.{table_name} "
            "(user_id, pinned desc, updated_at desc, id desc)"
        ) in migration

    assert migration.count("create index if not exists") == 3
    for index_name in (
        "idx_conversations_deleted_page",
        "idx_strategies_history_page",
        "idx_collections_history_page",
    ):
        assert f"drop index if exists public.{index_name}" in migration

    assert "create unique index" not in migration
    assert "create function" not in migration
    assert "create view" not in migration
    assert "create materialized view" not in migration
    assert "generated always as" not in migration
    assert "grant " not in migration


def test_message_recall_migration_is_user_only_private_and_index_only() -> None:
    migrations = sorted(
        (ROOT / "supabase" / "migrations_archive").glob(MESSAGE_RECALL_MIGRATION_GLOB)
    )
    assert len(migrations) == 1, "Message recall migration is missing or ambiguous"
    migration = " ".join(migrations[0].read_text(encoding="utf-8").lower().split())

    index_name = "idx_messages_user_content_norm_trgm"
    assert f"create index if not exists {index_name}" in migration
    assert "on public.messages using gin" in migration
    normalized_content = " ".join(
        normalizer_expression(sql.Identifier("content")).as_string().lower().split()
    )
    assert f"(({normalized_content}) extensions.gin_trgm_ops)" in migration
    assert "extensions.gin_trgm_ops" in migration
    assert "where role = 'user'" in migration
    assert f"drop index if exists public.{index_name}" in migration
    assert migration.count("create index if not exists") == 1
    assert "create unique index" not in migration
    assert "create function" not in migration
    assert "create view" not in migration
    assert "create materialized view" not in migration
    assert "generated always as" not in migration
    assert "grant " not in migration


def test_decision_recall_migration_is_private_and_index_only() -> None:
    migrations = sorted(
        (ROOT / "supabase" / "migrations_archive").glob(DECISION_RECALL_MIGRATION_GLOB)
    )
    assert len(migrations) == 1, "Decision recall migration is missing or ambiguous"
    migration = " ".join(migrations[0].read_text(encoding="utf-8").lower().split())

    index_name = "idx_decision_notes_recall_norm_trgm"
    assert f"create index if not exists {index_name}" in migration
    assert "on public.decision_notes using gin" in migration
    normalized_decision = " ".join(
        normalizer_expression(
            sql.SQL("decision_state || ' ' || coalesce(note, '')")
        )
        .as_string()
        .lower()
        .split()
    )
    assert f"(({normalized_decision}) extensions.gin_trgm_ops)" in migration
    assert "extensions.gin_trgm_ops" in migration
    assert f"drop index if exists public.{index_name}" in migration
    assert migration.count("create index if not exists") == 1
    assert "create unique index" not in migration
    assert "create function" not in migration
    assert "create view" not in migration
    assert "create materialized view" not in migration
    assert "generated always as" not in migration
    assert "grant " not in migration


def test_asset_symbol_prefix_migration_indexes_all_five_canonical_slots() -> None:
    from argus.domain.search_sql_text import symbol_normalizer_expression

    from scripts.generate_asset_symbol_index_migration import render_migration

    migrations = sorted(
        (ROOT / "supabase" / "migrations_archive").glob(ASSET_SYMBOL_MIGRATION_GLOB)
    )
    assert len(migrations) == 1, "Asset symbol prefix migration is missing or ambiguous"
    migration = " ".join(migrations[0].read_text(encoding="utf-8").split())
    lowered = migration.lower()
    function_name = "public.argus_search_symbol_casefold"
    expected_casefold = " ".join(
        symbol_normalizer_expression(sql.Identifier("source_text"))
        .as_string()
        .split()
    )

    assert f"create or replace function {function_name}" in lowered
    assert expected_casefold in migration
    assert "language sql immutable strict parallel safe" in lowered
    for slot in range(1, 6):
        index_name = f"idx_backtest_runs_owner_symbol_{slot}_prefix"
        assert f"create index if not exists {index_name}" in lowered
        assert (
            f"on public.backtest_runs ( user_id, "
            f"(btrim({function_name}(symbols[{slot}])) collate \"c\") )"
        ) in lowered
        assert (
            f"where status = 'completed' and symbols[{slot}] is not null"
        ) in lowered
        assert f"drop index if exists public.{index_name}" in lowered
    assert lowered.count("create index if not exists") == 5
    assert f"drop function if exists {function_name}(text)" in lowered
    assert "create table" not in lowered
    assert "create view" not in lowered
    assert "create materialized view" not in lowered
    assert "generated always as" not in lowered
    assert migrations[0].read_text(encoding="utf-8") == render_migration()
