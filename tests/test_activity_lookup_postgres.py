"""Scoped activity reads on a disposable database; every seed rolls back."""

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from argus.domain.owner_scope import PERSONAL, BusinessSpace
from argus.domain.recording.money_reads import current_activities
from argus.domain.recording.postgres_repository import PostgresFinancialAccountRepository
from psycopg.types.json import Jsonb

from tests.test_financial_accounts_postgres import DSN

pytestmark = pytest.mark.skipif(
    not DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is required"
)


@pytest.fixture(params=["account", "owner", "unstated"])
def stored_activity(request):
    with psycopg.connect(DSN) as connection:
        with connection.transaction(force_rollback=True):
            connection.execute("set transaction isolation level repeatable read")
            user, space, account, activity, record = (str(uuid4()) for _ in range(5))
            connection.execute(
                "insert into auth.users(id,is_anonymous) values(%s,false)", (user,)
            )
            connection.execute(
                "insert into public.spaces(id,kind,name,created_by) values(%s,'business','Lookup fixture',%s)",
                (space, user),
            )
            account_backed = request.param == "account"
            if account_backed:
                connection.execute(
                    "insert into public.financial_accounts(id,user_id,type,currency,owner_space_id) values(%s,%s,'checking','DOP',%s)",
                    (account, user, space),
                )
            connection.execute(
                "insert into public.financial_records(id,account_id,user_id,record_kind,owner_space_id,funding,currency) values(%s,%s,%s,'expense',%s,%s,%s)",
                (
                    record,
                    account if account_backed else None,
                    user,
                    None if account_backed else space,
                    "owner_funds" if request.param == "owner" else None,
                    None if account_backed else "DOP",
                ),
            )
            connection.execute(
                "insert into public.financial_activity_groups(id,user_id,kind,current_revision) values(%s,%s,'expense',1)",
                (activity, user),
            )
            connection.execute(
                "insert into public.financial_activity_revisions(activity_id,user_id,revision) values(%s,%s,1)",
                (activity, user),
            )
            connection.execute(
                "insert into public.financial_record_revisions(record_id,user_id,revision,amount_minor,as_of,as_of_zone,details) values(%s,%s,1,%s,'2026-10-05T12:00:00Z','America/Santo_Domingo',%s)",
                (
                    record,
                    user,
                    -25050 if account_backed else 25050,
                    Jsonb(
                        {
                            "activity_id": activity,
                            "activity_revision": 1,
                            "role": "single",
                            "note": "Lookup fixture",
                        }
                    ),
                ),
            )
            connection.execute(
                "insert into public.financial_activity_memberships(activity_id,user_id,activity_revision,record_id,record_revision,role,record_owner_id) values(%s,%s,1,%s,1,'single',%s)",
                (activity, user, record, user),
            )

            @contextmanager
            def transaction_connection():
                yield connection

            repository = PostgresFinancialAccountRepository(
                SimpleNamespace(connection=transaction_connection)
            )
            yield (
                repository,
                connection,
                user,
                BusinessSpace(space),
                activity,
                record,
                account_backed,
            )


def test_lookup_returns_the_saved_activity_without_listing(stored_activity, monkeypatch):
    repository, _, user, scope, aid, _, _ = stored_activity
    expected = next(
        a
        for a in current_activities(repository.list_accounts(user_id=user, scope=scope))
        if a["activity_id"] == aid
    )
    monkeypatch.setattr(
        repository,
        "list_accounts",
        lambda **kwargs: pytest.fail("lookup listed all accounts"),
    )
    assert repository.get_activity(user_id=user, scope=scope, activity_id=aid) == expected


@pytest.mark.parametrize(
    "outside", ["missing", "business", "person", "personal", "malformed"]
)
def test_lookup_does_not_return_another_scope(stored_activity, outside):
    repository, _, user, scope, aid, _, _ = stored_activity
    if outside == "missing":
        aid = str(uuid4())
    elif outside == "business":
        scope = BusinessSpace(str(uuid4()))
    elif outside == "person":
        user = str(uuid4())
    elif outside == "personal":
        scope = PERSONAL
    else:
        aid = "not-an-id"
    assert repository.get_activity(user_id=user, scope=scope, activity_id=aid) is None


def test_reversed_activity_is_not_found(stored_activity):
    repository, connection, user, scope, aid, _, _ = stored_activity
    connection.execute(
        "update public.financial_activity_groups set reversed_at=now() where id=%s",
        (aid,),
    )
    assert repository.get_activity(user_id=user, scope=scope, activity_id=aid) is None


@pytest.mark.parametrize("stored_activity", ["account"], indirect=True)
def test_only_the_requested_record_is_hydrated(stored_activity, monkeypatch):
    repository, connection, user, scope, aid, record, _ = stored_activity
    unrelated = str(uuid4())
    connection.execute(
        "insert into public.financial_records(id,user_id,account_id,record_kind) select %s,user_id,account_id,'expense' from public.financial_records where id=%s",
        (unrelated, record),
    )
    connection.execute(
        "insert into public.financial_record_revisions(record_id,user_id,revision,amount_minor,as_of,as_of_zone,details) select %s,user_id,1,amount_minor,as_of,as_of_zone,details from public.financial_record_revisions where record_id=%s",
        (unrelated, record),
    )
    original = repository._load

    def load(*args, **kwargs):
        result = original(*args, **kwargs)
        assert [item.id for item in result.expenses] == [record]
        return result

    monkeypatch.setattr(repository, "_load", load)
    assert (
        repository.get_activity(user_id=user, scope=scope, activity_id=aid)["amount"]
        == "250.50"
    )


@pytest.mark.parametrize("stored_activity", ["account"], indirect=True)
def test_lookup_uses_the_accepted_group_revision(stored_activity):
    repository, connection, user, scope, aid, record, _ = stored_activity
    for revision in (2, 3):
        connection.execute(
            "insert into public.financial_record_revisions(record_id,user_id,revision,amount_minor,as_of,as_of_zone,details) "
            "select record_id,user_id,%s,-30000,as_of,as_of_zone,details || %s from public.financial_record_revisions where record_id=%s and revision=1",
            (revision, Jsonb({"activity_revision": revision}), record),
        )
    connection.execute(
        "insert into public.financial_activity_revisions(activity_id,user_id,revision) values(%s,%s,2)",
        (aid, user),
    )
    connection.execute(
        "insert into public.financial_activity_memberships(activity_id,user_id,activity_revision,record_id,record_revision,role,record_owner_id) values(%s,%s,2,%s,2,'single',%s)",
        (aid, user, record, user),
    )
    connection.execute(
        "update public.financial_activity_groups set current_revision=2 where id=%s",
        (aid,),
    )
    found = repository.get_activity(user_id=user, scope=scope, activity_id=aid)
    assert (found["revision"], found["amount"]) == (2, "300.00")
