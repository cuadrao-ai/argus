"""Exercise the private retention registry on the disposable migrated database."""

import os
from pathlib import Path

import pytest

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL is not configured")


def test_m1_retention_registry_contract():
    psycopg = pytest.importorskip("psycopg")
    sql = Path(__file__).with_name("sql").joinpath("m1_retention_registry.sql")
    with psycopg.connect(DSN, autocommit=True) as connection:
        connection.execute(sql.read_text())


def test_sweep_window_seed_replay_preserves_evidence_and_other_policies():
    psycopg = pytest.importorskip("psycopg")
    migration = (
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath(
            "supabase/migrations/20261018045500_retention_sweeps_24_month_window.sql"
        )
    )
    with psycopg.connect(DSN) as connection:
        try:
            policies = connection.execute(
                "select * from argus_private.retention_policies order by table_name"
            ).fetchall()
            sweep_policy = next(
                row for row in policies if row[0] == "argus_private.retention_sweeps"
            )
            assert "24 calendar months after finished_at" in sweep_policy[1]
            assert "finished_at + interval '24 months'" in sweep_policy[1]
            assert "installs no purge executor or schedule" in sweep_policy[1]
            assert sweep_policy[2] == (
                "supabase/migrations/20261018045500_retention_sweeps_24_month_window.sql; "
                "docs/reports/evidence/retention-sweeps-window/implementation.md"
            )
            connection.execute("set local role service_role")
            connection.execute(
                """insert into argus_private.retention_sweeps
                (id, table_name, started_at, finished_at, outcome, rows_affected, rule, basis)
                select '00000000-0000-4000-8000-000000000024', table_name,
                    '2024-02-29 12:00:00+00', '2024-02-29 12:00:00+00',
                    'dry_run', 0, rule, basis
                from argus_private.retention_policies
                where table_name = 'argus_private.retention_sweeps'"""
            )
            connection.execute("reset role")
            evidence = connection.execute(
                "select * from argus_private.retention_sweeps order by id"
            ).fetchall()
            for _ in range(2):
                connection.execute(migration.read_text())
                assert (
                    connection.execute(
                        "select * from argus_private.retention_policies order by table_name"
                    ).fetchall()
                    == policies
                )
                assert (
                    connection.execute(
                        "select * from argus_private.retention_sweeps order by id"
                    ).fetchall()
                    == evidence
                )
            assert connection.execute(
                """select finished_at + interval '24 months' =
                    timestamptz '2026-02-28 12:00:00+00'
                from argus_private.retention_sweeps
                where id = '00000000-0000-4000-8000-000000000024'"""
            ).fetchone() == (True,)
            table_comment = connection.execute(
                "select obj_description('argus_private.retention_sweeps'::regclass)"
            ).fetchone()[0]
            assert "argus_private.retention_policies" in table_comment
            assert "month" not in table_comment.lower()
        finally:
            connection.rollback()
