from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from argus.api.business import (
    BusinessContext,
    _captured,
    require_business_surface,
    unavailable_problem,
)
from argus.api.business_spaces import business_spaces
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.ingestion import IngestionContext, require_ingestion_context
from argus.domain.business.actions import BusinessActions
from argus.domain.business.actions.dossier import record_context
from argus.domain.business.actions.receipts import draft_for_receipt
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import Refused
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dossier import AccountChoice, RecordContext
from argus.domain.business.contracts.facts import (
    BusinessAccountFunding,
    BusinessResolution,
    Known,
)
from argus.domain.business.scope import BusinessScope
from argus.domain.business.service import BusinessService
from argus.domain.business.transactions import GrantImportStore, transaction
from argus.domain.ingestion.receipt_review import DUPLICATE_WARNINGS
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.recording.repository import InMemoryFinancialAccountRepository


def action_problem(request: Request, refusal: Refused) -> HTTPException:
    status = {
        "not_found": 404,
        "permission_denied": 403,
        "stale_version": 409,
        "idempotency_conflict": 409,
        "invalid_input": 422,
    }[refusal.outcome]
    if refusal.code == "draft_not_prepared":
        status = 409
    return problem(
        request,
        status_code=status,
        code=refusal.code,
        title=refusal.code.replace("_", " ").capitalize(),
        detail=refusal.code,
        headers=NO_STORE,
    )


@dataclass(frozen=True)
class DraftContext:
    service: BusinessActions
    actor_id: UUID


def require_drafts(
    request: Request,
    _surface: Annotated[None, Depends(require_business_surface)],
    ingestion: Annotated[IngestionContext, Depends(require_ingestion_context)],
) -> DraftContext:
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None or not isinstance(ingestion.hub.sink, ReconciliationService):
        raise unavailable_problem(request)
    return DraftContext(
        BusinessActions(pool, ingestion.hub.sink), UUID(ingestion.user_id)
    )


def bind_to_grant(documents, hub, actions, context, capability):  # noqa: ANN001, ANN201
    """The one place a documents service is bound to a person's Business grant:
    the same hub with an import sink that acts only as that grant, for a request
    or for a delivery that has none. Returns the bound service and its sink."""

    imports = ReconciliationService(
        GrantImportStore(actions.authority, context, capability),
        hub.sink.money,
        hub.sink.clock,
        connections=hub.sink.connections,
    )
    scoped_hub, scoped_documents = copy(hub), copy(documents)
    scoped_hub.sink = imports
    scoped_documents.hub = scoped_hub
    return scoped_documents, imports


def scoped_legacy(request, documents, hub, user_id, scope):
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None:
        if not isinstance(hub.sink.money.repository, InMemoryFinancialAccountRepository):
            raise unavailable_problem(request)
        account_rows = hub.sink.money.accounts.list_accounts(
            user_id=scope.person_id, scope=scope.owner
        )
        space = business_spaces().open_space(user_id)
        record = RecordContext(
            space_id=scope.owner.space_id,
            space_name=space.name,
            accounts=tuple(
                AccountChoice(
                    id=row.account.id,
                    nickname=row.account.nickname,
                    type=row.account.type,
                    currency=row.account.currency,
                )
                for row in account_rows
            ),
            capabilities={"read", "prepare"},
        )
        return BusinessContext(
            scope, BusinessService(documents, hub.sink, _captured), record
        )
    actions = BusinessActions(pool, hub.sink)
    try:
        receipt_id = request.path_params.get("receipt_id")
        context = (
            actions.context_for_receipt(UUID(user_id), UUID(receipt_id))
            if receipt_id
            else actions.resolve_actor(
                TrustedActor(
                    actor_id=user_id, actor_kind="member", space_id=scope.owner.space_id
                )
            )
        )
        record = actions.record_context(context)
        capability = (
            "read"
            if request.method == "GET"
            else ("approve" if request.url.path.endswith("/confirm") else "prepare")
        )
        if capability not in record.capabilities:
            raise ActionError("permission_denied", "business_permission_denied")
    except ValueError:
        raise action_problem(
            request, Refused(outcome="not_found", code="business_record_not_found")
        ) from None
    except ActionError as error:
        raise action_problem(request, error.result) from None
    scoped_documents, imports = bind_to_grant(
        documents, hub, actions, context, capability
    )
    return BusinessContext(
        BusinessScope(context.owner_id, context.scope),
        BusinessService(scoped_documents, imports, _captured),
        record,
    )


def require_legacy_receipt_write(context: BusinessContext, receipt_id: str) -> None:
    store = context.service.imports.store
    if isinstance(store, GrantImportStore):
        with transaction(store.authority, store.context, "prepare") as tx:
            draft_id, ambiguous = draft_for_receipt(tx, UUID(receipt_id), None)
            if draft_id is not None or ambiguous:
                raise ActionError("invalid_input", "business_action_required")


def read_attention(event) -> dict:  # noqa: ANN001
    """Why a prepared receipt still needs a person, from what the read left on
    the draft: several purchases, none it could settle, or purchases the
    recorded expense does not cover (until a person records or settles them)."""

    business = event.resolution.get("business")
    if business is None:
        return {}
    resolution = BusinessResolution.model_validate(business)
    read = resolution.read_purchases
    if event.state == "open" and read:
        return {
            "status": "needs_attention",
            "attention": "several_purchases",
            "error_code": "several_purchases_found",
        }
    if (
        event.state == "open"
        and resolution.read_total is not None
        and not isinstance(resolution.facts.amount, Known)
    ):
        return {
            "status": "needs_attention",
            "attention": "no_purchase_found",
            "error_code": "no_purchase_found",
        }
    if event.state == "accepted" and resolution.unrecorded_purchases():
        return {"attention": "several_purchases", "error_code": "purchases_unrecorded"}
    return {}


_BRIDGE_STATUS = {
    "open": "review_ready",
    "accepting": "review_ready",
    "accepted": "confirmed",
    "dismissed": "dismissed",
}


def linked_drafts(tx, connection_ids: list[str]) -> dict[str, list[dict]]:  # noqa: ANN001
    """The bridge drafts each receipt is linked to, one query for all of them."""

    if not connection_ids:
        return {}
    rows = tx.rows(
        "select distinct s.connection_id, e.id, e.state, e.version, e.attention,"
        " e.activity_id, e.resolution, o.connection_id as duplicate_receipt_id"
        " from public.business_sources s"
        " join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id"
        " join public.financial_import_events e on e.id=l.draft_id and e.owner_space_id=l.space_id"
        " left join lateral ("
        "   select s2.connection_id from public.business_draft_sources l2"
        "   join public.business_sources s2 on s2.id=l2.source_id and s2.space_id=l2.space_id"
        "   where l2.space_id=e.owner_space_id and l2.draft_id=(e.possible_duplicates)[1]"
        "   and s2.connection_id is not null limit 1"
        " ) o on true"
        " where s.space_id=%s and s.connection_id = any(%s) and e.user_id=%s"
        " and e.resolution ? 'business' order by e.id",
        (
            tx.context.actor.space_id,
            [UUID(connection_id) for connection_id in connection_ids],
            tx.context.owner_id,
        ),
    )
    found: dict[str, list[dict]] = {}
    for row in rows:
        found.setdefault(str(row["connection_id"]), []).append(row)
    return found


def draft_overlay(summary: dict, drafts: list[dict]) -> dict:
    """A receipt linked to a bridge draft takes its status, facts and message
    from that draft, never from legacy import events. Keys absent from the
    wire shape handed in (a summary has no draft id) stay absent."""

    legacy = summary.get("draft_id")
    ids = {str(row["id"]) for row in drafts}
    if legacy:
        ids.add(str(legacy))
    if len(ids) > 1:
        out = {
            **summary,
            "status": "needs_attention",
            "attention": "check_details",
            "error_code": "receipt_candidate_ambiguous",
            "preparable": False,
            "enterable": False,
        }
        if "draft_id" in summary:
            out["draft_id"] = None
        return out
    if not drafts or legacy == str(drafts[0]["id"]):
        return summary
    row = drafts[0]
    facts = BusinessResolution.model_validate(row["resolution"]["business"]).facts

    def value(fact):  # noqa: ANN001, ANN202
        return fact.value if isinstance(fact, Known) else None

    funding = value(facts.funding)
    out = {
        **summary,
        "status": _BRIDGE_STATUS.get(row["state"], "review_ready"),
        "attention": None,
        "error_code": None,
        "preparable": False,
        "enterable": False,
        "expense_id": str(row["activity_id"]) if row["activity_id"] else None,
        "merchant": value(facts.counterparty),
        "amount": value(facts.amount),
        "currency": value(facts.currency),
        "occurred_on": (value(facts.occurred_on) or None)
        and value(facts.occurred_on).isoformat(),
        "category_id": value(facts.category_id),
        "account_id": str(funding.account_id)
        if isinstance(funding, BusinessAccountFunding)
        else None,
    }
    for key, item in (("draft_id", str(row["id"])), ("version", row["version"])):
        if key in summary:
            out[key] = item
    out.update(
        read_attention(SimpleNamespace(state=row["state"], resolution=row["resolution"]))
    )
    if row["state"] == "open" and row["attention"] in DUPLICATE_WARNINGS:
        original = row.get("duplicate_receipt_id")
        out.update(
            status="needs_attention",
            attention="duplicate",
            error_code="possible_duplicate",
            duplicate_of=str(original) if original else None,
        )
    return out


def bridged(context: BusinessContext, summaries: list[dict]) -> list[dict]:
    """Every receipt view the API returns passes here: with the hosted bridge,
    a linked draft owns the receipt's state."""

    store = context.service.imports.store
    if not isinstance(store, GrantImportStore) or not summaries:
        return summaries
    with transaction(store.authority, store.context) as tx:
        drafts = linked_drafts(tx, [summary["id"] for summary in summaries])
        return [
            draft_overlay(summary, drafts.get(summary["id"], [])) for summary in summaries
        ]


def receipt_summaries(context: BusinessContext, view: str) -> list[dict]:
    """The receipt list, overlaid; the inbox leaves out what is saved or dismissed."""

    from argus.api.routers.business import _email_flagged
    from argus.domain.business.receipts import CLOSED

    receipts = _email_flagged(context, context.service.receipts(context.scope))
    items = bridged(context, [receipt.summary() for receipt in receipts])
    if view == "inbox":
        items = [item for item in items if item["status"] not in CLOSED]
    return items


def overview_with_drafts(context: BusinessContext, start, end) -> dict:  # noqa: ANN001
    """The home overview with its receipt counts taken from the overlaid views,
    so an approved draft is a saved expense, not a receipt awaiting review."""

    from argus.domain.business.receipts import AWAITING_REVIEW

    data = context.service.overview(context.scope, start, end)
    items = receipt_summaries(context, "all")
    data["awaiting_review"] = sum(item["status"] in AWAITING_REVIEW for item in items)
    data["needs_attention"] = sum(item["status"] == "needs_attention" for item in items)
    return data


def receipt_summary(context: BusinessContext, receipt) -> dict:  # noqa: ANN001
    """One receipt's summary, overlaid: what upload and prepare answer with."""

    return bridged(context, [receipt.summary()])[0]


def linked_receipts(tx, activity_ids: list[str]) -> dict[str, str]:  # noqa: ANN001
    """Activity id to the one receipt whose linked bridge draft recorded it.

    An activity recorded from a draft linked to several receipts, or to
    none, has no entry: the person opens those through the draft."""

    if not activity_ids:
        return {}
    rows = tx.rows(
        "select e.activity_id, s.connection_id from public.financial_import_events e"
        " join public.business_draft_sources l on l.draft_id=e.id and l.space_id=e.owner_space_id"
        " join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id"
        " where e.owner_space_id=%s and e.user_id=%s and e.activity_id = any(%s)"
        " and e.resolution ? 'business' and s.connection_id is not null",
        (
            tx.context.actor.space_id,
            tx.context.owner_id,
            [UUID(activity_id) for activity_id in activity_ids],
        ),
    )
    held: dict[str, set[str]] = {}
    for row in rows:
        held.setdefault(str(row["activity_id"]), set()).add(str(row["connection_id"]))
    return {activity: ids.pop() for activity, ids in held.items() if len(ids) == 1}


def _with_receipts(context: BusinessContext, expenses: list[dict]) -> list[dict]:
    """Saved expenses with the receipt a linked bridge draft recorded them from.

    The legacy lookup reaches a receipt through import observations, which a
    bridge draft never has, so an expense approved from a draft had no
    receipt to open."""

    store = context.service.imports.store
    missing = [item["id"] for item in expenses if item.get("receipt_id") is None]
    if not isinstance(store, GrantImportStore) or not missing:
        return expenses
    with transaction(store.authority, store.context) as tx:
        found = linked_receipts(tx, missing)
    return [
        {**item, "receipt_id": found.get(item["id"], item.get("receipt_id"))}
        for item in expenses
    ]


def expenses_with_receipts(context: BusinessContext, start, end) -> list[dict]:  # noqa: ANN001
    """The saved expenses of a period, each with the receipt that opens its record."""

    return _with_receipts(context, context.service.expenses(context.scope, start, end))


def search_with_drafts(context: BusinessContext, q: str, limit: int) -> dict:
    """The search result with its receipts overlaid and its expenses linked to
    their receipts; accounts as found."""

    receipts = context.service.receipts(context.scope)
    views = {
        item["id"]: item for item in bridged(context, [r.summary() for r in receipts])
    }
    found = context.service.search(context.scope, q, limit, views)
    found["expenses"] = _with_receipts(context, found["expenses"])
    return found


def updates_with_drafts(context: BusinessContext) -> list[dict]:
    """The updates feed built from the overlaid receipt views, so a linked draft's
    state (ready, needs attention, saved) is the one the feed reports."""

    from argus.api.routers.business import _email_flagged

    receipts = _email_flagged(context, context.service.receipts(context.scope))
    views = {
        item["id"]: item for item in bridged(context, [r.summary() for r in receipts])
    }
    return context.service.updates(context.scope, views)


def receipt_detail(context: BusinessContext, receipt) -> dict:
    [detail] = bridged(context, [receipt.detail()])
    store = context.service.imports.store
    if isinstance(store, GrantImportStore):
        with transaction(store.authority, store.context) as tx:
            detail["record_context"] = record_context(tx).model_dump(mode="json")
        return detail
    if context.record_context is not None:
        detail["record_context"] = context.record_context.model_dump(mode="json")
    return detail
