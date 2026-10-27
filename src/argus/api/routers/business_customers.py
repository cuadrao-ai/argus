from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.routers.business_drafts import _key
from argus.api.routers.business_fiscal_operations import _actor
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.invoicing import (
    Customer,
    CustomerPage,
    CustomerWrite,
)
from argus.domain.business.invoicing.config import Settings
from argus.domain.business.invoicing.queries import CustomerQuery, customers
from argus.domain.business.invoicing.store import InvoiceError, Store


def require_invoicing(response: Response) -> None:
    response.headers.update(NO_STORE)
    if not Settings().enabled:
        raise HTTPException(
            404, detail="business_invoicing_unavailable", headers=NO_STORE
        )


def invoice_problem(request: Request, error: ActionError) -> HTTPException:
    if not isinstance(error, InvoiceError):
        return action_problem(request, error.result)
    return problem(
        request,
        status_code=422 if error.result.outcome == "invalid_input" else 409,
        code=error.code,
        title=error.code,
        detail=error.code,
        headers=NO_STORE,
        context={
            "field_errors": error.field_errors,
            "attempted": error.attempted,
            "current_version": error.current_version,
        },
    )


router = APIRouter(
    prefix="/business/customers",
    tags=["business"],
    dependencies=[Depends(require_invoicing)],
)
Context = Annotated[DraftContext, Depends(require_drafts)]
Key = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.get("", response_model=CustomerPage)
def list_customers(
    request: Request,
    context: Context,
    query: Annotated[CustomerQuery, Depends()],
    archived: bool = False,
) -> CustomerPage:
    try:
        return customers(
            Store(context.service.authority.pool),
            _actor(context),
            context.grant_id,
            query,
            archived,
        )
    except ActionError as error:
        raise invoice_problem(request, error) from None


@router.get("/{customer_id}", response_model=Customer)
def get_customer(request: Request, customer_id: UUID, context: Context) -> Customer:
    try:
        return Store(context.service.authority.pool).customer(
            _actor(context), context.grant_id, customer_id
        )
    except ActionError as error:
        raise invoice_problem(request, error) from None


@router.post("", response_model=Customer, status_code=201)
def create_customer(
    request: Request, body: CustomerWrite, context: Context, idempotency_key: Key = None
) -> Customer:
    try:
        return Store(context.service.authority.pool).save_customer(
            _actor(context), context.grant_id, None, body, _key(request, idempotency_key)
        )
    except ActionError as error:
        raise invoice_problem(request, error) from None


@router.put("/{customer_id}", response_model=Customer)
def save_customer(
    request: Request,
    customer_id: UUID,
    body: CustomerWrite,
    context: Context,
    idempotency_key: Key = None,
) -> Customer:
    try:
        return Store(context.service.authority.pool).save_customer(
            _actor(context),
            context.grant_id,
            customer_id,
            body,
            _key(request, idempotency_key),
        )
    except ActionError as error:
        raise invoice_problem(request, error) from None
