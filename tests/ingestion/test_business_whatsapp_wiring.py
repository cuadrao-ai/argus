"""Linked text gets the ordinary webhook reply even with the old agent switch on."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from argus.api.whatsapp import build_whatsapp
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings
from argus.domain.ingestion.whatsapp.payload import Delivery, TextMessage
from argus.domain.ingestion.whatsapp.store import InMemoryWhatsAppStore

from tests.ingestion.whatsapp_support import ALICE_PHONE, ENV


@pytest.mark.asyncio
async def test_linked_text_uses_the_ordinary_webhook_reply(monkeypatch):
    from json import loads

    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CUADRAO_WHATSAPP_AGENT_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_WHATSAPP_OUTBOUND_ENABLED", "true")
    now = datetime.now(timezone.utc)
    documents = SimpleNamespace(
        hub=SimpleNamespace(box=SecretBox(b"w" * 32), clock=lambda: now)
    )
    replies = []

    def send(request: httpx.Request) -> httpx.Response:
        replies.append(loads(request.content)["text"]["body"])
        return httpx.Response(200, json={"messages": [{"id": "wamid.sent"}]})

    store = InMemoryWhatsAppStore()
    pool = Mock()
    pool.connection.side_effect = AssertionError(
        "Linked text must only use the intake store"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        runtime = build_whatsapp(
            load_whatsapp_settings(),
            documents=documents,
            spaces=Mock(),
            store=store,
            client=client,
            app_origin="https://app.test",
            pool=pool,
        )
        issued = runtime.intake.issue_code(
            destination_owner_id=str(uuid4()), reply_language="en"
        )
        keys = runtime.intake.keys
        store.redeem_code(
            code_digest=keys.code(issued.code),
            sender_hash=keys.sender(ALICE_PHONE),
            last4=ALICE_PHONE[-4:],
            now=now,
        )
        message = TextMessage("wamid.linked-text", ALICE_PHONE, now, "hola")
        await runtime.intake.handle(Delivery((message,), 0, 0, 0))
        assert (
            store.inbound(keys.message(message.id)).error_code
            == "whatsapp_receipt_missing"
        )
    assert replies == [
        "We only take receipts here. For everything else use Cuadrao: https://app.test/biz"
    ]
    pool.connection.assert_not_called()
