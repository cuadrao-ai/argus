from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from argus.domain.business.notifications.store import (
    PostgresNotificationStore,
    put,
    resolve,
)
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared

pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def pool():
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as pool:
        yield pool


@pytest.fixture
def identities(pool):
    business, recipient, other, subject = (str(uuid4()) for _ in range(4))
    with pool.connection() as db:
        db.execute("insert into auth.users(id) values(%s),(%s)", (recipient, other))
        db.execute(
            "insert into public.spaces(id,kind,name,created_by) values(%s,'business','Test',%s)",
            (business, recipient),
        )
        db.execute(
            "insert into public.business_client_grants"
            "(space_id,grantee_id,issuer_id,business_role,capabilities)"
            " values(%s,%s,%s,'owner',array['read','prepare','approve'])",
            (business, recipient, recipient),
        )
    try:
        yield business, recipient, other, subject
    finally:
        with pool.connection() as db:
            db.execute(
                "delete from public.business_notifications where business_id=%s",
                (business,),
            )
            db.execute("delete from public.business_client_grants where space_id=%s", (business,))
            db.execute("delete from public.spaces where id=%s", (business,))
            db.execute("delete from auth.users where id in (%s,%s)", (recipient, other))


@contextmanager
def acting_as(db, user_id):
    with db.transaction(force_rollback=True):
        db.execute("set local role authenticated")
        db.execute("select set_config('request.jwt.claim.sub',%s,true)", (user_id,))
        db.execute(
            "select set_config('request.jwt.claims',%s,true)",
            ('{"sub":"' + user_id + '"}',),
        )
        yield


def test_rls_reads_and_updates_only_recipient_rows(pool, identities):
    business, recipient, other, subject = identities
    store = PostgresNotificationStore(pool)
    store.put(business, recipient, "invitation_received", subject)
    row = store.list(business, recipient)[0]
    with pool.connection() as db:
        with acting_as(db, other):
            assert (
                db.execute("select id from public.business_notifications").fetchall()
                == []
            )
            assert (
                db.execute(
                    "update public.business_notifications set read_at=now() where id=%s",
                    (row.id,),
                ).rowcount
                == 0
            )
        with acting_as(db, recipient):
            assert db.execute(
                "select id::text from public.business_notifications"
            ).fetchall() == [(row.id,)]
            assert (
                db.execute(
                    "update public.business_notifications set read_at=now() where id=%s",
                    (row.id,),
                ).rowcount
                == 1
            )
        for column, value in (
            ("recipient_user_id", other),
            ("business_id", str(uuid4())),
            ("resolved_at", "2026-11-04"),
            ("kind", "new_sender_waiting"),
        ):
            with (
                pytest.raises(psycopg.errors.InsufficientPrivilege),
                acting_as(db, recipient),
            ):
                db.execute(
                    f"update public.business_notifications set {column}=%s where id=%s",
                    (value, row.id),
                )
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            acting_as(db, recipient),
        ):
            put(db, business, recipient, "new_sender_waiting", str(uuid4()))
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            acting_as(db, recipient),
        ):
            db.execute("delete from public.business_notifications where id=%s", (row.id,))


def test_partial_unique_index_and_resolution(pool, identities):
    business, recipient, other, subject = identities
    with pool.connection() as db:
        put(db, business, recipient, "invitation_received", subject)
        with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
            db.execute(
                "insert into public.business_notifications(business_id,recipient_user_id,kind,subject_id) values(%s,%s,'invitation_received',%s)",
                (business, recipient, subject),
            )
        resolve(db, business, "invitation_received", subject)
        put(db, business, recipient, "invitation_received", subject)
        put(db, business, other, "invitation_received", subject)
        assert (
            db.execute(
                "select count(*) from public.business_notifications where business_id=%s",
                (business,),
            ).fetchone()[0]
            == 3
        )


def test_concurrent_replay_and_read_state_on_new_store(pool, identities):
    business, recipient, other, subject = identities
    store = PostgresNotificationStore(pool)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(
            executor.map(
                lambda _: store.put(business, recipient, "new_sender_waiting", subject),
                range(12),
            )
        )
    (row,) = store.list(business, recipient)
    assert store.mark_read(business, other, row.id) == 0
    assert store.mark_read(str(uuid4()), recipient, row.id) == 0
    assert store.mark_read(business, recipient, row.id) == 1
    second = PostgresNotificationStore(pool)
    assert second.list(business, recipient)[0].read_at is not None
    assert second.list(business, other) == []
    assert second.mark_read(business, recipient) == 0


def test_recent_resolved_rows_and_order_match_memory(pool, identities):
    business, recipient, _, subject = identities
    store = PostgresNotificationStore(pool)
    store.put(business, recipient, "new_sender_waiting", subject)
    store.resolve(business, "new_sender_waiting", subject)
    with pool.connection() as db:
        db.execute(
            "update public.business_notifications set resolved_at=now()-interval '31 days' where business_id=%s",
            (business,),
        )
    assert store.list(business, recipient) == []
    first, second = str(uuid4()), str(uuid4())
    store.put(business, recipient, "invitation_received", first)
    store.put(business, recipient, "invitation_received", second)
    store.resolve(business, "invitation_received", second)
    assert [row.subject_id for row in store.list(business, recipient)] == [second, first]
    assert store.mark_read(business, recipient) == 3


def test_deleting_recipient_cascades_only_their_personal_notifications(pool, identities):
    business, recipient, other, subject = identities
    store = PostgresNotificationStore(pool)
    store.put(business, recipient, "invitation_received", subject)
    store.put(business, other, "invitation_received", subject)
    with pool.connection() as db, db.transaction(force_rollback=True):
        db.execute("delete from auth.users where id=%s", (other,))
        assert db.execute(
            "select recipient_user_id::text from public.business_notifications where business_id=%s",
            (business,),
        ).fetchall() == [(recipient,)]
