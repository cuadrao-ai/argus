from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from argus.api.chat.legacy_onboarding_markers import (
    _LEGACY_GOAL_PREFIX,
    _LEGACY_SKIP_MARKER,
)
from argus.domain.conversation_previews import MAX_CONVERSATION_PREVIEWS
from argus.domain.owner_scope import OwnerScope, sql_predicate

_KEYSET_ACQUIRE_TIMEOUT_SECONDS = 2.0
_LEGACY_GOAL_LIKE = _LEGACY_GOAL_PREFIX.replace("_", r"\_").replace("%", r"\%") + "%"

_CONVERSATION_COLUMNS = """
id,
title,
title_source,
language,
pinned,
archived,
last_message_preview,
deleted_at,
created_at,
updated_at,
owner_space_id
"""
_MESSAGE_COLUMNS = """
id,
conversation_id,
role,
content,
metadata,
created_at
"""
_CONVERSATION_PIVOT_SQL = """
select id, pinned
from public.conversations
where user_id = %s
  and id = %s
limit 2
"""


class ConversationKeysetCursorError(ValueError):
    """Raised when a private Conversation page pivot cannot resolve exactly."""


def _uuid(value: str, *, label: str) -> UUID:
    try:
        return UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a UUID.") from exc


@lru_cache(maxsize=24)
def _conversation_page_sql(
    *,
    scope_condition: str,
    archived: bool | None,
    deleted: bool,
    has_cursor: bool,
) -> str:
    deleted_predicate = "deleted_at is not null" if deleted else "deleted_at is null"
    archived_predicate = "" if archived is None else "\n  and archived = %s"
    cursor_predicate = (
        "\n  and (pinned, updated_at, id) < (%s, %s, %s)" if has_cursor else ""
    )
    return f"""
select {_CONVERSATION_COLUMNS}
from public.conversations
where user_id = %s
  and {scope_condition}
  and {deleted_predicate}{archived_predicate}{cursor_predicate}
order by pinned desc, updated_at desc, id desc
limit %s
"""


@lru_cache(maxsize=2)
def _message_page_sql(*, has_cursor: bool) -> str:
    cursor_predicate = "\n  and (created_at, id) > (%s, %s)" if has_cursor else ""
    return f"""
select {_MESSAGE_COLUMNS}
from public.messages
where user_id = %s
  and conversation_id = %s
  and (
      role <> 'user'
      or (
          content <> %s
          and content not like %s escape '\\'
      )
  ){cursor_predicate}
order by created_at asc, id asc
limit %s
"""


def _stringify_uuid_fields(
    rows: list[dict[str, Any]],
    *,
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw_row in rows:
        row = dict(raw_row)
        for field in fields:
            value = row.get(field)
            if isinstance(value, UUID):
                row[field] = str(value)
        normalized.append(row)
    return normalized


@dataclass(frozen=True)
class PostgresKeysetReader:
    pool: Any

    def read_conversation_preview_messages(
        self, *, user_id: str, conversation_ids: list[str]
    ) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(conversation_ids))
        if len(ids) > MAX_CONVERSATION_PREVIEWS:
            raise ValueError("At most 100 conversation previews may be read at once.")
        if not ids:
            return []
        with self.pool.connection(timeout=_KEYSET_ACQUIRE_TIMEOUT_SECONDS) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    select c.id as conversation_id, latest.id, latest.role, latest.content, latest.metadata
                    from public.conversations c
                    left join lateral (
                        select m.id, m.role, m.content, m.metadata
                        from public.messages m
                        where m.user_id = c.user_id and m.conversation_id = c.id
                          and (m.role <> 'user' or (
                              m.content <> %s and m.content not like %s escape '\\'
                          ))
                        order by m.created_at desc, m.id desc
                        limit 1
                    ) latest on true
                    where c.user_id = %s and c.id = any(%s)
                    """,
                    (
                        _LEGACY_SKIP_MARKER,
                        _LEGACY_GOAL_LIKE,
                        _uuid(user_id, label="user_id"),
                        [_uuid(value, label="conversation_id") for value in ids],
                    ),
                )
                return _stringify_uuid_fields(
                    cursor.fetchall(),
                    fields=("conversation_id", "id"),
                )

    def list_conversation_rows(
        self,
        *,
        user_id: str,
        scope: OwnerScope,
        limit: int,
        archived: bool | None,
        deleted: bool,
        cursor_updated_at: datetime | None = None,
        cursor_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("Conversation page limit must be positive.")
        owner_id = _uuid(user_id, label="Conversation owner id")
        has_cursor = cursor_updated_at is not None or cursor_id is not None
        if has_cursor and (cursor_updated_at is None or cursor_id is None):
            raise ConversationKeysetCursorError("Conversation cursor is incomplete.")
        pivot_id = (
            _uuid(cursor_id, label="Conversation cursor id")
            if cursor_id is not None
            else None
        )

        with self.pool.connection(timeout=_KEYSET_ACQUIRE_TIMEOUT_SECONDS) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor_pinned: bool | None = None
                if has_cursor:
                    cursor.execute(
                        _CONVERSATION_PIVOT_SQL,
                        (owner_id, pivot_id),
                    )
                    pivots = cursor.fetchall()
                    if len(pivots) != 1:
                        raise ConversationKeysetCursorError(
                            "Conversation cursor pivot is missing or ambiguous."
                        )
                    pivot = pivots[0]
                    if pivot.get("id") not in {pivot_id, str(pivot_id)} or not isinstance(
                        pivot.get("pinned"), bool
                    ):
                        raise ConversationKeysetCursorError(
                            "Conversation cursor pivot is invalid."
                        )
                    cursor_pinned = pivot["pinned"]

                scope_condition, scope_params = sql_predicate(scope, "owner_space_id")
                params: list[Any] = [owner_id, *scope_params]
                if archived is not None:
                    params.append(archived)
                if has_cursor:
                    params.extend(
                        (
                            cursor_pinned,
                            cursor_updated_at,
                            pivot_id,
                        )
                    )
                params.append(limit + 1)
                cursor.execute(
                    _conversation_page_sql(
                        scope_condition=scope_condition,
                        archived=archived,
                        deleted=deleted,
                        has_cursor=has_cursor,
                    ),
                    tuple(params),
                )
                rows = cursor.fetchall()
        return _stringify_uuid_fields(rows, fields=("id",))

    def list_shared_message_rows(
        self, *, user_id: str, conversation_id: str
    ) -> list[dict[str, Any]]:
        with self.pool.connection(timeout=_KEYSET_ACQUIRE_TIMEOUT_SECONDS) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """select id,conversation_id,role,content,metadata,created_at
                    from public.messages where user_id=%s and conversation_id=%s
                    and metadata @> '{"shared_conversation":{}}'::jsonb
                    order by created_at,id""",
                    (
                        _uuid(user_id, label="Message owner id"),
                        _uuid(conversation_id, label="Message conversation id"),
                    ),
                )
                rows = cursor.fetchall()
        return _stringify_uuid_fields(rows, fields=("id", "conversation_id"))

    def list_message_rows(
        self,
        *,
        user_id: str,
        conversation_id: str,
        limit: int,
        cursor_created_at: datetime | None = None,
        cursor_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("Message page limit must be positive.")
        owner_id = _uuid(user_id, label="Message owner id")
        owned_conversation_id = _uuid(
            conversation_id,
            label="Message conversation id",
        )
        has_cursor = cursor_created_at is not None or cursor_id is not None
        if has_cursor and (cursor_created_at is None or cursor_id is None):
            raise ValueError("Message cursor is incomplete.")
        pivot_id = (
            _uuid(cursor_id, label="Message cursor id") if cursor_id is not None else None
        )

        params: list[Any] = [
            owner_id,
            owned_conversation_id,
            _LEGACY_SKIP_MARKER,
            _LEGACY_GOAL_LIKE,
        ]
        if has_cursor:
            params.extend((cursor_created_at, pivot_id))
        params.append(limit + 1)
        with self.pool.connection(timeout=_KEYSET_ACQUIRE_TIMEOUT_SECONDS) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    _message_page_sql(has_cursor=has_cursor),
                    tuple(params),
                )
                rows = cursor.fetchall()
        return _stringify_uuid_fields(
            rows,
            fields=("id", "conversation_id"),
        )
