"""Signed receipt webhooks through the production wiring and disposable Postgres."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from random import Random
from struct import pack
from time import perf_counter
from types import SimpleNamespace
from typing import Any
from uuid import uuid4
from zlib import crc32

import httpx
import pytest
import pytest_asyncio
from argus.api import whatsapp
from argus.api.main import app
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.jobs import PreparationJobs
from argus.domain.ingestion.documents.objects import owner_prefix, source_path
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
from loguru import logger
from PIL import Image
from psycopg_pool import ConnectionPool

from tests import test_business_actions_postgres as shared
from tests.business_reading_support import reading_setting, turn_reading
from tests.document_sources_support import source_objects
from tests.ingestion.whatsapp_cases import ALICE_PHONE, Clock, image
from tests.ingestion.whatsapp_support import (
    ENV,
    PHONE_NUMBER_ID,
    RECEIPT_PNG,
    FakeGraph,
    Media,
    RefusingExtractor,
    encode,
    sign,
)

actions = shared.actions
users = shared.users
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]

MESSAGE_ID = "wamid.WEBHOOK-POSTGRES"
MEDIA_ID = "700000000000901"


@pytest.fixture(autouse=True)
def reads_finish_inside_the_request() -> None:
    """Keep real preparation dispatch with no reader in the API process."""


@dataclass
class Webhook:
    client: httpx.AsyncClient
    graph: FakeGraph
    replies: list[dict[str, Any]]
    documents: DocumentsService
    pool: ConnectionPool
    store: PostgresWhatsAppStore
    key: bytes
    owner: str
    clock: Clock

    def drafts(self) -> list[tuple]:
        with self.pool.connection() as connection:
            return connection.execute(
                "select connection_id::text, draft, preparation_job, preparation_binding from "
                "public.financial_document_extractions where user_id=%s",
                (self.owner,),
            ).fetchall()

    def signed_receipt(self, content: bytes) -> bytes:
        self.graph.media[MEDIA_ID] = Media(content, "image/png")
        return encode(image(MEDIA_ID, MESSAGE_ID), self.clock.now)

    async def post(self, raw: bytes) -> httpx.Response:
        return await self.client.post(
            whatsapp.WEBHOOK_PATH,
            content=raw,
            headers={"X-Hub-Signature-256": sign(raw)},
        )


@pytest_asyncio.fixture
async def webhook(actions, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Webhook]:  # noqa: ANN001
    business, context, _ = actions
    pool, owner, space = (
        business.authority.pool,
        str(context.owner_id),
        str(context.actor.space_id),
    )
    clock = Clock()
    hub = IngestionHub(
        PostgresConnectionRepository(pool),
        box=SecretBox(b"w" * 32),
        sink=business.imports,
        clock=clock,
    )
    objects = source_objects()
    documents = DocumentsService(
        hub,
        PostgresDocumentStore(pool, objects),
        RefusingExtractor(),
        business_actions=business,
        business_preparation_required=True,
    )
    documents.business_receipt_consent = reading_setting(pool)
    turn_reading(documents.business_receipt_consent, space, owner)
    graph, replies = FakeGraph(), []

    def fake_graph(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/messages"):
            replies.append(json.loads(request.content))
            return httpx.Response(200, json={"messages": [{"id": "wamid.FAKE-ACK"}]})
        return graph.handler(request)

    for name, value in ENV.items():
        monkeypatch.setenv(name.replace("ARGUS_", "CUADRAO_", 1), value)
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    monkeypatch.setenv("CUADRAO_WHATSAPP_NUMBER_ID", PHONE_NUMBER_ID)
    monkeypatch.setenv("CUADRAO_WHATSAPP_SENDER_KEY", f"test-{uuid4()}")
    monkeypatch.setenv("CUADRAO_WHATSAPP_OUTBOUND_ENABLED", "true")
    monkeypatch.delenv("POSTHOG_PROJECT_TOKEN", raising=False)
    monkeypatch.setattr(whatsapp.api_state, "PERSISTENCE_MODE", "supabase")
    monkeypatch.setattr(whatsapp, "documents_service", lambda: documents)
    monkeypatch.setattr(whatsapp, "ingestion_hub", lambda: hub)
    monkeypatch.setattr(whatsapp, "business_spaces", lambda: PostgresSpaceStore(pool))
    previous = whatsapp.whatsapp_runtime()
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(fake_graph)) as provider,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        monkeypatch.setattr(
            whatsapp, "httpx", SimpleNamespace(AsyncClient=lambda: provider)
        )
        monkeypatch.setattr(app.state, "financial_accounts_pool", pool, raising=False)
        whatsapp.start_whatsapp(app)
        try:
            runtime = whatsapp.whatsapp_runtime()
            assert runtime is not None
            store = runtime.intake.store
            assert isinstance(store, PostgresWhatsAppStore)
            keys = runtime.intake.keys
            issued = runtime.intake.issue_code(
                destination_owner_id=owner, reply_language="es-419"
            )
            assert (
                store.redeem_code(
                    code_digest=keys.code(issued.code),
                    sender_hash=keys.sender(ALICE_PHONE),
                    last4=ALICE_PHONE[-4:],
                    now=clock.now,
                )
                is not None
            )
            yield Webhook(
                client,
                graph,
                replies,
                documents,
                pool,
                store,
                keys.message(MESSAGE_ID),
                owner,
                clock,
            )
        finally:
            whatsapp.configure_whatsapp(previous)
            objects.delete(owner_prefix(owner))


def _assert_captured(webhook: Webhook, content: bytes) -> tuple:
    [(connection_id, draft, job, binding)] = webhook.drafts()
    assert (draft["status"], draft["source_available"], draft["size_bytes"]) == (
        "queued",
        True,
        len(content),
    )
    assert job["attempt_id"] and job["attempt"] == 1
    assert binding["connection_id"] == connection_id
    assert job.get("provider_calls", 0) == 0
    assert job.get("provider_call_started_at") is None
    assert (
        webhook.documents.store.source(user_id=webhook.owner, connection_id=connection_id)
        == content
    )
    inbound = webhook.store.inbound(webhook.key)
    assert inbound is not None
    assert (inbound.status, inbound.claim_until, inbound.connection_id) == (
        "captured",
        None,
        connection_id,
    )
    [reply] = webhook.replies
    assert reply["context"] == {"message_id": MESSAGE_ID}
    assert reply["to"] == ALICE_PHONE
    return (draft, job, binding, inbound, reply)


async def _assert_interrupted(webhook: Webhook, raw: bytes) -> None:
    with suppress(asyncio.CancelledError):
        response = await webhook.post(raw)
        assert response.status_code >= 500, response


@pytest.mark.asyncio
async def test_preparation_stays_invisible_until_the_capture_commits(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = PreparationJobs.start
    observed = []

    def observe_after_start(
        jobs: PreparationJobs, *, user_id: str, connection_id: str
    ) -> None:
        start(jobs, user_id=user_id, connection_id=connection_id)
        inbound = webhook.store.inbound(webhook.key)
        assert inbound is not None
        [(_, draft, job, binding)] = webhook.drafts()
        observed.append(
            (inbound.status, draft["status"], draft["source_available"], job, binding)
        )

    monkeypatch.setattr(PreparationJobs, "start", observe_after_start)
    response = await webhook.post(webhook.signed_receipt(RECEIPT_PNG))

    assert response.status_code == 200
    assert observed == [("received", "saved", False, None, None)]
    _assert_captured(webhook, RECEIPT_PNG)


@pytest.mark.asyncio
async def test_reading_withdrawn_before_settlement_leaves_the_receipt_unread(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload = webhook.documents.upload

    async def upload_then_withdraw(**kwargs: Any):
        captured = await upload(**kwargs)
        await asyncio.to_thread(
            turn_reading,
            webhook.documents.business_receipt_consent,
            kwargs["scope"].space_id,
            webhook.owner,
            False,
        )
        return captured

    monkeypatch.setattr(webhook.documents, "upload", upload_then_withdraw)
    response = await webhook.post(webhook.signed_receipt(RECEIPT_PNG))

    assert response.status_code == 200
    [(connection_id, draft, job, binding)] = webhook.drafts()
    assert (draft["status"], draft["source_available"], draft["consent"]) == (
        "saved",
        True,
        False,
    )
    assert job is binding is None
    inbound = webhook.store.inbound(webhook.key)
    assert inbound is not None
    assert (inbound.status, inbound.connection_id) == ("captured", connection_id)


@pytest.mark.asyncio
async def test_refused_preparation_saves_the_receipt_with_its_reason(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = PreparationJobs.start

    def refuse_after_start(
        jobs: PreparationJobs, *, user_id: str, connection_id: str
    ) -> None:
        start(jobs, user_id=user_id, connection_id=connection_id)
        raise DocumentServiceError("business_preparation_unavailable")

    monkeypatch.setattr(PreparationJobs, "start", refuse_after_start)
    response = await webhook.post(webhook.signed_receipt(RECEIPT_PNG))

    assert response.status_code == 200
    [(connection_id, draft, job, binding)] = webhook.drafts()
    assert (draft["status"], draft["source_available"], draft["error_code"]) == (
        "saved",
        True,
        "business_preparation_unavailable",
    )
    assert job is binding is None
    inbound = webhook.store.inbound(webhook.key)
    assert inbound is not None
    assert (inbound.status, inbound.connection_id) == ("captured", connection_id)


@pytest.mark.asyncio
async def test_crash_before_save_requires_webhook_redelivery_after_lease(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = webhook.signed_receipt(RECEIPT_PNG)
    crashed_at_save = False

    async def crash_before_save(**_: object) -> None:
        nonlocal crashed_at_save
        claimed = webhook.store.inbound(webhook.key)
        assert claimed is not None and claimed.claim_until is not None
        assert claimed.claim_until > webhook.clock.now
        assert claimed.status == "received"
        assert webhook.drafts() == []
        crashed_at_save = True
        raise asyncio.CancelledError

    with monkeypatch.context() as patch:
        patch.setattr(webhook.documents, "upload", crash_before_save)
        await _assert_interrupted(webhook, raw)
    assert crashed_at_save

    claimed = webhook.store.inbound(webhook.key)
    assert claimed is not None and claimed.claim_until is not None
    assert claimed.claim_until > webhook.clock.now
    downloads = len(webhook.graph.requests)
    assert downloads == 2
    held = await webhook.post(raw)
    assert (held.status_code, held.json()["code"]) == (503, "whatsapp_webhook_retry")
    assert webhook.store.inbound(webhook.key) == claimed
    assert webhook.drafts() == webhook.replies == []
    assert len(webhook.graph.requests) == downloads

    webhook.clock.now = claimed.claim_until + timedelta(seconds=1)
    retry = await webhook.post(raw)
    assert (retry.status_code, retry.json()) == (200, {"received": True})
    settled = _assert_captured(webhook, RECEIPT_PNG)
    assert len(webhook.graph.requests) == downloads + 2

    replay = await webhook.post(raw)
    assert (replay.status_code, replay.json()) == (200, {"received": True})
    assert _assert_captured(webhook, RECEIPT_PNG) == settled
    assert len(webhook.graph.requests) == downloads + 2


@pytest.mark.asyncio
async def test_crash_after_save_redelivery_repairs_missing_preparation_attempt(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = webhook.signed_receipt(RECEIPT_PNG)
    start = PreparationJobs.start
    calls: list[str] = []

    def crash_once(jobs: PreparationJobs, *, user_id: str, connection_id: str) -> None:
        calls.append(connection_id)
        start(jobs, user_id=user_id, connection_id=connection_id)
        if len(calls) == 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(PreparationJobs, "start", crash_once)
    await _assert_interrupted(webhook, raw)

    [(connection_id, draft, job, binding)] = webhook.drafts()
    assert calls == [connection_id]
    assert (draft["status"], draft["source_available"], job, binding) == (
        "saved",
        False,
        None,
        None,
    )
    objects = webhook.documents.store.objects
    assert (
        objects.get(source_path(user_id=webhook.owner, sha256=draft["sha256"]))
        == RECEIPT_PNG
    )
    assert webhook.replies == []
    claimed = webhook.store.inbound(webhook.key)
    assert claimed is not None and claimed.claim_until is not None
    assert claimed.status == "received"
    assert claimed.claim_until > webhook.clock.now

    webhook.clock.now = claimed.claim_until + timedelta(seconds=1)
    retry = await webhook.post(raw)
    assert (retry.status_code, retry.json()) == (200, {"received": True})
    settled = _assert_captured(webhook, RECEIPT_PNG)
    assert calls == [connection_id, connection_id]

    replay = await webhook.post(raw)
    assert (replay.status_code, replay.json()) == (200, {"received": True})
    assert _assert_captured(webhook, RECEIPT_PNG) == settled
    assert calls == [connection_id, connection_id]


def _five_mb_png() -> bytes:
    width = 1290
    buffer = BytesIO()
    pixels = Random(0).randbytes(width * width * 3)
    Image.frombytes("RGB", (width, width), pixels).save(
        buffer, format="PNG", compress_level=0
    )
    png = buffer.getvalue()
    # Fill the small remainder with a valid PNG text chunk before IEND.
    chunk = b"tEXt" + b"fixture\0" + b" " * (5_000_000 - len(png) - 20)
    return (
        png[:-12]
        + pack(">I", len(chunk) - 4)
        + chunk
        + pack(">I", crc32(chunk))
        + png[-12:]
    )


@pytest.mark.asyncio
async def test_five_mb_webhook_finishes_with_durable_receipt_before_200(
    webhook: Webhook,
) -> None:
    content = _five_mb_png()
    assert len(content) == 5_000_000
    raw = webhook.signed_receipt(content)
    started = perf_counter()
    response = await webhook.post(raw)
    elapsed = perf_counter() - started
    assert (response.status_code, response.json()) == (200, {"received": True})
    _assert_captured(webhook, content)
    logger.info("5 MB signed receipt webhook with Postgres writes took {:.3f}s", elapsed)
