"""One signed delivery in, one durable record per message, at most one capture.

The destination for a capture is read only from the active sender link that
matches the HMAC of the signed ``from`` field. Message text, filenames and
captions never choose an owner, and a phone number typed in text proves
nothing. The Business destination applies the owner's receipt-reading choice.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from time import monotonic
from typing import Any, Protocol, TypeVar

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
    safe_graph_log_value,
)
from argus.domain.ingestion.whatsapp.payload import (
    Delivery,
    InboundMessage,
    MediaMessage,
    TextMessage,
    UnsupportedMessage,
)
from argus.domain.ingestion.whatsapp.replies import (
    ReplyFailed,
    ReplyTransport,
    compose_reply,
    inbox_url,
    reply_key,
    reply_payload,
    review_url,
)
from argus.domain.ingestion.whatsapp.reply_groups import (
    FAILURE_REASONS,
    PendingFailure,
    ReplyGroupCodec,
    suppressed,
)
from argus.domain.ingestion.whatsapp.store import (
    RETRYABLE,
    CapturePublisher,
    CaptureSource,
    ReplyLanguage,
    Settlement,
    WhatsAppStore,
)

CLAIM_SECONDS = 90
# Processing must end, and settle, while its claim is still held.
PROCESSING_SECONDS = CLAIM_SECONDS - 15
# While work runs, including a capture thread that outlives its cancellation,
# the claim is renewed this often, so it never lapses under a live worker.
RENEW_SECONDS = CLAIM_SECONDS / 3
CODE_TTL = timedelta(minutes=10)
SERVICE_WINDOW = timedelta(hours=24)
_Result = TypeVar("_Result")
_REPLY_REJECTION = re.compile(r"([1-5][0-9]{2})(?::([0-9]{1,10}))?")


class DeliveryInFlight(Exception):
    """Another worker holds a live claim on an unsettled message; ask Meta to retry."""


class CaptureRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CaptureFailed(Exception):
    def __init__(self, code: str, *, retry_delivery: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retry_delivery = retry_delivery


@dataclass(frozen=True)
class Captured:
    connection_id: str
    already_held: bool
    storage_user_id: str
    space_id: str | None
    # The receipt was queued for reading; the destination decides at capture.
    reading: bool = False
    previous_business_copy: bool = False


class IntakeDestination(CapturePublisher, Protocol):
    """Stage and publish receipts for the sender of a signed delivery."""

    def report_arrival(self, settled: Settlement) -> None: ...

    async def capture(
        self,
        *,
        owner_id: str,
        content: bytes,
        filename: str,
        media_type: str,
        source_text: str | None,
    ) -> Captured: ...




class MediaSource(Protocol):
    async def fetch(self, media_id: str) -> FetchedMedia: ...


@dataclass(frozen=True)
class IssuedCode:
    code: str
    expires_at: datetime


@dataclass
class _Lease:
    """The current fenced claim token; the heartbeat moves it forward."""

    held: datetime | None
    done: asyncio.Event = field(default_factory=asyncio.Event)


async def _bounded(task: asyncio.Task, timeout: float) -> Any:
    """``task``'s result within ``timeout`` seconds. On timeout or on the
    caller's cancellation the task is cancelled and awaited to its end, its
    cleanup included, before ``TimeoutError`` or the cancellation is raised.
    ``asyncio.wait_for`` cannot promise that: on Python 3.10 a second
    cancellation escapes it while the cancelled work is still running."""

    cancelled = False
    try:
        await asyncio.wait({task}, timeout=timeout)
    except asyncio.CancelledError:
        cancelled = True
    timed_out = not cancelled and not task.done()
    if not task.done():
        task.cancel()
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            cancelled = True
            task.cancel()
    if cancelled:
        raise asyncio.CancelledError
    if timed_out:
        raise asyncio.TimeoutError
    return task.result()


async def _finish(task: asyncio.Task[_Result]) -> _Result:
    """Wait for a started write even if the caller is cancelled."""

    cancelled = False
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        task.exception()
        raise asyncio.CancelledError
    return task.result()


async def _stop(lease: _Lease, task: asyncio.Task | None) -> None:
    """Let an in-flight renewal hand over its updated claim before stopping."""

    lease.done.set()
    if task is not None:
        await _finish(task)


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
        send_enabled: Callable[[], bool] = lambda: True,
        reply_codec: ReplyGroupCodec | None = None,
        reply_group_wait_seconds: int = 120,
    ) -> None:
        self.store, self.keys, self.media = store, keys, media
        self.destination, self.clock = destination, clock
        self.transport, self.app_origin, self.max_bytes = transport, app_origin, max_bytes
        self.processing_seconds: float = PROCESSING_SECONDS
        self.renew_seconds: float = RENEW_SECONDS
        self.send_enabled = send_enabled
        self.reply_codec = reply_codec
        self.reply_group_wait_seconds = reply_group_wait_seconds

    def issue_code(
        self, *, destination_owner_id: str, reply_language: ReplyLanguage, disclosure: str
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
            disclosure=disclosure,
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
        for failure in delivery.failures:
            logger.warning(
                f"WhatsApp outbound delivery failed: code={failure.code or 'unknown'} "
                f"reason={failure.reason}",
                event="whatsapp_delivery_failed",
                graph_code=failure.code,
                failure_reason=failure.reason,
            )
        in_flight = False
        first_error: Exception | None = None
        for message in delivery.messages:
            try:
                claimed = await self._claim(message)
                if isinstance(claimed, _Held):
                    in_flight = not await self._process(claimed) or in_flight
                else:
                    in_flight = not claimed or in_flight
            except Exception as error:
                first_error = first_error or error
        if first_error is not None:
            raise first_error
        if in_flight:
            raise DeliveryInFlight()

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
        lease = _Lease(held)
        if held is not None:
            # Confirm the claim is still ours before starting work.
            try:
                renewed = await self._renew(key, lease)
            except Exception as error:
                # An unproven lease stays silent until redelivery.
                log.warning(
                    "WhatsApp claim renewal failed before work",
                    failure_mode=type(error).__name__,
                )
                return False
            if not renewed:
                log.info("WhatsApp claim taken by another worker; skipped")
                return False
        # The work is a retained task: the documents service ends it only
        # once a cancelled capture thread has ended, and the heartbeat is
        # stopped only after that, even when this coroutine is cancelled, so
        # the claim is renewed for as long as the thread lives.
        heartbeat = (
            asyncio.create_task(self._heartbeat(key, lease)) if held is not None else None
        )
        deadline = monotonic() + self.processing_seconds
        work = asyncio.create_task(self._decide(message, sender))
        try:
            settlement = await _bounded(work, self.processing_seconds)
        except Exception as error:
            code = (
                "whatsapp_processing_timeout"
                if isinstance(error, asyncio.TimeoutError)
                else "whatsapp_processing_failed"
            )
            await _stop(lease, heartbeat)
            settled = await self._settle(
                key, lease.held, Settlement("failed", error_code=code)
            )
            log.warning("WhatsApp message failed", failure_mode=type(error).__name__)
            if settled is None:
                # Another worker owns the claim now; its outcome is the one
                # the sender hears, so this worker stays silent.
                log.warning("WhatsApp message claim lost before settling")
                return False
            raise
        except BaseException:
            await _stop(lease, heartbeat)
            raise
        await _stop(lease, heartbeat)
        held = lease.held
        failure = None
        if isinstance(message, MediaMessage) and settlement.error_code in FAILURE_REASONS:
            if self.reply_codec is None:
                raise RuntimeError("whatsapp_reply_grouping_unavailable")
            link = await asyncio.to_thread(self.store.sender_link, sender_hash=sender)
            if link is not None and link.authorizes(settlement):
                failure = self.reply_codec.failure(
                    message, link, now=self.clock(), wait=self.reply_group_wait_seconds
                )
        settled = await self._settle(
            key, held, settlement, reply_failure=failure, deadline=deadline
        )
        if settled is None:
            log.warning("WhatsApp message claim lost before settling")
            return False
        settlement = settled
        if settlement.report_arrival:
            self.destination.report_arrival(settlement)
        log.info(
            "WhatsApp message settled",
            status=settlement.status,
            error_code=settlement.error_code,
        )
        if failure is not None:
            log.info(
                "WhatsApp failed file grouped",
                event="whatsapp_file_failure",
                reason=FAILURE_REASONS[settlement.error_code],
            )
        await self._reply(message, settlement, log)
        return True

    async def _renew(self, key: bytes, lease: _Lease) -> bool:
        assert lease.held is not None
        now = self.clock()
        renewed = await asyncio.to_thread(
            self.store.renew,
            provider_message_key=key,
            held=lease.held,
            now=now,
            claim_until=now + timedelta(seconds=CLAIM_SECONDS),
        )
        if renewed is None:
            return False
        lease.held = renewed
        return True

    async def _heartbeat(self, key: bytes, lease: _Lease) -> None:
        """Keep the fenced claim alive until cancelled. Once a renewal loses,
        the stale token makes settlement fail its compare-and-set."""

        while True:
            try:
                await asyncio.wait_for(lease.done.wait(), self.renew_seconds)
                return
            except asyncio.TimeoutError:
                pass
            try:
                if not await self._renew(key, lease):
                    return
            except Exception as error:
                logger.warning(
                    "WhatsApp claim renewal failed", failure_mode=type(error).__name__
                )

    async def _settle(
        self,
        key: bytes,
        held: datetime | None,
        settlement: Settlement,
        *,
        reply_failure: PendingFailure | None = None,
        deadline: float | None = None,
    ) -> Settlement | None:
        return await _finish(
            asyncio.create_task(
                asyncio.to_thread(
                    self.store.settle,
                    provider_message_key=key,
                    claim_until=held,
                    settlement=settlement,
                    now=self.clock,
                    reply_failure=reply_failure,
                    publisher=self.destination if settlement.status == "captured" else None,
                    deadline=deadline,
                )
            )
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
                sender_link_id=link.id,
            )
        if isinstance(message, UnsupportedMessage):
            return Settlement(
                "rejected",
                owner,
                error_code="whatsapp_message_unsupported",
                reply_language=language,
                sender_link_id=link.id,
            )
        settlement = await self._capture(message, owner)
        return replace(settlement, reply_language=language, sender_link_id=link.id)

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
                        sender_link_id=linked.id,
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
            for attempt in range(2):
                try:
                    captured = await self.destination.capture(
                        owner_id=owner,
                        content=fetched.content,
                        filename=message.filename,
                        media_type=fetched.mime_type,
                        source_text=message.caption,
                    )
                    break
                except CaptureFailed as error:
                    if attempt:
                        if error.retry_delivery:
                            raise
                        return Settlement(
                            "rejected", owner, error_code="whatsapp_capture_failed"
                        )
                    await asyncio.sleep(0.25)
        except (MediaRejected, CaptureRejected) as error:
            return Settlement("rejected", owner, error_code=error.code)
        except MediaUnavailable as error:
            return Settlement("failed", owner, error_code=error.code)
        return Settlement(
            "captured",
            owner,
            captured.connection_id,
            duplicate=captured.already_held,
            previous_business_copy=captured.previous_business_copy,
            original=CaptureSource(fetched.content, message.filename, fetched.mime_type, message.caption),
            reading=captured.reading,
            storage_user_id=captured.storage_user_id,
            space_id=captured.space_id,
        )

    async def _reply(
        self,
        message: InboundMessage,
        settlement: Settlement,
        log,  # noqa: ANN001
    ) -> None:
        resolved_key = reply_key(
            settlement.status,
            settlement.error_code,
            duplicate=settlement.duplicate,
            reading=settlement.reading,
        )
        if resolved_key == "whatsapp_sender_not_linked":
            return
        sender = self.keys.sender(message.sender)
        if resolved_key != "whatsapp_link_code_invalid":
            current = await asyncio.to_thread(self.store.sender_link, sender_hash=sender)
            if current is None or not current.authorizes(settlement):
                suppressed("unknown_sender", sender)
                return
        if settlement.error_code in FAILURE_REASONS:
            return
        if self.transport is None or not self.send_enabled():
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
        elif settlement.error_code == "whatsapp_receipt_missing" and self.app_origin:
            url = inbox_url(self.app_origin)
        body = compose_reply(
            resolved_key,
            language=settlement.reply_language,
            link=url,
            limit_mb=self.max_bytes // (1024 * 1024),
        )
        if resolved_key in ("linked", "whatsapp_link_code_invalid"):
            reserved = await asyncio.to_thread(
                self.store.reserve_unlinked_reply,
                sender_hash=sender,
                provider_message_key=self.keys.message(message.id),
                now=self.clock(),
            )
            if not reserved:
                suppressed("unlinked_daily_limit", sender)
                return
        try:
            await self.transport.send(
                reply_payload(to=message.sender, in_reply_to=message.id, body=body)
            )
        except ReplyFailed as error:
            reason = (
                error.args[0] if error.args and isinstance(error.args[0], str) else ""
            )
            rejection = _REPLY_REJECTION.fullmatch(reason)
            failure_mode = (
                "transport"
                if reason == "transport"
                else "provider_rejection"
                if rejection
                else "unknown"
            )
            outcome = "unknown" if error.outcome_unknown is True else "known"
            diagnostics: dict[str, str | int] = {
                "failure_mode": failure_mode,
                "outcome": outcome,
            }
            if rejection:
                diagnostics["http_status"] = int(rejection.group(1))
                if rejection.group(2):
                    diagnostics["graph_code"] = safe_graph_log_value(
                        "graph_code", rejection.group(2)
                    )
            rendered = " ".join(f"{name}={value}" for name, value in diagnostics.items())
            log.warning(f"WhatsApp acknowledgement not sent: {rendered}", **diagnostics)
        else:
            log.info(
                "WhatsApp acknowledgement sent",
                event="whatsapp_reply",
                reply_key=resolved_key,
            )
