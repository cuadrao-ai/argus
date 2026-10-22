"""Ownership transfer commands, behind the Business surface gate."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, StrictStr

from argus.api.business import require_business_surface, unavailable_problem
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.routers.business_lifecycle import (
    CommandKey,
    Person,
    lifecycle_problem,
    no_store,
)
from argus.domain.business.lifecycle import BusinessLifecycleError
from argus.domain.business.transfer import PostgresBusinessTransfer, TransferResult


class RequestTransferBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_grant_id: UUID
    confirmation: StrictStr


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    space_id: str
    status: Literal["pending", "accepted", "cancelled", "declined", "expired"]
    expires_at: datetime | None = None


class TransferListResponse(BaseModel):
    transfers: list["TransferDetailsResponse"]


class TransferDetailsResponse(TransferResponse):
    business_name: str
    owner_name: str
    target_name: str
    role: Literal["owner", "target"]
    grant_id: str


def require_transfer(request: Request) -> PostgresBusinessTransfer:
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None:
        raise unavailable_problem(request)
    return PostgresBusinessTransfer(pool)


Transfer = Annotated[PostgresBusinessTransfer, Depends(require_transfer)]
router = APIRouter(
    prefix="/business",
    tags=["business"],
    dependencies=[Depends(require_business_surface), Depends(no_store)],
)


def _invoke(
    request: Request, command: Callable[..., TransferResult], **kwargs: str
) -> TransferResponse:
    try:
        return TransferResponse.model_validate(command(**kwargs))
    except BusinessLifecycleError as error:
        if error.code in (
            "business_transfer_target_invalid",
            "business_transfer_not_pending",
            "business_transfer_pending",
            "business_transfer_expired",
        ):
            raise problem(
                request,
                status_code=409,
                code=error.code,
                title="Business transfer refused",
                detail="The transfer cannot continue in its current state.",
                headers=NO_STORE,
            ) from None
        raise lifecycle_problem(request, error) from None


@router.get("/ownership-transfers", response_model=TransferListResponse)
def discover_transfers(person: Person, service: Transfer) -> TransferListResponse:
    return TransferListResponse(
        transfers=[
            TransferDetailsResponse.model_validate(row)
            for row in service.discover(actor_id=person.person_id)
        ]
    )


@router.post("/spaces/{space_id}/ownership-transfers", response_model=TransferResponse)
def request_transfer(
    request: Request,
    space_id: UUID,
    body: RequestTransferBody,
    person: Person,
    service: Transfer,
    idempotency_key: CommandKey,
) -> TransferResponse:
    return _invoke(
        request,
        service.request,
        owner_id=person.person_id,
        space_id=str(space_id),
        target_grant_id=str(body.target_grant_id),
        confirmation=body.confirmation,
        idempotency_key=idempotency_key,
    )


@router.post("/ownership-transfers/{transfer_id}/accept", response_model=TransferResponse)
def accept_transfer(
    request: Request, transfer_id: UUID, person: Person, service: Transfer
) -> TransferResponse:
    return _invoke(
        request, service.accept, actor_id=person.person_id, transfer_id=str(transfer_id)
    )


@router.post(
    "/ownership-transfers/{transfer_id}/decline", response_model=TransferResponse
)
def decline_transfer(
    request: Request, transfer_id: UUID, person: Person, service: Transfer
) -> TransferResponse:
    return _invoke(
        request, service.decline, actor_id=person.person_id, transfer_id=str(transfer_id)
    )


@router.post(
    "/ownership-transfers/{transfer_id}/withdraw", response_model=TransferResponse
)
def withdraw_transfer(
    request: Request, transfer_id: UUID, person: Person, service: Transfer
) -> TransferResponse:
    return _invoke(
        request, service.cancel, owner_id=person.person_id, transfer_id=str(transfer_id)
    )
