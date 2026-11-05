"""The Supabase bucket adapter: storage and transport failures become one
retryable error; anything else is a bug and propagates."""

from __future__ import annotations

import httpx
import pytest
from argus.domain.profile_images import ProfileImageStorageUnavailable
from argus.domain.profile_images.objects import (
    PROFILE_IMAGE_BUCKET,
    SupabaseProfileImageObjects,
)
from storage3.exceptions import StorageApiError


class _Bucket:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def upload(self, *args: object, **kwargs: object) -> None:
        raise self.error

    def remove(self, *args: object) -> None:
        raise self.error

    def create_signed_urls(self, *args: object) -> None:
        raise self.error


class _Storage:
    def __init__(self, error: Exception) -> None:
        self.bucket = _Bucket(error)
        self.opened: list[str] = []

    def from_(self, name: str) -> _Bucket:
        self.opened.append(name)
        return self.bucket


@pytest.mark.parametrize(
    "error",
    [
        StorageApiError("object not found", "NotFound", 404),
        httpx.ConnectError("storage away"),
        ConnectionResetError(),
    ],
)
def test_storage_and_transport_failures_are_one_retryable_error(error: Exception) -> None:
    storage = _Storage(error)
    objects = SupabaseProfileImageObjects(storage)
    assert storage.opened == [PROFILE_IMAGE_BUCKET]
    with pytest.raises(ProfileImageStorageUnavailable) as raised:
        objects.put("people/x/256.webp", b"RIFF", "image/webp")
    assert raised.value.__cause__ is error
    with pytest.raises(ProfileImageStorageUnavailable):
        objects.remove("people/x/256.webp")
    with pytest.raises(ProfileImageStorageUnavailable):
        objects.signed_urls(["people/x/256.webp"], 60)


def test_a_programming_error_is_not_hidden_as_unavailability() -> None:
    objects = SupabaseProfileImageObjects(_Storage(TypeError("bad call")))
    with pytest.raises(TypeError):
        objects.put("people/x/256.webp", b"RIFF", "image/webp")


def test_nothing_to_sign_makes_no_call() -> None:
    objects = SupabaseProfileImageObjects(_Storage(AssertionError("called")))
    assert objects.signed_urls([], 60) == {}
