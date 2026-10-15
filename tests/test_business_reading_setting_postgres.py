"""The owner's stored receipt-reading setting decides every Business read, over
HTTP on the real app, Auth and Postgres: a read in flight stops when the owner
turns reading off, an email receipt is read only while it is on, and a legacy
prepare is refused while it is off. A local stub stands in for the provider."""

from __future__ import annotations

import asyncio
import json
import os
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.api.documents import documents_service
from argus.api.email_intake import _read_receipt, configure_email_intake
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.domain.ingestion.email_intake.provider import ReceivedEmail
from argus.domain.ingestion.email_intake.service import (
    EmailCapture,
    grant_route_authority,
)
from argus.domain.ingestion.email_intake.store import PostgresEmailStore
from fastapi.testclient import TestClient
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.business.receipt_stub import ReceiptStub
from tests.business.test_business_api import RECEIPT
from tests.business.test_business_email_api import SECRET, WEBHOOK, signed
from tests.local_supabase_support import local_supabase_gateway
from tests.test_business_scope_switch_routes_postgres import API, ENV, _person

pytestmark = pytest.mark.skipif(
    not (shared.DSN and os.getenv("ARGUS_LOCAL_SUPABASE_URL")),
    reason="local Supabase proof variables are not configured",
)
ROUTE = {
    "gateway": "fixture",
    "interpretation": [{"model": "fixture-reader"}],
    "reply": [],
}


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Alice owns a Business; the provider is a counting local stub."""

    auth_router.reset_auth_attempt_limiter_for_tests()
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    gateway = local_supabase_gateway()
    created: list[str] = []
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", shared.DSN),
            patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            documents = documents_service()
            stub = ReceiptStub()
            monkeypatch.setattr(documents, "extractor", stub)
            monkeypatch.setattr(
                documents.business_receipt_consent, "route_resolver", lambda: ROUTE
            )
            monkeypatch.setattr(
                "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
                lambda: ROUTE,
            )
            alice = _person(client, gateway, "alice", created)
            started = client.post(f"{API}/business/space", json={}, headers=alice.headers)
            assert started.status_code == 201, started.text
            alice.space_id = started.json()["id"]
            yield SimpleNamespace(
                client=client, alice=alice, documents=documents, stub=stub
            )
    finally:
        configure_email_intake(None)
        for user_id in created:
            try:
                gateway.delete_auth_user(user_id)
            except Exception:  # noqa: BLE001
                pass


def _reading(world, enabled: bool):  # noqa: ANN001, ANN202
    shown = world.client.get(
        f"{API}/business/receipt-reading", headers=world.alice.headers
    )
    assert shown.status_code == 200, shown.text
    return world.client.post(
        f"{API}/business/receipt-reading",
        json={
            "enabled": enabled,
            "scope_version": 1,
            "disclosure_token": shown.json()["disclosure_token"],
        },
        headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
    )


def _upload(world, content: bytes):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{API}/business/receipts",
        content=content,
        headers={
            **world.alice.headers,
            "Content-Type": "image/png",
            "Idempotency-Key": str(uuid4()),
            "X-Document-Filename": "recibo.png",
        },
    )


def _receipt(world, receipt_id: str) -> dict:  # noqa: ANN001
    found = world.client.get(
        f"{API}/business/receipts/{receipt_id}", headers=world.alice.headers
    )
    assert found.status_code == 200, found.text
    return found.json()


def test_reading_turned_off_while_a_read_is_in_flight_stops_before_the_provider(
    web,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001
) -> None:
    assert _reading(web, True).status_code == 200
    store = web.documents.store
    source = store.source
    revoked: list[str] = []

    def revoke_while_reading(**kwargs):  # noqa: ANN003, ANN202
        # The owner turns reading off after the read began, before the provider.
        web.documents.business_receipt_consent.set(
            web.alice.space_id, web.alice.id, enabled=False, version=1
        )
        revoked.append(kwargs["connection_id"])
        return source(**kwargs)

    monkeypatch.setattr(store, "source", revoke_while_reading)
    uploaded = _upload(web, RECEIPT + b"\x11")
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]

    assert uploaded.json()["status"] == "queued"
    assert revoked == [receipt_id]
    assert web.stub.calls == []
    detail = _receipt(web, receipt_id)
    assert (detail["status"], detail["read_pending"]) == ("saved", False)
    reading = web.client.get(
        f"{API}/business/receipt-reading", headers=web.alice.headers
    ).json()
    assert reading["enabled"] is False


def test_legacy_prepare_is_refused_while_reading_is_off(web) -> None:  # noqa: ANN001
    uploaded = _upload(web, RECEIPT + b"\x12")
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    assert uploaded.json()["status"] == "saved"

    refused = web.client.post(
        f"{API}/business/receipts/{receipt_id}/prepare",
        headers={
            **web.alice.headers,
            "Idempotency-Key": str(uuid4()),
            "X-Extraction-Consent": "true",
        },
    )

    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "business_receipt_reading_off",
    )
    assert web.stub.calls == []
    assert _receipt(web, receipt_id)["status"] == "saved"
    # Turning reading on reads the waiting receipt: the refusal was the setting.
    assert _reading(web, True).status_code == 200
    assert web.stub.calls == [receipt_id]


class Provider:
    def __init__(self, raw: bytes) -> None:
        self.raw, self.recipients = raw, ()

    async def raw_message(self, email_id: str, *, budget=None) -> ReceivedEmail:  # noqa: ANN001
        return ReceivedEmail(self.raw, self.recipients)


def _email(attachment: bytes) -> bytes:
    message = EmailMessage()
    message["From"] = "proveedor@example.test"
    message["Subject"] = "Factura"
    message.set_content("Adjunto la factura.")
    message.add_attachment(
        attachment, maintype="image", subtype="png", filename="recibo.png"
    )
    return message.as_bytes()


def _email_runtime(web, monkeypatch: pytest.MonkeyPatch, raw: bytes):  # noqa: ANN001, ANN202
    monkeypatch.setenv("ARGUS_RESEND_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr("argus.api.routers.email_intake.webhook_enabled", lambda: True)
    pool = app.state.financial_accounts_pool
    with Connection.connect(shared.DSN) as db:
        [grant] = db.execute(
            "select id::text from public.business_client_grants where space_id=%s"
            " and grantee_id=%s and revoked_at is null",
            (web.alice.space_id, web.alice.id),
        ).fetchone()
    store = PostgresEmailStore(pool)
    route = store.create_route(
        recipient=f"recibos-{uuid4().hex[:8]}@recibos.example.test",
        space_id=web.alice.space_id,
        principal_id=web.alice.id,
        granted_by=web.alice.id,
        grant_id=grant,
    )
    provider = Provider(raw)
    provider.recipients = (route.recipient,)
    runtime = EmailCapture(
        store,
        web.documents,
        grant_route_authority(pool),
        provider,
        lambda: True,
        lambda: True,
        _read_receipt,
    )
    configure_email_intake(runtime)
    return runtime, route


@pytest.mark.parametrize("reading", [False, True])
def test_an_emailed_receipt_is_read_only_while_the_owners_reading_is_on(
    web,
    monkeypatch: pytest.MonkeyPatch,
    reading: bool,  # noqa: ANN001
) -> None:
    if reading:
        assert _reading(web, True).status_code == 200
    runtime, route = _email_runtime(web, monkeypatch, _email(RECEIPT + b"\x13"))
    body = json.dumps(
        {
            "type": "email.received",
            "data": {"email_id": str(uuid4()), "to": [route.recipient]},
        }
    ).encode()
    received = web.client.post(WEBHOOK, content=body, headers=signed(body))
    assert received.status_code == 202, received.text

    assert asyncio.run(runtime.next())

    receipts = web.client.get(
        f"{API}/business/receipts", params={"view": "all"}, headers=web.alice.headers
    ).json()["items"]
    [attachment] = [r for r in receipts if not r["email_original"]]
    [original] = [r for r in receipts if r["email_original"]]
    assert (attachment["channel"], original["channel"]) == ("email", "email")
    if reading:
        assert web.stub.calls == [attachment["id"]]
        assert _receipt(web, attachment["id"])["status"] == "review_ready"
    else:
        assert web.stub.calls == []
        assert _receipt(web, attachment["id"])["status"] == "saved"
    assert _receipt(web, original["id"])["status"] == "saved"
