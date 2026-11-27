"""The bell is the person's: one notice per live invitation addressed to
them, from any Business, with the read state on the server."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.api.business_spaces import business_access

from tests.business.conftest import BOB
from tests.business.test_business_access_invites_work import (  # noqa: F401
    _invite,
    invites_on,
    people,
)
from tests.business.test_business_api import BASE, Owner


@pytest.fixture
def bell_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "true")


def _bell(person: Owner, **headers: str) -> dict:
    response = person.client.get(
        BASE + "/notifications", headers={**person.auth, **headers}
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_switch_off_refuses_the_routes_and_the_directory_says_so(
    people: tuple[Owner, Owner],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice, _ = people
    monkeypatch.setenv("CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED", "false")
    for response in (
        alice.client.get(BASE + "/notifications"),
        alice.client.post(BASE + "/notifications/read", json={"ids": []}),
    ):
        assert response.status_code == 404, response.text
        assert response.headers["cache-control"] == "no-store"
    assert alice.get("/spaces").json()["notifications_available"] is False
    assert "notifications_available" not in alice.get("/workspace").json()


def test_an_invitee_with_no_business_sees_the_invitation_naming_its_business(
    people: tuple[Owner, Owner],  # noqa: F811
    invites_on: list[dict],  # noqa: F811
    identities,  # noqa: ANN001
    bell_on: None,
) -> None:
    alice, bob = people
    invite = _invite(alice, identities[BOB]["email"], "admin")
    directory = bob.get("/spaces").json()
    assert directory["spaces"] == []
    assert directory["notifications_available"] is True
    assert _bell(bob) == {
        "items": [
            {
                "id": invite["invite_id"],
                "kind": "invitation_received",
                "business_id": alice.scope().owner.space_id,
                "business_name": "Colmado La Esquina",
                "requested_role": "admin",
                "unread": True,
            }
        ],
        "unread_count": 1,
    }


def test_opening_marks_read_on_the_server_once_and_only_what_was_shown(
    people: tuple[Owner, Owner],  # noqa: F811
    invites_on: list[dict],  # noqa: F811
    identities,  # noqa: ANN001
    bell_on: None,
) -> None:
    alice, bob = people
    invite = _invite(alice, identities[BOB]["email"], "viewer")
    stranger = bob.post("/notifications/read", {"ids": [str(uuid4())]})
    assert stranger.json() == {"updated": 0}
    assert alice.post("/notifications/read", {"ids": [invite["invite_id"]]}).json() == {
        "updated": 0
    }
    assert _bell(bob)["unread_count"] == 1
    for updated in (1, 0):
        read = bob.post("/notifications/read", {"ids": [invite["invite_id"]]})
        assert read.status_code == 200, read.text
        assert read.json() == {"updated": updated}
    shown = _bell(bob)
    assert shown["unread_count"] == 0
    assert [item["unread"] for item in shown["items"]] == [False]


def test_the_list_is_the_same_whichever_business_the_person_works_in(
    people: tuple[Owner, Owner],  # noqa: F811
    invites_on: list[dict],  # noqa: F811
    identities,  # noqa: ANN001
    bell_on: None,
) -> None:
    alice, bob = people
    access = business_access()
    other = str(uuid4())
    access.ensure_owner_grant(other, alice.person)
    _, listing = access.give(other, alice.person, identities[BOB]["email"])
    first = _invite(alice, identities[BOB]["email"], "editor")
    ids = {first["invite_id"], listing.invites[0].id}
    plain = _bell(bob)
    assert {item["id"] for item in plain["items"]} == ids
    assert {item["business_id"] for item in plain["items"]} == {
        alice.scope().owner.space_id,
        other,
    }
    accepted = bob.post(
        f"/invitations/{first['invite_id']}/accept",
        {"space_id": alice.scope().owner.space_id},
    )
    assert accepted.status_code == 200, accepted.text
    inside = _bell(bob, **{"X-Business-Grant": accepted.json()["grant_id"]})
    assert [item["id"] for item in inside["items"]] == [listing.invites[0].id]
    assert _bell(bob) == inside


def test_a_withdrawn_invitation_leaves_the_list(
    people: tuple[Owner, Owner],  # noqa: F811
    invites_on: list[dict],  # noqa: F811
    identities,  # noqa: ANN001
    gateway,  # noqa: ANN001
    bell_on: None,
) -> None:
    """Bob keeps his account's standing, so the door still lets him in."""

    alice, bob = people
    gateway.private_alpha_email_allowed.side_effect = lambda email: True
    invite = _invite(alice, identities[BOB]["email"], "viewer")
    assert _bell(bob)["unread_count"] == 1
    assert business_access().revoke_invite(
        alice.scope().owner.space_id, alice.person, invite["invite_id"]
    )
    assert _bell(bob) == {"items": [], "unread_count": 0}


def test_the_older_list_route_is_gone(
    people: tuple[Owner, Owner],  # noqa: F811
    bell_on: None,
) -> None:
    _, bob = people
    assert bob.get("/invitations").status_code in (404, 405)


@pytest.mark.parametrize("role", ["admin", "editor", "viewer"])
def test_accepting_the_notice_gives_exactly_the_invited_role_and_empties_the_bell(
    people: tuple[Owner, Owner],  # noqa: F811
    invites_on: list[dict],  # noqa: F811
    identities,  # noqa: ANN001
    bell_on: None,
    role: str,
) -> None:
    alice, bob = people
    _invite(alice, identities[BOB]["email"], role)
    [notice] = _bell(bob)["items"]
    accepted = bob.post(
        f"/invitations/{notice['id']}/accept", {"space_id": notice["business_id"]}
    )
    assert accepted.status_code == 200, accepted.text
    [joined] = bob.get("/spaces").json()["spaces"]
    assert (joined["space_id"], joined["grant_id"], joined["business_role"]) == (
        notice["business_id"],
        accepted.json()["grant_id"],
        role,
    )
    assert _bell(bob) == {"items": [], "unread_count": 0}
