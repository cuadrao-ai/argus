"""Local rehearsal: clean install versus production-equivalent upgrade, synthetic data only.

Needs a throwaway local Postgres 17 (the Supabase CLI's local database container) and
psycopg. It creates and drops two databases named rehearsal_clean and rehearsal_upgrade
on that server; it never connects anywhere else.

    ARGUS_REHEARSAL_ADMIN_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \
    ARGUS_REHEARSAL_CONTAINER=supabase_db_<project> \
    poetry run python docs/reports/evidence/cuadrao-migration-rehearsal-20261007/rehearse_migration_upgrade.py

The container supplies the `auth` schema dump the migrations need.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from production_ledger_hashes import ROWS as PRODUCTION_ROWS  # noqa: E402

from scripts.ops import production_migration_gate as gate  # noqa: E402

ADMIN = os.environ["ARGUS_REHEARSAL_ADMIN_URL"]
CONTAINER = os.environ["ARGUS_REHEARSAL_CONTAINER"]
if urlsplit(ADMIN).hostname not in {"127.0.0.1", "localhost"}:
    raise SystemExit("the rehearsal runs only against a local database")
CANDIDATE = os.environ.get(
    "ARGUS_REHEARSAL_CANDIDATE", "93571e593e1677561e1dd38f63b6475574942e2d"
)
MAIN = os.environ.get("ARGUS_REHEARSAL_MAIN", "a9286b21886eb03df7a21f2f4b7d5e79af570679")
MISSING_OLDER = "20260505000001"  # group B: genuinely absent from production
MID_FILE_COMMIT = "20261003120001"  # commits inside itself (NOT VALID, commit, VALIDATE)


def url(database: str) -> str:
    parts = urlsplit(ADMIN)
    return urlunsplit(parts._replace(path=f"/{database}"))


def recreate(database: str) -> None:
    with psycopg.connect(ADMIN, autocommit=True) as admin:
        admin.execute(f"drop database if exists {database} with (force)")
        admin.execute(f"create database {database}")
    dump = subprocess.check_output(
        [
            "docker",
            "exec",
            CONTAINER,
            "pg_dump",
            "-U",
            "postgres",
            "-s",
            "-n",
            "auth",
            "postgres",
        ]
    )
    with psycopg.connect(url(database), autocommit=True) as connection:
        connection.execute("create schema if not exists extensions")
        for extension in ("pgcrypto", "vector", "pg_trgm"):
            connection.execute(
                f"create extension if not exists {extension} with schema extensions"
            )
        connection.execute(
            f'alter database {database} set search_path = "$user", public, extensions'
        )
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER,
            "psql",
            "-U",
            "postgres",
            "-d",
            database,
            "-q",
        ],
        input=dump,
        check=True,
        capture_output=True,
    )
    with psycopg.connect(url(database), autocommit=True) as connection:
        connection.execute("create schema if not exists supabase_migrations")
        connection.execute(
            "create table if not exists supabase_migrations.schema_migrations"
            " (version text primary key, statements text[], name text)"
        )


def run_file(
    connection: psycopg.Connection, migration: gate.CandidateMigration, record: bool
) -> None:
    """Run a file's statements as written (their own begin and commit included)."""

    for statement in migration.statements:
        connection.execute(statement)
    if record:
        connection.execute(
            "insert into supabase_migrations.schema_migrations (version, statements, name)"
            " values (%s, %s, %s)",
            (migration.version, list(migration.statements), migration.name),
        )


QUERIES = {
    "columns": "select table_schema||'.'||table_name, column_name, data_type, is_nullable, coalesce(column_default,'') from information_schema.columns where table_schema in ('public','argus_private')",
    "constraints": "select conrelid::regclass::text, conname, contype::text, pg_get_constraintdef(oid) from pg_constraint where connamespace in (select oid from pg_namespace where nspname in ('public','argus_private'))",
    "indexes": "select schemaname||'.'||tablename, indexname, indexdef from pg_indexes where schemaname in ('public','argus_private')",
    "triggers": "select tgrelid::regclass::text, tgname, pg_get_triggerdef(oid) from pg_trigger where not tgisinternal and tgrelid::regclass::text not like 'auth.%'",
    "functions": "select n.nspname||'.'||p.proname||'('||pg_get_function_identity_arguments(p.oid)||')', md5(p.prosrc), coalesce(p.proacl::text,'') from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname in ('public','argus_private')",
    "policies": "select schemaname||'.'||tablename, policyname, cmd, coalesce(qual,''), coalesce(with_check,'') from pg_policies where schemaname in ('public','argus_private')",
    "table_grants": "select table_schema||'.'||table_name, grantee, privilege_type from information_schema.role_table_grants where table_schema in ('public','argus_private') and grantee in ('anon','authenticated','service_role')",
    "rls": "select n.nspname||'.'||c.relname, c.relrowsecurity::text, c.relforcerowsecurity::text from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('public','argus_private') and c.relkind='r'",
}


def snapshot(database: str) -> dict[str, set[tuple[str, ...]]]:
    with psycopg.connect(url(database)) as connection:
        return {
            name: {tuple(map(str, row)) for row in connection.execute(sql).fetchall()}
            for name, sql in QUERIES.items()
        }


def gate_report(database: str) -> dict[str, object]:
    with psycopg.connect(url(database)) as connection:
        rows = connection.execute(
            "select version, coalesce(name,''), statements from supabase_migrations.schema_migrations order by version"
        ).fetchall()
    applied = [
        gate.AppliedMigration(
            version=r[0], name=r[1], statements=tuple(r[2]) if r[2] is not None else None
        )
        for r in rows
    ]
    return gate.build_migration_report(
        candidate_sha=CANDIDATE,
        target=gate.ProductionDatabaseTarget("rehearsal", "127.0.0.1"),
        candidate_migrations=gate.read_candidate_migrations(ROOT, CANDIDATE),
        applied_migrations=applied,
    )


def main() -> int:
    candidate = gate.read_candidate_migrations(ROOT, CANDIDATE)
    main_files = gate.read_candidate_migrations(ROOT, MAIN)
    print(f"candidate {CANDIDATE[:12]} | main {MAIN[:12]}")
    print(
        f"candidate files {len(candidate)} | main files {len(main_files)} | new {len(candidate) - len(main_files)}"
    )

    recreate("rehearsal_clean")
    with psycopg.connect(url("rehearsal_clean"), autocommit=True) as connection:
        for migration in candidate:
            run_file(connection, migration, True)
        rows = connection.execute(
            "select count(*) from supabase_migrations.schema_migrations"
        ).fetchone()[0]
    print(f"CLEAN INSTALL: applied {len(candidate)} files, ledger rows {rows}")

    recreate("rehearsal_upgrade")
    by_version = {m.version: m for m in candidate}
    by_name = {m.name: m for m in main_files}
    with psycopg.connect(url("rehearsal_upgrade"), autocommit=True) as connection:
        for migration in main_files:
            if migration.version != MISSING_OLDER:
                run_file(connection, migration, False)  # effects only, as in production
        for version, name, _count, _hash in PRODUCTION_ROWS:
            short = name.split("_", 1)[1] if name[:8].isdigit() and "_" in name else name
            match = by_version.get(version) or by_name.get(short)
            statements = (
                []
                if match is None
                else (
                    [match.source]
                    if version == "20260812183000"
                    else list(match.statements)
                )
            )
            connection.execute(
                "insert into supabase_migrations.schema_migrations (version, statements, name) values (%s, %s, %s)",
                (version, statements, name),
            )
    before = gate_report("rehearsal_upgrade")
    print(
        "UPGRADE gate before:",
        before["status"],
        before["stop_reasons"],
        "missing",
        len(before["missing_migrations"]),
    )
    pending = [m["version"] for m in before["missing_migrations"]]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(pending, handle)
    env = {**os.environ, "ARGUS_APPLY_DATABASE_URL": url("rehearsal_upgrade")}
    command = [
        sys.executable,
        str(ROOT / "scripts/ops/apply_approved_migrations.py"),
        "--candidate-sha",
        CANDIDATE,
        "--approved-file",
        handle.name,
        "--unrecorded",
        MISSING_OLDER,
        "--allow-mid-file-commit",
        MID_FILE_COMMIT,
        "--allow-host",
        "127.0.0.1",
        "--allow-database",
        "rehearsal_upgrade",
    ]
    subprocess.run(
        command, check=True, env=env, cwd=ROOT, stdout=subprocess.DEVNULL
    )  # plan only
    subprocess.run(
        [*command, "--execute"], check=True, env=env, cwd=ROOT, stdout=subprocess.DEVNULL
    )
    again = subprocess.run(
        [*command, "--execute"], env=env, cwd=ROOT, capture_output=True, text=True
    )
    print("second run refused:", again.returncode == 2, "|", again.stderr.strip())
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as empty:
        json.dump([], empty)
    repeat = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts/ops/apply_approved_migrations.py"),
            "--candidate-sha", CANDIDATE, "--approved-file", empty.name,
            "--unrecorded", MISSING_OLDER, "--allow-host", "127.0.0.1",
            "--allow-database", "rehearsal_upgrade", "--execute",
        ],
        env=env, cwd=ROOT, capture_output=True, text=True,
    )  # fmt: skip
    print("unrecorded repeat refused:", repeat.returncode == 2, "|", repeat.stderr.strip())
    after = gate_report("rehearsal_upgrade")
    print(
        "UPGRADE gate after:",
        after["status"],
        after["stop_reasons"],
        after["advisories"],
        "missing",
        len(after["missing_migrations"]),
        "content drift",
        len(after["content_drift"]),
        "name drift",
        len(after["name_drift"]),
    )
    with psycopg.connect(url("rehearsal_upgrade")) as connection:
        print(
            "ledger rows",
            connection.execute(
                "select count(*) from supabase_migrations.schema_migrations"
            ).fetchone()[0],
        )
    clean, upgraded = snapshot("rehearsal_clean"), snapshot("rehearsal_upgrade")
    differences = 0
    for name in clean:
        only_clean, only_upgrade = (
            clean[name] - upgraded[name],
            upgraded[name] - clean[name],
        )
        differences += len(only_clean) + len(only_upgrade)
        print(
            f"{name:13} clean {len(clean[name]):4} upgrade {len(upgraded[name]):4} differences {len(only_clean) + len(only_upgrade)}"
        )
    print("TOTAL CATALOG DIFFERENCES", differences)
    ok = (
        after["status"] == "pass" and differences == 0 and again.returncode == 2 and repeat.returncode == 2
    )
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
