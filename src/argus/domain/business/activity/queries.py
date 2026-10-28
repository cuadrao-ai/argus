"""One authorized, Business-scoped page of applied ledger rows, newest first.
The page is keyed by (created_at, item id), so it does not move when a newer
row lands."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone

from psycopg.rows import dict_row

from argus.domain.business.activity.catalog import project, visibility
from argus.domain.business.authority import (
    ActionContext,
    ActionError,
    BusinessAuthority,
    authorize,
)
from argus.domain.business.contracts.activity import (
    ActivityItem,
    ActivityPage,
    PageSize,
)


class InvalidCursor(ValueError):
    pass


@dataclass(frozen=True)
class Cursor:
    occurred_at: datetime
    id: str


#: An opaque id per row, from columns a member's departure never rewrites. The
#: idempotency key itself stays in the ledger.
_ROW_ID = (
    "left(encode(sha256(convert_to(space_id::text || ':' || idempotency_key"
    " || ':' || extract(epoch from created_at)::text, 'UTF8')), 'hex'), 32)"
)
_PAGE = f"""
    select id, created_at, actor, command, outcome
    from (
        select {_ROW_ID} as id, created_at, actor, command, outcome
        from public.business_action_receipts
        where space_id = %(space_id)s
          and outcome->>'outcome' = 'applied'
          and (%(only)s::text[] is null
               or command->>'action' = any(%(only)s::text[]))
          and coalesce(command->>'action', '') <> all(%(hidden)s::text[])
          and (%(before_at)s::timestamptz is null
               or created_at <= %(before_at)s::timestamptz)
    ) applied
    where %(before_at)s::timestamptz is null
       or (created_at, id) < (%(before_at)s::timestamptz, %(before_id)s::text)
    order by created_at desc, id desc
    limit %(limit)s
"""


def encode_cursor(item: ActivityItem) -> str:
    raw = f"{item.occurred_at.isoformat()}|{item.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> Cursor:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        occurred_at, _, item_id = raw.rpartition("|")
        parsed = datetime.fromisoformat(occurred_at)
        at = parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (binascii.Error, UnicodeDecodeError, ValueError, OverflowError):
        raise InvalidCursor() from None
    if at is None or len(item_id) != 32 or not _hex(item_id):
        raise InvalidCursor()
    return Cursor(at, item_id)


def _hex(value: str) -> bool:
    return all(char in "0123456789abcdef" for char in value)


def read_activity(
    authority: BusinessAuthority,
    context: ActionContext,
    *,
    limit: PageSize,
    before: Cursor | None = None,
) -> ActivityPage:
    with authority.pool.connection() as connection, connection.transaction():
        live = authorize(connection, context.actor, context.grant_id)
        live.require("read")
        if live.context.owner_id != context.owner_id:
            raise ActionError("not_found", "business_record_not_found")
        visible = visibility(manager="manage" in live.permissions)
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                _PAGE,
                {
                    "space_id": context.actor.space_id,
                    "only": None if visible.only is None else list(visible.only),
                    "hidden": list(visible.hidden),
                    "before_at": before.occurred_at if before else None,
                    "before_id": before.id if before else None,
                    "limit": limit + 1,
                },
            )
            rows = cursor.fetchall()
    items = tuple(project(row) for row in rows[:limit])
    return ActivityPage(
        items=items,
        next_cursor=encode_cursor(items[-1]) if len(rows) > limit else None,
    )
