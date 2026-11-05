"""Business logos are managed by a live Owner or Admin in the selected Business."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

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
    found = business_access().granted(context.scope.actor_id, context.scope.grant_id)
    if found is None or "manage" not in found.permissions:
        raise problem(
            request,
            status_code=403,
            code="business_permission_denied",
            title="Forbidden",
            detail="This access does not allow changing the logo.",
            headers=NO_STORE,
        )


def _payload(request: Request, space_id: str) -> dict[str, Any]:
    space = business_spaces().get(space_id)
    if space is None:
        raise space_missing_problem(request)
    return space_payload(space)


@router.put("/logo", response_model=BusinessSpaceInfo, responses=_RESPONSES)
async def put_logo(
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business_management)],
) -> dict[str, Any]:
    """Replace the Business logo with the raw picture in the body
    (`Content-Type: image/jpeg`, `image/png` or `image/webp`, at most 5 MiB).
    It is stored as a 256 px WebP square with its metadata dropped."""

    _require_manager(request, context)
    images = require_profile_images(request)
    media_type, content = await read_image_upload(request)
    space_id = context.scope.owner.space_id
    try:
        images.replace(business(space_id), content, media_type)
    except InvalidImage as error:
        raise image_problem(request, error) from None
    except ProfileImageStorageUnavailable:
        raise storage_problem(request) from None
    return _payload(request, space_id)


@router.delete("/logo", status_code=204, responses={k: _RESPONSES[k] for k in (403, 503)})
def delete_logo(
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business_management)],
) -> Response:
    """Remove the Business logo; removing an absent logo is a 204 too."""

    _require_manager(request, context)
    images = require_profile_images(request)
    try:
        images.remove(business(context.scope.owner.space_id))
    except ProfileImageStorageUnavailable:
        raise storage_problem(request) from None
    return Response(status_code=204, headers=NO_STORE)
