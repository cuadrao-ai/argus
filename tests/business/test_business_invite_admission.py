"""While sign-up is closed and ``CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED`` is
true, a live Business invitation admits exactly the invited email, and the
accepted grant keeps admitting it until revoked. With the switch off, the
default, the gate and the standing check answer as they did before the switch
existed: the allowlist and open sign-up alone decide."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.api.business_spaces import business_access
from argus.api.guest_access import permanent_account_access_allowed
from argus.domain.business.access import InMemoryAccessStore
from argus.domain.business.config import business_invite_admission_enabled
from faker import Faker
from fastapi.testclient import TestClient

from tests.business.conftest import ALICE, BOB
from tests.business.test_business_api import BASE, Owner
from tests.financial_accounts.conftest import _profile

fake = Faker()
OWNER = "owner-" + str(uuid4())
SWITCH = "CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED"


@pytest.fixture
def closed_signup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")


@pytest.fixture
def switch_on(closed_signup, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    monkeypatch.setenv(SWITCH, "true")


@pytest.fixture
def switch_off(closed_signup, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    monkeypatch.delenv(SWITCH, raising=False)


def _allowlist(*, listed: set[str] = frozenset(), disabled: set[str] = frozenset()):
    return SimpleNamespace(
        private_alpha_email_disabled=lambda email: email.strip().lower() in disabled,
        private_alpha_email_allowed=lambda email: email.strip().lower() in listed
        and email.strip().lower() not in disabled,
    )


def _business(owner: str = OWNER) -> tuple[InMemoryAccessStore, str]:
    store, space = InMemoryAccessStore(), str(uuid4())
    store.confirm(owner, f"{owner}@example.test")
    assert store.ensure_owner_grant(space, owner)
    return store, space


def test_a_live_invite_admits_exactly_that_email(switch_on) -> None:  # noqa: ANN001
    store, space = _business()
    gateway = _allowlist()
    invited = fake.email().lower()

    assert not permanent_account_access_allowed(gateway, invited, store)
    store.give(space, OWNER, f"  {invited.upper()} ")
    assert permanent_account_access_allowed(gateway, invited, store)
    assert permanent_account_access_allowed(gateway, invited.upper(), store)
    assert not permanent_account_access_allowed(gateway, "x" + invited, store)
    assert not permanent_account_access_allowed(gateway, "not-an-address", store)


def test_expired_and_revoked_invites_admit_no_one(switch_on) -> None:  # noqa: ANN001
    store, space = _business()
    gateway = _allowlist()
    invited = fake.email().lower()
    _, listed = store.give(space, OWNER, invited)
    store.revoke_invite(space, OWNER, listed.invites[0].id)
    assert not permanent_account_access_allowed(gateway, invited, store)

    _, listed = store.give(space, OWNER, invited)
    invite = next(i for i in store._invites if i["id"] == listed.invites[0].id)
    invite["expires_at"] = store._now() - timedelta(seconds=1)
    assert not permanent_account_access_allowed(gateway, invited, store)


def test_acceptance_moves_admission_to_the_grant_until_revoked(switch_on) -> None:  # noqa: ANN001
    store, space = _business()
    gateway = _allowlist()
    person, invited = str(uuid4()), fake.email().lower()
    store.confirm(person, invited)
    _, listed = store.give(space, OWNER, invited)
    grant_id = store.accept_invite(person, space, listed.invites[0].id)
    assert store.list(space, OWNER).invites == ()
    assert permanent_account_access_allowed(gateway, invited, store)

    assert store.revoke_grant(space, OWNER, grant_id) == "revoked"
    assert not permanent_account_access_allowed(gateway, invited, store)


def test_a_disabled_row_refuses_and_a_hand_listed_email_stays(switch_on) -> None:  # noqa: ANN001
    store, space = _business()
    disabled, listed_by_hand = fake.email().lower(), fake.email().lower()
    gateway = _allowlist(listed={listed_by_hand}, disabled={disabled})
    store.give(space, OWNER, disabled)
    assert not permanent_account_access_allowed(gateway, disabled, store)

    _, listed = store.give(space, OWNER, listed_by_hand)
    store.revoke_invite(space, OWNER, listed.invites[0].id)
    assert permanent_account_access_allowed(gateway, listed_by_hand, store)


def test_open_signup_and_a_missing_store_keep_the_old_rule(monkeypatch) -> None:  # noqa: ANN001
    store, space = _business()
    disabled, invited = fake.email().lower(), fake.email().lower()
    gateway = _allowlist(disabled={disabled})
    store.give(space, OWNER, invited)
    store.give(space, OWNER, disabled)

    monkeypatch.setenv(SWITCH, "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    assert permanent_account_access_allowed(gateway, fake.email(), store)
    assert not permanent_account_access_allowed(gateway, disabled, store)

    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "false")
    assert not permanent_account_access_allowed(gateway, invited, None)


def test_an_invited_person_signs_in_accepts_and_loses_access_on_revoke(
    biz: TestClient,
    identities,
    gateway,
    switch_on,  # noqa: ANN001
) -> None:
    alice = Owner(biz, ALICE, identities[ALICE]["id"])
    bob = Owner(biz, BOB, identities[BOB]["id"])
    gateway.private_alpha_email_allowed.side_effect = (
        lambda email: email == identities[ALICE]["email"]
    )
    gateway.login.return_value = {
        "session": {"access_token": "t", "refresh_token": "r", "expires_in": 3600},
        "user": {"id": identities[BOB]["id"], "email": identities[BOB]["email"]},
    }
    login = {
        "email": identities[BOB]["email"],
        "password": fake.password(),
        "captcha_token": "captcha-proof",
    }

    refused = bob.get("/invitations")
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "private_alpha_access_required"
    assert biz.post("/api/v1/auth/login", json=login).status_code == 401
    gateway.login.assert_not_called()

    assert alice.start({"name": "Colmado La Esquina"}).status_code == 201
    invited = alice.post("/access", {"email": identities[BOB]["email"].upper()})
    assert invited.status_code == 201, invited.text
    assert biz.post("/api/v1/auth/login", json=login).status_code == 200
    business_access().confirm(bob.person, identities[BOB]["email"])
    seen = bob.get("/invitations")
    assert seen.status_code == 200, seen.text
    assert [i["space_id"] for i in seen.json()] == [alice.scope().owner.space_id]

    accepted = bob.post(
        f"/invitations/{seen.json()[0]['id']}/accept",
        {"space_id": alice.scope().owner.space_id},
    )
    assert accepted.status_code == 200, accepted.text
    assert bob.get("/invitations").json() == []

    grants = alice.get("/access").json()["grants"]
    member = next(g for g in grants if not g["owner"])
    gone = biz.delete(f"{BASE}/access/grants/{member['id']}", headers=alice.auth)
    assert gone.status_code == 204, gone.text
    assert bob.get("/invitations").status_code == 403
    assert biz.post("/api/v1/auth/login", json=login).status_code == 401


def test_a_closed_business_admits_no_invitee_and_no_grantee(switch_on) -> None:  # noqa: ANN001
    store, space = _business()
    gateway = _allowlist()
    person, member, invited = str(uuid4()), fake.email().lower(), fake.email().lower()
    store.confirm(person, member)
    _, listed = store.give(space, OWNER, member)
    store.accept_invite(person, space, listed.invites[0].id)
    store.give(space, OWNER, invited)
    assert permanent_account_access_allowed(gateway, member, store)
    assert permanent_account_access_allowed(gateway, invited, store)

    store.close(space)
    assert not permanent_account_access_allowed(gateway, member, store)
    assert not permanent_account_access_allowed(gateway, invited, store)


def test_an_invited_person_cannot_start_a_business_or_admit_anyone(
    biz: TestClient,
    identities,
    gateway,
    switch_on,  # noqa: ANN001
) -> None:
    alice = Owner(biz, ALICE, identities[ALICE]["id"])
    bob = Owner(biz, BOB, identities[BOB]["id"])
    gateway.private_alpha_email_allowed.side_effect = (
        lambda email: email == identities[ALICE]["email"]
    )
    assert alice.start({"name": "Colmado La Esquina"}).status_code == 201
    assert alice.post("/access", {"email": identities[BOB]["email"]}).status_code == 201
    business_access().confirm(bob.person, identities[BOB]["email"])

    def refused(response) -> None:  # noqa: ANN001
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "private_alpha_access_required"

    refused(bob.start({"name": "Mi Negocio"}))
    [invitation] = bob.get("/invitations").json()
    accepted = bob.post(
        f"/invitations/{invitation['id']}/accept",
        {"space_id": alice.scope().owner.space_id},
    )
    assert accepted.status_code == 200, accepted.text
    refused(bob.start({"name": "Mi Negocio"}))
    refused(bob.post("/spaces", {"name": "Otro", "country": "DO"}, key=str(uuid4())))

    [membership] = bob.get("/spaces").json()["spaces"]
    promoted = biz.patch(
        f"{BASE}/access/grants/{membership['grant_id']}",
        json={"role": "admin"},
        headers=alice.auth,
    )
    assert promoted.status_code == 200, promoted.text
    [upgrade] = bob.get("/invitations").json()
    assert (
        bob.post(
            f"/invitations/{upgrade['id']}/accept",
            {"space_id": alice.scope().owner.space_id},
        ).status_code
        == 200
    )
    acting = {"X-Business-Grant": membership["grant_id"]}
    assert biz.get(f"{BASE}/access", headers={**bob.auth, **acting}).status_code == 200
    stranger = fake.email().lower()
    refused(bob.post("/access", {"email": stranger}, **acting))
    refused(
        bob.post(
            "/access/invitations",
            {"recipients": [{"email": stranger, "role": "editor", "command_key": "k1"}]},
            **acting,
        )
    )
    assert not permanent_account_access_allowed(gateway, stranger, business_access())
    assert alice.start().status_code == 200


def test_the_switch_is_off_unless_its_cuadrao_name_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SWITCH, raising=False)
    assert business_invite_admission_enabled() is False
    monkeypatch.setenv("ARGUS_BUSINESS_INVITE_ADMISSION_ENABLED", "true")
    assert business_invite_admission_enabled() is False
    for value, enabled in (
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("", False),
        ("maybe", False),
    ):
        monkeypatch.setenv(SWITCH, value)
        assert business_invite_admission_enabled() is enabled, value


@pytest.mark.parametrize("public_access", ["true", "false"])
def test_with_the_switch_off_the_gate_is_the_rule_before_this_switch(
    public_access: str,
    switch_off,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001
) -> None:
    """Off, every email gets the answer the gate gave before invitations could
    admit anyone: open sign-up refuses only a disabled row, closed sign-up
    admits only a listed one. The Business store is never asked, and the
    allowlist is read exactly as before, so a store passed in changes nothing."""

    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", public_access)
    store, space = _business()
    listed, disabled, invited, member, stranger = (fake.email().lower() for _ in range(5))
    person = str(uuid4())
    store.confirm(person, member)
    _, given = store.give(space, OWNER, member)
    store.accept_invite(person, space, given.invites[0].id)
    store.give(space, OWNER, invited)
    store.give(space, OWNER, disabled)
    gateway = Mock(wraps=_allowlist(listed={listed}, disabled={disabled}))
    business = Mock(wraps=store)

    for email in (listed, disabled, invited, member, stranger):
        before = email != disabled if public_access == "true" else email == listed
        assert permanent_account_access_allowed(gateway, email, business) is before, email
        assert permanent_account_access_allowed(gateway, email, None) is before, email
    business.admits_email.assert_not_called()
    if public_access == "false":
        gateway.private_alpha_email_disabled.assert_not_called()


def test_with_the_switch_off_an_invitation_admits_no_one_and_the_owner_keeps_every_power(
    biz: TestClient,
    identities,
    gateway,
    switch_off,  # noqa: ANN001
) -> None:
    """The walk before this switch: the person the owner invited is refused at
    login and on every request, and the hand-listed owner starts, adds, invites
    and resends with nothing new in the way."""

    alice = Owner(biz, ALICE, identities[ALICE]["id"])
    bob = Owner(biz, BOB, identities[BOB]["id"])
    gateway.private_alpha_email_allowed.side_effect = (
        lambda email: email == identities[ALICE]["email"]
    )
    gateway.login.return_value = {
        "session": {"access_token": "t", "refresh_token": "r", "expires_in": 3600},
        "user": {"id": identities[BOB]["id"], "email": identities[BOB]["email"]},
    }
    login = {
        "email": identities[BOB]["email"],
        "password": fake.password(),
        "captcha_token": "captcha-proof",
    }

    assert alice.start({"name": "Colmado La Esquina"}).status_code == 201
    invited = alice.post("/access", {"email": identities[BOB]["email"]})
    assert invited.status_code == 201, invited.text
    assert not permanent_account_access_allowed(
        gateway, identities[BOB]["email"], business_access()
    )
    assert biz.post("/api/v1/auth/login", json=login).status_code == 401
    gateway.login.assert_not_called()
    refused = bob.get("/invitations")
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "private_alpha_access_required"
    assert bob.start({"name": "Mi Negocio"}).status_code == 403

    assert alice.start().status_code == 200
    added = alice.post("/spaces", {"name": "Otro", "country": "DO"}, key=str(uuid4()))
    assert added.status_code == 201, added.text
    many = alice.post(
        "/access/invitations",
        {
            "recipients": [
                {"email": fake.email().lower(), "role": "editor", "command_key": "k1"}
            ]
        },
    )
    assert many.status_code == 200, many.text
    [pending] = [
        i for i in invited.json()["invites"] if i["email"] == identities[BOB]["email"]
    ]
    expired = next(i for i in business_access()._invites if i["id"] == pending["id"])
    expired["expires_at"] = business_access()._now() - timedelta(seconds=1)
    resent = alice.post(f"/access/invites/{pending['id']}/resend")
    assert resent.status_code == 200, resent.text


def test_with_the_switch_off_the_standing_check_never_refuses_a_person_the_gate_admitted(
    biz: TestClient,
    identities,
    gateway,
    switch_off,  # noqa: ANN001
) -> None:
    """The gate reads the Auth email and the standing check reads the profile
    email. Off, the check is inert, so a person the gate admits starts a
    Business even when the two emails differ."""

    alice = Owner(biz, ALICE, identities[ALICE]["id"])
    gateway.private_alpha_email_allowed.side_effect = (
        lambda email: email == identities[ALICE]["email"]
    )
    gateway.get_or_create_profile_for_auth_user.side_effect = lambda auth_user: (
        _profile(auth_user["id"], fake.email().lower())
    )

    assert alice.get("/space").status_code == 404
    assert alice.start({"name": "Colmado La Esquina"}).status_code == 201
