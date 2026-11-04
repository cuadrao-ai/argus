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
            db.execute(
                "delete from public.business_client_grants where space_id=%s", (business,)
            )
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


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_clients_cannot_read_or_update_any_notification(pool, identities, role):
    business, recipient, other, subject = identities
    store = PostgresNotificationStore(pool)
    store.put(business, recipient, "invitation_received", subject)
    store.put(business, other, "invitation_received", subject)
    with pool.connection() as db:
        assert db.execute(
            "select relrowsecurity from pg_class where oid='public.business_notifications'::regclass"
        ).fetchone() == (True,)
        for person in (recipient, other):
            for statement in (
                "select * from public.business_notifications",
                "update public.business_notifications set read_at=now()",
            ):
                with (
                    pytest.raises(psycopg.errors.InsufficientPrivilege),
                    acting_as(db, person),
                ):
                    db.execute("set local role " + role)
                    db.execute(statement)


def test_server_api_returns_and_updates_only_callers_items(pool, identities, monkeypatch):
    from argus.api import business_notifications as api
    from argus.api.business import BusinessPerson, require_business_person
    from argus.api.routers.business_notifications import router
    from argus.domain.business.access import PostgresAccessStore
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "true")
    monkeypatch.setattr(api, "business_access", lambda: PostgresAccessStore(pool))
    business, recipient, other, subject = identities
    store = PostgresNotificationStore(pool)
    for person in (recipient, other):
        store.put(business, person, "new_sender_waiting", subject)
    own, foreign = store.list(business, recipient)[0], store.list(business, other)[0]
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        recipient, None
    )
    with TestClient(app) as client:
        params = {"business_id": business}
        response = client.get("/notifications", params=params)
        assert response.status_code == 200
        assert [row["id"] for row in response.json()["items"]] == [own.id]
        assert (
            client.post(f"/notifications/{foreign.id}/read", params=params).status_code
            == 404
        )
        assert client.post("/notifications/read-all", params=params).json() == {
            "updated": 1
        }
        assert client.get("/notifications", params=params).json()["unread_count"] == 0
    assert store.list(business, other)[0].read_at is None


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
