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


def test_the_bell_lists_live_invitations_and_keeps_read_state(pool, identities, monkeypatch):
    """On Postgres the list is the access store's live invitations, each naming
    its Business, and a reading survives a new store."""

    from argus.api import business_notifications as api
    from argus.api.business import BusinessPerson, require_business_person
    from argus.api.routers.business_notifications import router
    from argus.domain.business.access import PostgresAccessStore
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "true")
    monkeypatch.setattr(api, "business_access", lambda: PostgresAccessStore(pool))
    business, owner, invitee, _ = identities
    alive, withdrawn = str(uuid4()), str(uuid4())
    with pool.connection() as db:
        db.execute(
            "update auth.users set email=%s,email_confirmed_at=now() where id=%s",
            (f"{invitee}@example.test", invitee),
        )
        for invite, revoked in ((alive, False), (withdrawn, True)):
            db.execute(
                "insert into public.business_access_invites"
                "(id,space_id,issuer_id,email,requested_role,expires_at,revoked_at)"
                " values(%s,%s,%s,%s,'editor',now()+interval '7 days',"
                "case when %s then now() end)",
                (invite, business, owner, f"{invitee}@example.test", revoked),
            )
    app = FastAPI()
    app.include_router(router)
    person = {"id": invitee}
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        person["id"], None
    )
    try:
        with TestClient(app) as client:
            assert client.get("/notifications").json() == {
                "items": [
                    {
                        "id": alive,
                        "kind": "invitation_received",
                        "business_id": business,
                        "business_name": "Test",
                        "requested_role": "editor",
                        "unread": True,
                    }
                ],
                "unread_count": 1,
            }
            for updated in (1, 0):
                assert client.post(
                    "/notifications/read", json={"ids": [alive, withdrawn]}
                ).json() == {"updated": updated}
            assert client.get("/notifications").json()["unread_count"] == 0
            person["id"] = owner
            assert client.post("/notifications/read", json={"ids": [alive]}).json() == {
                "updated": 0
            }
            assert client.get("/notifications").json() == {
                "items": [],
                "unread_count": 0,
            }
        assert PostgresNotificationStore(pool).read_subjects(
            invitee, "invitation_received", [alive, withdrawn]
        ) == {alive}
    finally:
        with pool.connection() as db:
            db.execute(
                "delete from public.business_access_invites where space_id=%s",
                (business,),
            )


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


def test_concurrent_readings_keep_one_row_and_the_writer_row_is_reused(pool, identities):
    business, recipient, other, subject = identities
    store = PostgresNotificationStore(pool)
    store.put(business, recipient, "invitation_received", subject)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(
            executor.map(
                lambda _: store.mark_read(
                    recipient, "invitation_received", [(business, subject)]
                ),
                range(12),
            )
        )
    with pool.connection() as db:
        rows = db.execute(
            "select read_at from public.business_notifications"
            " where business_id=%s and recipient_user_id=%s",
            (business, recipient),
        ).fetchall()
    assert len(rows) == 1 and rows[0][0] is not None
    second = PostgresNotificationStore(pool)
    assert second.read_subjects(recipient, "invitation_received", [subject]) == {subject}
    assert second.read_subjects(other, "invitation_received", [subject]) == set()
    second.mark_read(recipient, "invitation_received", [(business, subject)])
    with pool.connection() as db:
        assert db.execute(
            "select read_at from public.business_notifications"
            " where business_id=%s and recipient_user_id=%s",
            (business, recipient),
        ).fetchall() == rows


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
