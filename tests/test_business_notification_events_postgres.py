"""Notification projections preserve the source transaction on database failure."""

from uuid import uuid4

import psycopg
import pytest
from argus.domain.business.notifications import events

from tests import test_financial_accounts_postgres as shared

pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "true")
    people = tuple(str(uuid4()) for _ in range(5))
    business, invite, sender = (str(uuid4()) for _ in range(3))
    with psycopg.connect(shared.DSN) as db, db.transaction(force_rollback=True):
        for person in people:
            db.execute("insert into auth.users(id) values(%s)", (person,))
        db.execute(
            "insert into public.spaces(id,kind,name,created_by)"
            " values(%s,'business','Test',%s)",
            (business, people[0]),
        )
        for person, role, revoked in zip(
            people[:4],
            ("owner", "owner", "owner", "editor"),
            (False, False, True, False),
            strict=False,
        ):
            db.execute(
                "insert into public.business_client_grants"
                "(space_id,grantee_id,issuer_id,business_role,capabilities,revoked_at)"
                " values(%s,%s,%s,%s,array['read'],case when %s then now() end)",
                (business, person, people[0], role, revoked),
            )
        db.execute(
            "insert into public.business_access_invites"
            "(id,space_id,issuer_id,email,recipient_id,expires_at)"
            " values(%s,%s,%s,%s,%s,now()+interval '7 days')",
            (invite, business, people[0], f"{invite}@example.test", people[4]),
        )
        yield db, business, invite, sender, people


@pytest.fixture
def notification_logs():
    messages = []
    handler = events.logger.add(lambda message: messages.append(str(message)))
    try:
        yield messages
    finally:
        events.logger.remove(handler)


def notifications(db, business):
    return db.execute(
        "select recipient_user_id::text,kind,subject_id::text,resolved_at"
        " from public.business_notifications where business_id=%s"
        " order by recipient_user_id",
        (business,),
    ).fetchall()


@pytest.mark.parametrize("terminal_column", ["accepted_at", "revoked_at"])
def test_invitation_is_written_once_and_resolved(source, terminal_column):
    db, business, invite, _, people = source
    events.invitation_changed(db, business, invite)
    events.invitation_changed(db, business, invite)
    assert notifications(db, business) == [
        (people[4], "invitation_received", invite, None)
    ]
    terminal_at = db.execute(
        f"update public.business_access_invites set {terminal_column}=now() where id=%s returning {terminal_column}",
        (invite,),
    ).fetchone()[0]
    events.invitation_changed(db, business, invite)
    events.invitation_changed(db, business, invite)
    rows = notifications(db, business)
    assert len(rows) == 1
    assert rows[0][3] == terminal_at


@pytest.mark.parametrize("status", ["authorized", "blocked"])
def test_sender_notifies_each_active_owner_once_and_resolves(source, status):
    db, business, _, sender, people = source
    events.sender_changed(db, business, sender, "pending")
    events.sender_changed(db, business, sender, "pending")
    assert notifications(db, business) == sorted(
        (person, "new_sender_waiting", sender, None) for person in people[:2]
    )
    events.sender_changed(db, business, sender, status)
    events.sender_changed(db, business, sender, status)
    rows = notifications(db, business)
    assert len(rows) == 2
    assert all(row[3] is not None for row in rows)


def test_disabled_writers_neither_create_nor_resolve(source, monkeypatch):
    db, business, invite, sender, _ = source
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "false")
    events.invitation_changed(db, business, invite)
    events.sender_changed(db, business, sender, "pending")
    assert notifications(db, business) == []
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "true")
    events.invitation_changed(db, business, invite)
    events.sender_changed(db, business, sender, "pending")
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "false")
    db.execute(
        "update public.business_access_invites set revoked_at=now() where id=%s",
        (invite,),
    )
    before = notifications(db, business)
    events.invitation_changed(db, business, invite)
    events.sender_changed(db, business, sender, "authorized")
    assert notifications(db, business) == before


@pytest.mark.parametrize("writer", ["invitation", "sender"])
@pytest.mark.parametrize("operation", ["put", "resolve"])
def test_database_failure_rolls_back_only_notification_savepoint(
    source, monkeypatch, notification_logs, writer, operation
):
    db, business, invite, sender, _ = source
    events.invitation_changed(db, business, invite)
    events.sender_changed(db, business, sender, "pending")
    if operation == "resolve":
        db.execute(
            "update public.business_access_invites set revoked_at=now() where id=%s",
            (invite,),
        )

    def missing_table(connection, *args, **kwargs):
        connection.execute("select * from public.missing_notification_test_table")

    monkeypatch.setattr(events, operation, missing_table)
    db.execute("update public.spaces set name='Changed' where id=%s", (business,))
    before = notifications(db, business)
    if writer == "invitation":
        events.invitation_changed(db, business, invite)
    else:
        events.sender_changed(
            db, business, sender, "authorized" if operation == "resolve" else "pending"
        )
    assert db.execute(
        "select name from public.spaces where id=%s", (business,)
    ).fetchone() == ("Changed",)
    assert notifications(db, business) == before
    assert any(
        "business_notification_write_failed type=UndefinedTable" in message
        for message in notification_logs
    )
    db.execute("update public.spaces set name='Still usable' where id=%s", (business,))


@pytest.mark.parametrize("writer", ["invitation", "sender"])
def test_invalid_switch_cannot_break_source_action(source, monkeypatch, writer):
    db, business, invite, sender, _ = source
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "invalid")
    db.execute("update public.spaces set name='Changed' where id=%s", (business,))
    if writer == "invitation":
        events.invitation_changed(db, business, invite)
    else:
        events.sender_changed(db, business, sender, "pending")
    assert notifications(db, business) == []
    assert db.execute(
        "select name from public.spaces where id=%s", (business,)
    ).fetchone() == ("Changed",)


def test_sender_failure_on_second_owner_rolls_back_partial_notifications(
    source, monkeypatch
):
    db, business, _, sender, _ = source
    original = events.put
    inserted = []

    def fail_after_one(connection, *args):
        if inserted:
            connection.execute("select * from public.missing_notification_test_table")
        original(connection, *args)
        inserted.append(args)

    monkeypatch.setattr(events, "put", fail_after_one)
    events.sender_changed(db, business, sender, "pending")
    assert len(inserted) == 1
    assert notifications(db, business) == []
    assert db.execute("select 1").fetchone() == (1,)
