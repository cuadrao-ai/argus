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
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
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
        self.merchant: str | None = "Ferretería Ochoa"

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
                    merchant=self.merchant,
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
        f"Leí: Ferretería Ochoa, 850 DOP. Revísalo antes de guardar: {link}",
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


@pytest.mark.asyncio
async def test_a_read_that_stops_leaves_the_receipt_saved_and_the_owner_unharmed() -> (
    None
):
    world, extractor = _world(switch={"on": True})
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")

    async def stopped(**_: Any) -> None:
        raise RuntimeError("process stopped")

    world.intake.destination.read = stopped
    await world.deliver(cases.image("700000000000201", "wamid.READ-STOP"))
    [connection_id] = world.captures(world.alice)
    assert _status(world, connection_id) == "queued"
    assert world.record("wamid.READ-STOP").status == "captured"
    assert len(world.transport.sent) == 2  # the link and the acknowledgement only


@pytest.mark.asyncio
async def test_a_redelivered_message_sends_one_follow_up() -> None:
    world, extractor = _world(switch={"on": True})
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")
    body = cases.image("700000000000201", "wamid.READ-TWICE")
    await world.deliver(body)
    await world.deliver(body)
    assert extractor.calls == 1
    assert len([b for b in world.transport.bodies() if b.startswith("Leí:")]) == 1


@pytest.mark.asyncio
async def test_with_outbound_off_the_receipt_is_read_and_nothing_is_sent() -> None:
    world, extractor = _world(switch={"on": True})
    await world.link(world.alice, ALICE_PHONE)
    sent_before = len(world.transport.sent)
    world.intake.send_enabled = lambda: False
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(cases.image("700000000000201", "wamid.READ-QUIET"))
    [connection_id] = world.captures(world.alice)
    assert _status(world, connection_id) == "review_ready"
    assert len(world.transport.sent) == sent_before


@pytest.mark.asyncio
async def test_the_follow_up_names_merchant_amount_and_currency_as_read() -> None:
    world, _ = _world(switch={"on": True})
    connection_id = await _send(world, "wamid.READ-FIELDS")
    assert world.transport.bodies()[-1] == (
        "Leí: Ferretería Ochoa, 850 DOP. Revísalo antes de guardar: "
        f"{cases.ORIGIN}/biz?receipt={connection_id}"
    )


@pytest.mark.asyncio
async def test_a_read_without_a_merchant_says_only_that_it_is_ready() -> None:
    world, extractor = _world(switch={"on": True})
    extractor.merchant = None
    connection_id = await _send(world, "wamid.READ-NO-MERCHANT")
    assert world.transport.bodies()[-1] == (
        "Ya leímos tu recibo. Revísalo y confírmalo en Cuadrao: "
        f"{cases.ORIGIN}/biz?receipt={connection_id}"
    )


@pytest.mark.asyncio
async def test_prepare_from_the_web_with_the_switch_off_is_refused_not_queued() -> None:
    world, extractor = _world(switch={"on": False})
    connection_id = await _send(world, "wamid.READ-WEB")
    scope = world.business(world.alice)
    with pytest.raises(DocumentServiceError) as refused:
        world.documents.queue(
            user_id=world.alice, connection_id=connection_id, consent=True, scope=scope
        )
    assert refused.value.code == "whatsapp_receipt_reading_off"
    assert _status(world, connection_id) == "saved"
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_anyone_asking_for_the_read_meets_the_owners_switch() -> None:
    switch = {"on": False}
    world, _ = _world(switch=switch)
    connection_id = await _send(world, "wamid.READ-ACTOR")
    accountant = str(uuid4())
    assert world.documents.read_gate(accountant, connection_id) is False
    switch["on"] = True
    assert world.documents.read_gate(accountant, connection_id) is True
    assert world.documents.read_gate(accountant, "not-from-whatsapp") is True


@pytest.mark.asyncio
async def test_a_switch_turned_off_while_the_source_is_read_stops_before_the_provider() -> (
    None
):
    world, extractor = _world(switch={"on": True})
    answers = iter([True, False])
    world.documents.read_gate = lambda *_: next(answers, False)
    connection_id = await _send(world, "wamid.READ-LATE")
    assert extractor.calls == 0
    assert _status(world, connection_id) == "saved"
    assert len(world.transport.sent) == 2
