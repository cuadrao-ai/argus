from uuid import uuid4

import pytest
from argus.api.business_spaces import business_access

from tests.business.conftest import BOB
from tests.business.test_business_api import BASE, Owner, alice, bob  # noqa: F401


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "true")


def test_disabled_routes_refuse_before_auth_and_workspace_says_false(alice, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "false")
    business = alice.scope().owner.space_id
    paths = [
        "/notifications",
        "/notifications/read-all",
        f"/notifications/{uuid4()}/read",
    ]
    for index, path in enumerate(paths):
        call = alice.client.get if index == 0 else alice.client.post
        response = call(BASE + path, params={"business_id": business})
        assert response.status_code == 404, response.text
        assert response.headers["cache-control"] == "no-store"
    assert alice.get("/workspace").json()["notifications_available"] is False


def test_read_state_survives_requests_and_is_scoped(alice, bob, enabled):  # noqa: F811
    store = business_access().notifications
    business, other_business = alice.scope().owner.space_id, bob.scope().owner.space_id
    for space, recipient in [
        (business, alice.person),
        (business, alice.person),
        (business, bob.person),
        (other_business, alice.person),
    ]:
        store.put(space, recipient, "new_sender_waiting", str(uuid4()))
    assert alice.get("/workspace").json()["notifications_available"] is True
    first = alice.get("/notifications", business_id=business)
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    rows = first.json()["items"]
    assert len(rows) == first.json()["unread_count"] == 2
    assert all(row["recipient_user_id"] == alice.person for row in rows)
    path = BASE + f"/notifications/{rows[0]['id']}/read"
    for _ in range(2):
        assert (
            alice.client.post(
                path, params={"business_id": business}, headers=alice.auth
            ).status_code
            == 200
        )
    again = alice.get("/notifications", business_id=business).json()
    assert again["unread_count"] == 1
    assert again["items"][0]["read_at"] is not None
    alice.client.post(
        BASE + "/notifications/read-all",
        params={"business_id": business},
        headers=alice.auth,
    )
    assert alice.get("/notifications", business_id=business).json()["unread_count"] == 0
    assert bob.get("/notifications", business_id=business).json()["unread_count"] == 1
    assert (
        alice.get("/notifications", business_id=other_business).json()["unread_count"]
        == 1
    )
    assert (
        bob.client.post(
            path, params={"business_id": business}, headers=bob.auth
        ).status_code
        == 404
    )


def test_invited_person_can_read_without_membership(alice, biz, identities, enabled):  # noqa: F811
    recipient = Owner(biz, BOB, identities[BOB]["id"])
    access = business_access()
    access.confirm(recipient.person, "recipient@example.test")
    business = alice.scope().owner.space_id
    _, listing = access.give(business, alice.person, "recipient@example.test")
    assert access.capabilities(business, recipient.person) == ()
    response = recipient.get("/notifications", business_id=business)
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["subject_id"] == listing.invites[0].id
    assert recipient.get("/notifications", business_id=str(uuid4())).json() == {
        "items": [],
        "unread_count": 0,
    }


@pytest.mark.parametrize("days_later", [8, 40])
def test_expiration_clears_unread_without_an_invitation_action(
    alice,  # noqa: F811
    biz,
    identities,
    enabled,
    monkeypatch,
    days_later,
):  # noqa: F811
    from datetime import timedelta

    recipient = Owner(biz, BOB, identities[BOB]["id"])
    access = business_access()
    access.confirm(recipient.person, "recipient@example.test")
    business = alice.scope().owner.space_id
    _, listing = access.give(business, alice.person, "recipient@example.test")
    assert (
        recipient.get("/notifications", business_id=business).json()["unread_count"] == 1
    )
    now = access._now() + timedelta(days=days_later)
    monkeypatch.setattr(access, "_now", lambda: now)
    monkeypatch.setattr(access.notifications, "clock", lambda: now)
    response = recipient.get("/notifications", business_id=business).json()
    assert response["unread_count"] == 0
    if days_later == 40:
        assert response["items"] == []
    else:
        from datetime import datetime

        resolved = datetime.fromisoformat(
            response["items"][0]["resolved_at"].replace("Z", "+00:00")
        )
        assert resolved == listing.invites[0].expires_at
