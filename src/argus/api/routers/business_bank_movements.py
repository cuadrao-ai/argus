"""Transacciones: bank movements by period and the decisions on them.
Mounted from the Business router.

Default-off with bank matching. Needs the durable Business store. Every
decision needs ``prepare`` and an Idempotency-Key.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from psycopg import Error as PostgresError
from psycopg_pool import PoolTimeout

from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_bank_schemas import (
    BankSuggestionResponse,
    DispositionRequest,
    MatchRequest,
    MovementItem,
    MovementsResponse,
    OutcomeHistoryEntry,
)
from argus.api.business_drafts import (
    DraftContext,
    action_problem,
    require_drafts,
    stored_drafts,
)
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.routers.business_bank import (
    bank_problem,
    require_bank_surface,
    required_key,
)
from argus.domain.business.authority import ActionError
from argus.domain.business.bank import outcomes_store
from argus.domain.business.bank.model import BankMatchingError
from argus.domain.business.bank.movements import MAX_PAGE, InvalidCursor
from argus.domain.business.bank.movements_store import movements_page, read_movements

router = APIRouter(prefix="/bank", tags=["business-bank"])


def _refuse(request: Request, status: int, code: str):  # noqa: ANN202
    return problem(
        request,
        status_code=status,
        code=code,
        title="Bank matching",
        detail=code,
        headers=NO_STORE,
    )


@router.get(
    "/movements",
    response_model=MovementsResponse,
    dependencies=[Depends(require_bank_surface)],
    responses={
        422: {"description": "`invalid_period` or `invalid_cursor`."},
        503: {"description": "`business_bank_unavailable`."},
    },
)
def list_movements(
    request: Request,
    response: Response,
    context: Annotated[DraftContext | None, Depends(stored_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    period_start: date,
    period_end: date,
    segment: Literal["por_igualar", "igualadas", "todas"] = "todas",
    sense: Literal["charge", "deposit"] | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    currency: Annotated[
        str | None,
        Query(
            pattern=r"^[A-Z]{3}$",
            description="ISO 4217 code. Items and totals hold only this currency; `other_currencies` counts the rows left out.",
        ),
    ] = None,
):
    response.headers.update(NO_STORE)
    if period_end < period_start:
        raise _refuse(request, 422, "invalid_period")
    try:
        if context is None:
            return movements_page(
                [],
                (),
                period_start=period_start,
                period_end=period_end,
                segment=segment,
                sense=sense,
                limit=limit,
                cursor=cursor,
                currency=currency,
            )
        return read_movements(
            context.service.authority.pool,
            context.for_space(request, person.spaces),
            period_start=period_start,
            period_end=period_end,
            segment=segment,
            sense=sense,
            limit=limit,
            cursor=cursor,
            currency=currency,
        )
    except BankMatchingError as error:
        raise bank_problem(request, error) from None
    except InvalidCursor:
        raise _refuse(request, 422, "invalid_cursor") from None
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except (PostgresError, PoolTimeout):
        raise _refuse(request, 503, "business_bank_unavailable") from None


IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]
_DECISION_ERRORS = {
    404: {
        "description": "`suggestion_not_found`, `line_not_found`, `business_record_not_found`."
    },
    409: {
        "description": "`pair_declined`, `suggestion_not_pending`, `line_already_confirmed`, `line_marked_no_receipt`, `line_not_matched`, `line_not_marked`, `document_already_matched`, `target_not_approved`, `business_document_settlement_conflict`, `idempotency_conflict`."
    },
    422: {"description": "`document_not_matchable`."},
    503: {"description": "`business_bank_unavailable`."},
}


def _decide(
    request: Request,
    response: Response,
    context: DraftContext,
    person: BusinessPerson,
    raw_key: str | None,
    action: Callable,
    *args,
):  # noqa: ANN202
    response.headers.update(NO_STORE)
    key = required_key(request, raw_key)
    try:
        return action(
            context.service.authority.pool,
            context.for_space(request, person.spaces),
            *args,
            key,
        )
    except BankMatchingError as error:
        raise bank_problem(request, error) from None
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except (PostgresError, PoolTimeout):
        raise _refuse(request, 503, "business_bank_unavailable") from None


@router.post(
    "/suggestions/{suggestion_id}/confirm",
    response_model=BankSuggestionResponse,
    dependencies=[Depends(require_bank_surface)],
    responses=_DECISION_ERRORS,
)
def confirm_suggestion(
    request: Request,
    response: Response,
    suggestion_id: UUID,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: IdempotencyKey = None,
):
    """Igualar: match the line to this document and mark it pagado or cobrado."""

    return _decide(
        request,
        response,
        context,
        person,
        idempotency_key,
        outcomes_store.confirm_suggestion,
        suggestion_id,
    )


@router.post(
    "/suggestions/{suggestion_id}/decline",
    response_model=BankSuggestionResponse,
    dependencies=[Depends(require_bank_surface)],
    responses=_DECISION_ERRORS,
)
def decline_suggestion(
    request: Request,
    response: Response,
    suggestion_id: UUID,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: IdempotencyKey = None,
):
    return _decide(
        request,
        response,
        context,
        person,
        idempotency_key,
        outcomes_store.decline_suggestion,
        suggestion_id,
    )


@router.post(
    "/movements/{line_id}/match",
    response_model=MovementItem,
    dependencies=[Depends(require_bank_surface)],
    responses=_DECISION_ERRORS,
)
def match_movement(
    request: Request,
    response: Response,
    line_id: UUID,
    body: MatchRequest,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: IdempotencyKey = None,
):
    """Igualar with a document the person chose. Same sense, currency, and amount."""

    return _decide(
        request,
        response,
        context,
        person,
        idempotency_key,
        outcomes_store.match_line,
        line_id,
        body.activity_id,
    )


@router.post(
    "/movements/{line_id}/unmatch",
    response_model=MovementItem,
    dependencies=[Depends(require_bank_surface)],
    responses=_DECISION_ERRORS,
)
def unmatch_movement(
    request: Request,
    response: Response,
    line_id: UUID,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: IdempotencyKey = None,
):
    """Desigualar: end the match and put back the settlement it replaced."""

    return _decide(
        request,
        response,
        context,
        person,
        idempotency_key,
        outcomes_store.unmatch_line,
        line_id,
    )


@router.put(
    "/movements/{line_id}/disposition",
    response_model=MovementItem,
    dependencies=[Depends(require_bank_surface)],
    responses=_DECISION_ERRORS,
)
def set_disposition(
    request: Request,
    response: Response,
    line_id: UUID,
    body: DispositionRequest,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: IdempotencyKey = None,
):
    """No lleva comprobante, with the reason."""

    return _decide(
        request,
        response,
        context,
        person,
        idempotency_key,
        outcomes_store.set_disposition,
        line_id,
        body.reason,
    )


@router.delete(
    "/movements/{line_id}/disposition",
    response_model=MovementItem,
    dependencies=[Depends(require_bank_surface)],
    responses=_DECISION_ERRORS,
)
def clear_disposition(
    request: Request,
    response: Response,
    line_id: UUID,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: IdempotencyKey = None,
):
    return _decide(
        request,
        response,
        context,
        person,
        idempotency_key,
        outcomes_store.clear_disposition,
        line_id,
    )


@router.get(
    "/movements/{line_id}/history",
    response_model=list[OutcomeHistoryEntry],
    dependencies=[Depends(require_bank_surface)],
    responses=_DECISION_ERRORS,
)
def movement_history(
    request: Request,
    response: Response,
    line_id: UUID,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
):
    """Every outcome the line has had, oldest first, ended ones included."""

    response.headers.update(NO_STORE)
    try:
        return outcomes_store.line_history(
            context.service.authority.pool,
            context.for_space(request, person.spaces),
            line_id,
        )
    except BankMatchingError as error:
        raise bank_problem(request, error) from None
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except (PostgresError, PoolTimeout):
        raise _refuse(request, 503, "business_bank_unavailable") from None
