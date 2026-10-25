from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.business.access import InMemoryAccessStore
from argus.domain.business.memberships import MembershipError


def test_invite_expires_at_seven_days_and_owner_resend_resets_window():
    store = InMemoryAccessStore()
    now = datetime(2026, 10, 18, 3, tzinfo=timezone.utc)
    store._now = lambda: now
    space, owner, person = (str(uuid4()) for _ in range(3))
    store.ensure_owner_grant(space, owner)
    created, listed = store.give(space, owner, "person@example.test")
    assert created
    invite = listed.invites[0]
    assert invite.expires_at == now + timedelta(days=7)
    now = invite.expires_at
    store.confirm(person, invite.email)
    assert store.accept_invites(person) == 0
    assert store.capabilities(space, person) == ()
    assert store.list(space, owner).invites[0].state == "expired"
    renewed = store.resend(space, owner, invite.id)
    assert renewed is not None
    assert renewed.invites[0].expires_at == now + timedelta(days=7)
    store.accept_invite(person, space, renewed.invites[0].id)
    assert store.resend(space, owner, invite.id) is None
    assert store.capabilities(space, person) == ("read", "prepare")


def test_resend_cannot_cross_business_owner_or_revoked_invite():
    store = InMemoryAccessStore()
    space, owner = str(uuid4()), str(uuid4())
    store.ensure_owner_grant(space, owner)
    _, listed = store.give(space, owner, "person@example.test")
    invite = listed.invites[0]
    with pytest.raises(MembershipError):
        store.resend(str(uuid4()), owner, invite.id)
    with pytest.raises(MembershipError):
        store.resend(space, str(uuid4()), invite.id)
    assert store.revoke_invite(space, owner, invite.id)
    assert store.resend(space, owner, invite.id) is None


@pytest.mark.parametrize("offset,expected", [(-1, 1), (0, 0), (1, 0)])
def test_exact_expiry_boundary(offset, expected):
    store = InMemoryAccessStore()
    now = datetime(2026, 10, 18, 3, tzinfo=timezone.utc)
    store._now = lambda: now
    space, owner, person = (str(uuid4()) for _ in range(3))
    store.ensure_owner_grant(space, owner)
    _, listed = store.give(space, owner, "person@example.test")
    store.confirm(person, "person@example.test")
    now = listed.invites[0].expires_at + timedelta(microseconds=offset)
    if expected:
        assert store.accept_invite(person, space, listed.invites[0].id)
    else:
        with pytest.raises(MembershipError):
            store.accept_invite(person, space, listed.invites[0].id)
