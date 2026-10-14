"""Split a received message into its text and attachment parts, with per-part faults.

Unlike the single-document parser, a bad part does not fail the message: the
part carries its error code and its siblings still capture."""

from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.errors import MultipartInvariantViolationDefect
from email.parser import BytesHeaderParser, BytesParser

from argus.domain.ingestion.documents import preparation
from argus.domain.ingestion.documents.email_source import MAX_EMAIL_BYTES
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.service import stored_filename
from argus.domain.ingestion.gmail.html_text import html_to_text

MAX_BODY_BYTES = 64 * 1024


@dataclass(frozen=True)
class EnvelopePart:
    id: str
    filename: str
    media_type: str
    content: bytes
    error_code: str | None = None


@dataclass(frozen=True)
class Envelope:
    subject: str | None
    sender: str | None
    sent_at: str | None
    text_body: str
    parts: tuple[EnvelopePart, ...]


def validate_envelope(content: bytes) -> None:
    if not content or len(content) > MAX_EMAIL_BYTES:
        raise DocumentExtractionError("document_email_limit")
    separator = b"\r\n\r\n" if b"\r\n\r\n" in content else b"\n\n"
    header = content.split(separator, 1)[0]
    if len(header) > MAX_BODY_BYTES:
        raise DocumentExtractionError("document_email_limit")
    parsed = BytesHeaderParser(policy=policy.default).parsebytes(header)
    if not parsed.keys() or any(
        not isinstance(defect, MultipartInvariantViolationDefect)
        for defect in parsed.defects
    ):
        raise DocumentExtractionError("invalid_document")


def parse_envelope(content: bytes) -> Envelope:
    validate_envelope(content)
    message = BytesParser(policy=policy.default).parsebytes(content)
    parts, plain, html = [], [], []
    stack, count, body_size = [(message, "1", 0)], 0, 0
    pixels = 0
    while stack:
        part, key, depth = stack.pop()
        count += 1
        media = part.get_content_type()
        filename = stored_filename(part.get_filename() or "attachment")
        if count > 64 or depth > 8 or len(parts) >= 16:
            parts.append(EnvelopePart(key, filename, media, b"", "document_email_limit"))
            break
        if media == "message/rfc822":
            parts.append(
                EnvelopePart(key, filename, media, b"", "unsupported_email_attachment")
            )
            continue
        if part.is_multipart():
            stack.extend(
                (child, f"{key}.{index}", depth + 1)
                for index, child in reversed(list(enumerate(part.iter_parts(), 1)))
            )
            continue
        raw = part.get_payload(decode=True) or b""
        error = "invalid_document" if part.defects else None
        attachment = (
            part.get_filename()
            or part.get_content_disposition() == "attachment"
            or media not in ("text/plain", "text/html")
        )
        if attachment:
            if not error and media in ("image/png", "image/jpeg"):
                try:
                    pixels += preparation.image_pixels(raw, media)
                except DocumentExtractionError as failure:
                    error = failure.code
                if pixels > preparation.MAX_PIXELS:
                    raise DocumentExtractionError("document_email_limit")
            parts.append(EnvelopePart(key, filename, media, raw, error))
            continue
        body_size += len(raw)
        if body_size > MAX_BODY_BYTES:
            parts.append(
                EnvelopePart(key, "message-body", media, b"", "document_text_limit")
            )
            continue
        try:
            text = raw.decode(part.get_content_charset() or "utf-8", errors="strict")
            if error:
                raise ValueError(error)
            (html if media == "text/html" else plain).append(
                html_to_text(text) if media == "text/html" else text
            )
        except (UnicodeError, LookupError, ValueError):
            parts.append(
                EnvelopePart(key, "message-body", media, b"", "invalid_document")
            )

    def header(name: str) -> str | None:
        value = str(message.get(name, "")).strip()
        return "".join(char for char in value if char.isprintable())[:320] or None

    return Envelope(
        header("subject"),
        header("from"),
        header("date"),
        "\n".join(plain or html)[:MAX_BODY_BYTES],
        tuple(parts),
    )
