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
from argus.api.documents import documents_service
from argus.domain.ingestion.email_intake.store import InMemoryEmailStore
from fastapi.testclient import TestClient

from tests.business.test_business_api import BASE, Owner, alice, bob  # noqa: F401

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
    assert status.json() == {
        "enabled": False,
        "receiving_address": None,
        "alias": None,
        "review_required": False,
    }
    assert alice.get("/email/deliveries").json() == {"items": []}
    assert alice.get(f"/email/deliveries/{uuid4()}").status_code == 404
    created = alice.post("/email", key=str(uuid4()))
    assert (created.status_code, created.json()["code"]) == (
        503,
        "email_receiving_unconfigured",
    )


def test_endpoints_say_unavailable_without_a_runtime(alice: Owner) -> None:  # noqa: F811
    """The in-memory app keeps no deliveries: the list is empty, every other
    email route is unavailable."""

    runtime_module.configure_email_intake(None)
    assert alice.get("/email").status_code == 503
    deliveries = alice.get("/email/deliveries")
    assert (deliveries.status_code, deliveries.json()) == (200, {"items": []})


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
    original = alice.upload(
        content=b"Subject: Factura 0041\r\n\r\nForwarded receipt",
        consent=False,
        name="forwarded.eml",
        media_type="message/rfc822",
    )
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
    source = alice.get(f"/receipts/{original_id}/source")
    assert source.status_code == 200
    assert source.headers["content-type"] == "message/rfc822"
    assert source.content == documents_service().store.source(
        user_id=alice.scope().person_id, connection_id=original_id
    )
    # The original is the email, never a receipt hit; its delivery is the hit.
    assert alice.get("/search", q="forwarded").json()["receipts"] == []
    found = alice.get("/search", q="Factura 0041").json()
    assert [item["id"] for item in found["email_deliveries"]] == [delivery.id]
    assert found["receipts"] == []
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

    from argus.domain.ingestion.email_intake.budget import next_business_day
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
    assert _delivery(asdict(waiting_item)).available_at == next_business_day(now)
    expected = {
        "reason": "daily_budget",
        "retry_at": next_business_day(now).isoformat().replace("+00:00", "Z"),
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
    store._available[item.id] = next_business_day(now)
    for state in ("processing", "partial", "rejected", "captured"):
        store._deliveries[item.id] = replace(waiting_item, state=state)
        assert alice.get(f"/email/deliveries/{item.id}").json()["waiting"] is None
    store._deliveries[item.id] = replace(waiting_item, error_code=None)
    assert alice.get(f"/email/deliveries/{item.id}").json()["waiting"] is None


def test_new_senders_are_listed_before_the_tray(alice, runtime):  # noqa: F811
    from dataclasses import replace

    store = runtime.store
    route = _route_for(store, alice, "ferreterianunez@recibos.example.test")
    space_id = alice.scope().owner.space_id
    tray = store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=space_id,
        principal_id=route.principal_id,
    )
    fresh = store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=space_id,
        principal_id=route.principal_id,
    )
    store._deliveries[tray.id] = replace(
        store.get(tray.id, space_id), state="captured", inbox_group="bandeja"
    )
    store._deliveries[fresh.id] = replace(
        store.get(fresh.id, space_id), state="captured", inbox_group="remitentes_nuevos"
    )
    response = alice.get("/email/inbox")
    assert response.status_code == 200, response.text
    groups = response.json()["groups"]
    assert [group["id"] for group in groups] == ["remitentes_nuevos", "bandeja"]
    assert [item["id"] for item in groups[0]["items"]] == [fresh.id]
    assert [item["id"] for item in groups[1]["items"]] == [tray.id]


def test_the_tray_carries_the_unverified_sender_note(alice, runtime):  # noqa: F811
    from dataclasses import replace

    store = runtime.store
    route = _route_for(store, alice, "ferreterianunez@recibos.example.test")
    space_id = alice.scope().owner.space_id
    pending = store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=space_id,
        principal_id=route.principal_id,
    )
    store._deliveries[pending.id] = replace(
        store.get(pending.id, space_id),
        state="captured",
        inbox_group="bandeja",
        auth_result="failed",
        review_note="No pudimos verificar este remitente.",
    )
    groups = alice.get("/email/inbox").json()["groups"]
    item = groups[1]["items"][0]
    assert (item["id"], item["review_note"], item["approved"]) == (
        pending.id,
        "No pudimos verificar este remitente.",
        False,
    )


def test_inbox_items_carry_the_sender_standing_and_only_authorized_ones_the_note(
    alice,  # noqa: F811
    runtime,
):
    from dataclasses import replace

    store = runtime.store
    route = _route_for(store, alice, "remitentes@recibos.example.test")
    space_id = alice.scope().owner.space_id
    note = "No pudimos verificar este remitente."
    store.upsert_sender(space_id, "address", "caja@tienda.test", "authorized")
    store.upsert_sender(space_id, "address", "spam@otro.test", "blocked")
    rows = {
        "held": ("caja@tienda.test", "remitentes_nuevos", "unknown", note),
        "pending": ("caja@tienda.test", "bandeja", "failed", note),
        "blocked": ("spam@otro.test", "remitentes_nuevos", "aligned", None),
        "new": ("x@nuevo.test", "remitentes_nuevos", "failed", None),
    }
    ids = {}
    for name, (sender, group, auth, review_note) in rows.items():
        pending = store.enqueue(
            "resend",
            str(uuid4()),
            (route.recipient,),
            route_id=route.id,
            space_id=space_id,
            principal_id=route.principal_id,
        )
        store._deliveries[pending.id] = replace(
            store.get(pending.id, space_id),
            state="captured",
            sender=sender,
            inbox_group=group,
            auth_result=auth,
            review_note=review_note,
        )
        ids[pending.id] = name
    items = [
        item
        for group in alice.get("/email/inbox").json()["groups"]
        for item in group["items"]
    ]
    seen = {
        ids[item["id"]]: (item["sender_standing"], item["review_note"])
        for item in items
        if item["id"] in ids
    }
    assert seen == {
        "held": ("authorized", note),
        "pending": ("authorized", note),
        "blocked": ("blocked", None),
        "new": ("new", None),
    }
    listed = alice.get("/email/deliveries").json()["items"]
    assert {ids[i["id"]]: i["sender_standing"] for i in listed if i["id"] in ids} == {
        name: standing for name, (standing, _note) in seen.items()
    }


def test_owner_authorizes_one_sender_and_refuses_a_free_mail_domain(alice, runtime):  # noqa: F811
    body = {"kind": "address", "value": "Caja@Tienda.test", "status": "authorized"}
    created = alice.post("/email/senders", body)
    assert created.status_code == 201, created.text
    replay = alice.post("/email/senders", body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == created.json()["id"]
    refused = alice.post(
        "/email/senders",
        {"kind": "domain", "value": "gmail.com", "status": "authorized"},
    )
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "email_sender_domain_refused",
    )
    whole = alice.post(
        "/email/senders",
        {"kind": "domain", "value": "tienda.test", "status": "authorized"},
    )
    assert (whole.status_code, whole.json()["code"]) == (
        422,
        "email_sender_domain_refused",
    )
    listed = alice.get("/email/senders").json()["items"]
    authorized = [
        event
        for event in runtime.store.address_events(alice.scope().owner.space_id)
        if event.event_type == "sender_authorized"
    ]
    assert authorized[-1].actor_id == alice.scope().person_id
    assert authorized[-1].new_address == "caja@tienda.test"
    assert authorized[-1].old_address is None
    assert authorized[-1].created_at is not None
    assert listed == [
        {
            "id": created.json()["id"],
            "kind": "address",
            "value": "caja@tienda.test",
            "status": "authorized",
            "tag": None,
            "last_auth_result": None,
            "last_seen_at": None,
        }
    ]
    taken = runtime.store.create_route(
        recipient="ferreterianunez@recibos.example.test",
        space_id=str(uuid4()),
        principal_id=str(uuid4()),
        granted_by=str(uuid4()),
        grant_id=str(uuid4()),
        alias="ferreterianunez",
        alias_normalized="ferreterianunez",
    )
    answer = alice.get("/email/availability", alias="ferreterianunez")
    assert answer.status_code == 200, answer.text
    payload = answer.json()
    assert payload["available"] is False
    assert payload["message"] == "Ese nombre no está disponible. Prueba otro."
    assert taken.recipient not in answer.text
    assert "ferreterianunez@" not in answer.text


def test_alias_lookups_are_limited_for_the_owner(alice: Owner, runtime) -> None:  # noqa: F811
    from argus.api.routers import email_intake as routes

    limiter = getattr(routes, "_alias_lookup_limiter", None)
    if limiter is not None:
        limiter.reset()
    try:
        statuses = [
            alice.get("/email/availability", alias=f"nombre{i:02d}").status_code
            for i in range(30)
        ]
        suggestion = alice.get("/email/suggestion", name="Ferreteria Gomez")
        assert statuses == [200] * 30
        assert suggestion.status_code == 429, suggestion.text
        assert suggestion.json()["code"] == "email_alias_lookup_limited"
    finally:
        limiter = getattr(routes, "_alias_lookup_limiter", None)
        if limiter is not None:
            limiter.reset()


def test_the_owner_removes_a_sender(alice: Owner, runtime) -> None:  # noqa: F811
    created = alice.post(
        "/email/senders",
        {"kind": "address", "value": "caja@tienda.test", "status": "authorized"},
    )
    assert created.status_code == 201, created.text
    removed = alice.client.delete(
        f"{BASE}/email/senders/{created.json()['id']}", headers=alice.auth
    )
    assert removed.status_code == 204, removed.text
    assert alice.get("/email/senders").json()["items"] == []
    gone = [
        event
        for event in runtime.store.address_events(alice.scope().owner.space_id)
        if event.event_type == "sender_removed"
    ]
    assert gone[-1].actor_id == alice.scope().person_id
    assert gone[-1].old_address == "caja@tienda.test"
    assert gone[-1].new_address is None
    assert gone[-1].created_at is not None


def test_blocking_a_sender_records_the_sender(alice: Owner, runtime) -> None:  # noqa: F811
    blocked = alice.post(
        "/email/senders",
        {"kind": "address", "value": "caja@tienda.test", "status": "blocked"},
    )
    assert blocked.status_code == 201, blocked.text
    events = [
        event
        for event in runtime.store.address_events(alice.scope().owner.space_id)
        if event.event_type == "sender_blocked"
    ]
    assert events[-1].actor_id == alice.scope().person_id
    assert events[-1].old_address == "caja@tienda.test"
    assert events[-1].new_address == "caja@tienda.test"
    assert events[-1].created_at is not None


def test_stopping_the_address_records_the_old_one(alice: Owner, runtime) -> None:  # noqa: F811
    route = _route_for(runtime.store, alice, "recibos-stop01@recibos.example.test")
    stopped = alice.client.delete(f"{BASE}/email", headers=alice.auth)
    assert stopped.status_code == 204, stopped.text
    events = [
        event
        for event in runtime.store.address_events(alice.scope().owner.space_id)
        if event.event_type == "address_stopped"
    ]
    assert events[-1].actor_id == alice.scope().person_id
    assert events[-1].old_address == route.recipient
    assert events[-1].new_address is None
    assert events[-1].created_at is not None


def test_changing_the_address_records_both(
    alice: Owner,  # noqa: F811
    runtime,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "argus.api.routers.email_intake._configured_domain",
        lambda request: "recibos.example.test",
    )
    route = runtime.store.create_route(
        recipient="ferreteriagomez@recibos.example.test",
        space_id=alice.scope().owner.space_id,
        principal_id=alice.scope().person_id,
        granted_by=alice.scope().person_id,
        grant_id=str(uuid4()),
        alias="ferreteriagomez",
        alias_normalized="ferreteriagomez",
    )
    changed = alice.post("/email/address", {"alias": "tallerpena"})
    assert changed.status_code == 200, changed.text
    events = [
        event
        for event in runtime.store.address_events(alice.scope().owner.space_id)
        if event.event_type == "address_changed"
    ]
    assert events[-1].actor_id == alice.scope().person_id
    assert events[-1].old_address == route.recipient
    assert events[-1].new_address == "tallerpena@recibos.example.test"
    assert events[-1].created_at is not None


def test_approve_waits_until_the_sender_is_authorized(alice: Owner, runtime) -> None:  # noqa: F811
    from argus.api.business_drafts import DraftContext, require_drafts
    from argus.api.routers.business_drafts import router
    from argus.domain.business.contracts.actions import Refused
    from argus.domain.ingestion.email_intake.models import EmailDeliveryPart
    from fastapi import FastAPI

    store = runtime.store
    route = _route_for(store, alice, "recibos-approve1@recibos.example.test")
    document_id = uuid4()
    delivery = store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=route.space_id,
        principal_id=route.principal_id,
    )
    claimed = store.claim()
    store.update(claimed, sender="caja@tienda.test")
    store.put_part(
        claimed,
        EmailDeliveryPart(
            "1.2", "recibo.png", "image/png", "captured", str(document_id), None
        ),
    )
    store.stamp_route(
        claimed,
        inbox_group="bandeja",
        auth_result="aligned",
        review_note=None,
        first_scan=False,
    )
    store.finish(claimed, "captured")
    draft_id = uuid4()
    store.link_draft_documents(route.space_id, draft_id, [document_id])

    class Recording:
        def __init__(self) -> None:
            self.calls: list = []

        def context_for_draft(self, actor_id, draft_id, **_pin):  # noqa: ANN001
            return object()

        def approve(self, context, draft_id, request, key):  # noqa: ANN001
            self.calls.append(draft_id)
            return Refused(outcome="invalid_input", code="expense_blocked")

    service = Recording()
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):  # noqa: ANN001
        request.state.request_id = "approve-sender"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, uuid4(), route.space_id
    )
    body = {"version": 1, "action": "record_expense"}
    url = f"/business/drafts/{draft_id}/approve"
    with TestClient(app) as drafts:
        blocked = drafts.post(url, json=body, headers={"Idempotency-Key": str(uuid4())})
        assert blocked.status_code == 403, blocked.text
        assert blocked.json()["detail"]["code"] == "email_sender_unauthorized"
        assert service.calls == []
        assert store.get(delivery.id, route.space_id).approved is False
        allowed = alice.post(
            "/email/senders",
            {"kind": "address", "value": "caja@tienda.test", "status": "authorized"},
        )
        assert allowed.status_code == 201, allowed.text
        opened = drafts.post(url, json=body, headers={"Idempotency-Key": str(uuid4())})
    assert opened.status_code == 422, opened.text
    assert opened.json()["detail"]["code"] == "expense_blocked"
    assert service.calls == [draft_id]
    assert store.get(delivery.id, route.space_id).approved is False


def test_unverified_mail_held_before_its_sender_was_authorized_stays_refused(
    alice: Owner,  # noqa: F811
    runtime,
) -> None:
    from argus.api.business_drafts import DraftContext, require_drafts
    from argus.api.routers.business_drafts import router
    from argus.domain.business.contracts.actions import Refused
    from argus.domain.ingestion.email_intake.models import EmailDeliveryPart
    from fastapi import FastAPI

    store = runtime.store
    route = _route_for(store, alice, "recibos-approve2@recibos.example.test")
    document_id = uuid4()
    store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=route.space_id,
        principal_id=route.principal_id,
    )
    claimed = store.claim()
    store.update(claimed, sender="caja@tienda.test")
    store.put_part(
        claimed,
        EmailDeliveryPart(
            "1.2", "recibo.png", "image/png", "captured", str(document_id), None
        ),
    )
    store.stamp_route(
        claimed,
        inbox_group="remitentes_nuevos",
        auth_result="failed",
        review_note=None,
        first_scan=False,
    )
    store.finish(claimed, "captured")
    draft_id = uuid4()
    store.link_draft_documents(route.space_id, draft_id, [document_id])

    class Recording:
        def __init__(self) -> None:
            self.calls: list = []

        def context_for_draft(self, actor_id, draft_id, **_pin):
            return object()

        def approve(self, context, draft_id, request, key):
            self.calls.append(draft_id)
            return Refused(outcome="invalid_input", code="expense_blocked")

    service = Recording()
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "approve-forged"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, uuid4(), route.space_id
    )
    body = {"version": 1, "action": "record_expense"}
    url = f"/business/drafts/{draft_id}/approve"
    with TestClient(app) as drafts:
        forged = drafts.post(url, json=body, headers={"Idempotency-Key": str(uuid4())})
        assert forged.status_code == 403, forged.text
        assert forged.json()["detail"]["code"] == "email_sender_unauthorized"
        assert service.calls == []
        alice.post(
            "/email/senders",
            {"kind": "address", "value": "caja@tienda.test", "status": "authorized"},
        )
        delivery = store.get(claimed.id, route.space_id)
        assert (delivery.auth_result, delivery.approved) == ("failed", False)
        # Held without the note: authorizing the sender later does not open it.
        pressed = drafts.post(url, json=body, headers={"Idempotency-Key": str(uuid4())})
        assert pressed.status_code == 403, pressed.text
        assert pressed.json()["detail"]["code"] == "email_sender_unauthorized"
        assert service.calls == []
        assert store.get(claimed.id, route.space_id).approved is False
        service.calls.clear()

        def unreachable(*_args, **_kwargs):
            raise RuntimeError("email store unreachable")

        store.email_document_standing = unreachable
        down = drafts.post(url, json=body, headers={"Idempotency-Key": str(uuid4())})
    assert down.status_code == 503, down.text
    assert down.json()["detail"]["code"] == "email_store_unavailable"
    assert service.calls == []
