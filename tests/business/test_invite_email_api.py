# ruff: noqa: F811
from datetime import datetime, timedelta

import pytest
from argus.api.business_spaces import business_access

from tests.business.test_business_access_api import ALICE, alice  # noqa: F401
from tests.business.test_business_api import Owner, bob  # noqa: F401


@pytest.fixture(autouse=True)
def owner_email(request: pytest.FixtureRequest) -> None:
    """The in-memory twin learns the owner's email as the auth row holds it:
    an owner with no name is named by it in the invitation."""

    if "alice" in request.fixturenames:
        owner = request.getfixturevalue("alice")
        email = request.getfixturevalue("identities")[ALICE]["email"]
        business_access().confirm(owner.person, email)


@pytest.fixture(autouse=True)
def invitations_admission_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")


def _after_the_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    store = business_access()
    now = store._now() + timedelta(seconds=61)
    monkeypatch.setattr(store, "_now", lambda: now)


def test_configured_create_and_resend_call_actual_adapter_with_canonical_labels(
    alice: Owner, monkeypatch
):
    sent = []
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    monkeypatch.setattr(
        "argus.domain.business.invite_email.send_resend_email",
        lambda **message: sent.append(message) or "fake-receipt",
    )
    first = alice.post("/access", {"email": "Contadora@example.test"})
    assert first.status_code == 201
    assert first.json()["invite_delivery"] == "accepted"
    invite = first.json()["invites"][0]
    assert sent[0]["recipient"] == "contadora@example.test"
    assert "Colmado La Esquina" in sent[0]["subject"]
    # The owner set no name: their email names them.
    assert f"{ALICE}@example.test" in sent[0]["subject"]
    assert "https://app.example.test/" in sent[0]["html"]
    assert "token" not in sent[0]["html"]
    assert alice.post("/access", {"email": invite["email"]}).status_code == 200
    alice.get("/access")
    assert len(sent) == 1
    _after_the_cooldown(monkeypatch)
    again = alice.post(f"/access/invites/{invite['id']}/resend")
    assert again.status_code == 200
    assert again.json()["invite_delivery"] == "accepted"
    assert len(sent) == 2
    expiry = datetime.fromisoformat(
        again.json()["invites"][0]["expires_at"].replace("Z", "+00:00")
    )
    created = datetime.fromisoformat(
        again.json()["invites"][0]["created_at"].replace("Z", "+00:00")
    )
    assert expiry - created == timedelta(days=7)


def test_transport_rejection_reports_failure_and_explicit_resend_can_retry(
    alice: Owner, monkeypatch
):
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    from smtplib import SMTPDataError

    def reject(**message):
        raise SMTPDataError(550, b"synthetic rejection")

    monkeypatch.setattr("argus.domain.business.invite_email.send_resend_email", reject)
    first = alice.post("/access", {"email": "contadora@example.test"})
    assert first.status_code == 201
    assert first.json()["invite_delivery"] == "failed"
    invite = first.json()["invites"][0]
    monkeypatch.setattr(
        "argus.domain.business.invite_email.send_resend_email",
        lambda **message: "fake-receipt",
    )
    _after_the_cooldown(monkeypatch)
    again = alice.post(f"/access/invites/{invite['id']}/resend")
    assert again.json()["invite_delivery"] == "accepted"


def test_foreign_and_revoked_invite_cannot_resend(alice: Owner, bob: Owner):
    first = alice.post("/access", {"email": "contadora@example.test"})
    invite = first.json()["invites"][0]
    # Bob's own Business has no name yet, which refuses before the invite is looked up.
    foreign = bob.post(f"/access/invites/{invite['id']}/resend")
    assert (foreign.status_code, foreign.json()["code"]) == (409, "business_name_required")
    alice.client.delete(
        f"/api/v1/business/access/invites/{invite['id']}", headers=alice.auth
    )
    assert alice.post(f"/access/invites/{invite['id']}/resend").status_code == 404


def test_enabled_delivery_sends_without_a_postal_address(alice: Owner, monkeypatch):
    sent = []
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    monkeypatch.delenv("MARKETING_POSTAL_ADDRESS", raising=False)
    monkeypatch.setattr(
        "argus.domain.business.invite_email.send_resend_email",
        lambda **message: sent.append(message) or "fake-receipt",
    )
    first = alice.post("/access", {"email": "contadora@example.test"})
    assert first.status_code == 201
    assert first.json()["invite_delivery"] == "accepted"
    assert len(sent) == 1
    assert ">Cuadrao LLC</p>" in sent[0]["html"]
    assert sent[0]["plain_text"].rstrip().endswith("Cuadrao LLC")
    assert "Cuadrao LLC," not in sent[0]["html"] + sent[0]["plain_text"]
    assert "Salir de la lista" not in sent[0]["html"] + sent[0]["plain_text"]


def test_transport_timeout_stays_uncertain_until_an_explicit_resend(alice, monkeypatch):
    calls = []
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")

    def timeout(**message):
        calls.append(message)
        raise TimeoutError("synthetic lost response")

    monkeypatch.setattr("argus.domain.business.invite_email.send_resend_email", timeout)
    first = alice.post("/access", {"email": "contadora@example.test"})
    assert first.json()["invite_delivery"] == "uncertain"
    invite = first.json()["invites"][0]
    replay = alice.post("/access", {"email": invite["email"]})
    assert replay.json()["invite_delivery"] == "uncertain"
    assert len(calls) == 1
    _after_the_cooldown(monkeypatch)
    again = alice.post(f"/access/invites/{invite['id']}/resend")
    assert again.json()["invite_delivery"] == "uncertain"
    assert len(calls) == 2
