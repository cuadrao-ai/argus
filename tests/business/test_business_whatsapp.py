"""A WhatsApp receipt joins the Business inbox and the same review and confirm path."""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.business_spaces import business_spaces
from argus.api.documents import documents_service
from argus.api.main import app
from argus.api.whatsapp import (
    build_whatsapp,
    configure_whatsapp,
    whatsapp_runtime,
)
from argus.domain.business.scope import BusinessScope, resolve_business_scope
from argus.domain.business.spaces import InMemorySpaceStore
from argus.domain.ingestion.whatsapp.store import InMemoryWhatsAppStore
from argus.domain.owner_scope import BusinessSpace
from fastapi.testclient import TestClient

from tests.business.conftest import ALICE, BOB
from tests.business.receipt_stub import ReceiptStub
from tests.business.test_business_api import Owner, started
from tests.ingestion.test_whatsapp_api import link_alice, post
from tests.ingestion.whatsapp_cases import FORWARDED
from tests.ingestion.whatsapp_support import (
    DOCUMENT_FIXTURES,
    ENV,
    RECEIPT_PNG,
    FakeGraph,
    Media,
    fixture,
)


@pytest.fixture
def wa_biz(
    business_env, gateway, monkeypatch
) -> Iterator[tuple[TestClient, ReceiptStub]]:  # noqa: ANN001
    for name in tuple(os.environ):
        if name.startswith("CUADRAO_WHATSAPP_"):
            monkeypatch.delenv(name, raising=False)
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
        if name.startswith("ARGUS_"):
            monkeypatch.delenv(name.replace("ARGUS_", "CUADRAO_", 1), raising=False)
    graph = FakeGraph({"700000000000001": Media(RECEIPT_PNG, "image/png")})
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        runtime = whatsapp_runtime()
        assert runtime is not None
        configure_whatsapp(
            build_whatsapp(
                runtime.settings,
                documents=documents_service(),
                spaces=business_spaces(),
                store=InMemoryWhatsAppStore(),
                client=graph.client(),
                app_origin="https://app.test",
            )
        )
        stub = ReceiptStub()
        monkeypatch.setattr(documents_service(), "extractor", stub)
        documents_service().business_receipt_consent.route_resolver = lambda: {"gateway":"synthetic","interpretation":[{"model":"receipt-fixture"}],"reply":[]}
        test_client.graph = graph
        yield test_client, stub


def test_scope_is_the_persons_own_space_once_started() -> None:
    spaces = InMemorySpaceStore()
    assert resolve_business_scope(spaces, "person-1") is None
    space, _ = spaces.create("person-1", "Mi negocio")
    assert resolve_business_scope(spaces, "person-1") == BusinessScope(
        "person-1", BusinessSpace(space.id)
    )
    assert resolve_business_scope(spaces, "person-2") is None


def test_linking_waits_for_the_space(wa_biz) -> None:  # noqa: ANN001
    client, _ = wa_biz
    alice = Owner(client, ALICE)
    calls = [
        client.post("/api/v1/whatsapp/link-codes", headers=alice.auth),
        client.get("/api/v1/whatsapp/link", headers=alice.auth),
    ]
    assert [(r.status_code, r.json()["code"]) for r in calls] == [
        (404, "business_space_missing")
    ] * 2
    assert client.delete("/api/v1/whatsapp/link", headers=alice.auth).status_code == 204


def test_whatsapp_is_off_while_business_is_off(wa_biz, monkeypatch) -> None:  # noqa: ANN001
    client, _ = wa_biz
    monkeypatch.delenv("ARGUS_BUSINESS_PILOT_ENABLED")
    alice = Owner(client, ALICE)
    responses = [
        client.post("/api/v1/whatsapp/link-codes", headers=alice.auth),
        post(client, fixture("image_message.json")),
    ]
    assert [(r.status_code, r.json()["code"]) for r in responses] == [
        (404, "whatsapp_unavailable")
    ] * 2


def test_whatsapp_receipt_is_reviewed_and_confirmed_like_an_upload(wa_biz) -> None:  # noqa: ANN001
    client, stub = wa_biz
    alice, bob = started(Owner(client, ALICE)), started(Owner(client, BOB))
    link_alice(client)
    assert post(client, fixture("image_message.json")).status_code == 200
    [captured] = alice.get("/receipts", view="inbox").json()["items"]
    assert (captured["channel"], captured["status"], captured["size_bytes"]) == (
        "whatsapp",
        "saved",
        len(RECEIPT_PNG),
    )
    assert stub.calls == []
    receipt_id = captured["id"]
    assert post(client, fixture("image_message.json")).status_code == 200
    assert [r["id"] for r in alice.get("/receipts", view="all").json()["items"]] == [
        receipt_id
    ]
    assert alice.reading(True).status_code == 200
    prepared = alice.post(
        f"/receipts/{receipt_id}/prepare", **{"X-Extraction-Consent": "true"}
    )
    assert prepared.status_code == 200, prepared.text
    detail = alice.detail(receipt_id)
    assert (detail["channel"], detail["status"]) == ("whatsapp", "review_ready")
    account = alice.account()
    version = alice.review(receipt_id, detail["version"], account_id=account).json()[
        "version"
    ]
    first = alice.confirm(receipt_id, version, "wa-confirm").json()
    second = alice.confirm(receipt_id, version, "wa-confirm").json()
    assert first["status"] == second["status"] == "confirmed"
    assert first["expense_id"] == second["expense_id"]
    window = {"from": "2026-10-01", "to": "2026-10-31"}
    assert [
        (e["id"], e["receipt_id"])
        for e in alice.get("/expenses", **window).json()["items"]
    ] == [(first["expense_id"], receipt_id)]
    assert bob.get(f"/receipts/{receipt_id}").status_code == 404
    personal = client.get("/api/v1/financial-documents", headers=alice.auth).json()
    assert personal["items"] == []


def test_forwards_and_captions_reach_the_inbox_like_a_direct_send(wa_biz) -> None:  # noqa: ANN001
    client, stub = wa_biz
    alice = started(Owner(client, ALICE))
    link_alice(client)
    for name, source, media_type, _filename in FORWARDED:
        body = fixture(name)
        message = body["entry"][0]["changes"][0]["value"]["messages"][0]
        client.graph.media[message[message["type"]]["id"]] = Media(
            (DOCUMENT_FIXTURES / source).read_bytes(), media_type
        )
        assert post(client, body).status_code == 200
    inbox = alice.get("/receipts", view="inbox").json()["items"]
    assert sorted((r["channel"], r["status"], r["media_type"]) for r in inbox) == [
        ("whatsapp", "saved", "application/pdf"),
        ("whatsapp", "saved", "image/jpeg"),
        ("whatsapp", "saved", "image/jpeg"),
        ("whatsapp", "saved", "image/png"),
    ]
    assert stub.calls == []
