"""The Bandeja counts include each email that is a row of its own (still being
read, or brought no receipt), over HTTP on real Postgres: the sidebar badge, the
Bandeja list and the Resumen read one number, and an email that later brings a
receipt is never counted twice."""

from __future__ import annotations

import asyncio
from email.message import EmailMessage
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.business import require_business, require_business_surface
from argus.api.email_intake import configure_email_intake, email_intake
from argus.api.routers import business as business_api
from argus.api.routers import email_intake as email_api
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.service import DocumentServiceError
from faker import Faker
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_business_email_intake_postgres as intake
from tests import test_business_receipt_views_postgres as views

actions = intake.actions
users = intake.users
rig = intake.rig
pytestmark = intake.pytestmark

fake = Faker()
PERIOD = {"from": "2026-10-01", "to": "2026-10-31"}


def unreadable() -> bytes:
    """No body text and one attachment the reader refuses: nothing to save."""

    msg = EmailMessage()
    msg["From"] = "proveedor@example.test"
    msg["Subject"] = fake.sentence()
    msg.add_attachment(
        b"MZ", maintype="application", subtype="octet-stream", filename="virus.exe"
    )
    return msg.as_bytes()


def with_receipt(*, attached: bool = True) -> bytes:
    """A readable email; without an attachment its own text is the receipt."""

    msg = EmailMessage()
    msg["From"] = "proveedor@example.test"
    msg["Subject"] = fake.sentence()
    msg.set_content(fake.paragraph())
    if attached:
        msg.add_attachment(
            intake.receipt_png(), maintype="image", subtype="png", filename="recibo.png"
        )
    return msg.as_bytes()


@pytest.fixture
def bandeja(rig, actions):
    web = views._web(actions[0], actions[1])
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = str(uuid4())
        return await call_next(request)

    app.dependency_overrides[require_business] = lambda: web
    app.dependency_overrides[require_business_surface] = lambda: None
    app.include_router(business_api.router)
    app.include_router(email_api.router)
    previous = email_intake()
    configure_email_intake(rig["runtime"])
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(rig=rig, client=client)
    finally:
        configure_email_intake(previous)


def arrive(bandeja, raw: bytes, *, run: bool = True) -> str:
    rig = bandeja.rig
    rig["provider"].raw = raw
    delivery = rig["runtime"].enqueue_resend(str(uuid4()), (rig["route"].recipient,))
    if run:
        assert asyncio.run(rig["runtime"].next())
    return delivery.id


def numbers(bandeja) -> dict[str, int]:
    """The three surfaces' counts; they must agree before any test reads them."""

    def read(path: str, **params):
        response = bandeja.client.get(path, params=params)
        assert response.status_code == 200, response.text
        return response.json()

    found = read("/business/receipt-activity")
    listed = read("/business/receipts")["activity"]
    overview = read("/business/overview", **PERIOD)
    both = (
        "pending_review_count",
        "needs_attention_count",
        "reading_count",
        "presentation",
    )
    assert {key: listed[key] for key in both} == {key: found[key] for key in both}
    assert overview["needs_attention"] == found["needs_attention_count"]
    assert (
        overview["awaiting_review"] + overview["needs_attention"]
        == found["pending_review_count"]
    )
    assert (found["presentation"] == "working") == (found["reading_count"] > 0)
    return {
        "pending": found["pending_review_count"],
        "attention": found["needs_attention_count"],
        "reading": found["reading_count"],
        "awaiting": overview["awaiting_review"],
    }


def standing(bandeja, delivery_id: str) -> str | None:
    """The delivery's standing; the list and the detail must agree."""

    items = bandeja.client.get("/business/email/deliveries").json()["items"]
    [row] = [item for item in items if item["id"] == delivery_id]
    detail = bandeja.client.get(f"/business/email/deliveries/{delivery_id}").json()
    assert detail["standing"] == row["standing"]
    assert "needs_attention" not in row
    return row["standing"]


def test_an_email_that_saved_nothing_counts_once_in_every_surface(bandeja):
    before = numbers(bandeja)
    delivery_id = arrive(bandeja, unreadable())
    saved = bandeja.rig["store"].get(delivery_id, bandeja.rig["route"].space_id)
    assert (saved.state, saved.error_code, saved.original_document_id) == (
        "captured",
        "email_parts_rejected",
        None,
    )
    assert standing(bandeja, delivery_id) == "no_receipt"
    after = numbers(bandeja)
    assert after["pending"] == before["pending"] + 1
    assert after["attention"] == before["attention"] + 1
    assert after["reading"] == before["reading"]
    assert after["awaiting"] == before["awaiting"]
    inbox = bandeja.client.get("/business/email/inbox").json()["groups"]
    assert [item["standing"] for group in inbox for item in group["items"]] == [
        "no_receipt"
    ]


@pytest.mark.parametrize(
    ("attached", "original"),
    [(True, True), (True, False), (False, True)],
    ids=["attachment", "attachment-original-refused", "body-only"],
)
def test_an_email_that_brought_a_receipt_counts_as_that_receipt_only(
    bandeja, monkeypatch, attached, original
):
    documents = bandeja.rig["documents"]
    upload = documents.upload

    async def refuse_the_message(**kwargs):
        if kwargs["media_type"] == "message/rfc822":
            raise DocumentExtractionError("document_too_large")
        return await upload(**kwargs)

    if not original:
        monkeypatch.setattr(documents, "upload", refuse_the_message)
    before = numbers(bandeja)
    delivery_id = arrive(bandeja, with_receipt(attached=attached))
    saved = bandeja.rig["store"].get(delivery_id, bandeja.rig["route"].space_id)
    assert (saved.state, saved.original_document_id is not None) == ("captured", original)
    assert standing(bandeja, delivery_id) is None
    after = numbers(bandeja)
    assert after["pending"] == before["pending"] + 1
    assert after["attention"] == before["attention"]
    assert after["reading"] == before["reading"]
    assert after["awaiting"] == before["awaiting"] + 1


def test_a_retry_that_brings_the_receipt_replaces_the_email_count(bandeja, monkeypatch):
    rig = bandeja.rig
    documents = rig["documents"]
    upload = documents.upload
    outage = {"on": True}

    async def flaky(**kwargs):
        if outage["on"]:
            raise DocumentServiceError("document_storage_unavailable", retryable=True)
        return await upload(**kwargs)

    monkeypatch.setattr(documents, "upload", flaky)
    before = numbers(bandeja)
    delivery_id = arrive(bandeja, with_receipt())
    space = rig["route"].space_id
    assert rig["store"].get(delivery_id, space).state == "partial"
    assert rig["store"].parts(delivery_id) == []
    assert standing(bandeja, delivery_id) == "no_receipt"
    stuck = numbers(bandeja)
    assert stuck["pending"] == before["pending"] + 1
    assert stuck["attention"] == before["attention"] + 1
    assert stuck["reading"] == before["reading"]

    outage["on"] = False
    assert rig["store"].retry(delivery_id, space)
    assert asyncio.run(rig["runtime"].next())
    assert rig["store"].get(delivery_id, space).state == "captured"
    assert standing(bandeja, delivery_id) is None
    done = numbers(bandeja)
    assert done["pending"] == before["pending"] + 1
    assert done["attention"] == before["attention"]
    assert done["awaiting"] == before["awaiting"] + 1


def test_an_email_still_being_read_waits_and_is_reading_not_attention(bandeja):
    rig = bandeja.rig
    space = rig["route"].space_id
    before = numbers(bandeja)

    waiting = arrive(bandeja, unreadable(), run=False)
    assert rig["store"].get(waiting, space).state == "received"
    assert standing(bandeja, waiting) == "reading"
    received = numbers(bandeja)
    assert received["pending"] == before["pending"] + 1
    assert received["reading"] == before["reading"] + 1
    assert received["attention"] == before["attention"]
    assert received["awaiting"] == before["awaiting"] + 1
    assert bandeja.client.get("/business/receipt-activity").json()["presentation"] == (
        "working"
    )

    held = rig["store"].claim(delivery_id=waiting)
    assert rig["store"].get(waiting, space).state == "processing"
    assert standing(bandeja, waiting) == "reading"
    assert numbers(bandeja) == received

    rig["store"].finish(held, "rejected", "email_parts_rejected")
    assert standing(bandeja, waiting) == "no_receipt"
    settled = numbers(bandeja)
    assert settled["pending"] == before["pending"] + 1
    assert settled["reading"] == before["reading"]
    assert settled["attention"] == before["attention"] + 1
    assert settled["awaiting"] == before["awaiting"]


def test_a_blocked_sender_brought_no_receipt_and_counts(bandeja):
    rig = bandeja.rig
    before = numbers(bandeja)
    rig["store"].upsert_sender(
        rig["route"].space_id, "address", rig["provider"].sender, "blocked"
    )
    blocked = arrive(bandeja, unreadable())
    saved = rig["store"].get(blocked, rig["route"].space_id)
    assert (saved.state, saved.error_code) == ("rejected", "email_sender_blocked")
    assert standing(bandeja, blocked) == "no_receipt"
    settled = numbers(bandeja)
    assert settled["pending"] == before["pending"] + 1
    assert settled["attention"] == before["attention"] + 1
    assert settled["reading"] == before["reading"]
    assert settled["awaiting"] == before["awaiting"]


def test_an_email_that_only_repeats_a_saved_file_is_no_row_and_no_problem(bandeja):
    raw = with_receipt()
    first = arrive(bandeja, raw)
    assert standing(bandeja, first) is None
    before = numbers(bandeja)
    again = arrive(bandeja, raw)
    detail = bandeja.client.get(f"/business/email/deliveries/{again}").json()
    assert [part["repeat_of_delivery_id"] for part in detail["parts"]] == [first]
    assert detail["standing"] is None
    assert numbers(bandeja) == before
