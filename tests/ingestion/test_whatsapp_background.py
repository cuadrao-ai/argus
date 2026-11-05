"""With a background runner the webhook answers once every claim is committed."""

import asyncio

import pytest
from argus.api.whatsapp import BackgroundWork
from argus.domain.ingestion.whatsapp.intake import DeliveryInFlight
from argus.domain.ingestion.whatsapp.media import MediaUnavailable

from tests.ingestion.test_whatsapp_intake import _world
from tests.ingestion.whatsapp_cases import ALICE_PHONE, ORIGIN, image
from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media


class Gate:
    """A media source that waits until the test lets it through."""

    def __init__(self, inner, fail: bool = False) -> None:  # noqa: ANN001
        self.inner, self.fail = inner, fail
        self.opened, self.entered = asyncio.Event(), asyncio.Event()

    async def fetch(self, media_id: str):  # noqa: ANN202
        self.entered.set()
        await self.opened.wait()
        if self.fail:
            raise MediaUnavailable("whatsapp_media_unavailable")
        return await self.inner.fetch(media_id)


async def background_world():  # noqa: ANN202
    world = _world()
    work = BackgroundWork()
    await world.link(world.alice, ALICE_PHONE)
    world.intake.background = work.start
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")
    return world, work


@pytest.mark.asyncio
async def test_the_webhook_answers_before_the_media_is_fetched() -> None:
    world, work = await background_world()
    gate = world.intake.media = Gate(world.intake.media)

    await asyncio.wait_for(
        world.deliver(image("700000000000201", "wamid.BG-ONE")), timeout=1
    )
    record = world.record("wamid.BG-ONE")
    assert (record.status, record.claim_until is not None) == ("received", True)
    assert world.captures(world.alice) == []

    gate.opened.set()
    await work.drain(timeout=5)
    assert world.record("wamid.BG-ONE").status == "captured"
    [connection_id] = world.captures(world.alice)
    # Reading is off in this world: the acknowledgement keeps the review link.
    assert world.transport.bodies()[-1] == (
        f"Recibido. Revísalo aquí: {ORIGIN}/biz?receipt={connection_id}"
    )


@pytest.mark.asyncio
async def test_a_failure_behind_the_acknowledgement_is_settled_and_told() -> None:
    world, work = await background_world()
    gate = world.intake.media = Gate(world.intake.media, fail=True)
    gate.opened.set()

    await world.deliver(image("700000000000201", "wamid.BG-FAIL"))
    await work.drain(timeout=5)

    record = world.record("wamid.BG-FAIL")
    assert (record.status, record.error_code, record.claim_until) == (
        "failed",
        "whatsapp_media_unavailable",
        None,
    )
    assert (
        world.transport.bodies()[-1] == "No pudimos guardarlo. Envíalo de nuevo."
    )


@pytest.mark.asyncio
async def test_a_redelivery_during_background_work_asks_meta_to_retry() -> None:
    world, work = await background_world()
    gate = world.intake.media = Gate(world.intake.media)
    await world.deliver(image("700000000000201", "wamid.BG-TWICE"))
    with pytest.raises(DeliveryInFlight):
        await world.deliver(image("700000000000201", "wamid.BG-TWICE"))

    gate.opened.set()
    await work.drain(timeout=5)
    await world.deliver(image("700000000000201", "wamid.BG-TWICE"))
    assert len(world.captures(world.alice)) == 1


@pytest.mark.asyncio
async def test_messages_in_one_delivery_finish_in_order() -> None:
    world, work = await background_world()
    world.graph.media["700000000000202"] = Media(RECEIPT_PNG + b"\x00", "image/png")
    first = image("700000000000201", "wamid.BG-A")
    second = image("700000000000202", "wamid.BG-B")
    first["entry"][0]["changes"][0]["value"]["messages"] += second["entry"][0]["changes"][
        0
    ]["value"]["messages"]

    await world.deliver(first)
    await work.drain(timeout=5)

    assert [world.record(m).status for m in ("wamid.BG-A", "wamid.BG-B")] == [
        "captured",
        "captured",
    ]
    assert len(world.captures(world.alice)) == 2
