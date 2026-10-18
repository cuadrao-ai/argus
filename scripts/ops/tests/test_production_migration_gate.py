from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

import scripts.ops.production_migration_gate as migration_gate
from scripts.ops.production_migration_gate import (
    AppliedMigration,
    CandidateMigration,
    MigrationGateError,
    ProductionDatabaseTarget,
    build_migration_report,
    classify_migration,
    load_gate_contract,
    main,
    read_applied_migrations,
    read_candidate_migrations,
    resolve_production_target,
    verify_landed_ref,
)


def test_missing_additive_migration_blocks_promotion() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        "create table public.release_marker (id uuid primary key);",
    )

    report = build_migration_report(
        candidate_sha="a" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[candidate],
        applied_migrations=[],
    )

    assert report["status"] == "blocked"
    assert report["stop_reasons"] == ["missing_candidate_migrations"]
    assert report["latest_applied_version"] is None
    assert report["human_approval"] == "required_before_out_of_band_apply"
    assert report["apply_result"] == "not_performed_by_gate"
    assert report["readback"] == "blocked_pending_schema_parity"
    assert report["missing_migrations"] == [
        {
            "version": "20260812000000",
            "name": "add_release_marker",
            "path": ("supabase/migrations/" "20260812000000_add_release_marker.sql"),
            "sha256": candidate.sha256,
            "statement_count": 1,
            "statements_sha256": candidate.statements_sha256,
            "classification": "additive",
            "classification_basis": "conservative_top_level_sql",
            "live_requirement": "human_review_and_live_readback",
        }
    ]


def test_exact_version_and_name_parity_passes() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        "create table public.release_marker (id uuid primary key);",
    )

    report = build_migration_report(
        candidate_sha="b" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[candidate],
        applied_migrations=[
            AppliedMigration(
                version="20260812000000",
                name="add_release_marker",
                statements=(candidate.source,),
            )
        ],
    )

    assert report["status"] == "pass"
    assert report["stop_reasons"] == []
    assert report["latest_applied_version"] == "20260812000000"
    assert report["human_approval"] == "not_required_no_gap"
    assert report["apply_result"] == "not_performed_by_gate"
    assert report["readback"] == "migration_ledger_parity_verified"
    assert report["missing_migrations"] == []
    assert report["applied_migrations"] == [
        {
            "version": "20260812000000",
            "name": "add_release_marker",
            "statement_count": 1,
            "statements_sha256": AppliedMigration(
                version=candidate.version,
                name=candidate.name,
                statements=(candidate.source,),
            ).statements_sha256,
        }
    ]


def test_post_reconciliation_applied_only_and_name_drift_both_block() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        "create table public.release_marker (id uuid primary key);",
    )

    report = build_migration_report(
        candidate_sha="c" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[candidate],
        applied_migrations=[
            AppliedMigration(
                version="20260812000000",
                name="different_name",
                statements=candidate.statements,
            ),
            AppliedMigration(
                version="20260813000000",
                name="production_only",
                statements=("select 1",),
            ),
        ],
    )

    assert report["status"] == "blocked"
    assert report["stop_reasons"] == [
        "unexpected_applied_migrations",
        "applied_migration_name_drift",
    ]
    assert report["advisories"] == []
    assert report["unexpected_applied_migrations"] == [
        {
            "version": "20260813000000",
            "name": "production_only",
            "statement_count": 1,
            "statements_sha256": AppliedMigration(
                version="20260813000000",
                name="production_only",
                statements=("select 1",),
            ).statements_sha256,
        }
    ]
    assert report["name_drift"] == [
        {
            "version": "20260812000000",
            "candidate_name": "add_release_marker",
            "applied_name": "different_name",
        }
    ]
    assert report["human_approval"] == "required_for_migration_drift_reconciliation"


def test_post_reconciliation_applied_only_migration_blocks_by_itself() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        "create table public.release_marker (id uuid primary key);",
    )

    report = build_migration_report(
        candidate_sha="2" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[candidate],
        applied_migrations=[
            AppliedMigration(
                version=candidate.version,
                name=candidate.name,
                statements=(candidate.source,),
            ),
            AppliedMigration(
                version="20260813000000",
                name="production_only",
                statements=("select 1",),
            ),
        ],
    )

    assert report["status"] == "blocked"
    assert report["stop_reasons"] == ["unexpected_applied_migrations"]
    assert report["advisories"] == []


def test_untracked_production_history_is_visible_without_blocking_coverage() -> None:
    candidates = [
        CandidateMigration.from_source(
            f"supabase/migrations/20260701{index:06d}_tracked_{index}.sql",
            f"create table public.tracked_{index} (id uuid primary key);",
        )
        for index in range(60)
    ]
    latest = CandidateMigration.from_source(
        "supabase/migrations/20260811210000_delete_withheld_backtest_result.sql",
        "create table public.delete_withheld_backtest_result (id uuid primary key);",
    )
    candidates.append(latest)
    historical_applied = [
        AppliedMigration(
            version=f"20260601{index:06d}",
            name=f"promotion_one_history_{index}",
            statements=(f"select {index}",),
        )
        for index in range(7)
    ]
    historical_mapped = [
        AppliedMigration(
            version=f"20260602{index:06d}",
            name=candidate.name,
            statements=(candidate.source,),
        )
        for index, candidate in enumerate(candidates[5:10])
    ]
    applied = [
        *historical_applied,
        *historical_mapped,
        *[
            AppliedMigration(
                version=candidate.version,
                name=candidate.name,
                statements=(candidate.source,),
            )
            for candidate in candidates[10:]
        ],
    ]

    report = build_migration_report(
        candidate_sha="d" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=candidates,
        applied_migrations=applied,
        reconciled_candidate_catalog_sha256=(
            migration_gate._candidate_catalog_sha256(candidates)
        ),
    )

    assert report["status"] == "pass"
    assert report["stop_reasons"] == []
    assert report["advisories"] == ["historical_migration_ledger_variance"]
    assert report["latest_candidate_version"] == "20260811210000"
    assert report["latest_applied_version"] == "20260811210000"
    assert report["missing_migrations"] == []
    variance = report["historical_ledger_variance"]
    assert variance["reconciled_through_version"] == "20260811210000"
    assert [mapping["candidate_version"] for mapping in variance["version_mappings"]] == [
        candidate.version for candidate in candidates[5:10]
    ]
    assert [
        migration["version"]
        for migration in variance["candidate_without_ledger_identity"]
    ] == [candidate.version for candidate in candidates[:5]]
    assert [
        migration["version"]
        for migration in variance["applied_without_candidate_identity"]
    ] == [migration.version for migration in historical_applied]
    assert variance["applied_row_surplus"] == 2
    assert report["readback"] == (
        "candidate_migration_coverage_verified_with_historical_ledger_variance"
    )
    assert report["counts"] == {
        "candidate": 61,
        "applied": 63,
        "missing": 0,
        "unexpected": 7,
        "name_drift": 0,
        "content_drift": 0,
        "historical_candidate_without_ledger_identity": 5,
        "historical_applied_without_candidate_identity": 7,
        "applied_row_surplus": 2,
    }
    assert report["migration_apply"] == "never"


def test_candidate_newer_than_reconciled_production_watermark_still_blocks() -> None:
    applied_candidate = CandidateMigration.from_source(
        "supabase/migrations/20260811210000_delete_withheld_backtest_result.sql",
        "create function public.delete_withheld() returns boolean "
        "language sql as 'select true';",
    )
    pending_candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812183000_guest_account_signup_handoffs.sql",
        "create table public.guest_account_signup_handoffs (id uuid primary key);",
    )

    report = build_migration_report(
        candidate_sha="e" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[applied_candidate, pending_candidate],
        applied_migrations=[
            AppliedMigration(
                version=applied_candidate.version,
                name=applied_candidate.name,
                statements=(applied_candidate.source,),
            )
        ],
    )

    assert report["status"] == "blocked"
    assert report["stop_reasons"] == ["missing_candidate_migrations"]
    assert [row["version"] for row in report["missing_migrations"]] == [
        pending_candidate.version
    ]


def test_backdated_candidate_change_breaks_the_reconciled_catalog_fingerprint() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260811000000_backdated_release_marker.sql",
        "create table public.backdated_release_marker (id uuid primary key);",
    )

    report = build_migration_report(
        candidate_sha="1" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[candidate],
        applied_migrations=[
            AppliedMigration(
                version=candidate.version,
                name=candidate.name,
                statements=(candidate.source,),
            )
        ],
        reconciled_candidate_catalog_sha256="0" * 64,
    )

    assert report["status"] == "blocked"
    assert report["stop_reasons"] == ["historical_candidate_catalog_drift"]
    assert (
        report["historical_ledger_variance"]["candidate_catalog_matches_reconciliation"]
        is False
    )


def test_historical_ledger_change_breaks_the_reconciled_production_fingerprint() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260811210000_delete_withheld_backtest_result.sql",
        "create function public.delete_withheld() returns boolean "
        "language sql as 'select true';",
    )
    applied = AppliedMigration(
        version=candidate.version,
        name=candidate.name,
        statements=(candidate.source,),
    )

    report = build_migration_report(
        candidate_sha="3" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[candidate],
        applied_migrations=[applied],
        reconciled_candidate_catalog_sha256=(
            migration_gate._candidate_catalog_sha256([candidate])
        ),
        reconciled_production_ledger_sha256="0" * 64,
    )

    assert report["status"] == "blocked"
    assert report["stop_reasons"] == ["historical_production_ledger_drift"]
    assert (
        report["historical_ledger_variance"]["production_ledger_matches_reconciliation"]
        is False
    )


def test_blank_applied_migration_name_blocks_as_drift() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        "create table public.release_marker (id uuid primary key);",
    )

    report = build_migration_report(
        candidate_sha="c" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[candidate],
        applied_migrations=[
            AppliedMigration(
                version="20260812000000",
                name="",
                statements=candidate.statements,
            ),
        ],
    )

    assert report["status"] == "blocked"
    assert report["stop_reasons"] == ["applied_migration_name_drift"]
    assert report["name_drift"] == [
        {
            "version": "20260812000000",
            "candidate_name": "add_release_marker",
            "applied_name": "",
        }
    ]


def test_same_version_and_name_with_different_statements_blocks() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        "create table public.release_marker (id uuid primary key);",
    )
    applied = AppliedMigration(
        version=candidate.version,
        name=candidate.name,
        statements=("create table public.release_marker (id text primary key)",),
    )

    report = build_migration_report(
        candidate_sha="d" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[candidate],
        applied_migrations=[applied],
        reconciled_candidate_catalog_sha256=(
            migration_gate._candidate_catalog_sha256([candidate])
        ),
    )

    assert report["status"] == "blocked"
    assert report["stop_reasons"] == ["applied_migration_content_drift"]
    assert report["content_drift"] == [
        {
            "version": candidate.version,
            "reason": "statements_mismatch",
            "candidate_statement_count": 1,
            "candidate_statements_sha256": candidate.statements_sha256,
            "applied_statement_count": 1,
            "applied_statements_sha256": applied.statements_sha256,
        }
    ]


def test_reconciled_historical_content_drift_is_reported_without_blocking() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260811210000_delete_withheld_backtest_result.sql",
        "create function public.delete_withheld() returns boolean "
        "language sql as 'select true';",
    )
    applied = AppliedMigration(
        version=candidate.version,
        name=candidate.name,
        statements=("select 'hand-reconciled history'",),
    )

    report = build_migration_report(
        candidate_sha="f" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[candidate],
        applied_migrations=[applied],
    )

    assert report["status"] == "pass"
    assert report["stop_reasons"] == []
    assert report["content_drift"] == []
    assert report["advisories"] == ["historical_migration_ledger_variance"]
    assert report["historical_ledger_variance"]["content_drift"] == [
        {
            "version": candidate.version,
            "reason": "statements_mismatch",
            "candidate_statement_count": len(candidate.statements),
            "candidate_statements_sha256": candidate.statements_sha256,
            "applied_statement_count": 1,
            "applied_statements_sha256": applied.statements_sha256,
        }
    ]


def test_missing_applied_statement_history_blocks_content_parity() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        "create table public.release_marker (id uuid primary key);",
    )

    report = build_migration_report(
        candidate_sha="e" * 40,
        target=ProductionDatabaseTarget(
            project_ref="production-ref",
            database_host="pooler.supabase.test",
        ),
        candidate_migrations=[candidate],
        applied_migrations=[
            AppliedMigration(
                version=candidate.version,
                name=candidate.name,
                statements=None,
            )
        ],
    )

    assert report["status"] == "blocked"
    assert report["stop_reasons"] == ["applied_migration_content_drift"]
    assert report["content_drift"][0]["reason"] == "missing_applied_statements"


def test_candidate_statement_history_matches_supabase_split_boundaries() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        """-- setup; comment
create table public.release_marker (
  label text default 'semi;colon',
  check (label <> ';')
);
create function public.marker() returns void language plpgsql as $body$
begin
  perform 'inside;body';
end;
$body$;
/* trailing; comment */ grant select on public.release_marker to authenticated;;
""",
    )

    assert candidate.statements == (
        """-- setup; comment
create table public.release_marker (
  label text default 'semi;colon',
  check (label <> ';')
)""",
        """create function public.marker() returns void language plpgsql as $body$
begin
  perform 'inside;body';
end;
$body$""",
        "/* trailing; comment */ grant select on public.release_marker to authenticated",
    )


def test_candidate_statement_history_keeps_begin_atomic_together() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        """create function public.marker() returns void language sql
begin atomic
  select 1;
  select 2;
end;
select 3;
""",
    )

    assert candidate.statements == (
        """create function public.marker() returns void language sql
begin atomic
  select 1;
  select 2;
end""",
        "select 3",
    )


def test_candidate_statement_history_accepts_unicode_dollar_tags() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        """create function public.marker() returns void language plpgsql as $café２$
begin
  perform 1;
end;
$café２$;
select 2;
""",
    )

    assert candidate.statements == (
        """create function public.marker() returns void language plpgsql as $café２$
begin
  perform 1;
end;
$café２$""",
        "select 2",
    )


def test_duplicate_candidate_version_fails_closed() -> None:
    first = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_first.sql",
        "create table public.first (id uuid primary key);",
    )
    second = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_second.sql",
        "create table public.second (id uuid primary key);",
    )

    with pytest.raises(MigrationGateError, match="duplicate candidate"):
        build_migration_report(
            candidate_sha="d" * 40,
            target=ProductionDatabaseTarget(
                project_ref="production-ref",
                database_host="pooler.supabase.test",
            ),
            candidate_migrations=[first, second],
            applied_migrations=[],
        )


def test_classifier_is_conservative_and_ignores_function_body_deletes() -> None:
    contract_source = """
    create or replace function public.remove_row() returns void
    language plpgsql as $$
    begin
        delete from public.rows;
    end;
    $$;
    """

    assert classify_migration(contract_source) == (
        "contract-replacing",
        "expand_contract_or_maintenance_required",
    )
    assert classify_migration(contract_source.replace(" or replace", "")) == (
        "additive",
        "human_review_and_live_readback",
    )
    assert classify_migration("alter table public.rows drop column legacy;") == (
        "destructive",
        "maintenance_backup_and_founder_approval_required",
    )
    assert classify_migration("drop table public.rows;") == (
        "destructive",
        "maintenance_backup_and_founder_approval_required",
    )
    assert classify_migration("drop function public.old_contract();") == (
        "destructive",
        "maintenance_backup_and_founder_approval_required",
    )
    assert classify_migration(
        "with old_rows as (select id from public.rows) "
        "delete from public.rows where id in (select id from old_rows);"
    ) == (
        "destructive",
        "maintenance_backup_and_founder_approval_required",
    )
    assert classify_migration("alter table public.rows enable row level security;") == (
        "contract-replacing",
        "expand_contract_or_maintenance_required",
    )


@pytest.mark.parametrize(
    "source",
    [
        "drop view public.old_view;",
        "drop policy old_policy on public.rows;",
        "alter table public.rows drop constraint rows_legacy_key;",
        (
            "alter table public.rows "
            "add column replacement text, drop constraint rows_legacy_key;"
        ),
    ],
)
def test_classifier_marks_top_level_object_removal_destructive(source: str) -> None:
    assert classify_migration(source) == (
        "destructive",
        "maintenance_backup_and_founder_approval_required",
    )


@pytest.mark.parametrize(
    "source",
    [
        "do $$ begin delete from public.rows; end $$;",
        "do $migration$ begin perform public.rebuild_rows(); end $migration$;",
    ],
)
def test_classifier_marks_executable_do_blocks_destructive(source: str) -> None:
    assert classify_migration(source) == (
        "destructive",
        "maintenance_backup_and_founder_approval_required",
    )


@pytest.mark.parametrize(
    ("source", "classification"),
    [
        (
            "alter table public.rows "
            "add column replacement text, add constraint replacement_present "
            "check (replacement is not null);",
            "additive",
        ),
        (
            "alter table public.rows add column replacement text, "
            "alter column existing set not null;",
            "contract-replacing",
        ),
        (
            "alter table public.rows add column replacement text, "
            "rename column existing to legacy;",
            "contract-replacing",
        ),
    ],
)
def test_classifier_only_accepts_pure_alter_table_add_actions(
    source: str,
    classification: str,
) -> None:
    expected_requirement = (
        "human_review_and_live_readback"
        if classification == "additive"
        else "expand_contract_or_maintenance_required"
    )

    assert classify_migration(source) == (classification, expected_requirement)


def test_candidate_and_contract_are_read_from_exact_git_commit(
    tmp_path: Path,
) -> None:
    repo, candidate_sha = _candidate_repo(tmp_path, project_ref="a" * 20)
    migration_path = (
        repo / "supabase" / "migrations" / "20260812000000_add_release_marker.sql"
    )
    migration_path.write_text(
        "drop table public.release_marker;\n",
        encoding="utf-8",
    )

    migrations = read_candidate_migrations(repo, candidate_sha)
    contract = load_gate_contract(repo, candidate_sha)

    assert [migration.source for migration in migrations] == [
        "create table public.release_marker (id uuid primary key);\n"
    ]
    assert contract.production_supabase_project_ref == "a" * 20
    with pytest.raises(MigrationGateError, match="40-character"):
        read_candidate_migrations(repo, candidate_sha[:8])


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql://postgres:secret@db.{ref}.supabase.co:5432/postgres",
        (
            "postgresql://postgres.{ref}:secret@"
            "aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        ),
    ),
)
def test_production_target_requires_the_checked_in_project_ref(
    database_url: str,
) -> None:
    project_ref = "a" * 20

    target = resolve_production_target(
        database_url.format(ref=project_ref),
        expected_project_ref=project_ref,
    )

    assert target.project_ref == project_ref
    assert "secret" not in repr(target)


def test_production_target_rejects_a_different_pooler_project_without_leaking() -> None:
    database_url = (
        "postgresql://postgres."
        f"{'b' * 20}:do-not-print@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    )

    with pytest.raises(MigrationGateError) as exc_info:
        resolve_production_target(
            database_url,
            expected_project_ref="a" * 20,
        )

    assert "does not match" in str(exc_info.value)
    assert "do-not-print" not in str(exc_info.value)


@pytest.mark.parametrize(
    "suffix",
    (
        "?host=db.evil.example",
        "?user=postgres.evil",
        "?options=-csearch_path%3Devil",
        "#host=db.evil.example",
    ),
)
def test_production_target_rejects_uri_target_overrides(suffix: str) -> None:
    project_ref = "a" * 20
    database_url = (
        f"postgresql://postgres:do-not-print@db.{project_ref}.supabase.co/postgres"
        f"{suffix}"
    )

    with pytest.raises(MigrationGateError, match="query parameters or fragments"):
        resolve_production_target(database_url, expected_project_ref=project_ref)


def test_applied_migrations_are_read_in_one_verified_read_only_transaction() -> None:
    calls: dict[str, Any] = {}

    class FakeCursor:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: str) -> None:
            self.queries.append(query)

        def fetchone(self) -> tuple[str]:
            return ("on",)

        def fetchall(self) -> list[tuple[object, ...]]:
            return [
                ("20260811000000", "first", ["create table first (id uuid)"]),
                ("20260812000000", "second", ["create table second (id uuid)"]),
            ]

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()
            self.closed = False

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

        def close(self) -> None:
            self.closed = True

    connection = FakeConnection()

    def connect(database_url: str, **kwargs: object) -> FakeConnection:
        calls["database_url"] = database_url
        calls["kwargs"] = kwargs
        return connection

    applied = read_applied_migrations(
        "postgresql://postgres:do-not-print@db.example.test/postgres",
        ssl_root_cert="/operator/production-supabase-ca.crt",
        connect_factory=connect,
    )

    assert applied == [
        AppliedMigration(
            version="20260811000000",
            name="first",
            statements=("create table first (id uuid)",),
        ),
        AppliedMigration(
            version="20260812000000",
            name="second",
            statements=("create table second (id uuid)",),
        ),
    ]
    assert calls["kwargs"] == {
        "application_name": "argus-production-migration-gate",
        "autocommit": True,
        "connect_timeout": 10,
        "gssencmode": "disable",
        "sslmode": "verify-full",
        "sslrootcert": "/operator/production-supabase-ca.crt",
    }
    assert connection.cursor_instance.queries == [
        "begin transaction read only",
        "show transaction_read_only",
        (
            "select version, coalesce(name, ''), statements "
            "from supabase_migrations.schema_migrations order by version"
        ),
        "rollback",
    ]
    assert connection.closed is True


def test_applied_migrations_fail_closed_when_read_only_is_not_established() -> None:
    class ReadWriteCursor:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def __enter__(self) -> ReadWriteCursor:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: str) -> None:
            self.queries.append(query)

        def fetchone(self) -> tuple[str]:
            return ("off",)

        def fetchall(self) -> list[tuple[object, ...]]:
            pytest.fail("the ledger must not be read without read-only proof")

    class ReadWriteConnection:
        def __init__(self) -> None:
            self.cursor_instance = ReadWriteCursor()

        def cursor(self) -> ReadWriteCursor:
            return self.cursor_instance

        def close(self) -> None:
            return None

    connection = ReadWriteConnection()

    with pytest.raises(
        MigrationGateError,
        match="production database transaction did not enter read-only mode",
    ):
        read_applied_migrations(
            "postgresql://postgres:do-not-print@db.example.test/postgres",
            ssl_root_cert="/operator/production-supabase-ca.crt",
            connect_factory=lambda *_args, **_kwargs: connection,
        )

    assert connection.cursor_instance.queries == [
        "begin transaction read only",
        "show transaction_read_only",
        "rollback",
    ]


def test_applied_migrations_reject_malformed_statement_history() -> None:
    connection = _FakeConnection(
        [("20260812000000", "release_marker", "not-a-text-array")]
    )

    with pytest.raises(MigrationGateError, match="malformed statements"):
        read_applied_migrations(
            "postgresql://postgres:do-not-print@db.example.test/postgres",
            ssl_root_cert="/operator/production-supabase-ca.crt",
            connect_factory=lambda *_args, **_kwargs: connection,
        )


def test_migration_apply_is_never_for_pass_block_and_advisory_reports() -> None:
    candidate = CandidateMigration.from_source(
        "supabase/migrations/20260812000000_add_release_marker.sql",
        "create table public.release_marker (id uuid primary key);",
    )
    target = ProductionDatabaseTarget(
        project_ref="production-ref",
        database_host="pooler.supabase.test",
    )
    reports = [
        build_migration_report(
            candidate_sha="a" * 40,
            target=target,
            candidate_migrations=[candidate],
            applied_migrations=[],
        ),
        build_migration_report(
            candidate_sha="b" * 40,
            target=target,
            candidate_migrations=[candidate],
            applied_migrations=[
                AppliedMigration(
                    version=candidate.version,
                    name=candidate.name,
                    statements=candidate.statements,
                )
            ],
        ),
        build_migration_report(
            candidate_sha="c" * 40,
            target=target,
            candidate_migrations=[candidate],
            applied_migrations=[
                AppliedMigration(
                    version="20260811000000",
                    name="manual_repair",
                    statements=("select 1",),
                ),
                AppliedMigration(
                    version=candidate.version,
                    name=candidate.name,
                    statements=candidate.statements,
                ),
            ],
        ),
    ]

    assert {report["status"] for report in reports} == {"blocked", "pass"}
    assert {report["migration_apply"] for report in reports} == {"never"}


@pytest.mark.skipif(
    not os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip(),
    reason="disposable PostgreSQL is not configured",
)
def test_gate_read_only_transaction_rejects_a_real_postgres_write() -> None:
    import psycopg

    connection = psycopg.connect(
        os.environ["ARGUS_DISPOSABLE_DATABASE_URL"],
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            migration_gate._begin_read_only_transaction(cursor)
            try:
                with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                    cursor.execute(
                        "create table public.argus_migration_gate_write_probe "
                        "(id integer)"
                    )
            finally:
                cursor.execute("rollback")
    finally:
        connection.close()


@pytest.mark.skipif(
    not os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip(),
    reason="disposable PostgreSQL is not configured",
)
def test_gate_fails_closed_when_real_postgres_cannot_begin_read_only() -> None:
    import psycopg

    connection = psycopg.connect(
        os.environ["ARGUS_DISPOSABLE_DATABASE_URL"],
        autocommit=False,
    )
    with connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.UndefinedTable):
            cursor.execute("select * from public.argus_migration_gate_missing_fixture")

    with pytest.raises(
        MigrationGateError,
        match="production migration ledger read failed",
    ) as error:
        read_applied_migrations(
            "postgresql://postgres:do-not-print@db.example.test/postgres",
            ssl_root_cert="/operator/production-supabase-ca.crt",
            connect_factory=lambda *_args, **_kwargs: connection,
        )

    assert isinstance(error.value.__cause__, psycopg.errors.InFailedSqlTransaction)


def test_cli_writes_a_complete_blocking_report_without_leaking_credentials(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, candidate_sha = _candidate_repo(tmp_path, project_ref="a" * 20)
    output_path = tmp_path / "evidence" / "migration-gate.json"
    ssl_root_cert = _ssl_root_cert(tmp_path)
    connection = _FakeConnection([])

    exit_code = main(
        ["--candidate-sha", candidate_sha, "--output", str(output_path)],
        environ={
            "ARGUS_PRODUCTION_DATABASE_URL": (
                "postgresql://postgres."
                f"{'a' * 20}:do-not-print@"
                "aws-0-us-east-1.pooler.supabase.com:6543/postgres"
            ),
            "ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT": str(ssl_root_cert),
        },
        repo_root=repo,
        connect_factory=lambda *_args, **_kwargs: connection,
        reconciled_candidate_catalog_sha256=None,
        reconciled_production_ledger_sha256=None,
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    captured = capsys.readouterr()
    assert exit_code == 1
    assert json.loads(captured.out) == report
    assert report["status"] == "blocked"
    assert report["candidate_sha"] == candidate_sha
    assert report["counts"] == {
        "applied": 0,
        "candidate": 1,
        "content_drift": 0,
        "missing": 1,
        "name_drift": 0,
        "unexpected": 0,
        "historical_candidate_without_ledger_identity": 0,
        "historical_applied_without_candidate_identity": 0,
        "applied_row_surplus": 0,
    }
    assert report["database_access"] == "read_only"
    assert report["database_transport"] == "tls_verify_full"
    assert report["migration_apply"] == "never"
    assert "do-not-print" not in captured.out
    assert "do-not-print" not in output_path.read_text(encoding="utf-8")


def test_cli_passes_only_when_the_production_ledger_matches(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, candidate_sha = _candidate_repo(tmp_path, project_ref="a" * 20)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
    subprocess.run(
        ["git", "push", "-q", "origin", "HEAD:main"],
        cwd=repo,
        check=True,
    )
    output_path = tmp_path / "migration-gate.json"
    ssl_root_cert = _ssl_root_cert(tmp_path)
    connection = _FakeConnection(
        [
            (
                "20260812000000",
                "add_release_marker",
                ["create table public.release_marker (id uuid primary key)"],
            ),
        ]
    )

    exit_code = main(
        [
            "--candidate-sha",
            candidate_sha,
            "--verify-landed-ref",
            "origin/main",
            "--output",
            str(output_path),
        ],
        environ={
            "ARGUS_PRODUCTION_DATABASE_URL": (
                "postgresql://postgres:do-not-print@"
                f"db.{'a' * 20}.supabase.co:5432/postgres"
            ),
            "ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT": str(ssl_root_cert),
        },
        repo_root=repo,
        connect_factory=lambda *_args, **_kwargs: connection,
        reconciled_candidate_catalog_sha256=None,
        reconciled_production_ledger_sha256=None,
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["status"] == "pass"
    assert report["missing_migrations"] == []
    assert report["landing_verification"] == {
        "status": "verified",
        "remote_ref": "origin/main",
        "resolved_sha": candidate_sha,
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == report


def test_cli_requires_a_readable_absolute_production_ca_before_connecting(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, candidate_sha = _candidate_repo(tmp_path, project_ref="a" * 20)
    empty_ca = tmp_path / "empty-ca.crt"
    empty_ca.touch()

    for ssl_root_cert in (
        "",
        "relative-ca.crt",
        str(tmp_path / "missing-ca.crt"),
        str(empty_ca),
    ):
        exit_code = main(
            [
                "--candidate-sha",
                candidate_sha,
                "--output",
                str(tmp_path / "migration-gate.json"),
            ],
            environ={
                "ARGUS_PRODUCTION_DATABASE_URL": (
                    "postgresql://postgres:do-not-print@"
                    f"db.{'a' * 20}.supabase.co:5432/postgres"
                ),
                "ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT": ssl_root_cert,
            },
            repo_root=repo,
            connect_factory=lambda *_args, **_kwargs: pytest.fail(
                "database access must not start"
            ),
        )

        report = json.loads(capsys.readouterr().out)
        assert exit_code == 2
        assert report["error"] == (
            "ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT must be an absolute " "readable file"
        )


def test_verify_landed_ref_fetches_the_remote_before_comparing(tmp_path: Path) -> None:
    repo, candidate_sha = _candidate_repo(tmp_path, project_ref="a" * 20)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
    subprocess.run(
        ["git", "push", "-q", "origin", "HEAD:main"],
        cwd=repo,
        check=True,
    )

    assert verify_landed_ref(repo, candidate_sha, "origin/main") == candidate_sha


def test_cli_blocks_when_the_fresh_landed_ref_differs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, candidate_sha = _candidate_repo(tmp_path, project_ref="a" * 20)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
    subprocess.run(
        ["git", "push", "-q", "origin", "HEAD:main"],
        cwd=repo,
        check=True,
    )
    (repo / "README.md").write_text("advanced remote\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "advance remote"], cwd=repo, check=True)
    subprocess.run(
        ["git", "push", "-q", "origin", "HEAD:main"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "checkout", "-q", candidate_sha], cwd=repo, check=True)

    exit_code = main(
        [
            "--candidate-sha",
            candidate_sha,
            "--verify-landed-ref",
            "origin/main",
            "--output",
            str(tmp_path / "migration-gate.json"),
        ],
        environ={
            "ARGUS_PRODUCTION_DATABASE_URL": (
                "postgresql://postgres:do-not-print@"
                f"db.{'a' * 20}.supabase.co:5432/postgres"
            )
        },
        repo_root=repo,
        connect_factory=lambda *_args, **_kwargs: pytest.fail(
            "database access must not start"
        ),
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert report["error"] == "landed ref does not match the candidate SHA"


def test_cli_blocks_when_the_landed_ref_cannot_be_fetched(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, candidate_sha = _candidate_repo(tmp_path, project_ref="a" * 20)
    subprocess.run(
        ["git", "remote", "add", "origin", str(tmp_path / "missing.git")],
        cwd=repo,
        check=True,
    )

    exit_code = main(
        [
            "--candidate-sha",
            candidate_sha,
            "--verify-landed-ref",
            "origin/main",
            "--output",
            str(tmp_path / "migration-gate.json"),
        ],
        environ={
            "ARGUS_PRODUCTION_DATABASE_URL": (
                "postgresql://postgres:do-not-print@"
                f"db.{'a' * 20}.supabase.co:5432/postgres"
            )
        },
        repo_root=repo,
        connect_factory=lambda *_args, **_kwargs: pytest.fail(
            "database access must not start"
        ),
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert report["error"] == "Git candidate read failed: git fetch"


def test_cli_redacts_database_failures_and_writes_a_blocked_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, candidate_sha = _candidate_repo(tmp_path, project_ref="a" * 20)
    output_path = tmp_path / "migration-gate.json"
    ssl_root_cert = _ssl_root_cert(tmp_path)

    def fail_connect(*_args: object, **_kwargs: object) -> _FakeConnection:
        raise RuntimeError("driver failed with password do-not-print")

    exit_code = main(
        ["--candidate-sha", candidate_sha, "--output", str(output_path)],
        environ={
            "ARGUS_PRODUCTION_DATABASE_URL": (
                "postgresql://postgres:do-not-print@"
                f"db.{'a' * 20}.supabase.co:5432/postgres"
            ),
            "ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT": str(ssl_root_cert),
        },
        repo_root=repo,
        connect_factory=fail_connect,
    )

    rendered = capsys.readouterr().out
    report = json.loads(rendered)
    assert exit_code == 2
    assert report["status"] == "blocked"
    assert report["stop_reasons"] == ["gate_execution_failed"]
    assert report["error"] == "production migration ledger read failed"
    assert report["migration_apply"] == "never"
    assert "do-not-print" not in rendered
    assert output_path.read_text(encoding="utf-8") == rendered


def test_cli_rejects_a_candidate_that_is_not_the_clean_checkout_head(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, candidate_sha = _candidate_repo(tmp_path, project_ref="a" * 20)
    (repo / "README.md").write_text("new head\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "advance fixture"],
        cwd=repo,
        check=True,
    )
    output_path = tmp_path / "migration-gate.json"

    exit_code = main(
        ["--candidate-sha", candidate_sha, "--output", str(output_path)],
        environ={
            "ARGUS_PRODUCTION_DATABASE_URL": (
                "postgresql://postgres:do-not-print@"
                f"db.{'a' * 20}.supabase.co:5432/postgres"
            )
        },
        repo_root=repo,
        connect_factory=lambda *_args, **_kwargs: pytest.fail(
            "database access must not start"
        ),
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert report["error"] == "checkout HEAD does not match the candidate SHA"


def test_cli_rejects_tracked_changes_before_database_access(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, candidate_sha = _candidate_repo(tmp_path, project_ref="a" * 20)
    (repo / "render.yaml").write_text("dirty checkout\n", encoding="utf-8")
    output_path = tmp_path / "migration-gate.json"

    exit_code = main(
        ["--candidate-sha", candidate_sha, "--output", str(output_path)],
        environ={
            "ARGUS_PRODUCTION_DATABASE_URL": (
                "postgresql://postgres:do-not-print@"
                f"db.{'a' * 20}.supabase.co:5432/postgres"
            )
        },
        repo_root=repo,
        connect_factory=lambda *_args, **_kwargs: pytest.fail(
            "database access must not start"
        ),
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert report["error"] == "checkout has tracked changes outside the candidate"


def _candidate_repo(tmp_path: Path, *, project_ref: str) -> tuple[Path, str]:
    repo = tmp_path / "candidate-repo"
    migration_path = (
        repo / "supabase" / "migrations" / "20260812000000_add_release_marker.sql"
    )
    render_path = repo / "render.yaml"
    migration_path.parent.mkdir(parents=True)
    migration_path.write_text(
        "create table public.release_marker (id uuid primary key);\n",
        encoding="utf-8",
    )
    render_path.write_text(
        "services:\n"
        "  - type: web\n"
        "    name: argus-api\n"
        "    envVars:\n"
        "      - key: SUPABASE_URL\n"
        f"        value: https://{project_ref}.supabase.co\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "migration-gate@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Migration Gate Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "test fixture"],
        cwd=repo,
        check=True,
    )
    candidate_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, candidate_sha


def _ssl_root_cert(tmp_path: Path) -> Path:
    certificate = tmp_path / "production-supabase-ca.crt"
    certificate.write_text("test-only production CA\n", encoding="utf-8")
    return certificate


class _FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _query: str) -> None:
        return None

    def fetchone(self) -> tuple[str]:
        return ("on",)

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class _FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._cursor = _FakeCursor(rows)

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def close(self) -> None:
        return None
