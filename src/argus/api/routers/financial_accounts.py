"""Financial accounts, first slice: create, list, reopen, edit, opening.

Thin transport: auth, flag, request validation, error shaping. Rules live in
``argus.domain.recording``; storage in its repositories.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, Response

from argus.api.dependencies import problem
from argus.api.financial_accounts import (
    FinancialAccountsContext,
    domain_problem,
    require_financial_accounts_context,
)
from argus.api.routers.business import router as business_router
from argus.api.routers.business_drafts import router as business_drafts_router
from argus.api.routers.business_export import router as business_export_router
from argus.api.routers.business_fiscal import router as business_fiscal_router
from argus.api.routers.business_manual import router as business_manual_router
from argus.api.routers.business_month_close import (
    open_items_router as business_open_items_router,
)
from argus.api.routers.business_month_close import router as business_month_close_router
from argus.api.routers.email_intake import router as business_email_router
from argus.api.routers.email_intake import webhook_router as resend_webhook_router
from argus.api.routers.financial_activities import router as money_router
from argus.api.routers.financial_assets import router as asset_router
from argus.api.routers.financial_connections import router as connections_router
from argus.api.routers.financial_debts import router as debt_router
from argus.api.routers.financial_documents import router as documents_router
from argus.api.routers.financial_imports import router as imports_router
from argus.api.routers.financial_loop import router as loop_router
from argus.api.routers.financial_plan import router as plan_router
from argus.api.routers.financial_search import router as search_router
from argus.api.routers.ingestion_shortcuts import (
    intake_router as shortcuts_intake_router,
)
from argus.api.routers.whatsapp import link_router as whatsapp_link_router
from argus.api.routers.whatsapp import webhook_router as whatsapp_webhook_router
from argus.domain import backtest_admission
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.loop_schemas import LoopOpeningRequest
from argus.domain.recording.schemas import (
    CreateFinancialAccountRequest,
    EditFinancialAccountRequest,
    FinancialAccountListResponse,
    FinancialAccountResponse,
    account_response,
)

router = APIRouter(prefix="/api/v1", tags=["financial-accounts"])


@router.post(
    "/financial-accounts",
    response_model=FinancialAccountResponse,
    status_code=201,
    responses={200: {"model": FinancialAccountResponse, "description": "Exact replay"}},
)
def create_financial_account(
    request: Request,
    response: Response,
    body: CreateFinancialAccountRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> FinancialAccountResponse:
    key = _required_idempotency_key(request, idempotency_key)
    try:
        result = context.service.create(
            user_id=context.user_id, idempotency_key=key, request=body, scope=PERSONAL
        )
    except Exception as error:
        raise domain_problem(request, error) from None
    response.status_code = 201 if result.created else 200
    return account_response(result.stored)


@router.get("/financial-accounts", response_model=FinancialAccountListResponse)
def list_financial_accounts(
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> FinancialAccountListResponse:
    accounts = context.service.list_accounts(user_id=context.user_id, scope=PERSONAL)
    return FinancialAccountListResponse(
        accounts=[account_response(item) for item in accounts]
    )


@router.get("/financial-accounts/{account_id}", response_model=FinancialAccountResponse)
def get_financial_account(
    request: Request,
    account_id: str,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> FinancialAccountResponse:
    try:
        stored = context.service.get(
            user_id=context.user_id, account_id=account_id, scope=PERSONAL
        )
    except Exception as error:
        raise domain_problem(request, error) from None
    return account_response(stored)


@router.patch("/financial-accounts/{account_id}", response_model=FinancialAccountResponse)
def edit_financial_account(
    request: Request,
    account_id: str,
    body: EditFinancialAccountRequest,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> FinancialAccountResponse:
    try:
        stored = context.service.edit(
            user_id=context.user_id, account_id=account_id, request=body, scope=PERSONAL
        )
    except Exception as error:
        raise domain_problem(request, error) from None
    return account_response(stored)


@router.put(
    "/financial-accounts/{account_id}/opening", response_model=FinancialAccountResponse
)
def write_financial_opening(
    request: Request,
    account_id: str,
    body: LoopOpeningRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> FinancialAccountResponse:
    try:
        current = context.service.get(
            user_id=context.user_id, account_id=account_id, scope=PERSONAL
        )
        if current.expenses or current.checks or body.preview_token:
            key = _required_idempotency_key(request, idempotency_key)
            result = context.service.loop.write_opening(
                user_id=context.user_id,
                account_id=account_id,
                request=body,
                idempotency_key=key,
            )
            stored = result.stored
        else:
            stored = context.service.write_opening(
                user_id=context.user_id,
                account_id=account_id,
                request=body,
                scope=PERSONAL,
            )
    except Exception as error:
        raise domain_problem(request, error) from None
    return account_response(stored)


def _required_idempotency_key(request: Request, raw: str | None) -> str:
    state, key = backtest_admission.validate_idempotency_key(raw)
    if state == "ok" and key is not None:
        return key
    if state == "invalid":
        raise problem(
            request,
            status_code=422,
            code="validation_error",
            title="Validation Error",
            detail="Idempotency-Key must be 1-128 visible ASCII characters with no whitespace.",
        )
    raise problem(
        request,
        status_code=400,
        code="idempotency_key_required",
        title="Idempotency Key Required",
        detail="POST /financial-accounts requires an Idempotency-Key header.",
    )


router.include_router(loop_router)
router.include_router(asset_router)

router.include_router(money_router)

router.include_router(plan_router)
router.include_router(debt_router)

router.include_router(search_router)

router.include_router(connections_router)
router.include_router(imports_router)
router.include_router(documents_router)

router.include_router(shortcuts_intake_router)
router.include_router(whatsapp_webhook_router)
router.include_router(whatsapp_link_router)
router.include_router(business_router)
router.include_router(business_drafts_router)
router.include_router(business_manual_router)
router.include_router(resend_webhook_router)
router.include_router(business_email_router)

router.include_router(business_export_router)
router.include_router(business_month_close_router)
router.include_router(business_open_items_router)
router.include_router(business_fiscal_router)
