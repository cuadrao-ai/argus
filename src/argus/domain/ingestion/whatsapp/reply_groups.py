from __future__ import annotations

import base64
import hmac
import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger

from argus.domain.ingestion.secrets import SecretBox, SecretUnreadable
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys, ref
from argus.domain.ingestion.whatsapp.payload import MediaMessage
from argus.domain.ingestion.whatsapp.replies import compose_reply, reply_payload
from argus.domain.ingestion.whatsapp.store import SenderLink

FAILURE_REASONS = {
    "whatsapp_media_invalid": "blocked",
    "whatsapp_media_unsupported": "unsupported_type",
    "whatsapp_media_too_large": "too_large",
    "whatsapp_capture_failed": "capture_failed",
}
FINAL_REPLY = (
    "Hoy no responderemos más sobre archivos que no podamos leer. "
    "Los recibos válidos siguen entrando."
)
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


def file_label(message: MediaMessage) -> str:
    name = message.filename
    if name in {"whatsapp-image", "whatsapp-document"}:
        name = ""
    name = "".join(
        char
        for char in name
        if not unicodedata.category(char).startswith("C") and char not in "\u2028\u2029"
    ).strip()
    if name:
        return name if len(name) <= 30 else name[:29] + "…"
    at = message.sent_at.astimezone(ZoneInfo("America/Santo_Domingo"))
    clock = f"{at.hour % 12 or 12}:{at.minute:02d} {'a. m.' if at.hour < 12 else 'p. m.'}"
    noun = "foto enviada" if message.mime_type.startswith("image/") else "archivo enviado"
    return f"{noun} a las {clock}"


@dataclass(frozen=True)
class PendingFailure:
    sender_hash: bytes
    owner_id: str
    linked_at: datetime
    sent_at: datetime
    send_after: datetime
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


@dataclass(frozen=True)
class ReplyAttempt:
    token: str
    group: ReplyGroup
    final: bool


def earliest(samples: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(samples, key=lambda sample: sample["at"])[:3]


class ReplyGroupCodec:
    def __init__(self, box: SecretBox, keys: WhatsAppKeys) -> None:
        self.box, self.keys = box, keys

    def failure(
        self, message: MediaMessage, link: SenderLink, *, now: datetime, wait: int
    ) -> PendingFailure:
        key = self.keys.message(message.id).hex()
        payload = json.dumps(
            {
                "sender": message.sender,
                "message_id": message.id,
                "label": file_label(message),
                "language": link.reply_language,
            }
        )
        sealed = self.box.seal(payload, source="whatsapp-reply", connection_id=key)
        return PendingFailure(
            self.keys.sender(message.sender),
            link.destination_owner_id,
            link.linked_at,
            message.sent_at,
            now + timedelta(seconds=wait),
            {
                "at": message.sent_at.astimezone(timezone.utc).isoformat(),
                "key": key,
                "sealed": base64.b64encode(sealed).decode("ascii"),
            },
        )

    def payload(self, attempt: ReplyAttempt) -> dict[str, Any]:
        group = attempt.group
        opened = []
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
            opened.append(payload)
        first = opened[0]
        if attempt.final:
            body = FINAL_REPLY
        elif first["language"] == "en" or group.count == 1:
            body = compose_reply("whatsapp_media_invalid", language=first["language"])
        else:
            lines = [f"No pudimos leer {group.count} archivos:"]
            lines.extend(f"• {item['label']}" for item in opened)
            if group.count > len(opened):
                lines.append(f"• y {group.count - len(opened)} más")
            lines.append("Envíalos como foto o PDF.")
            body = "\n".join(lines)
        return reply_payload(
            to=first["sender"],
            in_reply_to=first["message_id"] if group.count == 1 else None,
            body=body,
        )
