"""Explicit creation and selected-Business profile transport."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict

from argus.api.business import BusinessPerson, chosen_scope, require_business_person
from argus.api.business_schemas import BusinessSpaceInfo, SpaceName
from argus.api.business_spaces import space_payload
from argus.api.business_workspace_images import (
    BusinessProfile,
    profile_response,
    workspace_image_problem,
)
from argus.api.dependencies import problem, require_standing_account
from argus.api.documents import NO_STORE
from argus.api.profile_images import profile_images, storage_problem
from argus.domain.business.authority import ActionError
from argus.domain.business.country import CountryCode
from argus.domain.business.lifecycle import BusinessLifecycleError
from argus.domain.business.memberships import MembershipError
from argus.domain.business.workspace import (
    PHONE_REFUSAL_CODES,
    BusinessDetails,
    BusinessDetailsInput,
    SaveWorkspace,
    WorkspaceError,
)
from argus.domain.profile_images.images import InvalidImage
from argus.domain.profile_images.objects import ProfileImageStorageUnavailable

DETAIL_CODES = {
    "invalid_business_email",
    "invalid_business_website",
    "string_too_long",
    *PHONE_REFUSAL_CODES,
}


def _detail_errors(errors: Any) -> dict[str, str]:
    """The refused detail fields and their codes, or nothing when another part failed."""
    fields: dict[str, str] = {}
    for error in errors:
        *where, field = error["loc"]
        if (
            where not in (["body"], ["body", "details"])
            or field not in BusinessDetails.model_fields
            or error["type"] not in DETAIL_CODES
        ):
            return {}
        fields[field] = error["type"]
    return fields


class DetailsRoute(APIRoute):
    """Answers refused details with one code per field, the shape the forms show."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as error:
                fields = _detail_errors(error.errors())
                if not fields:
                    raise
                raise problem(
                    request,
                    status_code=422,
                    code="invalid_business_details",
                    title="Business details refused",
                    detail="One or more Business details are not valid.",
                    headers=NO_STORE,
                    context={"field_errors": fields},
                ) from None

        return handler


router = APIRouter(route_class=DetailsRoute)

DETAILS_REFUSED = {
    422: {
        "description": "`invalid_business_details` when only detail fields failed: "
        "`context.field_errors` maps each refused field to `invalid_business_email`, "
        "`invalid_business_website`, `string_too_long`, or for a phone "
        "`invalid_business_phone_empty`, `invalid_business_phone_length`, "
        "`invalid_business_phone_format` or `invalid_business_phone_region`. "
        "`validation_error` for any other body failure."
    }
}


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


@router.post(
    "/spaces",
    response_model=BusinessSpaceInfo,
    status_code=201,
    dependencies=[Depends(require_standing_account)],
)
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


@router.post(
    "/profile-details/check",
    response_model=BusinessDetailsInput,
    response_model_exclude_unset=True,
    responses=DETAILS_REFUSED,
    dependencies=[Depends(require_business_person)],
)
def check_business_details(
    response: Response, body: BusinessDetailsInput
) -> BusinessDetailsInput:
    """Answers with the fields sent, each in its saved form. Saves nothing.

    A valid phone comes back as `+1 809 555 0142`.
    """
    response.headers.update(NO_STORE)
    return body


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


@router.patch(
    "/spaces/{space_id}/profile",
    response_model=BusinessProfile,
    responses=DETAILS_REFUSED,
)
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
