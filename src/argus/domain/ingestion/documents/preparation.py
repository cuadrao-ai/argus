"""Bounded local decoding. Rendered pages and OCR intermediates are transient."""

from __future__ import annotations

import os
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import psutil
from loguru import logger

from argus.domain.business.contracts.checks import DgiiQr
from argus.domain.ingestion.documents.config import (
    DocumentExtractionSettings,
    load_document_extraction_settings,
)
from argus.domain.ingestion.documents.dgii_qr import read_dgii_qr
from argus.domain.ingestion.documents.ecf_checks import EcfDocument, read_ecf
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.tabular import (
    FLAT_MEDIA_TYPES,
    XML_MEDIA_TYPES,
    document_currency,
    flat_text,
)

MAX_PIXELS = 20_000_000
MAX_TEXT_BYTES = 200_000
# Set limits in a fresh child, never preexec_fn in the threaded API process.
_RESOURCE_WRAPPER = (
    "import os,resource,sys; "
    "resource.setrlimit(resource.RLIMIT_AS,(536870912,536870912)) if sys.platform == 'linux' else None; "
    "resource.setrlimit(resource.RLIMIT_CPU,(20,20)); "
    "resource.setrlimit(resource.RLIMIT_FSIZE,(10485760,10485760)); "
    "os.execvp(sys.argv[1],sys.argv[1:])"
)


# Standalone child code avoids importing the application before resource limits apply.
_IMAGE_REBUILD = """
import sys, warnings
from PIL import Image, ImageOps

source_path, target_path, media_type, maximum, mode = sys.argv[1:]
Image.MAX_IMAGE_PIXELS = int(maximum)
warnings.simplefilter("error", Image.DecompressionBombWarning)
try:
    with Image.open(source_path, formats=[{"image/png": "PNG", "image/jpeg": "JPEG"}[media_type]]) as source:
        pixels = source.width * source.height
        if pixels > Image.MAX_IMAGE_PIXELS:
            sys.exit(10)
        if getattr(source, "n_frames", 1) != 1:
            sys.exit(12)
        if mode == "pixels":
            sys.stdout.write(str(pixels))
        else:
            source.load()
            oriented = ImageOps.exif_transpose(source).convert("RGBA")
            background = Image.new("RGBA", oriented.size, "white")
            image = Image.alpha_composite(background, oriented).convert("RGB")
            image.thumbnail((1600, 1600))
            image.save(target_path, format="JPEG", quality=90)
except (Image.DecompressionBombError, Image.DecompressionBombWarning):
    sys.exit(10)
except MemoryError:
    sys.exit(13)
except Exception:
    sys.exit(11)
"""
_IMAGE_EXIT_CODES = {
    10: ("invalid_document", "pixels"),
    11: ("invalid_document", "format"),
    12: ("unsupported_image_frames", "frames"),
    13: ("document_memory_limit", "memory"),
}


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


def image_pixels(content: bytes, media_type: str) -> int:
    """Read dimensions in the capped child before any pixel allocation."""
    return int(_image_process(content, media_type, "pixels"))


def email_image_budget(parts: Iterable[tuple[bytes, str]]) -> None:
    """All image attachments together share the existing single-image cap."""
    total = 0
    for content, media_type in parts:
        if media_type in ("image/png", "image/jpeg"):
            total += image_pixels(content, media_type)
            if total > MAX_PIXELS:
                raise DocumentExtractionError("document_email_limit")


def _image(content: bytes, media_type: str) -> bytes:
    return _image_process(content, media_type, "rebuild")


def _image_process(content: bytes, media_type: str, mode: str) -> bytes:
    try:
        with tempfile.TemporaryDirectory(prefix="argus-image-") as temporary:
            root = Path(temporary)
            source, rebuilt, dimensions = (
                root / "source",
                root / "rebuilt.jpg",
                root / "dimensions",
            )
            source.write_bytes(content)
            _run(
                [
                    sys.executable,
                    "-c",
                    _IMAGE_REBUILD,
                    str(source),
                    str(rebuilt),
                    media_type,
                    str(MAX_PIXELS),
                    mode,
                ],
                dimensions,
                image=True,
            )
            return (dimensions if mode == "pixels" else rebuilt).read_bytes()
    except DocumentExtractionError as exc:
        reason = str(
            exc.metadata.get(
                "reason",
                {
                    "document_memory_limit": "memory",
                    "document_preparation_timeout": "timeout",
                }.get(exc.code, "format"),
            )
        )
        signal = exc.metadata.get("signal", 0)
        alert = reason in {"memory", "timeout"} or bool(signal)
        logger.bind(
            metric="document_image_rejected",
            reason=reason,
            value=1,
            signal=signal,
            alert=alert,
        ).log(
            "ERROR" if alert else "WARNING",
            'document_image_rejected{{reason="{}"}} 1 signal={} alert={}',
            reason,
            signal,
            alert,
        )
        raise


def _run(args: list[str], output: Path, *, image: bool = False) -> None:
    if not shutil.which(args[0]):
        raise DocumentExtractionError("document_tools_unavailable")
    try:
        with subprocess.Popen(
            [sys.executable, "-c", _RESOURCE_WRAPPER, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
        ) as process:
            assert process.stdout is not None
            monitored = psutil.Process(process.pid)
            deadline = time.monotonic() + 20
            size = 0
            try:
                with output.open("wb") as target, selectors.DefaultSelector() as reader:
                    reader.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        try:
                            if monitored.memory_info().rss > 536870912:
                                raise DocumentExtractionError("document_memory_limit")
                        except psutil.NoSuchProcess:
                            pass
                        if time.monotonic() >= deadline:
                            raise DocumentExtractionError(
                                "document_preparation_timeout", True
                            )
                        if not reader.select(timeout=0.1):
                            continue
                        chunk = os.read(process.stdout.fileno(), 65536)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_TEXT_BYTES:
                            raise DocumentExtractionError("document_text_limit")
                        target.write(chunk)
                returncode = process.wait(timeout=max(0.01, deadline - time.monotonic()))
                if returncode:
                    code, reason = (
                        _IMAGE_EXIT_CODES.get(returncode, ("invalid_document", "format"))
                        if image
                        else ("invalid_document", "format")
                    )
                    error = DocumentExtractionError(code)
                    error.metadata["reason"] = reason
                    if returncode < 0:
                        error.metadata["signal"] = -returncode
                    raise error
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    except FileNotFoundError:
        raise DocumentExtractionError("document_tools_unavailable") from None
    except subprocess.TimeoutExpired:
        raise DocumentExtractionError("document_preparation_timeout", True) from None
    except OSError:
        raise DocumentExtractionError("invalid_document") from None


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
