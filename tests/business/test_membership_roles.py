from uuid import uuid4

from argus.domain.business.access import InMemoryAccessStore


def test_confirmed_recipient_stays_pending_until_explicit_acceptance() -> None:
    access = InMemoryAccessStore()
    space, owner, recipient = (str(uuid4()) for _ in range(3))
    access.ensure_owner_grant(space, owner)
    access.confirm(recipient, "member@example.test")

    created, result = access.give(space, owner, "member@example.test")

    assert created
    assert len(result.invites) == 1
    assert access.spaces_for(recipient) == ()
    assert access.capabilities(space, recipient) == ()


def test_read_hook_never_accepts_pending_invitations() -> None:
    access = InMemoryAccessStore()
    space, owner, recipient = (str(uuid4()) for _ in range(3))
    access.ensure_owner_grant(space, owner)
    access.give(space, owner, "member@example.test")
    access.confirm(recipient, "member@example.test")

    assert access.accept_invites(recipient) == 0
    assert access.spaces_for(recipient) == ()
