"""A receipt sent by WhatsApp is read only while the owner's stored
receipt-reading setting is on."""

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.access import InMemoryAccessStore
from argus.domain.business.spaces import InMemorySpaceStore
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.ingestion.whatsapp.senders import SenderBusinesses
from argus.domain.ingestion.whatsapp.store import InMemoryWhatsAppStore

from tests.business_reading_support import reading_setting, turn_reading
from tests.document_extractor_support import StubPreparation, start_request
from tests.document_reads_support import read_receipt
from tests.ingestion import whatsapp_cases as cases
from tests.ingestion.whatsapp_link_support import SYNTHETIC_TAX_ID
from tests.ingestion.whatsapp_support import ALICE_PHONE, RECEIPT_PNG, Media


class Extractor(StubPreparation):
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.merchant: str | None = "Ferretería Ochoa"

    async def extract(self, **kwargs: Any) -> ExtractionBatch:
        await start_request(kwargs)
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider down")
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
                    merchant=self.merchant,
                    currency="DOP",
                    direction="outflow",
                ),
            )
        )


async def _world(*, on: bool) -> tuple[cases.World, Extractor, Callable[[bool], None]]:
    """The world, the provider stand-in and the owner's setting switch."""

    clock = cases.Clock()
    connections = InMemoryConnectionRepository()
    sink = Mock()
    sink.submit.return_value = SubmitResult(1, 0, 0)
    hub = IngestionHub(connections, box=None, sink=sink, clock=clock)
    extractor = Extractor()
    documents = DocumentsService(hub, InMemoryDocumentStore(connections), extractor)
    setting = reading_setting()
    documents.business_receipt_consent = setting
    access = InMemoryAccessStore()
    senders = SenderBusinesses(access, lambda _: SYNTHETIC_TAX_ID, lambda g: setting.status(g.space_id, g.owner_id))
    spaces, store = InMemorySpaceStore(), InMemoryWhatsAppStore(connections, access, senders.eligible_businesses)
    world = cases.build_world(
        documents=documents,
        store=store,
        clock=clock,
        alice=str(uuid4()),
        bob=str(uuid4()),
        spaces=spaces,
        access=access,
    )

    def turn(enabled: bool) -> None:
        turn_reading(setting, world.business(world.alice).space_id, world.alice, enabled)

    turn(True)
    await world.link(world.alice, ALICE_PHONE)
    if not on:
        turn(False)
    return world, extractor, turn


async def _deliver(world: cases.World, message_id: str) -> str:
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(cases.image("700000000000201", message_id))
    return world.record(message_id).connection_id


async def _send(world: cases.World, message_id: str) -> str:
    """Deliver a receipt, then let the document worker take its attempt."""
    connection_id = await _deliver(world, message_id)
    await read_receipt(world.documents, world.alice, connection_id)
    return connection_id


def _status(world: cases.World, connection_id: str) -> str:
    return world.documents.get(
        user_id=world.alice,
        connection_id=connection_id,
        scope=world.documents.hub.connections.get_any_scope(
            user_id=world.alice, connection_id=connection_id
        ).scope,
    ).status


@pytest.mark.asyncio
async def test_worker_read_does_not_send_a_second_reply() -> None:
    world, extractor, _ = await _world(on=True)
    connection_id = await _deliver(world, "wamid.READ-ON")
    assert _status(world, connection_id) == "queued"
    assert extractor.calls == 0
    replies = world.transport.bodies()
    assert len(replies) == 2
    assert replies[-1] == "Recibido. Lo estoy leyendo."
    await read_receipt(world.documents, world.alice, connection_id)
    assert _status(world, connection_id) == "review_ready"
    assert extractor.calls == 1
    assert world.transport.bodies() == replies


@pytest.mark.asyncio
async def test_with_the_switch_off_the_receipt_waits_unread_and_no_follow_up() -> None:
    world, extractor, _ = await _world(on=False)
    connection_id = await _deliver(world, "wamid.READ-OFF")
    assert _status(world, connection_id) == "saved"
    assert extractor.calls == 0
    assert len(world.transport.sent) == 2
    assert world.transport.bodies()[-1] == (
        f"Recibido. Revísalo aquí: {cases.ORIGIN}/biz?receipt={connection_id}"
    )


@pytest.mark.asyncio
async def test_same_bytes_resent_in_a_new_message_keep_one_receipt_and_one_read() -> None:
    world, extractor, _ = await _world(on=True)
    connection_id = await _deliver(world, "wamid.READ-FIRST")
    await world.deliver(cases.image("700000000000201", "wamid.READ-RESENT"))
    await world.deliver(cases.image("700000000000201", "wamid.READ-RESENT"))
    assert extractor.calls == 0
    await read_receipt(world.documents, world.alice, connection_id)
    assert world.captures(world.alice) == [connection_id]
    assert world.captures(world.bob) == []
    assert extractor.calls == 1
    assert _status(world, connection_id) == "review_ready"
    assert world.record("wamid.READ-RESENT").connection_id == connection_id
    assert world.transport.bodies()[-1].startswith("Ya lo teníamos.")


@pytest.mark.asyncio
async def test_with_outbound_off_the_receipt_is_read_and_nothing_is_sent() -> None:
    world, extractor, _ = await _world(on=True)
    sent_before = len(world.transport.sent)
    world.intake.send_enabled = lambda: False
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(cases.image("700000000000201", "wamid.READ-QUIET"))
    [connection_id] = world.captures(world.alice)
    await read_receipt(world.documents, world.alice, connection_id)
    assert _status(world, connection_id) == "review_ready"
    assert len(world.transport.sent) == sent_before


@pytest.mark.asyncio
async def test_prepare_from_the_web_with_the_switch_off_is_refused_not_queued() -> None:
    world, extractor, turn = await _world(on=True)
    connection_id = await _deliver(world, "wamid.READ-WEB")
    turn(False)
    await read_receipt(world.documents, world.alice, connection_id)
    scope = world.business(world.alice)
    with pytest.raises(DocumentServiceError) as refused:
        world.documents.queue(
            user_id=world.alice, connection_id=connection_id, consent=True, scope=scope
        )
    assert refused.value.code == "business_receipt_reading_off"
    assert _status(world, connection_id) == "saved"
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_a_switch_turned_off_while_the_source_is_read_stops_before_the_provider() -> (
    None
):
    world, extractor, turn = await _world(on=True)
    store = world.documents.store
    source = store.source

    def revoke_while_reading(**kwargs: Any) -> bytes | None:
        turn(False)
        return source(**kwargs)

    store.source = revoke_while_reading
    connection_id = await _send(world, "wamid.READ-LATE")
    assert extractor.calls == 0
    assert _status(world, connection_id) == "saved"
    assert len(world.transport.bodies()) == 2
