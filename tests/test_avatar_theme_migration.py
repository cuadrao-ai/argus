from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_avatar_theme_migration_defaults_to_a_fixed_token_and_restricts_guest_writes():
    migrations = sorted((ROOT / "supabase" / "migrations_archive").glob("*avatar_theme*.sql"))

    assert len(migrations) == 1
    migration = migrations[0].read_text(encoding="utf-8")

    assert "avatar_theme" in migration
    assert "default 'ocean'" in migration
    assert "profiles_registered_avatar_theme_select" in migration
    assert "profiles_registered_avatar_theme_update" in migration
    assert "(select auth.uid()) = id" in migration
    assert "((select auth.jwt()) ->> 'is_anonymous') is distinct from 'true'" in migration
    assert "grant select (id, avatar_theme), update (avatar_theme)" in migration
