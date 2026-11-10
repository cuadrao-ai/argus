from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE_MIGRATION = (
    ROOT
    / "supabase/migrations_archive/20260723000001_add_chat_turn_lifecycles.sql"
)
ACCEPTANCE_MIGRATION = (
    ROOT
    / (
        "supabase/migrations_archive/"
        "20260723000002_chat_turn_acceptance_and_reconciliation.sql"
    )
)
LIFECYCLE_RPC_MIGRATION = (
    ROOT
    / (
        "supabase/migrations_archive/"
        "20260723000003_chat_turn_option_acceptance_and_finalization.sql"
    )
)
IDEMPOTENT_FINALIZATION_MIGRATION = (
    ROOT
    / (
        "supabase/migrations_archive/"
        "20260724214312_idempotent_chat_turn_finalization.sql"
    )
)
BASE_ACCEPTANCE_MIGRATION_SHA256 = (
    "b0e7ade1d01b8c3290397b82dc76048f8c64477d4ef0f6eeea8a1b8c0b5dca3f"
)


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_committed_acceptance_migration_is_byte_immutable() -> None:
    digest = hashlib.sha256(ACCEPTANCE_MIGRATION.read_bytes()).hexdigest()

    assert digest == BASE_ACCEPTANCE_MIGRATION_SHA256


def test_lifecycle_table_has_locked_constraints_indexes_and_owner_rls() -> None:
    assert TABLE_MIGRATION.exists()
    sql = _normalized(TABLE_MIGRATION)

    assert "create table public.chat_turn_lifecycles" in sql
    assert (
        "turn_id uuid primary key references public.messages(id)"
        in sql
    )
    assert "user_id uuid not null references public.profiles(id)" in sql
    assert (
        "conversation_id uuid not null references public.conversations(id)"
        in sql
    )
    for status in (
        "accepted",
        "running",
        "completed",
        "recoverable_failed",
        "abandoned",
        "reconciled",
    ):
        assert f"'{status}'" in sql
    assert "reconciled_outcome in ('completed', 'recoverable_failed')" in sql
    assert "assistant_message_id uuid unique" in sql
    assert "status = 'abandoned'" in sql
    assert "assistant_message_id is null" in sql
    assert "failure_code = 'turn_abandoned'" in sql
    assert "retryable = true" in sql
    assert (
        "create index chat_turn_lifecycles_conversation_status_idx" in sql
    )
    assert "create index chat_turn_lifecycles_user_status_idx" in sql

    assert (
        "alter table public.chat_turn_lifecycles enable row level security"
        in sql
    )
    assert "for select to authenticated" in sql
    assert "(select auth.uid()) = user_id" in sql
    assert (
        "revoke insert, update, delete on public.chat_turn_lifecycles "
        "from anon, authenticated"
    ) in sql
    assert "grant select on public.chat_turn_lifecycles to authenticated" in sql
    assert (
        "grant select, insert, update, delete on "
        "public.chat_turn_lifecycles to service_role"
    ) in sql


def test_transition_function_is_service_role_only_null_safe_cas() -> None:
    sql = _normalized(TABLE_MIGRATION)

    assert "create or replace function public.transition_chat_turn(" in sql
    assert "p_turn_id uuid" in sql
    assert "p_to_status text" in sql
    assert "p_assistant_message_id uuid" in sql
    assert "p_reconciled_outcome text" in sql
    assert "p_failure_code text" in sql
    assert "p_retryable boolean" in sql
    assert "for update" in sql
    assert "is not distinct from" in sql
    assert "v_turn.status in (" in sql
    assert "'completed'" in sql
    assert "'recoverable_failed'" in sql
    assert "'abandoned'" in sql
    assert "'reconciled'" in sql
    assert "v_turn.status not in ('accepted', 'running')" in sql
    assert "v_turn.status = 'accepted' and p_to_status = 'running'" in sql
    assert (
        "v_message.metadata -> 'agent_runtime_turn' ? 'failure_code'"
        in sql
    )
    assert "v_message.metadata -> 'agent_runtime_turn' ? 'retryable'" in sql
    assert (
        "jsonb_typeof( v_message.metadata #> "
        "'{agent_runtime_turn,retryable}' ) is distinct from 'boolean'"
        in sql
    )
    assert (
        "jsonb_typeof( v_message.metadata #> "
        "'{agent_runtime_turn,failure_code}' ) "
        "in ('string', 'null')"
    ) in sql
    assert (
        "v_message.metadata #>> '{agent_runtime_turn,failure_code}' "
        "is distinct from p_failure_code"
    ) in sql
    assert (
        "v_message.metadata #> '{agent_runtime_turn,retryable}' "
        "is distinct from to_jsonb(v_retryable)"
    ) in sql
    for outcome in ("applied", "noop", "conflict", "missing", "invalid"):
        assert f"'outcome', '{outcome}'" in sql
    for role in ("public", "anon", "authenticated"):
        assert (
            "revoke all on function public.transition_chat_turn("
            in sql
        )
        assert f"from {role}" in sql
    assert "grant execute on function public.transition_chat_turn(" in sql
    assert "to service_role" in sql


def test_acceptance_rpc_composes_serialized_append_in_one_transaction() -> None:
    assert ACCEPTANCE_MIGRATION.exists()
    sql = _normalized(ACCEPTANCE_MIGRATION)

    assert "create or replace function public.accept_chat_turn(" in sql
    for parameter in (
        "p_user_id uuid",
        "p_conversation_id uuid",
        "p_message_id uuid",
        "p_role text",
        "p_content text",
        "p_metadata jsonb",
        "p_created_at timestamptz",
        "p_preview text",
        "p_request_id text",
    ):
        assert parameter in sql
    assert "from public.append_conversation_message(" in sql
    assert "insert into public.chat_turn_lifecycles" in sql
    assert "insert into public.messages" not in sql
    assert "on conflict (turn_id)" in sql
    assert "v_lifecycle.request_id is distinct from p_request_id" in sql
    assert "v_appended.message is null" in sql
    for role in ("public", "anon", "authenticated"):
        assert f"from {role}" in sql
    assert "grant execute on function public.accept_chat_turn(" in sql
    assert "to service_role" in sql


def test_option_acceptance_and_terminal_finalization_are_single_transactions() -> None:
    assert LIFECYCLE_RPC_MIGRATION.exists()
    sql = _normalized(LIFECYCLE_RPC_MIGRATION)

    old_signature = (
        "public.accept_chat_turn( uuid, uuid, uuid, text, text, jsonb, "
        "timestamptz, text, text )"
    )
    assert f"drop function if exists {old_signature}" in sql

    for parameter in (
        "p_expected_source_assistant_id uuid",
        "p_expected_source_metadata jsonb",
        "p_option_id text",
        "p_replacement_values jsonb",
    ):
        assert parameter in sql
    assert "v_appended.source_message" in sql
    assert "source_message jsonb" in sql

    assert "create function public.finalize_chat_turn(" in sql
    finalizer = sql.split(
        "create function public.finalize_chat_turn(",
        1,
    )[1]
    assert finalizer.index("from public.chat_turn_lifecycles") < finalizer.index(
        "from public.append_conversation_message"
    )
    assert "for update" in finalizer
    assert "from public.append_conversation_message_settling_usage(" in finalizer
    assert "select public.transition_chat_turn(" in finalizer
    assert "raise exception 'chat-turn finalization conflict.'" in finalizer
    for role in ("public", "anon", "authenticated"):
        assert f"from {role}" in finalizer
    assert "grant execute on function public.finalize_chat_turn(" in finalizer
    assert "to service_role" in finalizer


def test_response_option_retry_matches_finalizer_lock_order() -> None:
    sql = _normalized(LIFECYCLE_RPC_MIGRATION)
    retry_branch = sql.split("if v_retry then", 1)[1].split(
        "else v_canonical_content := p_content",
        1,
    )[0]

    lifecycle_lock = retry_branch.index(
        "from public.chat_turn_lifecycles as l"
    )
    conversation_lock = retry_branch.index("from public.conversations as c")
    original_message_load = retry_branch.index("from public.messages as m")

    assert lifecycle_lock < conversation_lock < original_message_load


def test_forward_finalizer_migration_replays_exact_terminal_tuple_without_charge() -> None:
    assert IDEMPOTENT_FINALIZATION_MIGRATION.exists()
    sql = _normalized(IDEMPOTENT_FINALIZATION_MIGRATION)

    assert "create or replace function public.finalize_chat_turn(" in sql
    finalizer = sql.split(
        "create or replace function public.finalize_chat_turn(",
        1,
    )[1]
    lifecycle_lock = finalizer.index("from public.chat_turn_lifecycles as l")
    existing_message = finalizer.index("from public.messages as m")
    first_append = finalizer.index("from public.append_conversation_message")
    assert lifecycle_lock < existing_message < first_append
    assert "for update" in finalizer
    assert "v_turn.status in ('completed', 'recoverable_failed')" in finalizer
    assert "v_turn.assistant_message_id is distinct from p_message_id" in finalizer
    assert "v_turn.failure_code is distinct from p_failure_code" in finalizer
    assert "v_turn.retryable is distinct from v_retryable" in finalizer
    assert "v_existing.content is distinct from p_content" in finalizer
    assert (
        "v_existing.metadata is distinct from coalesce(p_metadata, '{}'::jsonb)"
        in finalizer
    )
    assert "return query select to_jsonb(v_existing)" in finalizer
    replay_branch = finalizer.split(
        "if v_turn.status in ('completed', 'recoverable_failed') then",
        1,
    )[1].split("end if;", 1)[0]
    assert "p_usage_resource" not in replay_branch
    assert "p_usage_limits" not in replay_branch

    for role in ("public", "anon", "authenticated"):
        assert "revoke all on function public.finalize_chat_turn(" in finalizer
        assert f"from {role}" in finalizer
    assert "grant execute on function public.finalize_chat_turn(" in finalizer
    assert "to service_role" in finalizer


def test_forward_migration_leaves_only_service_role_rpc_execution() -> None:
    sql = _normalized(LIFECYCLE_RPC_MIGRATION)

    for function_name in ("accept_chat_turn", "finalize_chat_turn"):
        for role in ("public", "anon", "authenticated"):
            assert f"revoke all on function public.{function_name}(" in sql
            assert f"from {role}" in sql
        assert f"grant execute on function public.{function_name}(" in sql
        assert "to service_role" in sql


def test_reconciliation_is_bounded_locked_database_time_recovery() -> None:
    sql = _normalized(ACCEPTANCE_MIGRATION)

    assert "create or replace function public.reconcile_stale_chat_turns(" in sql
    assert "v_now timestamptz := clock_timestamp()" in sql
    assert "coalesce(l.running_at, l.accepted_at)" in sql
    assert "v_now - interval '15 minutes'" in sql
    assert (
        "order by coalesce(l.running_at, l.accepted_at) asc, "
        "l.turn_id asc"
    ) in sql
    assert "limit 20" in sql
    assert "for update skip locked" in sql
    assert "v_turn.status not in ('accepted', 'running')" in sql
    assert "coalesce(v_turn.running_at, v_turn.accepted_at)" in sql

    assert "m.user_id = v_turn.user_id" in sql
    assert "m.conversation_id = v_turn.conversation_id" in sql
    assert "m.role = 'assistant'" in sql
    assert (
        "m.metadata #>> '{agent_runtime_turn,turn_id}' = "
        "v_turn.turn_id::text"
    ) in sql
    assert (
        "m.metadata #>> '{agent_runtime_turn,request_id}' = "
        "v_turn.request_id"
    ) in sql
    assert (
        "m.metadata #> '{agent_runtime_turn,terminal}' = 'true'::jsonb"
        in sql
    )
    assert (
        "m.metadata #>> '{agent_runtime_turn,status}' in "
        "('completed', 'recoverable_failed')"
    ) in sql
    assert (
        "m.metadata #>> '{agent_runtime_turn,status}' = 'completed'"
        in sql
    )
    assert (
        "m.metadata #>> '{agent_runtime_turn,status}' = "
        "'recoverable_failed'"
    ) in sql
    assert "m.metadata -> 'agent_runtime_turn' ? 'failure_code'" in sql
    assert (
        "jsonb_typeof( m.metadata #> "
        "'{agent_runtime_turn,failure_code}' ) in ('string', 'null')"
        in sql
    )
    assert "m.metadata -> 'agent_runtime_turn' ? 'retryable'" in sql
    assert (
        "jsonb_typeof( m.metadata #> '{agent_runtime_turn,retryable}' ) "
        "= 'boolean'"
    ) in sql
    assert "order by m.created_at asc" in sql
    assert "when 'recoverable_failed' then 0" in sql
    assert "m.id asc" in sql
    assert "select public.transition_chat_turn(" in sql
    assert "'turn_abandoned'" in sql
    assert "true" in sql
    assert "grant execute on function public.reconcile_stale_chat_turns(" in sql
    assert "to service_role" in sql


def test_gateway_source_uses_only_the_approved_server_boundaries() -> None:
    mixin = (
        ROOT / "src/argus/domain/chat_turn_lifecycle_gateway.py"
    ).read_text(encoding="utf-8")
    gateway = (ROOT / "src/argus/domain/supabase_gateway.py").read_text(
        encoding="utf-8"
    )

    assert 'self.client.rpc(\n            "accept_chat_turn"' in mixin
    assert 'self.client.rpc(\n            "finalize_chat_turn"' in mixin
    assert 'self.client.rpc(\n            "transition_chat_turn"' in mixin
    assert 'self.client.rpc(\n            "reconcile_stale_chat_turns"' in mixin
    assert 'table("chat_turn_lifecycles").insert' not in mixin
    assert 'table("chat_turn_lifecycles").update' not in mixin
    assert "ChatTurnLifecycleGatewayMixin" in gateway
