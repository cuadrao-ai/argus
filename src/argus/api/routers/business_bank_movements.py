"""Transacciones: bank movements by period. Mounted from the Business router.

Default-off with bank matching. Needs the durable Business store.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from psycopg import Error as PostgresError
from psycopg_pool import PoolTimeout

from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_bank_schemas import MovementsResponse
from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.routers.business_bank import require_bank_surface
from argus.domain.business.authority import ActionError
from argus.domain.business.bank.movements import MAX_PAGE, InvalidCursor
from argus.domain.business.bank.movements_store import read_movements

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
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    period_start: date,
    period_end: date,
    segment: Literal["por_igualar", "igualadas", "todas"] = "todas",
    sense: Literal["charge", "deposit"] | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
):
    response.headers.update(NO_STORE)
    if period_end < period_start:
        raise _refuse(request, 422, "invalid_period")
    try:
        return read_movements(
            context.service.authority.pool,
            context.for_space(request, person.spaces),
            period_start=period_start,
            period_end=period_end,
            segment=segment,
            sense=sense,
            limit=limit,
            cursor=cursor,
        )
    except InvalidCursor:
        raise _refuse(request, 422, "invalid_cursor") from None
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except (PostgresError, PoolTimeout):
        raise _refuse(request, 503, "business_bank_unavailable") from None
