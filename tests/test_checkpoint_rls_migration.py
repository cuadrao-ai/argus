from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    REPO_ROOT / "supabase/migrations_archive/20260608041032_secure_checkpoint_rls.sql"
)
CHECKPOINT_TABLES = (
    "checkpoint_blobs",
    "checkpoint_migrations",
    "checkpoint_writes",
    "checkpoints",
)


def _migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8").lower()


def test_checkpoint_rls_migration_enables_rls_on_all_checkpoint_tables() -> None:
    sql = _migration_sql()

    for table in CHECKPOINT_TABLES:
        assert f"create table if not exists public.{table}" in sql
        assert f"alter table public.{table} enable row level security;" in sql


def test_checkpoint_rls_migration_does_not_grant_browser_roles_access() -> None:
    sql = _migration_sql()

    assert "create policy" not in sql
    assert "grant " not in sql
    assert "force row level security" not in sql
    for table in CHECKPOINT_TABLES:
        assert (
            f"revoke all on table public.{table} from public, anon, authenticated;"
            in sql
        )
