from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from argus.api import state as api_state
from argus.api.conversation_previews import conversation_previews
from argus.api.conversation_surface import (
    memory_conversation_in_scope,
    refuse_closed_chat,
    require_open_business_chat,
    surface_scope,
)
from argus.api.dependencies import current_user, problem, require_account_capability
from argus.api.pagination import decode_cursor, encode_cursor
from argus.api.schemas import (
    BulkConversationDeleteResponse,
    Conversation,
    ConversationActivity,
    ConversationAttention,
    ConversationCreate,
    ConversationOperation,
    ConversationPatch,
    ConversationResponse,
    HistoryItem,
    PaginatedConversations,
    PaginatedHistory,
    PaginatedMessages,
    PaginatedSearch,
    SearchItem,
    SearchMatch,
    User,
)
from argus.domain.owner_scope import space_id, surface_of
from argus.domain.store import utcnow

router = APIRouter(prefix="/api/v1", tags=["conversations"])
def _remember(title: str, title_source: str, language: str | None, scope, user_id: str) -> Conversation:
    now, owner_space = utcnow(), space_id(scope)
    conversation = Conversation(
        id=api_state.store.new_id(), title=title, title_source=title_source, language=language,
        created_at=now, updated_at=now, surface=surface_of(owner_space),
    )
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user_id
    if owner_space is not None:
        api_state.store.conversation_spaces[conversation.id] = owner_space
    api_state.store.messages[conversation.id] = []
    return conversation
def _owned(request: Request, user: User, conversation_id: str) -> Conversation:
    conversation = api_state.store.conversations.get(conversation_id)
    if conversation is None or api_state.store.conversation_owners.get(conversation_id) != user.id:
        raise problem(request, status_code=404, code="conversation_not_found", title="Not Found", detail="Conversation not found.")
    if conversation.surface == "business":
        surface_scope(request, user_id=user.id, surface="business")
    return conversation
def _rows(user: User, scope, *, deleted: bool | None = False, archived: bool | None = None) -> list[Conversation]:
    return [
        conversation for conversation in api_state.store.conversations.values()
        if api_state.store.conversation_owners.get(conversation.id) == user.id
        and memory_conversation_in_scope(conversation.id, scope)
        and (deleted is None or (conversation.deleted_at is not None) is deleted)
        and (archived is None or conversation.archived is archived)
    ]
def _activity(conversation: Conversation) -> ConversationActivity:
    messages = api_state.store.messages.get(conversation.id, [])
    return ConversationActivity(
        operation=ConversationOperation(status="idle"),
        attention=ConversationAttention(status="none"),
        latest_message_id=messages[-1].id if messages else None,
    )
def _missing(request: Request, conversation: Conversation | None) -> None:
    detail = "Conversation not found." if conversation is not None and conversation.surface == "business" else "Not Found"
    raise problem(request, status_code=404, code="not_found", title="Not Found", detail=detail)
@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(payload: ConversationCreate, request: Request, user: User = Depends(current_user)) -> ConversationResponse:  # noqa: B008
    scope = surface_scope(request, user_id=user.id, surface=payload.surface)
    refuse_closed_chat(request, payload.surface)
    return ConversationResponse(conversation=_remember(
        payload.title or "New idea", "user_renamed" if payload.title else "system_default",
        payload.language or user.language, scope, user.id,
    ))
@router.get("/conversations", response_model=PaginatedConversations)
def list_conversations(request: Request, surface: str = Query("personal"), user: User = Depends(current_user)) -> PaginatedConversations:  # noqa: B008
    return PaginatedConversations(items=_rows(user, surface_scope(request, user_id=user.id, surface=surface)))  # type: ignore[arg-type]
@router.delete("/conversations", response_model=BulkConversationDeleteResponse)
def delete_conversations(request: Request, surface: str = Query("personal"), user: User = Depends(current_user)) -> BulkConversationDeleteResponse:  # noqa: B008
    scope = surface_scope(request, user_id=user.id, surface=surface)  # type: ignore[arg-type]
    require_account_capability(request, "can_manage_conversation", detail="Sign in to manage saved conversations.", reason="keep_history")
    now, deleted = utcnow(), 0
    for conversation in _rows(user, scope):
        api_state.store.conversations[conversation.id] = conversation.model_copy(update={"deleted_at": now, "updated_at": now})
        deleted += 1
    return BulkConversationDeleteResponse(success=True, deleted_count=deleted)
@router.get("/conversations/{conversation_id}/messages", response_model=PaginatedMessages)
def list_messages(
    conversation_id: str, request: Request, limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None), anchor_message_id: str | None = Query(None),
    user: User = Depends(current_user),  # noqa: B008
) -> PaginatedMessages:
    if cursor is not None and anchor_message_id is not None:
        raise problem(request, status_code=422, code="invalid_message_anchor", title="Invalid Message Anchor", detail="A message anchor cannot be combined with a cursor.")
    conversation = _owned(request, user, conversation_id)
    items = sorted(api_state.store.messages.get(conversation_id, []), key=lambda item: (item.created_at, item.id))
    if cursor is not None:
        stamp, message_id = decode_cursor(cursor, request)
        try:
            cursor_at = datetime.fromisoformat(stamp)
        except ValueError:
            raise problem(request, status_code=400, code="validation_error", title="Validation Error", detail="Invalid cursor.") from None
        items = [item for item in items if (item.created_at, item.id) > (cursor_at, message_id)]
    if anchor_message_id is not None:
        anchors = [item for item in items if item.id == anchor_message_id]
        if len(anchors) != 1:
            raise problem(request, status_code=404, code="not_found", title="Not Found", detail="Message anchor not found.")
        items = [item for item in items if (item.created_at, item.id) >= (anchors[0].created_at, anchors[0].id)]
    page, last = items[:limit], None
    if len(items) > limit and page:
        last = page[-1]
    return PaginatedMessages(
        items=page, surface=conversation.surface,
        next_cursor=encode_cursor(last.created_at.isoformat(), last.id) if last else None,
    )
@router.get("/conversations/{conversation_id}/activity")
def read_activity(conversation_id: str, request: Request, user: User = Depends(current_user)) -> ConversationActivity:  # noqa: B008
    return _activity(_owned(request, user, conversation_id))
@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
def patch_conversation(conversation_id: str, payload: ConversationPatch, request: Request, user: User = Depends(current_user)) -> ConversationResponse:  # noqa: B008
    conversation = _owned(request, user, conversation_id)
    update = payload.model_dump(exclude_unset=True)
    if update:
        update["updated_at"] = utcnow()
        conversation = conversation.model_copy(update=update)
        api_state.store.conversations[conversation_id] = conversation
    return ConversationResponse(conversation=conversation)
@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request, user: User = Depends(current_user)) -> dict[str, bool]:  # noqa: B008
    conversation = _owned(request, user, conversation_id)
    now = utcnow()
    api_state.store.conversations[conversation_id] = conversation.model_copy(update={"deleted_at": now, "updated_at": now})
    return {"success": True}
@router.get("/history", response_model=PaginatedHistory)
def history(
    request: Request, limit: int = Query(20, ge=1, le=100), archived: bool = Query(False),
    deleted: bool = Query(False), surface: str = Query("personal"), user: User = Depends(current_user),  # noqa: B008
) -> PaginatedHistory:
    scope = surface_scope(request, user_id=user.id, surface=surface)  # type: ignore[arg-type]
    page = sorted(_rows(user, scope, deleted=deleted, archived=archived), key=lambda item: (item.pinned, item.updated_at, item.id), reverse=True)[:limit]
    previews = conversation_previews(user_id=user.id, conversation_ids=[item.id for item in page])
    return PaginatedHistory(items=[
        HistoryItem(
            type="chat", id=item.id, title=item.title, title_source=item.title_source,
            subtitle=previews[item.id].text or "", pinned=item.pinned, created_at=item.updated_at,
            activity=_activity(item), preview=previews[item.id],
        )
        for item in page
    ])
def _match(conversation: Conversation, query: str) -> tuple[str, str | None] | None:
    if not query or query in conversation.title.lower():
        return conversation.title, None
    for message in api_state.store.messages.get(conversation.id, []):
        if query in (message.content or "").lower():
            return message.content, message.id
    return None
@router.get("/search", response_model=PaginatedSearch)
def search(
    request: Request, q: str = Query("", max_length=512), limit: int = Query(20, ge=1, le=100),
    include_ledger_groups: bool = Query(False), conversation_id: list[str] | None = Query(None),  # noqa: B008
    surface: str = Query("personal"), user: User = Depends(current_user),  # noqa: B008
) -> PaginatedSearch:
    scope = surface_scope(request, user_id=user.id, surface=surface)  # type: ignore[arg-type]
    query, wanted, found = q.strip().lower(), set(conversation_id or []), []
    previews = conversation_previews(user_id=user.id, conversation_ids=[item.id for item in _rows(user, scope)])
    for conversation in _rows(user, scope):
        if wanted and conversation.id not in wanted:
            continue
        matched = _match(conversation, query)
        if matched is None:
            continue
        fragment, message_id = matched
        found.append(SearchItem(
            type="conversation", id=conversation.id, title=conversation.title, archived=conversation.archived,
            matched_text=fragment[:500], preview=previews[conversation.id], updated_at=conversation.updated_at,
            conversation_id=conversation.id, dossier=None, total_runs=0, decided_runs=0,
            match=SearchMatch(layer="message" if message_id else "conversation", fragment=fragment[:500], count=1, message_id=message_id),
        ))
        if len(found) >= limit:
            break
    return PaginatedSearch(items=found, ledger_groups=[] if include_ledger_groups else None)
@router.api_route("/conversations/{conversation_id}/{rest:path}", methods=["POST"], dependencies=[Depends(require_open_business_chat)])
@router.api_route("/conversations/{conversation_id}/{rest:path}", methods=["GET", "PATCH", "DELETE"])
def closed_conversation_route(conversation_id: str, request: Request, rest: str = "", user: User = Depends(current_user)) -> None:  # noqa: B008
    del rest
    conversation = api_state.store.conversations.get(conversation_id)
    if conversation is not None and conversation.surface == "business":
        surface_scope(request, user_id=user.id, surface="business")
    owned = conversation if api_state.store.conversation_owners.get(conversation_id) == user.id else None
    _missing(request, owned)
@router.api_route("/evidence-artifacts/{artifact_id}/{rest:path}", methods=["GET", "POST", "PATCH", "DELETE"])
def closed_artifact_route(artifact_id: str, request: Request, rest: str = "", user: User = Depends(current_user)) -> None:  # noqa: B008
    del rest, user
    artifact = api_state.store.evidence_artifacts.get(artifact_id)
    conversation_id = getattr(artifact, "source_conversation_id", None)
    _missing(request, api_state.store.conversations.get(conversation_id) if conversation_id else None)
