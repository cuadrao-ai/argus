"""Daily receiving allowances defer mail without losing its durable delivery."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest
from argus.domain.ingestion.documents.config import SOURCE_MAX_BYTES
from argus.domain.ingestion.email_intake.budget import DailyEmailBudget
from argus.domain.ingestion.email_intake.provider import ResendReceivingClient
from argus.domain.ingestion.email_intake.store import LeaseLost

from tests.ingestion.test_email_intake_service import rig


def test_daily_message_cap_keeps_mail_pending_and_exact_replays_are_free():
    world = rig()
    first = world.enqueue()
    for _ in range(100):
        assert world.enqueue(external_id=first.external_id).id == first.id
    for _ in range(99):
        world.enqueue()
    waiting = world.enqueue()
    assert waiting.state == "received"
    assert waiting.error_code == "email_daily_message_budget"
    assert world.provider.calls == 0
    assert world.store.get(waiting.id, world.route.space_id) == waiting
    assert world.store.claim(delivery_id=waiting.id) is None


def usage(world):
    from argus.domain.ingestion.email_intake.budget import business_day

    day = business_day(world.clock())
    return world.store._usage.get((world.route.id, day), [0, 0])


def test_concurrent_last_message_allowance_has_one_winner():
    world = rig()
    world.store.budget = DailyEmailBudget(1, 100 * SOURCE_MAX_BYTES)
    barrier = Barrier(2)

    def enqueue(_):
        barrier.wait()
        return world.enqueue()

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(enqueue, range(2)))
    assert sorted(item.error_code or "admitted" for item in results) == [
        "admitted",
        "email_daily_message_budget",
    ]
    assert usage(world) == [1, 0]


@pytest.mark.asyncio
async def test_byte_wait_never_fetches_and_does_not_spend_worker_attempts():
    world = rig()
    world.store.budget = DailyEmailBudget(100, SOURCE_MAX_BYTES)
    first, second = world.enqueue(), world.enqueue()
    held = world.store.claim(delivery_id=first.id)
    reservation = world.store.reserve_fetch(held)
    await world.runtime.process(world.store.claim(delivery_id=second.id))
    waiting = world.store.get(second.id, world.route.space_id)
    assert (waiting.state, waiting.error_code, waiting.attempts) == (
        "received",
        "email_daily_byte_budget",
        0,
    )
    assert world.provider.calls == 0
    assert world.store.claim(delivery_id=second.id) is None
    assert not await world.runtime.next()
    world.clock.advance(24 * 60 * 60)
    resumed = world.store.claim(delivery_id=second.id)
    assert resumed is not None
    await world.runtime.process(resumed)
    assert world.store.get(second.id, world.route.space_id).state == "captured"
    assert usage(world)[1] == len(world.provider.raw)
    with pytest.raises(LeaseLost):
        world.store.settle_fetch(held, reservation, 0)


def test_exact_settlement_refunds_once_and_retry_counts_again():
    world = rig()
    world.store.budget = DailyEmailBudget(2, 2 * SOURCE_MAX_BYTES)
    delivery = world.enqueue()
    first = world.store.claim(delivery_id=delivery.id)
    reservation = world.store.reserve_fetch(first)
    world.store.settle_fetch(first, reservation, 31)
    assert usage(world) == [1, 31]
    with pytest.raises(LeaseLost):
        world.store.settle_fetch(first, reservation, 0)
    world.store.finish(first, "partial", "provider_unavailable")
    world.clock.advance(10)
    retry = world.store.claim(delivery_id=delivery.id)
    new = world.store.reserve_fetch(retry)
    world.store.settle_fetch(retry, new, 19)
    assert usage(world) == [2, 50]


def test_crashed_fetch_stays_charged_and_cannot_refund_reclaimed_attempt():
    world = rig()
    delivery = world.enqueue()
    first = world.store.claim(delivery_id=delivery.id)
    old = world.store.reserve_fetch(first)
    world.clock.advance(121)
    recovered = world.store.claim(delivery_id=delivery.id)
    new = world.store.reserve_fetch(recovered)
    with pytest.raises(LeaseLost):
        world.store.settle_fetch(first, old, 0)
    world.store.settle_fetch(recovered, new, 11)
    assert usage(world) == [2, SOURCE_MAX_BYTES + 11]


def test_new_business_day_is_independent_and_existing_reservation_settles_its_own_day():
    world = rig()
    # 03:59:59 UTC is 23:59:59 in Santo Domingo. Two seconds later is the next day.
    world.clock.now = world.clock.now.replace(hour=3, minute=59, second=59)
    delivery = world.enqueue()
    held = world.store.claim(delivery_id=delivery.id)
    first = world.store.reserve_fetch(held)
    world.clock.advance(2)
    world.store.settle_fetch(held, first, 20)
    second = world.store.reserve_fetch(held)
    world.store.settle_fetch(held, second, 10)
    assert world.store._usage[(world.route.id, first.day)] == [1, 20]
    assert usage(world) == [1, 10]


@pytest.mark.asyncio
async def test_metadata_and_raw_reserve_separately_and_settle_actual_bytes():
    world = rig()
    delivery = world.enqueue()
    requests = []
    metadata_bytes = (
        b'{"id":"'
        + delivery.external_id.encode()
        + b'","to":["'
        + world.route.recipient.encode()
        + b'"],"raw":{"download_url":"https://cdn.resend.app/raw"}}'
    )

    def handler(request):
        requests.append(request)
        assert usage(world)[1] >= SOURCE_MAX_BYTES
        return httpx.Response(
            200,
            content=metadata_bytes
            if request.url.host == "api.resend.com"
            else world.provider.raw,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        world.runtime.provider = ResendReceivingClient(
            client, "synthetic", ("cdn.resend.app",)
        )
        assert await world.runtime.next()
    assert len(requests) == 2
    assert usage(world) == [1, len(metadata_bytes) + len(world.provider.raw)]
    assert world.store.get(delivery.id, world.route.space_id).state == "captured"


@pytest.mark.asyncio
async def test_oversized_download_stops_at_the_cap_and_keeps_that_charge():
    world = rig()
    delivery = world.enqueue()
    pulled = []
    metadata = {
        "id": delivery.external_id,
        "to": [world.route.recipient],
        "raw": {"download_url": "https://cdn.resend.app/raw"},
    }
    metadata_bytes = len(httpx.Response(200, json=metadata).content)

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            pulled.append(1)
            yield b"x" * (SOURCE_MAX_BYTES - 1)
            pulled.append(2)
            yield b"yy"
            pulled.append(3)
            yield b"z" * 64

    def handler(request):
        if request.url.host == "api.resend.com":
            return httpx.Response(200, json=metadata)
        return httpx.Response(200, stream=Chunks(), headers={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        world.runtime.provider = ResendReceivingClient(
            client, "synthetic", ("cdn.resend.app",)
        )
        assert await world.runtime.next()
    saved = world.store.get(delivery.id, world.route.space_id)
    assert (saved.state, saved.error_code) == ("rejected", "provider_response_too_large")
    assert pulled == [1, 2]
    assert usage(world) == [1, metadata_bytes + SOURCE_MAX_BYTES]
    assert world.drafts() == []


@pytest.mark.asyncio
async def test_metadata_consumes_bytes_and_raw_waits_before_request():
    world = rig()
    world.store.budget = DailyEmailBudget(100, SOURCE_MAX_BYTES)
    delivery = world.enqueue()
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": delivery.external_id,
                "to": [world.route.recipient],
                "raw": {"download_url": "https://cdn.resend.app/raw"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        world.runtime.provider = ResendReceivingClient(
            client, "synthetic", ("cdn.resend.app",)
        )
        assert await world.runtime.next()
    waiting = world.store.get(delivery.id, world.route.space_id)
    assert len(requests) == 1
    assert (waiting.state, waiting.attempts, waiting.error_code) == (
        "received",
        0,
        "email_daily_byte_budget",
    )
    assert usage(world)[1] == len(
        httpx.Response(
            200,
            json={
                "id": delivery.external_id,
                "to": [world.route.recipient],
                "raw": {"download_url": "https://cdn.resend.app/raw"},
            },
        ).content
    )


@pytest.mark.asyncio
async def test_cancelled_fetch_retains_reservation():
    world = rig()
    delivery = world.enqueue()
    started = asyncio.Event()

    async def handler(request):
        started.set()
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        world.runtime.provider = ResendReceivingClient(
            client, "synthetic", ("cdn.resend.app",)
        )
        task = asyncio.create_task(world.runtime.next())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert usage(world) == [1, SOURCE_MAX_BYTES]
    assert world.store.get(delivery.id, world.route.space_id).state == "processing"


def test_each_address_has_an_independent_daily_allowance():
    from uuid import uuid4

    world = rig()
    world.store.budget = DailyEmailBudget(1, SOURCE_MAX_BYTES)
    second = world.store.create_route(
        recipient="another@recibos.example.test",
        space_id=str(uuid4()),
        principal_id=str(uuid4()),
        granted_by=str(uuid4()),
        grant_id=str(uuid4()),
    )
    assert world.enqueue().error_code is None
    assert world.enqueue().error_code == "email_daily_message_budget"
    assert world.enqueue(second.recipient).error_code is None
    from argus.domain.ingestion.email_intake.budget import business_day

    assert world.store._usage[(second.id, business_day(world.clock()))] == [1, 0]


def test_manual_retry_of_quota_wait_cannot_bypass_next_day_or_spend_attempts():
    world = rig()
    world.store.budget = DailyEmailBudget(1, SOURCE_MAX_BYTES)
    world.enqueue()
    waiting = world.enqueue()
    assert not world.runtime.retryable(waiting)
    assert not world.store.retry(waiting.id, world.route.space_id)
    assert world.store.claim(delivery_id=waiting.id) is None
    assert world.store.get(waiting.id, world.route.space_id).attempts == 0


@pytest.mark.asyncio
async def test_metadata_before_midnight_and_raw_after_midnight_charge_separate_days():
    from argus.domain.ingestion.email_intake.budget import business_day

    world = rig()
    world.clock.now = world.clock.now.replace(hour=3, minute=59, second=59)
    delivery = world.enqueue()
    first_day = business_day(world.clock())
    settle = world.store.settle_fetch

    def advance_after_metadata(*args):
        settle(*args)
        if business_day(world.clock()) == first_day:
            world.clock.advance(2)

    world.store.settle_fetch = advance_after_metadata
    response = httpx.Response(
        200,
        json={
            "id": delivery.external_id,
            "to": [world.route.recipient],
            "raw": {"download_url": "https://cdn.resend.app/raw"},
        },
    )

    def handler(request):
        return (
            response
            if request.url.host == "api.resend.com"
            else httpx.Response(200, content=world.provider.raw)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        world.runtime.provider = ResendReceivingClient(
            client, "synthetic", ("cdn.resend.app",)
        )
        assert await world.runtime.next()
    assert world.store._usage[(world.route.id, first_day)] == [1, len(response.content)]
    assert usage(world) == [1, len(world.provider.raw)]
    assert world.store.get(delivery.id, world.route.space_id).state == "captured"


def test_quota_log_exposes_counts_without_addresses_or_message_content():
    from loguru import logger

    world = rig()
    world.store.budget = DailyEmailBudget(1, SOURCE_MAX_BYTES)
    messages = []
    sink = logger.add(messages.append, format="{message}")
    try:
        world.enqueue()
        world.enqueue()
    finally:
        logger.remove(sink)
    log = "".join(messages)
    assert world.route.id in log
    assert "email_daily_message_budget" in log
    assert "messages=1 bytes=0" in log
    assert world.route.recipient not in log
    assert world.provider.raw.decode(errors="ignore") not in log


@pytest.mark.asyncio
async def test_cancelled_reservation_thread_cannot_grant_free_fetch(monkeypatch):
    from threading import Event

    world = rig()
    world.enqueue()
    started, release, finished = Event(), Event(), Event()
    original = world.store.reserve_fetch

    def blocked(delivery):
        started.set()
        release.wait(timeout=5)
        try:
            return original(delivery)
        finally:
            finished.set()

    monkeypatch.setattr(world.store, "reserve_fetch", blocked)
    task = asyncio.create_task(world.runtime.next())
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
    assert await asyncio.to_thread(finished.wait, 5)
    assert usage(world) == [1, SOURCE_MAX_BYTES]
    assert world.provider.calls == 0
