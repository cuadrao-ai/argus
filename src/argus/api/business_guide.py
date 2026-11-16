"""Person-scoped guide card preferences for the Business web app."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, get_args

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from loguru import logger
from psycopg import Error
from pydantic import BaseModel

from argus.api.business import BusinessPerson, MembershipRoute, require_business_person
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.schemas import GuideCardId


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


def _failed(request: Request, error: Error) -> None:
    logger.warning(
        "Business guide database request failed",
        request_id=getattr(request.state, "request_id", None),
        failure_mode=type(error).__name__,
    )


def dismissed_guide_cards(request: Request, user_id: str) -> list[GuideCardId] | None:
    """The guide cards this person dismissed, for `GET /me`; None when they cannot be read."""
    pool = getattr(getattr(request.scope.get("app"), "state", None), "financial_accounts_pool", None)
    if pool is None:
        return None
    try:
        with pool.connection() as connection:
            rows = connection.execute(
                "select card_id from public.business_guide_dismissals where user_id = %s",
                (user_id,),
            ).fetchall()
    except Error as error:
        _failed(request, error)
        return None
    dismissed = {card_id for (card_id,) in rows}
    return [card_id for card_id in get_args(GuideCardId) if card_id in dismissed]


@router.post("/guide-cards/{card_id}/dismiss")
def dismiss_guide_card(
    request: Request, person: Person, card_id: GuideCardId
) -> BusinessGuideState:
    """Dismiss this guide for the signed-in person. The Business grant is ignored."""
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None:
        raise _unavailable(request)
    try:
        with pool.connection() as connection:
            connection.execute(
                "insert into public.business_guide_dismissals (user_id, card_id)"
                " values (%s, %s) on conflict (user_id, card_id) do nothing",
                (person.person_id, card_id),
            )
    except Error as error:
        _failed(request, error)
        raise _unavailable(request) from None
    return BusinessGuideState(dismissed=True)
