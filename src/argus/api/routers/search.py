from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from argus.api import state as api_state
from argus.api.client_capabilities import (
    ClientCapabilitiesHeader,
    dossier_decision_action_availability,
)
from argus.api.conversation_previews import conversation_previews
from argus.api.conversation_surface import surface_scope
from argus.api.dependencies import current_user, problem
from argus.api.guest_access import account_context
from argus.api.memory_ledger_index import MemoryLedgerWorkLimitExceeded
from argus.api.pagination import decode_cursor, encode_cursor, invalid_cursor_problem
from argus.api.schemas import (
    ConversationSurface,
    DecisionState,
    PaginatedSearch,
    SearchAssetRollup,
    SearchItem,
    SearchLedgerGroup,
    User,
)
from argus.api.search_assembly import (
    memory_search_read,
    scored_supabase_search_items,
)
from argus.api.search_computed import attach_answer_dossiers, with_computed_results
from argus.api.search_utils import search_rank_key
from argus.domain.postgres_search_reader import (
    SearchCursorError,
    SearchReadResult,
)
from argus.domain.search_text import (
    normalize_search_symbol,
    search_has_indexable_token,
    search_query_is_indexable,
)

router = APIRouter(prefix="/api/v1", tags=["search"])

LEDGER_DECISION_STATE_ORDER: tuple[DecisionState, ...] = (
    "promising",
    "watching",
    "rejected",
    "revisit_later",
)


@router.get("/search", response_model=PaginatedSearch)
def search(
    q: Annotated[str, Query(max_length=512)],
    request: Request,
    client_capabilities: ClientCapabilitiesHeader = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    decision_state: DecisionState | None = Query(None),  # noqa: B008
    include_ledger_groups: bool = Query(False),  # noqa: B008
    conversation_id: list[UUID] | None = Query(  # noqa: B008
        None,
        min_length=1,
        max_length=50,
    ),
    surface: ConversationSurface = Query("personal"),  # noqa: B008
    user: User = Depends(current_user),  # noqa: B008
) -> PaginatedSearch:
    scope = surface_scope(request, user_id=user.id, surface=surface)
    context = account_context(request)
    decision_action_availability = dossier_decision_action_availability(
        can_save_decision=context.capabilities.can_save_decision,
        raw_client_capabilities=client_capabilities,
    )
    query = q.strip().lower()
    requested_conversation_ids = list(
        dict.fromkeys(str(value) for value in (conversation_id or ()))
    )
    id_scoped_recall = bool(requested_conversation_ids)
    if id_scoped_recall and (
        query
        or cursor is not None
        or decision_state is not None
        or len(requested_conversation_ids) > limit
    ):
        raise problem(
            request,
            status_code=400,
            code="validation_error",
            title="Validation Error",
            detail=(
                "Visible conversation recall requires an empty query, no cursor "
                "or decision filter, and a limit covering every requested id."
            ),
        )

    cursor_dt: datetime | None = None
    cursor_id: str | None = None
    if cursor:
        cursor_updated_at, cursor_id = decode_cursor(cursor, request)
        try:
            cursor_dt = datetime.fromisoformat(cursor_updated_at)
        except ValueError:
            raise invalid_cursor_problem(request) from None
        if cursor_dt.tzinfo is None or cursor_dt.utcoffset() is None:
            raise invalid_cursor_problem(request)

    workspace_conversation_id: str | None = None
    if context.kind == "guest" and api_state.supabase_gateway is not None:
        workspace = api_state.supabase_gateway.get_active_guest_workspace(
            user_id=user.id,
            at=datetime.now(timezone.utc),
        )
        workspace_conversation_id = (
            workspace.conversation_id if workspace is not None else None
        )

    if query and not search_query_is_indexable(query):
        if cursor:
            raise invalid_cursor_problem(request)
        ledger_groups = (
            []
            if context.kind == "guest" and include_ledger_groups
            else _ledger_groups_from_counts(None)
            if include_ledger_groups
            else None
        )
        return PaginatedSearch(
            items=[],
            next_cursor=None,
            ledger_groups=ledger_groups,
        )

    text_search_enabled = not query or search_has_indexable_token(query)
    conversation_search_enabled = (
        text_search_enabled or normalize_search_symbol(query) is not None
    )
    if cursor and not conversation_search_enabled:
        raise invalid_cursor_problem(request)

    scored_items: list[tuple[int, SearchItem]] = []
    asset_rollup: SearchAssetRollup | None = None
    search_read: SearchReadResult | None = None
    memory_ledger_counts: dict[str, int] | None = None
    if api_state.supabase_gateway is not None:
        try:
            read_kwargs: dict[str, Any] = {
                "user_id": user.id,
                "scope": scope,
                "query": query,
                "source_limit": (
                    len(requested_conversation_ids) if id_scoped_recall else limit + 1
                ),
                "cursor_updated_at": cursor_dt,
                "cursor_id": cursor_id,
                "decision_state": decision_state,
                "include_ledger_groups": include_ledger_groups,
                "guest_scope": context.kind == "guest",
                "guest_conversation_id": workspace_conversation_id,
            }
            if id_scoped_recall:
                read_kwargs["conversation_ids"] = requested_conversation_ids
            read_result = api_state.supabase_gateway.search_rows(
                **read_kwargs,
            )
        except SearchCursorError:
            raise invalid_cursor_problem(request) from None
        if isinstance(read_result, SearchReadResult):
            search_read = read_result
            asset_rollup = read_result.asset_rollup
            raw = read_result.rows
        else:
            # Keep injected test gateways compatible while the production
            # Supabase gateway always returns the typed reader result.
            raw = read_result
        scored_items.extend(
            scored_supabase_search_items(
                raw=raw,
                query=query,
                decision_action_availability=decision_action_availability,
                language=user.language,
            )
        )
    else:
        try:
            memory_read = memory_search_read(
                user=user,
                scope=scope,
                query=query,
                source_limit=(
                    len(requested_conversation_ids) if id_scoped_recall else limit + 1
                ),
                decision_action_availability=decision_action_availability,
                include_conversation_rows=conversation_search_enabled,
                cursor_updated_at=cursor_dt,
                cursor_id=cursor_id,
                decision_state=decision_state,
                include_ledger_groups=include_ledger_groups,
                guest_conversation_id=workspace_conversation_id,
                conversation_ids=(
                    requested_conversation_ids if id_scoped_recall else None
                ),
            )
        except MemoryLedgerWorkLimitExceeded:
            raise problem(
                request,
                status_code=503,
                code="search_temporarily_unavailable",
                title="Search Temporarily Unavailable",
                detail=(
                    "Search is temporarily unavailable. Please refine your "
                    "query and try again."
                ),
            ) from None
        scored_items.extend(memory_read.scored_items)
        asset_rollup = memory_read.asset_rollup
        memory_ledger_counts = memory_read.ledger_counts

    if context.kind == "guest":
        # Defense in depth: the persistent reader applies this scope before
        # each source limit; this keeps non-production injected gateways safe.
        scored_items = [
            pair
            for pair in scored_items
            if workspace_conversation_id is not None
            and pair[1].conversation_id == workspace_conversation_id
        ]
    if id_scoped_recall:
        requested_ids = set(requested_conversation_ids)
        scored_items = [
            pair for pair in scored_items if pair[1].conversation_id in requested_ids
        ]

    scored_items.sort(
        key=lambda pair: search_rank_key(
            score=pair[0],
            kind=pair[1].type,
            updated_at=pair[1].updated_at,
            item_id=pair[1].id,
        ),
        reverse=True,
    )
    ledger_groups = (
        []
        if context.kind == "guest" and include_ledger_groups
        else _ledger_groups_from_counts(search_read.ledger_counts)
        if include_ledger_groups and search_read is not None
        else _ledger_groups_from_counts(memory_ledger_counts)
        if include_ledger_groups and memory_ledger_counts is not None
        else _ledger_groups_from_items(scored_items)
        if include_ledger_groups
        else None
    )
    if decision_state is not None:
        scored_items = [
            pair for pair in scored_items if decision_state in pair[1].decision_states
        ]
    filtered = scored_items
    if cursor and search_read is None:
        assert cursor_dt is not None
        assert cursor_id is not None
        cursor_pair = next(
            (
                pair
                for pair in scored_items
                if pair[1].id == cursor_id and pair[1].updated_at == cursor_dt
            ),
            None,
        )
        if cursor_pair is None:
            raise invalid_cursor_problem(request)
        cursor_score, cursor_item = cursor_pair
        cursor_key = search_rank_key(
            score=cursor_score,
            kind=cursor_item.type,
            updated_at=cursor_dt,
            item_id=cursor_id,
        )
        filtered = [
            pair
            for pair in scored_items
            if search_rank_key(
                score=pair[0],
                kind=pair[1].type,
                updated_at=pair[1].updated_at,
                item_id=pair[1].id,
            )
            < cursor_key
        ]

    page = filtered if id_scoped_recall else filtered[: limit + 1]
    has_more = False if id_scoped_recall else len(page) > limit
    page_items = page if id_scoped_recall else page[:limit]
    previews = conversation_previews(
        user_id=user.id, conversation_ids=[item.conversation_id for _, item in page_items]
    )
    page_items = [
        (
            score,
            item.model_copy(
                update={
                    "preview": previews[item.conversation_id],
                    "matched_text": item.matched_text
                    if item.match.layer == "message"
                    else "",
                    "match": item.match
                    if item.match.layer == "message"
                    else item.match.model_copy(update={"fragment": ""}),
                }
            ),
        )
        for score, item in page_items
    ]
    next_cursor = None
    if has_more and page_items:
        _, last_item = page_items[-1]
        next_cursor = encode_cursor(last_item.updated_at.isoformat(), last_item.id)
    # Computed answers join after the read: the run dossier projection and its
    # SQL stay as they are, and the asset row counts every result.
    hydrated_items = attach_answer_dossiers(
        [item for _, item in page_items],
        user=user,
        decision_action_availability=decision_action_availability,
    )
    page_items = list(
        zip((score for score, _ in page_items), hydrated_items, strict=True)
    )
    asset_rollup = with_computed_results(
        asset_rollup,
        user=user,
        scope=scope,
        query=query,
        guest_conversation_id=workspace_conversation_id,
    )
    return PaginatedSearch(
        items=[
            *([asset_rollup] if asset_rollup is not None else []),
            *(item for _, item in page_items),
        ],
        next_cursor=next_cursor,
        ledger_groups=ledger_groups,
    )


def _ledger_groups_from_items(
    scored_items: list[tuple[int, SearchItem]],
) -> list[SearchLedgerGroup]:
    counts: dict[DecisionState, int] = {state: 0 for state in LEDGER_DECISION_STATE_ORDER}
    for _, item in scored_items:
        for state in item.decision_states:
            counts[state] += 1
    return [
        SearchLedgerGroup(decision_state=state, count=counts[state])
        for state in LEDGER_DECISION_STATE_ORDER
    ]


def _ledger_groups_from_counts(
    counts: dict[str, int] | None,
) -> list[SearchLedgerGroup]:
    values = counts or {}
    return [
        SearchLedgerGroup(decision_state=state, count=int(values.get(state, 0)))
        for state in LEDGER_DECISION_STATE_ORDER
    ]
