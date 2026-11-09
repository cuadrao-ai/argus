"""Person-scoped guide card preferences for the Business web app."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from loguru import logger
from psycopg import Error
from pydantic import BaseModel

from argus.api.business import BusinessPerson, MembershipRoute, require_business_person
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE


class GuideRoute(MembershipRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                response = await original(request)
            except RequestValidationError as error:
                validation = request.app.exception_handlers.get(
                    RequestValidationError, request_validation_exception_handler
                )
                response = await validation(request, error)
            except HTTPException as error:
                error.headers = {**(error.headers or {}), **NO_STORE}
                raise
            response.headers.update(NO_STORE)
            return response

        return handler


router = APIRouter(
    route_class=GuideRoute,
    responses={403: {"description": "A registered account is required."}},
)

CardId = Literal["bandeja-intro"]
Person = Annotated[BusinessPerson, Depends(require_business_person)]


class BusinessGuideState(BaseModel):
    dismissed: bool


def _unavailable(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=503,
        code="business_guide_unavailable",
        title="Guide unavailable",
        detail="The guide preference could not be read or saved.",
        headers=NO_STORE,
    )


def _state(
    request: Request, person: BusinessPerson, card_id: CardId, *, dismiss: bool
) -> BusinessGuideState:
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None:
        raise _unavailable(request)
    key = (person.person_id, card_id)
    try:
        with pool.connection() as connection:
            if dismiss:
                connection.execute(
                    "insert into public.business_guide_dismissals (user_id, card_id)"
                    " values (%s, %s) on conflict (user_id, card_id) do nothing",
                    key,
                )
                dismissed = True
            else:
                dismissed = (
                    connection.execute(
                        "select 1 from public.business_guide_dismissals"
                        " where user_id = %s and card_id = %s",
                        key,
                    ).fetchone()
                    is not None
                )
    except Error as error:
        logger.warning(
            "Business guide database request failed",
            request_id=getattr(request.state, "request_id", None),
            failure_mode=type(error).__name__,
        )
        raise _unavailable(request) from None
    return BusinessGuideState(dismissed=dismissed)


@router.get("/guide-cards/{card_id}")
def get_guide_card(
    request: Request, person: Person, card_id: CardId
) -> BusinessGuideState:
    """Read the signed-in person's guide state. The Business grant is ignored."""
    return _state(request, person, card_id, dismiss=False)


@router.post("/guide-cards/{card_id}/dismiss")
def dismiss_guide_card(
    request: Request, person: Person, card_id: CardId
) -> BusinessGuideState:
    """Dismiss this guide for the signed-in person. The Business grant is ignored."""
    return _state(request, person, card_id, dismiss=True)
