from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Literal, Protocol

from loguru import logger

from argus.domain.ingestion.whatsapp.replies import ReplyFailed, ReplyTransport
from argus.domain.ingestion.whatsapp.reply_groups import (
    SEND_TIMEOUT,
    WINDOW,
    ReplyAttempt,
    ReplyGroupCodec,
    suppressed,
)


class ReplyGroupStore(Protocol):
    def recover(self, *, now: datetime) -> None: ...
    def claim(self, *, now: datetime, limit: int) -> ReplyAttempt | None: ...
    def authorized(self, attempt: ReplyAttempt, *, now: datetime) -> bool: ...
    def finish(
        self,
        attempt: ReplyAttempt,
        *,
        now: datetime,
        outcome: Literal["sent", "retry", "drop", "unknown"],
    ) -> None: ...


class FailureReplyWorker:
    def __init__(
        self,
        *,
        store: ReplyGroupStore,
        codec: ReplyGroupCodec,
        transport: ReplyTransport,
        clock: Callable[[], datetime],
        enabled: Callable[[], bool],
        limit: int = 10,
    ) -> None:
        self.store, self.codec, self.transport = store, codec, transport
        self.clock, self.enabled, self.limit = clock, enabled, limit

    async def run_once(self) -> bool:
        await asyncio.to_thread(self.store.recover, now=self.clock())
        if not self.enabled():
            return False
        attempt = await asyncio.to_thread(
            self.store.claim, now=self.clock(), limit=self.limit
        )
        if attempt is None:
            return False
        group = attempt.group
        try:
            payload = self.codec.payload(attempt)
        except Exception:
            suppressed("unreadable", group.sender_hash)
            await asyncio.to_thread(
                self.store.finish, attempt, now=self.clock(), outcome="drop"
            )
            return True
        if not self.enabled():
            outcome = "retry"
        elif self.clock() - group.last_sent_at >= WINDOW:
            suppressed("window", group.sender_hash)
            outcome = "drop"
        elif not await asyncio.to_thread(
            self.store.authorized, attempt, now=self.clock()
        ):
            suppressed("unknown_sender", group.sender_hash)
            outcome = "drop"
        else:
            try:
                await asyncio.wait_for(self.transport.send(payload), timeout=SEND_TIMEOUT)
                outcome = "sent"
            except ReplyFailed as error:
                outcome = "unknown" if error.outcome_unknown else "retry"
            except asyncio.TimeoutError:
                outcome = "unknown"
            except Exception:
                outcome = "unknown"
            if outcome == "unknown":
                suppressed("send_outcome_unknown", group.sender_hash)
        await asyncio.to_thread(
            self.store.finish, attempt, now=self.clock(), outcome=outcome
        )
        return True

    async def run(self) -> None:
        while True:
            try:
                worked = await self.run_once()
            except Exception as error:
                logger.warning(
                    "WhatsApp failure reply worker interrupted",
                    failure_mode=type(error).__name__,
                )
                worked = False
            await asyncio.sleep(0 if worked else 1)
