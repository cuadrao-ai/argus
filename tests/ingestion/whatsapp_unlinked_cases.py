"""Unlinked-sender reply cases shared by the in-memory and Postgres runs: a
number with no link hears the linking hint at most once per Dominican day."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, time, timedelta, timezone

from tests.ingestion.whatsapp_cases import (
    UNLINKED,
    World,
    _revoke_while_capturing,
    image,
)
from tests.ingestion.whatsapp_support import ALICE_PHONE, STRANGER_PHONE, fixture


async def an_unlinked_number_hears_back_once_per_day(world: World) -> None:
    for message in (
        fixture("text_message.json", id="wamid.CASE-DAY-1", sender=STRANGER_PHONE),
        image("700000000000150", "wamid.CASE-DAY-2", STRANGER_PHONE),
        fixture("text_message.json", id="wamid.CASE-DAY-3", sender=STRANGER_PHONE),
    ):
        await world.deliver(message)
        world.clock.now += timedelta(seconds=1)
    assert world.transport.bodies() == [UNLINKED]
    assert world.graph.requests == []
    world.clock.now += timedelta(days=1)
    await world.deliver(
        fixture("text_message.json", id="wamid.CASE-DAY-4", sender=STRANGER_PHONE)
    )
    assert world.transport.bodies() == [UNLINKED, UNLINKED]


def _hold_claims(
    world: World, count: int, *, before_insert: bool = False
) -> tuple[threading.Event, list[str]]:
    """Stop the first ``count`` claims until released: after they commit, or
    after the arrival time is read but before the claim row is inserted."""

    release, held = threading.Event(), []
    claim = world.store.claim

    def held_claim(**kwargs):  # noqa: ANN003, ANN202
        hold = len(held) < count
        if hold:
            held.append(kwargs["provider_message_key"])
        if hold and before_insert:
            assert release.wait(10)
        result = claim(**kwargs)
        if hold and not before_insert:
            assert release.wait(10)
        return result

    world.store.claim = held_claim  # type: ignore[method-assign]
    return release, held


async def _until(predicate) -> None:  # noqa: ANN001
    for _ in range(500):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition never held")


def _stranger_text(message_id: str) -> dict:
    return fixture("text_message.json", id=message_id, sender=STRANGER_PHONE)


async def a_paused_unlinked_message_resumed_later_does_not_reply_again(
    world: World,
) -> None:
    release, held = _hold_claims(world, 1, before_insert=True)
    first = asyncio.create_task(world.deliver(_stranger_text("wamid.CASE-PAUSED-A")))
    await _until(lambda: held)
    world.clock.now += timedelta(seconds=1)
    await world.deliver(_stranger_text("wamid.CASE-PAUSED-B"))
    release.set()
    await first
    assert world.transport.bodies() == [UNLINKED]


def _just_before_dominican_midnight(world: World) -> None:
    # 00:00 in Santo Domingo is 04:00 UTC all year.
    tomorrow = world.clock.now.date() + timedelta(days=1)
    world.clock.now = datetime.combine(tomorrow, time(3, 59, 59), timezone.utc)


async def two_unlinked_claims_before_midnight_reply_once_after_it(
    world: World,
) -> None:
    _just_before_dominican_midnight(world)
    release, held = _hold_claims(world, 2)
    pending = [
        asyncio.create_task(world.deliver(_stranger_text(f"wamid.CASE-EVE-{n}")))
        for n in (1, 2)
    ]
    await _until(lambda: len(held) == 2)
    world.clock.now += timedelta(seconds=2)
    release.set()
    await asyncio.gather(*pending)
    assert world.transport.bodies() == [UNLINKED]


async def unlinked_claims_straddling_midnight_reply_once_each_day(
    world: World,
) -> None:
    _just_before_dominican_midnight(world)
    release, held = _hold_claims(world, 1)
    before = asyncio.create_task(world.deliver(_stranger_text("wamid.CASE-OLD-DAY")))
    await _until(lambda: held)
    world.clock.now += timedelta(seconds=2)
    await world.deliver(_stranger_text("wamid.CASE-NEW-DAY"))
    release.set()
    await before
    world.clock.now += timedelta(seconds=1)
    await world.deliver(_stranger_text("wamid.CASE-NEW-DAY-AGAIN"))
    assert world.transport.bodies() == [UNLINKED, UNLINKED]


async def a_revoked_photo_counts_as_the_days_unlinked_reply(world: World) -> None:
    await _revoke_while_capturing(
        world, "es-419", "700000000000142", "wamid.CASE-REVOKED-THEN-TEXT"
    )
    world.clock.now += timedelta(seconds=1)
    await world.deliver(
        fixture("text_message.json", id="wamid.CASE-AFTER-REVOKE", sender=ALICE_PHONE)
    )
    assert world.transport.bodies()[1:] == [UNLINKED]


UNLINKED_CASES = (
    an_unlinked_number_hears_back_once_per_day,
    a_paused_unlinked_message_resumed_later_does_not_reply_again,
    two_unlinked_claims_before_midnight_reply_once_after_it,
    unlinked_claims_straddling_midnight_reply_once_each_day,
    a_revoked_photo_counts_as_the_days_unlinked_reply,
)
