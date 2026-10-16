"""Retained document sources in a private Storage bucket.

New copies use ``{kind}/{user_id}/{original_sha256}``. Existing unprefixed
objects stay in place. The private bucket is reached only by the service role.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal, Protocol

from loguru import logger

SOURCE_BUCKET = "financial-document-sources"
_PAGE = 1000


def source_path(
    *, user_id: str, sha256: str, kind: Literal["sealed", "rebuilt"] = "sealed"
) -> str:
    if kind not in ("sealed", "rebuilt") or "/" in user_id or not user_id:
        raise ValueError("invalid source identity")
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise ValueError("invalid source digest")
    return f"{kind}/{user_id}/{sha256}"


def connection_prefix(*, user_id: str, connection_id: str) -> str:
    return f"{user_id}/{connection_id}/"


def owner_prefix(user_id: str) -> str:
    return f"{user_id}/"


class SourceStorageUnavailable(RuntimeError):
    """Storage could not be reached or refused the call; retrying may succeed."""


def verify_content(content: bytes | None, sha256: str) -> bytes | None:
    if content is not None and hashlib.sha256(content).hexdigest() != sha256:
        logger.error("document_source_integrity_failed")
        raise SourceStorageUnavailable("document_source_integrity_failed")
    return content


def _original(path: str, content: bytes | None) -> bytes | None:
    if not path.startswith("rebuilt/"):
        logger.info("document_original_read caller=internal_source_reader")
        return verify_content(content, path.rsplit("/", 1)[-1])
    return content


def _delete_prefixes(prefix: str) -> tuple[str, ...]:
    _require_folder(prefix)
    if prefix.count("/") == 1:
        return prefix, f"sealed/{prefix}", f"rebuilt/{prefix}"
    return (prefix,)


def _require_folder(prefix: str) -> None:
    if not prefix.endswith("/"):
        raise ValueError("delete takes a folder prefix ending with /")


class SourceObjects(Protocol):
    bucket: str

    def put(self, path: str, content: bytes, media_type: str) -> None:
        """Create a copy; an identical retry is a no-op. Never replace bytes."""
        ...

    def get(self, path: str) -> bytes | None:
        """The object's bytes, or None when it does not exist."""
        ...

    def delete(self, prefix: str) -> None:
        """Remove every object under ``prefix``, which ends with ``/``.
        Nothing there is not an error."""
        ...

    def remove(self, path: str) -> None: ...


class InMemorySourceObjects:
    bucket = SOURCE_BUCKET

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def put(self, path: str, content: bytes, media_type: str) -> None:
        if path.startswith("sealed/"):
            verify_content(content, path.rsplit("/", 1)[-1])
        with self._lock:
            if path in self.objects:
                verify_content(self.objects[path], hashlib.sha256(content).hexdigest())
            else:
                self.objects[path] = content

    def get(self, path: str) -> bytes | None:
        with self._lock:
            return _original(path, self.objects.get(path))

    def delete(self, prefix: str) -> None:
        prefixes = _delete_prefixes(prefix)
        with self._lock:
            for path in [path for path in self.objects if path.startswith(prefixes)]:
                del self.objects[path]

    def remove(self, path: str) -> None:
        with self._lock:
            self.objects.pop(path, None)


class SupabaseSourceObjects:
    """Supabase Storage through the service-role client (``supabase.Client.storage``)."""

    bucket = SOURCE_BUCKET

    def __init__(self, storage: Any) -> None:
        self._bucket = storage.from_(self.bucket)

    def put(self, path: str, content: bytes, media_type: str) -> None:
        from storage3.exceptions import StorageApiError

        if path.startswith("sealed/"):
            verify_content(content, path.rsplit("/", 1)[-1])
        with _unavailable():
            try:
                self._bucket.upload(
                    path, content, {"content-type": media_type, "upsert": "false"}
                )
            except StorageApiError as error:
                if str(error.status) != "409" and error.code != "Duplicate":
                    raise
                verify_content(
                    _original(path, self._bucket.download(path)),
                    hashlib.sha256(content).hexdigest(),
                )

    def get(self, path: str) -> bytes | None:
        from storage3.exceptions import StorageApiError

        with _unavailable():
            try:
                return _original(path, self._bucket.download(path))
            except StorageApiError as error:
                if str(error.status) == "404":
                    return None
                raise

    def delete(self, prefix: str) -> None:
        with _unavailable():
            paths = [
                path
                for folder in _delete_prefixes(prefix)
                for path in self._paths(folder)
            ]
            for start in range(0, len(paths), _PAGE):
                self._bucket.remove(paths[start : start + _PAGE])

    def remove(self, path: str) -> None:
        with _unavailable():
            self._bucket.remove([path])

    def _paths(self, prefix: str) -> list[str]:
        found: list[str] = []
        offset = 0
        while True:
            page = self._bucket.list(
                prefix.rstrip("/"), {"limit": _PAGE, "offset": offset}
            )
            for entry in page:
                path = f"{prefix}{entry['name']}"
                if entry.get("id") is None:
                    found += self._paths(f"{path}/")
                else:
                    found.append(path)
            if len(page) < _PAGE:
                return found
            offset += _PAGE


@contextmanager
def _unavailable() -> Iterator[None]:
    try:
        yield
    except Exception as error:
        raise SourceStorageUnavailable(type(error).__name__) from error
