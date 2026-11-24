"""Grouped failure replies sent by document upkeep against disposable Postgres."""

import asyncio
import base64
import json
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from argus.domain.ingestion.whatsapp import document_step
from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings
from psycopg_pool import ConnectionPool

from tests import test_whatsapp_intake_postgres as shared
from tests.ingestion import whatsapp_cases as cases
from tests.ingestion.whatsapp_support import PHONE_NUMBER_ID, SENDER_KEY, Media
from workflows.document_worker import in_turn

pool = shared.pool
users = shared.users
pytestmark = shared.pytestmark


def _configure_replies(
    monkeypatch: pytest.MonkeyPatch, suffix: UUID
) -> list[dict[str, Any]]:
    for key, value in {
        "CUADRAO_WHATSAPP_INTAKE_ENABLED": "true",
        "CUADRAO_WHATSAPP_OUTBOUND_ENABLED": "true",
        "CUADRAO_WHATSAPP_ACCESS_TOKEN": "test-access-token",
        "CUADRAO_WHATSAPP_SENDER_KEY": f"{SENDER_KEY}-{suffix}",
        "CUADRAO_WHATSAPP_NUMBER_ID": PHONE_NUMBER_ID,
        "CUADRAO_WHATSAPP_GRAPH_API_VERSION": "v23.0",
        "CUADRAO_WHATSAPP_VERIFY_TOKEN": "",
        "CUADRAO_WHATSAPP_APP_SECRET": "",
        "CUADRAO_INGESTION_SECRET_KEY": base64.urlsafe_b64encode(b"w" * 32).decode(),
        "CUADRAO_DOCUMENT_EXTRACTION_ENABLED": "false",
    }.items():
        monkeypatch.setenv(key, value)

    sent = []

    def send(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v23.0/{PHONE_NUMBER_ID}/messages"
        assert request.headers["Authorization"] == "Bearer test-access-token"
        sent.append(json.loads(request.content))
        return httpx.Response(200)

    monkeypatch.setattr(
        document_step,
        "httpx",
        SimpleNamespace(
            AsyncClient=lambda: httpx.AsyncClient(transport=httpx.MockTransport(send))
        ),
    )
    return sent


@pytest.mark.asyncio
async def test_document_upkeep_sends_a_due_group_without_webhook_credentials(
    monkeypatch: pytest.MonkeyPatch, pool: ConnectionPool, users: dict[str, str]
) -> None:
    suffix = uuid4()
    monkeypatch.setattr(cases, "uuid4", lambda: suffix)
    world = await shared._linked(pool, users)
    world.clock.now = world.clock.now.replace(hour=12, minute=0, second=0, microsecond=0)
    sent = _configure_replies(monkeypatch, suffix)
    monkeypatch.setenv("CUADRAO_WHATSAPP_OUTBOUND_ENABLED", "false")
    for index, kind in enumerate(("unsupported", "blocked")):
        await shared._failed(world, index, kind=kind)

    grouped = document_step.FailureReplyUpkeep(
        world.store.reply_groups, clock=world.clock
    )
    tick = in_turn(grouped.cleanup, grouped.send_due)
    await asyncio.to_thread(tick)
    assert sent == []

    monkeypatch.setenv("CUADRAO_WHATSAPP_OUTBOUND_ENABLED", "true")
    settings = load_whatsapp_settings()
    assert settings.replies_ready
    assert not settings.intake_ready
    world.clock.now += timedelta(seconds=60)
    await asyncio.to_thread(tick)
    assert sent == []

    world.clock.now += timedelta(seconds=60)
    await asyncio.to_thread(tick)
    [message] = sent
    assert message["to"] == cases.ALICE_PHONE
    assert all(f"factura_{index}.png" in message["text"]["body"] for index in range(2))
    assert shared._counts(pool, world) == [(1, 0)]

    restarted = document_step.FailureReplyUpkeep(
        world.store.reply_groups, clock=world.clock
    )
    await asyncio.to_thread(in_turn(restarted.cleanup, restarted.send_due))
    assert len(sent) == 1
    assert shared._counts(pool, world) == [(1, 0)]


@pytest.mark.asyncio
@pytest.mark.parametrize("first_group", ["daily_limit", "revoked", "window"])
async def test_due_pass_continues_after_dropping_a_group(
    monkeypatch: pytest.MonkeyPatch,
    pool: ConnectionPool,
    users: dict[str, str],
    first_group: str,
) -> None:
    suffix = uuid4()
    monkeypatch.setattr(cases, "uuid4", lambda: suffix)
    world = await shared._linked(pool, users)
    await world.link(world.bob, cases.BOB_PHONE)
    world.clock.now = world.clock.now.replace(hour=12, minute=0, second=0, microsecond=0)
    sent = _configure_replies(monkeypatch, suffix)

    await shared._failed(world, 0)
    if first_group == "daily_limit":
        world.clock.now += timedelta(seconds=120)
        assert await shared._worker(world).run_once()
        monkeypatch.setenv("CUADRAO_WHATSAPP_REPLY_DAILY_LIMIT", "1")
        await shared._failed(world, 1)
    elif first_group == "revoked":
        world.store.revoke(destination_owner_id=world.alice, now=world.clock.now)
    else:
        world.clock.now += timedelta(hours=24)

    # The suppressed group has the earlier send_after, so the worker must
    # consume it before it can reach the valid group.
    world.clock.now += timedelta(seconds=1)
    media_id = "700000000000901"
    world.graph.media[media_id] = Media(b"not an image", "image/png")
    await world.deliver(cases.image(media_id, "wamid.GROUP-BOB", cases.BOB_PHONE))
    world.clock.now += timedelta(seconds=120)

    grouped = document_step.FailureReplyUpkeep(
        world.store.reply_groups, clock=world.clock
    )
    await asyncio.to_thread(grouped.send_due)

    assert [message["to"] for message in sent] == [cases.BOB_PHONE]
    with pool.connection() as connection:
        assert (
            connection.execute(
                "select sender_hash from public.whatsapp_reply_groups where owner_id in (%s, %s)",
                (world.alice, world.bob),
            ).fetchall()
            == []
        )
