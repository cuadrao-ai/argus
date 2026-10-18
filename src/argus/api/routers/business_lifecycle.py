"""WIP close transport, unmounted and denied until retention is complete."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, StrictStr

from argus.api.business import (
    BusinessPerson,
    require_business_person,
    require_business_surface,
    unavailable_problem,
)
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.domain.business.lifecycle import (
    BusinessLifecycleError,
    LifecycleResult,
    PostgresBusinessLifecycle,
)


class CloseBusinessBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: StrictStr


class BusinessLifecycleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    space_id: str
    name: str
    closed_at: datetime | None
    reopen_until: datetime | None


class TransferMember(BaseModel):
    grant_id: str
    name: str


class OwnedBusiness(BaseModel):
    space_id: str
    name: str
    grant_id: str
    members: list[TransferMember]


class OwnedBusinesses(BaseModel):
    spaces: list[OwnedBusiness]


class ClosedBusinesses(BaseModel):
    spaces: list[BusinessLifecycleResponse]


def require_lifecycle_ready(request: Request) -> None:
    # Mounting this module must not enable closure before custody and purge work.
    raise unavailable_problem(request)


def require_lifecycle(request: Request) -> PostgresBusinessLifecycle:
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None:
        raise unavailable_problem(request)
    return PostgresBusinessLifecycle(pool)


def no_store(response: Response) -> None:
    response.headers.update(NO_STORE)


router = APIRouter(
    prefix="/business",
    tags=["business"],
    dependencies=[
        Depends(require_business_surface),
        Depends(require_lifecycle_ready),
        Depends(no_store),
    ],
)
Person = Annotated[BusinessPerson, Depends(require_business_person)]
Lifecycle = Annotated[PostgresBusinessLifecycle, Depends(require_lifecycle)]
CommandKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]
_PROBLEMS = {
    "business_name_mismatch": (422, "Business name does not match."),
    "invalid_idempotency_key": (422, "A command key is required."),
    "business_record_not_found": (404, "No such Business."),
    "business_reopen_expired": (409, "The reopening period has ended."),
    "business_already_open": (409, "Another Business is already open."),
    "idempotency_conflict": (409, "This command key was already used."),
}


def lifecycle_problem(request: Request, error: BusinessLifecycleError) -> Exception:
    status, detail = _PROBLEMS[error.code]
    return problem(
        request,
        status_code=status,
        code=error.code,
        title="Not Found" if status == 404 else "Business lifecycle command refused",
        detail=detail,
        headers=NO_STORE,
    )


def response(result: LifecycleResult) -> BusinessLifecycleResponse:
    return BusinessLifecycleResponse.model_validate(result)


@router.get("/owned-spaces", response_model=OwnedBusinesses)
def owned_businesses(person: Person, service: Lifecycle) -> OwnedBusinesses:
    return OwnedBusinesses(
        spaces=[
            OwnedBusiness.model_validate(row)
            for row in service.owned_spaces(person.person_id)
        ]
    )


@router.get("/closed-spaces", response_model=ClosedBusinesses)
def closed_businesses(person: Person, service: Lifecycle) -> ClosedBusinesses:
    return ClosedBusinesses(
        spaces=[response(row) for row in service.closed_spaces(person.person_id)]
    )


@router.post("/spaces/{space_id}/close", response_model=BusinessLifecycleResponse)
def close_business(
    request: Request,
    space_id: UUID,
    body: CloseBusinessBody,
    person: Person,
    service: Lifecycle,
    idempotency_key: CommandKey,
) -> BusinessLifecycleResponse:
    try:
        return response(
            service.close(
                owner_id=person.person_id,
                space_id=str(space_id),
                confirmation=body.confirmation,
                idempotency_key=idempotency_key,
            )
        )
    except BusinessLifecycleError as error:
        raise lifecycle_problem(request, error) from None


@router.post("/spaces/{space_id}/reopen", response_model=BusinessLifecycleResponse)
def reopen_business(
    request: Request,
    space_id: UUID,
    person: Person,
    service: Lifecycle,
    idempotency_key: CommandKey,
) -> BusinessLifecycleResponse:
    try:
        return response(
            service.reopen(
                owner_id=person.person_id,
                space_id=str(space_id),
                idempotency_key=idempotency_key,
            )
        )
    except BusinessLifecycleError as error:
        raise lifecycle_problem(request, error) from None
