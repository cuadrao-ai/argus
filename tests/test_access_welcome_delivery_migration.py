"""Static contract proof for the private access-welcome delivery migration."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _normalized_sql() -> str:
    migrations = sorted(
        (ROOT / "supabase" / "migrations_archive").glob("*_add_access_welcome_deliveries.sql")
    )
    assert len(migrations) == 1
    return re.sub(r"\s+", " ", migrations[0].read_text()).strip().lower()


def test_access_welcome_delivery_migration_is_private_and_once_only() -> None:
    sql = _normalized_sql()
    assert "create table public.private_alpha_access_welcome_deliveries" in sql
    assert "recipient_email text primary key" in sql
    assert "content_version = 'private-alpha-access-welcome/v1'" in sql
    assert "enable row level security" in sql
    assert "from public, anon, authenticated, service_role" in sql
    assert "grant select, insert" in sql
    assert "create policy" not in sql


def test_access_welcome_delivery_migration_guards_direct_activation() -> None:
    sql = _normalized_sql()
    assert "complete_private_alpha_access_welcome" in sql
    assert "security invoker" in sql
    assert "require_private_alpha_access_welcome_delivery" in sql
    assert "new.role = 'user'" in sql
    assert "new.disabled_at is null" in sql


def test_completion_preflights_existing_delivery_before_insert() -> None:
    sql = _normalized_sql()
    function_start = sql.index(
        "create or replace function public.complete_private_alpha_access_welcome"
    )
    function_end = sql.index("revoke all on function", function_start)
    function_sql = sql[function_start:function_end]
    delivery_lookup = (
        "select language, content_version, subject into v_delivery_language, "
        "v_delivery_content_version, v_delivery_subject from "
        "public.private_alpha_access_welcome_deliveries"
    )

    assert function_sql.index(delivery_lookup) < function_sql.index(
        "insert into public.private_alpha_access_welcome_deliveries"
    )
