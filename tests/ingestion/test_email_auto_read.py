"""An emailed receipt is read on its own only while the owner's permission is on
at that moment; a person's own click is never gated by that switch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.api.email_intake import EmailReader, automatic_read_gate
from argus.domain.business.authority import ActionError
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.email_intake.models import RecipientRoute
from argus.domain.ingestion.email_intake.service import EmailCapture
from argus.domain.ingestion.email_intake.store import InMemoryEmailStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import BusinessSpace

from tests.ingestion.test_email_intake_service import (
    RECIPIENT,
    Clock,
    Provider,
    message,
    png,
)


class Extractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, **kwargs: Any) -> ExtractionBatch:
        self.calls += 1
        return ExtractionBatch(
            candidates=(
                ImportCandidate(
                    source=SourceRef(
                        source="statement",
                        connection_id=kwargs["connection_id"],
                        external_id="document:p1:r1",
                        observed_at=kwargs["observed_at"],
                    ),
                    evidence="transaction",
                    amount="850.00",
                    merchant="Ferretería Ochoa",
                    currency="DOP",
                    direction="outflow",
                ),
            )
        )


class Permission:
    """The owner's switch as the runtime reads it: fresh on every ask."""

    def __init__(self, on: bool = True) -> None:
        self.on = on
        self.asked: list[str] = []
        self.answers: list[bool] | None = None

    def reading_allowed(self, space_id: str) -> bool:
        self.asked.append(space_id)
        if self.answers:
            return self.answers.pop(0)
        return self.on


@dataclass
class Rig:
    runtime: EmailCapture
    store: InMemoryEmailStore
    documents: DocumentsService
    extractor: Extractor
    permission: Permission
    provider: Provider
    route: RecipientRoute

    @property
    def scope(self) -> BusinessSpace:
        return BusinessSpace(self.route.space_id)

    def enqueue(self, external_id: str | None = None):  # noqa: ANN201
        return self.runtime.enqueue_resend(external_id or str(uuid4()), (RECIPIENT,))

    def drafts(self) -> dict[str, Any]:
        return {
            draft.filename: draft
            for draft in (
                self.documents.get(
                    user_id=self.route.principal_id, connection_id=c.id, scope=self.scope
                )
                for c in self.documents.hub.connections.list(
                    user_id=self.route.principal_id, scope=self.scope
                )
            )
        }


def rig(*, on: bool = True, raw: bytes | None = None) -> Rig:
    clock = Clock()
    repo = InMemoryConnectionRepository()
    sink = Mock()
    sink.submit.return_value = SubmitResult(1, 0, 0)
    hub = IngestionHub(repo, box=None, sink=sink, clock=clock)
    extractor = Extractor()
    documents = DocumentsService(hub, InMemoryDocumentStore(repo), extractor)
    store = InMemoryEmailStore(clock)
    route = store.create_route(
        recipient=RECIPIENT,
        space_id=str(uuid4()),
        principal_id=str(uuid4()),
        granted_by=str(uuid4()),
        grant_id=str(uuid4()),
    )
    permission = Permission(on)
    provider = Provider(
        raw if raw is not None else message(("recibo.png", "image/png", png())),
        (RECIPIENT,),
    )
    runtime = EmailCapture(
        store,
        documents,
        lambda live: None,
        provider,
        lambda: True,
        lambda: True,
        reading=permission.reading_allowed,
        reader=EmailReader(documents),
    )
    documents.add_read_gate(automatic_read_gate(runtime, permission))
    return Rig(runtime, store, documents, extractor, permission, provider, route)


@pytest.mark.asyncio
async def test_with_the_permission_on_the_attachment_is_read_and_the_original_never():
    world = rig(on=True)
    delivery = world.enqueue()
    assert await world.runtime.next()
    drafts = world.drafts()
    assert (drafts["recibo.png"].status, drafts["recibo.png"].consent) == (
        "review_ready",
        True,
    )
    assert (drafts["forwarded.eml"].status, drafts["forwarded.eml"].consent) == (
        "saved",
        False,
    )
    assert world.extractor.calls == 1
    # Asked at capture, by Business; then when the read starts and before the provider.
    assert world.permission.asked == [world.route.space_id] * 3
    assert world.store.get(delivery.id, world.route.space_id).state == "captured"


@pytest.mark.asyncio
async def test_with_the_permission_off_or_unseen_the_attachment_waits_saved_unread():
    world = rig(on=False)
    world.enqueue()
    assert await world.runtime.next()
    draft = world.drafts()["recibo.png"]
    assert (draft.status, draft.consent) == ("saved", False)
    assert world.extractor.calls == 0
    assert world.permission.asked == [world.route.space_id]


@pytest.mark.asyncio
async def test_a_runtime_without_a_permission_store_never_reads_on_its_own():
    world = rig(on=True)
    world.runtime.reading = None
    world.enqueue()
    assert await world.runtime.next()
    assert world.drafts()["recibo.png"].status == "saved"
    assert world.extractor.calls == 0


@pytest.mark.asyncio
async def test_a_permission_turned_off_between_the_capture_and_the_queue_stops_the_read():
    world = rig(on=True)
    # On at capture; off by the time the read is queued.
    world.permission.answers = [True, False]
    world.enqueue()
    assert await world.runtime.next()
    draft = world.drafts()["recibo.png"]
    assert (draft.status, draft.consent) == ("saved", False)
    assert world.extractor.calls == 0


@pytest.mark.asyncio
async def test_a_permission_turned_off_while_the_source_is_read_stops_before_the_provider():
    world = rig(on=True)
    # On at capture and when the read starts; off right before the provider.
    world.permission.answers = [True, True, False]
    world.enqueue()
    assert await world.runtime.next()
    draft = world.drafts()["recibo.png"]
    assert (draft.status, draft.consent) == ("saved", False)
    assert world.extractor.calls == 0


@pytest.mark.asyncio
async def test_a_replayed_event_and_the_same_bytes_in_a_second_email_read_once():
    world = rig(on=True)
    first = world.enqueue()
    assert await world.runtime.next()
    assert world.extractor.calls == 1
    # The provider replays the same event: the same row, no second capture, no second read.
    assert world.enqueue(external_id=first.external_id).id == first.id
    assert not await world.runtime.next()
    # A second email brings the same file: one receipt, already read, never read twice.
    second = world.enqueue()
    assert await world.runtime.next()
    assert world.extractor.calls == 1
    [part] = [p for p in world.store.parts(second.id) if p.filename == "recibo.png"]
    assert part.state == "captured"
    assert world.drafts()["recibo.png"].status == "review_ready"


@pytest.mark.asyncio
async def test_a_persons_own_prepare_is_never_gated_by_the_email_switch():
    world = rig(on=False)
    world.enqueue()
    assert await world.runtime.next()
    draft = world.drafts()["recibo.png"]
    assert draft.status == "saved"
    outcome = world.documents.queue(
        user_id=world.route.principal_id,
        connection_id=draft.connection_id,
        consent=True,
        scope=world.scope,
    )
    assert (
        world.documents.get(
            user_id=world.route.principal_id,
            connection_id=outcome.connection_id,
            scope=world.scope,
        ).status
        == "queued"
    )


@pytest.mark.asyncio
async def test_a_read_that_cannot_start_leaves_the_receipt_saved_with_the_reason():
    world = rig(on=True)

    async def refuse(*args: Any, **kwargs: Any) -> None:
        raise ActionError("permission_denied", "business_permission_denied")

    world.runtime.reader = refuse
    delivery = world.enqueue()
    assert await world.runtime.next()
    assert world.drafts()["recibo.png"].status == "saved"
    assert world.store.get(delivery.id, world.route.space_id).state == "captured"


@pytest.mark.asyncio
async def test_the_marker_survives_a_restart_so_a_revoked_switch_stops_a_queued_read():
    """The draft itself says the owner's switch asked for the read. A process
    that starts after the queue (a deploy restarts the API) builds a fresh gate
    and still refuses that read once the permission is off; a person's own
    click is marked as theirs and goes on."""

    world = rig(on=True)

    async def queue_only(delivery, document: str) -> None:  # noqa: ANN001
        world.documents.queue(
            user_id=delivery.principal_id,
            connection_id=document,
            consent=True,
            scope=BusinessSpace(delivery.space_id),
            automatic=True,
        )

    world.runtime.reader = queue_only
    world.enqueue()
    assert await world.runtime.next()
    queued = world.drafts()["recibo.png"]
    assert (queued.status, queued.consent, queued.read_by) == (
        "queued",
        True,
        "email_switch",
    )
    # The process restarts: a new runtime and a new gate, nothing remembered in memory.
    world.documents.read_gate = None
    fresh = EmailCapture(
        world.store,
        world.documents,
        lambda live: None,
        world.provider,
        lambda: True,
        lambda: True,
    )
    world.documents.add_read_gate(automatic_read_gate(fresh, world.permission))
    world.permission.on = False
    await world.documents.background_prepare(
        user_id=world.route.principal_id,
        connection_id=queued.connection_id,
        scope=world.scope,
    )
    after = world.drafts()["recibo.png"]
    assert (after.status, after.consent) == ("saved", False)
    assert world.extractor.calls == 0
    # The person asks for it themselves: marked as theirs, read while the switch is off.
    world.documents.queue(
        user_id=world.route.principal_id,
        connection_id=queued.connection_id,
        consent=True,
        scope=world.scope,
    )
    assert world.drafts()["recibo.png"].read_by == "person"
    await world.documents.background_prepare(
        user_id=world.route.principal_id,
        connection_id=queued.connection_id,
        scope=world.scope,
    )
    assert world.drafts()["recibo.png"].status == "review_ready"
    assert world.extractor.calls == 1
