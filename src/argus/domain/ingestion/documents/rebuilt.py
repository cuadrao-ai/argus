"""Bounded image copies for authorized downloads and document preparation."""

from __future__ import annotations

import hashlib
import os
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import psutil
from loguru import logger

from argus.domain.ingestion.documents.config import SOURCE_MAX_BYTES
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.objects import SourceStorageUnavailable

if TYPE_CHECKING:
    from argus.domain.ingestion.documents.store import DocumentStore

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


def rebuild_image(content: bytes, media_type: str) -> bytes:
    return _image_process(content, media_type, "rebuild")


def image_pixels(content: bytes, media_type: str) -> int:
    return int(_image_process(content, media_type, "pixels"))


def ensure_rebuilt_image(
    *, store: DocumentStore, user_id: str, connection_id: str
) -> None:
    """Build one missing image copy after authorization and outside caller locks.

    Callers must recheck authorization and source identity before serving bytes.
    The store owns deletion fences, integrity checks and duplicate-safe writes.
    """
    draft = store.draft(user_id=user_id, connection_id=connection_id)
    if draft is None or draft.media_type not in ("image/png", "image/jpeg"):
        return
    if store.rebuilt(user_id=user_id, connection_id=connection_id) is not None:
        return
    content = store.source(user_id=user_id, connection_id=connection_id)
    if content is None:
        return
    if hashlib.sha256(content).hexdigest() != draft.sha256:
        raise SourceStorageUnavailable("source_content_mismatch")
    if len(content) > SOURCE_MAX_BYTES:
        raise DocumentExtractionError("document_too_large")
    rebuilt = rebuild_image(content, draft.media_type)
    current = store.draft(user_id=user_id, connection_id=connection_id)
    if current is None:
        return
    if (current.sha256, current.media_type) != (draft.sha256, draft.media_type):
        raise SourceStorageUnavailable("source_content_mismatch")
    store.save_rebuilt(
        user_id=user_id,
        connection_id=connection_id,
        content=rebuilt,
        media_type="image/jpeg",
    )


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
            run_capped(
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


def run_capped(args: list[str], output: Path, *, image: bool = False) -> None:
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
