"""A capture that outlives its cancellation, shared by the in-memory and
Postgres runs. The real capture thread is held past the lease: the heartbeat
keeps the claim, and a worker that lost it anyway sends nothing."""

from __future__ import annotations

import asyncio
import copy
import threading
from datetime import timedelta

from argus.api.whatsapp import DocumentsDestination
from argus.domain.ingestion.whatsapp.intake import (
    CLAIM_SECONDS,
    PROCESSING_SECONDS,
    WhatsAppIntake,
)

from tests.ingestion.whatsapp_cases import World, image
from tests.ingestion.whatsapp_support import ALICE_PHONE, RECEIPT_PNG, Media


class HeldCapture:
    """The first capture blocks its thread until released; later ones run."""

    def __init__(self, world: World) -> None:
        self.store = world.documents.store
        self.inner = self.store.capture
        self.entered, self.release = threading.Event(), threading.Event()
        self.calls = 0
        self.store.capture = self

    def __call__(self, **kwargs):  # noqa: ANN003, ANN204
        self.calls += 1
        if self.calls == 1:
            self.entered.set()
            self.release.wait(timeout=10)
        return self.inner(**kwargs)

    def restore(self) -> None:
        self.release.set()
        self.store.capture = self.inner


def _second_worker(world: World) -> WhatsAppIntake:
    """Another process: same database, its own documents capture slot."""

    documents = copy.copy(world.documents)
    documents._capture_slot = asyncio.Semaphore(1)
    second = copy.copy(world.intake)
    second.destination = DocumentsDestination(documents, world.spaces)
    second.background = None
    second.processing_seconds = PROCESSING_SECONDS
    return second


async def _start(world: World, media_id: str, message_id: str) -> asyncio.Task:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    started: list = []
    world.intake.background = started.append
    world.intake._last_nudge = world.clock()
    world.intake.processing_seconds = 0.05
    await world.deliver(image(media_id, message_id))
    [work] = started
    return asyncio.create_task(work)


async def _entered(held: HeldCapture) -> None:
    while not held.entered.is_set():
        await asyncio.sleep(0.005)


def _fetches(world: World, media_id: str) -> int:
    return sum(
        1
        for request in world.graph.requests
        if request.url.host == "graph.facebook.com"
        and request.url.path.endswith(media_id)
    )


async def a_heartbeat_holds_the_claim_through_a_cancelled_capture(world: World) -> None:
    world.intake.renew_seconds = 0.01
    held = HeldCapture(world)
    try:
        original = await _start(world, "700000000000501", "wamid.BEAT-HOLD")
        await _entered(held)
        await asyncio.sleep(0.1)  # timed out; now waiting on the capture thread
        world.clock.now += timedelta(seconds=CLAIM_SECONDS + 1)
        await asyncio.sleep(0.05)  # the heartbeat renews against the new time

        assert await _second_worker(world).recover() == 0
    finally:
        held.restore()
    await original

    assert held.calls == 1
    assert _fetches(world, "700000000000501") == 1
    assert len(world.captures(world.alice)) == 1


async def a_worker_that_lost_its_claim_sends_nothing(world: World) -> None:
    world.intake.renew_seconds = 3600  # a heartbeat that cannot keep up
    held = HeldCapture(world)
    try:
        original = await _start(world, "700000000000502", "wamid.BEAT-LOST")
        await _entered(held)
        await asyncio.sleep(0.1)
        world.clock.now += timedelta(seconds=CLAIM_SECONDS + 1)

        assert await _second_worker(world).recover() == 1
        assert world.record("wamid.BEAT-LOST").status == "captured"
        replies = world.transport.bodies()
        assert replies
    finally:
        held.restore()
    await original

    assert world.transport.bodies() == replies
    assert world.record("wamid.BEAT-LOST").status == "captured"
    assert len(world.captures(world.alice)) == 1


HEARTBEAT_CASES = (
    a_heartbeat_holds_the_claim_through_a_cancelled_capture,
    a_worker_that_lost_its_claim_sends_nothing,
)
