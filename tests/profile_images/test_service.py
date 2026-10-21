"""Write order: the object before the row on replace, the row before the
object on remove, so a failure half-way never leaves a row naming nothing."""

from __future__ import annotations

import pytest
from argus.domain.profile_images import ProfileImages, person
from argus.domain.profile_images.objects import InMemoryProfileImageObjects
from argus.domain.profile_images.store import InMemoryProfileImageStore

from tests.profile_images.pictures import png

ALICE = "11111111-1111-1111-1111-111111111111"


class _StoreDown(InMemoryProfileImageStore):
    def save(self, kind, subject_id, sha256):  # noqa: ANN001, ANN201
        raise ConnectionError("row store down")


class _BucketDown(InMemoryProfileImageObjects):
    def remove(self, path: str) -> None:
        raise ConnectionError("bucket down")


def test_a_failed_row_write_leaves_an_object_but_no_url() -> None:
    objects = InMemoryProfileImageObjects()
    images = ProfileImages(_StoreDown(), objects)
    with pytest.raises(ConnectionError):
        images.replace(person(ALICE), png(), "image/png")
    assert set(objects.objects) == {person(ALICE).path}
    assert images.url(person(ALICE)) is None


def test_a_failed_object_removal_still_forgets_the_row() -> None:
    store, objects = InMemoryProfileImageStore(), _BucketDown()
    images = ProfileImages(store, objects)
    objects.objects[person(ALICE).path] = b"RIFF"
    store.save("person", ALICE, "a" * 64)
    with pytest.raises(ConnectionError):
        images.remove(person(ALICE))
    assert images.url(person(ALICE)) is None
    assert set(objects.objects) == {person(ALICE).path}
