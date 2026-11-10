"""Static contract proof for the access-welcome claim and enforcement SQL.

The terminal behavior lives in the scoped-enforcement migration; the earlier
claim migration remains as applied history and only its table shape is pinned
here.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _normalized_sql(glob: str) -> str:
    migrations = sorted((ROOT / "supabase" / "migrations_archive").glob(glob))
    assert len(migrations) == 1
    return re.sub(r"\s+", " ", migrations[0].read_text()).strip().lower()


def _claim_history_sql() -> str:
    return _normalized_sql("*_claim_access_welcome_delivery.sql")


def _enforcement_sql() -> str:
    return _normalized_sql("*_scope_access_welcome_enforcement.sql")


def test_claim_migration_is_private_fixed_and_service_owned() -> None:
    sql = _claim_history_sql()

    assert "create table public.private_alpha_access_welcome_claims" in sql
    assert "recipient_email text primary key" in sql
    assert "claim_token uuid not null unique" in sql
    assert "claimed_at timestamptz not null default now()" in sql
    assert "content_version = 'private-alpha-access-welcome/v1'" in sql
    assert "enable row level security" in sql
    assert "from public, anon, authenticated, service_role" in sql
    assert "create policy" not in sql


def test_enforcement_removes_the_freeze_and_the_consumed_state() -> None:
    sql = _enforcement_sql()

    assert (
        "drop trigger guard_private_alpha_access_welcome_claim "
        "on public.private_alpha_allowlist"
    ) in sql
    assert "drop function public.guard_private_alpha_access_welcome_claim()" in sql
    assert (
        "alter table public.private_alpha_access_welcome_claims "
        "drop column consumed_at"
    ) in sql


def test_delivery_guard_is_scoped_to_the_promotion_edge() -> None:
    sql = _enforcement_sql()
    function_sql = sql.split(
        "create or replace function "
        "public.require_private_alpha_access_welcome_delivery",
        1,
    )[1].split("create or replace function", 1)[0]

    assert "old.role = 'requested'" in function_sql
    assert "new.role = 'user'" in function_sql
    assert "new.disabled_at is null" in function_sql
    assert "old.disabled_at" not in function_sql
    assert "old.role is distinct from 'user'" not in function_sql


def test_claim_rpc_locks_and_revalidates_before_allowing_send() -> None:
    sql = _enforcement_sql()
    function_sql = sql.split(
        "create or replace function public.claim_private_alpha_access_welcome", 1
    )[1].split("revoke all on function", 1)[0]

    assert "security definer" in function_sql
    assert "set search_path = ''" in function_sql
    assert "from public.private_alpha_allowlist" in function_sql
    assert "for update" in function_sql
    assert "v_role is distinct from 'requested'" in function_sql
    assert "v_disabled_at is not null" in function_sql
    assert "p_language is distinct from v_language" in function_sql
    assert "interval '24 hours'" in function_sql
    assert "consumed_at" not in function_sql


def test_completion_upserts_delivery_deletes_claim_then_promotes() -> None:
    sql = _enforcement_sql()
    function_sql = sql.split(
        "create or replace function public.complete_private_alpha_access_welcome", 1
    )[1].split("revoke all on function", 1)[0]

    assert "p_claim_token uuid" in function_sql
    assert "for update" in function_sql
    upsert_index = function_sql.index(
        "insert into public.private_alpha_access_welcome_deliveries"
    )
    assert "on conflict (recipient_email) do update" in function_sql
    delete_index = function_sql.index(
        "delete from public.private_alpha_access_welcome_claims"
    )
    promote_index = function_sql.index("update public.private_alpha_allowlist")
    assert upsert_index < delete_index < promote_index
    assert "set consumed_at" not in function_sql
    # A null-token replay succeeds only for an already-active user with no
    # open claim, so a fresh grant can never be silently promoted.
    assert "if v_claim_found or v_role is distinct from 'user'" in function_sql


def test_recovery_rpcs_are_service_role_reachable() -> None:
    sql = _enforcement_sql()

    assert (
        "create or replace function "
        "public.release_expired_private_alpha_access_welcome_claims"
    ) in sql
    assert "interval '48 hours'" in sql
    assert (
        "grant execute on function "
        "public.release_expired_private_alpha_access_welcome_claims( "
        "timestamptz ) to service_role"
    ) in sql
    assert (
        "create or replace function "
        "public.delete_private_alpha_access_welcome_artifacts"
    ) in sql
    assert (
        "grant execute on function "
        "public.delete_private_alpha_access_welcome_artifacts( "
        "text ) to service_role"
    ) in sql
    artifacts_sql = sql.split(
        "create or replace function "
        "public.delete_private_alpha_access_welcome_artifacts",
        1,
    )[1]
    refusal_index = artifacts_sql.index("from public.private_alpha_allowlist")
    assert refusal_index < artifacts_sql.index(
        "delete from public.private_alpha_access_welcome_claims"
    )
