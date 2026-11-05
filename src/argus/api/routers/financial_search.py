"""Owner-scoped financial Search transport."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from argus.api.dependencies import problem
from argus.api.financial_accounts import (
    FinancialAccountsContext,
    require_financial_accounts_context,
)
from argus.domain.financial_search import (
    InvalidCursor,
    Kind,
    SearchPage,
    StaleCursor,
    search,
)

router = APIRouter(tags=["financial-search"])


@router.get("/financial-search", response_model=SearchPage)
def read(
    request: Request,
    context: Annotated[
        FinancialAccountsContext, Depends(require_financial_accounts_context)
    ],
    q: Annotated[str, Query(max_length=512)] = "",
    kind: Kind | None = None,
    currency: Annotated[str | None, Query(pattern="^[A-Z]{3}$")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> SearchPage:
    try:
        return search(
            context.service,
            context.user_id,
            q=q,
            kind=kind,
            currency=currency,
            limit=limit,
            cursor=cursor,
        )
    except (InvalidCursor, StaleCursor) as error:
        stale = isinstance(error, StaleCursor)
        raise problem(
            request,
            status_code=409 if stale else 422,
            code="financial_search_stale_cursor"
            if stale
            else "financial_search_invalid_cursor",
            title="Search changed" if stale else "Invalid cursor",
            detail="Reload Search from the first page.",
        ) from None
