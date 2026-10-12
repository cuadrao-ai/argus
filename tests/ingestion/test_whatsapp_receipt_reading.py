"""A receipt sent by WhatsApp is read only while the owner's switch is on."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.api.whatsapp import DocumentsDestination, _whatsapp_read_gate
from argus.domain.business.spaces import InMemorySpaceStore
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.ingestion.whatsapp.store import InMemoryWhatsAppStore

from tests.ingestion import whatsapp_cases as cases
from tests.ingestion.whatsapp_support import ALICE_PHONE, RECEIPT_PNG, Media


class Extractor:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    async def extract(self, **kwargs: Any) -> ExtractionBatch:
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
                    currency="DOP",
                    direction="outflow",
                ),
            )
        )


def _world(*, switch: dict) -> tuple[cases.World, Extractor]:
    clock = cases.Clock()
    connections = InMemoryConnectionRepository()
    sink = Mock()
    sink.submit.return_value = SubmitResult(1, 0, 0)
    hub = IngestionHub(connections, box=None, sink=sink, clock=clock)
    extractor = Extractor()
    documents = DocumentsService(hub, InMemoryDocumentStore(connections), extractor)
    spaces, store = InMemorySpaceStore(), InMemoryWhatsAppStore()
    world = cases.build_world(
        documents=documents,
        store=store,
        clock=clock,
        alice=str(uuid4()),
        bob=str(uuid4()),
        spaces=spaces,
    )
    reading = lambda owner: switch["on"]  # noqa: E731
    world.intake.destination = DocumentsDestination(documents, spaces, reading)
    documents.read_gate = _whatsapp_read_gate(store, reading)
    return world, extractor


async def _send(world: cases.World, message_id: str) -> str:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(cases.image("700000000000201", message_id))
    [connection_id] = world.captures(world.alice)
    return connection_id


def _status(world: cases.World, connection_id: str) -> str:
    return world.documents.get(
        user_id=world.alice,
        connection_id=connection_id,
        scope=world.business(world.alice),
    ).status


@pytest.mark.asyncio
async def test_with_the_switch_on_the_receipt_is_read_and_followed_up_once() -> None:
    world, extractor = _world(switch={"on": True})
    connection_id = await _send(world, "wamid.READ-ON")
    link = f"{cases.ORIGIN}/biz?receipt={connection_id}"
    assert _status(world, connection_id) == "review_ready"
    assert extractor.calls == 1
    assert world.transport.bodies()[-2:] == [
        "Recibimos tu recibo y lo guardamos en tu bandeja. "
        f"Revísalo y confírmalo en Cuadrao: {link}",
        f"Ya leímos tu recibo. Revísalo y confírmalo en Cuadrao: {link}",
    ]


@pytest.mark.asyncio
async def test_with_the_switch_off_the_receipt_waits_unread_and_no_follow_up() -> None:
    world, extractor = _world(switch={"on": False})
    connection_id = await _send(world, "wamid.READ-OFF")
    assert _status(world, connection_id) == "saved"
    assert extractor.calls == 0
    assert len(world.transport.sent) == 2


@pytest.mark.asyncio
async def test_a_switch_turned_off_after_capture_stops_the_read() -> None:
    switch = {"on": True}
    world, extractor = _world(switch=switch)
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")
    # The owner revokes between the save and the read.
    original = world.intake.destination.read

    async def revoke_then_read(**kwargs: Any) -> str | None:
        switch["on"] = False
        return await original(**kwargs)

    world.intake.destination.read = revoke_then_read
    await world.deliver(cases.image("700000000000201", "wamid.READ-REVOKED"))
    [connection_id] = world.captures(world.alice)
    assert extractor.calls == 0
    assert _status(world, connection_id) == "saved"
    assert len(world.transport.sent) == 2


@pytest.mark.asyncio
async def test_a_read_that_fails_sends_the_open_it_follow_up() -> None:
    world, extractor = _world(switch={"on": True})
    extractor.fail = True
    connection_id = await _send(world, "wamid.READ-FAIL")
    assert _status(world, connection_id) == "needs_attention"
    assert world.transport.bodies()[-1] == (
        "No pudimos leer bien tu recibo. Ábrelo en Cuadrao para completarlo: "
        f"{cases.ORIGIN}/biz?receipt={connection_id}"
    )


@pytest.mark.asyncio
async def test_no_follow_up_outside_the_service_window() -> None:
    world, extractor = _world(switch={"on": True})
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")
    sent = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    await world.deliver(cases.image("700000000000201", "wamid.READ-OLD"), sent)
    assert extractor.calls == 1
    assert len(world.transport.sent) == 1
