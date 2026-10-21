from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

from fastapi import APIRouter, Depends, Query, Request

from argus.api import state as api_state
from argus.api.conversation_activity import conversation_activity_service
from argus.api.conversation_previews import conversation_previews
from argus.api.conversation_surface import memory_conversation_in_scope, surface_scope
from argus.api.dependencies import current_user
from argus.api.guest_access import account_context
from argus.api.memory_ownership import memory_object_visible
from argus.api.pagination import decode_cursor, encode_cursor, invalid_cursor_problem
from argus.api.schemas import (
    BacktestRun,
    Conversation,
    ConversationSurface,
    HistoryItem,
    PaginatedHistory,
    User,
)
from argus.api.search_utils import search_type_rank
from argus.domain.owner_scope import holds
from argus.domain.postgres_history_reader import HistoryCursorError

router = APIRouter(prefix="/api/v1", tags=["history"])

_HISTORY_CURSOR_VERSION = "h1"


def _decode_history_cursor(
    cursor: str,
    request: Request,
) -> tuple[str, str, bool | None, int | None]:
    timestamp: str
    encoded_id: str
    timestamp, encoded_id = decode_cursor(cursor, request)
    prefix = f"{_HISTORY_CURSOR_VERSION}:"
    if not encoded_id.startswith(prefix):
        return timestamp, encoded_id, None, None

    parts = encoded_id.split(":", 3)
    if len(parts) != 4:
        raise invalid_cursor_problem(request)
    _, pinned_text, type_rank_text, item_id = parts
    if pinned_text not in {"0", "1"} or not item_id:
        raise invalid_cursor_problem(request)
    try:
        type_rank = int(type_rank_text)
    except ValueError:
        raise invalid_cursor_problem(request) from None
    if type_rank not in {1, 2, 3, 4}:
        raise invalid_cursor_problem(request)
    return timestamp, item_id, pinned_text == "1", type_rank


def _encode_history_cursor(item: HistoryItem) -> str:
    type_rank = search_type_rank(item.type)
    ranked_id = f"{_HISTORY_CURSOR_VERSION}:{int(item.pinned)}:{type_rank}:{item.id}"
    return cast(str, encode_cursor(item.created_at.isoformat(), ranked_id))


@router.get("/history", response_model=PaginatedHistory)
def history(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    archived: bool = Query(False),
    deleted: bool = Query(False),
    surface: ConversationSurface = Query("personal"),  # noqa: B008
    user: User = Depends(current_user),  # noqa: B008
) -> PaginatedHistory:
    scope = surface_scope(request, user_id=user.id, surface=surface)
    # Strategies and collections store no space, so they are Personal.
    spaceless_in_scope = holds(scope, None)
    context = account_context(request)
    if context.kind == "guest":
        if api_state.supabase_gateway is None:
            return PaginatedHistory(items=[], next_cursor=None)
        workspace = api_state.supabase_gateway.get_active_guest_workspace(
            user_id=user.id,
            at=datetime.now(timezone.utc),
        )
        if workspace is None or workspace.conversation_id is None:
            return PaginatedHistory(items=[], next_cursor=None)
        conversation = api_state.supabase_gateway.get_conversation(
            user_id=user.id,
            conversation_id=workspace.conversation_id,
        )
        if (
            conversation is None
            or conversation.deleted_at is not None
            or conversation.archived is not archived
            or deleted
        ):
            return PaginatedHistory(items=[], next_cursor=None)
        activity = conversation_activity_service.project(
            user_id=user.id,
            conversation_ids=[conversation.id],
            reconcile=True,
        )[conversation.id]
        return PaginatedHistory(
            items=[
                HistoryItem(
                    type="chat",
                    id=conversation.id,
                    title=conversation.title,
                    title_source=conversation.title_source,
                    subtitle="",
                    preview=conversation_previews(
                        user_id=user.id, conversation_ids=[conversation.id]
                    )[conversation.id],
                    pinned=False,
                    created_at=conversation.updated_at,
                    conversation_id=conversation.id,
                    expires_at=workspace.expires_at,
                    activity=activity,
                )
            ],
            next_cursor=None,
        )
    cursor_dt: datetime | None = None
    cursor_id: str | None = None
    cursor_pinned: bool | None = None
    cursor_type_rank: int | None = None
    if cursor:
        (
            cursor_created_at,
            cursor_id,
            cursor_pinned,
            cursor_type_rank,
        ) = _decode_history_cursor(cursor, request)
        try:
            cursor_dt = datetime.fromisoformat(cursor_created_at)
        except ValueError:
            raise invalid_cursor_problem(request) from None

    gateway = api_state.supabase_gateway
    persistent_history = gateway is not None
    if gateway is not None:
        try:
            raw = gateway.list_history_rows(
                user_id=user.id,
                scope=scope,
                limit=limit + 1,
                cursor_activity_at=cursor_dt,
                cursor_id=cursor_id,
                archived=archived,
                deleted=deleted,
                cursor_pinned=cursor_pinned,
                cursor_type_rank=cursor_type_rank,
            )
        except HistoryCursorError:
            raise invalid_cursor_problem(request) from None
        items: list[HistoryItem] = []
        for run in raw["runs"]:
            items.append(
                HistoryItem(
                    type="run",
                    id=run["id"],
                    title=run["conversation_result_card"]["title"],
                    subtitle=run["conversation_result_card"]["rows"][0]["value"],
                    created_at=run["created_at"],
                    conversation_id=run.get("conversation_id"),
                )
            )
        for conversation_row in raw["conversations"]:
            items.append(
                HistoryItem(
                    type="chat",
                    id=conversation_row["id"],
                    title=conversation_row["title"],
                    title_source=conversation_row["title_source"],
                    subtitle="",
                    pinned=conversation_row["pinned"],
                    created_at=conversation_row["updated_at"],
                )
            )
        for strategy_row in raw["strategies"]:
            items.append(
                HistoryItem(
                    type="strategy",
                    id=strategy_row["id"],
                    title=strategy_row["name"],
                    subtitle=", ".join(strategy_row["symbols"]),
                    pinned=strategy_row["pinned"],
                    created_at=strategy_row["updated_at"],
                )
            )
        for collection_row in raw["collections"]:
            items.append(
                HistoryItem(
                    type="collection",
                    id=collection_row["id"],
                    title=collection_row["name"],
                    subtitle=(f"{collection_row.get('strategy_count', 0)} strategies"),
                    pinned=collection_row["pinned"],
                    created_at=collection_row["updated_at"],
                )
            )
    else:
        items = []
        for run_id, run in api_state.store.backtest_runs.items():
            if not memory_object_visible(
                owner_map=api_state.store.backtest_run_owners,
                object_id=run_id,
                user_id=user.id,
            ) or not memory_conversation_in_scope(run.conversation_id or "", scope):
                continue
            if _run_matches_history_filters(
                run,
                api_state.store.conversations,
                archived=archived,
                deleted=deleted,
            ):
                items.append(
                    HistoryItem(
                        type="run",
                        id=run.id,
                        title=run.conversation_result_card["title"],
                        subtitle=run.conversation_result_card["rows"][0]["value"],
                        created_at=run.created_at,
                        conversation_id=run.conversation_id,
                    )
                )
        for stored_conversation in api_state.store.conversations.values():
            if not memory_object_visible(
                owner_map=api_state.store.conversation_owners,
                object_id=stored_conversation.id,
                user_id=user.id,
            ) or not memory_conversation_in_scope(stored_conversation.id, scope):
                continue
            if (
                stored_conversation.deleted_at is not None
                if deleted
                else stored_conversation.deleted_at is None
            ) and stored_conversation.archived is archived:
                items.append(
                    HistoryItem(
                        type="chat",
                        id=stored_conversation.id,
                        title=stored_conversation.title,
                        title_source=stored_conversation.title_source,
                        subtitle="",
                        pinned=stored_conversation.pinned,
                        created_at=stored_conversation.updated_at,
                    )
                )
        for stored_strategy in api_state.store.strategies.values():
            if (
                not memory_object_visible(
                    owner_map=api_state.store.strategy_owners,
                    object_id=stored_strategy.id,
                    user_id=user.id,
                )
                or not spaceless_in_scope
            ):
                continue
            if (
                stored_strategy.deleted_at is not None
                if deleted
                else stored_strategy.deleted_at is None
            ):
                items.append(
                    HistoryItem(
                        type="strategy",
                        id=stored_strategy.id,
                        title=stored_strategy.name,
                        subtitle=", ".join(stored_strategy.symbols),
                        pinned=stored_strategy.pinned,
                        created_at=stored_strategy.updated_at,
                    )
                )
        for stored_collection in api_state.store.collections.values():
            if (
                not memory_object_visible(
                    owner_map=api_state.store.collection_owners,
                    object_id=stored_collection.id,
                    user_id=user.id,
                )
                or not spaceless_in_scope
            ):
                continue
            if (
                stored_collection.deleted_at is not None
                if deleted
                else stored_collection.deleted_at is None
            ):
                items.append(
                    HistoryItem(
                        type="collection",
                        id=stored_collection.id,
                        title=stored_collection.name,
                        subtitle=f"{stored_collection.strategy_count} strategies",
                        pinned=stored_collection.pinned,
                        created_at=stored_collection.updated_at,
                    )
                )

    items.sort(
        key=lambda item: (
            int(item.pinned),
            item.created_at,
            search_type_rank(item.type),
            item.id,
        ),
        reverse=True,
    )
    filtered = items
    if cursor and not persistent_history:
        assert cursor_dt is not None
        assert cursor_id is not None
        cursor_item = next(
            (
                item
                for item in items
                if item.id == cursor_id and item.created_at == cursor_dt
            ),
            None,
        )
        if cursor_item is None:
            raise invalid_cursor_problem(request)
        cursor_key = (
            int(cursor_item.pinned),
            cursor_dt,
            search_type_rank(cursor_item.type),
            cursor_id,
        )
        filtered = [
            item
            for item in items
            if (
                int(item.pinned),
                item.created_at,
                search_type_rank(item.type),
                item.id,
            )
            < cursor_key
        ]
    page = filtered[: limit + 1]
    has_more = len(page) > limit
    page_items = page[:limit]
    chat_ids = [item.id for item in page_items if item.type == "chat"]
    activities = conversation_activity_service.project(
        user_id=user.id,
        conversation_ids=chat_ids,
        reconcile=True,
    )
    previews = conversation_previews(user_id=user.id, conversation_ids=chat_ids)
    page_items = [
        item.model_copy(
            update={
                "activity": activities[item.id],
                "preview": previews[item.id],
                "subtitle": previews[item.id].text or "",
            }
        )
        if item.type == "chat"
        else item
        for item in page_items
    ]
    next_cursor = None
    if has_more and page_items:
        last = page_items[-1]
        next_cursor = _encode_history_cursor(last)
    return PaginatedHistory(items=page_items, next_cursor=next_cursor)


def _conversation_matches_history_filters(
    conversation: Conversation,
    *,
    archived: bool,
    deleted: bool,
) -> bool:
    deleted_matches = (
        conversation.deleted_at is not None
        if deleted
        else conversation.deleted_at is None
    )
    return deleted_matches and conversation.archived == archived


def _run_matches_history_filters(
    run: BacktestRun,
    conversations: Mapping[str, Conversation],
    *,
    archived: bool,
    deleted: bool,
) -> bool:
    if not run.conversation_id:
        return not archived and not deleted
    conversation = conversations.get(run.conversation_id)
    if conversation is None:
        return not archived and not deleted
    return _conversation_matches_history_filters(
        conversation,
        archived=archived,
        deleted=deleted,
    )
