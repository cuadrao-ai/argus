"""The receiving webhook and the owner's address endpoints, through the real app."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.api import email_intake as runtime_module
from argus.domain.ingestion.email_intake.store import InMemoryEmailStore
from fastapi.testclient import TestClient

from tests.business.test_business_api import Owner, alice  # noqa: F401

UNREADABLE = (
    Path(__file__).parents[1] / "document_extraction_fixtures/unreadable.png"
).read_bytes()
SECRET_KEY = b"synthetic-webhook-secret"
SECRET = "whsec_" + base64.b64encode(SECRET_KEY).decode()
WEBHOOK = "/api/v1/webhooks/resend"


def signed(body: bytes, *, now: int | None = None) -> dict[str, str]:
    stamp = str(now or int(time.time()))
    digest = base64.b64encode(
        hmac.digest(SECRET_KEY, f"msg_1.{stamp}.".encode() + body, hashlib.sha256)
    ).decode()
    return {"svix-id": "msg_1", "svix-timestamp": stamp, "svix-signature": "v1," + digest}


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("ARGUS_RESEND_WEBHOOK_SECRET", SECRET)
    fake = Mock()
    fake.store = InMemoryEmailStore()
    fake.provider = object()
    fake.enabled = lambda: True
    fake.route_usable = lambda route: True
    fake.retryable = lambda delivery: False
    runtime_module.configure_email_intake(fake)
    monkeypatch.setattr("argus.api.routers.email_intake.webhook_enabled", lambda: True)
    yield fake
    runtime_module.configure_email_intake(None)


def event(**overrides) -> bytes:
    body = {
        "type": "email.received",
        "data": {
            "email_id": str(uuid4()),
            "to": ["Recibos-AB12@Example.test", "recibos-ab12@example.test"],
        },
    }
    body.update(overrides)
    return json.dumps(body).encode()


def test_signed_received_event_is_recorded_once_with_normalized_recipients(
    client: TestClient, runtime
) -> None:  # noqa: F811
    body = event()
    response = client.post(
        WEBHOOK,
        content=body,
        headers={**signed(body), "Content-Type": "application/json"},
    )
    assert response.status_code == 202, response.text
    assert response.headers["cache-control"] == "no-store"
    email_id = json.loads(body)["data"]["email_id"]
    runtime.enqueue_resend.assert_called_once_with(
        email_id, ("recibos-ab12@example.test",)
    )


def test_bad_signature_other_event_and_oversize_body_never_enqueue(
    client: TestClient, runtime
) -> None:  # noqa: F811
    body = event()
    assert (
        client.post(WEBHOOK, content=body, headers=signed(body + b" ")).status_code == 401
    )
    assert (
        client.post(
            WEBHOOK, content=body, headers=signed(body, now=int(time.time()) - 900)
        ).status_code
        == 401
    )
    assert client.post(WEBHOOK, content=body).status_code == 401
    other = event(type="email.delivered")
    assert client.post(WEBHOOK, content=other, headers=signed(other)).status_code == 204
    malformed = json.dumps({"type": "email.received", "data": {"to": []}}).encode()
    assert (
        client.post(WEBHOOK, content=malformed, headers=signed(malformed)).status_code
        == 400
    )
    huge = b"{" + b" " * (64 * 1024) + b"}"
    assert client.post(WEBHOOK, content=huge, headers=signed(huge)).status_code == 413
    runtime.enqueue_resend.assert_not_called()


def test_webhook_is_absent_when_receiving_is_off(
    client: TestClient, runtime, monkeypatch
) -> None:  # noqa: F811
    monkeypatch.setattr("argus.api.routers.email_intake.webhook_enabled", lambda: False)
    body = event()
    assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 404
    runtime_module.configure_email_intake(None)
    monkeypatch.setattr("argus.api.routers.email_intake.webhook_enabled", lambda: True)
    assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 404


def test_owner_sees_readiness_and_in_memory_app_cannot_mint_an_address(
    alice: Owner,  # noqa: F811
    runtime,  # noqa: F811
) -> None:  # noqa: F811
    status = alice.get("/email")
    assert status.status_code == 200, status.text
    assert status.json() == {"enabled": False, "receiving_address": None}
    assert alice.get("/email/deliveries").json() == {"items": []}
    assert alice.get(f"/email/deliveries/{uuid4()}").status_code == 404
    created = alice.post("/email", key=str(uuid4()))
    assert (created.status_code, created.json()["code"]) == (
        503,
        "email_receiving_unconfigured",
    )


def test_endpoints_say_unavailable_without_a_runtime(alice: Owner) -> None:  # noqa: F811
    runtime_module.configure_email_intake(None)
    assert alice.get("/email").status_code == 503
    assert alice.get("/email/deliveries").status_code == 503


def test_a_grouped_email_original_is_context_not_a_second_receipt(
    alice: Owner,  # noqa: F811
    runtime,  # noqa: ANN001
) -> None:
    """The .eml of an email whose attachment is saved can be seen and downloaded,
    never prepared, entered by hand or confirmed."""

    original = alice.upload(consent=False, name="forwarded.eml")
    attachment = alice.upload(content=UNREADABLE, consent=False, name="recibo.png")
    assert (original.status_code, attachment.status_code) == (200, 200), attachment.text
    original_id, attachment_id = original.json()["id"], attachment.json()["id"]
    space_id = alice.scope().owner.space_id
    store = runtime.store
    route = store.create_route(
        recipient="recibos-00000001@recibos.example.test",
        space_id=space_id,
        principal_id=alice.scope().person_id,
        granted_by=alice.scope().person_id,
        grant_id=str(uuid4()),
    )
    delivery = store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=space_id,
        principal_id=route.principal_id,
    )
    claimed = store.claim()
    store.update(claimed, original_document_id=original_id, subject="Factura 0041")
    from argus.domain.ingestion.email_intake.models import EmailDeliveryPart

    store.put_part(
        claimed,
        EmailDeliveryPart(
            "1.2", "recibo.png", "image/png", "captured", attachment_id, None
        ),
    )
    store.finish(claimed, "captured")

    listed = {
        item["id"]: item for item in alice.get("/receipts", view="all").json()["items"]
    }
    assert listed[original_id]["email_original"] is True
    assert listed[original_id]["email_delivery_ids"] == [delivery.id]
    assert (listed[original_id]["preparable"], listed[original_id]["enterable"]) == (
        False,
        False,
    )
    assert listed[attachment_id]["email_original"] is False
    assert listed[attachment_id]["email_delivery_ids"] == [delivery.id]
    assert listed[attachment_id]["preparable"] is True
    detail = alice.detail(original_id)
    assert detail["email_original"] is True

    refused = [
        alice.post(
            f"/receipts/{original_id}/prepare", **{"X-Extraction-Consent": "true"}
        ),
        alice.review(original_id, 0, merchant="Nadie"),
        alice.confirm(original_id, 0, str(uuid4())),
    ]
    assert [(r.status_code, r.json()["code"]) for r in refused] == [
        (409, "email_original_not_a_receipt")
    ] * 3
    assert alice.get(f"/receipts/{original_id}/source").status_code == 200
    searched = {
        item["id"]: item
        for item in alice.get("/search", q="forwarded").json()["receipts"]
    }
    assert searched[original_id]["email_original"] is True
    # The attachment is the receipt: it still prepares.
    prepared = alice.post(
        f"/receipts/{attachment_id}/prepare", **{"X-Extraction-Consent": "true"}
    )
    assert prepared.status_code == 200, prepared.text
