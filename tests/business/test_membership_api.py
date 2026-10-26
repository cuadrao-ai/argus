from uuid import uuid4

import pytest
from argus.api.business_spaces import business_access
from fastapi.testclient import TestClient

from tests.business import test_business_api as api_fixtures
from tests.business.conftest import ALICE
from tests.business.test_business_api import Owner

bob = api_fixtures.bob


@pytest.fixture
def alice(biz: TestClient, identities) -> Owner:
    owner = Owner(biz, ALICE, identities[ALICE]["id"])
    assert owner.start({"name": "Colmado"}).status_code == 201
    return owner


def join(alice, bob, role):
    store = business_access()
    store.confirm(bob.person, "member@example.test")
    response = alice.post("/access", {"email": "member@example.test", "role": role})
    assert response.status_code == 201, response.text
    invite = response.json()["invites"][0]
    assert all(
        s["space_id"] != alice.scope().owner.space_id
        for s in bob.get("/spaces").json()["spaces"]
    )
    accepted = bob.post(
        f"/invitations/{invite['id']}/accept", {"space_id": alice.scope().owner.space_id}
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()["grant_id"]


@pytest.mark.parametrize("role", ["owner", "admin", "editor", "viewer"])
def test_roles_require_explicit_recipient_acceptance(alice, bob, role):
    grant = join(alice, bob, role)
    selected = {**bob.auth, "X-Business-Grant": grant}
    listing = next(
        s for s in bob.get("/spaces").json()["spaces"] if s["grant_id"] == grant
    )
    assert listing["business_role"] == role
    assert listing["role"] == ("owner" if role == "owner" else "accountant")
    assert (
        bob.client.get("/api/v1/business/space", headers=selected).json()["id"]
        == alice.scope().owner.space_id
    )
    manage = bob.client.get("/api/v1/business/access", headers=selected)
    assert manage.status_code == (200 if role in ("owner", "admin") else 403)
    raw = bob.client.get(f"/api/v1/business/receipts/{uuid4()}/source", headers=selected)
    assert raw.status_code == (403 if role == "viewer" else 404)


def test_coowner_selected_space_never_changes_default_business(alice, bob):
    grant = join(alice, bob, "owner")
    assert bob.start({"name": "Otro"}).status_code in (200, 201)
    default_name = bob.get("/space").json()["name"]
    default = bob.get("/space").json()["id"]
    selected = {**bob.auth, "X-Business-Grant": grant}
    first = alice.scope().owner.space_id
    assert first != default
    assert (
        bob.client.get("/api/v1/business/space", headers=selected).json()["id"] == first
    )
    renamed = bob.client.patch(
        "/api/v1/business/space/name",
        headers=selected,
        json={"space_id": first, "name": "Nombre compartido"},
    )
    assert renamed.status_code == 200, renamed.text
    assert alice.get("/space").json()["name"] == "Nombre compartido"
    assert bob.get("/space").json()["name"] == default_name


def test_batch_partial_send_retries_only_unsent(alice, monkeypatch):
    sent = []

    def send(**kwargs):
        email = kwargs["invite"].email
        sent.append(email)
        if email == "second@example.test" and sent.count(email) == 1:
            from smtplib import SMTPDataError

            raise SMTPDataError(550, b"synthetic transport refusal")
        return "synthetic-id"

    monkeypatch.setattr("argus.api.business_invite_delivery.send_invite_email", send)
    monkeypatch.setattr(
        "argus.api.business_invite_delivery.setting_value",
        lambda key: "true"
        if key == "BUSINESS_INVITE_EMAIL_ENABLED"
        else "https://example.test",
    )
    body = {
        "recipients": [
            {"email": f"{name}@example.test", "role": "viewer", "command_key": name}
            for name in ("first", "second")
        ]
    }
    first = alice.post("/access/invitations", body)
    assert first.status_code == 200, first.text
    assert [r["delivery"] for r in first.json()["results"]] == ["accepted", "failed"]
    second = alice.post("/access/invitations", body)
    assert second.status_code == 200, second.text
    assert [r["delivery"] for r in second.json()["results"]] == ["accepted", "accepted"]
    assert sent == ["first@example.test", "second@example.test", "second@example.test"]
    invitation = second.json()["results"][0]["invite_id"]
    assert (
        alice.client.delete(
            f"/api/v1/business/access/invites/{invitation}", headers=alice.auth
        ).status_code
        == 204
    )
    stale = alice.post("/access/invitations", body)
    assert stale.json()["results"][0]["state"] == "revoked"
    assert len(sent) == 3


def test_viewer_reads_receipt_metadata_but_cannot_read_original_or_use_personal_route(
    alice, bob, monkeypatch
):
    from argus.api.documents import documents_service

    receipt = alice.upload(consent=False).json()["id"]
    grant = join(alice, bob, "viewer")
    selected = {**bob.auth, "X-Business-Grant": grant}
    metadata = bob.client.get(f"/api/v1/business/receipts/{receipt}", headers=selected)
    assert metadata.status_code == 200, metadata.text
    assert "source_url" not in metadata.json() and "download_url" not in metadata.json()
    objects = documents_service().store.objects
    monkeypatch.setattr(
        objects,
        "get",
        lambda *args: pytest.fail("Viewer reached original object storage"),
    )
    original = bob.client.get(
        f"/api/v1/business/receipts/{receipt}/source", headers=selected
    )
    assert original.status_code == 403
    personal = bob.client.get(
        f"/api/v1/financial-documents/{receipt}/source", headers=bob.auth
    )
    assert personal.status_code == 404


def test_coowner_reading_consent_is_explicit_and_stops_with_role_loss(alice, bob):
    grant = join(alice, bob, "owner")
    selected = {**bob.auth, "X-Business-Grant": grant}
    before = bob.client.get("/api/v1/business/receipt-reading", headers=selected).json()
    assert before["can_change"] and not before["enabled"]
    body = {
        "enabled": True,
        "scope_version": 1,
        "disclosure_token": before["disclosure_token"],
    }
    changed = bob.client.post(
        "/api/v1/business/receipt-reading",
        headers={**selected, "Idempotency-Key": "coowner-reading"},
        json=body,
    )
    assert changed.status_code == 200 and changed.json()["enabled"], changed.text
    assert alice.get("/receipt-reading").json()["enabled"]
    demoted = alice.client.patch(
        f"/api/v1/business/access/grants/{grant}",
        headers=alice.auth,
        json={"role": "editor"},
    )
    assert demoted.status_code == 200
    assert not alice.get("/receipt-reading").json()["enabled"]
    replay = bob.client.post(
        "/api/v1/business/receipt-reading",
        headers={**selected, "Idempotency-Key": "coowner-reading"},
        json=body,
    )
    assert replay.status_code == 403


@pytest.mark.parametrize(
    "current,requested,pending",
    [
        ("viewer", "admin", True),
        ("editor", "admin", True),
        ("admin", "owner", True),
        ("viewer", "editor", False),
        ("owner", "admin", False),
    ],
)
def test_existing_member_promotion_acceptance_boundary(
    alice, bob, current, requested, pending
):
    grant = join(alice, bob, current)
    changed = alice.client.patch(
        f"/api/v1/business/access/grants/{grant}",
        headers=alice.auth,
        json={"role": requested},
    )
    assert changed.status_code == 200, changed.text
    membership = next(g for g in changed.json()["grants"] if g["id"] == grant)
    assert membership["business_role"] == (current if pending else requested)
    if pending:
        invitation = changed.json()["invites"][0]
        accepted = bob.post(
            f"/invitations/{invitation['id']}/accept",
            {"space_id": alice.scope().owner.space_id},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["grant_id"] == grant
        assert business_access().granted(bob.person, grant).business_role == requested
    else:
        assert changed.json()["invites"] == []


@pytest.mark.parametrize("role", ["editor", "viewer"])
@pytest.mark.parametrize("path", ["/space", "/space/name"])
def test_name_routes_refuse_live_non_managers_but_hide_foreign_scope(
    alice, bob, role, path
):
    grant = join(alice, bob, role)
    headers = {**bob.auth, "X-Business-Grant": grant}
    body = {"name": "Changed"}
    if path.endswith("/name"):
        body["space_id"] = alice.scope().owner.space_id
    refused = bob.client.patch("/api/v1/business" + path, json=body, headers=headers)
    assert refused.status_code == 403
    assert refused.json()["code"] == "business_permission_denied"
    if path.endswith("/name"):
        body["space_id"] = str(uuid4())
        missing = bob.client.patch("/api/v1/business" + path, json=body, headers=headers)
        assert missing.status_code == 404
        assert missing.json()["code"] == "business_space_missing"
    assert alice.get("/space").json()["name"] == "Colmado"


@pytest.mark.parametrize("state", ["owner", "viewer", "revoked"])
def test_default_business_bootstrap_rechecks_live_membership(alice, bob, state):
    from copy import deepcopy

    from argus.api.business_spaces import business_spaces

    access = business_access()
    spaces = business_spaces()
    space = alice.scope().owner.space_id
    join(alice, bob, "owner")
    owner = next(
        g.id
        for g in access.list(space, bob.person).grants
        if g.grantee_id == alice.person
    )
    if state == "revoked":
        access.revoke_grant(space, bob.person, owner)
    elif state == "viewer":
        access.change_role(space, bob.person, owner, state)
    before = deepcopy((spaces._spaces, access._grants, access.ledger))
    replay = alice.start({"name": "Do not replace", "country": "DO"})
    assert (spaces._spaces, access._grants, access.ledger) == before
    if state == "revoked":
        assert replay.status_code == 404
        assert replay.json()["code"] == "business_record_not_found"
        assert "id" not in replay.json() and "name" not in replay.json()
        assert access.capabilities(space, alice.person) == ()
    else:
        assert replay.status_code == 200
        assert replay.json()["id"] == space
        assert replay.json()["name"] == "Colmado"
        assert access.granted(alice.person, owner).business_role == state
