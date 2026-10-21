# ruff: noqa: F811
from datetime import datetime, timedelta

from tests.business.test_business_access_api import alice  # noqa: F401
from tests.business.test_business_api import Owner, bob  # noqa: F401


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
    assert "Member" in sent[0]["subject"]
    assert "https://app.example.test/" in sent[0]["html"]
    assert "token" not in sent[0]["html"]
    assert alice.post("/access", {"email": invite["email"]}).status_code == 200
    alice.get("/access")
    assert len(sent) == 1
    again = alice.post(f"/access/invites/{invite['id']}/resend")
    assert again.status_code == 200
    assert again.json()["invite_delivery"] == "accepted"
    assert len(sent) == 2
    assert sent[0]["idempotency_key"] != sent[1]["idempotency_key"]
    expiry = datetime.fromisoformat(
        again.json()["invites"][0]["expires_at"].replace("Z", "+00:00")
    )
    created = datetime.fromisoformat(
        again.json()["invites"][0]["created_at"].replace("Z", "+00:00")
    )
    assert expiry - created == timedelta(days=7)


def test_missing_provider_config_reports_failure_and_explicit_resend_can_retry(
    alice: Owner, monkeypatch
):
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    monkeypatch.setenv("ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD", "")
    first = alice.post("/access", {"email": "contadora@example.test"})
    assert first.status_code == 201
    assert first.json()["invite_delivery"] == "failed"
    invite = first.json()["invites"][0]
    monkeypatch.setattr(
        "argus.domain.business.invite_email.send_resend_email",
        lambda **message: "fake-receipt",
    )
    again = alice.post(f"/access/invites/{invite['id']}/resend")
    assert again.json()["invite_delivery"] == "accepted"


def test_foreign_and_revoked_invite_cannot_resend(alice: Owner, bob: Owner):
    first = alice.post("/access", {"email": "contadora@example.test"})
    invite = first.json()["invites"][0]
    assert bob.post(f"/access/invites/{invite['id']}/resend").status_code == 404
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
