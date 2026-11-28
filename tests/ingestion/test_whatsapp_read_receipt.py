from datetime import timedelta

import pytest

from tests.ingestion.test_whatsapp_intake import _world
from tests.ingestion.whatsapp_cases import ALICE_PHONE, image
from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media


@pytest.mark.asyncio
async def test_read_receipt_follows_a_committed_save_once(monkeypatch) -> None:
    world = _world()
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000601"] = Media(RECEIPT_PNG, "image/png")
    message_id = "wamid.SAVED"
    outbound = []

    async def observe(payload: dict) -> None:
        assert world.record(message_id).status == "captured"
        outbound.append(payload)

    monkeypatch.setattr(world.transport, "send", observe)
    await world.deliver(image("700000000000601", message_id))
    await world.deliver(image("700000000000601", message_id))
    await world.deliver(image("700000000000601", "wamid.DUPLICATE"))
    assert outbound == [
        {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
    ]


@pytest.mark.asyncio
async def test_uncommitted_capture_never_acknowledges_or_groups(monkeypatch) -> None:
    world = _world()
    await world.link(world.alice, ALICE_PHONE)
    world.transport.sent.clear()
    world.graph.media["700000000000602"] = Media(RECEIPT_PNG, "image/png")

    def fail_commit(**kwargs) -> None:
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(world.store, "settle", fail_commit)
    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        await world.deliver(image("700000000000602", "wamid.COMMIT-FAILED"))
    assert world.transport.sent == []
    assert world.store.reply_failures == []


@pytest.mark.asyncio
async def test_read_receipt_stops_at_service_window_boundary() -> None:
    world = _world()
    await world.link(world.alice, ALICE_PHONE)
    world.transport.sent.clear()
    world.graph.media["700000000000603"] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(
        image("700000000000603", "wamid.OLD-SAVE"),
        sent_at=world.clock.now - timedelta(hours=24),
    )
    assert world.record("wamid.OLD-SAVE").status == "captured"
    assert world.transport.sent == []
