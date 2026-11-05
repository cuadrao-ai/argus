"""The Business read budget on real Postgres: three reads starting at once never
overshoot the cap, the month is the sum of its days, no client role can see the
counts, the rows go with their Business, and an emailed receipt's read spends
the same budget as every other channel."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from argus.api.documents import dispatch_preparation
from argus.domain.business.read_budget import PostgresReadBudget, ReadBudgetSettings
from argus.domain.owner_scope import BusinessSpace
from psycopg_pool import ConnectionPool

from tests import test_business_actions_postgres as shared
from tests import test_financial_accounts_postgres as accounts
from tests.document_reads_support import read_receipt
from tests.test_business_email_intake_postgres import deliver, receipts  # noqa: F401

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark

TABLE = "public.business_read_daily_usage"
NOON = datetime(2026, 11, 4, 16, tzinfo=timezone.utc)


@pytest.fixture
def pool():
    with ConnectionPool(accounts.DSN, min_size=0, max_size=6) as pool:
        yield pool


@pytest.fixture
def space(pool, users):  # noqa: ANN001
    business = str(uuid4())
    with pool.connection() as db:
        db.execute(
            "insert into public.spaces(id,kind,name,created_by) values(%s,'business','Budget',%s)",
            (business, users["owner"]),
        )
    try:
        yield business
    finally:
        with pool.connection() as db:
            db.execute(f"delete from {TABLE} where business_id=%s", (business,))
            db.execute("delete from public.spaces where id=%s", (business,))


def reads(pool, business: str) -> list[tuple]:  # noqa: ANN001
    with pool.connection() as db:
        return db.execute(
            f"select day, reads from {TABLE} where business_id=%s order by day",
            (business,),
        ).fetchall()


def test_three_reads_starting_at_once_never_overshoot_the_day_cap(pool, space):  # noqa: ANN001
    budget = PostgresReadBudget(pool, ReadBudgetSettings(per_day=2))
    barrier = Barrier(3)

    def charge(_: int) -> str | None:
        barrier.wait()
        return budget.charge(space, NOON)

    with ThreadPoolExecutor(max_workers=3) as threads:
        outcomes = list(threads.map(charge, range(3)))
    assert sorted(item or "charged" for item in outcomes) == [
        "business_read_budget_day",
        "charged",
        "charged",
    ]
    assert [row[1] for row in reads(pool, space)] == [2]


def test_the_month_is_the_sum_of_its_days_and_the_next_month_starts_clean(pool, space):  # noqa: ANN001
    budget = PostgresReadBudget(pool, ReadBudgetSettings(per_day=300, per_month=3))
    with pool.connection() as db:
        db.execute(
            f"insert into {TABLE}(business_id,day,reads) values (%s,'2026-11-01',2)",
            (space,),
        )
    assert budget.charge(space, NOON) is None
    assert budget.charge(space, NOON) == "business_read_budget_month"
    assert budget.charge(space, datetime(2026, 12, 1, 16, tzinfo=timezone.utc)) is None
    assert reads(pool, space) == [
        (datetime(2026, 11, 1).date(), 2),
        (NOON.date(), 1),
        (datetime(2026, 12, 1).date(), 1),
    ]


def test_the_day_turns_at_midnight_in_santo_domingo(pool, space):  # noqa: ANN001
    budget = PostgresReadBudget(pool, ReadBudgetSettings(per_day=1))
    # 03:59 UTC is still 23:59 the day before in Santo Domingo.
    late = datetime(2026, 11, 5, 3, 59, tzinfo=timezone.utc)
    assert budget.charge(space, late) is None
    assert budget.charge(space, late) == "business_read_budget_day"
    assert budget.charge(space, datetime(2026, 11, 5, 4, 1, tzinfo=timezone.utc)) is None
    assert [row[0].isoformat() for row in reads(pool, space)] == [
        "2026-11-04",
        "2026-11-05",
    ]


@contextmanager
def acting_as(db, role: str, user_id: str):  # noqa: ANN001
    with db.transaction(force_rollback=True):
        db.execute(f"set local role {role}")
        db.execute("select set_config('request.jwt.claim.sub',%s,true)", (user_id,))
        yield


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_no_client_role_reads_or_writes_the_counts(pool, space, users, role):  # noqa: ANN001
    PostgresReadBudget(pool, ReadBudgetSettings()).charge(space, NOON)
    with pool.connection() as db:
        assert db.execute(
            f"select relrowsecurity from pg_class where oid='{TABLE}'::regclass"
        ).fetchone() == (True,)
        for statement in (
            f"select * from {TABLE}",
            f"insert into {TABLE}(business_id,day,reads) values ('{space}','2026-11-04',0)",
            f"update {TABLE} set reads=0",
            f"delete from {TABLE}",
        ):
            with (
                acting_as(db, role, users["owner"]),
                pytest.raises(psycopg.errors.InsufficientPrivilege),
            ):
                db.execute(statement)


def test_the_counts_go_with_their_business(pool, users):  # noqa: ANN001
    business = str(uuid4())
    with pool.connection() as db:
        db.execute(
            "insert into public.spaces(id,kind,name,created_by) values(%s,'business','Gone',%s)",
            (business, users["owner"]),
        )
    PostgresReadBudget(pool, ReadBudgetSettings()).charge(business, NOON)
    assert reads(pool, business) == [(NOON.date(), 1)]
    with pool.connection() as db:
        db.execute("delete from public.spaces where id=%s", (business,))
    assert reads(pool, business) == []


@pytest.mark.owner_acts
def test_an_emailed_receipt_spends_the_same_budget(receipts):  # noqa: ANN001, F811
    documents, owner = receipts["documents"], receipts["owner"]
    scope = BusinessSpace(receipts["space"])
    budget = PostgresReadBudget(receipts["pool"], ReadBudgetSettings(per_day=1))
    documents.read_budget = budget
    assert budget.charge(receipts["space"], documents.hub.clock()) is None
    receipts["store"].upsert_sender(
        receipts["space"], "address", receipts["provider"].sender, "authorized"
    )
    attachment = deliver(receipts, {"spf": "pass", "dkim": "pass", "dmarc": "pass"})
    assert attachment is not None
    documents.queue(user_id=owner, connection_id=attachment, consent=True, scope=scope)

    async def read() -> None:
        await dispatch_preparation(documents, owner, attachment, scope=scope)
        # The dispatch only records the attempt; a puller takes it.
        await read_receipt(documents, owner, attachment)

    asyncio.run(read())
    draft = documents.get(user_id=owner, connection_id=attachment, scope=scope)
    assert (draft.status, draft.error_code) == ("saved", "business_read_budget_day")
    assert documents.extractor.calls == 0
