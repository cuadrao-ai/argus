from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase/migrations_archive/"
    / "20260801000000_add_conversation_activity_read_states.sql"
)


def _normalized() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_conversation_read_state_table_preserves_owner_cascade_and_read_shape() -> None:
    assert MIGRATION.exists()
    sql = _normalized()

    assert "create table public.conversation_read_states" in sql
    assert "primary key (user_id, conversation_id)" in sql
    assert "read_through_occurred_at timestamptz" in sql
    assert "read_through_source_kind text" in sql
    assert "read_through_source_id uuid" in sql
    assert "manual_unread_at timestamptz" in sql
    assert "read_through_source_kind in ('chat_turn', 'backtest_job')" in sql
    assert "read_through_occurred_at is null" in sql
    assert "read_through_source_kind is null" in sql
    assert "read_through_source_id is null" in sql

    assert "unique (id, user_id)" in sql
    assert "foreign key (conversation_id, user_id)" in sql
    assert "references public.conversations(id, user_id)" in sql
    assert "on update cascade" in sql
    assert "on delete cascade" in sql


def test_conversation_read_state_rls_is_owner_read_service_write_only() -> None:
    sql = _normalized()

    assert (
        "alter table public.conversation_read_states enable row level security"
        in sql
    )
    assert "conversation_read_states_owner_select" in sql
    assert "for select to authenticated" in sql
    assert "using ((select auth.uid()) = user_id)" in sql
    assert (
        "revoke all on public.conversation_read_states from public, anon, "
        "authenticated"
    ) in sql
    assert "grant select on public.conversation_read_states to authenticated" in sql
    assert (
        "grant select, insert, update, delete on "
        "public.conversation_read_states to service_role"
    ) in sql
    assert (
        "revoke insert, update, delete on public.conversation_read_states "
        "from anon, authenticated"
    ) in sql


def test_activity_indexes_bound_lifecycle_and_job_reads() -> None:
    sql = _normalized()

    for index_name in (
        "chat_turn_lifecycles_activity_operation_idx",
        "chat_turn_lifecycles_activity_terminal_idx",
        "backtest_jobs_activity_operation_idx",
        "backtest_jobs_activity_terminal_idx",
    ):
        assert f"create index {index_name}" in sql
    assert "user_id, conversation_id, status" in sql
    assert "terminal_at desc" in sql
    assert "finished_at desc" in sql


def test_batch_reconciliation_keeps_existing_evidence_predicate_and_global_cap() -> None:
    sql = _normalized()
    function = sql.split(
        "create function public.reconcile_stale_conversation_activity_turns(",
        1,
    )[1].split("$$;", 1)[0]

    assert "p_conversation_ids uuid[]" in function
    assert "cardinality(p_conversation_ids) > 100" in function
    assert "limit 20" in function
    assert "interval '15 minutes'" in function
    assert "for update of l skip locked" in function
    assert "metadata #>> '{agent_runtime_turn,turn_id}'" in function
    assert "metadata #>> '{agent_runtime_turn,request_id}'" in function
    assert "metadata #> '{agent_runtime_turn,terminal}' = 'true'::jsonb" in function
    assert "in ('completed', 'recoverable_failed')" in function
    assert "jsonb_typeof" in function
    assert "select public.transition_chat_turn(" in function


def test_batch_source_read_is_bounded_typed_and_never_reads_message_prose() -> None:
    sql = _normalized()
    function = sql.split(
        "create function public.read_conversation_activity_sources(",
        1,
    )[1].split("$$;", 1)[0]

    assert "p_conversation_ids uuid[]" in function
    assert "cardinality(p_conversation_ids) > 100" in function
    assert "agent_runtime_stage_outcome" in function
    assert "conversation_result_card" in function
    assert "evidence_artifacts" in function
    assert "content" not in function
    assert "result_hydrateable" in function
    assert "conversation_read_states" in function
    assert "order by" in function
    assert "limit 1" in function
    # Deleted-list responses still emit chat records; the API endpoint itself
    # separately returns 404 for direct access to a deleted conversation.
    assert "c.deleted_at is null" not in function


def test_read_mutation_locks_and_revalidates_source_before_monotonic_advance() -> None:
    sql = _normalized()
    function = sql.split(
        "create function public.mutate_conversation_activity_read_state(",
        1,
    )[1].split("$$;", 1)[0]

    assert "p_action text" in function
    assert "p_source_kind text" in function
    assert "p_source_id uuid" in function
    assert "for update" in function
    assert "conversation_read_states" in function
    assert "manual_unread_at" in function
    assert "'conflict'" in function
    assert "read_through_occurred_at" in function
    assert "read_through_source_kind" in function
    assert "read_through_source_id" in function
    assert "greatest" not in function
    assert "on conflict (user_id, conversation_id)" in function


def test_activity_rpcs_are_service_role_only() -> None:
    sql = _normalized()

    for function_name in (
        "reconcile_stale_conversation_activity_turns",
        "read_conversation_activity_sources",
        "mutate_conversation_activity_read_state",
    ):
        for role in ("public", "anon", "authenticated"):
            assert f"revoke all on function public.{function_name}(" in sql
            assert f"from {role}" in sql
        assert f"grant execute on function public.{function_name}(" in sql
    assert sql.count("to service_role") >= 4


def test_baseline_is_cutoff_safe_keyset_batched_and_timestamp_neutral() -> None:
    sql = _normalized()
    baseline_function = sql.split(
        "create function public.baseline_conversation_activity_read_states(",
        1,
    )[1].split("$$;", 1)[0]
    baseline = sql.split("do $activity_baseline$", 1)[1]

    assert (
        "create function public.baseline_conversation_activity_read_states("
        in sql
    )
    assert "v_cutoff timestamptz := clock_timestamp()" in baseline
    assert "v_after_id" in baseline
    assert "500" in baseline
    assert "c.id > p_after_id" in baseline_function
    assert "<= p_cutoff" in baseline_function
    assert (
        "on conflict (user_id, conversation_id) do nothing"
        in baseline_function
    )
    assert "insert into public.conversation_read_states" in baseline_function
    assert "update public.conversations" not in baseline_function
    assert "update public.messages" not in baseline_function
    assert "update public.chat_turn_lifecycles" not in baseline_function
    assert "update public.backtest_jobs" not in baseline_function
    assert "update public.backtest_runs" not in baseline_function
