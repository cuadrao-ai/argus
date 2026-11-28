"""The WhatsApp passes on the document worker's existing sweep."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta

import httpx

from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.whatsapp.config import (
    WhatsAppSettings,
    load_whatsapp_settings,
)
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys
from argus.domain.ingestion.whatsapp.replies import CloudApiTransport
from argus.domain.ingestion.whatsapp.reply_groups import (
    DUE_EVERY,
    SEND_TIMEOUT,
    ReplyGroupCodec,
)
from argus.domain.ingestion.whatsapp.reply_worker import (
    FailureReplyWorker,
    ReplyGroupStore,
)

CLEANUP_EVERY = timedelta(hours=1)


class FailureReplyUpkeep:
    """Run grouped replies and expiry from the document worker's sweep thread."""

    def __init__(self, store: ReplyGroupStore, *, clock: Callable[[], datetime]) -> None:
        self.store, self.clock = store, clock
        self._next_due: datetime | None = None
        self._next_cleanup: datetime | None = None

    def cleanup(self) -> None:
        now = self.clock()
        if self._next_cleanup is not None and now < self._next_cleanup:
            return
        self._next_cleanup = now + CLEANUP_EVERY
        if load_whatsapp_settings().intake_enabled:
            self.store.recover(now=now)

    def send_due(self) -> None:
        now = self.clock()
        if self._next_due is not None and now < self._next_due:
            return
        self._next_due = now + DUE_EVERY
        settings = load_whatsapp_settings()
        if settings.replies_ready:
            asyncio.run(self._send(settings))

    async def _send(self, settings: WhatsAppSettings) -> None:
        assert settings.access_token and settings.sender_key and settings.phone_number_id
        codec = ReplyGroupCodec(
            SecretBox.from_env(), WhatsAppKeys(settings.sender_key.get_secret_value())
        )
        loop = asyncio.get_running_loop()
        # Leave enough time for the final send before yielding the sweep thread.
        stop_claiming_at = loop.time() + DUE_EVERY.total_seconds() - SEND_TIMEOUT
        async with httpx.AsyncClient() as client:
            worker = FailureReplyWorker(
                store=self.store,
                codec=codec,
                transport=CloudApiTransport(
                    client=client,
                    access_token=settings.access_token.get_secret_value(),
                    phone_number_id=settings.phone_number_id,
                    graph_api_version=settings.graph_api_version,
                ),
                clock=self.clock,
                enabled=lambda: load_whatsapp_settings().replies_ready,
                limit=settings.reply_daily_limit,
            )
            while loop.time() < stop_claiming_at:
                if not await worker.run_once():
                    return
