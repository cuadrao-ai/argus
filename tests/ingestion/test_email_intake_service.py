"""Email receiving without a provider, a database or a session: the queue rules."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.email_intake.models import RecipientRoute
from argus.domain.ingestion.email_intake.provider import EmailProviderError, ReceivedEmail
from argus.domain.ingestion.email_intake.service import EmailCapture
from argus.domain.ingestion.email_intake.store import (
    MAX_ATTEMPTS,
    InMemoryEmailStore,
    LeaseLost,
)
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import BusinessSpace
from PIL import Image

RECIPIENT = "recibos-ab12cd34@recibos.example.test"


def png() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
    return stream.getvalue()


def message(*attachments: tuple[str, str, bytes], subject="Factura ferretería") -> bytes:
    msg = EmailMessage()
    msg["From"] = "proveedor@example.test"
    msg["To"] = "forged-header@example.test"
    msg["Subject"] = subject
    msg.set_content("Adjunto la factura de hoy.")
    for filename, media, content in attachments:
        main, sub = media.split("/")
        msg.add_attachment(content, maintype=main, subtype=sub, filename=filename)
    return msg.as_bytes()


class Provider:
    def __init__(self, raw: bytes, recipients: tuple[str, ...]) -> None:
        self.raw, self.recipients, self.calls = raw, recipients, 0
        self.failure: EmailProviderError | None = None

    async def raw_message(self, email_id: str) -> ReceivedEmail:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return ReceivedEmail(self.raw, self.recipients)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class Rig:
    runtime: EmailCapture
    store: InMemoryEmailStore
    documents: DocumentsService
    provider: Provider
    route: RecipientRoute
    clock: Clock
    checks: list[str]
    revoked: set[str]

    @property
    def scope(self) -> BusinessSpace:
        return BusinessSpace(self.route.space_id)

    def enqueue(self, *recipients: str, external_id: str | None = None):
        return self.runtime.enqueue_resend(
            external_id or str(uuid4()), recipients or (RECIPIENT,)
        )

    def drafts(self):
        return [
            self.documents.get(
                user_id=self.route.principal_id, connection_id=c.id, scope=self.scope
            )
            for c in self.documents.hub.connections.list(
                user_id=self.route.principal_id, scope=self.scope
            )
        ]


def rig(raw: bytes | None = None, recipients: tuple[str, ...] = (RECIPIENT,)) -> Rig:
    clock = Clock()
    repo = InMemoryConnectionRepository()
    hub = IngestionHub(repo, box=None, sink=None, clock=clock)
    documents = DocumentsService(
        hub, InMemoryDocumentStore(repo), Mock(extract=AsyncMock())
    )
    store = InMemoryEmailStore(clock)
    route = store.create_route(
        recipient=RECIPIENT,
        space_id=str(uuid4()),
        principal_id=str(uuid4()),
        granted_by=str(uuid4()),
        grant_id=str(uuid4()),
    )
    checks: list[str] = []
    revoked: set[str] = set()

    def authority(live: RecipientRoute) -> None:
        checks.append(live.id)
        if live.grant_id in revoked:
            raise ActionError("not_found", "business_record_not_found")

    provider = Provider(
        raw if raw is not None else message(("recibo.png", "image/png", png())),
        recipients,
    )
    runtime = EmailCapture(
        store, documents, authority, provider, lambda: True, lambda: True
    )
    return Rig(runtime, store, documents, provider, route, clock, checks, revoked)


@pytest.mark.asyncio
async def test_signed_event_becomes_one_capture_with_original_and_parts_and_no_consent():
    world = rig(
        message(
            ("recibo.png", "image/png", png()), ("filas.csv", "text/csv", b"a,b\n1,2\n")
        )
    )
    delivery = world.enqueue()
    assert (delivery.state, delivery.route_id, delivery.space_id) == (
        "received",
        world.route.id,
        world.route.space_id,
    )
    assert await world.runtime.next()
    saved = world.store.get(delivery.id, world.route.space_id)
    assert (saved.state, saved.error_code, saved.subject, saved.sender) == (
        "captured",
        None,
        "Factura ferretería",
        "proveedor@example.test",
    )
    assert saved.original_document_id is not None
    parts = world.store.parts(delivery.id)
    assert [(p.filename, p.media_type, p.state) for p in parts] == [
        ("recibo.png", "image/png", "captured"),
        ("filas.csv", "text/csv", "captured"),
    ]
    drafts = world.drafts()
    assert sorted(d.filename for d in drafts) == [
        "filas.csv",
        "forwarded.eml",
        "recibo.png",
    ]
    assert all(d.consent is False and d.status == "saved" for d in drafts)
    assert world.provider.calls == 1
    assert world.checks == [world.route.id] * 3
    # The provider's replay of the same event is the same row and no second capture.
    assert world.enqueue(external_id=delivery.external_id).id == delivery.id
    assert not await world.runtime.next()
    assert world.provider.calls == 1
    world.documents.extractor.extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_or_ambiguous_recipient_is_rejected_before_any_fetch():
    world = rig()
    unknown = world.enqueue("nobody@recibos.example.test")
    assert (unknown.state, unknown.error_code, unknown.route_id) == (
        "rejected",
        "email_route_unavailable",
        None,
    )
    other = world.store.create_route(
        recipient="recibos-ffff0000@recibos.example.test",
        space_id=str(uuid4()),
        principal_id=str(uuid4()),
        granted_by=str(uuid4()),
        grant_id=str(uuid4()),
    )
    both = world.enqueue(RECIPIENT, other.recipient)
    assert (both.state, both.error_code) == ("rejected", "email_route_ambiguous")
    assert not await world.runtime.next()
    assert world.provider.calls == 0


@pytest.mark.asyncio
async def test_revoked_grant_stops_the_route_at_enqueue_and_again_before_fetch():
    world = rig()
    world.revoked.add(world.route.grant_id)
    rejected = world.enqueue()
    assert (rejected.state, rejected.error_code, rejected.route_id) == (
        "rejected",
        "email_route_revoked",
        None,
    )
    world.revoked.clear()
    queued = world.enqueue()
    world.revoked.add(world.route.grant_id)
    assert await world.runtime.next()
    assert (
        world.store.get(queued.id, world.route.space_id).error_code
        == "email_route_revoked"
    )
    assert world.provider.calls == 0
    assert world.drafts() == []


@pytest.mark.asyncio
async def test_provider_recipients_must_equal_the_signed_event_recipients():
    world = rig(recipients=("someone-else@recibos.example.test",))
    delivery = world.enqueue()
    assert await world.runtime.next()
    saved = world.store.get(delivery.id, world.route.space_id)
    assert (saved.state, saved.error_code) == ("rejected", "email_recipient_mismatch")
    assert world.drafts() == []


@pytest.mark.asyncio
async def test_unsupported_sibling_never_blocks_the_good_attachment():
    world = rig(
        message(
            ("recibo.png", "image/png", png()),
            ("virus.exe", "application/octet-stream", b"MZ"),
        )
    )
    delivery = world.enqueue()
    assert await world.runtime.next()
    saved = world.store.get(delivery.id, world.route.space_id)
    # The whole message stays one readable document: the bad part is noted
    # inside it, and refused only as a document of its own.
    assert (saved.state, saved.error_code) == ("captured", "email_parts_rejected")
    assert saved.original_document_id is not None
    assert [
        (p.filename, p.state, p.error_code) for p in world.store.parts(delivery.id)
    ] == [
        ("recibo.png", "captured", None),
        ("virus.exe", "rejected", "unsupported_media_type"),
    ]
    assert sorted(d.filename for d in world.drafts()) == ["forwarded.eml", "recibo.png"]


@pytest.mark.asyncio
async def test_transient_storage_failure_keeps_the_delivery_retryable_and_resumes_only_pending_parts(
    monkeypatch,
):
    world = rig(
        message(("first.png", "image/png", png()), ("later.png", "image/png", png()))
    )
    uploads: list[str] = []
    original = world.documents.upload
    failing = {"later.png"}

    async def upload(**kwargs):
        uploads.append(kwargs["filename"])
        if kwargs["filename"] in failing:
            failing.clear()
            raise DocumentServiceError("document_storage_unavailable", retryable=True)
        return await original(**kwargs)

    monkeypatch.setattr(world.documents, "upload", upload)
    delivery = world.enqueue()
    assert await world.runtime.next()
    saved = world.store.get(delivery.id, world.route.space_id)
    assert (saved.state, saved.error_code) == ("partial", "email_capture_incomplete")
    assert world.runtime.retryable(saved) is True
    assert [(p.filename, p.state) for p in world.store.parts(delivery.id)] == [
        ("first.png", "captured"),
        ("later.png", "pending"),
    ]
    assert not await world.runtime.next()  # backoff holds it
    world.clock.advance(11)
    assert await world.runtime.next()
    assert world.store.get(delivery.id, world.route.space_id).state == "captured"
    assert uploads == ["forwarded.eml", "first.png", "later.png", "later.png"]
    assert (
        world.provider.calls == 1
    )  # the retained original, not the provider, feeds the retry


@pytest.mark.asyncio
async def test_provider_outage_backs_off_caps_attempts_and_waits_for_an_explicit_retry():
    world = rig()
    world.provider.failure = EmailProviderError("provider_unavailable", retryable=True)
    delivery = world.enqueue()
    for _ in range(MAX_ATTEMPTS):
        world.clock.advance(400)
        assert await world.runtime.next()
    world.clock.advance(400)
    assert not await world.runtime.next()
    saved = world.store.get(delivery.id, world.route.space_id)
    assert (saved.state, saved.attempts, saved.error_code) == (
        "partial",
        MAX_ATTEMPTS,
        "provider_unavailable",
    )
    world.provider.failure = None
    assert world.store.retry(delivery.id, world.route.space_id)
    assert await world.runtime.next()
    assert world.store.get(delivery.id, world.route.space_id).state == "captured"


@pytest.mark.asyncio
async def test_receiving_switched_off_does_no_work_and_offers_no_retry():
    world = rig()
    world.runtime.receiving_enabled = lambda: False
    delivery = world.enqueue()
    assert not await world.runtime.next()
    assert world.store.get(delivery.id, world.route.space_id).state == "received"
    assert world.provider.calls == 0


def test_in_memory_queue_enforces_leases_and_single_claims():
    world = rig()
    first = world.enqueue()
    claimed = world.store.claim()
    assert claimed.id == first.id and claimed.state == "processing"
    assert world.store.claim() is None
    world.store.finish(claimed, "captured")
    # A worker holding the old token cannot write after the row settled.
    with pytest.raises(LeaseLost):
        world.store.finish(claimed, "captured")
    assert world.store.claim() is None


def test_the_earliest_save_of_a_file_is_the_business_s_not_one_person_s():
    """Two people of one Business saving the same bytes are two documents; the
    Business's first save is the one the email repeat mark compares against,
    and another Business's save never counts."""

    import asyncio
    from datetime import timedelta

    world = rig()
    documents, clock = world.documents, world.clock
    content = png()
    digest = __import__("hashlib").sha256(content).hexdigest()
    space, other_space = world.route.space_id, str(uuid4())
    assert documents.store.earliest_saved(space_id=space, sha256=digest) is None
    accountant, owner = str(uuid4()), world.route.principal_id
    asyncio.run(
        documents.upload(
            user_id=accountant,
            scope=BusinessSpace(space),
            content=content,
            filename="a.png",
            media_type="image/png",
            consent=False,
        )
    )
    first = clock.now
    clock.advance(60)
    asyncio.run(
        documents.upload(
            user_id=owner,
            scope=BusinessSpace(space),
            content=content,
            filename="b.png",
            media_type="image/png",
            consent=False,
        )
    )
    clock.advance(60)
    asyncio.run(
        documents.upload(
            user_id=owner,
            scope=BusinessSpace(other_space),
            content=content,
            filename="c.png",
            media_type="image/png",
            consent=False,
        )
    )
    assert documents.store.earliest_saved(space_id=space, sha256=digest) == first
    assert documents.store.earliest_saved(
        space_id=other_space, sha256=digest
    ) == first + timedelta(seconds=120)
    assert documents.store.earliest_saved(space_id=space, sha256="0" * 64) is None


@pytest.mark.asyncio
async def test_aggregate_pixel_overflow_rejects_before_any_document_capture(monkeypatch):
    from argus.domain.ingestion.documents import preparation

    monkeypatch.setattr(preparation, "MAX_PIXELS", 2 * 32 * 32 - 1)
    world = rig(message(("one.png", "image/png", png()), ("two.png", "image/png", png())))
    delivery = world.enqueue()
    assert await world.runtime.next()
    saved = world.store.get(delivery.id, world.route.space_id)
    assert (saved.state, saved.error_code) == ("rejected", "document_email_limit")
    assert not world.drafts()
    assert not world.store.parts(delivery.id)


@pytest.mark.asyncio
async def test_ai_dispatch_happens_after_capture_settles_and_failure_keeps_original():
    world = rig(message(("receipt.png", "image/png", png())))
    delivery = world.enqueue()
    seen = []

    async def read(route, connection_id):
        captured = world.store.get(delivery.id, route.space_id)
        assert captured.state == "captured"
        assert captured.lease_token is None
        seen.append(connection_id)
        raise DocumentServiceError("document_reading_not_allowed")

    world.runtime.read_receipt = read
    assert await world.runtime.next()
    captured = world.store.get(delivery.id, world.route.space_id)
    assert captured.state == "captured"
    assert captured.original_document_id is not None
    assert len(seen) == 1
    assert seen[0] != captured.original_document_id
    assert len(world.drafts()) == 2
