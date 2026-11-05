"""Thin authenticated transport for reviewed personal money activities."""

from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, Header, Request

from argus.api.financial_accounts import (
    FinancialAccountsContext,
    domain_problem,
    require_financial_accounts_context,
)
from argus.api.routers.financial_loop import _key
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.loop_schemas import CATEGORY_IDS
from argus.domain.recording.money_responses import (
    MoneyActivityResponse,
    MoneyHistoryResponse,
    MoneyOptionsResponse,
    MoneyPreviewResponse,
    MoneyReceiptResponse,
    PurchasePageResponse,
)
from argus.domain.recording.money_schemas import (
    DESTINATION_ELIGIBILITY,
    ELIGIBILITY,
    SOURCE_IDS,
    MoneyRequest,
)
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.schemas import account_response

T = TypeVar("T")


def _call(request: Request, action: Callable[[], T]) -> T:
    try:
        return action()
    except Exception as error:
        raise domain_problem(request, error) from None


router = APIRouter(prefix="/financial-activities", tags=["financial-accounts"])


@router.get("/options", response_model=MoneyOptionsResponse)
def options(
    request: Request,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> dict[str, Any]:
    return _call(
        request,
        lambda: {
            "accounts": [
                account_response(s)
                for s in context.service.list_accounts(
                    user_id=context.user_id, scope=PERSONAL
                )
            ],
            "eligibility": ELIGIBILITY,
            "destination_eligibility": DESTINATION_ELIGIBILITY,
            "categories": CATEGORY_IDS,
            "sources": SOURCE_IDS,
        },
    )


@router.get("/purchases", response_model=PurchasePageResponse)
def purchases(
    request: Request,
    currency: str | None = None,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> dict[str, Any]:
    return _call(
        request,
        lambda: MoneyService(context.service).purchases(
            user_id=context.user_id, currency=currency, scope=PERSONAL
        ),
    )


@router.post("/preview", response_model=MoneyPreviewResponse)
def preview(
    request: Request,
    body: MoneyRequest,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> dict[str, Any]:
    return _call(
        request,
        lambda: MoneyService(context.service).preview(
            user_id=context.user_id, request=body, scope=PERSONAL
        ),
    )


@router.post("", status_code=201, response_model=MoneyReceiptResponse)
def create(
    request: Request,
    body: MoneyRequest,
    idempotency_key: str | None = Header(default=None),
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> dict[str, Any]:
    return _call(
        request,
        lambda: MoneyService(context.service).write(
            user_id=context.user_id,
            request=body,
            idempotency_key=_key(request, idempotency_key),
            scope=PERSONAL,
        ),
    )


@router.get("/{activity_id}", response_model=MoneyActivityResponse)
def detail(
    request: Request,
    activity_id: str,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> dict[str, Any]:
    return _call(
        request,
        lambda: MoneyService(context.service).detail(
            user_id=context.user_id, activity_id=activity_id, scope=PERSONAL
        ),
    )


@router.get("/{activity_id}/history", response_model=MoneyHistoryResponse)
def history(
    request: Request,
    activity_id: str,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> dict[str, Any]:
    return _call(
        request,
        lambda: MoneyService(context.service).history(
            user_id=context.user_id, activity_id=activity_id, scope=PERSONAL
        ),
    )


@router.post("/{activity_id}/preview", response_model=MoneyPreviewResponse)
def correction_preview(
    request: Request,
    activity_id: str,
    body: MoneyRequest,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> dict[str, Any]:
    return _call(
        request,
        lambda: MoneyService(context.service).preview(
            user_id=context.user_id, request=body, activity_id=activity_id, scope=PERSONAL
        ),
    )


@router.patch("/{activity_id}", response_model=MoneyReceiptResponse)
def correct(
    request: Request,
    activity_id: str,
    body: MoneyRequest,
    idempotency_key: str | None = Header(default=None),
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> dict[str, Any]:
    return _call(
        request,
        lambda: MoneyService(context.service).write(
            user_id=context.user_id,
            request=body,
            activity_id=activity_id,
            idempotency_key=_key(request, idempotency_key),
            scope=PERSONAL,
        ),
    )
