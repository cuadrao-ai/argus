"""Manual asset commands behind the existing registered financial boundary."""

from fastapi import APIRouter, Depends, Header, Request

from argus.api.financial_accounts import (
    FinancialAccountsContext,
    require_financial_accounts_context,
)
from argus.api.routers.financial_loop import _call, _key
from argus.domain.recording.asset_schemas import AssetDetailsRequest, AssetEstimateRequest
from argus.domain.recording.assets import (
    AssetDetailsResponse,
    AssetOperationResponse,
    AssetPreviewResponse,
    AssetService,
)
from argus.domain.recording.schemas import account_response

router = APIRouter(tags=["financial-accounts"])


@router.post(
    "/financial-accounts/{account_id}/asset-estimates/preview",
    response_model=AssetPreviewResponse,
)
def preview(
    request: Request,
    account_id: str,
    body: AssetEstimateRequest,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    return _call(
        request,
        lambda: AssetService(context.service).preview(context.user_id, account_id, body),
    )


@router.post(
    "/financial-accounts/{account_id}/asset-estimates",
    response_model=AssetOperationResponse,
)
def estimate(
    request: Request,
    account_id: str,
    body: AssetEstimateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    key = _key(request, idempotency_key)
    result = _call(
        request,
        lambda: AssetService(context.service).write(
            context.user_id, account_id, body, key
        ),
    )
    return AssetOperationResponse(
        account=account_response(result.stored),
        record_id=result.record_id,
        revision=result.revision,
        replayed=result.replayed,
    )


@router.put(
    "/financial-accounts/{account_id}/asset-details", response_model=AssetDetailsResponse
)
def details(
    request: Request,
    account_id: str,
    body: AssetDetailsRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    key = _key(request, idempotency_key)
    result = _call(
        request,
        lambda: AssetService(context.service).details(
            context.user_id, account_id, body, key
        ),
    )
    return AssetDetailsResponse(
        account=account_response(result.stored),
        change_version=result.change_version,
        replayed=result.replayed,
    )
