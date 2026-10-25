"""Upload immutable Business identity assets and project temporary image URLs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from argus.api.business import BusinessPerson, chosen_scope, require_business_person
from argus.api.business_spaces import business_access
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.profile_images import (
    require_profile_images,
    storage_problem,
)
from argus.domain.business.authority import ActionError
from argus.domain.business.lifecycle import BusinessLifecycleError
from argus.domain.business.memberships import MembershipError
from argus.domain.business.workspace import WorkspaceError, WorkspaceSnapshot
from argus.domain.business.workspace_images import (
    MAX_UPLOAD_BYTES,
    ImageAppearance,
    WorkspaceAsset,
)
from argus.domain.profile_images.images import MEDIA_TYPES, InvalidImage
from argus.domain.profile_images.objects import ProfileImageStorageUnavailable

router = APIRouter()


def workspace_image_problem(request: Request, error: InvalidImage) -> HTTPException:
    return problem(
        request,
        status_code=422,
        code="image_invalid",
        title="Unprocessable picture",
        detail="The Business picture could not be read.",
        context={"reason": error.reason},
        headers=NO_STORE,
    )


class WorkspaceImageLinks(BaseModel):
    asset_id: str
    width: int
    height: int
    source_url: str | None = None
    rendered_url: str | None = None


class BusinessProfile(WorkspaceSnapshot):
    image: WorkspaceImageLinks | None = None


def _links(
    request: Request,
    asset: WorkspaceAsset,
    appearance: ImageAppearance | None = None,
    *,
    include_source: bool = True,
) -> WorkspaceImageLinks:
    images = require_profile_images(request)
    paths = [asset.source_path] if include_source else []
    render_path = asset.render_path(appearance.crop) if appearance is not None else None
    if render_path is not None:
        paths.append(render_path)
    urls = images.objects.signed_urls(paths, 3600)
    if any(not urls.get(path) for path in paths):
        raise ProfileImageStorageUnavailable("image_url_unavailable")
    return WorkspaceImageLinks(
        asset_id=asset.id,
        width=asset.width,
        height=asset.height,
        source_url=urls.get(asset.source_path),
        rendered_url=urls.get(render_path) if render_path is not None else None,
    )


def profile_response(
    request: Request, person: BusinessPerson, snapshot: WorkspaceSnapshot
) -> BusinessProfile:
    image = None
    if isinstance(snapshot.appearance, ImageAppearance):
        asset = person.spaces.workspace_asset(
            person.person_id, snapshot.space_id, snapshot.appearance.asset_id
        )
        selected = chosen_scope(request, person.person_id)
        if selected is not None:
            permissions = selected.permissions
        else:
            access = business_access()
            grant = (
                next(
                    (
                        entry
                        for entry in access.spaces_for(person.person_id)
                        if entry.space_id == snapshot.space_id
                    ),
                    None,
                )
                if access is not None
                else None
            )
            if grant is None:
                raise WorkspaceError("business_record_not_found")
            permissions = grant.permissions
        image = _links(
            request, asset, snapshot.appearance, include_source="download" in permissions
        )
    return BusinessProfile(**snapshot.model_dump(), image=image)


@router.post(
    "/spaces/{space_id}/appearance/assets",
    response_model=WorkspaceImageLinks,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media: {"schema": {"type": "string", "format": "binary"}}
                for media in MEDIA_TYPES
            },
        }
    },
)
async def upload_business_identity(
    request: Request,
    space_id: UUID,
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceImageLinks:
    from argus.api.business_workspace import _failure, _selected

    _selected(request, person, space_id)
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
        if len(content) + len(chunk) > MAX_UPLOAD_BYTES:
            raise problem(
                request,
                status_code=413,
                code="image_too_large",
                title="Picture too large",
                detail="Upload a picture of at most 10 MiB.",
                headers=NO_STORE,
            )
        content.extend(chunk)
    images = require_profile_images(request)
    try:
        asset = person.spaces.upload_workspace_image(
            person.person_id,
            str(space_id),
            bytes(content),
            media_type,
            key or "",
            images.objects,
        )
        return _links(request, asset)
    except InvalidImage as error:
        raise workspace_image_problem(request, error) from None
    except ProfileImageStorageUnavailable:
        raise storage_problem(request) from None
    except (
        WorkspaceError,
        MembershipError,
        BusinessLifecycleError,
        ActionError,
    ) as error:
        raise _failure(request, error) from None
