import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from argus.api.fiscal_operations import fiscal_service, require_fiscal
from argus.api.routers.business_customers import (
    Context,
    Key,
    invoice_problem,
    require_invoicing,
)
from argus.api.routers.business_drafts import _key
from argus.api.routers.business_fiscal_operations import _actor
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.invoicing import (
    Invoice,
    InvoicePage,
    InvoicePrepare,
    InvoiceWrite,
)
from argus.domain.business.fiscal_sandbox.service import Service
from argus.domain.business.invoicing.queries import Query, invoices
from argus.domain.business.invoicing.store import Store

router = APIRouter(
    prefix="/business/invoices",
    tags=["business"],
    dependencies=[Depends(require_invoicing)],
)


@router.get("", response_model=InvoicePage)
def list_invoices(
    request: Request,
    context: Context,
    query: Annotated[Query, Depends()],
    fiscal: Annotated[Service | None, Depends(fiscal_service)],
) -> InvoicePage:
    try:
        return invoices(
            Store(context.service.authority.pool),
            _actor(context),
            context.grant_id,
            query,
            issuance_available=fiscal is not None,
        )
    except ActionError as error:
        raise invoice_problem(request, error) from None


@router.get("/{invoice_id}", response_model=Invoice)
def get_invoice(request: Request, invoice_id: UUID, context: Context) -> Invoice:
    try:
        return Store(context.service.authority.pool).invoice(
            _actor(context), context.grant_id, invoice_id
        )
    except ActionError as error:
        raise invoice_problem(request, error) from None


@router.post("", response_model=Invoice, status_code=201)
def create_invoice(
    request: Request, body: InvoiceWrite, context: Context, idempotency_key: Key = None
) -> Invoice:
    try:
        return Store(context.service.authority.pool).save_invoice(
            _actor(context), context.grant_id, None, body, _key(request, idempotency_key)
        )
    except ActionError as error:
        raise invoice_problem(request, error) from None


@router.put("/{invoice_id}", response_model=Invoice)
def save_invoice(
    request: Request,
    invoice_id: UUID,
    body: InvoiceWrite,
    context: Context,
    idempotency_key: Key = None,
) -> Invoice:
    try:
        return Store(context.service.authority.pool).save_invoice(
            _actor(context),
            context.grant_id,
            invoice_id,
            body,
            _key(request, idempotency_key),
        )
    except ActionError as error:
        raise invoice_problem(request, error) from None


@router.post("/{invoice_id}/prepare", response_model=Invoice)
async def prepare_invoice(
    request: Request,
    invoice_id: UUID,
    body: InvoicePrepare,
    context: Context,
    service: Annotated[Service, Depends(require_fiscal)],
) -> Invoice:
    from argus.domain.business.invoicing.preparation import prepare

    try:
        return await asyncio.to_thread(
            prepare,
            Store(context.service.authority.pool),
            service,
            _actor(context),
            context.grant_id,
            invoice_id,
            body.expected_version,
        )
    except ActionError as error:
        raise invoice_problem(request, error) from None
