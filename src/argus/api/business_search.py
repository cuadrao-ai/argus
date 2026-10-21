"""GET /business/search: one read over the owners of each record, a page per kind.

Records come from their owners on every request: the money service and the
overlaid receipt views (``search_with_drafts``), the bridge drafts' fiscal
facts, and the email queue. The member's opens (``search_memory``) rank them.
"""

from __future__ import annotations

from typing import Any

from argus.api.business import BusinessContext
from argus.api.business_drafts import search_with_drafts
from argus.api.business_spaces import business_search_memory
from argus.api.email_intake import email_intake
from argus.domain import financial_search
from argus.domain.business import search as business_search
from argus.domain.business.contracts.facts import BusinessResolution, Known
from argus.domain.business.search import KINDS, SearchKind, SearchQuery
from argus.domain.business.search_memory import ranked
from argus.domain.business.transactions import GrantImportStore, transaction

# Search reads the Business's newest deliveries, as many as the email inbox lists.
DELIVERY_WINDOW = 200


def fiscal_numbers(context: BusinessContext) -> dict[str, tuple[str, ...]]:
    """The RNC, NCF and e-CF each bridge draft knows, by the activity it
    recorded and by each receipt linked to it. The latest draft of a record
    speaks for it."""

    store = context.service.imports.store
    if not isinstance(store, GrantImportStore):
        return {}
    with transaction(store.authority, store.context) as tx:
        rows = tx.rows(
            "select e.activity_id, e.resolution,"
            " array_remove(array_agg(s.connection_id), null) as receipt_ids"
            " from public.financial_import_events e"
            " left join public.business_draft_sources l on l.draft_id=e.id"
            " and l.space_id=e.owner_space_id"
            " left join public.business_sources s on s.id=l.source_id"
            " and s.space_id=l.space_id"
            " where e.owner_space_id=%s and e.user_id=%s and e.resolution ? 'business'"
            " group by e.id order by e.updated_at, e.id",
            (tx.context.actor.space_id, tx.context.owner_id),
        )
    found: dict[str, tuple[str, ...]] = {}
    for row in rows:
        fiscal = BusinessResolution.model_validate(
            row["resolution"]["business"]
        ).facts.fiscal
        numbers = (
            tuple(
                fact.value
                for fact in (fiscal.rnc, fiscal.ncf, fiscal.ecf)
                if isinstance(fact, Known)
            )
            if fiscal is not None
            else ()
        )
        records = [str(receipt) for receipt in row["receipt_ids"]]
        if row["activity_id"] is not None:
            records.append(str(row["activity_id"]))
        found.update(dict.fromkeys(records, numbers))
    return found


def _email_hits(
    context: BusinessContext, query: SearchQuery
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deliveries by sender and subject, sender rules by address; none while
    email receiving is off."""

    runtime = email_intake()
    if runtime is None:
        return [], []
    space_id = context.scope.owner.space_id
    deliveries = [
        {
            "id": item.id,
            "sender": item.sender,
            "subject": item.subject,
            "received_at": item.received_at,
            "state": item.state,
            "inbox_group": item.inbox_group,
        }
        for item in runtime.store.list(space_id, limit=DELIVERY_WINDOW)
        if business_search.matches(
            query, " ".join(filter(None, [item.sender, item.subject]))
        )
    ]
    senders = [
        {"id": rule.id, "kind": rule.kind, "value": rule.value, "status": rule.status}
        for rule in runtime.store.list_senders(space_id)
        if business_search.matches(query, rule.value)
    ]
    return deliveries, senders


def search(
    context: BusinessContext,
    q: str,
    *,
    kind: SearchKind | None,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    """A page of each kind, or of the one ``kind`` asked for, with the records
    this member opened before ranked first. A cursor is scoped to the kind it
    was issued for, so it continues only that ``kind``; an open recorded since
    reorders the list, so its cursor is stale."""

    query = business_search.parse(q)
    found = search_with_drafts(context, query, fiscal_numbers(context))
    found["email_deliveries"], found["email_senders"] = _email_hits(context, query)
    space_id = context.scope.owner.space_id
    member = context.scope.actor_id or context.scope.person_id
    memory = business_search_memory()
    opens = memory.opens(space_id, member) if memory is not None else {}
    result: dict[str, Any] = {name: [] for name in KINDS}
    result["next_cursors"] = dict.fromkeys(KINDS)
    for name in (kind,) if kind else KINDS:
        items = ranked(found[name], name, opens)
        result[name], result["next_cursors"][name] = financial_search.page(
            items,
            scope=financial_search.digest([space_id, member, q, name]),
            snapshot=financial_search.digest([item["id"] for item in items]),
            limit=limit,
            cursor=cursor,
        )
    return result
