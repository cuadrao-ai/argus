"""Email sender checks: authorized senders in Bandeja, unlisted senders in new senders."""

from __future__ import annotations

import pytest

from tests.ingestion.test_email_intake_service import _authorize, rig


@pytest.mark.asyncio
async def test_an_authorized_from_with_no_result_lands_in_bandeja_and_warns():
    from loguru import logger

    seen: list[str] = []
    sink = logger.add(
        lambda message: seen.append(message.record["message"]), level="WARNING"
    )
    try:
        for authentication in (None, {}, {"dmarc": "processing_failed"}):
            world = rig()
            _authorize(world)
            world.provider.authentication = authentication
            world.provider.provider_from = "proveedor@example.test"
            delivery = world.enqueue()
            assert await world.runtime.next()
            saved = world.store.get(delivery.id, world.route.space_id)
            assert (
                saved.inbox_group,
                saved.auth_result,
                saved.review_note,
                saved.approved,
            ) == ("bandeja", "no_result", None, False)
    finally:
        logger.remove(sink)
    assert seen.count("email_auth_no_result") == 3


@pytest.mark.asyncio
async def test_an_authorized_from_with_no_dmarc_policy_is_pending_with_a_note():
    world = rig()
    _authorize(world)
    world.provider.authentication = {"spf": "pass", "dkim": "gray", "dmarc": "gray"}
    world.provider.provider_from = "proveedor@example.test"
    delivery = world.enqueue()
    assert await world.runtime.next()
    saved = world.store.get(delivery.id, world.route.space_id)
    assert (saved.inbox_group, saved.auth_result, saved.review_note, saved.approved) == (
        "bandeja",
        "failed",
        "No pudimos verificar este remitente.",
        False,
    )


@pytest.mark.asyncio
async def test_a_sender_not_on_the_list_goes_to_new_senders_whatever_its_check():
    for authentication in ({"dmarc": "pass", "dkim": "pass"}, {"dmarc": "fail"}, {}):
        world = rig()
        world.provider.authentication = authentication
        world.provider.provider_from = "proveedor@example.test"
        delivery = world.enqueue()
        assert await world.runtime.next()
        saved = world.store.get(delivery.id, world.route.space_id)
        assert (saved.inbox_group, saved.review_note, saved.approved) == (
            "remitentes_nuevos",
            None,
            False,
        )
