"""Offline RFC822 parsing. No SMTP, provider authenticity or sender authorization.

A caller already authenticated the owner and chose the scope. Headers never
choose the owner. The message body and its attachments become one document.
"""

from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser

from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.tabular import MAX_TEXT_BYTES
from argus.domain.ingestion.gmail.html_text import MAX_HTML_CHARS, html_to_text

MAX_EMAIL_BYTES = 10 * 1024 * 1024
MAX_PARTS = 64
MAX_ATTACHMENTS = 16


@dataclass(frozen=True)
class EmailPart:
    part_id: str
    filename: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class EmailSource:
    text: str
    attachments: tuple[EmailPart, ...]


def parse_email(content: bytes) -> EmailSource:
    if not content or len(content) > MAX_EMAIL_BYTES:
        raise DocumentExtractionError("document_email_limit")
    try:
        message = BytesParser(policy=policy.default).parsebytes(content)
        if not message.keys():
            raise DocumentExtractionError("invalid_document")
        plain, html, attachments = [], [], []
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
                raise DocumentExtractionError("unsupported_email_attachment")
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
            if (
                filename
                or part.get_content_disposition() == "attachment"
                or media not in ("text/plain", "text/html")
            ):
                if len(attachments) >= MAX_ATTACHMENTS:
                    raise DocumentExtractionError("document_email_limit")
                attachments.append(
                    EmailPart(part_id, filename or "attachment", media, raw)
                )
            else:
                if len(raw) > MAX_TEXT_BYTES:
                    raise DocumentExtractionError("document_text_limit")
                charset = part.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="strict")
                if media == "text/html":
                    if len(text) > min(MAX_HTML_CHARS, 64 * 1024):
                        raise DocumentExtractionError("document_text_limit")
                    html.append(html_to_text(text))
                else:
                    plain.append(text)
        text = "\n".join(plain if plain else html)
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise DocumentExtractionError("document_text_limit")
        return EmailSource(text, tuple(attachments))
    except DocumentExtractionError:
        raise
    except (ValueError, TypeError, LookupError, UnicodeError, RecursionError):
        raise DocumentExtractionError("invalid_document") from None
