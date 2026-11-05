"""Real-Postgres proof for import reconciliation.

Runs the shared cases (including the four-source purchase and concurrent
acceptance) against the migrations, plus what only the database enforces:
one import per recorded activity, no client writes, owner-only reads.
"""

import json
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL

from tests import test_financial_accounts_postgres as shared
from tests.ingestion.reconcile_cases import *  # noqa: F403
from tests.ingestion.reconcile_cases import plaid, submit
from tests.ingestion.reconcile_review_cases import *  # noqa: F403
from tests.ingestion.reconcile_world import build

pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)
psycopg = pytest.importorskip("psycopg")
psycopg_pool = pytest.importorskip("psycopg_pool")


@pytest.fixture
def backend():
    from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
    from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
    from argus.domain.recording.postgres_repository import (
        PostgresFinancialAccountRepository,
    )

    pool = psycopg_pool.ConnectionPool(shared.DSN, min_size=0, max_size=10, open=True)
    users = []
    with pool.connection() as connection:
        for _ in range(2):
            user = str(uuid4())
            connection.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (user, f"recon-{user}@example.test"),
            )
            users.append(user)
    try:
        yield (
            PostgresFinancialAccountRepository(pool),
            PostgresImportStore(pool),
            PostgresConnectionRepository(pool),
            users,
            pool,
        )
    finally:
        with pool.connection() as connection:
            connection.execute("delete from auth.users where id = any(%s)", (users,))
        pool.close()


@pytest.fixture
def world(backend):
    repository, store, connections, users, _ = backend
    return build(repository, store, connections, users[0])


@pytest.fixture
def other_world(backend):
    repository, store, connections, users, _ = backend
    return build(repository, store, connections, users[1])


def _as(cursor, user_id):  # noqa: ANN001
    cursor.execute("set local role authenticated")
    cursor.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (json.dumps({"sub": user_id, "role": "authenticated", "is_anonymous": False}),),
    )


def test_owner_reads_and_no_client_writes(world, other_world):
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "txn-1"))
    with psycopg.connect(shared.DSN) as connection:
        for user, expected in ((world.user, 1), (other_world.user, 0)):
            with connection.transaction(), connection.cursor() as cursor:
                _as(cursor, user)
                cursor.execute(
                    "select count(*) from public.financial_import_observations"
                )
                assert cursor.fetchone()[0] == expected
        for statement in (
            "update public.financial_import_events set state = 'accepted'",
            "delete from public.financial_import_observations",
            "insert into public.financial_import_account_links(user_id) values (gen_random_uuid())",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction(), connection.cursor() as cursor:
                    _as(cursor, world.user)
                    cursor.execute(statement)


def test_database_refuses_two_imports_for_one_record(world):
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "txn-1"), plaid(bank, "txn-2", amount="40"))
    activity = str(uuid4())
    with psycopg.connect(shared.DSN) as connection:
        with pytest.raises(psycopg.errors.UniqueViolation):
            with connection.transaction():
                connection.execute(
                    "update public.financial_import_events set state='accepted', activity_id=%s "
                    "where user_id=%s",
                    (activity, world.user),
                )
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                connection.execute(
                    "update public.financial_import_events set state='accepted' where user_id=%s",
                    (world.user,),
                )


def test_household_scope_is_shown_and_never_granted_by_importing(world, other_world):
    """Connecting and importing share nothing; an explicitly shared account
    is named as shared before the person confirms."""

    from tests.ingestion.reconcile_cases import new_account

    private, shared_card = new_account(world), new_account(world)
    bank = world.connect("plaid")
    submit(world, bank, plaid(bank, "txn-1"))
    with psycopg.connect(shared.DSN) as connection, connection.transaction():
        household = connection.execute(
            "insert into public.households(created_by, admin_user_id) values (%s, %s) returning id",
            (world.user, world.user),
        ).fetchone()[0]
        owner_member, other_member = (
            connection.execute(
                "insert into public.household_members(household_id, user_id) values (%s, %s) returning id",
                (household, user),
            ).fetchone()[0]
            for user in (world.user, other_world.user)
        )
        connection.execute(
            "insert into public.household_account_grants(household_id, account_id, owner_user_id,"
            " owner_membership_id, recipient_membership_id) values (%s, %s, %s, %s, %s)",
            (household, shared_card, world.user, owner_member, other_member),
        )
    [event] = world.recon.list(user_id=world.user, states=("open",), scope=PERSONAL)
    assert event["account_shared_with_household"] is None
    event = world.recon.resolve(
        user_id=world.user,
        event_id=event["id"],
        version=event["version"],
        changes={"account_id": private},
        scope=PERSONAL,
    )
    assert event["account_shared_with_household"] is False
    event = world.recon.resolve(
        user_id=world.user,
        event_id=event["id"],
        version=event["version"],
        changes={"account_id": shared_card},
        scope=PERSONAL,
    )
    assert event["account_shared_with_household"] is True
    with psycopg.connect(shared.DSN) as connection:
        grants = connection.execute(
            "select count(*) from public.household_account_grants where owner_user_id = %s",
            (world.user,),
        ).fetchone()[0]
        connection.execute("delete from public.households where id = %s", (household,))
    assert grants == 1  # importing created no grant
    assert (
        other_world.recon.list(user_id=other_world.user, states=("open",), scope=PERSONAL)
        == []
    )
