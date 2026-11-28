"""A delayed or restarted worker still separates forwards and charges only notices."""

from datetime import timedelta

import pytest

from tests.test_whatsapp_intake_postgres import (
    _counts,
    _failed,
    _linked,
    _worker,
    pool,
    pytestmark,
    users,
)

__all__ = ["pool", "pytestmark", "users"]


@pytest.mark.asyncio
async def test_separate_forwards_survive_a_late_due_pass(pool, users):
    world = await _linked(pool, users)
    await _failed(world, 0)
    world.clock.now += timedelta(minutes=4)
    await _failed(world, 1)
    worker = _worker(world)
    assert await worker.run_once()
    assert len(world.transport.sent) == 1
    assert not await worker.run_once()
    world.clock.now += timedelta(minutes=1)
    assert await worker.run_once()
    assert [reply["context"]["message_id"] for reply in world.transport.sent] == [
        "wamid.GROUP-0",
        "wamid.GROUP-1",
    ]
    assert _counts(pool, world) == [(2, 0)]


@pytest.mark.asyncio
@pytest.mark.parametrize("recover_before_reply", [False, True])
async def test_recovered_download_is_counted_once(pool, users, recover_before_reply):
    from tests.ingestion.whatsapp_cases import image
    from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media

    world = await _linked(pool, users)
    media_id = "700000000000052"
    delivery = image(media_id, "wamid.RECOVER")
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png", meta_status=404)
    await world.deliver(delivery)
    groups = world.store.reply_groups
    if not recover_before_reply:
        world.clock.now += timedelta(minutes=1)
        attempt = groups.claim(now=world.clock.now, limit=10)
        assert attempt.outcomes.not_received == 1
        groups.finish(attempt, now=world.clock.now, outcome="sent")
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(delivery)
    world.clock.now += timedelta(minutes=1)
    attempt = groups.claim(now=world.clock.now, limit=10)
    if recover_before_reply:
        assert attempt.group.count == 1
        assert attempt.outcomes.not_received == 0
        assert attempt.outcomes.failure_keys == ()
        groups.finish(attempt, now=world.clock.now, outcome="sent")
    else:
        assert attempt is None


@pytest.mark.asyncio
async def test_business_closes_between_claim_and_send(pool, users):
    from tests.ingestion.whatsapp_cases import image
    from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media

    world = await _linked(pool, users)
    space = world.business(world.alice).space_id
    media_id = "700000000000055"
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(image(media_id, "wamid.CLOSE"))
    groups = world.store.reply_groups
    world.clock.now += timedelta(minutes=1)
    attempt = groups.claim(now=world.clock.now, limit=10)
    assert len(attempt.outcomes.businesses) == 1
    with pool.connection() as db:
        db.execute("update public.spaces set closed_at=now() where id=%s", (space,))
    assert not groups.authorized(attempt, now=world.clock.now)
    # A different worker claims the refreshed group after a restart.
    restarted = type(groups)(pool)
    fresh = restarted.claim(now=world.clock.now, limit=10)
    assert restarted.authorized(fresh, now=world.clock.now)
    assert fresh.outcomes.held == 1
    assert fresh.outcomes.businesses == ()
    restarted.finish(fresh, now=world.clock.now, outcome="sent")
    assert restarted.claim(now=world.clock.now, limit=10) is None
    assert not _counts(pool, world)


@pytest.mark.asyncio
async def test_slow_read_schedules_its_non_aligned_deadline(pool, users):
    from tests.ingestion.whatsapp_cases import image
    from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media

    world = await _linked(pool, users)
    media_id = "700000000000056"
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(image(media_id, "wamid.SLOW-PHASE"))
    [cid] = world.captures(world.alice)
    with pool.connection() as db:
        db.execute(
            """update public.financial_document_extractions set
               draft=jsonb_set(draft,'{status}','"preparing"') where connection_id=%s""",
            (cid,),
        )
    groups = world.store.reply_groups
    world.clock.now += timedelta(seconds=95)
    assert groups.claim(now=world.clock.now, limit=10) is True
    world.clock.now += timedelta(seconds=60)
    assert groups.claim(now=world.clock.now, limit=10) is True
    cutoff = world.clock.now + timedelta(seconds=25)
    assert groups.claim(now=world.clock.now, limit=10) == cutoff
    world.clock.now = cutoff
    attempt = groups.claim(now=world.clock.now, limit=10)
    assert attempt.outcomes.reading == 1
    groups.finish(attempt, now=world.clock.now, outcome="sent")
    world.clock.now += timedelta(seconds=60)
    assert groups.claim(now=world.clock.now, limit=10) is None


@pytest.mark.asyncio
async def test_terminal_forward_stays_separate_after_its_quiet_minute(pool, users):
    from tests.ingestion.whatsapp_cases import image
    from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media

    world = await _linked(pool, users)
    media_id = "700000000000062"
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(image(media_id, "wamid.BETWEEN-PASSES"))
    [cid] = world.captures(world.alice)
    with pool.connection() as db:
        db.execute(
            """update public.financial_document_extractions set
               draft=jsonb_set(draft,'{status}','"preparing"') where connection_id=%s""", (cid,),
        )
    world.clock.now += timedelta(seconds=60)
    groups = world.store.reply_groups
    assert groups.claim(now=world.clock.now, limit=10) is True
    with pool.connection() as db:
        db.execute(
            """update public.financial_document_extractions set
               draft=jsonb_set(draft,'{status}','"prepared"') where connection_id=%s""", (cid,),
        )
    world.clock.now += timedelta(seconds=10)
    await _failed(world, 1)
    world.clock.now += timedelta(seconds=60)
    worker = _worker(world)
    assert await worker.run_once() and await worker.run_once()
    assert len(world.transport.bodies()) == 2


@pytest.mark.asyncio
async def test_download_in_progress_keeps_its_original_forward(pool, users, monkeypatch):
    import asyncio

    from tests.ingestion.whatsapp_cases import image
    from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media

    world = await _linked(pool, users)
    await _failed(world, 0)
    started, release = asyncio.Event(), asyncio.Event()
    fetch = world.intake.media.fetch

    async def delayed(media_id):
        started.set()
        await release.wait()
        return await fetch(media_id)

    monkeypatch.setattr(world.intake.media, "fetch", delayed)
    media_id = "700000000000057"
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    world.clock.now += timedelta(seconds=55)
    delivery = asyncio.create_task(world.deliver(image(media_id, "wamid.DOWNLOADING")))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        groups = world.store.reply_groups
        world.clock.now += timedelta(seconds=10)
        assert groups.claim(now=world.clock.now, limit=10) == world.clock.now + timedelta(seconds=50)
    finally:
        release.set()
        await delivery
    world.clock.now += timedelta(seconds=60)
    attempt = groups.claim(now=world.clock.now, limit=10)
    assert attempt.group.count == 2
    assert attempt.outcomes.not_received == 1
    assert sum(count for _, count in attempt.outcomes.businesses) == 1
    groups.finish(attempt, now=world.clock.now, outcome="sent")
    assert groups.claim(now=world.clock.now, limit=10) is None
