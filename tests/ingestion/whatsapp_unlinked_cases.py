"""Unlinked sender and link-code reply behavior on both stores."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, time, timedelta, timezone

from tests.ingestion.whatsapp_cases import World, _revoke_while_capturing, image
from tests.ingestion.whatsapp_support import (
    ALICE_PHONE,
    BOB_PHONE,
    RECEIPT_PNG,
    STRANGER_PHONE,
    Media,
    fixture,
)


async def an_unlinked_number_gets_one_code_reply_per_day(world: World) -> None:
    await world.deliver(image("700000000000150", "wamid.CASE-DAY-1", STRANGER_PHONE))
    await world.deliver(
        fixture("text_message.json", id="wamid.CASE-DAY-2", sender=STRANGER_PHONE)
    )
    assert world.transport.bodies() == []
    assert world.graph.requests == []
    for message_id in ("wamid.CASE-DAY-3", "wamid.CASE-DAY-4"):
        await world.deliver(_stranger_code(message_id))
    assert world.transport.bodies() == [INVALID_CODE]
    world.clock.now += timedelta(days=1)
    await world.deliver(_stranger_code("wamid.CASE-DAY-5"))
    assert world.transport.bodies() == [INVALID_CODE, INVALID_CODE]


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


def _stranger_code(message_id: str) -> dict:
    return fixture(
        "text_link_code.json", id=message_id, sender=STRANGER_PHONE, text="ZZZZ2222"
    )


async def a_paused_code_message_resumed_later_does_not_reply_again(
    world: World,
) -> None:
    release, held = _hold_claims(world, 1, before_insert=True)
    first = asyncio.create_task(world.deliver(_stranger_code("wamid.CASE-PAUSED-A")))
    await _until(lambda: held)
    world.clock.now += timedelta(seconds=1)
    await world.deliver(_stranger_code("wamid.CASE-PAUSED-B"))
    release.set()
    await first
    assert world.transport.bodies() == [INVALID_CODE]


def _just_before_dominican_midnight(world: World) -> None:
    # 00:00 in Santo Domingo is 04:00 UTC all year.
    tomorrow = world.clock.now.date() + timedelta(days=1)
    world.clock.now = datetime.combine(tomorrow, time(3, 59, 59), timezone.utc)


async def two_code_claims_before_midnight_reply_once_after_it(
    world: World,
) -> None:
    _just_before_dominican_midnight(world)
    release, held = _hold_claims(world, 2)
    pending = [
        asyncio.create_task(world.deliver(_stranger_code(f"wamid.CASE-EVE-{n}")))
        for n in (1, 2)
    ]
    await _until(lambda: len(held) == 2)
    world.clock.now += timedelta(seconds=2)
    release.set()
    await asyncio.gather(*pending)
    assert world.transport.bodies() == [INVALID_CODE]


async def code_claims_straddling_midnight_reply_once_each_day(
    world: World,
) -> None:
    _just_before_dominican_midnight(world)
    release, held = _hold_claims(world, 1)
    before = asyncio.create_task(world.deliver(_stranger_code("wamid.CASE-OLD-DAY")))
    await _until(lambda: held)
    world.clock.now += timedelta(seconds=2)
    await world.deliver(_stranger_code("wamid.CASE-NEW-DAY"))
    release.set()
    await before
    world.clock.now += timedelta(seconds=1)
    await world.deliver(_stranger_code("wamid.CASE-NEW-DAY-AGAIN"))
    assert world.transport.bodies() == [INVALID_CODE, INVALID_CODE]


async def a_revoked_photo_does_not_use_the_days_code_reply(world: World) -> None:
    # Link with sending off so the initial success reply does not reserve a slot.
    world.intake.send_enabled = lambda: False

    async def revoke_after_capture(**kwargs):  # noqa: ANN003, ANN202
        captured = await capture(**kwargs)
        world.store.revoke(destination_owner_id=world.alice, now=world.clock.now)
        return captured

    await world.link(world.alice, ALICE_PHONE)
    world.intake.send_enabled = lambda: True
    destination = world.intake.destination
    capture = destination.capture
    destination.capture = revoke_after_capture
    world.graph.media["700000000000142"] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(image("700000000000142", "wamid.CASE-REVOKED-THEN-TEXT"))
    assert world.transport.bodies() == []
    world.clock.now += timedelta(seconds=1)
    await world.deliver(
        fixture("text_link_code.json", id="wamid.CASE-AFTER-REVOKE", text="ZZZZ2222")
    )
    assert world.transport.bodies() == [INVALID_CODE]


async def a_revoked_photo_with_a_new_number_linked_stays_silent(
    world: World,
) -> None:
    await _revoke_while_capturing(
        world, "es-419", "700000000000143", "wamid.CASE-RELINKED-THEN-TEXT", BOB_PHONE
    )
    world.clock.now += timedelta(seconds=1)
    await world.deliver(
        fixture("text_message.json", id="wamid.CASE-AFTER-RELINK", sender=ALICE_PHONE)
    )
    assert world.transport.bodies()[2:] == []


INVALID_CODE = "Ese código venció o ya se usó. Crea uno nuevo en Cuadrao."


async def a_valid_code_still_links_when_the_days_reply_is_used(world: World) -> None:
    await world.deliver(
        fixture("text_link_code.json", id="wamid.CASE-INVALID-FIRST", text="ZZZZ2222")
    )
    issue = world.issue(world.alice)
    await world.deliver(
        fixture("text_link_code.json", id="wamid.CASE-VALID-LATE", text=issue.code)
    )

    assert world.record("wamid.CASE-VALID-LATE").status == "linked"
    assert world.store.sender_link(sender_hash=world.keys.sender(ALICE_PHONE))
    assert world.transport.bodies() == [INVALID_CODE]


UNLINKED_CASES = (
    a_valid_code_still_links_when_the_days_reply_is_used,
    an_unlinked_number_gets_one_code_reply_per_day,
    a_paused_code_message_resumed_later_does_not_reply_again,
    two_code_claims_before_midnight_reply_once_after_it,
    code_claims_straddling_midnight_reply_once_each_day,
    a_revoked_photo_does_not_use_the_days_code_reply,
    a_revoked_photo_with_a_new_number_linked_stays_silent,
)
