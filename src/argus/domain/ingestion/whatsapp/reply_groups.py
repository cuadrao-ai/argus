from __future__ import annotations

import base64
import hmac
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from loguru import logger

from argus.domain.ingestion.secrets import SecretBox, SecretUnreadable
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys, ref
from argus.domain.ingestion.whatsapp.payload import InboundMessage, MediaMessage
from argus.domain.ingestion.whatsapp.replies import compose_reply, reply_payload
from argus.domain.ingestion.whatsapp.store import SenderLink

FAILURE_REASONS = {
    "whatsapp_media_invalid": "blocked",
    "whatsapp_media_unsupported": "unsupported_type",
    "whatsapp_media_too_large": "too_large",
    "whatsapp_capture_failed": "capture_failed",
    "whatsapp_media_expired": "download_failed",
    "whatsapp_media_unavailable": "download_failed",
    "whatsapp_media_untrusted": "download_failed",
}
DUE_EVERY = timedelta(minutes=1)
WINDOW = timedelta(hours=24)
SEND_TIMEOUT = 15
ATTEMPT_TTL = timedelta(seconds=60)


def suppressed(reason: str, sender_hash: bytes) -> None:
    logger.info(
        "WhatsApp reply suppressed",
        event="whatsapp_reply_suppressed",
        metric_name="whatsapp_reply_suppressed",
        metric_type="counter",
        metric_value=1,
        reason=reason,
        sender_ref=ref(sender_hash),
    )


# An ordinary file extension can appear in a label. Check the filename stem
# separately so a URL disguised as "example.com.pdf" still gets a time label.
_LINK = re.compile(
    r"(?i)(?:[a-z][a-z0-9+.-]*://|www\.|mailto:|tel:|\b[^\s.]+\.(?:[a-z]{2,}|xn--[a-z0-9-]+)\b|\b(?:\d{1,3}\.){3}\d{1,3}\b)"
)
_FILE_EXT = re.compile(
    r"(?i)\.(?:pdf|jpe?g|png|webp|gif|tiff?|heic|zip|docx?|xlsx?|csv|txt)$"
)


def _clean_label(value: str) -> str:
    return "".join(
        c
        for c in value
        if not unicodedata.category(c).startswith("C") and c not in "\u2028\u2029"
    ).strip()


def file_label(message: MediaMessage, *, language: str | None = None) -> str:
    name = _clean_label(message.filename)
    if name in {"whatsapp-image", "whatsapp-document"}:
        name = ""
    if name and not _LINK.search(_FILE_EXT.sub("", name)):
        return name if len(name) <= 30 else name[:29] + "…"
    return _time_label(
        message.sent_at, language=language, photo=message.mime_type.startswith("image/")
    )


def _time_label(sent_at: datetime, *, language: str | None, photo: bool) -> str:
    at = sent_at.astimezone(ZoneInfo("America/Santo_Domingo"))
    clock = f"{at.hour % 12 or 12}:{at.minute:02d} {'a. m.' if at.hour < 12 else 'p. m.'}"
    if language == "en":
        noun = "photo" if photo else "file"
        return f"{noun} sent at {at.hour % 12 or 12}:{at.minute:02d} {'a.m.' if at.hour < 12 else 'p.m.'}"
    noun = "foto enviada" if photo else "archivo enviado"
    return f"{noun} a las {clock}"


@dataclass(frozen=True)
class PendingFailure:
    sender_hash: bytes
    owner_id: str
    linked_at: datetime
    sent_at: datetime
    sample: dict[str, str]


@dataclass(frozen=True)
class ReplyGroup:
    sender_hash: bytes
    owner_id: str
    link_id: str
    count: int
    samples: list[dict[str, str]]
    last_sent_at: datetime
    send_after: datetime
    retries: int = 0
    kind: str = "files"
    last_arrival: datetime | None = None
    group_id: UUID | None = None


@dataclass(frozen=True)
class BatchOutcomes:
    businesses: tuple[tuple[str, int], ...] = ()
    held: int = 0
    duplicates: int = 0
    not_received: int = 0
    reading: int = 0
    read_tomorrow: int = 0
    failure_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReplyAttempt:
    token: str
    group: ReplyGroup
    final: bool
    outcomes: BatchOutcomes = BatchOutcomes()
    failures_suppressed: bool = False


class ReplyGroupCodec:
    def __init__(self, box: SecretBox, keys: WhatsAppKeys) -> None:
        self.box, self.keys = box, keys

    def pending(
        self, message: InboundMessage, link: SenderLink
    ) -> PendingFailure:
        key = self.keys.message(message.id).hex()
        media = isinstance(message, MediaMessage)
        payload = json.dumps(
            {
                "sender": message.sender,
                "message_id": message.id,
                "label": file_label(message, language=link.reply_language)
                if media
                else "",
                "language": link.reply_language,
            }
        )
        sealed = self.box.seal(payload, source="whatsapp-reply", connection_id=key)
        return PendingFailure(
            self.keys.sender(message.sender),
            link.destination_owner_id,
            link.linked_at,
            message.sent_at,
            {
                "at": message.sent_at.astimezone(timezone.utc).isoformat(),
                "key": key,
                "sealed": base64.b64encode(sealed).decode("ascii"),
                "kind": "files" if media else "guidance",
            },
        )

    def payload(self, attempt: ReplyAttempt) -> dict[str, Any]:
        group = attempt.group
        opened = {}
        for sample in group.samples:
            payload = json.loads(
                self.box.open(
                    base64.b64decode(sample["sealed"]),
                    source="whatsapp-reply",
                    connection_id=sample["key"],
                )
            )
            if not hmac.compare_digest(
                self.keys.sender(payload["sender"]), group.sender_hash
            ):
                raise SecretUnreadable("whatsapp_reply_sender_mismatch")
            if not hmac.compare_digest(
                self.keys.message(payload["message_id"]).hex(), sample["key"]
            ):
                raise SecretUnreadable("whatsapp_reply_message_mismatch")
            # Envelopes already queued before W11 can still carry URL filenames.
            if _LINK.search(_FILE_EXT.sub("", payload["label"])):
                payload["label"] = _time_label(
                    datetime.fromisoformat(sample["at"]),
                    language=payload["language"],
                    photo=False,
                )
            opened[sample["key"]] = payload
        first = next(iter(opened.values()))
        language = first["language"]
        if group.kind == "guidance":
            body = compose_reply("whatsapp_receipt_missing", language=language)
        else:
            labels = [opened[key]["label"] for key in attempt.outcomes.failure_keys]
            body = _summary(attempt, language, labels)
        return reply_payload(
            to=first["sender"],
            in_reply_to=first["message_id"] if group.count == 1 else None,
            body=body,
        )


def _summary(attempt: ReplyAttempt, language: str, labels: list[str]) -> str:
    counts, total = attempt.outcomes, attempt.group.count

    def line(key: str, n: int = 0, *, singular: bool = False, **values: str | int) -> str:
        if singular:
            key += "_one"
        return compose_reply(key, language=language, n=n, **values)

    if total == 1 and counts.duplicates == 1:
        return line("duplicate")

    lines = []
    if counts.not_received < total:
        lines.append(line("batch_received", total, singular=total == 1))
    if counts.businesses:
        inbox_total = sum(n for _, n in counts.businesses)
        lines.append(line("batch_in_inbox", singular=inbox_total == 1))
        businesses = sorted(counts.businesses, key=lambda item: (-item[1], item[0]))
        displayed = 0
        displayed_files = 0
        for name, n in businesses:
            label = _clean_label(name)
            if label and not _LINK.search(label) and displayed < 5:
                lines.append(line("batch_business_line", n, business=label))
                displayed += 1
                displayed_files += n
        extra = len(businesses) - displayed
        if extra:
            lines.append(
                line(
                    "batch_more_businesses",
                    inbox_total - displayed_files,
                    singular=extra == 1,
                    k=extra,
                )
            )
    if counts.held:
        lines.append(line("batch_held", counts.held, singular=counts.held == 1))
    if counts.duplicates:
        lines.append(
            line("batch_duplicates", counts.duplicates, singular=counts.duplicates == 1)
        )
    if counts.not_received and not attempt.failures_suppressed:
        if attempt.final:
            lines.append(line("daily_cap"))
        else:
            single = counts.not_received == 1
            lines.append(
                line("not_received_header", counts.not_received, singular=single)
            )
            lines.extend(f"• {label}" for label in labels[:3])
            if labels and counts.not_received > len(labels):
                lines.append(line("not_received_more", counts.not_received - len(labels)))
            lines.append(line("not_received_closing", singular=single))
    if counts.read_tomorrow:
        lines.append(line("batch_read_tomorrow", counts.read_tomorrow))
    if counts.reading:
        lines.append(line("batch_reading_follow", singular=counts.reading == 1))
    return "\n".join(lines)
