"""Bounded local decoding. Rendered pages and OCR intermediates are transient."""

from __future__ import annotations

import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from argus.domain.business.contracts.checks import DgiiQr
from argus.domain.ingestion.documents.config import (
    DocumentExtractionSettings,
    load_document_extraction_settings,
)
from argus.domain.ingestion.documents.dgii_qr import read_dgii_qr
from argus.domain.ingestion.documents.ecf_checks import EcfDocument, read_ecf
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.rebuilt import (
    MAX_PIXELS,
    MAX_TEXT_BYTES,
    image_pixels,
)
from argus.domain.ingestion.documents.rebuilt import (
    rebuild_image as _image,
)
from argus.domain.ingestion.documents.rebuilt import (
    run_capped as _run,
)
from argus.domain.ingestion.documents.tabular import (
    FLAT_MEDIA_TYPES,
    XML_MEDIA_TYPES,
    document_currency,
    flat_text,
)


@dataclass(frozen=True)
class PreparedDocument:
    pages: int
    images: tuple[bytes, ...]
    text: str | None = None
    #: The currency the source names for itself (a DGII e-CF: DOP), else None.
    document_currency: str | None = None
    #: The e-CF the source is, read once for the local checks; None otherwise.
    ecf: EcfDocument | None = None
    #: The DGII QR decoded from the page images; None when there is none.
    dgii_qr: DgiiQr | None = None


def email_image_budget(parts: Iterable[tuple[bytes, str]]) -> None:
    """All image attachments together share the existing single-image cap."""
    total = 0
    for content, media_type in parts:
        if media_type in ("image/png", "image/jpeg"):
            total += image_pixels(content, media_type)
            if total > MAX_PIXELS:
                raise DocumentExtractionError("document_email_limit")


def prepare_document(
    content: bytes,
    media_type: str,
    settings: DocumentExtractionSettings | None = None,
) -> PreparedDocument:
    settings = settings if settings is not None else load_document_extraction_settings()
    if not content:
        raise DocumentExtractionError("empty_document")
    if len(content) > settings.max_bytes:
        raise DocumentExtractionError("document_too_large")
    if media_type == "message/rfc822":
        return _email(content, settings)
    if media_type in FLAT_MEDIA_TYPES:
        pages, text = flat_text(content, media_type)
        currency = document_currency(content, media_type)
        if pages > settings.max_pages:
            raise DocumentExtractionError("document_page_limit")
        ecf = read_ecf(content) if media_type in XML_MEDIA_TYPES else None
        return PreparedDocument(pages, (), text, currency, ecf)
    if media_type in ("image/png", "image/jpeg"):
        image = _image(content, media_type)
        return PreparedDocument(1, (image,), dgii_qr=read_dgii_qr((image,)))
    if media_type != "application/pdf":
        raise DocumentExtractionError("unsupported_media_type")
    if not content.startswith(b"%PDF-"):
        raise DocumentExtractionError("invalid_document")
    with tempfile.TemporaryDirectory(prefix="argus-document-") as temporary:
        root = Path(temporary)
        source = root / "source.pdf"
        source.write_bytes(content)
        info = root / "info.txt"
        _run(["pdfinfo", str(source)], info)
        if info.stat().st_size > MAX_TEXT_BYTES:
            raise DocumentExtractionError("invalid_document")
        metadata = info.read_text(errors="replace")
        if re.search(r"^Encrypted:\s+yes", metadata, re.MULTILINE):
            raise DocumentExtractionError("encrypted_document")
        match = re.search(r"^Pages:\s+(\d+)", metadata, re.MULTILINE)
        if not match:
            raise DocumentExtractionError("invalid_document")
        pages = int(match[1])
        if not 1 <= pages <= settings.max_pages:
            raise DocumentExtractionError("document_page_limit")
        text_path = root / "text.txt"
        _run(["pdftotext", "-layout", str(source), "-"], text_path)
        if text_path.stat().st_size > MAX_TEXT_BYTES:
            raise DocumentExtractionError("document_text_limit")
        images = []
        for page in range(1, pages + 1):
            prefix = root / f"page-{page}"
            _run(
                [
                    "pdftoppm",
                    "-f",
                    str(page),
                    "-l",
                    str(page),
                    "-singlefile",
                    "-scale-to",
                    "1600",
                    "-jpeg",
                    str(source),
                    str(prefix),
                ],
                root / "render.log",
            )
            rendered = prefix.with_suffix(".jpg")
            if rendered.stat().st_size > settings.max_bytes:
                raise DocumentExtractionError("document_too_large")
            images.append(_image(rendered.read_bytes(), "image/jpeg"))
        return PreparedDocument(
            pages,
            tuple(images),
            text_path.read_text(errors="replace"),
            dgii_qr=read_dgii_qr(images),
        )


def _email(content: bytes, settings: DocumentExtractionSettings) -> PreparedDocument:
    """An email is one document: its text is page 1, each attachment adds pages.

    Image pages keep the order of the attachments; text pages are labelled so the
    model can number what it read."""

    from argus.domain.ingestion.documents.email_source import parse_email

    parsed = parse_email(content)
    email_image_budget((part.content, part.media_type) for part in parsed.attachments)
    if not parsed.readable:
        raise DocumentExtractionError(
            "unsupported_email_attachment" if parsed.skipped else "empty_document"
        )
    pages, images, texts = 1, [], []
    currency, ecf = None, None
    if parsed.text.strip():
        texts.append("Page 1 (email message text):\n" + parsed.text)
    for part in parsed.attachments:
        if part.media_type in ("image/png", "image/jpeg"):
            pages += 1
            images.append(_image(part.content, part.media_type))
        elif part.media_type == "application/pdf":
            nested = prepare_document(part.content, "application/pdf", settings)
            images.extend(nested.images)
            if nested.text and nested.text.strip():
                texts.append(
                    f"Pages {pages + 1} to {pages + nested.pages} (attachment "
                    f"{part.filename!r} PDF text):\n{nested.text}"
                )
            pages += nested.pages
        elif part.media_type in FLAT_MEDIA_TYPES:
            count, text = flat_text(part.content, part.media_type)
            currency = currency or document_currency(part.content, part.media_type)
            if ecf is None and part.media_type in XML_MEDIA_TYPES:
                ecf = read_ecf(part.content)
            texts.append(
                f"Attachment {part.filename!r}, starting at page {pages + 1}:\n{text}"
            )
            pages += count
        if pages > settings.max_pages:
            raise DocumentExtractionError("document_page_limit")
    if parsed.skipped:
        texts.append(
            "Parts not read: "
            + "; ".join(
                f"{part.filename} ({part.media_type}, {part.reason})"
                for part in parsed.skipped
            )
        )
    text = "\n\n".join(texts)
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise DocumentExtractionError("document_text_limit")
    return PreparedDocument(
        pages, tuple(images), text or None, currency, ecf, read_dgii_qr(images)
    )


def validate_source(content: bytes, media_type: str) -> None:
    """Validate bounded capture without requiring extraction tools or credentials."""
    if not content:
        raise DocumentExtractionError("document_empty")
    if len(content) > load_document_extraction_settings().max_bytes:
        raise DocumentExtractionError("document_too_large")
    if media_type == "message/rfc822":
        from argus.domain.ingestion.documents.email_source import parse_email

        parsed = parse_email(content)
        email_image_budget((part.content, part.media_type) for part in parsed.attachments)
        if not parsed.readable:
            raise DocumentExtractionError(
                "unsupported_email_attachment" if parsed.skipped else "empty_document"
            )
        for part in parsed.attachments:
            validate_source(part.content, part.media_type)
    elif media_type in FLAT_MEDIA_TYPES:
        flat_text(content, media_type)
    elif media_type in ("image/jpeg", "image/png"):
        _image(content, media_type)
    elif media_type == "application/pdf":
        if not content.startswith(b"%PDF-"):
            raise DocumentExtractionError("invalid_document")
    else:
        raise DocumentExtractionError("unsupported_media_type")
