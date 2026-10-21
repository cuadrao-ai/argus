"""Month close and open items. Transport only: auth, validation, and the settlement store."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from psycopg import Error as PostgresError
from psycopg_pool import PoolTimeout

from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.business_month_close_schemas import (
    MonthClose,
    OpenItems,
    SettlementResult,
    SettlementUpdate,
)
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.domain.business.authority import ActionError
from argus.domain.business.month_close import Settlement
from argus.domain.business.month_close_store import (
    read_month,
    read_open,
    settle_document,
)

_GRANT_REFUSALS = {
    403: {
        "description": "`business_grant_not_live`: the chosen grant (`X-Business-Grant`) is missing, someone else's, revoked or expired; `business_permission_denied`: the live grant does not allow this."
    }
}
router = APIRouter(
    prefix="/business/month-close", tags=["business"], responses=_GRANT_REFUSALS
)
open_items_router = APIRouter(
    prefix="/business/open-items", tags=["business"], responses=_GRANT_REFUSALS
)


def _owner(request: Request, context: DraftContext, person: BusinessPerson):
    return context.for_space(request, person.spaces)


def _unavailable(request: Request):
    raise problem(
        request,
        status_code=503,
        code="business_month_close_unavailable",
        title="Month close unavailable",
        detail="The authorized month snapshot is unavailable.",
        headers=NO_STORE,
    )


@router.get("", response_model=MonthClose)
def month_summary(
    request: Request,
    response: Response,
    month: str,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
):
    response.headers.update(NO_STORE)
    if (
        set(request.query_params) != {"month"}
        or len(request.query_params.getlist("month")) != 1
    ):
        raise problem(
            request,
            status_code=422,
            code="validation_error",
            title="Validation Error",
            detail="Only month is accepted.",
            headers=NO_STORE,
        )
    try:
        return read_month(
            context.service.authority, _owner(request, context, person), month
        )
    except ValueError as error:
        if str(error) != "month_invalid":
            raise
        raise problem(
            request,
            status_code=422,
            code="month_invalid",
            title="Invalid month",
            detail="month_invalid",
            headers=NO_STORE,
        ) from None
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except (PostgresError, PoolTimeout):
        _unavailable(request)


@open_items_router.get("", response_model=OpenItems)
def open_items(
    request: Request,
    response: Response,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
):
    response.headers.update(NO_STORE)
    if request.query_params:
        raise problem(
            request,
            status_code=422,
            code="validation_error",
            title="Validation Error",
            detail="No query parameters are accepted.",
            headers=NO_STORE,
        )
    try:
        return read_open(context.service.authority, _owner(request, context, person))
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except (PostgresError, PoolTimeout):
        _unavailable(request)


@router.patch(
    "/documents/{activity_id}",
    response_model=SettlementResult,
    responses={
        409: {
            "description": "`business_document_settlement_conflict`: another first settlement of this document landed, and a fresh retry still collided.",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
            },
        }
    },
)
def update_document(
    request: Request,
    response: Response,
    activity_id: UUID,
    body: SettlementUpdate,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
):
    response.headers.update(NO_STORE)
    command = Settlement(body.status, body.settled_on, body.payment_method)
    try:
        return settle_document(
            context.service.authority,
            _owner(request, context, person),
            str(activity_id),
            command,
        )
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except (PostgresError, PoolTimeout):
        _unavailable(request)
