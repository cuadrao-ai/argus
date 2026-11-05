"""Which attachment parts are fetched, and how their bytes are checked.

Only PDF, CSV and common image types declared by the message are fetched, and
only when Gmail reports a size within ``MAX_ATTACHMENT_BYTES``; a larger part
is never downloaded. Fetched bytes must match the declared type's file
signature, are hashed (SHA-256) and measured, and are then dropped: this wave
emits ``Attachment`` references only. Reading statement files belongs to the
document-import path, which does not exist yet; until it does, the reference
lets the person and that future path find the file in Gmail again.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.gmail.mime import AttachmentPart

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS = 10

SkipReason = Literal[
    "media_type", "too_large", "empty", "signature", "limit", "unreadable"
]


def _pdf(data: bytes) -> bool:
    return data[:1024].lstrip(b"\r\n\t ").startswith(b"%PDF-")


def _csv(data: bytes) -> bool:
    return b"\x00" not in data[:65536]


def _png(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n")


def _jpeg(data: bytes) -> bool:
    return data.startswith(b"\xff\xd8\xff")


def _gif(data: bytes) -> bool:
    return data[:6] in (b"GIF87a", b"GIF89a")


def _webp(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


SIGNATURES: dict[str, Callable[[bytes], bool]] = {
    "application/pdf": _pdf,
    "text/csv": _csv,
    "image/png": _png,
    "image/jpeg": _jpeg,
    "image/gif": _gif,
    "image/webp": _webp,
}


@dataclass(frozen=True)
class AttachmentDecision:
    part: AttachmentPart
    skip: SkipReason | None


def admissible(parts: tuple[AttachmentPart, ...]) -> list[AttachmentDecision]:
    """Decide from metadata alone, before any byte is downloaded."""

    decisions: list[AttachmentDecision] = []
    accepted = 0
    for part in parts:
        reason: SkipReason | None = None
        if part.media_type not in SIGNATURES:
            reason = "media_type"
        elif part.size > MAX_ATTACHMENT_BYTES:
            reason = "too_large"
        elif part.size == 0:
            reason = "empty"
        elif accepted >= MAX_ATTACHMENTS:
            reason = "limit"
        else:
            accepted += 1
        decisions.append(AttachmentDecision(part, reason))
    return decisions


def reference(
    message_id: str, part: AttachmentPart, data: bytes
) -> Attachment | SkipReason:
    if len(data) > MAX_ATTACHMENT_BYTES:
        return "too_large"
    if not data:
        return "empty"
    if not SIGNATURES[part.media_type](data):
        return "signature"
    return Attachment(
        external_id=f"{message_id}:{part.part_id}",
        media_type=part.media_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        filename=part.filename,
    )
