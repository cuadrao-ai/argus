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
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from argus.domain.business import search
from argus.domain.business.activity.catalog import (
    LEGACY,
    EventRow,
    project,
    visibility,
    with_labels,
)
from argus.domain.business.authority import (
    ActionContext,
    ActionError,
    Authorization,
    BusinessAuthority,
    authorize,
)
from argus.domain.business.contracts.activity import (
    ActivityFacetActor,
    ActivityFilters,
    ActivityItem,
    ActivityObject,
    ActivityPage,
    ObjectKind,
    PageSize,
)
from argus.domain.business.people import people, person_label
from argus.domain.business.reporting_query import CALENDAR


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
    " and (g.expires_at is null or g.expires_at > now())"
)
_ANY_GRANT = (
    "select 1 from public.business_client_grants g"
    " where g.space_id = e.space_id and g.grantee_id = e.actor_id"
)
_EVENTS = f"""
    with events as (
        select {_ROW_ID} as id, space_id, created_at, actor_id,
               actor->>'actor_kind' as actor_kind,
               command->>'action' as action, command, outcome
        from public.business_action_receipts
        where space_id = %(space_id)s
          and outcome->>'outcome' = 'applied'
        union all
        select {_key("space_id::text || ':transfer:' || id::text")}, space_id,
               resolved_at, target_id, 'member',
               'ownership_transferred', '{{}}'::jsonb, null::jsonb
        from public.business_ownership_transfers
        where space_id = %(space_id)s and status = 'accepted'
        union all
        select {_key("space_id::text || ':reading:' || id::text")}, space_id,
               consented_at, owner_id, 'member',
               'receipt_reading_enabled', '{{}}'::jsonb, null::jsonb
        from public.business_receipt_reading_consents
        where space_id = %(space_id)s
        union all
        select {_key("space_id::text || ':purge:' || id::text")}, space_id,
               purged_at, null::uuid, 'extractor',
               'expire_document', '{{}}'::jsonb, null::jsonb
        from argus_private.business_document_purges
        where space_id = %(space_id)s and reason = 'expiry'
    ), visible as (
        select e.id, e.created_at, e.actor_id, e.actor_kind,
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
    select id, created_at, actor_id, actor_key, actor_kind,
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
           actor_id, actor_key, actor_kind, membership
    from visible
    order by actor_key, created_at desc, id desc
"""
_DRAFT_LABELS = """
    select id, resolution->'business'->'facts'->'counterparty' as counterparty
    from public.financial_import_events
    where owner_space_id = %(space_id)s and id = any(%(ids)s::uuid[])
"""
_GRANT_LABELS = """
    select g.id, g.grantee_id
    from public.business_client_grants g
    where g.space_id = %(space_id)s and g.id = any(%(ids)s::uuid[])
"""


#: A read with a query scans this many rows a statement, this many statements.
_SCAN_ROWS = 500
_SCAN_READS = 4


def fingerprint(filters: ActivityFilters) -> str:
    # Without a query the set reads as it did before the feed took one, so a
    # cursor issued then still continues.
    dumped = filters.model_dump(mode="json", exclude=None if filters.q else {"q"})
    canonical = json.dumps(dumped, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def encode_cursor(item: ActivityItem, filters: ActivityFilters) -> str:
    """The place after ``item`` in the filter set's page order."""

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
            read = _Read(cursor, live, scope, filters)
            facets = None
            if before is None:
                cursor.execute(_FACETS, scope)
                facets = cursor.fetchall()
                _fill_names(cursor, live, facets)
            if filters.q:
                items, last = read.matching(search.parse(filters.q), before, limit)
            else:
                items, more = read.page(before, limit)
                last = items[-1] if more else None
    return ActivityPage(
        items=items,
        next_cursor=None if last is None else encode_cursor(last, filters),
        actors=None if facets is None else _facet(facets),
    )


def holds(query: search.SearchQuery, item: ActivityItem) -> bool:
    """The query's words are in what the row says of who and of which object,
    read as the Business search reads a record."""

    said = (
        item.actor and (item.actor.display_name or item.actor.email),
        item.object and item.object.label,
    )
    return search.matches(query, " ".join(part for part in said if part))


@dataclass(frozen=True)
class _Read:
    cursor: Any
    viewer: Authorization
    scope: dict[str, Any]
    filters: ActivityFilters

    def page(
        self, before: Cursor | ActivityItem | None, limit: int
    ) -> tuple[tuple[ActivityItem, ...], bool]:
        """The next ``limit`` rows as the reader sees them, and whether more follow."""

        self.cursor.execute(
            _PAGE,
            {
                **self.scope,
                "actors": list(self.filters.actors) or None,
                "before_at": before.occurred_at if before else None,
                "before_id": before.id if before else None,
                "limit": limit + 1,
            },
        )
        rows = self.cursor.fetchall()
        page = rows[:limit]
        _fill_names(self.cursor, self.viewer, page)
        space_id = self.viewer.context.actor.space_id
        items = _receipt_targets(
            self.cursor,
            space_id,
            _purged(self.cursor, space_id, tuple(project(row) for row in page)),
        )
        labels = _labels(self.cursor, self.viewer, items)
        return tuple(with_labels(item, labels) for item in items), len(rows) > limit

    def matching(
        self, query: search.SearchQuery, before: Cursor | None, limit: int
    ) -> tuple[tuple[ActivityItem, ...], ActivityItem | None]:
        """The next ``limit`` rows that hold the query, and the row to continue
        after when more may follow. One read scans a bounded stretch of the
        history, so a page may come short, or empty, with a row to continue
        after: the reader follows it to the end."""

        found: list[ActivityItem] = []
        scanned: ActivityItem | None = None
        for _ in range(_SCAN_READS):
            items, more = self.page(scanned or before, _SCAN_ROWS)
            for item in items:
                if holds(query, item):
                    if len(found) == limit:
                        return tuple(found), found[-1]
                    found.append(item)
            if not more:
                return tuple(found), None
            scanned = items[-1]
        return tuple(found), scanned


#: A draft of the legacy receipt surface read from one upload, and an upload
#: that holds a document, each with the receipt it answers to.
_RECEIPTS = """
    select e.id, min(o.connection_id::text) as receipt_id
    from public.financial_import_events e
    join public.financial_import_observations o
      on o.event_id = e.id and o.user_id = e.user_id
    where e.owner_space_id = %(space_id)s and e.id = any(%(ids)s)
      and not (e.resolution ? 'business')
    group by e.id having count(distinct o.connection_id) = 1
    union all
    select c.id, c.id::text
    from public.financial_source_connections c
    join public.financial_document_extractions d
      on d.connection_id = c.id and d.user_id = c.user_id
    where c.owner_space_id = %(space_id)s and c.id = any(%(ids)s)
"""


def _leads_to_a_receipt(item: ActivityItem) -> bool:
    if item.object is None or item.object.purged:
        return False
    return item.action in LEGACY or (
        item.action in ("delete_document", "restore_document")
        and item.object.kind == "draft"
    )


def _receipt_targets(
    cursor, space_id: UUID, items: tuple[ActivityItem, ...]
) -> tuple[ActivityItem, ...]:
    """A document change that names a draft, and a write on the legacy receipt
    surface, lead to the one receipt the subject answers to. A legacy subject
    that is no receipt of this Business names nothing."""

    ids = sorted({item.object.id for item in items if _leads_to_a_receipt(item)})
    if not ids:
        return items
    cursor.execute(_RECEIPTS, {"space_id": space_id, "ids": ids})
    receipts = {row["id"]: row["receipt_id"] for row in cursor.fetchall()}

    def led(item: ActivityItem) -> ActivityItem:
        if not _leads_to_a_receipt(item):
            return item
        receipt = receipts.get(item.object.id)
        if receipt is not None:
            named = ActivityObject(kind="receipt", id=receipt)
            return item.model_copy(update={"object": named})
        return item.model_copy(update={"object": None}) if item.action in LEGACY else item

    return tuple(led(item) for item in items)


def _purged(
    cursor, space_id: UUID, items: tuple[ActivityItem, ...]
) -> tuple[ActivityItem, ...]:
    """Every entry whose document a purge removed says so. The purge record
    keeps the draft and upload ids the document answered to, never a name."""

    ids = sorted(
        {
            item.object.id
            for item in items
            if item.object is not None and item.object.kind in ("draft", "receipt")
        }
    )
    if not ids:
        return items
    cursor.execute(
        "select distinct d.id from argus_private.business_document_purges p,"
        " unnest(p.document_ids) as d(id)"
        " where p.space_id=%s and p.document_ids && %s::uuid[]",
        (space_id, ids),
    )
    gone = {row["id"] for row in cursor.fetchall()}
    return tuple(
        item.model_copy(
            update={"object": item.object.model_copy(update={"purged": True})}
        )
        if item.object is not None
        and item.object.kind in ("draft", "receipt")
        and item.object.id in gone
        else item
        for item in items
    )


def _fill_names(cursor, viewer: Authorization, rows: list[dict]) -> None:
    """Every row stores the actor's id, never a name the feed reads: the
    profile names the person now, as ``viewer`` reads them (``people``).
    Automated work names no one; the screen words it."""

    named = [row["actor_id"] for row in rows if row["actor_kind"] != "extractor"]
    found = people(cursor.connection, viewer, named)
    for row in rows:
        automated = row["actor_kind"] == "extractor"
        person = None if automated else found.get(str(row["actor_id"]))
        row.update(
            display_name=person and person.display_name,
            email=person and person.email,
            shown_as=person and person.shown_as,
            known=automated or person is not None,
        )


def _facet(rows: Iterable[EventRow]) -> tuple[ActivityFacetActor, ...]:
    known = [row for row in rows if row["known"]]
    return tuple(
        ActivityFacetActor(
            id=row["actor_key"],
            display_name=row["display_name"],
            email=row["email"],
            shown_as=row["shown_as"],
            kind=row["actor_kind"],
            membership=row["membership"],
        )
        for row in sorted(
            known,
            key=lambda row: (row["display_name"] or row["email"] or "", row["actor_key"]),
        )
    )


def _labels(
    cursor, viewer: Authorization, items: Iterable[ActivityItem]
) -> dict[tuple[ObjectKind, UUID], str]:
    """A human label per object the page names, from records the reader may
    read: a draft's counterparty, a grant's person as the reader reads them.
    An invite names only an email, which never leaves the ledger."""

    space_id = viewer.context.actor.space_id

    ids: dict[ObjectKind, set[UUID]] = {"draft": set(), "receipt": set(), "grant": set()}
    document_ids = set()
    for item in items:
        if item.object is not None and item.object.kind in ids:
            ids[item.object.kind].add(item.object.id)
            if (
                item.action in ("delete_document", "restore_document")
                and item.object.kind == "draft"
            ):
                document_ids.add(item.object.id)
    labels: dict[tuple[ObjectKind, UUID], str] = {}
    if ids["draft"]:
        cursor.execute(_DRAFT_LABELS, {"space_id": space_id, "ids": sorted(ids["draft"])})
        for row in cursor.fetchall():
            label = _known(row["counterparty"])
            if label:
                labels[("draft", row["id"])] = label
    unnamed = document_ids - {identity for kind, identity in labels if kind == "draft"}
    if unnamed:
        cursor.execute(
            "select e.id,coalesce("
            " (select coalesce(d.draft->>'filename',s.text_content) from public.business_draft_sources l"
            " join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id"
            " left join public.financial_document_extractions d on d.connection_id=s.connection_id"
            " where l.space_id=e.owner_space_id and l.draft_id=e.id order by s.received_at,s.id limit 1),"
            " (select d.draft->>'filename' from public.financial_import_observations o"
            " join public.financial_document_extractions d on d.connection_id=o.connection_id and d.user_id=o.user_id"
            " where o.event_id=e.id and o.user_id=e.user_id order by o.first_seen_at,o.id limit 1)) as label"
            " from public.financial_import_events e where e.owner_space_id=%s and e.id=any(%s)",
            (space_id, sorted(unnamed)),
        )
        for row in cursor.fetchall():
            if row["label"]:
                labels[("draft", row["id"])] = row["label"]
    if ids["receipt"]:
        cursor.execute(
            "select d.connection_id,d.draft->>'filename' as label from public.financial_document_extractions d"
            " join public.financial_source_connections c on c.id=d.connection_id and c.user_id=d.user_id"
            " where c.owner_space_id=%s and d.connection_id=any(%s)",
            (space_id, sorted(ids["receipt"])),
        )
        for row in cursor.fetchall():
            if row["label"]:
                labels[("receipt", row["connection_id"])] = row["label"]
    if ids["grant"]:
        cursor.execute(_GRANT_LABELS, {"space_id": space_id, "ids": sorted(ids["grant"])})
        grantees = {row["id"]: row["grantee_id"] for row in cursor.fetchall()}
        found = people(cursor.connection, viewer, grantees.values())
        for grant, grantee in grantees.items():
            label = person_label(found.get(str(grantee)))
            if label:
                labels[("grant", grant)] = label
    return labels


def _known(fact: object) -> str | None:
    if not isinstance(fact, Mapping) or fact.get("state") != "known":
        return None
    value = fact.get("value")
    return value.strip() or None if isinstance(value, str) else None
