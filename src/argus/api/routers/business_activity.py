"""Business activity feed. Transport only: auth, the cursor, the read."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from psycopg import Error as PostgresError
from psycopg_pool import PoolTimeout

from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_drafts import DraftContext, action_problem, stored_drafts
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.domain.business.activity.queries import (
    InvalidCursor,
    decode_cursor,
    read_activity,
)
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.activity import ActivityPage, PageSize

_GRANT_REFUSALS = {
    403: {
        "description": "`business_grant_not_live`: the chosen grant (`X-Business-Grant`) is missing, someone else's, revoked or expired; `business_permission_denied`: the live grant does not allow this."
    }
}
router = APIRouter(
    prefix="/business/activity", tags=["business"], responses=_GRANT_REFUSALS
)


@router.get("", response_model=ActivityPage)
def activity_page(
    request: Request,
    response: Response,
    context: Annotated[DraftContext | None, Depends(stored_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    limit: PageSize = 25,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
):
    """Who changed what and when in the working Business: applied ledger rows,
    newest first. Access changes list only for a reader who may manage."""

    response.headers.update(NO_STORE)
    try:
        before = decode_cursor(cursor) if cursor else None
    except InvalidCursor:
        raise problem(
            request,
            status_code=422,
            code="invalid_cursor",
            title="Invalid cursor",
            detail="The cursor is not one this read issued.",
            headers=NO_STORE,
        ) from None
    if context is None:
        return ActivityPage(items=())
    try:
        return read_activity(
            context.service.authority,
            context.for_space(request, person.spaces),
            limit=limit,
            before=before,
        )
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except (PostgresError, PoolTimeout):
        raise problem(
            request,
            status_code=503,
            code="business_activity_unavailable",
            title="Activity unavailable",
            detail="The Business activity feed is unavailable.",
            headers=NO_STORE,
        ) from None
