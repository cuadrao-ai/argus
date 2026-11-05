"""The process's profile pictures service, and the picture upload boundary.

Postgres and the private bucket in ``supabase`` persistence, in memory
otherwise. The profile and Business routes read it through
``profile_images``; a read answers with no URL when the service or its
Storage is away, and logs that.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import HTTPException, Request
from loguru import logger

from argus.api import state as api_state
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.domain.profile_images import (
    InvalidImage,
    ProfileImages,
    ProfileImageStorageUnavailable,
)
from argus.domain.profile_images.images import MAX_BYTES, MEDIA_TYPES
from argus.domain.profile_images.objects import (
    InMemoryProfileImageObjects,
    SupabaseProfileImageObjects,
)
from argus.domain.profile_images.store import (
    InMemoryProfileImageStore,
    Kind,
    PostgresProfileImageStore,
)

_images: ProfileImages | None = None


def profile_images() -> ProfileImages | None:
    return _images


def configure_profile_images(service: ProfileImages | None) -> None:
    global _images
    _images = service


def start_profile_images(app: object) -> None:
    if api_state.PERSISTENCE_MODE != "supabase":
        configure_profile_images(
            ProfileImages(InMemoryProfileImageStore(), InMemoryProfileImageObjects())
        )
        return
    pool = getattr(getattr(app, "state", None), "financial_accounts_pool", None)
    gateway = api_state.supabase_gateway
    if pool is None or gateway is None:
        logger.warning("Profile pictures need DATABASE_URL and Supabase; surface stays off")
        configure_profile_images(None)
        return
    configure_profile_images(
        ProfileImages(
            PostgresProfileImageStore(pool),
            SupabaseProfileImageObjects(gateway.client.storage),
        )
    )


def stop_profile_images(app: object) -> None:
    configure_profile_images(None)


def picture_urls(kind: Kind, ids: Sequence[str]) -> dict[str, str | None]:
    """A signed URL per id, or None: for a subject with no picture, and for
    every subject while the service or its Storage is away."""

    images = profile_images()
    if images is None:
        return dict.fromkeys(ids)
    try:
        return images.urls(kind, ids)
    except ProfileImageStorageUnavailable as error:
        logger.warning("profile_image_urls_unavailable", kind=kind, error=str(error))
        return dict.fromkeys(ids)


def require_profile_images(request: Request) -> ProfileImages:
    images = profile_images()
    if images is None:
        raise problem(
            request,
            status_code=503,
            code="profile_images_unavailable",
            title="Service Unavailable",
            detail="Pictures are not available.",
            headers=NO_STORE,
        )
    return images


async def read_image_upload(request: Request) -> tuple[str, bytes]:
    """The media type and bounded raw bytes of a picture upload."""

    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in MEDIA_TYPES:
        raise problem(
            request,
            status_code=415,
            code="image_media_type_unsupported",
            title="Unsupported picture",
            detail="Upload a JPEG, PNG or WebP picture.",
            headers=NO_STORE,
        )
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_BYTES:
            raise problem(
                request,
                status_code=413,
                code="image_too_large",
                title="Picture too large",
                detail=f"Upload a picture of at most {MAX_BYTES / 1048576:g} MiB.",
                headers=NO_STORE,
            )
        content.extend(chunk)
    return media_type, bytes(content)


def image_problem(request: Request, error: InvalidImage) -> HTTPException:
    return problem(
        request,
        status_code=422,
        code="image_invalid",
        title="Unprocessable picture",
        detail="The picture could not be read. Upload a still image of at least 64 pixels.",
        context={"reason": error.reason},
        headers=NO_STORE,
    )


def storage_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=503,
        code="profile_image_storage_unavailable",
        title="Service Unavailable",
        detail="Pictures cannot be saved right now. Try again.",
        headers=NO_STORE,
    )
