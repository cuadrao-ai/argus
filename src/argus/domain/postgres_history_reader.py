from __future__ import annotations

import atexit
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from argus.domain.owner_scope import (
    PERSONAL,
    SCOPE_PARAMETER,
    BusinessSpace,
    OwnerScope,
    space_id,
    sql_named_predicate,
)

_HISTORY_CONNECT_TIMEOUT_SECONDS = 2
_HISTORY_ACQUIRE_TIMEOUT_SECONDS = 2.0
_HISTORY_STATEMENT_TIMEOUT_MS = 2_000
_HISTORY_POOL_SIZE = 5


class HistoryCursorError(ValueError):
    """Raised when a merged History cursor pivot cannot be resolved exactly."""


_PIVOT_SQL = """
select source_type, pinned, type_rank, activity_at
from (
    select
        'run'::text as source_type,
        false as pinned,
        1 as type_rank,
        run.created_at as activity_at
    from public.backtest_runs as run
    where run.user_id = %s
      and run.id = %s

    union all

    select
        'chat'::text as source_type,
        chat.pinned,
        4 as type_rank,
        chat.updated_at as activity_at
    from public.conversations as chat
    where chat.user_id = %s
      and chat.id = %s
      and exists (
          select 1
          from public.messages as message
          where message.user_id = %s
            and message.conversation_id = chat.id
      )

    union all

    select
        'strategy'::text as source_type,
        strategy.pinned,
        3 as type_rank,
        strategy.updated_at as activity_at
    from public.strategies as strategy
    where strategy.user_id = %s
      and strategy.id = %s

    union all

    select
        'collection'::text as source_type,
        collection.pinned,
        2 as type_rank,
        collection.updated_at as activity_at
    from public.collections as collection
    where collection.user_id = %s
      and collection.id = %s
) as pivots
"""


_SOURCE_RANKS = {
    "run": 1,
    "collection": 2,
    "strategy": 3,
    "chat": 4,
}


def _cursor_predicate(
    *,
    activity_column: str,
    id_column: str,
    source_rank: int,
    pivot_type_rank: int,
) -> str:
    if source_rank < pivot_type_rank:
        return f"{activity_column} <= %(cursor_activity_at)s"
    if source_rank > pivot_type_rank:
        return f"{activity_column} < %(cursor_activity_at)s"
    return (
        f"row({activity_column}, {id_column}) "
        "< row(%(cursor_activity_at)s, %(cursor_id)s)"
    )


def _bounded_leaf(
    *,
    select_sql: str,
    from_sql: str,
    filters: tuple[str, ...],
    order_sql: str,
) -> str:
    where_sql = "\n      and ".join(filters)
    return f"""
    select
{select_sql}
    from {from_sql}
    where {where_sql}
    order by {order_sql}
    limit %(source_limit)s
"""


def _variable_source_sql(
    *,
    select_sql: str,
    from_sql: str,
    base_filters: tuple[str, ...],
    order_sql: str,
    outer_order_sql: str,
    source_alias: str,
    activity_column: str,
    id_column: str,
    source_rank: int,
    has_cursor: bool,
    pivot_pinned: bool,
    pivot_type_rank: int,
) -> str:
    cursor_filters = (
        (*base_filters, f"{source_alias}.id <> %(cursor_id)s")
        if has_cursor
        else base_filters
    )
    if not has_cursor:
        pinned_leaf = _bounded_leaf(
            select_sql=select_sql,
            from_sql=from_sql,
            filters=(*cursor_filters, f"{source_alias}.pinned is true"),
            order_sql=order_sql,
        )
        unpinned_leaf = _bounded_leaf(
            select_sql=select_sql,
            from_sql=from_sql,
            filters=(*cursor_filters, f"{source_alias}.pinned is false"),
            order_sql=order_sql,
        )
        return f"""
    select *
    from (
        ({pinned_leaf})
        union all
        ({unpinned_leaf})
    ) as {source_alias}_tiers
    order by {outer_order_sql}
    limit %(source_limit)s
"""

    cursor_predicate = _cursor_predicate(
        activity_column=activity_column,
        id_column=id_column,
        source_rank=source_rank,
        pivot_type_rank=pivot_type_rank,
    )
    if not pivot_pinned:
        return _bounded_leaf(
            select_sql=select_sql,
            from_sql=from_sql,
            filters=(
                *cursor_filters,
                f"{source_alias}.pinned is false",
                cursor_predicate,
            ),
            order_sql=order_sql,
        )

    pinned_leaf = _bounded_leaf(
        select_sql=select_sql,
        from_sql=from_sql,
        filters=(
            *cursor_filters,
            f"{source_alias}.pinned is true",
            cursor_predicate,
        ),
        order_sql=order_sql,
    )
    unpinned_leaf = _bounded_leaf(
        select_sql=select_sql,
        from_sql=from_sql,
        filters=(*cursor_filters, f"{source_alias}.pinned is false"),
        order_sql=order_sql,
    )
    return f"""
    select *
    from (
        ({pinned_leaf})
        union all
        ({unpinned_leaf})
    ) as {source_alias}_tiers
    order by {outer_order_sql}
    limit %(source_limit)s
"""


@lru_cache(maxsize=80)
def _candidate_sql(
    *,
    archived: bool,
    deleted: bool,
    has_cursor: bool,
    pivot_pinned: bool,
    pivot_type_rank: int,
    business: bool,
) -> str:
    if has_cursor and pivot_type_rank not in _SOURCE_RANKS.values():
        raise HistoryCursorError("History cursor pivot rank is invalid.")

    # The text names the space parameter, never a space, so one entry per side.
    scope: OwnerScope = BusinessSpace("") if business else PERSONAL
    # Runs without a conversation, strategies and collections store no space.
    spaceless_row_in_scope = sql_named_predicate(scope, "null::uuid")

    archive_state = "true" if archived else "false"
    deleted_state = "is not null" if deleted else "is null"

    missing_parent_default = "true" if not archived and not deleted else "false"
    run_parent_filter = f"""coalesce((
        select parent.archived is {archive_state}
           and parent.deleted_at {deleted_state}
           and {sql_named_predicate(scope, "parent.owner_space_id")}
        from public.conversations as parent
        where parent.id = run.conversation_id
          and parent.user_id = %(user_id)s
        offset 0
    ), {missing_parent_default} and {spaceless_row_in_scope})"""
    run_filters: tuple[str, ...] = (
        "run.user_id = %(user_id)s",
        run_parent_filter,
    )
    if has_cursor:
        run_filters = (*run_filters, "run.id <> %(cursor_id)s")
    if has_cursor and not pivot_pinned:
        run_filters = (
            *run_filters,
            _cursor_predicate(
                activity_column="run.created_at",
                id_column="run.id",
                source_rank=_SOURCE_RANKS["run"],
                pivot_type_rank=pivot_type_rank,
            ),
        )
    run_sql = _bounded_leaf(
        select_sql="""        'run'::text as source_type,
        false as pinned,
        run.created_at as activity_at,
        1 as type_rank,
        run.id,
        jsonb_build_object(
            'id', run.id,
            'conversation_id', run.conversation_id,
            'conversation_result_card', run.conversation_result_card,
            'created_at', run.created_at
        ) as payload""",
        from_sql="public.backtest_runs as run",
        filters=run_filters,
        order_sql="run.created_at desc, run.id desc",
    )

    chat_sql = _variable_source_sql(
        select_sql="""        'chat'::text as source_type,
        chat.pinned,
        chat.updated_at as activity_at,
        4 as type_rank,
        chat.id,
        jsonb_build_object(
            'id', chat.id,
            'title', chat.title,
            'title_source', chat.title_source,
            'last_message_preview', chat.last_message_preview,
            'pinned', chat.pinned,
            'updated_at', chat.updated_at,
            'deleted_at', chat.deleted_at,
            'archived', chat.archived
        ) as payload""",
        from_sql="public.conversations as chat",
        base_filters=(
            "chat.user_id = %(user_id)s",
            sql_named_predicate(scope, "chat.owner_space_id"),
            f"chat.archived is {archive_state}",
            f"chat.deleted_at {deleted_state}",
            """exists (
          select 1
          from public.messages as message
          where message.user_id = %(user_id)s
            and message.conversation_id = chat.id
      )""",
        ),
        order_sql="chat.pinned desc, chat.updated_at desc, chat.id desc",
        outer_order_sql="pinned desc, activity_at desc, id desc",
        source_alias="chat",
        activity_column="chat.updated_at",
        id_column="chat.id",
        source_rank=_SOURCE_RANKS["chat"],
        has_cursor=has_cursor,
        pivot_pinned=pivot_pinned,
        pivot_type_rank=pivot_type_rank,
    )

    strategy_sql = _variable_source_sql(
        select_sql="""        'strategy'::text as source_type,
        strategy.pinned,
        strategy.updated_at as activity_at,
        3 as type_rank,
        strategy.id,
        jsonb_build_object(
            'id', strategy.id,
            'name', strategy.name,
            'symbols', strategy.symbols,
            'pinned', strategy.pinned,
            'updated_at', strategy.updated_at,
            'deleted_at', strategy.deleted_at
        ) as payload""",
        from_sql="public.strategies as strategy",
        base_filters=(
            "strategy.user_id = %(user_id)s",
            spaceless_row_in_scope,
            f"strategy.deleted_at {deleted_state}",
        ),
        order_sql=("strategy.pinned desc, strategy.updated_at desc, strategy.id desc"),
        outer_order_sql="pinned desc, activity_at desc, id desc",
        source_alias="strategy",
        activity_column="strategy.updated_at",
        id_column="strategy.id",
        source_rank=_SOURCE_RANKS["strategy"],
        has_cursor=has_cursor,
        pivot_pinned=pivot_pinned,
        pivot_type_rank=pivot_type_rank,
    )

    collection_sql = _variable_source_sql(
        select_sql="""        collection.user_id,
        collection.id,
        collection.name,
        collection.pinned,
        collection.deleted_at,
        collection.updated_at""",
        from_sql="public.collections as collection",
        base_filters=(
            "collection.user_id = %(user_id)s",
            spaceless_row_in_scope,
            f"collection.deleted_at {deleted_state}",
        ),
        order_sql=(
            "collection.pinned desc, collection.updated_at desc, collection.id desc"
        ),
        outer_order_sql="pinned desc, updated_at desc, id desc",
        source_alias="collection",
        activity_column="collection.updated_at",
        id_column="collection.id",
        source_rank=_SOURCE_RANKS["collection"],
        has_cursor=has_cursor,
        pivot_pinned=pivot_pinned,
        pivot_type_rank=pivot_type_rank,
    )

    return f"""
with run_candidates as (
{run_sql}
),
chat_candidates as (
{chat_sql}
),
strategy_candidates as (
{strategy_sql}
),
collection_candidates as (
{collection_sql}
),
collection_rows as (
    select
        'collection'::text as source_type,
        collection.pinned,
        collection.updated_at as activity_at,
        2 as type_rank,
        collection.id,
        jsonb_build_object(
            'id', collection.id,
            'name', collection.name,
            'pinned', collection.pinned,
            'updated_at', collection.updated_at,
            'deleted_at', collection.deleted_at,
            'strategy_count', (
                select count(*)
                from public.collection_strategies as member
                where member.user_id = collection.user_id
                  and member.collection_id = collection.id
            )
        ) as payload
    from collection_candidates as collection
),
candidates as (
    select * from run_candidates
    union all
    select * from chat_candidates
    union all
    select * from strategy_candidates
    union all
    select * from collection_rows
)
select source_type, payload
from candidates
order by pinned desc, activity_at desc, type_rank desc, id desc
"""


@dataclass(frozen=True)
class PostgresHistoryReader:
    pool: Any

    def list_rows(
        self,
        *,
        user_id: str,
        scope: OwnerScope,
        limit: int,
        archived: bool,
        deleted: bool,
        cursor_activity_at: datetime | None = None,
        cursor_id: str | None = None,
        cursor_pinned: bool | None = None,
        cursor_type_rank: int | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if limit < 1:
            raise ValueError("History source limit must be positive.")
        try:
            owner_id = UUID(user_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("History owner id must be a UUID.") from exc

        has_cursor = cursor_activity_at is not None or cursor_id is not None
        if has_cursor and (cursor_activity_at is None or cursor_id is None):
            raise HistoryCursorError("History cursor is incomplete.")
        has_ranked_cursor = cursor_pinned is not None or cursor_type_rank is not None
        if has_ranked_cursor and (
            not has_cursor
            or not isinstance(cursor_pinned, bool)
            or not isinstance(cursor_type_rank, int)
            or isinstance(cursor_type_rank, bool)
            or cursor_type_rank not in _SOURCE_RANKS.values()
        ):
            raise HistoryCursorError("History cursor rank is invalid.")
        if cursor_activity_at is not None and (
            cursor_activity_at.tzinfo is None or cursor_activity_at.utcoffset() is None
        ):
            raise HistoryCursorError("History cursor timestamp is invalid.")
        try:
            pivot_id = UUID(cursor_id) if cursor_id is not None else None
        except (TypeError, ValueError) as exc:
            raise HistoryCursorError("History cursor id is invalid.") from exc
        if pivot_id is not None and str(pivot_id) != cursor_id:
            raise HistoryCursorError("History cursor id is invalid.")

        pivot_pinned = False
        pivot_type_rank = 0
        with self.pool.connection(timeout=_HISTORY_ACQUIRE_TIMEOUT_SECONDS) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                if has_cursor:
                    pivot_params = (
                        owner_id,
                        pivot_id,
                        owner_id,
                        pivot_id,
                        owner_id,
                        owner_id,
                        pivot_id,
                        owner_id,
                        pivot_id,
                    )
                    cursor.execute(_PIVOT_SQL, pivot_params)
                    pivots = cursor.fetchall()
                    if len(pivots) != 1:
                        raise HistoryCursorError(
                            "History cursor pivot is missing or ambiguous."
                        )
                    pivot = pivots[0]
                    resolved_type_rank = int(pivot["type_rank"])
                    if has_ranked_cursor:
                        if cursor_type_rank != resolved_type_rank:
                            raise HistoryCursorError(
                                "History cursor pivot rank is invalid."
                            )
                        assert cursor_pinned is not None
                        pivot_pinned = cursor_pinned
                    else:
                        if pivot.get("activity_at") != cursor_activity_at:
                            raise HistoryCursorError(
                                "History cursor pivot changed after it was issued."
                            )
                        pivot_pinned = bool(pivot["pinned"])
                    pivot_type_rank = resolved_type_rank

                candidate_params = {
                    "user_id": owner_id,
                    SCOPE_PARAMETER: space_id(scope),
                    "cursor_activity_at": cursor_activity_at,
                    "cursor_id": pivot_id,
                    "source_limit": limit,
                }
                cursor.execute(
                    _candidate_sql(
                        archived=archived,
                        deleted=deleted,
                        has_cursor=has_cursor,
                        pivot_pinned=pivot_pinned,
                        pivot_type_rank=pivot_type_rank,
                        business=isinstance(scope, BusinessSpace),
                    ),
                    candidate_params,
                )
                candidates = cursor.fetchall()

        grouped: dict[str, list[dict[str, Any]]] = {
            "runs": [],
            "conversations": [],
            "strategies": [],
            "collections": [],
        }
        target_by_source = {
            "run": "runs",
            "chat": "conversations",
            "strategy": "strategies",
            "collection": "collections",
        }
        for candidate in candidates:
            target = target_by_source.get(str(candidate.get("source_type")))
            payload = candidate.get("payload")
            if target is None or not isinstance(payload, dict):
                continue
            grouped[target].append(payload)
        return grouped


@lru_cache(maxsize=2)
def history_reader_for_database_url(database_url: str) -> PostgresHistoryReader:
    if not database_url:
        raise RuntimeError("Persistent History requires DATABASE_URL.")
    pool = ConnectionPool(
        conninfo=database_url,
        kwargs={
            "autocommit": True,
            "connect_timeout": _HISTORY_CONNECT_TIMEOUT_SECONDS,
            "options": f"-c statement_timeout={_HISTORY_STATEMENT_TIMEOUT_MS}",
        },
        min_size=0,
        max_size=_HISTORY_POOL_SIZE,
        open=True,
        timeout=_HISTORY_ACQUIRE_TIMEOUT_SECONDS,
        name="argus-history",
    )
    atexit.register(pool.close)
    return PostgresHistoryReader(pool)
