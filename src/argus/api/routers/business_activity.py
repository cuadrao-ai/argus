"""Business activity feed. Transport only: auth, the filters, the cursor, the read."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from psycopg import Error as PostgresError
from psycopg_pool import PoolTimeout
from pydantic import ValidationError

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
from argus.domain.business.contracts.activity import (
    EARLIEST_DAY,
    LATEST_DAY,
    ActionGroup,
    ActivityFilters,
    ActivityPage,
    ActorId,
    Area,
    PageSize,
)

_SPAN = f"{EARLIEST_DAY.isoformat()} to {LATEST_DAY.isoformat()}"
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
    since: Annotated[
        date | None,
        Query(
            alias="from", description=f"First calendar day, Business time zone, {_SPAN}."
        ),
    ] = None,
    until: Annotated[
        date | None,
        Query(alias="to", description=f"Last calendar day, Business time zone, {_SPAN}."),
    ] = None,
    actor: Annotated[
        list[ActorId] | None,
        Query(max_length=50, description="Actor ids from the page's `actors`."),
    ] = None,
    area: Annotated[list[Area] | None, Query(max_length=4)] = None,
    action_group: Annotated[list[ActionGroup] | None, Query(max_length=9)] = None,
):
    """Who changed what and when in the working Business: applied ledger rows,
    newest first. Access changes, and an action the feed does not know yet, list
    only for a reader who may manage. Values of one filter are OR'ed, filters
    are AND'ed, and a cursor continues only the filter set that issued it."""

    response.headers.update(NO_STORE)
    try:
        filters = ActivityFilters(
            since=since,
            until=until,
            actors=tuple(actor or ()),
            areas=tuple(area or ()),
            groups=tuple(action_group or ()),
        )
    except ValidationError:
        raise problem(
            request,
            status_code=422,
            code="invalid_date_range",
            title="Invalid date range",
            detail=f"`to` is before `from`, or a day is outside {_SPAN}.",
            headers=NO_STORE,
        ) from None
    try:
        before = decode_cursor(cursor, filters) if cursor else None
        if context is None:
            return ActivityPage(items=(), actors=() if before is None else None)
        return read_activity(
            context.service.authority,
            context.for_space(request, person.spaces),
            limit=limit,
            filters=filters,
            before=before,
        )
    except InvalidCursor:
        raise problem(
            request,
            status_code=422,
            code="invalid_cursor",
            title="Invalid cursor",
            detail="The cursor is not one this read issued for these filters.",
            headers=NO_STORE,
        ) from None
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
