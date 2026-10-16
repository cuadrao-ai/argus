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

from tests.business.test_business_api import Owner, alice, bob  # noqa: F401

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
    from argus.api.documents import documents_service

    fake = Mock()
    fake.store = InMemoryEmailStore()
    # The real runtime holds the app's documents service; the deliveries view
    # reads a document's save time through it.
    fake.documents = documents_service()
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
    # Intake saves the documents after the email arrived: the save follows the arrival.
    original = alice.upload(consent=False, name="forwarded.eml")
    attachment = alice.upload(content=UNREADABLE, consent=False, name="recibo.png")
    assert (original.status_code, attachment.status_code) == (200, 200), attachment.text
    original_id, attachment_id = original.json()["id"], attachment.json()["id"]
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
    # Both arrived by email, and the views say so; the stored draft still knows only web.
    assert (listed[original_id]["channel"], listed[attachment_id]["channel"]) == (
        "email",
        "email",
    )
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
    assert alice.get(f"/receipts/{original_id}/source").json()["code"] == "document_source_unavailable"
    searched = {
        item["id"]: item
        for item in alice.get("/search", q="forwarded").json()["receipts"]
    }
    assert searched[original_id]["email_original"] is True
    # The attachment is the receipt; the owner opts in to its reading.
    assert alice.reading(True).status_code == 200
    prepared = alice.post(
        f"/receipts/{attachment_id}/prepare", **{"X-Extraction-Consent": "true"}
    )
    assert prepared.status_code == 200, prepared.text


def test_the_same_file_in_a_second_email_names_the_first_delivery_and_adds_no_receipt(
    alice: Owner,  # noqa: F811
    runtime,  # noqa: ANN001
) -> None:
    """The second email's part replays the first receipt; the deliveries list
    says which delivery brought it first, the receipt lists both deliveries,
    and the Business still has one receipt for those bytes."""

    from argus.domain.ingestion.email_intake.models import EmailDeliveryPart

    space_id = alice.scope().owner.space_id
    store = runtime.store
    route = store.create_route(
        recipient="recibos-00000002@recibos.example.test",
        space_id=space_id,
        principal_id=alice.scope().person_id,
        granted_by=alice.scope().person_id,
        grant_id=str(uuid4()),
    )
    ids = []
    document_id = None
    for subject in ("Factura 0041", "Fwd: Factura 0041"):
        delivery = store.enqueue(
            "resend",
            str(uuid4()),
            (route.recipient,),
            route_id=route.id,
            space_id=space_id,
            principal_id=route.principal_id,
        )
        claimed = store.claim()
        store.update(claimed, subject=subject)
        # Intake saves the part after the email arrived; the second save replays the first.
        saved = alice.upload(content=UNREADABLE, consent=False, name="recibo.png")
        assert saved.json()["replayed"] is (document_id is not None)
        document_id = saved.json()["id"]
        store.put_part(
            claimed,
            EmailDeliveryPart(
                "1.2", "recibo.png", "image/png", "captured", document_id, None
            ),
        )
        store.finish(claimed, "captured")
        ids.append(delivery.id)
    first, second = ids
    deliveries = {
        item["id"]: item for item in alice.get("/email/deliveries").json()["items"]
    }
    assert deliveries[first]["parts"][0]["repeat_of_delivery_id"] is None
    assert deliveries[second]["parts"][0]["repeat_of_delivery_id"] == first
    one = alice.get(f"/email/deliveries/{second}").json()
    assert one["parts"][0]["repeat_of_delivery_id"] == first
    detail = alice.detail(document_id)
    assert sorted(detail["email_delivery_ids"]) == sorted([first, second])
    assert detail["channel"] == "email"
    assert (
        len(
            [
                i
                for i in alice.get("/receipts", view="all").json()["items"]
                if i["id"] == document_id
            ]
        )
        == 1
    )


def test_dossier_attachment_sources_that_arrived_by_email_say_so(monkeypatch):  # noqa: ANN001
    from datetime import datetime, timedelta, timezone

    from argus.api import business_drafts as api
    from argus.domain.business.contracts.dossier import AttachmentSource, BusinessDossier

    now = datetime(2026, 10, 13, 17, 14, tzinfo=timezone.utc)

    def attachment(name: str) -> AttachmentSource:
        return AttachmentSource(
            id=uuid4(),
            channel="web",
            received_at=now,
            connection_id=uuid4(),
            filename=name,
            media_type="application/pdf",
        )

    by_email, web_first, by_web = (
        attachment("a.pdf"),
        attachment("c.pdf"),
        attachment("b.pdf"),
    )
    dossier = BusinessDossier.model_construct(sources=(by_email, web_first, by_web))
    monkeypatch.setattr(
        "argus.api.email_intake.email_receipt_flags",
        lambda space_id: {
            # Arrived by email a minute before it was saved: an email receipt.
            str(by_email.connection_id): (
                ("d1", "d2"),
                False,
                now - timedelta(minutes=1),
            ),
            # Saved on the web an hour before any email brought it: keeps web, lists the email.
            str(web_first.connection_id): (("d3",), False, now + timedelta(hours=1)),
        },
    )
    seen = api.with_email_sources(dossier, "space")
    assert [(s.channel, s.email_delivery_ids) for s in seen.sources] == [
        ("email", ("d1", "d2")),
        ("web", ("d3",)),
        ("web", ()),
    ]
    monkeypatch.setattr("argus.api.email_intake.email_receipt_flags", lambda space_id: {})
    assert api.with_email_sources(dossier, "space") is dossier


def _route_for(store, owner: Owner, recipient: str):  # noqa: ANN001, ANN202
    return store.create_route(
        recipient=recipient,
        space_id=owner.scope().owner.space_id,
        principal_id=owner.scope().person_id,
        granted_by=owner.scope().person_id,
        grant_id=str(uuid4()),
    )


def _deliver(store, route, owner: Owner, document, subject: str) -> str:  # noqa: ANN001
    """An email arrives, then intake saves its part: ``document`` is the saved
    id, or a callable that saves after the arrival and returns the id."""

    from argus.domain.ingestion.email_intake.models import EmailDeliveryPart

    delivery = store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=owner.scope().owner.space_id,
        principal_id=route.principal_id,
    )
    claimed = store.claim()
    store.update(claimed, subject=subject)
    document_id = document() if callable(document) else document
    store.put_part(
        claimed,
        EmailDeliveryPart(
            "1.2", "recibo.png", "image/png", "captured", document_id, None
        ),
    )
    store.finish(claimed, "captured")
    return delivery.id


def _upload(owner: Owner):  # noqa: ANN202
    return lambda: owner.upload(
        content=UNREADABLE, consent=False, name="recibo.png"
    ).json()["id"]


def test_the_same_bytes_in_two_businesses_never_mark_each_other(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
    runtime,  # noqa: ANN001
) -> None:
    store = runtime.store
    route_a = _route_for(store, alice, "recibos-00000003@recibos.example.test")
    route_b = _route_for(store, bob, "recibos-00000004@recibos.example.test")
    # Each Business receives the file once by email: neither is a repeat of the other's.
    a1 = _deliver(store, route_a, alice, _upload(alice), "Factura A")
    b1 = _deliver(store, route_b, bob, _upload(bob), "Factura B")
    seen_a = {i["id"]: i for i in alice.get("/email/deliveries").json()["items"]}
    seen_b = {i["id"]: i for i in bob.get("/email/deliveries").json()["items"]}
    assert set(seen_a) == {a1} and set(seen_b) == {b1}
    first_a = seen_a[a1]["parts"][0]["document_id"]
    first_b = seen_b[b1]["parts"][0]["document_id"]
    assert first_a != first_b
    for item in (seen_a[a1], seen_b[b1]):
        assert (
            item["parts"][0]["repeat_of_delivery_id"],
            item["parts"][0]["repeat_of_upload"],
        ) == (None, False)
    assert alice.detail(first_a)["email_delivery_ids"] == [a1]
    assert bob.detail(first_b)["email_delivery_ids"] == [b1]
    assert (alice.detail(first_a)["channel"], bob.detail(first_b)["channel"]) == (
        "email",
        "email",
    )


def test_a_file_uploaded_on_the_web_first_keeps_its_label_and_the_email_is_the_repeat(
    alice: Owner,  # noqa: F811
    runtime,  # noqa: ANN001
) -> None:
    """The web upload came first: the receipt still says web, the email that
    brought the same bytes later is a repeat of that upload (no earlier email
    to name), and a second email names the first email."""

    store = runtime.store
    document_id = _upload(alice)()
    route = _route_for(store, alice, "recibos-00000005@recibos.example.test")
    first = _deliver(store, route, alice, _upload(alice), "Factura 0041")
    second = _deliver(store, route, alice, _upload(alice), "Fwd: Factura 0041")
    detail = alice.detail(document_id)
    assert detail["channel"] == "web"
    # Earliest first, so the receipt page can point at the first email.
    assert detail["email_delivery_ids"] == [first, second]
    deliveries = {i["id"]: i for i in alice.get("/email/deliveries").json()["items"]}
    assert (
        deliveries[first]["parts"][0]["repeat_of_delivery_id"],
        deliveries[first]["parts"][0]["repeat_of_upload"],
    ) == (None, True)
    assert (
        deliveries[second]["parts"][0]["repeat_of_delivery_id"],
        deliveries[second]["parts"][0]["repeat_of_upload"],
    ) == (first, False)
    one = alice.get(f"/email/deliveries/{second}").json()
    assert one["parts"][0]["repeat_of_delivery_id"] == first


@pytest.mark.parametrize(
    "code", ["email_daily_message_budget", "email_daily_byte_budget"]
)
def test_capped_email_waiting_survives_real_api_serialization(alice, runtime, code):  # noqa: F811
    from dataclasses import asdict, replace
    from datetime import datetime, timedelta, timezone

    from argus.domain.ingestion.email_intake.budget import next_utc_day
    from argus.domain.ingestion.email_intake.store import _delivery

    now = datetime.now(timezone.utc)
    store = runtime.store
    store.clock = lambda: now
    scope = alice.scope()
    route = store.create_route(
        recipient="recibos-wait@example.test",
        space_id=scope.owner.space_id,
        principal_id=scope.person_id,
        granted_by=scope.person_id,
        grant_id=str(uuid4()),
    )
    item = store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=route.space_id,
        principal_id=route.principal_id,
    )
    store.defer_budget(store.claim(delivery_id=item.id), code)
    waiting_item = store.get(item.id, route.space_id)
    assert _delivery(asdict(waiting_item)).available_at == next_utc_day(now)
    expected = {
        "reason": "daily_budget",
        "retry_at": next_utc_day(now).isoformat().replace("+00:00", "Z"),
    }
    for payload in (
        alice.get("/email/deliveries").json()["items"][0],
        alice.get(f"/email/deliveries/{item.id}").json(),
    ):
        assert payload["waiting"] == expected
        assert payload["state"] == "received"
        assert payload["error_code"] is None
        assert payload["retryable"] is False
        assert "available_at" not in payload

    # A refresh after the server deadline must not promise another tomorrow.
    store._available[item.id] = now - timedelta(seconds=1)
    due = alice.get(f"/email/deliveries/{item.id}").json()
    assert due["waiting"] is None and due["error_code"] is None
    assert store.get(item.id, route.space_id).error_code == code
    store._available[item.id] = next_utc_day(now)
    for state in ("processing", "partial", "rejected", "captured"):
        store._deliveries[item.id] = replace(waiting_item, state=state)
        assert alice.get(f"/email/deliveries/{item.id}").json()["waiting"] is None
    store._deliveries[item.id] = replace(waiting_item, error_code=None)
    assert alice.get(f"/email/deliveries/{item.id}").json()["waiting"] is None
