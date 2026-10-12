"""The receiving webhook and the owner's address endpoints, through the real app."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.api import email_intake as runtime_module
from argus.domain.ingestion.email_intake.store import InMemoryEmailStore
from fastapi.testclient import TestClient

from tests.business.test_business_api import Owner, alice  # noqa: F401

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
