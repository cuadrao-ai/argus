from uuid import uuid4

import pytest
from argus.domain.business.access import InMemoryAccessStore
from argus.domain.business.notifications.store import InMemoryNotificationStore
from argus.domain.business.roles import BusinessRole
from argus.domain.ingestion.email_intake.store import InMemoryEmailStore


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "true")
    notices = InMemoryNotificationStore()
    access = InMemoryAccessStore(notifications=notices)
    owner, other, space = (str(uuid4()) for _ in range(3))
    access.confirm(owner, "owner@example.test")
    access.confirm(other, "other@example.test")
    access.ensure_owner_grant(space, owner)
    email = InMemoryEmailStore(
        notifications=notices, notification_owners=access.owner_ids
    )
    return notices, access, email, owner, other, space


@pytest.mark.parametrize("resolution", ["accept", "revoke"])
def test_invitation_is_once_and_resolves(rig, resolution):
    notices, access, _, owner, other, space = rig
    _, listing = access.give(space, owner, "other@example.test")
    access.give(space, owner, "other@example.test")
    items = notices.list(space, other)
    assert len(items) == 1
    assert items[0].kind == "invitation_received"
    assert items[0].subject_id == listing.invites[0].id
    assert notices.list(space, owner) == []
    if resolution == "accept":
        access.accept_invite(other, space, listing.invites[0].id)
    else:
        access.revoke_invite(space, owner, listing.invites[0].id)
    assert notices.list(space, other)[0].resolved_at is not None


@pytest.mark.parametrize("status", ["authorized", "blocked"])
def test_sender_notifies_every_owner_once_and_resolves(rig, status):
    notices, access, email, owner, other, space = rig
    _, invited = access.give(space, owner, "other@example.test", BusinessRole.OWNER)
    access.accept_invite(other, space, invited.invites[0].id)
    email.record_sender(space, "sender@example.test", "aligned")
    email.record_sender(space, "sender@example.test", "aligned")
    for person in [owner, other]:
        items = [n for n in notices.list(space, person) if n.kind == "new_sender_waiting"]
        assert len(items) == 1 and items[0].resolved_at is None
    email.upsert_sender(space, "address", "sender@example.test", status)
    for person in [owner, other]:
        items = [n for n in notices.list(space, person) if n.kind == "new_sender_waiting"]
        assert items[0].resolved_at is not None


def test_switch_off_writes_nothing(rig, monkeypatch):
    notices, access, email, owner, other, space = rig
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "false")
    access.give(space, owner, "other@example.test")
    email.record_sender(space, "sender@example.test", "aligned")
    assert notices.list(space, other) == notices.list(space, owner) == []


def test_writer_failure_does_not_break_actions(rig, monkeypatch):
    notices, access, email, owner, other, space = rig

    def fail(*args):
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(notices, "put", fail)
    assert access.give(space, owner, "other@example.test")[0]
    email.record_sender(space, "sender@example.test", "aligned")
    assert email.list_senders(space)[0].status == "pending"


@pytest.mark.parametrize("action", ["revoke", "resend"])
def test_old_expired_invitation_stays_outside_recent_window(rig, monkeypatch, action):
    from datetime import timedelta

    notices, access, _, owner, other, space = rig
    _, listing = access.give(space, owner, "other@example.test")
    invite = listing.invites[0]
    now = invite.expires_at + timedelta(days=40)
    monkeypatch.setattr(access, "_now", lambda: now)
    monkeypatch.setattr(notices, "clock", lambda: now)
    if action == "revoke":
        access.revoke_invite(space, owner, invite.id)
    else:
        access.give(space, owner, "other@example.test")
    assert all(row.subject_id != invite.id for row in notices.list(space, other))
