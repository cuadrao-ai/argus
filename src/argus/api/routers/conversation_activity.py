from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from argus.api import state as api_state
from argus.api.conversation_activity import (
    ConversationActivityConflict,
    conversation_activity_service,
)
from argus.api.conversation_surface import refuse_business_under_grant
from argus.api.dependencies import current_user, problem
from argus.api.guest_access import account_context
from argus.api.schemas import (
    Conversation,
    ConversationActivity,
    ConversationActivityMarkRead,
    ConversationActivityPatch,
    User,
)
from argus.domain.conversation_activity import CursorShapeError, decode_attention_cursor

router = APIRouter(prefix="/api/v1", tags=["conversation-activity"])

_ERROR_CONTENT = {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}


def _not_found(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=404,
        code="not_found",
        title="Not Found",
        detail="Conversation not found.",
    )


def _visible_conversation(
    *,
    request: Request,
    user: User,
    conversation_id: str,
) -> Conversation:
    gateway = api_state.supabase_gateway
    if gateway is not None:
        conversation = gateway.get_conversation(
            user_id=user.id,
            conversation_id=conversation_id,
        )
    else:
        conversation = api_state.store.conversations.get(conversation_id)
        if api_state.store.conversation_owners.get(conversation_id) != user.id:
            conversation = None
    if conversation is None or conversation.deleted_at is not None:
        raise _not_found(request)

    context = account_context(request)
    if context.kind == "guest" and gateway is not None:
        workspace = gateway.get_active_guest_workspace(
            user_id=user.id,
            at=datetime.now(timezone.utc),
        )
        if workspace is None or workspace.conversation_id != conversation_id:
            raise _not_found(request)
    return Conversation.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}/activity",
    response_model=ConversationActivity,
    responses={
        404: {
            "description": "The conversation was not found or visible.",
            "content": _ERROR_CONTENT,
        },
    },
)
def get_conversation_activity(
    conversation_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> ConversationActivity:
    # Chat is the owner's: a chosen client grant is refused on a Business conversation.
    refuse_business_under_grant(request, user_id=user.id, conversation_id=conversation_id)
    _visible_conversation(request=request, user=user, conversation_id=conversation_id)
    return conversation_activity_service.project(
        user_id=user.id,
        conversation_ids=[conversation_id],
        reconcile=True,
    )[conversation_id]


@router.patch(
    "/conversations/{conversation_id}/activity",
    response_model=ConversationActivity,
    responses={
        403: {
            "description": "A guest cannot manually mark a task unread.",
            "content": _ERROR_CONTENT,
        },
        404: {
            "description": "The conversation was not found or visible.",
            "content": _ERROR_CONTENT,
        },
        409: {
            "description": "The supplied terminal source is no longer eligible.",
            "content": _ERROR_CONTENT,
        },
    },
)
def patch_conversation_activity(
    conversation_id: str,
    payload: ConversationActivityPatch,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> ConversationActivity:
    # Chat is the owner's: a chosen client grant is refused on a Business conversation.
    refuse_business_under_grant(request, user_id=user.id, conversation_id=conversation_id)
    _visible_conversation(request=request, user=user, conversation_id=conversation_id)
    context = account_context(request)
    if payload.action == "mark_unread" and context.kind == "guest":
        raise problem(
            request,
            status_code=403,
            code="account_conversion_required",
            title="Account Required",
            detail="Sign in to mark a conversation unread.",
            context={"reason": "mark_unread"},
        )

    cursor_source = None
    if isinstance(payload, ConversationActivityMarkRead):
        cursor = payload.through_attention_cursor
        if cursor is not None:
            try:
                cursor_source = decode_attention_cursor(cursor)
            except CursorShapeError:
                raise problem(
                    request,
                    status_code=422,
                    code="invalid_attention_cursor",
                    title="Invalid Attention Cursor",
                    detail="The activity cursor is malformed.",
                ) from None
    try:
        return conversation_activity_service.mutate(
            user_id=user.id,
            conversation_id=conversation_id,
            action=payload.action,
            cursor_source=cursor_source,
        )
    except KeyError:
        raise _not_found(request) from None
    except ConversationActivityConflict:
        raise problem(
            request,
            status_code=409,
            code="attention_cursor_conflict",
            title="Activity Changed",
            detail="That activity boundary is no longer valid for this conversation.",
        ) from None
