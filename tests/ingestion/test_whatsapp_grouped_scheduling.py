"""Grouped failure replies sent by document upkeep against disposable Postgres."""

import asyncio
import base64
import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from argus.domain.ingestion.whatsapp import document_step
from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings

from tests import test_whatsapp_intake_postgres as shared
from tests.ingestion import whatsapp_cases as cases
from tests.ingestion.whatsapp_support import PHONE_NUMBER_ID, SENDER_KEY
from workflows.document_worker import in_turn

pool = shared.pool
users = shared.users
pytestmark = shared.pytestmark


@pytest.mark.asyncio
async def test_document_upkeep_sends_a_due_group_without_webhook_credentials(
    monkeypatch, pool, users
):
    suffix = uuid4()
    monkeypatch.setattr(cases, "uuid4", lambda: suffix)
    world = await shared._linked(pool, users)
    world.clock.now = world.clock.now.replace(hour=12, minute=0, second=0, microsecond=0)
    for key, value in {
        "CUADRAO_WHATSAPP_INTAKE_ENABLED": "true",
        "CUADRAO_WHATSAPP_OUTBOUND_ENABLED": "false",
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
    for index in range(2):
        await shared._failed(world, index)

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
    assert [message["text"]["body"] for message in sent] == [
        "No pudimos leer 2 archivos:\n• factura_0.png\n• factura_1.png\nEnvíalos como foto o PDF."
    ]
    assert sent[0]["to"] == cases.ALICE_PHONE
    assert shared._counts(pool, world) == [(1, 0)]

    restarted = document_step.FailureReplyUpkeep(
        world.store.reply_groups, clock=world.clock
    )
    await asyncio.to_thread(in_turn(restarted.cleanup, restarted.send_due))
    assert len(sent) == 1
    assert shared._counts(pool, world) == [(1, 0)]
