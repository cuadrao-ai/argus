"""Reviewed expenses and checks using the existing financial access boundary."""

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from argus.api.financial_accounts import (
    FinancialAccountsContext,
    domain_problem,
    require_financial_accounts_context,
)
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning.budget_schemas import BudgetHomeResponse
from argus.domain.planning.budgets import BudgetService
from argus.domain.planning.service import PlanService
from argus.domain.recording.loop_reads import (
    activity_response,
    check_response,
    expense_record,
    operation_response,
    page,
)
from argus.domain.recording.loop_schemas import (
    CATEGORY_IDS,
    ActivityOperationResponse,
    ActivityPageResponse,
    ActivityPreviewResponse,
    ActivityRequest,
    ActivityResponse,
    CategoriesResponse,
    CheckOperationResponse,
    CheckPageResponse,
    CheckPreviewResponse,
    CheckRequest,
    LoopOpeningRequest,
    OpeningPreviewResponse,
)

router = APIRouter(tags=["financial-accounts"])


def _call(request, action):
    try:
        return action()
    except Exception as error:
        raise domain_problem(request, error) from None


def _key(request, raw):
    from argus.api.routers.financial_accounts import _required_idempotency_key

    return _required_idempotency_key(request, raw)


@router.get("/financial-categories", response_model=CategoriesResponse)
def categories(
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    return {"categories": [{"id": key, "kind": "expense"} for key in CATEGORY_IDS]}


@router.get("/financial-home", response_model=BudgetHomeResponse)
def home(
    request: Request,
    month: str | None = None,
    time_zone: str | None = None,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    return _call(
        request,
        lambda: BudgetService(PlanService(context.service)).home(
            context.user_id, month, time_zone
        ),
    )


@router.post(
    "/financial-accounts/{account_id}/activity/preview",
    response_model=ActivityPreviewResponse,
)
def preview_activity(
    request: Request,
    account_id: str,
    body: ActivityRequest,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    return _call(
        request,
        lambda: context.service.loop.preview_activity(
            user_id=context.user_id, account_id=account_id, request=body
        ),
    )


@router.post(
    "/financial-accounts/{account_id}/activity/{record_id}/preview",
    response_model=ActivityPreviewResponse,
)
def preview_correction(
    request: Request,
    account_id: str,
    record_id: str,
    body: ActivityRequest,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    return _call(
        request,
        lambda: context.service.loop.preview_activity(
            user_id=context.user_id,
            account_id=account_id,
            record_id=record_id,
            request=body,
        ),
    )


@router.post(
    "/financial-accounts/{account_id}/activity",
    status_code=201,
    response_model=ActivityOperationResponse,
)
def write_activity(
    request: Request,
    response: Response,
    account_id: str,
    body: ActivityRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    key = _key(request, idempotency_key)
    result = _call(
        request,
        lambda: context.service.loop.write_activity(
            user_id=context.user_id,
            account_id=account_id,
            request=body,
            idempotency_key=key,
        ),
    )
    response.status_code = 200 if result.replayed else 201
    return operation_response(result)


@router.patch(
    "/financial-accounts/{account_id}/activity/{record_id}",
    response_model=ActivityOperationResponse,
)
def correct_activity(
    request: Request,
    account_id: str,
    record_id: str,
    body: ActivityRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    key = _key(request, idempotency_key)
    result = _call(
        request,
        lambda: context.service.loop.write_activity(
            user_id=context.user_id,
            account_id=account_id,
            record_id=record_id,
            request=body,
            idempotency_key=key,
        ),
    )
    return operation_response(result)


@router.get(
    "/financial-accounts/{account_id}/activity", response_model=ActivityPageResponse
)
def activity_list(
    request: Request,
    account_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    def read():
        stored = context.service.get(
            user_id=context.user_id, account_id=account_id, scope=PERSONAL
        )
        items = sorted(
            stored.expenses, key=lambda e: (e.current.occurred_at, e.id), reverse=True
        )
        return page(
            stored,
            [activity_response(stored, e) for e in items],
            limit,
            cursor,
            "activity",
        )

    return _call(request, read)


@router.get(
    "/financial-accounts/{account_id}/activity/{record_id}",
    response_model=ActivityResponse,
)
def activity_detail(
    request: Request,
    account_id: str,
    record_id: str,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    def read():
        stored = context.service.get(
            user_id=context.user_id, account_id=account_id, scope=PERSONAL
        )
        return activity_response(stored, expense_record(stored, record_id))

    return _call(request, read)


@router.get(
    "/financial-accounts/{account_id}/activity/{record_id}/history",
    response_model=ActivityPageResponse,
)
def activity_history(
    request: Request,
    account_id: str,
    record_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    def read():
        stored = context.service.get(
            user_id=context.user_id, account_id=account_id, scope=PERSONAL
        )
        record = expense_record(stored, record_id)
        return page(
            stored,
            [
                activity_response(stored, record, r.revision)
                for r in reversed(record.revisions)
            ],
            limit,
            cursor,
            "history:" + record.id,
        )

    return _call(request, read)


@router.post(
    "/financial-accounts/{account_id}/balance-checks/preview",
    response_model=CheckPreviewResponse,
)
def preview_check(
    request: Request,
    account_id: str,
    body: CheckRequest,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    return _call(
        request,
        lambda: context.service.loop.preview_check(
            user_id=context.user_id, account_id=account_id, request=body
        ),
    )


@router.post(
    "/financial-accounts/{account_id}/balance-checks",
    status_code=201,
    response_model=CheckOperationResponse,
)
def write_check(
    request: Request,
    response: Response,
    account_id: str,
    body: CheckRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    key = _key(request, idempotency_key)
    result = _call(
        request,
        lambda: context.service.loop.write_check(
            user_id=context.user_id,
            account_id=account_id,
            request=body,
            idempotency_key=key,
        ),
    )
    response.status_code = 200 if result.replayed else 201
    return operation_response(result)


@router.get(
    "/financial-accounts/{account_id}/balance-checks", response_model=CheckPageResponse
)
def check_list(
    request: Request,
    account_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    def read():
        stored = context.service.get(
            user_id=context.user_id, account_id=account_id, scope=PERSONAL
        )
        return page(
            stored,
            [
                check_response(stored, c)
                for c in sorted(
                    stored.checks, key=lambda c: c.reviewed_version, reverse=True
                )
            ],
            limit,
            cursor,
            "checks",
        )

    return _call(request, read)


@router.post(
    "/financial-accounts/{account_id}/opening/preview",
    response_model=OpeningPreviewResponse,
)
def preview_opening(
    request: Request,
    account_id: str,
    body: LoopOpeningRequest,
    context: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
):
    return _call(
        request,
        lambda: context.service.loop.preview_opening(
            user_id=context.user_id, account_id=account_id, request=body
        ),
    )
