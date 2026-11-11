from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from argus.api import state as api_state
from argus.api.conversation_surface import refuse_closed_chat, surface_scope
from argus.api.dependencies import current_user, problem
from argus.api.schemas import (
    Conversation,
    ConversationCreate,
    ConversationResponse,
    PaginatedConversations,
    User,
)
from argus.domain.owner_scope import space_id, surface_of
from argus.domain.store import utcnow

router = APIRouter(prefix="/api/v1", tags=["conversations"])


def _remember(
    *,
    title: str,
    title_source: str,
    language: str | None,
    scope,
    user_id: str,
) -> Conversation:
    now = utcnow()
    conversation = Conversation(
        id=api_state.store.new_id(),
        title=title,
        title_source=title_source,
        language=language,
        created_at=now,
        updated_at=now,
        surface=surface_of(space_id(scope)),
    )
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user_id
    owner_space_id = space_id(scope)
    if owner_space_id is not None:
        api_state.store.conversation_spaces[conversation.id] = owner_space_id
    api_state.store.messages[conversation.id] = []
    return conversation


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    payload: ConversationCreate,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> ConversationResponse:
    scope = surface_scope(request, user_id=user.id, surface=payload.surface)
    refuse_closed_chat(request, payload.surface)
    title = payload.title or "New idea"
    conversation = _remember(
        title=title,
        title_source="user_renamed" if payload.title else "system_default",
        language=payload.language or user.language,
        scope=scope,
        user_id=user.id,
    )
    return ConversationResponse(conversation=conversation)


@router.get("/conversations", response_model=PaginatedConversations)
def list_conversations(
    request: Request,
    surface: str = Query("personal"),
    user: User = Depends(current_user),  # noqa: B008
) -> PaginatedConversations:
    scope = surface_scope(request, user_id=user.id, surface=surface)  # type: ignore[arg-type]
    refuse_closed_chat(request, surface)  # type: ignore[arg-type]
    owner_space_id = space_id(scope)
    items = [
        conversation
        for conversation in api_state.store.conversations.values()
        if api_state.store.conversation_owners.get(conversation.id) == user.id
        and api_state.store.conversation_spaces.get(conversation.id) == owner_space_id
    ]
    return PaginatedConversations(items=items)


def _guard(request: Request, user: User, conversation_id: str) -> Conversation:
    conversation = api_state.store.conversations.get(conversation_id)
    if conversation is None or api_state.store.conversation_owners.get(conversation_id) != user.id:
        raise problem(
            request,
            status_code=404,
            code="conversation_not_found",
            title="Not Found",
            detail="Conversation not found.",
        )
    if conversation.surface == "business":
        surface_scope(request, user_id=user.id, surface="business")
    return conversation


@router.api_route("/conversations/{conversation_id}", methods=["PATCH", "DELETE"])
@router.api_route(
    "/conversations/{conversation_id}/{rest:path}",
    methods=["GET", "POST", "PATCH", "DELETE"],
)
def follow_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    rest: str = "",
) -> dict[str, str]:
    del rest
    return {"id": _guard(request, user, conversation_id).id}
