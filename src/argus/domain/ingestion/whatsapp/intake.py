"""One signed delivery in, one durable record per message, at most one capture.

The destination for a capture is read only from the active sender link that
matches the HMAC of the signed ``from`` field. Message text, filenames and
captions never choose an owner, and a phone number typed in text proves
nothing. Captures are saved with ``consent=False``: AI preparation waits for
the owner's choice in the web app.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Protocol

from loguru import logger

from argus.domain.ingestion.secrets import SecretUnreadable
from argus.domain.ingestion.whatsapp.business_envelope import ClaimCodec
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
    SENDER_LINK_REVOKED,
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
# A lapsed claim is run again at most this many times before it settles
# failed and the sender is asked to send the photo again.
RECOVERY_ATTEMPTS = 3
# Webhook traffic also runs the sweep, at most once per this many seconds per
# process, so recovery does not wait on any background job switch.
RECOVERY_NUDGE_SECONDS = 60
RECOVERY_NUDGE_LIMIT = 5
PHOTO_LOST = "whatsapp_photo_lost"
CODE_TTL = timedelta(minutes=10)
SERVICE_WINDOW = timedelta(hours=24)
_REPLY_REJECTION = re.compile(r"([1-5][0-9]{2})(?::([0-9]{1,10}))?")


class DeliveryInFlight(Exception):
    """Another worker holds a live claim on an unsettled message; ask Meta to retry."""


class ClaimNotSealed(Exception):
    """A photo whose recovery envelope could not be sealed is not acknowledged:
    the webhook answers 503 and the provider redelivers it."""


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
    # The receipt was queued and will be read inline right after the
    # acknowledgement. The destination decides it once at capture time; the
    # acknowledgement and the follow-up both read it, never recompute it.
    reading: bool = False


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

    async def read(
        self, *, owner_id: str, connection_id: str
    ) -> tuple[str, dict[str, str] | None] | None:
        """Read the saved receipt when the owner allows it: the draft's status
        once settled and the one merchant, amount and currency it found if any,
        else ``None``."""
        ...


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


async def _stop(lease: _Lease, task: asyncio.Task | None) -> None:
    """Stop the heartbeat between renewals, never inside one: a renewal cut
    off mid-write would move the claim without moving ``lease.held``. The
    heartbeat itself is never cancelled, so a renewal in flight always hands
    its token to ``lease.held``."""

    lease.done.set()
    cancelled = False
    while task is not None and not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError


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
        capture_text: Callable[[TextMessage], bool] | None = None,
        send_enabled: Callable[[], bool] = lambda: True,
        background: Callable[[Coroutine[Any, Any, None]], None] | None = None,
        reply_codec: ReplyGroupCodec | None = None,
        reply_group_wait_seconds: int = 120,
        claim_codec: ClaimCodec | None = None,
    ) -> None:
        self.store, self.keys, self.media = store, keys, media
        self.destination, self.clock = destination, clock
        self.transport, self.app_origin, self.max_bytes = transport, app_origin, max_bytes
        # With a runner, ``handle`` returns once every message has a committed
        # claim and the work runs behind the acknowledgement. Without one the
        # work finishes inside ``handle``.
        self.background = background
        self.processing_seconds: float = PROCESSING_SECONDS
        self.renew_seconds: float = RENEW_SECONDS
        self.capture_text = capture_text
        self.send_enabled = send_enabled
        self.reply_codec = reply_codec
        self.reply_group_wait_seconds = reply_group_wait_seconds
        self.claim_codec = claim_codec
        self._last_nudge: datetime | None = None

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
            self._nudge_recovery()
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
                await self._process(item, background=True)
            except Exception as error:
                # Only a fenced failure settlement may tell the sender; an
                # unsettled claim lapses and the sweep runs it again.
                item.log.warning(
                    "WhatsApp message left unsettled", failure_mode=type(error).__name__
                )

    async def _claim(self, message: InboundMessage) -> _Held | bool:
        """Commit this message's claim. A ``_Held`` means this worker owns it;
        otherwise ``True`` when it is already settled and ``False`` while
        another claim still holds it unsettled."""

        if isinstance(message, TextMessage) and self.capture_text is not None:
            if await asyncio.to_thread(self.capture_text, message):
                return True
        sender = self.keys.sender(message.sender)
        key = self.keys.message(message.id)
        try:
            envelope = self._seal(message)
        except ClaimNotSealed:
            # A replay of a message already settled needs no envelope.
            record = await asyncio.to_thread(self.store.inbound, key)
            if record is not None and record.status not in RETRYABLE:
                return True
            raise
        now = self.clock()
        claim = await asyncio.to_thread(
            self.store.claim,
            provider_message_key=key,
            sender_hash=sender,
            now=now,
            claim_until=now + timedelta(seconds=CLAIM_SECONDS),
            claim_envelope=envelope,
        )
        log = logger.bind(message_ref=ref(key), sender_ref=ref(sender))
        if not claim.claimed:
            log.info("WhatsApp message replayed", status=claim.record.status)
            return claim.record.status not in RETRYABLE
        return _Held(message, sender, key, claim.record.claim_until, log)

    def _seal(self, message: InboundMessage) -> bytes | None:
        """A photo is acknowledged only once its envelope is sealed, so a lost
        worker can always fetch it again. Text stays best effort."""

        required = isinstance(message, MediaMessage)
        if self.claim_codec is None:
            if required:
                logger.warning("WhatsApp claim codec missing; photo not acknowledged")
                raise ClaimNotSealed("whatsapp_claim_codec_unavailable")
            return None
        try:
            return self.claim_codec.seal(message)
        except Exception as error:
            logger.warning(
                "WhatsApp claim envelope not sealed",
                failure_mode=type(error).__name__,
                acknowledged=not required,
            )
            if required:
                raise ClaimNotSealed("whatsapp_claim_not_sealed") from error
            return None

    def _nudge_recovery(self) -> None:
        now = self.clock()
        if self._last_nudge is not None and now - self._last_nudge < timedelta(
            seconds=RECOVERY_NUDGE_SECONDS
        ):
            return
        self._last_nudge = now
        assert self.background is not None
        self.background(self.recover(limit=RECOVERY_NUDGE_LIMIT))

    async def recover(self, *, limit: int = 20) -> int:
        """Run again every message whose claim lapsed unsettled, through the
        same path as the original task. A retake is a compare-and-set on the
        lapsed claim, so a concurrent sweep or a live original task never runs
        the same message twice. Returns how many claims this call took."""

        now = self.clock()
        lapsed = await asyncio.to_thread(self.store.lapsed_claims, now=now, limit=limit)
        taken = 0
        for record in lapsed:
            try:
                taken += await self._recover_one(record)
            except Exception as error:
                logger.warning(
                    "WhatsApp claim recovery failed", failure_mode=type(error).__name__
                )
        return taken

    async def _recover_one(self, record: Any) -> bool:
        assert record.claim_until is not None
        key, sender = record.provider_message_key, record.sender_hash
        # The clock is read per item: a sweep-start time would hand later items
        # a lease that has already run out.
        now = self.clock()
        held = await asyncio.to_thread(
            self.store.retake,
            provider_message_key=key,
            held=record.claim_until,
            now=now,
            claim_until=now + timedelta(seconds=CLAIM_SECONDS),
        )
        if held is None:
            return False
        log = logger.bind(message_ref=ref(key), sender_ref=ref(sender))
        message = self._open(record)
        if message is None:
            await self._settle(
                key,
                held,
                Settlement("failed", error_code="whatsapp_claim_envelope_missing"),
            )
            log.warning("WhatsApp lapsed claim had no envelope; settled failed")
            return True
        if record.recovery_attempts >= RECOVERY_ATTEMPTS:
            settled = await self._settle(
                key, held, Settlement("failed", error_code="whatsapp_recovery_exhausted")
            )
            log.warning("WhatsApp lapsed claim gave up after bounded retries")
            if settled is not None and isinstance(message, MediaMessage):
                link = await asyncio.to_thread(self.store.sender_link, sender_hash=sender)
                if link is not None:
                    await self._reply(
                        message,
                        replace(settled, reply_language=link.reply_language),
                        log,
                        key=PHOTO_LOST,
                    )
            return True
        log.info("WhatsApp lapsed claim recovered", attempt=record.recovery_attempts + 1)
        await self._run([_Held(message, sender, key, held, log)])
        return True

    def _open(self, record: Any) -> InboundMessage | None:
        if record.claim_envelope is None or self.claim_codec is None:
            return None
        try:
            return self.claim_codec.open(
                record.claim_envelope,
                message_key=record.provider_message_key,
                sender_hash=record.sender_hash,
            )
        except (SecretUnreadable, ValueError):
            return None

    async def _process(self, item: _Held, *, background: bool = False) -> bool:
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
            # Renew right before the work: an earlier item in this batch may
            # have used up the lease, and a fetch must never run on a lapsed one.
            try:
                renewed = await self._renew(key, lease)
            except Exception as error:
                # An unproven lease stays silent; the sweep retries the claim.
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
            if background:
                await self._reply(
                    message,
                    Settlement("failed", error_code="whatsapp_processing_failed"),
                    log,
                )
                return True
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
            if (
                link is not None
                and link.destination_owner_id == settlement.destination_owner_id
            ):
                failure = self.reply_codec.failure(
                    message, link, now=self.clock(), wait=self.reply_group_wait_seconds
                )
        settled = await self._settle(key, held, settlement, reply_failure=failure)
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
        if failure is not None:
            log.info(
                "WhatsApp failed file grouped",
                event="whatsapp_file_failure",
                reason=FAILURE_REASONS[settlement.error_code],
            )
        await self._reply(message, settlement, log)
        await self._followup(message, settlement, log)
        return True

    async def _followup(
        self, message: InboundMessage, settlement: Settlement, log
    ) -> None:  # noqa: ANN001
        """One more message, once the receipt is read: where it stands. Best
        effort. A ``reading`` acknowledgement promised the link, so when the
        read does not settle or the follow-up does not go out, the standard
        acknowledgement with the link stands in; every other acknowledgement
        already carried it."""

        if settlement.status != "captured" or settlement.duplicate:
            return
        sent = False
        try:
            result = await self.destination.read(
                owner_id=settlement.destination_owner_id or "",
                connection_id=settlement.connection_id or "",
            )
            if result is None or result[0] not in ("review_ready", "needs_attention"):
                reason = {"status": None if result is None else result[0]}
            else:
                status, found = result
                if status == "needs_attention":
                    key = "read_attention"
                else:
                    key = "read_summary" if found else "read_ready"
                sent = await self._reply(message, settlement, log, key=key, read=found)
                reason = {"status": status, "follow_up": "not_sent"}
        except Exception as error:
            reason = {"failure_mode": getattr(error, "code", type(error).__name__)}
            log.warning("WhatsApp receipt read follow-up skipped", **reason)
        if settlement.reading and not sent:
            log.warning(
                "WhatsApp receipt acknowledged as reading but no follow-up was sent",
                **reason,
            )
            await self._reply(message, settlement, log, key="captured")

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
    ) -> Settlement | None:
        return await asyncio.to_thread(
            self.store.settle,
            provider_message_key=key,
            claim_until=held,
            settlement=settlement,
            now=self.clock(),
            reply_failure=reply_failure,
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
        if isinstance(message, UnsupportedMessage):
            return Settlement(
                "rejected",
                owner,
                error_code="whatsapp_message_unsupported",
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
                except CaptureFailed:
                    if attempt:
                        return Settlement(
                            "rejected", owner, error_code="whatsapp_capture_failed"
                        )
                    await asyncio.sleep(0.25)
        except (MediaRejected, CaptureRejected) as error:
            return Settlement("rejected", owner, error_code=error.code)
        except (MediaUnavailable, CaptureFailed) as error:
            return Settlement("failed", owner, error_code=error.code)
        return Settlement(
            "captured",
            owner,
            captured.connection_id,
            duplicate=captured.already_held,
            reading=captured.reading,
        )

    async def _reply(
        self,
        message: InboundMessage,
        settlement: Settlement,
        log,  # noqa: ANN001
        key: str | None = None,
        read: dict[str, str] | None = None,
    ) -> bool:
        """``True`` when the message went out."""

        resolved_key = key or reply_key(
            settlement.status,
            settlement.error_code,
            duplicate=settlement.duplicate,
            reading=settlement.reading,
        )
        if resolved_key == "whatsapp_sender_not_linked":
            suppressed("unknown_sender", self.keys.sender(message.sender))
            return False
        if (
            resolved_key != "whatsapp_link_code_invalid"
            and await asyncio.to_thread(
                self.store.sender_link, sender_hash=self.keys.sender(message.sender)
            )
            is None
        ):
            suppressed("unknown_sender", self.keys.sender(message.sender))
            return False
        if settlement.error_code in FAILURE_REASONS:
            return False
        if self.transport is None or not self.send_enabled():
            return False
        if self.clock() - message.sent_at > SERVICE_WINDOW:
            log.info("WhatsApp acknowledgement skipped: outside the service window")
            return False
        url = None
        if settlement.status == "captured":
            if not self.app_origin:
                log.warning("WhatsApp acknowledgement skipped: no app origin")
                return False
            url = review_url(self.app_origin, settlement.connection_id or "")
        elif settlement.error_code == "whatsapp_receipt_missing" and self.app_origin:
            url = inbox_url(self.app_origin)
        body = compose_reply(
            resolved_key,
            language=settlement.reply_language,
            link=url,
            limit_mb=self.max_bytes // (1024 * 1024),
            read=read,
        )
        try:
            await self.transport.send(
                reply_payload(to=message.sender, in_reply_to=message.id, body=body)
            )
            return True
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
            return False
