from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.documents import NO_STORE
from argus.api.fiscal_operations import require_fiscal
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.fiscal_sandbox.contracts import (
    FiscalOperation,
    FiscalPrepare,
    FiscalSubmit,
)
from argus.domain.business.fiscal_sandbox.service import Service

router = APIRouter(tags=["business"])


def _actor(context: DraftContext) -> TrustedActor:
    if context.space_id is None:
        raise HTTPException(404, detail="business_record_not_found", headers=NO_STORE)
    return TrustedActor(
        actor_id=context.actor_id, space_id=UUID(context.space_id), actor_kind="member"
    )


@router.post(
    "/business/fiscal-operations", response_model=FiscalOperation, status_code=201
)
async def prepare(
    request: Request,
    response: Response,
    body: FiscalPrepare,
    context: Annotated[DraftContext, Depends(require_drafts)],
    service: Annotated[Service, Depends(require_fiscal)],
):
    response.headers.update(NO_STORE)
    try:
        return await service.prepare(_actor(context), context.grant_id, body.case_id)
    except ActionError as error:
        raise action_problem(request, error.result) from None


@router.get("/business/fiscal-operations/{operation_id}", response_model=FiscalOperation)
async def get(
    request: Request,
    response: Response,
    operation_id: UUID,
    context: Annotated[DraftContext, Depends(require_drafts)],
    service: Annotated[Service, Depends(require_fiscal)],
):
    response.headers.update(NO_STORE)
    try:
        return await service.get(_actor(context), context.grant_id, operation_id)
    except ActionError as error:
        raise action_problem(request, error.result) from None


@router.post(
    "/business/fiscal-operations/{operation_id}/submit",
    response_model=FiscalOperation,
    status_code=202,
)
async def submit(
    request: Request,
    response: Response,
    operation_id: UUID,
    body: FiscalSubmit,
    context: Annotated[DraftContext, Depends(require_drafts)],
    service: Annotated[Service, Depends(require_fiscal)],
):
    response.headers.update(NO_STORE)
    try:
        return await service.submit(
            _actor(context), context.grant_id, operation_id, body.payload_digest
        )
    except ActionError as error:
        raise action_problem(request, error.result) from None


@router.get("/business/fiscal-operations/{operation_id}/artifacts/{kind}")
async def artifact(
    request: Request,
    operation_id: UUID,
    kind: Literal["xml", "pdf"],
    context: Annotated[DraftContext, Depends(require_drafts)],
    service: Annotated[Service, Depends(require_fiscal)],
):
    try:
        content = await service.artifact(
            _actor(context), context.grant_id, operation_id, kind
        )
        return Response(
            content,
            media_type="application/xml" if kind == "xml" else "application/pdf",
            headers={
                **NO_STORE,
                "Content-Disposition": f'attachment; filename="fiscal.{kind}"',
                "X-Content-Type-Options": "nosniff",
            },
        )
    except ActionError as error:
        raise action_problem(request, error.result) from None


@router.post(
    "/webhooks/fiscal-sandbox/emission",
    status_code=202,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"type": "object"}}},
        }
    },
    responses={
        200: {"description": "Authenticated probe only"},
        401: {"description": "Static callback authentication failed"},
        413: {"description": "Body exceeds 32768 bytes"},
        503: {"description": "Observation was not durably persisted"},
    },
)
async def callback(
    request: Request,
    service: Annotated[Service, Depends(require_fiscal)],
    callback_header: Annotated[
        str | None, Header(alias="X-Cuadrao-Fiscal-Callback")
    ] = None,
):
    try:
        service.authenticate(callback_header or "")
    except PermissionError:
        raise HTTPException(
            401, detail="fiscal_callback_authentication", headers=NO_STORE
        ) from None
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 32768:
            raise HTTPException(413, detail="fiscal_callback_size", headers=NO_STORE)
    try:
        disposition = await service.callback(bytes(body))
    except ValueError:
        raise HTTPException(
            422, detail="fiscal_callback_invalid", headers=NO_STORE
        ) from None
    except Exception:
        raise HTTPException(
            503, detail="fiscal_callback_not_persisted", headers=NO_STORE
        ) from None
    return Response(status_code=200 if disposition == "probe" else 202, headers=NO_STORE)
