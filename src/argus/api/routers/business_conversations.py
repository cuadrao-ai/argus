from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from argus.api import state as api_state
from argus.api.conversation_activity import conversation_activity_service
from argus.api.conversation_previews import conversation_previews
from argus.api.conversation_surface import (
    conversation_not_found,
    conversation_scope,
    memory_conversation_in_scope,
    refuse_closed_chat,
    require_open_business_chat,
    surface_scope,
)
from argus.api.dependencies import current_user, problem, require_account_capability
from argus.api.pagination import decode_cursor, encode_cursor, invalid_cursor_problem
from argus.api.routers.history import history
from argus.api.routers.search import search
from argus.api.schemas import (
    BulkConversationDeleteResponse,
    Conversation,
    ConversationCreate,
    ConversationPatch,
    ConversationResponse,
    ConversationSurface,
    PaginatedConversations,
    PaginatedHistory,
    PaginatedMessages,
    PaginatedSearch,
    User,
)
from argus.domain.owner_scope import OwnerScope, space_id, surface_of
from argus.domain.store import utcnow
from argus.domain.supabase_gateway import (
    ConversationCursorError,
    MessageAnchorError,
    MessageCursorError,
)


def _require_storage(request: Request) -> None:
    if api_state.supabase_gateway is None and api_state.PERSISTENCE_MODE != "memory":
        raise problem(
            request,
            status_code=503,
            code="conversation_storage_unavailable",
            title="Service Unavailable",
            detail="Conversation storage is unavailable.",
        )


router = APIRouter(
    prefix="/api/v1", tags=["conversations"], dependencies=[Depends(_require_storage)]
)
router.add_api_route(
    "/history", history, methods=["GET"], response_model=PaginatedHistory
)

router.add_api_route("/search", search, methods=["GET"], response_model=PaginatedSearch)


def _remember(
    title: str, title_source: str, language: str | None, scope: OwnerScope, user_id: str
) -> Conversation:
    now, owner_space = utcnow(), space_id(scope)
    conversation = Conversation(
        id=api_state.store.new_id(),
        title=title,
        title_source=title_source,
        language=language,
        created_at=now,
        updated_at=now,
        surface=surface_of(owner_space),
    )
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user_id
    if owner_space is not None:
        api_state.store.conversation_spaces[conversation.id] = owner_space
    api_state.store.messages[conversation.id] = []
    return conversation


def _owned(request: Request, user: User, conversation_id: str) -> Conversation:
    gateway = api_state.supabase_gateway
    stored_scope = conversation_scope(user_id=user.id, conversation_id=conversation_id)
    if stored_scope is None:
        raise conversation_not_found(request)
    if gateway is not None:
        conversation = gateway.get_conversation(
            user_id=user.id, conversation_id=conversation_id
        )
    else:
        conversation = api_state.store.conversations.get(conversation_id)
        if api_state.store.conversation_owners.get(conversation_id) != user.id:
            conversation = None
    if conversation is None:
        raise conversation_not_found(request)
    if conversation.surface == "business":
        scope = surface_scope(request, user_id=user.id, surface="business")
        if stored_scope != scope:
            raise conversation_not_found(request)
    return conversation


def _rows(
    user: User, scope: OwnerScope, *, deleted: bool = False, archived: bool | None = None
) -> list[Conversation]:
    return [
        conversation
        for conversation in api_state.store.conversations.values()
        if api_state.store.conversation_owners.get(conversation.id) == user.id
        and memory_conversation_in_scope(conversation.id, scope)
        and (conversation.deleted_at is not None) is deleted
        and (archived is None or conversation.archived is archived)
    ]


def _with_activity(conversations: list[Conversation], user_id: str) -> list[Conversation]:
    if not conversations:
        return []
    activities = conversation_activity_service.project(
        user_id=user_id,
        conversation_ids=[item.id for item in conversations],
        reconcile=True,
    )
    previews = conversation_previews(
        user_id=user_id, conversation_ids=[item.id for item in conversations]
    )
    return [
        item.model_copy(
            update={
                "activity": activities[item.id],
                "preview": previews[item.id],
                "last_message_preview": previews[item.id].text,
            }
        )
        for item in conversations
    ]


def _cursor(cursor: str | None, request: Request) -> tuple[datetime | None, str | None]:
    if cursor is None:
        return None, None
    stamp, item_id = decode_cursor(cursor, request)
    try:
        at = datetime.fromisoformat(stamp)
    except ValueError:
        raise invalid_cursor_problem(request) from None
    if at.tzinfo is None or at.utcoffset() is None:
        raise invalid_cursor_problem(request)
    return at, item_id


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    payload: ConversationCreate,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> ConversationResponse:  # noqa: B008
    scope = surface_scope(request, user_id=user.id, surface=payload.surface)
    refuse_closed_chat(request, payload.surface)
    fields = {
        "title": payload.title or "New idea",
        "title_source": "user_renamed" if payload.title else "system_default",
        "language": payload.language or user.language,
        "scope": scope,
        "user_id": user.id,
    }
    gateway = api_state.supabase_gateway
    created = (
        gateway.create_conversation(**fields)
        if gateway is not None
        else _remember(**fields)
    )
    return ConversationResponse(conversation=_with_activity([created], user.id)[0])


@router.get("/conversations", response_model=PaginatedConversations)
def list_conversations(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    archived: bool | None = Query(None),
    deleted: bool = Query(False),
    surface: ConversationSurface = Query("personal"),  # noqa: B008
    user: User = Depends(current_user),  # noqa: B008
) -> PaginatedConversations:
    scope = surface_scope(request, user_id=user.id, surface=surface)
    at, item_id = _cursor(cursor, request)
    gateway = api_state.supabase_gateway
    if gateway is not None:
        try:
            rows = gateway.list_conversations(
                user_id=user.id,
                scope=scope,
                limit=limit,
                archived=archived,
                deleted=deleted,
                cursor_updated_at=at,
                cursor_id=item_id,
            )
        except ConversationCursorError:
            raise invalid_cursor_problem(request) from None
    else:
        rows = sorted(
            _rows(user, scope, deleted=deleted, archived=archived),
            key=lambda row: (row.pinned, row.updated_at, row.id),
            reverse=True,
        )
        if at is not None:
            pivot = next(
                (row for row in rows if row.id == item_id and row.updated_at == at), None
            )
            if pivot is None:
                raise invalid_cursor_problem(request)
            rows = [
                row
                for row in rows
                if (row.pinned, row.updated_at, row.id) < (pivot.pinned, at, item_id)
            ]
    page = rows[:limit]
    next_cursor = (
        encode_cursor(page[-1].updated_at.isoformat(), page[-1].id)
        if len(rows) > limit
        else None
    )
    return PaginatedConversations(
        items=_with_activity(page, user.id), next_cursor=next_cursor
    )


@router.delete("/conversations", response_model=BulkConversationDeleteResponse)
def delete_conversations(
    request: Request,
    surface: ConversationSurface = Query("personal"),  # noqa: B008
    user: User = Depends(current_user),  # noqa: B008
) -> BulkConversationDeleteResponse:  # noqa: B008
    scope = surface_scope(request, user_id=user.id, surface=surface)
    require_account_capability(
        request,
        "can_manage_conversation",
        detail="Sign in to manage saved conversations.",
        reason="keep_history",
    )
    gateway = api_state.supabase_gateway
    if gateway is not None:
        deleted = gateway.soft_delete_all_conversations(user_id=user.id, scope=scope)
    else:
        now, deleted = utcnow(), 0
        for conversation in _rows(user, scope):
            api_state.store.conversations[conversation.id] = conversation.model_copy(
                update={"deleted_at": now, "updated_at": now}
            )
            deleted += 1
    return BulkConversationDeleteResponse(success=True, deleted_count=deleted)


@router.get("/conversations/{conversation_id}/messages", response_model=PaginatedMessages)
def list_messages(
    conversation_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
    anchor_message_id: str | None = Query(None),
    user: User = Depends(current_user),  # noqa: B008
) -> PaginatedMessages:
    if cursor is not None and anchor_message_id is not None:
        raise problem(
            request,
            status_code=422,
            code="invalid_message_anchor",
            title="Invalid Message Anchor",
            detail="A message anchor cannot be combined with a cursor.",
        )
    conversation = _owned(request, user, conversation_id)
    if conversation.deleted_at is not None:
        raise conversation_not_found(request)
    at, item_id = _cursor(cursor, request)
    gateway = api_state.supabase_gateway
    if gateway is not None:
        try:
            items = gateway.list_messages(
                user_id=user.id,
                conversation_id=conversation_id,
                limit=limit,
                page=True,
                cursor_created_at=at,
                cursor_id=item_id,
                anchor_message_id=anchor_message_id,
            )
        except MessageCursorError:
            raise invalid_cursor_problem(request) from None
        except MessageAnchorError:
            raise problem(
                request,
                status_code=404,
                code="not_found",
                title="Not Found",
                detail="Message anchor not found.",
            ) from None
    else:
        items = sorted(
            api_state.store.messages.get(conversation_id, []),
            key=lambda item: (item.created_at, item.id),
        )
        if at is not None:
            items = [item for item in items if (item.created_at, item.id) > (at, item_id)]
        if anchor_message_id is not None:
            anchors = [item for item in items if item.id == anchor_message_id]
            if len(anchors) != 1:
                raise problem(
                    request,
                    status_code=404,
                    code="not_found",
                    title="Not Found",
                    detail="Message anchor not found.",
                )
            items = [
                item
                for item in items
                if (item.created_at, item.id) >= (anchors[0].created_at, anchors[0].id)
            ]
    page = items[:limit]
    last = page[-1] if len(items) > limit else None
    return PaginatedMessages(
        items=page,
        surface=conversation.surface,
        next_cursor=encode_cursor(last.created_at.isoformat(), last.id) if last else None,
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
def patch_conversation(
    conversation_id: str,
    payload: ConversationPatch,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> ConversationResponse:  # noqa: B008
    conversation = _owned(request, user, conversation_id)
    require_account_capability(
        request,
        "can_manage_conversation",
        detail="Sign in to manage saved conversations.",
        reason="keep_history",
    )
    update = payload.model_dump(exclude_unset=True)
    if update.get("title"):
        update["title_source"] = "user_renamed"
    gateway = api_state.supabase_gateway
    if gateway is not None:
        conversation = gateway.patch_conversation(
            user_id=user.id, conversation_id=conversation_id, patch=update
        )
        if conversation is None:
            raise conversation_not_found(request)
    elif update:
        update["updated_at"] = utcnow()
        conversation = conversation.model_copy(update=update)
        api_state.store.conversations[conversation_id] = conversation
    return ConversationResponse(conversation=_with_activity([conversation], user.id)[0])


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> dict[str, bool]:  # noqa: B008
    conversation = _owned(request, user, conversation_id)
    require_account_capability(
        request,
        "can_manage_conversation",
        detail="Sign in to manage saved conversations.",
        reason="keep_history",
    )
    gateway = api_state.supabase_gateway
    if gateway is not None:
        gateway.soft_delete_conversation(user_id=user.id, conversation_id=conversation_id)
    else:
        now = utcnow()
        api_state.store.conversations[conversation_id] = conversation.model_copy(
            update={"deleted_at": now, "updated_at": now}
        )
    return {"success": True}


def _missing(request: Request, conversation: Conversation | None) -> None:
    detail = (
        "Conversation not found."
        if conversation is not None and conversation.surface == "business"
        else "Not Found"
    )
    raise problem(
        request, status_code=404, code="not_found", title="Not Found", detail=detail
    )


@router.api_route(
    "/conversations/{conversation_id}/{rest:path}",
    methods=["POST"],
    dependencies=[Depends(require_open_business_chat)],
)
@router.api_route(
    "/conversations/{conversation_id}/{rest:path}", methods=["GET", "PATCH", "DELETE"]
)
def closed_conversation_route(
    conversation_id: str,
    request: Request,
    rest: str = "",
    user: User = Depends(current_user),  # noqa: B008
) -> None:  # noqa: B008
    del rest
    _missing(request, _owned(request, user, conversation_id))


@router.api_route(
    "/evidence-artifacts/{artifact_id}/{rest:path}",
    methods=["GET", "POST", "PATCH", "DELETE"],
)
def closed_artifact_route(
    artifact_id: str,
    request: Request,
    rest: str = "",
    user: User = Depends(current_user),  # noqa: B008
) -> None:  # noqa: B008
    del rest, user
    artifact = api_state.store.evidence_artifacts.get(artifact_id)
    conversation_id = getattr(artifact, "source_conversation_id", None)
    _missing(
        request,
        api_state.store.conversations.get(conversation_id) if conversation_id else None,
    )
