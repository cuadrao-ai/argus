"""Lease and sealing cases shared by the in-memory and Postgres runs: every
item renews its own lease right before its fetch, and a photo is never
acknowledged without a sealed envelope."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

import pytest
from argus.domain.ingestion.whatsapp.intake import CLAIM_SECONDS, ClaimNotSealed

from tests.ingestion.whatsapp_cases import World, image
from tests.ingestion.whatsapp_support import ALICE_PHONE, RECEIPT_PNG, Media


class SlowMedia:
    """Each fetch takes a minute. On the last one a second worker sweeps."""

    def __init__(self, world: World, sweep_on: int) -> None:
        self.world, self.inner, self.sweep_on = world, world.intake.media, sweep_on
        self.fetches: Counter[str] = Counter()

    async def fetch(self, media_id: str):  # noqa: ANN201
        self.fetches[media_id] += 1
        self.world.clock.now += timedelta(seconds=60)
        if sum(self.fetches.values()) == self.sweep_on:
            await self.world.intake.recover()
        return await self.inner.fetch(media_id)


def _photos(world: World, tag: str, count: int) -> tuple[list[str], dict]:
    ids = [f"7000000000003{tag}{n}" for n in range(count)]
    body = image(ids[0], f"wamid.LEASE-{tag}-0")
    messages = body["entry"][0]["changes"][0]["value"]["messages"]
    for n, media_id in enumerate(ids[1:], start=1):
        messages += image(media_id, f"wamid.LEASE-{tag}-{n}")["entry"][0]["changes"][0][
            "value"
        ]["messages"]
    for media_id in ids:
        world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    return ids, body


async def a_sweep_renews_each_lease_so_no_photo_is_fetched_twice(world: World) -> None:
    await world.link(world.alice, ALICE_PHONE)
    ids, body = _photos(world, "1", 3)
    world.intake.background = lambda work: work.close()
    try:
        await world.deliver(body)
    finally:
        world.intake.background = None
    world.clock.now += timedelta(seconds=CLAIM_SECONDS + 1)
    media = world.intake.media = SlowMedia(world, sweep_on=3)

    await world.intake.recover()

    assert media.fetches == Counter({media_id: 1 for media_id in ids})
    assert {world.record(f"wamid.LEASE-1-{k}").status for k in range(3)} == {"captured"}


async def a_queued_batch_renews_each_lease_before_its_fetch(world: World) -> None:
    await world.link(world.alice, ALICE_PHONE)
    ids, body = _photos(world, "2", 2)
    started: list = []
    world.intake.background = started.append
    world.intake._last_nudge = world.clock()
    try:
        await world.deliver(body)
    finally:
        world.intake.background = None
    media = world.intake.media = SlowMedia(world, sweep_on=2)

    for work in started:
        await work

    assert media.fetches == Counter({media_id: 1 for media_id in ids})
    assert {world.record(f"wamid.LEASE-2-{k}").status for k in range(2)} == {"captured"}


class Breaks:
    def seal(self, message):  # noqa: ANN001, ANN201
        raise RuntimeError("sealing failed")


async def _unsealed(world: World, codec: object) -> None:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000390"] = Media(RECEIPT_PNG, "image/png")
    sealing = world.intake.claim_codec
    world.intake.claim_codec = codec
    with pytest.raises(ClaimNotSealed):
        await world.deliver(image("700000000000390", "wamid.LEASE-UNSEALED"))
    assert world.record("wamid.LEASE-UNSEALED") is None
    assert world.captures(world.alice) == []

    world.intake.claim_codec = sealing
    await world.deliver(image("700000000000390", "wamid.LEASE-UNSEALED"))
    world.intake.claim_codec = codec
    await world.deliver(image("700000000000390", "wamid.LEASE-UNSEALED"))
    assert world.record("wamid.LEASE-UNSEALED").status == "captured"
    assert len(world.captures(world.alice)) == 1


async def a_photo_without_a_codec_is_not_acknowledged(world: World) -> None:
    await _unsealed(world, None)


async def a_photo_whose_sealing_fails_is_not_acknowledged(world: World) -> None:
    await _unsealed(world, Breaks())


LEASE_CASES = (
    a_sweep_renews_each_lease_so_no_photo_is_fetched_twice,
    a_queued_batch_renews_each_lease_before_its_fetch,
    a_photo_without_a_codec_is_not_acknowledged,
    a_photo_whose_sealing_fails_is_not_acknowledged,
)
