"""Computed answers outside a turn: list, compare, continue in a new chat, refresh."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from argus.api.business import own_business_only
from argus.api.chat.computed_answers import (
    ComputationSelectionError,
    ComputationUnsupportedError,
    ComputedAnswerNotFoundError,
    NothingToRefreshError,
    RefreshCapacityExhaustedError,
    RefreshUnavailableError,
    compare_computed_answers,
    computed_answers_of_kind,
    continue_computed_answer,
    refresh_computed_answer,
)
from argus.api.computation_contract import (
    ComputationCompareRequest,
    ComputationComparison,
    ComputationRefreshResponse,
    ComputedAnswerList,
    ContinuedResultResponse,
)
from argus.api.conversation_surface import require_open_business_chat, surface_scope
from argus.api.dependencies import current_user, problem, require_account_capability
from argus.api.schemas import ConversationSurface, User

router = APIRouter(prefix="/api/v1", tags=["computations"])


def _answer_problem(request: Request, exc: Exception):
    if isinstance(exc, ComputedAnswerNotFoundError):
        return problem(
            request, status_code=404, code="not_found", title="Not Found", detail=str(exc)
        )
    return problem(
        request,
        status_code=409,
        code="decision_attachment_unsupported",
        title="Decision Attachment Unsupported",
        detail=str(exc),
    )


@router.get("/computations/answers", response_model=ComputedAnswerList)
def list_computed_answers(
    request: Request,
    kind: str = Query(min_length=1, max_length=80),
    exclude_message_id: str | None = Query(default=None, max_length=64),
    surface: ConversationSurface = Query("personal"),  # noqa: B008
    user: User = Depends(current_user),  # noqa: B008
) -> ComputedAnswerList:
    scope = surface_scope(request, user_id=user.id, surface=surface)
    return ComputedAnswerList(
        items=computed_answers_of_kind(
            user=user, scope=scope, kind=kind, exclude_message_id=exclude_message_id
        )
    )


@router.post("/computations/compare", response_model=ComputationComparison)
def compare_computed_answers_route(
    payload: ComputationCompareRequest,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> ComputationComparison:
    try:
        return compare_computed_answers(user=user, left=payload.left, right=payload.right)
    except (ComputedAnswerNotFoundError, ComputationUnsupportedError) as exc:
        raise _answer_problem(request, exc) from exc
    except ComputationSelectionError as exc:
        raise problem(
            request,
            status_code=422,
            code="invalid_selection",
            title="Invalid Selection",
            detail=str(exc),
        ) from exc


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/continue",
    response_model=ContinuedResultResponse,
    dependencies=[Depends(require_open_business_chat)],
)
def continue_computed_answer_route(
    conversation_id: str,
    message_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> ContinuedResultResponse:
    # Chat is the owner's: a chosen client grant is refused on every chat route.
    own_business_only(request, user.id)
    require_account_capability(
        request,
        "can_create_additional_conversation",
        detail="Sign in to continue this result in a new chat.",
        reason="new_conversation",
    )
    try:
        conversation, message = continue_computed_answer(
            user=user, conversation_id=conversation_id, message_id=message_id
        )
    except (ComputedAnswerNotFoundError, ComputationUnsupportedError) as exc:
        raise _answer_problem(request, exc) from exc
    return ContinuedResultResponse(conversation=conversation, message_id=message.id)


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/computation/refresh",
    response_model=ComputationRefreshResponse,
    dependencies=[Depends(require_open_business_chat)],
)
async def refresh_computed_answer_route(
    conversation_id: str,
    message_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> ComputationRefreshResponse:
    # Chat is the owner's: a chosen client grant is refused on every chat route.
    own_business_only(request, user.id)
    from argus.api.chat.research_evidence import guest_research_visitor_key
    from argus.api.guest_access import account_context, client_identity

    visitor_key = guest_research_visitor_key(
        is_guest=account_context(request).kind == "guest",
        client_identity=client_identity(request),
        user_id=user.id,
    )
    try:
        return await refresh_computed_answer(
            user=user,
            conversation_id=conversation_id,
            message_id=message_id,
            guest_visitor_key=visitor_key,
        )
    except (ComputedAnswerNotFoundError, ComputationUnsupportedError) as exc:
        raise _answer_problem(request, exc) from exc
    except NothingToRefreshError as exc:
        raise problem(
            request,
            status_code=409,
            code="nothing_to_refresh",
            title="Nothing To Refresh",
            detail=str(exc),
        ) from exc
    except RefreshCapacityExhaustedError as exc:
        raise problem(
            request,
            status_code=429,
            code="research_capacity_exhausted",
            title="Research Capacity Exhausted",
            detail="Research is at its limit for now.",
            context={"guest_exhausted": exc.guest_exhausted},
        ) from exc
    except RefreshUnavailableError as exc:
        raise problem(
            request,
            status_code=503,
            code="research_unavailable",
            title="Research Unavailable",
            detail="The inputs could not be looked up right now.",
            context={"reason": exc.reason},
        ) from exc
