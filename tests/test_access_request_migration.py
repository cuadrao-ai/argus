from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations_archive"
    / "20260731080154_add_requested_private_alpha_access.sql"
)


def _sql() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_access_request_migration_reuses_allowlist_with_locked_constraints() -> None:
    sql = _sql()

    assert "create table" not in sql
    assert "alter table public.private_alpha_allowlist" in sql
    assert "role in ('admin', 'developer', 'user', 'requested')" in sql
    assert "add column if not exists language text not null default 'en'" in sql
    assert "language in ('en', 'es-419')" in sql


def test_access_request_migration_preserves_service_role_only_rls() -> None:
    sql = _sql()

    assert (
        "alter table public.private_alpha_allowlist enable row level security"
        in sql
    )
    assert (
        "revoke all on table public.private_alpha_allowlist "
        "from public, anon, authenticated" in sql
    )
    assert (
        "grant select, insert, update, delete on table "
        "public.private_alpha_allowlist to service_role" in sql
    )
    assert "create policy" not in sql
