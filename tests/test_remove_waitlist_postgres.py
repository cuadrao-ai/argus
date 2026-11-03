"""Real-Postgres proof that the waitlist removal migration drops cleanly and refuses to lose rows."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from faker import Faker

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)
psycopg = pytest.importorskip("psycopg")
fake = Faker()

MIGRATION = (
    Path(__file__)
    .resolve()
    .parents[1]
    .joinpath("supabase/migrations/20261103010000_remove_waitlist.sql")
    .read_text()
)
TABLE = "public.cuadrao_early_access_signups"
JOBS = ("cuadrao-waitlist-retention", "cuadrao-waitlist-reminders")

LEFTOVERS = """
select
    (select count(*) from pg_class where oid = to_regclass('public.cuadrao_early_access_signups')),
    (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'cuadrao_scheduler' or p.proname like 'cuadrao_waitlist\\_%'),
    (select count(*) from pg_namespace where nspname = 'cuadrao_scheduler'),
    (select count(*) from cron.job where jobname like 'cuadrao-waitlist-%'),
    (select count(*) from argus_private.retention_policies
        where table_name = 'public.cuadrao_early_access_signups')
"""


@pytest.fixture()
def connection():
    with psycopg.connect(DSN) as conn:
        try:
            yield conn
        finally:
            conn.rollback()


def _restore_waitlist_stand_in(connection, *, rows: int, jobs: tuple[str, ...]) -> None:
    connection.execute(f"create table {TABLE} (email text)")
    for _ in range(rows):
        connection.execute(f"insert into {TABLE} values (%s)", (fake.email(),))
    connection.execute("create schema cuadrao_scheduler")
    connection.execute(
        "create function cuadrao_scheduler.purge_waitlist() returns integer "
        "language sql as 'select 1'"
    )
    connection.execute(
        "create function public.cuadrao_waitlist_purge(integer) returns integer "
        "language sql as 'select 1'"
    )
    for job in jobs:
        connection.execute("select cron.schedule(%s, '* * * * *', 'select 1')", (job,))
    connection.execute(
        "insert into argus_private.retention_policies values (%s, 'rule', 'basis')",
        ("public.cuadrao_early_access_signups",),
    )


def test_the_migrated_database_holds_none_of_the_waitlist(connection):
    assert connection.execute(LEFTOVERS).fetchone() == (0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "jobs", [JOBS, JOBS[:1], ()], ids=["both jobs", "one job gone", "both jobs gone"]
)
def test_an_empty_table_is_removed_with_everything_that_hangs_on_it(connection, jobs):
    _restore_waitlist_stand_in(connection, rows=0, jobs=jobs)
    assert connection.execute(LEFTOVERS).fetchone() == (1, 2, 1, len(jobs), 1)

    connection.execute(MIGRATION)

    assert connection.execute(LEFTOVERS).fetchone() == (0, 0, 0, 0, 0)


@pytest.mark.parametrize("rows", [1, 3])
def test_a_table_with_any_row_is_refused_and_nothing_changes(connection, rows):
    _restore_waitlist_stand_in(connection, rows=rows, jobs=JOBS)
    connection.execute("savepoint before_removal")

    with pytest.raises(
        psycopg.errors.RaiseException, match="Refusing to remove the waitlist"
    ):
        connection.execute(MIGRATION)
    connection.execute("rollback to savepoint before_removal")

    assert connection.execute(LEFTOVERS).fetchone() == (1, 2, 1, 2, 1)
    assert connection.execute(f"select count(*) from {TABLE}").fetchone() == (rows,)


def test_a_second_run_is_a_no_op(connection):
    connection.execute(MIGRATION)
    before = connection.execute(LEFTOVERS).fetchone()

    connection.execute(MIGRATION)

    assert connection.execute(LEFTOVERS).fetchone() == before == (0, 0, 0, 0, 0)
