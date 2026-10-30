"""One authorized, Business-scoped page of changes, newest first. The page is
keyed by (created_at, item id), so it does not move when a newer row lands,
and its cursor is bound to the filter set it was read with."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from argus.domain.business.activity.catalog import (
    EventRow,
    project,
    visibility,
    with_labels,
)
from argus.domain.business.authority import (
    ActionContext,
    ActionError,
    BusinessAuthority,
    _profile_label,
    authorize,
)
from argus.domain.business.contracts.activity import (
    ActivityFacetActor,
    ActivityFilters,
    ActivityItem,
    ActivityPage,
    ObjectKind,
    PageSize,
)
from argus.domain.business.reporting_query import CALENDAR

#: The name the departure migration writes over an erased member's rows.
ERASED_NAME = "Exmiembro"


class InvalidCursor(ValueError):
    pass


@dataclass(frozen=True)
class Cursor:
    occurred_at: datetime
    id: str
    filters: str


def _key(expression: str) -> str:
    return f"left(encode(sha256(convert_to({expression}, 'UTF8')), 'hex'), 32)"


#: An opaque id per row, from columns a member's departure never rewrites. The
#: idempotency key itself stays in the ledger.
_ROW_ID = _key(
    "space_id::text || ':' || idempotency_key || ':' || extract(epoch from created_at)::text"
)
#: An opaque id per person and Business; the extractor is one actor per Business.
_ACTOR_KEY = (
    "case when e.actor_kind = 'extractor' then "
    + _key("e.space_id::text || ':extractor'")
    + " else "
    + _key("e.space_id::text || ':actor:' || e.actor_id::text")
    + " end"
)
_LIVE_GRANT = (
    "select 1 from public.business_client_grants g"
    " where g.space_id = e.space_id and g.grantee_id = e.actor_id"
    " and g.revoked_at is null"
    " and (g.expires_at is null or g.expires_at > clock_timestamp())"
)
_ANY_GRANT = (
    "select 1 from public.business_client_grants g"
    " where g.space_id = e.space_id and g.grantee_id = e.actor_id"
)
_EVENTS = f"""
    with events as (
        select {_ROW_ID} as id, space_id, created_at, actor_id,
               actor->>'actor_kind' as actor_kind,
               actor->>'display_name' as display_name,
               command->>'action' as action, command, outcome
        from public.business_action_receipts
        where space_id = %(space_id)s
          and outcome->>'outcome' = 'applied'
        union all
        select {_key("space_id::text || ':transfer:' || id::text")}, space_id,
               resolved_at, target_id, 'member', null::text,
               'ownership_transferred', '{{}}'::jsonb, null::jsonb
        from public.business_ownership_transfers
        where space_id = %(space_id)s and status = 'accepted'
        union all
        select {_key("space_id::text || ':reading:' || id::text")}, space_id,
               consented_at, owner_id, 'member', null::text,
               'receipt_reading_enabled', '{{}}'::jsonb, null::jsonb
        from public.business_receipt_reading_consents
        where space_id = %(space_id)s
    ), visible as (
        select e.id, e.created_at, e.actor_id, e.actor_kind, e.display_name,
               e.action, e.command, e.outcome, {_ACTOR_KEY} as actor_key,
               case when e.actor_kind = 'extractor' then null
                    when exists ({_LIVE_GRANT}) then 'current'
                    when exists ({_ANY_GRANT}) then 'former'
               end as membership
        from events e
        where (%(only)s::text[] is null or e.action = any(%(only)s::text[]))
          and coalesce(e.action, '') <> all(%(hidden)s::text[])
          and (%(since)s::timestamptz is null or e.created_at >= %(since)s::timestamptz)
          and (%(until)s::timestamptz is null or e.created_at < %(until)s::timestamptz)
    )
"""
_PAGE = f"""
    {_EVENTS}
    select id, created_at, actor_id, actor_key, actor_kind, display_name,
           membership, action, command, outcome
    from visible
    where (%(actors)s::text[] is null or actor_key = any(%(actors)s::text[]))
      and (%(before_at)s::timestamptz is null
           or (created_at, id) < (%(before_at)s::timestamptz, %(before_id)s::text))
    order by created_at desc, id desc
    limit %(limit)s
"""
_FACETS = f"""
    {_EVENTS}
    select distinct on (actor_key)
           actor_id, actor_key, actor_kind, display_name, membership
    from visible
    order by actor_key, display_name is null, created_at desc, id desc
"""
#: A departure leaves an alias in the derived columns: a member's from the
#: departure flow, a deleted creator's from the custody reservation.
_NAMES = """
    select i.id, p.id is not null as named, p.display_name, p.username,
           d.actor_id is not null or r.deleted_actor_id is not null as erased
    from unnest(%(ids)s::uuid[]) as i(id)
    left join public.profiles p on p.id = i.id
    left join argus_private.business_departure_aliases d
           on d.space_id = %(space_id)s and d.actor_id = i.id
    left join argus_private.business_custody_reservations r
           on r.space_id = %(space_id)s and r.deleted_actor_id = i.id
"""
_DRAFT_LABELS = """
    select id, resolution->'business'->'facts'->'counterparty' as counterparty
    from public.financial_import_events
    where owner_space_id = %(space_id)s and id = any(%(ids)s::uuid[])
"""
_GRANT_LABELS = """
    select g.id, p.display_name, p.username
    from public.business_client_grants g
    left join public.profiles p on p.id = g.grantee_id
    where g.space_id = %(space_id)s and g.id = any(%(ids)s::uuid[])
"""


def fingerprint(filters: ActivityFilters) -> str:
    canonical = json.dumps(filters.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def encode_cursor(item: ActivityItem, filters: ActivityFilters) -> str:
    raw = f"{item.occurred_at.isoformat()}|{item.id}|{fingerprint(filters)}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, filters: ActivityFilters) -> Cursor:
    """The cursor this read issued for exactly this filter set; any other,
    including one issued for other filters, is refused."""

    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        occurred_at, _, rest = raw.partition("|")
        item_id, _, issued_for = rest.partition("|")
        parsed = datetime.fromisoformat(occurred_at)
        at = parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (binascii.Error, UnicodeDecodeError, ValueError, OverflowError):
        raise InvalidCursor() from None
    if at is None or not _hex(item_id, 32) or issued_for != fingerprint(filters):
        raise InvalidCursor()
    return Cursor(at, item_id, issued_for)


def _hex(value: str, length: int) -> bool:
    return len(value) == length and all(char in "0123456789abcdef" for char in value)


def day_bounds(filters: ActivityFilters) -> tuple[datetime | None, datetime | None]:
    """The half-open instant range of the filter's calendar days in the
    Business time zone."""

    zone = ZoneInfo(CALENDAR)
    since = until = None
    if filters.since is not None:
        since = datetime.combine(filters.since, time.min, zone)
    if filters.until is not None:
        until = datetime.combine(filters.until + timedelta(days=1), time.min, zone)
    return since, until


def read_activity(
    authority: BusinessAuthority,
    context: ActionContext,
    *,
    limit: PageSize,
    filters: ActivityFilters | None = None,
    before: Cursor | None = None,
) -> ActivityPage:
    filters = filters or ActivityFilters()
    with authority.pool.connection() as connection, connection.transaction():
        live = authorize(connection, context.actor, context.grant_id)
        live.require("read")
        if live.context.owner_id != context.owner_id:
            raise ActionError("not_found", "business_record_not_found")
        visible = visibility(manager="manage" in live.permissions, filters=filters)
        since, until = day_bounds(filters)
        scope = {
            "space_id": context.actor.space_id,
            "only": None if visible.only is None else list(visible.only),
            "hidden": list(visible.hidden),
            "since": since,
            "until": until,
        }
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                _PAGE,
                {
                    **scope,
                    "actors": list(filters.actors) or None,
                    "before_at": before.occurred_at if before else None,
                    "before_id": before.id if before else None,
                    "limit": limit + 1,
                },
            )
            rows = cursor.fetchall()
            facets = None
            if before is None:
                cursor.execute(_FACETS, scope)
                facets = cursor.fetchall()
            page = rows[:limit]
            _fill_names(cursor, context.actor.space_id, page + (facets or []))
            items = tuple(project(row) for row in page)
            labels = _labels(cursor, context.actor.space_id, items)
    items = tuple(with_labels(item, labels) for item in items)
    return ActivityPage(
        items=items,
        next_cursor=encode_cursor(items[-1], filters) if len(rows) > limit else None,
        actors=None if facets is None else _facet(facets),
    )


def _fill_names(cursor, space_id: UUID, rows: list[dict]) -> None:
    """A derived source stores the actor's id, not a name: the profile names
    the person, and a departure alias keeps the departure name."""

    unnamed = {str(row["actor_id"]) for row in rows if row["display_name"] is None}
    if not unnamed:
        return
    cursor.execute(_NAMES, {"space_id": space_id, "ids": sorted(unnamed)})
    names = {
        str(row["id"]): ERASED_NAME
        if row["erased"]
        else _profile_label(row["display_name"], row["username"])
        if row["named"]
        else None
        for row in cursor.fetchall()
    }
    for row in rows:
        if row["display_name"] is None:
            row["display_name"] = names.get(str(row["actor_id"]))


def _facet(rows: Iterable[EventRow]) -> tuple[ActivityFacetActor, ...]:
    named = [row for row in rows if row["display_name"] is not None]
    return tuple(
        ActivityFacetActor(
            id=row["actor_key"],
            display_name=row["display_name"],
            kind=row["actor_kind"],
            membership=row["membership"],
        )
        for row in sorted(named, key=lambda row: (row["display_name"], row["actor_key"]))
    )


def _labels(
    cursor, space_id: UUID, items: Iterable[ActivityItem]
) -> dict[tuple[ObjectKind, UUID], str]:
    """A human label per object the page names, from records the reader may
    read: a draft's counterparty, a grant's person. An invite names only an
    email, which never leaves the ledger."""

    ids: dict[ObjectKind, set[UUID]] = {"draft": set(), "grant": set()}
    for item in items:
        if item.object is not None and item.object.kind in ids:
            ids[item.object.kind].add(item.object.id)
    labels: dict[tuple[ObjectKind, UUID], str] = {}
    if ids["draft"]:
        cursor.execute(_DRAFT_LABELS, {"space_id": space_id, "ids": sorted(ids["draft"])})
        for row in cursor.fetchall():
            label = _known(row["counterparty"])
            if label:
                labels[("draft", row["id"])] = label
    if ids["grant"]:
        cursor.execute(_GRANT_LABELS, {"space_id": space_id, "ids": sorted(ids["grant"])})
        for row in cursor.fetchall():
            labels[("grant", row["id"])] = _profile_label(
                row["display_name"], row["username"]
            )
    return labels


def _known(fact: object) -> str | None:
    if not isinstance(fact, Mapping) or fact.get("state") != "known":
        return None
    value = fact.get("value")
    return value.strip() or None if isinstance(value, str) else None
