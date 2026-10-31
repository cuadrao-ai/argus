"""Loss recovery cases shared by the in-memory and Postgres runs: a claim that
lapsed because the process died after the 200 is run again from its sealed
envelope."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from argus.domain.ingestion.whatsapp.intake import CLAIM_SECONDS, RECOVERY_ATTEMPTS

from tests.ingestion.whatsapp_cases import ORIGIN, World, image
from tests.ingestion.whatsapp_support import (
    ALICE_PHONE,
    RECEIPT_PNG,
    STRANGER_PHONE,
    Media,
    fixture,
)

PHOTO_LOST = "No pude guardar tu foto. ¿Me la envías otra vez?"


def _media_lookups(world: World) -> int:
    return sum(
        1 for request in world.graph.requests if request.url.host == "graph.facebook.com"
    )


async def _deliver_then_die(world: World, body: dict) -> None:
    """The webhook commits the claim and answers; the process dies before the
    background read starts."""

    world.intake.background = lambda work: work.close()
    try:
        await world.deliver(body)
    finally:
        world.intake.background = None


def _lapse(world: World) -> None:
    world.clock.now += timedelta(seconds=CLAIM_SECONDS + 1)


async def a_photo_lost_behind_the_ack_is_recovered_exactly_once(world: World) -> None:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000201"] = Media(RECEIPT_PNG, "image/png")
    await _deliver_then_die(world, image("700000000000201", "wamid.CASE-LOST"))
    record = world.record("wamid.CASE-LOST")
    assert (record.status, record.claim_envelope is not None) == ("received", True)
    assert world.captures(world.alice) == []

    _lapse(world)
    await world.intake.recover()
    await world.intake.recover()

    [connection_id] = world.captures(world.alice)
    record = world.record("wamid.CASE-LOST")
    assert (record.status, record.connection_id, record.claim_envelope) == (
        "captured",
        connection_id,
        None,
    )
    assert _media_lookups(world) == 1
    assert world.transport.bodies()[-1] == (
        f"Recibido. Revísalo aquí: {ORIGIN}/biz?receipt={connection_id}"
    )


async def a_fresh_claim_is_left_to_its_own_worker(world: World) -> None:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000202"] = Media(RECEIPT_PNG, "image/png")
    await _deliver_then_die(world, image("700000000000202", "wamid.CASE-FRESH"))
    world.clock.now += timedelta(seconds=CLAIM_SECONDS - 1)
    await world.intake.recover()
    assert world.record("wamid.CASE-FRESH").status == "received"
    assert world.captures(world.alice) == []


async def a_settled_message_is_never_run_again(world: World) -> None:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000203"] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(image("700000000000203", "wamid.CASE-SETTLED"))
    replies = len(world.transport.sent)
    _lapse(world)
    await world.intake.recover()
    assert len(world.captures(world.alice)) == 1
    assert len(world.transport.sent) == replies
    assert world.record("wamid.CASE-SETTLED").claim_envelope is None


async def retries_are_bounded_then_the_sender_is_asked_once_to_resend(
    world: World,
) -> None:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000204"] = Media(RECEIPT_PNG, "image/png")
    await _deliver_then_die(world, image("700000000000204", "wamid.CASE-DOOMED"))
    media = world.intake.media

    class Dies:
        async def fetch(self, media_id: str):  # noqa: ANN202
            raise asyncio.CancelledError

    world.intake.media = Dies()
    for _ in range(RECOVERY_ATTEMPTS):
        _lapse(world)
        with pytest.raises(asyncio.CancelledError):
            await world.intake.recover()
        assert world.record("wamid.CASE-DOOMED").status == "received"
    world.intake.media = media
    replies = len(world.transport.sent)

    _lapse(world)
    await world.intake.recover()
    _lapse(world)
    await world.intake.recover()

    record = world.record("wamid.CASE-DOOMED")
    assert (record.status, record.error_code, record.claim_envelope) == (
        "failed",
        "whatsapp_recovery_exhausted",
        None,
    )
    assert world.transport.bodies()[replies:] == [PHOTO_LOST]
    assert world.captures(world.alice) == []


async def concurrent_sweeps_make_one_receipt(world: World) -> None:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000205"] = Media(RECEIPT_PNG, "image/png")
    await _deliver_then_die(world, image("700000000000205", "wamid.CASE-RACE"))
    _lapse(world)
    await asyncio.gather(*(world.intake.recover() for _ in range(4)))
    assert len(world.captures(world.alice)) == 1
    assert _media_lookups(world) == 1
    assert world.record("wamid.CASE-RACE").claim_envelope is None


async def a_lapsed_claim_with_no_envelope_fails_visibly(world: World) -> None:
    await world.link(world.alice, ALICE_PHONE)
    now = world.clock()
    key = world.keys.message("wamid.CASE-OLDROW")
    world.store.claim(
        provider_message_key=key,
        sender_hash=world.keys.sender(ALICE_PHONE),
        now=now,
        claim_until=now + timedelta(seconds=CLAIM_SECONDS),
    )
    replies = len(world.transport.sent)
    _lapse(world)
    await world.intake.recover()
    record = world.store.inbound(key)
    assert (record.status, record.error_code, record.claim_until) == (
        "failed",
        "whatsapp_claim_envelope_missing",
        None,
    )
    assert len(world.transport.sent) == replies


async def a_sender_who_unlinked_meanwhile_gets_nothing_and_leaves_no_envelope(
    world: World,
) -> None:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000206"] = Media(RECEIPT_PNG, "image/png")
    await _deliver_then_die(world, image("700000000000206", "wamid.CASE-GONE"))
    world.store.revoke(destination_owner_id=world.alice, now=world.clock())
    replies = len(world.transport.sent)
    _lapse(world)
    await world.intake.recover()
    record = world.record("wamid.CASE-GONE")
    assert (record.status, record.claim_envelope) == ("rejected", None)
    assert world.captures(world.alice) == []
    assert len(world.transport.sent) == replies


async def webhook_traffic_runs_the_sweep_without_background_jobs(world: World) -> None:
    await world.link(world.alice, ALICE_PHONE)
    world.graph.media["700000000000207"] = Media(RECEIPT_PNG, "image/png")
    await _deliver_then_die(world, image("700000000000207", "wamid.CASE-NUDGED"))
    _lapse(world)
    started: list = []
    world.intake.background = started.append
    world.intake._last_nudge = None
    await world.deliver(
        fixture(
            "text_link_code.json",
            id="wamid.CASE-POKE",
            sender=STRANGER_PHONE,
            text="hola",
        )
    )
    world.intake.background = None
    for work in started:
        await work
    assert len(world.captures(world.alice)) == 1
    assert world.record("wamid.CASE-NUDGED").status == "captured"


RECOVERY_CASES = (
    a_photo_lost_behind_the_ack_is_recovered_exactly_once,
    a_fresh_claim_is_left_to_its_own_worker,
    a_settled_message_is_never_run_again,
    retries_are_bounded_then_the_sender_is_asked_once_to_resend,
    concurrent_sweeps_make_one_receipt,
    a_lapsed_claim_with_no_envelope_fails_visibly,
    a_sender_who_unlinked_meanwhile_gets_nothing_and_leaves_no_envelope,
    webhook_traffic_runs_the_sweep_without_background_jobs,
)
