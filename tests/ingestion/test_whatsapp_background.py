"""The webhook finishes each message before answering or claiming the next."""

import asyncio

import pytest

from tests.ingestion.test_whatsapp_intake import _world
from tests.ingestion.whatsapp_cases import ALICE_PHONE, image
from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media


class Gate:
    """A media source that waits until the test lets it through."""

    def __init__(self, inner) -> None:  # noqa: ANN001
        self.inner = inner
        self.opened, self.entered = asyncio.Event(), asyncio.Event()

    async def fetch(self, media_id: str):  # noqa: ANN202
        self.entered.set()
        await self.opened.wait()
        return await self.inner.fetch(media_id)


@pytest.mark.asyncio
async def test_delivery_waits_for_each_message_before_claiming_the_next() -> None:
    world = _world()
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")
    world.graph.media["700000000000202"] = Media(RECEIPT_PNG + b"\x00", "image/png")
    first_id, second_id = "wamid.INLINE-A", "wamid.INLINE-B"
    first = image("700000000000201", first_id)
    second = image("700000000000202", second_id)
    first["entry"][0]["changes"][0]["value"]["messages"].extend(
        second["entry"][0]["changes"][0]["value"]["messages"]
    )
    gate = world.intake.media = Gate(world.intake.media)
    delivery = asyncio.create_task(world.deliver(first))
    try:
        await asyncio.wait_for(gate.entered.wait(), timeout=2)
        assert not delivery.done()
        assert world.record(first_id).status == "received"
        assert world.record(second_id) is None
        assert world.captures(world.alice) == []
    finally:
        gate.opened.set()
        await asyncio.wait_for(delivery, timeout=5)

    assert [world.record(key).status for key in (first_id, second_id)] == [
        "captured",
        "captured",
    ]
    assert [item["context"]["message_id"] for item in world.transport.sent[1:]] == [
        first_id,
        second_id,
    ]
