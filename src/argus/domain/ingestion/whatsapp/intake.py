"""One signed delivery in, one durable record per message, at most one capture.

The destination for a capture is read only from the active sender link that
matches the HMAC of the signed ``from`` field. Message text, filenames and
captions never choose an owner, and a phone number typed in text proves
nothing. Captures are saved with ``consent=False``: AI preparation waits for
the owner's choice in the web app.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Protocol

from loguru import logger

from argus.domain.ingestion.whatsapp.identity import (
    WhatsAppKeys,
    code_candidates,
    last4,
    mint_code,
    ref,
)
from argus.domain.ingestion.whatsapp.media import (
    ACCEPTED_MEDIA_TYPES,
    FetchedMedia,
    MediaRejected,
    MediaUnavailable,
)
from argus.domain.ingestion.whatsapp.payload import (
    Delivery,
    InboundMessage,
    MediaMessage,
    TextMessage,
)
from argus.domain.ingestion.whatsapp.replies import (
    ReplyFailed,
    ReplyTransport,
    compose_reply,
    reply_key,
    reply_payload,
    review_url,
)
from argus.domain.ingestion.whatsapp.store import (
    RETRYABLE,
    SENDER_LINK_REVOKED,
    ReplyLanguage,
    Settlement,
    WhatsAppStore,
)

CLAIM_SECONDS = 90
# Processing must end, and settle, while its claim is still held.
PROCESSING_SECONDS = CLAIM_SECONDS - 15
CODE_TTL = timedelta(minutes=10)
SERVICE_WINDOW = timedelta(hours=24)


class DeliveryInFlight(Exception):
    """Another worker holds a live claim on an unsettled message; ask Meta to retry."""


class CaptureRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CaptureFailed(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Captured:
    connection_id: str
    already_held: bool


class IntakeDestination(Protocol):
    """Where a linked sender's receipt lands: the owner's Business space."""

    async def capture(
        self,
        *,
        owner_id: str,
        content: bytes,
        filename: str,
        media_type: str,
        source_text: str | None,
    ) -> Captured: ...

    async def discard(self, *, owner_id: str, connection_id: str) -> None: ...


class MediaSource(Protocol):
    async def fetch(self, media_id: str) -> FetchedMedia: ...


@dataclass(frozen=True)
class IssuedCode:
    code: str
    expires_at: datetime


@dataclass(frozen=True)
class _Held:
    """One message whose claim this worker holds."""

    message: InboundMessage
    sender: bytes
    key: bytes
    held: datetime | None
    log: Any


class WhatsAppIntake:
    def __init__(
        self,
        *,
        store: WhatsAppStore,
        keys: WhatsAppKeys,
        media: MediaSource,
        destination: IntakeDestination,
        clock: Callable[[], datetime],
        transport: ReplyTransport | None = None,
        app_origin: str | None = None,
        max_bytes: int,
        background: Callable[[Coroutine[Any, Any, None]], None] | None = None,
    ) -> None:
        self.store, self.keys, self.media = store, keys, media
        self.destination, self.clock = destination, clock
        self.transport, self.app_origin, self.max_bytes = transport, app_origin, max_bytes
        # With a runner, ``handle`` returns once every message has a committed
        # claim and the work runs behind the acknowledgement. Without one the
        # work finishes inside ``handle``.
        self.background = background
        self.processing_seconds: float = PROCESSING_SECONDS

    def issue_code(
        self, *, destination_owner_id: str, reply_language: ReplyLanguage
    ) -> IssuedCode:
        """A new single-use code; any earlier unused code for this owner stops working.

        ``reply_language`` is the web language the owner is using now. The link
        the code creates keeps it, and every WhatsApp reply uses it.
        """

        code = mint_code()
        now = self.clock()
        expires_at = now + CODE_TTL
        self.store.issue_code(
            destination_owner_id=destination_owner_id,
            code_digest=self.keys.code(code),
            reply_language=reply_language,
            now=now,
            expires_at=expires_at,
        )
        return IssuedCode(code, expires_at)

    async def handle(self, delivery: Delivery) -> None:
        logger.info(
            "WhatsApp delivery verified",
            messages=len(delivery.messages),
            ignored_messages=delivery.ignored_messages,
            statuses=delivery.statuses,
            other_numbers=delivery.other_numbers,
        )
        in_flight = False
        first_error: Exception | None = None
        held: list[_Held] = []
        for message in delivery.messages:
            try:
                claimed = await self._claim(message)
            except Exception as error:
                first_error = first_error or error
                continue
            if isinstance(claimed, _Held):
                held.append(claimed)
            else:
                in_flight = not claimed or in_flight
        if self.background is not None:
            if held:
                self.background(self._run(held))
        else:
            for item in held:
                try:
                    in_flight = not await self._process(item) or in_flight
                except Exception as error:
                    first_error = first_error or error
        if first_error is not None:
            raise first_error
        if in_flight:
            raise DeliveryInFlight()

    async def _run(self, held: list[_Held]) -> None:
        """Background work for claims already committed. A failure is settled
        by ``_process``; the sender is told to send it again."""

        for item in held:
            try:
                await self._process(item)
            except Exception:
                await self._reply(
                    item.message,
                    Settlement("failed", error_code="whatsapp_processing_failed"),
                    item.log,
                )

    async def _claim(self, message: InboundMessage) -> _Held | bool:
        """Commit this message's claim. A ``_Held`` means this worker owns it;
        otherwise ``True`` when it is already settled and ``False`` while
        another claim still holds it unsettled."""

        sender = self.keys.sender(message.sender)
        key = self.keys.message(message.id)
        now = self.clock()
        claim = await asyncio.to_thread(
            self.store.claim,
            provider_message_key=key,
            sender_hash=sender,
            now=now,
            claim_until=now + timedelta(seconds=CLAIM_SECONDS),
        )
        log = logger.bind(message_ref=ref(key), sender_ref=ref(sender))
        if not claim.claimed:
            log.info("WhatsApp message replayed", status=claim.record.status)
            return claim.record.status not in RETRYABLE
        return _Held(message, sender, key, claim.record.claim_until, log)

    async def _process(self, item: _Held) -> bool:
        """Finish one claimed message; ``False`` when the claim was lost first."""

        message, sender, key, held, log = (
            item.message,
            item.sender,
            item.key,
            item.held,
            item.log,
        )
        try:
            settlement = await asyncio.wait_for(
                self._decide(message, sender), timeout=self.processing_seconds
            )
        except Exception as error:
            code = (
                "whatsapp_processing_timeout"
                if isinstance(error, asyncio.TimeoutError)
                else "whatsapp_processing_failed"
            )
            await self._settle(key, held, Settlement("failed", error_code=code))
            log.warning("WhatsApp message failed", failure_mode=type(error).__name__)
            raise
        settled = await self._settle(key, held, settlement)
        if settled is None:
            log.warning("WhatsApp message claim lost before settling")
            return False
        if (
            settled.error_code == SENDER_LINK_REVOKED
            and settlement.connection_id is not None
            and not settlement.duplicate
        ):
            await self._discard(settlement, log)
        settlement = settled
        log.info(
            "WhatsApp message settled",
            status=settlement.status,
            error_code=settlement.error_code,
        )
        await self._reply(message, settlement, log)
        return True

    async def _discard(self, captured: Settlement, log) -> None:  # noqa: ANN001
        """The link ended while this receipt was being saved; the sender is
        told to send it again, so the new draft must not stay in the inbox."""

        try:
            await self.destination.discard(
                owner_id=captured.destination_owner_id or "",
                connection_id=captured.connection_id or "",
            )
            log.info("WhatsApp capture discarded after the link ended")
        except Exception as error:
            log.warning(
                "WhatsApp capture could not be discarded after the link ended",
                failure_mode=type(error).__name__,
            )

    async def _settle(
        self, key: bytes, held: datetime | None, settlement: Settlement
    ) -> Settlement | None:
        return await asyncio.to_thread(
            self.store.settle,
            provider_message_key=key,
            claim_until=held,
            settlement=settlement,
            now=self.clock(),
        )

    async def _decide(self, message: InboundMessage, sender: bytes) -> Settlement:
        link = await asyncio.to_thread(self.store.sender_link, sender_hash=sender)
        if link is None:
            return await self._unlinked(message, sender)
        owner, language = link.destination_owner_id, link.reply_language
        if isinstance(message, TextMessage):
            return Settlement(
                "rejected",
                owner,
                error_code="whatsapp_receipt_missing",
                reply_language=language,
            )
        settlement = await self._capture(message, owner)
        return replace(settlement, reply_language=language)

    async def _unlinked(self, message: InboundMessage, sender: bytes) -> Settlement:
        """A sender with no active link can only link: no word is read for
        meaning, a code-shaped token is looked up by digest."""

        tried = False
        if isinstance(message, TextMessage):
            for code in code_candidates(message.body):
                tried = True
                linked = await asyncio.to_thread(
                    self.store.redeem_code,
                    code_digest=self.keys.code(code),
                    sender_hash=sender,
                    last4=last4(message.sender),
                    now=self.clock(),
                )
                if linked is not None:
                    return Settlement(
                        "linked",
                        destination_owner_id=linked.destination_owner_id,
                        reply_language=linked.reply_language,
                    )
        return Settlement(
            "rejected",
            error_code="whatsapp_link_code_invalid"
            if tried
            else "whatsapp_sender_not_linked",
        )

    async def _capture(self, message: MediaMessage, owner: str) -> Settlement:
        if message.mime_type not in ACCEPTED_MEDIA_TYPES:
            return Settlement("rejected", owner, error_code="whatsapp_media_unsupported")
        try:
            fetched = await self.media.fetch(message.media_id)
            captured = await self.destination.capture(
                owner_id=owner,
                content=fetched.content,
                filename=message.filename,
                media_type=fetched.mime_type,
                source_text=message.caption,
            )
        except (MediaRejected, CaptureRejected) as error:
            return Settlement("rejected", owner, error_code=error.code)
        except (MediaUnavailable, CaptureFailed) as error:
            return Settlement("failed", owner, error_code=error.code)
        return Settlement(
            "captured",
            owner,
            captured.connection_id,
            duplicate=captured.already_held,
        )

    async def _reply(self, message: InboundMessage, settlement: Settlement, log) -> None:  # noqa: ANN001
        if self.transport is None:
            return
        if self.clock() - message.sent_at > SERVICE_WINDOW:
            log.info("WhatsApp acknowledgement skipped: outside the service window")
            return
        url = None
        if settlement.status == "captured":
            if not self.app_origin:
                log.warning("WhatsApp acknowledgement skipped: no app origin")
                return
            url = review_url(self.app_origin, settlement.connection_id or "")
        body = compose_reply(
            reply_key(
                settlement.status, settlement.error_code, duplicate=settlement.duplicate
            ),
            language=settlement.reply_language,
            link=url,
            limit_mb=self.max_bytes // (1024 * 1024),
        )
        try:
            await self.transport.send(
                reply_payload(to=message.sender, in_reply_to=message.id, body=body)
            )
        except ReplyFailed as error:
            log.warning("WhatsApp acknowledgement not sent", failure_mode=str(error))
