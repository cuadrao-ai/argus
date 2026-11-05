"""Offline RFC822 parsing. No SMTP, provider authenticity or sender authorization.

A caller already authenticated the owner and chose the scope. Headers never
choose the owner. The message body and its attachments become one document.
"""

from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser

from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.tabular import FLAT_MEDIA_TYPES, MAX_TEXT_BYTES
from argus.domain.ingestion.gmail.html_text import html_to_text

MAX_EMAIL_BYTES = 10 * 1024 * 1024
MAX_PARTS = 64
MAX_ATTACHMENTS = 16
READABLE_ATTACHMENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "application/pdf", *FLAT_MEDIA_TYPES}
)


@dataclass(frozen=True)
class EmailPart:
    part_id: str
    filename: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class SkippedPart:
    """A part the reader does not open: an inline logo, a signature, a calendar."""

    part_id: str
    filename: str
    media_type: str
    reason: str


@dataclass(frozen=True)
class EmailSource:
    text: str
    attachments: tuple[EmailPart, ...]
    skipped: tuple[SkippedPart, ...] = ()

    @property
    def readable(self) -> bool:
        return bool(self.text.strip()) or bool(self.attachments)


def parse_email(content: bytes) -> EmailSource:
    if not content or len(content) > MAX_EMAIL_BYTES:
        raise DocumentExtractionError("document_email_limit")
    try:
        message = BytesParser(policy=policy.default).parsebytes(content)
        if not message.keys():
            raise DocumentExtractionError("invalid_document")
        plain, html, attachments, skipped = [], [], [], []
        stack = [(message, "1", 0)]
        count, decoded = 0, 0
        while stack:
            part, part_id, depth = stack.pop()
            count += 1
            if count > MAX_PARTS or depth > 8:
                raise DocumentExtractionError("document_email_limit")
            if part.defects:
                raise DocumentExtractionError("invalid_document")
            if part.get_content_type() == "message/rfc822":
                # A forwarded message is noted, never opened: one email is one document.
                skipped.append(
                    SkippedPart(
                        part_id,
                        part.get_filename() or "message",
                        "message/rfc822",
                        "unsupported",
                    )
                )
                continue
            if part.is_multipart():
                children = list(part.iter_parts())
                stack.extend(
                    (p, f"{part_id}.{i}", depth + 1)
                    for i, p in reversed(list(enumerate(children, 1)))
                )
                continue
            raw = part.get_payload(decode=True) or b""
            if part.defects:
                raise DocumentExtractionError("invalid_document")
            decoded += len(raw)
            if decoded > MAX_EMAIL_BYTES:
                raise DocumentExtractionError("document_email_limit")
            media = part.get_content_type()
            filename = part.get_filename()
            inline = part.get_content_disposition() == "inline" or bool(
                part.get("Content-ID")
            )
            if (
                filename
                or part.get_content_disposition() == "attachment"
                or media not in ("text/plain", "text/html")
            ):
                name = filename or "attachment"
                # Inline logos, signatures, calendars and other non-document
                # parts are noted, not read, and never cost a page.
                if media not in READABLE_ATTACHMENT_TYPES:
                    skipped.append(SkippedPart(part_id, name, media, "unsupported"))
                elif inline and media.startswith("image/"):
                    skipped.append(SkippedPart(part_id, name, media, "inline"))
                elif len(attachments) >= MAX_ATTACHMENTS:
                    raise DocumentExtractionError("document_email_limit")
                else:
                    attachments.append(EmailPart(part_id, name, media, raw))
            else:
                if len(raw) > MAX_TEXT_BYTES:
                    raise DocumentExtractionError("document_text_limit")
                charset = part.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="strict")
                (html if media == "text/html" else plain).append(text)
        # Plain text wins. HTML is converted only when it is all the message
        # has; html_to_text caps its own input and output.
        text = "\n".join(plain if plain else [html_to_text(piece) for piece in html])
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise DocumentExtractionError("document_text_limit")
        return EmailSource(text, tuple(attachments), tuple(skipped))
    except DocumentExtractionError:
        raise
    except (ValueError, TypeError, LookupError, UnicodeError, RecursionError):
        raise DocumentExtractionError("invalid_document") from None
