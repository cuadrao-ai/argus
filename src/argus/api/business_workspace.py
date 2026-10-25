"""Explicit creation and selected-Business profile transport."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from argus.api.business import BusinessPerson, chosen_scope, require_business_person
from argus.api.business_schemas import BusinessSpaceInfo, SpaceName
from argus.api.business_spaces import space_payload
from argus.api.business_workspace_images import (
    BusinessProfile,
    profile_response,
    workspace_image_problem,
)
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.profile_images import profile_images, storage_problem
from argus.domain.business.authority import ActionError
from argus.domain.business.country import CountryCode
from argus.domain.business.lifecycle import BusinessLifecycleError
from argus.domain.business.memberships import MembershipError
from argus.domain.business.workspace import (
    SaveWorkspace,
    WorkspaceError,
)
from argus.domain.profile_images.images import InvalidImage
from argus.domain.profile_images.objects import ProfileImageStorageUnavailable

router = APIRouter()


class CreateAdditionalBusiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: SpaceName
    country: CountryCode


def _failure(
    request: Request,
    error: WorkspaceError | MembershipError | BusinessLifecycleError | ActionError,
) -> HTTPException:
    code = error.code
    status = 409
    if code in {
        "business_record_not_found",
        "business_space_missing",
        "business_image_not_found",
    }:
        status = 404
    elif code in {
        "business_permission_denied",
        "business_closed",
        "business_grant_not_live",
    }:
        status = 403
    elif code == "invalid_idempotency_key":
        status = 400
    return problem(
        request,
        status_code=status,
        code=code,
        title="Business request refused",
        detail="The Business request could not be completed.",
        headers=NO_STORE,
    )


def _selected(request: Request, person: BusinessPerson, space_id: UUID) -> None:
    scope = chosen_scope(request, person.person_id)
    if scope is not None and scope.owner.space_id != str(space_id):
        raise _failure(request, WorkspaceError("business_record_not_found"))


@router.post("/spaces", response_model=BusinessSpaceInfo, status_code=201)
def create_additional_business(
    request: Request,
    response: Response,
    body: CreateAdditionalBusiness,
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    try:
        space, created = person.spaces.create_additional(
            person.person_id, body.name, body.country, key or ""
        )
    except (
        WorkspaceError,
        MembershipError,
        BusinessLifecycleError,
        ActionError,
    ) as error:
        raise _failure(request, error) from None
    response.status_code = 201 if created else 200
    return space_payload(space)


@router.get("/spaces/{space_id}/profile", response_model=BusinessProfile)
def read_business_profile(
    request: Request,
    space_id: UUID,
    person: Annotated[BusinessPerson, Depends(require_business_person)],
) -> BusinessProfile:
    _selected(request, person, space_id)
    try:
        return profile_response(
            request, person, person.spaces.read_workspace(person.person_id, str(space_id))
        )
    except ProfileImageStorageUnavailable:
        raise storage_problem(request) from None
    except (
        WorkspaceError,
        MembershipError,
        BusinessLifecycleError,
        ActionError,
    ) as error:
        raise _failure(request, error) from None


@router.patch("/spaces/{space_id}/profile", response_model=BusinessProfile)
def save_business_profile(
    request: Request,
    space_id: UUID,
    body: SaveWorkspace,
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> BusinessProfile:
    _selected(request, person, space_id)
    try:
        images = profile_images()
        snapshot = person.spaces.save_workspace(
            person.person_id,
            str(space_id),
            body,
            key or "",
            images.objects if images else None,
        )
        return profile_response(request, person, snapshot)
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
