"""Profile pictures in the private ``profile-images`` Storage bucket.

Only the service role reaches the bucket. A reader gets a signed URL that
expires; a writer replaces the object in place.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Protocol
from uuid import UUID

import httpx
from storage3.exceptions import StorageApiError

PROFILE_IMAGE_BUCKET = "profile-images"


class ProfileImageStorageUnavailable(RuntimeError):
    """Storage could not be reached or refused the call; retrying may succeed."""


class ProfileImageObjects(Protocol):
    def read(self, path: str) -> bytes: ...

    def remove_identity(self, space_id: str) -> None: ...

    def put(self, path: str, content: bytes, media_type: str) -> None:
        """Create or replace the object."""
        ...

    def remove(self, path: str) -> None:
        """Remove the object; nothing there is not an error."""
        ...

    def signed_urls(self, paths: Sequence[str], expires_in: int) -> dict[str, str]:
        """A URL per path that serves the object for ``expires_in`` seconds."""
        ...


class InMemoryProfileImageObjects:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def put(self, path: str, content: bytes, media_type: str) -> None:
        with self._lock:
            self.objects[path] = content

    def remove(self, path: str) -> None:
        with self._lock:
            self.objects.pop(path, None)

    def read(self, path: str) -> bytes:
        with self._lock:
            try:
                return self.objects[path]
            except KeyError:
                raise ProfileImageStorageUnavailable("object_missing") from None

    def remove_identity(self, space_id: str) -> None:
        prefix = _identity_prefix(space_id)
        with self._lock:
            for path in list(self.objects):
                if path.startswith(prefix):
                    del self.objects[path]

    def signed_urls(self, paths: Sequence[str], expires_in: int) -> dict[str, str]:
        return {
            path: f"memory://{PROFILE_IMAGE_BUCKET}/{path}?expires_in={expires_in}"
            for path in paths
        }


class SupabaseProfileImageObjects:
    """Supabase Storage through the service-role client (``supabase.Client.storage``)."""

    def __init__(self, storage: Any) -> None:
        self._bucket = storage.from_(PROFILE_IMAGE_BUCKET)

    def put(self, path: str, content: bytes, media_type: str) -> None:
        with _unavailable():
            self._bucket.upload(
                path, content, {"content-type": media_type, "upsert": "true"}
            )

    def remove(self, path: str) -> None:
        with _unavailable():
            self._bucket.remove([path])

    def read(self, path: str) -> bytes:
        with _unavailable():
            return self._bucket.download(path)

    def remove_identity(self, space_id: str) -> None:
        prefix = _identity_prefix(space_id)
        with _unavailable():
            previous: list[str] | None = None
            while True:
                rows = self._bucket.list(prefix.rstrip("/"), {"limit": 100, "offset": 0})
                if not rows:
                    return
                if any(not row.get("id") or "/" in row["name"] for row in rows):
                    raise ProfileImageStorageUnavailable("unexpected_identity_object")
                names = [prefix + row["name"] for row in rows]
                if names == previous:
                    raise ProfileImageStorageUnavailable(
                        "identity_delete_not_progressing"
                    )
                self._bucket.remove(names)
                previous = names

    def signed_urls(self, paths: Sequence[str], expires_in: int) -> dict[str, str]:
        if not paths:
            return {}
        with _unavailable():
            signed = self._bucket.create_signed_urls(list(paths), expires_in)
        return {
            entry["path"]: entry["signedURL"]
            for entry in signed
            if entry["error"] is None
        }


def _identity_prefix(space_id: str) -> str:
    return f"business/{UUID(space_id)}/identity/"


@contextmanager
def _unavailable() -> Iterator[None]:
    try:
        yield
    except (StorageApiError, httpx.HTTPError, OSError) as error:
        raise ProfileImageStorageUnavailable(type(error).__name__) from error
