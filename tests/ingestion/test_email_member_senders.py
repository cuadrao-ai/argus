"""Owner and team are approved by default when pending senders are on, in memory."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.ingestion.email_intake import sender_policy

from tests.ingestion.test_email_intake_service import RECIPIENT, rig

ALIGNED = {"spf": "pass", "dkim": "pass", "dmarc": "pass"}
FORGED = {"spf": "pass", "dkim": "fail", "dmarc": "fail"}
NO_POLICY = {"spf": "pass", "dkim": "gray", "dmarc": "gray"}
MEMBER = "jose@negocio.test"


def _world(authentication, *, on=True, member=True):
    world = rig()
    world.runtime.pending_senders = lambda: on
    if member:
        world.store.add_member(world.route.space_id, "Jose@Negocio.test")
    world.provider.raw = world.provider.raw.replace(
        b"proveedor@example.test", MEMBER.encode()
    )
    world.provider.sender = world.provider.provider_from = MEMBER
    world.provider.authentication = authentication
    return world


async def _send(world):
    delivery = world.runtime.enqueue_resend(str(uuid4()), (RECIPIENT,))
    assert await world.runtime.next()
    return world.store.get(delivery.id, world.route.space_id)


def _status(world):
    rules = world.store.list_senders(world.route.space_id)
    return [(r.value, r.status, r.last_auth_result) for r in rules]


@pytest.mark.parametrize(
    ("verdict", "aligned"),
    [("aligned", True), ("failed", False), ("none", False), ("no_result", False)],
)
@pytest.mark.parametrize("required", [True, False])
def test_the_one_switch_decides_the_member_default(
    monkeypatch, verdict, aligned, required
):
    monkeypatch.setattr(sender_policy, "DEFAULT_APPROVAL_REQUIRES_ALIGNED", required)
    assert sender_policy.default_approves(True, verdict) is (aligned or not required)
    assert sender_policy.default_approves(False, verdict) is False


@pytest.mark.asyncio
async def test_an_aligned_member_is_approved_and_lands_in_bandeja():
    world = _world(ALIGNED)
    saved = await _send(world)
    assert (saved.state, saved.inbox_group) == ("captured", "bandeja")
    assert _status(world) == [(MEMBER, "authorized", "aligned")]
    event = world.store.address_events(world.route.space_id)[-1]
    assert (event.event_type, event.actor_id, event.new_address) == (
        "sender_authorized",
        None,
        MEMBER,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authentication", "verdict"),
    [(FORGED, "failed"), (NO_POLICY, "none"), (None, "no_result")],
)
async def test_an_unverified_member_is_pending_while_alignment_is_required(
    authentication, verdict, monkeypatch
):
    monkeypatch.setattr(sender_policy, "DEFAULT_APPROVAL_REQUIRES_ALIGNED", True)
    world = _world(authentication)
    saved = await _send(world)
    assert (saved.state, saved.error_code) == ("rejected", "email_sender_pending")
    assert _status(world) == [(MEMBER, "pending", verdict)]


@pytest.mark.asyncio
async def test_by_default_an_unverified_member_is_approved():
    assert sender_policy.DEFAULT_APPROVAL_REQUIRES_ALIGNED is False
    world = _world(FORGED)
    saved = await _send(world)
    assert (saved.state, saved.inbox_group) == ("captured", "bandeja")
    assert _status(world) == [(MEMBER, "authorized", "failed")]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["blocked", "pending"])
async def test_the_default_never_overrides_an_existing_row(status):
    world = _world(ALIGNED)
    world.store.upsert_sender(world.route.space_id, "address", MEMBER, status)
    saved = await _send(world)
    assert saved.state == "rejected"
    assert _status(world)[0][1] == status


@pytest.mark.asyncio
async def test_a_stranger_and_the_flag_off_get_no_default():
    stranger = _world(ALIGNED, member=False)
    assert (await _send(stranger)).error_code == "email_sender_pending"
    off = _world(ALIGNED, on=False)
    saved = await _send(off)
    assert (saved.state, saved.inbox_group) == ("captured", "remitentes_nuevos")
    assert _status(off) == []
