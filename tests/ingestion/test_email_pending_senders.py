"""Pending senders in memory: mail from a sender not on the list is not stored."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.ingestion.email_intake.standing import email_row

from tests.ingestion.test_email_intake_service import RECIPIENT, rig

ALIGNED = {"spf": "pass", "dkim": "pass", "dmarc": "pass"}
FORGED = {"spf": "pass", "dkim": "fail", "dmarc": "fail"}
NOTE = "No pudimos verificar este remitente."
SENDER = "proveedor@example.test"


def _world(*, on: bool = True, authentication=ALIGNED):
    world = rig()
    world.runtime.pending_senders = lambda: on
    world.provider.authentication = authentication
    world.provider.provider_from = SENDER
    return world


async def _send(world):
    delivery = world.runtime.enqueue_resend(str(uuid4()), (RECIPIENT,))
    assert await world.runtime.next()
    return world.store.get(delivery.id, world.route.space_id)


def _rule(world, address=SENDER):
    return next(
        (r for r in world.store.list_senders(world.route.space_id) if r.value == address),
        None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authentication", "verdict"),
    [(ALIGNED, "aligned"), (FORGED, "failed"), (None, "no_result")],
)
async def test_an_unknown_sender_stores_nothing_and_is_listed_pending(
    authentication, verdict
):
    world = _world(authentication=authentication)
    saved = await _send(world)
    assert (saved.state, saved.error_code, saved.inbox_group) == (
        "rejected",
        "email_sender_pending",
        None,
    )
    assert saved.original_document_id is None
    assert world.store.parts(saved.id) == []
    assert world.drafts() == []
    rule = _rule(world)
    assert (rule.status, rule.last_auth_result) == ("pending", verdict)
    assert rule.last_seen_at == world.clock.now
    # Not a Bandeja row of its own, so no Bandeja count.
    assert email_row(saved, [], lambda part: False).standing is None


@pytest.mark.asyncio
async def test_a_second_message_refreshes_the_pending_row_and_keeps_it_pending():
    world = _world(authentication=FORGED)
    await _send(world)
    first = _rule(world)
    world.clock.advance(60)
    world.provider.authentication = ALIGNED
    await _send(world)
    again = _rule(world)
    assert (again.id, again.status, again.last_auth_result) == (
        first.id,
        "pending",
        "aligned",
    )
    assert again.last_seen_at == world.clock.now


@pytest.mark.asyncio
async def test_once_authorized_the_sender_lands_in_bandeja():
    world = _world()
    await _send(world)
    world.store.upsert_sender(world.route.space_id, "address", SENDER, "authorized")
    saved = await _send(world)
    assert (saved.state, saved.inbox_group, saved.review_note) == (
        "captured",
        "bandeja",
        None,
    )
    assert _rule(world).status == "authorized"


@pytest.mark.asyncio
async def test_an_authorized_sender_keeps_todays_routing_whatever_the_verdict():
    world = _world(authentication=FORGED)
    world.store.upsert_sender(world.route.space_id, "address", SENDER, "authorized")
    failed = await _send(world)
    assert (failed.state, failed.inbox_group, failed.review_note) == (
        "captured",
        "bandeja",
        NOTE,
    )
    world.provider.authentication = None
    unknown = await _send(world)
    assert (unknown.state, unknown.inbox_group, unknown.review_note) == (
        "captured",
        "bandeja",
        None,
    )
    rule = _rule(world)
    assert (rule.status, rule.last_auth_result) == ("authorized", "no_result")


@pytest.mark.asyncio
async def test_a_blocked_sender_is_dropped_and_its_row_untouched():
    world = _world()
    world.store.upsert_sender(world.route.space_id, "address", SENDER, "blocked")
    saved = await _send(world)
    assert (saved.state, saved.error_code) == ("rejected", "email_sender_blocked")
    rule = _rule(world)
    assert (rule.status, rule.last_auth_result, rule.last_seen_at) == (
        "blocked",
        None,
        None,
    )
    assert world.provider.calls == 0


@pytest.mark.asyncio
async def test_with_the_flag_off_an_unknown_sender_is_stored_in_new_senders():
    world = _world(on=False)
    saved = await _send(world)
    assert (saved.state, saved.inbox_group) == ("captured", "remitentes_nuevos")
    assert saved.original_document_id is not None
    assert world.store.list_senders(world.route.space_id) == []


@pytest.mark.asyncio
async def test_turning_the_flag_on_leaves_earlier_new_sender_rows_as_they_were():
    world = _world(on=False)
    old = await _send(world)
    world.runtime.pending_senders = lambda: True
    await _send(world)
    kept = world.store.get(old.id, world.route.space_id)
    assert kept == old
    assert _rule(world).status == "pending"


def test_the_flag_defaults_off(monkeypatch):
    from argus.domain.ingestion.email_intake.config import EmailIntakeSettings

    for prefix in ("CUADRAO_", "ARGUS_"):
        monkeypatch.delenv(
            f"{prefix}BUSINESS_EMAIL_PENDING_SENDERS_ENABLED", raising=False
        )
    assert EmailIntakeSettings().pending_senders_enabled is False
    assert rig().runtime.pending_senders() is False
    monkeypatch.setenv("CUADRAO_BUSINESS_EMAIL_PENDING_SENDERS_ENABLED", "true")
    assert rig().runtime.pending_senders() is True
