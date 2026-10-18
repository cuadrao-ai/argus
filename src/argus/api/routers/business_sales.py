from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from argus.api.business import (
    BusinessPerson,
    owner_required_problem,
    require_business_person,
    require_business_surface,
)
from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.routers.business_drafts import _key
from argus.domain.business import ledger
from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.config import business_venta_enabled
from argus.domain.business.contracts.actions import Refused
from argus.domain.business.contracts.venta import (
    MarkVenta,
    Sale,
    SalesPeriod,
    SetVentaCollection,
)
from argus.domain.business.sales import (
    load_sales_period,
    mark_venta,
    set_venta_collection,
)
from argus.domain.business.transactions import transaction


def require_venta_surface(request: Request) -> None:
    if not business_venta_enabled():
        raise problem(
            request,
            status_code=404,
            code="business_venta_unavailable",
            title="Not Found",
            detail="Business sales are not available.",
            headers=NO_STORE,
        )


router = APIRouter(
    prefix="/ventas",
    dependencies=[
        Depends(require_business_surface),
        Depends(require_venta_surface),
    ],
)


def _owner_context(
    request: Request, drafts: DraftContext, person: BusinessPerson
) -> ActionContext:
    context = drafts.for_space(request, person.spaces)
    if str(context.actor.actor_id) != context.owner_id:
        raise owner_required_problem(request)
    return context


@router.post(
    "",
    response_model=Sale,
    status_code=201,
    responses={200: {"model": Sale, "description": "Exact replay"}},
)
def create_sale(
    request: Request,
    response: Response,
    body: MarkVenta,
    drafts: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Sale:
    response.headers.update(NO_STORE)
    context = _owner_context(request, drafts, person)
    result = mark_venta(
        drafts.service.authority,
        context,
        body,
        _key(request, idempotency_key),
    )
    if isinstance(result, Refused):
        raise action_problem(request, result)
    response.status_code = 201 if result.created else 200
    return result.sale


@router.patch("/{venta_id}/collection", response_model=Sale)
def update_collection(
    venta_id: UUID,
    request: Request,
    response: Response,
    body: SetVentaCollection,
    drafts: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Sale:
    response.headers.update(NO_STORE)
    context = _owner_context(request, drafts, person)
    result = set_venta_collection(
        drafts.service.authority,
        context,
        venta_id,
        body,
        _key(request, idempotency_key),
    )
    if isinstance(result, Refused):
        raise action_problem(request, result)
    return result


@router.get("", response_model=SalesPeriod)
def list_sales(
    request: Request,
    response: Response,
    start: Annotated[date, Query(alias="from")],
    drafts: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    end: Annotated[date | None, Query(alias="to")] = None,
) -> SalesPeriod:
    response.headers.update(NO_STORE)
    context = _owner_context(request, drafts, person)
    through = end or ledger.today()
    if start > through:
        raise problem(
            request,
            status_code=422,
            code="period_reversed",
            title="Invalid period",
            detail="The period must start on or before its end.",
            headers=NO_STORE,
        )
    try:
        with transaction(drafts.service.authority, context) as tx:
            return load_sales_period(
                tx,
                space_id=context.actor.space_id,
                start=start,
                end=through,
            )
    except ActionError as error:
        raise action_problem(request, error.result) from None
