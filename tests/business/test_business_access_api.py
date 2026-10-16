"""The owner's access screen through the real app on the in-memory stores."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from argus.api.business_spaces import accept_business_invites, business_access
from fastapi.testclient import TestClient

from tests.business.conftest import ALICE, BOB
from tests.business.test_business_api import Owner, bob  # noqa: F401


@pytest.fixture
def alice(biz: TestClient, identities) -> Owner:  # noqa: ANN001
    owner = Owner(biz, ALICE, identities[ALICE]["id"])
    assert owner.start({"name": "Colmado La Esquina"}).status_code == 201
    return owner


def test_starting_a_space_gives_the_owner_a_live_grant_once(
    biz: TestClient, identities
) -> None:  # noqa: ANN001, F811
    owner = Owner(biz, ALICE, identities[ALICE]["id"])
    assert owner.start().status_code == 201
    store = business_access()
    assert store is not None
    space_id = owner.scope().owner.space_id
    assert store.capabilities(space_id, owner.person) == ("read", "prepare", "approve")
    # Replays and workspace reads heal nothing when the grant is there: one row, one ledger entry.
    assert owner.start().status_code == 200
    assert owner.get("/workspace").status_code == 200
    listed = owner.get("/access")
    assert listed.status_code == 200, listed.text
    assert [(g["owner"], g["capabilities"]) for g in listed.json()["grants"]] == [
        (True, ["read", "prepare", "approve"])
    ]
    assert [c.action for c in store.ledger if c.action == "owner_grant"].count(
        "owner_grant"
    ) == 1


def test_an_unknown_email_becomes_one_pending_invite_the_owner_can_revoke(
    alice: Owner,  # noqa: F811
) -> None:  # noqa: F811
    first = alice.post("/access", {"email": "  Contadora@Example.TEST "})
    assert first.status_code == 201, first.text
    invites = first.json()["invites"]
    assert [i["email"] for i in invites] == ["contadora@example.test"]
    replay = alice.post("/access", {"email": "contadora@example.test"})
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert alice.post("/access", {"email": "not-an-address"}).status_code == 422
    gone = alice.client.delete(
        f"/api/v1/business/access/invites/{invites[0]['id']}", headers=alice.auth
    )
    assert gone.status_code == 204
    assert alice.get("/access").json()["invites"] == []
    assert (
        alice.client.delete(
            f"/api/v1/business/access/invites/{invites[0]['id']}", headers=alice.auth
        ).status_code
        == 404
    )


def test_a_confirmed_account_gets_read_and_prepare_and_loses_it_at_once(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:  # noqa: F811
    store = business_access()
    assert store is not None
    store.confirm(bob.person, "bob@example.test")
    space_id = alice.scope().owner.space_id
    given = alice.post("/access", {"email": "BOB@example.test"})
    assert given.status_code == 201, given.text
    grants = given.json()["grants"]
    assert [(g["owner"], g["capabilities"], g["email"]) for g in grants] == [
        (True, ["read", "prepare", "approve"], None),
        (False, ["read", "prepare"], "bob@example.test"),
    ]
    assert store.capabilities(space_id, bob.person) == ("read", "prepare")
    assert "approve" not in store.capabilities(space_id, bob.person)
    revoked = alice.client.delete(
        f"/api/v1/business/access/grants/{grants[1]['id']}", headers=alice.auth
    )
    assert revoked.status_code == 204
    assert store.capabilities(space_id, bob.person) == ()
    assert [g["owner"] for g in alice.get("/access").json()["grants"]] == [True]
    assert [c.action for c in store.ledger][-2:] == ["grant_access", "revoke_grant"]


def test_the_owner_cannot_revoke_their_own_grant(alice: Owner) -> None:  # noqa: F811
    own = alice.get("/access").json()["grants"][0]
    refused = alice.client.delete(
        f"/api/v1/business/access/grants/{own['id']}", headers=alice.auth
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "owner_grant_required"
    assert alice.get("/access").json()["grants"][0]["id"] == own["id"]
    assert (
        alice.client.delete(
            f"/api/v1/business/access/grants/{uuid4()}", headers=alice.auth
        ).status_code
        == 404
    )


def test_a_pending_invite_turns_into_a_grant_when_that_email_signs_in(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:
    store = business_access()
    assert store is not None
    invited = alice.post("/access", {"email": "bob@example.test"})
    assert invited.status_code == 201 and invited.json()["invites"]
    # Not confirmed yet: a profile read grants nothing.
    assert accept_business_invites(bob.person) is None
    assert store.capabilities(alice.scope().owner.space_id, bob.person) == ()
    store.confirm(bob.person, "bob@example.test")
    accept_business_invites(bob.person)
    assert store.capabilities(alice.scope().owner.space_id, bob.person) == (
        "read",
        "prepare",
    )
    listed = alice.get("/access").json()
    assert listed["invites"] == []
    assert [g["email"] for g in listed["grants"]] == [None, "bob@example.test"]
    assert "accept_invite" in [c.action for c in store.ledger]


def test_the_first_spaces_read_after_sign_in_lists_the_client_business(
    biz: TestClient,
    identities,  # noqa: ANN001
    alice: Owner,  # noqa: F811
) -> None:
    """The web client reads the switcher beside the profile, so the listing
    itself turns the invite into a grant; a replay accepts nothing twice."""

    store = business_access()
    assert store is not None
    invited = alice.post("/access", {"email": "bob@example.test"})
    assert invited.status_code == 201, invited.text
    newcomer = Owner(biz, BOB, identities[BOB]["id"])
    store.confirm(newcomer.person, "bob@example.test")

    first = newcomer.get("/spaces")
    assert first.status_code == 200, first.text
    [client_business] = first.json()["spaces"]
    assert (
        client_business["space_id"],
        client_business["role"],
        client_business["capabilities"],
        client_business["access_seen"],
    ) == (alice.scope().owner.space_id, "accountant", ["read", "prepare"], False)
    assert newcomer.get("/spaces").json()["spaces"] == [client_business]
    assert [c.action for c in store.ledger].count("accept_invite") == 1
    assert alice.get("/access").json()["invites"] == []


def test_the_profile_read_never_fails_because_of_the_invite_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Broken:
        def accept_invites(self, user_id: str) -> int:
            raise RuntimeError("database away")

    monkeypatch.setattr("argus.api.business_spaces._access", Broken())
    assert accept_business_invites(str(uuid4())) is None
    monkeypatch.setattr("argus.api.business_spaces._access", None)
    assert accept_business_invites(str(uuid4())) is None


def test_re_inviting_an_expired_email_makes_a_fresh_live_invite(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:  # noqa: F811
    """The in-memory store follows the Postgres rule: live stays, expired is
    re-issued with a new window and a receipt, revoked and accepted no longer
    hold the slot, and the owner sees the result."""

    store = business_access()
    assert store is not None
    first = alice.post("/access", {"email": "contadora@example.test"})
    assert first.status_code == 201, first.text
    [invite] = first.json()["invites"]
    # Live: a replay changes nothing.
    assert alice.post("/access", {"email": "contadora@example.test"}).status_code == 200
    # Expired: the owner sees no invite; re-inviting makes a fresh live one with a new window.
    pending = next(i for i in store._invites if i["id"] == invite["id"])
    pending["expires_at"] = store._now() - timedelta(days=1)
    assert alice.get("/access").json()["invites"] == []
    again = alice.post("/access", {"email": "contadora@example.test"})
    assert again.status_code == 201, again.text
    [fresh] = again.json()["invites"]
    assert (
        fresh["email"] == "contadora@example.test"
        and fresh["expires_at"] > invite["expires_at"]
    )
    assert [c.action for c in store.ledger].count("invite_access") == 2
    assert len([i for i in store._invites if i["email"] == "contadora@example.test"]) == 1
    # Revoked: a new invite is born beside the revoked row.
    gone = alice.client.delete(
        f"/api/v1/business/access/invites/{fresh['id']}", headers=alice.auth
    )
    assert gone.status_code == 204
    reborn = alice.post("/access", {"email": "contadora@example.test"})
    assert reborn.status_code == 201 and len(reborn.json()["invites"]) == 1
    assert len([i for i in store._invites if i["email"] == "contadora@example.test"]) == 2
    # Accepted: the confirmed account holds the grant; re-inviting it creates nothing.
    store.confirm(bob.person, "bob@example.test")
    assert alice.post("/access", {"email": "bob@example.test"}).status_code == 201
    replay = alice.post("/access", {"email": "bob@example.test"})
    assert replay.status_code == 200
    assert "bob@example.test" not in [i["email"] for i in replay.json()["invites"]]
