"""A capture that outlives its cancellation, shared by the in-memory and
Postgres runs. The real capture thread is held past the lease: the heartbeat
keeps the claim, and a worker that lost it anyway sends nothing."""

from __future__ import annotations

import asyncio
import copy
import threading
from dataclasses import replace
from datetime import timedelta

import pytest
from argus.api.whatsapp import DocumentsDestination
from argus.domain.ingestion.whatsapp.intake import (
    CLAIM_SECONDS,
    PROCESSING_SECONDS,
    DeliveryInFlight,
    _Held,
    _Lease,
    _stop,
)
from argus.domain.ingestion.whatsapp.payload import parse_delivery
from argus.domain.ingestion.whatsapp.store import Settlement

from tests.ingestion.whatsapp_cases import World, image
from tests.ingestion.whatsapp_support import (
    ALICE_PHONE,
    PHONE_NUMBER_ID,
    RECEIPT_PNG,
    Media,
    encode,
)


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


def _second_worker(world: World) -> World:
    """Another process: same database, its own documents capture slot."""

    documents = copy.copy(world.documents)
    documents._capture_slot = asyncio.Semaphore(1)
    second = copy.copy(world.intake)
    second.destination = DocumentsDestination(documents, world.store)
    second.processing_seconds = PROCESSING_SECONDS
    return replace(world, intake=second)


async def _start(world: World, media_id: str, message_id: str) -> asyncio.Task:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    world.intake.processing_seconds = 0.05
    return asyncio.create_task(world.deliver(image(media_id, message_id)))


async def _entered(held: HeldCapture) -> None:
    assert await asyncio.to_thread(held.entered.wait, 5)


async def _renewed(world: World, message_id: str) -> None:
    """Wait, bounded, for the heartbeat to renew against the advanced clock."""

    for _ in range(400):
        if world.record(message_id).claim_until > world.clock.now:
            return
        await asyncio.sleep(0.005)
    raise AssertionError("claim was not renewed")


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
        await _renewed(world, "wamid.BEAT-HOLD")

        with pytest.raises(DeliveryInFlight):
            await _second_worker(world).deliver(
                image("700000000000501", "wamid.BEAT-HOLD")
            )
    finally:
        held.restore()
    with pytest.raises(asyncio.TimeoutError):
        await original

    row = world.record("wamid.BEAT-HOLD")
    assert (row.status, row.error_code, row.claim_until) == (
        "failed",
        "whatsapp_processing_timeout",
        None,
    )
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

        await _second_worker(world).deliver(image("700000000000502", "wamid.BEAT-LOST"))
        assert world.record("wamid.BEAT-LOST").status == "captured"
        replies = world.transport.bodies()
        assert replies
    finally:
        held.restore()
    with pytest.raises(DeliveryInFlight):
        await original

    assert world.transport.bodies() == replies
    assert world.record("wamid.BEAT-LOST").status == "captured"
    assert len(world.captures(world.alice)) == 1


FAILURE_TEXT = "Envíalo de nuevo"


def _failures(world: World) -> list[str]:
    return [body for body in world.transport.bodies() if FAILURE_TEXT in body]


async def a_cancelled_worker_keeps_its_claim_until_the_capture_ends(world: World) -> None:
    world.intake.renew_seconds = 0.01
    held = HeldCapture(world)
    second = _second_worker(world)
    body = image("700000000000503", "wamid.BEAT-CANCEL")
    try:
        original = await _start(world, "700000000000503", "wamid.BEAT-CANCEL")
        await _entered(held)
        await asyncio.sleep(0.1)  # timed out; now waiting on the capture thread
        original.cancel()
        await asyncio.sleep(0.02)
        for _ in range(3):
            world.clock.now += timedelta(seconds=CLAIM_SECONDS + 1)
            await _renewed(world, "wamid.BEAT-CANCEL")
            with pytest.raises(DeliveryInFlight):
                await second.deliver(body)
            assert world.record("wamid.BEAT-CANCEL").status == "received"
        assert held.calls == 1
        assert _fetches(world, "700000000000503") == 1
    finally:
        held.restore()
    with pytest.raises(asyncio.CancelledError):
        await original

    assert len(world.captures(world.alice)) == 1
    assert world.record("wamid.BEAT-CANCEL").status == "received"
    assert _failures(world) == []
    # The cancelled worker never settled; redelivery can finish once the claim lapses.
    world.clock.now += timedelta(seconds=CLAIM_SECONDS + 1)
    await second.deliver(body)
    assert world.record("wamid.BEAT-CANCEL").status == "captured"
    assert len(world.captures(world.alice)) == 1
    assert _failures(world) == []


class HeldRenewal:
    """A renewal that commits, then blocks before returning its token."""

    def __init__(self, world: World) -> None:
        self.store = world.intake.store
        self.inner = self.store.renew
        self.entered, self.release = threading.Event(), threading.Event()
        self.store.renew = self

    def __call__(self, **kwargs):  # noqa: ANN003, ANN204
        token = self.inner(**kwargs)
        self.entered.set()
        self.release.wait(timeout=10)
        return token

    def restore(self) -> None:
        self.release.set()
        self.store.renew = self.inner


async def _claim_photo(world: World, media_id: str, message_id: str) -> _Held:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    delivery = parse_delivery(
        encode(image(media_id, message_id), world.clock()),
        phone_number_id=PHONE_NUMBER_ID,
    )
    [message] = delivery.messages
    item = await world.intake._claim(message)
    assert isinstance(item, _Held)
    return item


async def a_cancelled_shutdown_keeps_the_renewed_token(world: World) -> None:
    item = await _claim_photo(world, "700000000000504", "wamid.BEAT-STOP")
    key = item.key
    lease = _Lease(item.held)
    world.intake.renew_seconds = 0.01
    world.clock.now += timedelta(seconds=10)  # each renewal moves the token
    renewal = HeldRenewal(world)
    try:
        beat = asyncio.create_task(world.intake._heartbeat(key, lease))
        assert await asyncio.to_thread(renewal.entered.wait, 5)
        stopping = asyncio.create_task(_stop(lease, beat))
        for _ in range(4):
            await asyncio.sleep(0.01)
            stopping.cancel()
    finally:
        renewal.restore()
    with pytest.raises(asyncio.CancelledError):
        await stopping

    assert beat.done()
    assert lease.held != world.record("wamid.BEAT-STOP").claim_until - timedelta(
        seconds=10
    )
    assert lease.held == world.record("wamid.BEAT-STOP").claim_until
    settled = await world.intake._settle(
        key, lease.held, Settlement("failed", error_code="whatsapp_processing_failed")
    )
    assert settled is not None


async def a_renewal_error_after_redelivery_sends_nothing(world: World) -> None:
    item = await _claim_photo(world, "700000000000505", "wamid.BEAT-ERROR")
    world.clock.now += timedelta(seconds=CLAIM_SECONDS + 1)
    await _second_worker(world).deliver(image("700000000000505", "wamid.BEAT-ERROR"))
    assert world.record("wamid.BEAT-ERROR").status == "captured"
    replies = world.transport.bodies()
    store = world.intake.store
    inner = store.renew

    def broken(**kwargs):  # noqa: ANN003, ANN202
        raise ConnectionError("pool exhausted")

    store.renew = broken
    try:
        assert not await world.intake._process(item)
    finally:
        store.renew = inner

    assert world.transport.bodies() == replies
    assert _failures(world) == []
    assert world.record("wamid.BEAT-ERROR").status == "captured"
    assert len(world.captures(world.alice)) == 1


HEARTBEAT_CASES = (
    a_heartbeat_holds_the_claim_through_a_cancelled_capture,
    a_worker_that_lost_its_claim_sends_nothing,
    a_cancelled_worker_keeps_its_claim_until_the_capture_ends,
    a_cancelled_shutdown_keeps_the_renewed_token,
    a_renewal_error_after_redelivery_sends_nothing,
)
