"""A WhatsApp receipt joins the Business inbox and the same review and confirm path."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.business_spaces import business_access, business_spaces
from argus.api.documents import documents_service
from argus.api.main import app
from argus.api.whatsapp import (
    build_whatsapp,
    configure_whatsapp,
    eligible_sender_businesses,
    whatsapp_runtime,
)
from argus.domain.business.scope import BusinessScope, resolve_business_scope
from argus.domain.business.spaces import InMemorySpaceStore
from argus.domain.ingestion.whatsapp.store import InMemoryWhatsAppStore
from argus.domain.owner_scope import BusinessSpace
from fastapi.testclient import TestClient

from tests.business.conftest import ALICE, BOB
from tests.business.receipt_stub import ReceiptStub, receipt_date
from tests.business.test_business_api import Owner, started
from tests.document_reads_support import read_receipt
from tests.ingestion.test_whatsapp_api import UNSHOWN_LINK, link_alice, post
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
    monkeypatch.setattr("argus.api.whatsapp._memory_has_tax_id", lambda _space: True)
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
                access=business_access(),
                store=InMemoryWhatsAppStore(
                    documents_service().hub.connections, business_access(), eligible_sender_businesses
                ),
                client=graph.client(),
                app_origin="https://app.test",
            )
        )
        stub = ReceiptStub()
        monkeypatch.setattr(documents_service(), "extractor", stub)
        documents_service().business_receipt_consent.route_resolver = lambda: {
            "gateway": "synthetic",
            "interpretation": [{"model": "receipt-fixture"}],
            "reply": [],
        }
        test_client.graph = graph
        yield test_client, stub


def test_scope_is_the_persons_own_space_once_started() -> None:
    spaces = InMemorySpaceStore()
    assert resolve_business_scope(spaces, "person-1") is None
    space, _ = spaces.create("person-1", "Mi negocio")
    assert resolve_business_scope(spaces, "person-1") == BusinessScope(
        "person-1", BusinessSpace(space.id), actor_id="person-1"
    )
    assert resolve_business_scope(spaces, "person-2") is None


def test_linking_waits_for_the_space(wa_biz) -> None:  # noqa: ANN001
    client, _ = wa_biz
    alice = Owner(client, ALICE)
    calls = [
        client.post("/api/v1/whatsapp/link-codes", json=UNSHOWN_LINK, headers=alice.auth),
        client.get("/api/v1/whatsapp/link", headers=alice.auth),
    ]
    assert [(r.status_code, r.json()["code"]) for r in calls] == [
        (409, "whatsapp_setup_required"), (404, "whatsapp_unavailable")
    ]
    assert client.delete("/api/v1/whatsapp/link", headers=alice.auth).status_code == 204


def test_whatsapp_receipt_is_reviewed_and_confirmed_like_an_upload(
    wa_biz, identities
) -> None:  # noqa: ANN001
    client, stub = wa_biz
    alice = started(Owner(client, ALICE, identities[ALICE]["id"]))
    bob = started(Owner(client, BOB))
    assert alice.reading(True).status_code == 200
    link_alice(client)
    assert post(client, fixture("image_message.json")).status_code == 200
    [captured] = alice.get("/receipts", view="inbox").json()["items"]
    assert (captured["channel"], captured["status"], captured["size_bytes"]) == (
        "whatsapp",
        "queued",
        len(RECEIPT_PNG),
    )
    assert stub.calls == []
    receipt_id = captured["id"]
    assert post(client, fixture("image_message.json")).status_code == 200
    assert [r["id"] for r in alice.get("/receipts", view="all").json()["items"]] == [
        receipt_id
    ]
    assert asyncio.run(read_receipt(documents_service(), identities[ALICE]["id"], receipt_id)) == "prepared"
    detail = alice.detail(receipt_id)
    assert (detail["channel"], detail["status"]) == ("whatsapp", "review_ready")
    account = alice.account()
    version = alice.resolve_receipt(receipt_id, detail["version"], account_id=account).json()[
        "version"
    ]
    first = alice.confirm(receipt_id, version, "wa-confirm").json()
    second = alice.confirm(receipt_id, version, "wa-confirm").json()
    assert first["status"] == second["status"] == "confirmed"
    assert first["expense_id"] == second["expense_id"]
    window = {"from": receipt_date(), "to": receipt_date()}
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
    assert alice.reading(True).status_code == 200
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
        ("whatsapp", "queued", "application/pdf"),
        ("whatsapp", "queued", "image/jpeg"),
        ("whatsapp", "queued", "image/jpeg"),
        ("whatsapp", "queued", "image/png"),
    ]
    assert stub.calls == []


def test_dossier_attachment_sources_that_arrived_by_whatsapp_say_so() -> None:
    """The dossier reads the same captured set /business/receipts reads: a
    WhatsApp arrival says whatsapp, a web upload keeps web, and an email arrival
    of the same file still wins, as it does on the receipt list."""

    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from argus.domain.business.contracts.dossier import (
        AttachmentSource,
        BusinessDossier,
        MessageSource,
    )
    from argus.domain.business.record_origin import UploadIntake, with_source_channels

    now = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)

    def attachment(name: str) -> AttachmentSource:
        return AttachmentSource(
            id=uuid4(),
            channel="web",
            received_at=now,
            connection_id=uuid4(),
            filename=name,
            media_type="image/png",
        )

    by_whatsapp, by_web, whatsapp_then_email = (
        attachment("wa.png"),
        attachment("web.png"),
        attachment("both.png"),
    )
    note = MessageSource(
        id=uuid4(), kind="message", channel="web", received_at=now, text="nota"
    )
    dossier = BusinessDossier.model_construct(
        sources=(by_whatsapp, by_web, whatsapp_then_email, note)
    )
    captured = frozenset(
        {str(by_whatsapp.connection_id), str(whatsapp_then_email.connection_id)}
    )
    emails = {str(whatsapp_then_email.connection_id): (("d1",), False, now - timedelta(minutes=1))}
    seen = with_source_channels(dossier, UploadIntake(captured, emails))
    assert [s.channel for s in seen.sources] == ["whatsapp", "web", "email", "web"]


@pytest.mark.parametrize("runtime_present", [True, False])
def test_saved_whatsapp_provenance_survives_receiving_off(
    wa_biz, identities, monkeypatch, runtime_present
):
    from types import SimpleNamespace

    from argus.api import account_deletion_runtime
    from argus.api import whatsapp as whatsapp_api
    from argus.domain.ingestion.whatsapp import store_postgres

    client, _ = wa_biz
    alice = started(Owner(client, ALICE, identities[ALICE]["id"]))
    bob = started(Owner(client, BOB))
    assert alice.reading(True).status_code == 200
    link_alice(client)
    assert post(client, fixture("image_message.json")).status_code == 200
    [saved] = alice.get("/receipts", view="all").json()["items"]
    store = whatsapp_runtime().intake.store
    monkeypatch.setenv("CUADRAO_WHATSAPP_INTAKE_ENABLED", "false")
    if not runtime_present:
        configure_whatsapp(None)
        pool = object()
        documents = SimpleNamespace(
            business_actions=SimpleNamespace(authority=SimpleNamespace(pool=pool))
        )
        monkeypatch.setattr(whatsapp_api, "documents_service", lambda: documents)

        def cleanup_pool_forbidden(*args):
            raise AssertionError("History must use the Business authority pool")

        def history_store(selected):
            assert selected is pool
            return store

        monkeypatch.setattr(account_deletion_runtime, "deletion_pool", cleanup_pool_forbidden)
        monkeypatch.setattr(store_postgres, "PostgresWhatsAppStore", history_store)
    [still_saved] = alice.get("/receipts", view="all").json()["items"]
    assert still_saved["id"] == saved["id"]
    assert still_saved["channel"] == "whatsapp"
    assert alice.detail(saved["id"])["channel"] == "whatsapp"
    assert bob.get("/receipts", view="all").json()["items"] == []
    assert bob.get(f"/receipts/{saved['id']}").status_code == 404
