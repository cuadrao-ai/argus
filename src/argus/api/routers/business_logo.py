"""Business logos are managed by a live Owner or Admin in the selected Business."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg import Connection

from argus.api.business import BusinessContext, require_business_management
from argus.api.business_schemas import BusinessSpaceInfo
from argus.api.business_spaces import (
    business_access,
    business_spaces,
    space_missing_problem,
    space_payload,
)
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.profile_images import (
    image_problem,
    read_image_upload,
    require_profile_images,
    storage_problem,
)
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.postgres_connection import BorrowedConnection
from argus.domain.profile_images import (
    InvalidImage,
    ProfileImageStorageUnavailable,
    business,
)

router = APIRouter()

_RESPONSES = {
    403: {
        "description": "`business_permission_denied`: the live grant does not hold `manage`."
    },
    413: {"description": "`image_too_large`: the picture is over 5 MiB."},
    415: {"description": "`image_media_type_unsupported`: not a JPEG, PNG or WebP."},
    422: {
        "description": "`image_invalid`: not one still picture of at least 64 pixels on each side and at most 25 million pixels in all (`context.reason`: `undecodable`, `too_small`, `animated`, `too_many_pixels`)."
    },
    503: {
        "description": "`profile_images_unavailable` or `profile_image_storage_unavailable`: pictures cannot be served or saved right now."
    },
}


def _require_manager(request: Request, context: BusinessContext) -> None:
    access = (
        PostgresAccessStore(BorrowedConnection(context.connection))
        if context.connection is not None
        else business_access()
    )
    found = access.granted(context.scope.actor_id, context.scope.grant_id)
    if found is None or "manage" not in found.permissions:
        raise problem(
            request,
            status_code=403,
            code="business_permission_denied",
            title="Forbidden",
            detail="This access does not allow changing the logo.",
            headers=NO_STORE,
        )


def _payload(
    request: Request, space_id: str, connection: Connection | None = None
) -> dict[str, Any]:
    spaces = (
        PostgresSpaceStore(BorrowedConnection(connection))
        if connection is not None
        else business_spaces()
    )
    space = spaces.get(space_id)
    if space is None:
        raise space_missing_problem(request)
    return space_payload(space, connection=connection)


async def _read_logo_upload(request: Request) -> tuple[str, bytes] | HTTPException:
    try:
        return await read_image_upload(request)
    except HTTPException as error:
        # Keep permission and service-availability errors ahead of upload errors.
        return error


@router.put("/logo", response_model=BusinessSpaceInfo, responses=_RESPONSES)
async def put_logo(
    request: Request,
    # Dependencies resolve in declaration order: finish the bounded body read
    # before the management guard acquires the shared connection and grant lock.
    upload: Annotated[tuple[str, bytes] | HTTPException, Depends(_read_logo_upload)],
    context: Annotated[
        BusinessContext, Depends(require_business_management, scope="function")
    ],
) -> dict[str, Any]:
    """Replace the Business logo with the raw picture in the body
    (`Content-Type: image/jpeg`, `image/png` or `image/webp`, at most 5 MiB).
    It is stored as a 256 px WebP square with its metadata dropped."""

    _require_manager(request, context)
    images = require_profile_images(request, connection=context.connection)
    if isinstance(upload, HTTPException):
        raise upload
    media_type, content = upload
    space_id = context.scope.owner.space_id
    try:
        images.replace(business(space_id), content, media_type)
    except InvalidImage as error:
        raise image_problem(request, error) from None
    except ProfileImageStorageUnavailable:
        raise storage_problem(request) from None
    return _payload(request, space_id, context.connection)


@router.delete("/logo", status_code=204, responses={k: _RESPONSES[k] for k in (403, 503)})
def delete_logo(
    request: Request,
    context: Annotated[
        BusinessContext, Depends(require_business_management, scope="function")
    ],
) -> Response:
    """Remove the Business logo; removing an absent logo is a 204 too."""

    _require_manager(request, context)
    images = require_profile_images(request, connection=context.connection)

    def after_commit(remove: Callable[[], None]) -> None:
        def cleanup() -> None:
            try:
                remove()
            except ProfileImageStorageUnavailable:
                raise storage_problem(request) from None

        assert context.after_commit is not None
        context.after_commit(cleanup)

    try:
        images.remove(
            business(context.scope.owner.space_id),
            after_commit=after_commit if context.after_commit is not None else None,
        )
    except ProfileImageStorageUnavailable:
        raise storage_problem(request) from None
    return Response(status_code=204, headers=NO_STORE)
