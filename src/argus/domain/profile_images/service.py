"""One photo per person and one logo per Business, served as signed URLs.

The server is the one owner of the picture: every upload is re-encoded to the
one stored shape (``images.square_webp``), written to the bucket, and then
recorded in the subject's row. A reader gets a URL only when the row exists.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from argus.domain.profile_images.images import OUTPUT_MEDIA_TYPE, SIZE, square_webp
from argus.domain.profile_images.objects import ProfileImageObjects
from argus.domain.profile_images.store import Kind, ProfileImageStore, StoredImage

URL_TTL_SECONDS = 3600
_FOLDERS: dict[Kind, str] = {"person": "people", "business": "business"}


@dataclass(frozen=True)
class Subject:
    kind: Kind
    id: str

    @property
    def path(self) -> str:
        return f"{_FOLDERS[self.kind]}/{self.id}/{SIZE}.webp"


def person(user_id: str) -> Subject:
    return Subject("person", user_id)


def business(space_id: str) -> Subject:
    return Subject("business", space_id)


class ProfileImages:
    def __init__(
        self,
        store: ProfileImageStore,
        objects: ProfileImageObjects,
        *,
        url_ttl_seconds: int = URL_TTL_SECONDS,
    ) -> None:
        self._store = store
        self._objects = objects
        self._ttl = url_ttl_seconds

    def urls(self, kind: Kind, ids: Sequence[str]) -> dict[str, str | None]:
        """A signed URL per id, or None for a subject with no picture."""

        rows = self._store.get_many(kind, ids)
        subjects = {subject_id: Subject(kind, subject_id) for subject_id in rows}
        signed = self._objects.signed_urls(
            [subject.path for subject in subjects.values()], self._ttl
        )
        return {
            subject_id: _versioned(signed.get(subjects[subject_id].path), rows[subject_id])
            if subject_id in rows
            else None
            for subject_id in ids
        }

    def url(self, subject: Subject) -> str | None:
        return self.urls(subject.kind, [subject.id])[subject.id]

    def replace(self, subject: Subject, content: bytes, media_type: str) -> None:
        """Store ``content`` as the subject's picture. Raises ``InvalidImage``."""

        stored = square_webp(content, media_type)
        # The object first, then the row: a crash leaves an object nobody is
        # told about, never a row pointing at nothing.
        self._objects.put(subject.path, stored, OUTPUT_MEDIA_TYPE)
        self._store.save(subject.kind, subject.id, hashlib.sha256(stored).hexdigest())

    def remove(self, subject: Subject) -> None:
        """Row first, so readers stop being told; then the object. Idempotent."""

        self._store.delete(subject.kind, subject.id)
        self._objects.remove(subject.path)

    def erase(self, subject: Subject) -> None:
        """The object alone: the row goes with its auth user or its space."""

        self._objects.remove(subject.path)


def _versioned(url: str | None, row: StoredImage) -> str | None:
    # The path never changes, so the content hash makes a replaced picture a
    # new URL for every cache in between.
    if url is None:
        return None
    return f"{url}{'&' if '?' in url else '?'}v={row.sha256[:12]}"
