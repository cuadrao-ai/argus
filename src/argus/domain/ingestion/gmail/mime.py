"""Gmail's ``format=full`` message resource to a bounded, inert ``ParsedEmail``.

Gmail has already split the MIME tree and undone transfer encodings; this
module walks that tree with hard limits (depth, part count, decoded text
size), decodes headers and part parameters with the standard ``email``
package (``policy.default``: RFC 2047 words, RFC 2231 file names, charsets)
and turns HTML into text without rendering it. Attachment parts are described
(media type, size, file name, Gmail attachment id); their bytes are fetched
later, only for allowed types under the size cap.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from typing import Any

from argus.domain.ingestion.gmail.client import decode_base64url
from argus.domain.ingestion.gmail.html_text import MAX_TEXT_CHARS, html_to_text
from argus.domain.ingestion.gmail.senders import domain_of, from_address

MAX_DEPTH = 8
MAX_PARTS = 64
MAX_INLINE_TEXT_BYTES = 1024 * 1024
_PART_HEADERS = ("content-type", "content-disposition", "content-transfer-encoding")


@dataclass(frozen=True)
class AttachmentPart:
    part_id: str
    media_type: str
    size: int
    filename: str | None
    attachment_id: str | None = field(default=None, repr=False)
    inline_data: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ParsedEmail:
    message_id: str
    thread_id: str | None
    received_at: datetime
    label_ids: frozenset[str]
    sender: str | None
    subject: str | None
    text: str
    attachments: tuple[AttachmentPart, ...]
    parts_truncated: bool

    @property
    def sender_domain(self) -> str | None:
        return domain_of(self.sender) if self.sender else None


def header_value(name: str, value: str) -> str:
    """Decode a header with ``policy.default``; fall back to the raw text."""

    try:
        return str(policy.default.header_factory(name, value))
    except Exception:  # noqa: BLE001 - malformed headers stay as received
        return value


def headers_of(part: dict[str, Any]) -> list[tuple[str, str]]:
    found = []
    for item in part.get("headers") or ():
        if isinstance(item, dict):
            name, value = item.get("name"), item.get("value")
            if isinstance(name, str) and isinstance(value, str):
                found.append((name, value))
    return found


def first_header(headers: list[tuple[str, str]], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers:
        if key.lower() == wanted:
            return header_value(key, value)
    return None


def received_at(message: dict[str, Any]) -> datetime:
    """``internalDate``: when Gmail received the message (epoch ms)."""

    try:
        millis = int(message.get("internalDate"))
    except (TypeError, ValueError):
        raise ValueError("message has no internalDate") from None
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc)


def parse_message(message: dict[str, Any]) -> ParsedEmail:
    payload = message.get("payload") or {}
    headers = headers_of(payload)
    plain: list[str] = []
    html: list[str] = []
    attachments: list[AttachmentPart] = []
    stack: list[tuple[dict[str, Any], int]] = [(payload, 0)]
    seen = 0
    truncated = False
    while stack:
        part, depth = stack.pop()
        seen += 1
        if seen > MAX_PARTS or depth > MAX_DEPTH:
            truncated = True
            break
        children = [p for p in part.get("parts") or () if isinstance(p, dict)]
        if children:
            stack.extend((child, depth + 1) for child in reversed(children))
            continue
        _leaf(part, plain, html, attachments)
    text = "\n".join(plain) if plain else "\n".join(html_to_text(h) for h in html)
    return ParsedEmail(
        message_id=str(message.get("id") or ""),
        thread_id=message.get("threadId")
        if isinstance(message.get("threadId"), str)
        else None,
        received_at=received_at(message),
        label_ids=frozenset(
            label for label in message.get("labelIds") or () if isinstance(label, str)
        ),
        sender=from_address(first_header(headers, "From")),
        subject=first_header(headers, "Subject"),
        text=text[:MAX_TEXT_CHARS],
        attachments=tuple(attachments),
        parts_truncated=truncated,
    )


def _leaf(
    part: dict[str, Any],
    plain: list[str],
    html: list[str],
    attachments: list[AttachmentPart],
) -> None:
    described = _describe(part)
    body = part.get("body") or {}
    media_type = described.get_content_type()
    filename = described.get_filename() or part.get("filename") or None
    disposition = described.get_content_disposition()
    attachment_id = body.get("attachmentId")
    if filename or disposition == "attachment" or isinstance(attachment_id, str):
        size = body.get("size")
        data = body.get("data")
        attachments.append(
            AttachmentPart(
                part_id=str(part.get("partId") or ""),
                media_type=media_type,
                size=size if isinstance(size, int) and size >= 0 else 0,
                filename=filename if isinstance(filename, str) else None,
                attachment_id=attachment_id if isinstance(attachment_id, str) else None,
                inline_data=decode_base64url(data) if isinstance(data, str) else None,
            )
        )
        return
    if media_type not in ("text/plain", "text/html"):
        return
    data = body.get("data")
    if not isinstance(data, str) or len(data) > MAX_INLINE_TEXT_BYTES * 4 // 3:
        return
    decoded = _decode(decode_base64url(data), described.get_content_charset())
    (plain if media_type == "text/plain" else html).append(decoded)


def _describe(part: dict[str, Any]) -> EmailMessage:
    described = EmailMessage(policy=policy.default)
    for name, value in headers_of(part):
        if name.lower() in _PART_HEADERS:
            try:
                described[name] = value
            except Exception:  # noqa: BLE001 - unusable header is ignored
                continue
    if "content-type" not in described and isinstance(part.get("mimeType"), str):
        try:
            described["Content-Type"] = part["mimeType"]
        except Exception:  # noqa: BLE001
            pass
    return described


def _decode(raw: bytes, charset: str | None) -> str:
    """Text codecs only: ``bytes.decode`` refuses bytes-to-bytes codecs such
    as ``zlib_codec`` with ``LookupError``, which falls back to UTF-8."""

    name = charset or "utf-8"
    try:
        if not codecs.lookup(name)._is_text_encoding:
            name = "utf-8"
        return raw.decode(name, errors="replace")
    except (LookupError, AttributeError):
        return raw.decode("utf-8", errors="replace")
