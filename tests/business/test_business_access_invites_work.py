"""Invites work: a member's actions follow the role, an invitee keeps no
Business of their own, Reenviar sends again within its limits, and the email
link carries the exact invite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.api.business_spaces import business_access
from argus.domain.business.access import AccessInvite
from argus.domain.business.invite_email import invite_path, render_invite_email
from argus.domain.business.roles import BusinessRole
from faker import Faker
from fastapi.testclient import TestClient
from loguru import logger

from tests.business.conftest import ALICE, BOB
from tests.business.test_business_api import Owner

fake = Faker()
CONSENT_VERSION = "0123456789abcdef"


@pytest.fixture
def invites_on(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Closed sign-up, both invite switches on, and a mailbox that only counts."""

    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    sent: list[dict] = []
    monkeypatch.setattr(
        "argus.domain.business.invite_email.send_resend_email",
        lambda **message: sent.append(message) or "fake-receipt",
    )
    return sent


@pytest.fixture
def people(biz: TestClient, identities, gateway) -> tuple[Owner, Owner]:  # noqa: ANN001
    """Alice is on the allowlist and owns a Business. Bob is on no list."""

    alice = Owner(biz, ALICE, identities[ALICE]["id"])
    bob = Owner(biz, BOB, identities[BOB]["id"])
    gateway.private_alpha_email_allowed.side_effect = (
        lambda email: email == identities[ALICE]["email"]
    )
    assert alice.start({"name": "Colmado La Esquina"}).status_code == 201
    business_access().confirm(alice.person, identities[ALICE]["email"])
    business_access().confirm(bob.person, identities[BOB]["email"])
    return alice, bob


def _invite(owner: Owner, email: str, role: str) -> dict:
    response = owner.post(
        "/access/invitations",
        {"recipients": [{"email": email, "role": role, "command_key": str(uuid4())}]},
    )
    assert response.status_code == 200, response.text
    [result] = response.json()["results"]
    return result


def _join(alice: Owner, bob: Owner, email: str, role: str) -> dict[str, str]:
    """Bob accepts Alice's invitation and gets the header that picks her Business."""

    invite = _invite(alice, email, role)
    space_id = alice.scope().owner.space_id
    accepted = bob.post(
        f"/invitations/{invite['invite_id']}/accept", {"space_id": space_id}
    )
    assert accepted.status_code == 200, accepted.text
    return {"X-Business-Grant": accepted.json()["grant_id"]}


def _pending(owner: Owner, **headers: str) -> dict:
    response = owner.client.get(
        "/api/v1/business/access", headers={**owner.auth, **headers}
    )
    assert response.status_code == 200, response.text
    [invite] = response.json()["invites"]
    return invite


def _resend(owner: Owner, invite_id: str):
    return owner.post(f"/access/invites/{invite_id}/resend")


def _later(monkeypatch: pytest.MonkeyPatch, **gap: float) -> None:
    """Moves the store's clock forward by ``gap`` from where it stands."""

    store = business_access()
    now = store._now() + timedelta(**gap)
    monkeypatch.setattr(store, "_now", lambda: now)


def test_an_admin_admitted_only_by_invitation_invites_a_viewer(
    people, identities, invites_on
) -> None:  # noqa: ANN001
    alice, bob = people
    grant = _join(alice, bob, identities[BOB]["email"], "admin")

    invited = bob.post(
        "/access/invitations",
        {
            "recipients": [
                {"email": fake.email(), "role": "viewer", "command_key": str(uuid4())}
            ]
        },
        **grant,
    )

    assert invited.status_code == 200, invited.text
    assert invited.json()["results"][0]["state"] == "pending"
    assert [mail["recipient"] for mail in invites_on][1:] == [
        invited.json()["results"][0]["email"].lower()
    ]


def test_the_server_says_who_may_start_a_business(people, identities, invites_on) -> None:  # noqa: ANN001
    alice, bob = people
    _join(alice, bob, identities[BOB]["email"], "admin")

    assert alice.get("/spaces").json()["can_start_business"] is True
    assert bob.get("/spaces").json()["can_start_business"] is False
    refused = bob.start({"name": "Mi negocio"})
    assert refused.status_code == 403, refused.text


@pytest.mark.parametrize("role", ["viewer", "editor", "admin"])
def test_a_new_invitee_saves_consent_and_gets_only_the_invited_role(
    people, identities, invites_on, role: str
) -> None:  # noqa: ANN001
    alice, bob = people
    invite = _invite(alice, identities[BOB]["email"], role)

    consent = bob.post("/consent", {"version": CONSENT_VERSION})

    assert consent.status_code == 200, consent.text
    assert consent.json()["accepted_at"]
    assert bob.get("/consent", version=CONSENT_VERSION).json()["accepted_at"]
    assert bob.get("/spaces").json()["spaces"] == []

    space_id = alice.scope().owner.space_id
    accepted = bob.post(
        f"/invitations/{invite['invite_id']}/accept", {"space_id": space_id}
    )
    assert accepted.status_code == 200, accepted.text
    [space] = bob.get("/spaces").json()["spaces"]
    assert (space["space_id"], space["business_role"]) == (space_id, role)


def test_consent_with_no_business_and_no_invitation_is_refused(
    biz: TestClient, identities, gateway
) -> None:  # noqa: ANN001
    alice = Owner(biz, ALICE, identities[ALICE]["id"])

    refused = alice.post("/consent", {"version": CONSENT_VERSION})

    assert refused.status_code == 404, refused.text
    assert refused.json()["code"] == "business_space_missing"


def test_reenviar_sends_the_same_link_again_and_keeps_the_expiry(
    people, invites_on, monkeypatch
) -> None:  # noqa: ANN001
    alice, _ = people
    invite = _invite(alice, fake.email(), "viewer")
    before = _pending(alice)
    _later(monkeypatch, seconds=61)

    again = _resend(alice, invite["invite_id"])

    assert again.status_code == 200, again.text
    assert again.json()["invite_delivery"] == "accepted"
    after = _pending(alice)
    assert (after["id"], after["expires_at"]) == (before["id"], before["expires_at"])
    first, second = invites_on
    assert first["plain_text"] == second["plain_text"]
    assert f"/biz?invite={invite['invite_id']}" in second["plain_text"]
    assert first["idempotency_key"] != second["idempotency_key"]


def test_reenviar_inside_the_cooldown_is_refused_with_the_seconds_left(
    people, invites_on, monkeypatch
) -> None:  # noqa: ANN001
    alice, _ = people
    invite = _invite(alice, fake.email(), "viewer")
    assert _pending(alice)["resend_wait_seconds"] == 60
    _later(monkeypatch, seconds=20)

    refused = _resend(alice, invite["invite_id"])

    assert refused.status_code == 429, refused.text
    assert refused.json()["code"] == "business_invite_resend_cooldown"
    assert refused.json()["context"] == {"retry_after_seconds": 40}
    assert refused.headers["Retry-After"] == "40"
    assert _pending(alice)["resend_wait_seconds"] == 40
    assert len(invites_on) == 1


def test_the_wait_after_a_resend_is_in_its_answer(
    people, invites_on, monkeypatch
) -> None:  # noqa: ANN001
    alice, _ = people
    invite = _invite(alice, fake.email(), "viewer")
    _later(monkeypatch, seconds=60)

    again = _resend(alice, invite["invite_id"])

    assert again.status_code == 200, again.text
    assert again.json()["invites"][0]["resend_wait_seconds"] == 60


def test_reenviar_past_the_send_cap_of_one_invite_is_refused(
    people, invites_on, monkeypatch
) -> None:  # noqa: ANN001
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_SENDS_PER_INVITE", "3")
    alice, _ = people
    invite = _invite(alice, fake.email(), "viewer")
    for minutes in (2, 4):
        _later(monkeypatch, minutes=minutes)
        assert _resend(alice, invite["invite_id"]).status_code == 200
    _later(monkeypatch, minutes=6)

    refused = _resend(alice, invite["invite_id"])

    assert refused.status_code == 429, refused.text
    assert refused.json()["code"] == "business_invite_send_cap_reached"
    assert len(invites_on) == 3


def test_reenviar_past_the_daily_cap_of_the_business_is_refused(
    people, invites_on, monkeypatch
) -> None:  # noqa: ANN001
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_RESENDS_PER_DAY", "2")
    alice, _ = people
    first, second, third = (
        _invite(alice, fake.unique.email(), "viewer")["invite_id"] for _ in range(3)
    )
    _later(monkeypatch, minutes=2)
    assert _resend(alice, first).status_code == 200
    assert _resend(alice, second).status_code == 200

    refused = _resend(alice, third)

    assert refused.status_code == 429, refused.text
    assert refused.json()["code"] == "business_invite_daily_cap_reached"
    assert len(invites_on) == 5
    _later(monkeypatch, days=1, minutes=3)
    assert _resend(alice, third).status_code == 200


def test_each_send_writes_one_log_line_without_the_address(
    people, invites_on, monkeypatch
) -> None:  # noqa: ANN001
    alice, _ = people
    email = fake.email().lower()
    lines: list[str] = []
    sink = logger.add(lines.append, format="{message}")
    try:
        invite = _invite(alice, email, "viewer")
        _later(monkeypatch, seconds=61)
        assert _resend(alice, invite["invite_id"]).status_code == 200
        _later(monkeypatch, seconds=5)
        assert _resend(alice, invite["invite_id"]).status_code == 429
    finally:
        logger.remove(sink)

    sends = [line for line in lines if "business_invite_email_send" in line]
    assert len(sends) == 2
    assert f"invite_id={invite['invite_id']}" in sends[0]
    assert "send_number=1 resend=False" in sends[0]
    assert "send_number=2 resend=True" in sends[1]
    assert not any(email in line or "/biz?invite=" in line for line in lines)


def _listed(has_account: bool) -> AccessInvite:
    now = datetime.now(timezone.utc)
    return AccessInvite(
        str(uuid4()),
        fake.email(),
        now,
        now + timedelta(days=7),
        "pending",
        BusinessRole.VIEWER,
        has_account=has_account,
    )


def test_the_email_link_carries_the_invite_and_the_right_door() -> None:
    new, known = _listed(False), _listed(True)

    assert invite_path(new) == f"/biz?invite={new.id}&auth=signup"
    assert invite_path(known) == f"/biz?invite={known.id}"
    message = render_invite_email(
        owner_name="Ana",
        business_name="Colmado La Esquina",
        expires_at=new.expires_at,
        sign_in_origin="https://app.example.test",
        path=invite_path(new),
    )
    link = f"https://app.example.test/biz?invite={new.id}"
    assert f"{link}&auth=signup" in message.text
    assert f"{link}&amp;auth=signup" in message.html


def test_a_business_without_a_name_sends_and_resends_no_invite(
    biz: TestClient, identities, gateway, invites_on
) -> None:  # noqa: ANN001
    alice = Owner(biz, ALICE, identities[ALICE]["id"])
    assert alice.start().status_code == 201
    business_access().confirm(alice.person, identities[ALICE]["email"])
    recipient = {"email": fake.email(), "role": "viewer", "command_key": str(uuid4())}

    refused = alice.post("/access/invitations", {"recipients": [recipient]})

    assert (refused.status_code, refused.json()["code"]) == (
        409,
        "business_name_required",
    )
    assert alice.get("/access").json()["invites"] == []
    _, listed = business_access().give(
        alice.scope().owner.space_id,
        alice.person,
        recipient["email"],
        BusinessRole.VIEWER,
    )
    again = _resend(alice, listed.invites[0].id)
    assert (again.status_code, again.json()["code"]) == (409, "business_name_required")
    assert invites_on == []


def test_a_member_with_no_business_of_their_own_saves_consent(
    people, identities, invites_on
) -> None:  # noqa: ANN001
    """The first visit after accepting: no Business chosen yet in the browser."""

    alice, bob = people
    _join(alice, bob, identities[BOB]["email"], "viewer")

    consent = bob.post("/consent", {"version": CONSENT_VERSION})

    assert consent.status_code == 200, consent.text
    assert [s["business_role"] for s in bob.get("/spaces").json()["spaces"]] == ["viewer"]
