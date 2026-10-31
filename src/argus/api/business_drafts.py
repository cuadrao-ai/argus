from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from argus.api import state as api_state
from argus.api.business import (
    BusinessContext,
    _captured,
    require_business_surface,
    unavailable_problem,
    working_scope,
)
from argus.api.business_spaces import (
    business_access,
    business_spaces,
    space_missing_problem,
)
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.ingestion import IngestionContext, require_ingestion_context
from argus.domain.business.actions import BusinessActions
from argus.domain.business.actions.dossier import record_context
from argus.domain.business.actions.marks import (
    MARKER_COLUMNS,
    MARKER_JOIN,
    record_marks,
)
from argus.domain.business.actions.receipts import draft_for_receipt
from argus.domain.business.authority import ActionContext, ActionError, authorize
from argus.domain.business.contracts.actions import Refused
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dossier import AccountChoice, RecordContext
from argus.domain.business.contracts.facts import (
    BusinessAccountFunding,
    BusinessResolution,
    Known,
    personal_mark_admits,
)
from argus.domain.business.scope import BusinessScope, resolve_business_scope
from argus.domain.business.search import SearchQuery
from argus.domain.business.service import BusinessService
from argus.domain.business.transactions import (
    GrantImportStore,
    LegacyAction,
    record_legacy_action,
    transaction,
)
from argus.domain.ingestion.receipt_review import DUPLICATE_WARNINGS
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.recording.repository import InMemoryFinancialAccountRepository

SEARCH_MEMORY_PATH = "/api/v1/business/search/"


def action_problem(request: Request, refusal: Refused) -> HTTPException:
    status = {
        "not_found": 404,
        "permission_denied": 403,
        "stale_version": 409,
        "idempotency_conflict": 409,
        "invalid_input": 422,
    }[refusal.outcome]
    if refusal.code in ("draft_not_prepared", "business_606_not_applicable"):
        status = 409
    return problem(
        request,
        status_code=status,
        code=refusal.code,
        title=refusal.code.replace("_", " ").capitalize(),
        detail=refusal.code,
        context={"existing_record_id": str(refusal.existing_record_id)}
        if refusal.existing_record_id
        else None,
        headers=NO_STORE,
    )


@dataclass(frozen=True)
class DraftContext:
    service: BusinessActions
    actor_id: UUID
    # The Business the caller is working in, proven per request: the chosen
    # grant's, else their own. A record of any other Business is missing.
    space_id: str | None = None
    grant_id: UUID | None = None

    def for_draft(self, draft_id: UUID) -> ActionContext:
        return self.service.context_for_draft(
            self.actor_id, draft_id, space_id=self.space_id, grant_id=self.grant_id
        )

    def for_space(self, request: Request, spaces=None) -> ActionContext:  # noqa: ANN001
        """The working Business itself, for routes that name no record: the
        chosen grant's, else the caller's own open space."""

        space_id = self.space_id
        if space_id is None and spaces is not None:
            own = resolve_business_scope(spaces, str(self.actor_id))
            space_id = own.owner.space_id if own else None
        if space_id is None:
            raise space_missing_problem(request)
        return self.service.resolve_actor(
            TrustedActor(
                actor_id=self.actor_id, actor_kind="member", space_id=UUID(space_id)
            ),
            grant_id=self.grant_id,
        )


def require_drafts(
    request: Request,
    _surface: Annotated[None, Depends(require_business_surface)],
    ingestion: Annotated[IngestionContext, Depends(require_ingestion_context)],
) -> DraftContext:
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    spaces = business_spaces()
    if (
        pool is None
        or spaces is None
        or not isinstance(ingestion.hub.sink, ReconciliationService)
    ):
        raise unavailable_problem(request)
    scope = working_scope(request, spaces, ingestion.user_id)
    if scope is None:
        # No chosen grant and no own Business: nothing is in scope, by id either.
        raise space_missing_problem(request)
    return DraftContext(
        BusinessActions(pool, ingestion.hub.sink),
        UUID(ingestion.user_id),
        scope.owner.space_id,
        UUID(scope.grant_id) if scope.grant_id else None,
    )


def stored_drafts(
    request: Request,
    _surface: Annotated[None, Depends(require_business_surface)],
    ingestion: Annotated[IngestionContext, Depends(require_ingestion_context)],
) -> DraftContext | None:
    """``require_drafts`` for a read whose answer without a store is nothing:
    None when the in-memory app keeps no Business store, once the caller's
    Business is in scope. Durable mode refuses exactly as ``require_drafts``."""

    pool = getattr(request.app.state, "financial_accounts_pool", None)
    spaces = business_spaces()
    if pool is not None or api_state.PERSISTENCE_MODE == "supabase" or spaces is None:
        return require_drafts(request, _surface, ingestion)
    if working_scope(request, spaces, ingestion.user_id) is None:
        raise space_missing_problem(request)
    return None


def legacy_action(request) -> LegacyAction | None:  # noqa: ANN001
    """The name a legacy receipt write leaves in the ledger, from the route."""

    path = request.url.path
    if request.method == "PATCH" and path.endswith("/review"):
        return "receipt_review"
    if request.method == "POST" and path.endswith("/confirm"):
        return "receipt_confirm"
    return None


def request_key(request) -> str:  # noqa: ANN001
    """What names this request in the ledger: its idempotency key, else a
    one-off, so a replay repeats its row and a plain second write gets its own."""

    from uuid import uuid4

    return (request.headers.get("Idempotency-Key") or "").strip() or uuid4().hex


def bind_to_grant(documents, hub, actions, context, capability, action=None, key=None):  # noqa: ANN001, ANN201
    """The one place a documents service is bound to a person's Business grant:
    the same hub with an import sink that acts only as that grant, for a request
    or for a delivery that has none. Returns the bound service and its sink."""

    imports = ReconciliationService(
        GrantImportStore(actions.authority, context, capability, action, key),
        hub.sink.money,
        hub.sink.clock,
        connections=hub.sink.connections,
    )
    scoped_hub, scoped_documents = copy(hub), copy(documents)
    scoped_hub.sink = imports
    scoped_documents.hub = scoped_hub
    return scoped_documents, imports


def _needs_only_read(request) -> bool:
    """A write that needs only ``read``: marking a receipt read, or the
    member's own search memory."""

    if request.url.path.startswith(SEARCH_MEMORY_PATH):
        return True
    receipt_id = request.path_params.get("receipt_id")
    return bool(
        receipt_id
        and request.method == "POST"
        and request.url.path == f"/api/v1/business/receipts/{receipt_id}/read"
    )


def scoped_legacy(request, documents, hub, user_id, scope):
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None:
        if not isinstance(hub.sink.money.repository, InMemoryFinancialAccountRepository):
            raise unavailable_problem(request)
        account_rows = hub.sink.money.accounts.list_accounts(
            user_id=scope.person_id, scope=scope.owner
        )
        space = business_spaces().get(scope.owner.space_id)
        capabilities = {"read", "prepare"}
        if scope.actor_id is not None:
            # A chosen grant: its own capabilities, never approve for a member.
            held = business_access().capabilities(scope.owner.space_id, scope.actor_id)
            capabilities = set(held)
            if not scope.acting_as_owner:
                needed = (
                    "read"
                    if (
                        request.method == "GET"
                        and not request.url.path.endswith("/source")
                    )
                    or _needs_only_read(request)
                    else (
                        "download"
                        if request.url.path.endswith("/source")
                        else "approve"
                        if request.url.path.endswith("/confirm")
                        else "prepare"
                    )
                )
                if needed not in scope.permissions:
                    raise action_problem(
                        request,
                        Refused(
                            outcome="permission_denied",
                            code="business_permission_denied",
                        ),
                    )
        record = RecordContext(
            space_id=scope.owner.space_id,
            space_name=space.name if space else "",
            accounts=tuple(
                AccountChoice(
                    id=row.account.id,
                    nickname=row.account.nickname,
                    type=row.account.type,
                    currency=row.account.currency,
                )
                for row in account_rows
            ),
            capabilities=capabilities,
        )
        return BusinessContext(
            scope, BusinessService(documents, hub.sink, _captured), record
        )
    actions = BusinessActions(pool, hub.sink)
    try:
        receipt_id = request.path_params.get("receipt_id")
        grant_id = UUID(scope.grant_id) if scope and scope.grant_id else None
        context = (
            # Pinned to the Business the caller works in: a receipt of another
            # Business is missing, whatever other grants the caller holds.
            actions.context_for_receipt(
                UUID(user_id),
                UUID(receipt_id),
                space_id=scope.owner.space_id if scope else None,
                grant_id=grant_id,
            )
            if receipt_id
            else actions.resolve_actor(
                TrustedActor(
                    actor_id=user_id, actor_kind="member", space_id=scope.owner.space_id
                ),
                grant_id=grant_id,
            )
        )
        record = actions.record_context(context)
        capability = (
            "read"
            if (request.method == "GET" and not request.url.path.endswith("/source"))
            or _needs_only_read(request)
            else (
                "download"
                if request.url.path.endswith("/source")
                else "approve"
                if request.url.path.endswith("/confirm")
                else "prepare"
            )
        )
        from argus.domain.business.roles import ROLE_PERMISSIONS

        if capability not in ROLE_PERMISSIONS[context.business_role]:
            raise ActionError("permission_denied", "business_permission_denied")
    except ValueError:
        raise action_problem(
            request, Refused(outcome="not_found", code="business_record_not_found")
        ) from None
    except ActionError as error:
        raise action_problem(request, error.result) from None
    scoped_documents, imports = bind_to_grant(
        documents,
        hub,
        actions,
        context,
        capability,
        legacy_action(request),
        request_key(request),
    )
    return BusinessContext(
        BusinessScope(
            context.owner_id,
            context.scope,
            actor_id=user_id,
            grant_id=str(context.grant_id),
            role="owner" if context.is_current_owner else "accountant",
            business_role=context.business_role,
            **({"country": scope.country, "currency": scope.currency} if scope else {}),
        ),
        BusinessService(scoped_documents, imports, _captured),
        record,
    )


def upload_recorder(context: BusinessContext, request):  # noqa: ANN001, ANN201
    """A saved upload is a write on the legacy surface: one ledger row naming
    the grant it ran under, written in the transaction that saves the receipt,
    so no receipt is saved without its row. The in-memory app keeps no ledger."""

    store = context.service.imports.store
    if not isinstance(store, GrantImportStore):
        return None
    key = request_key(request)

    def record(connection, receipt_id: str) -> None:  # noqa: ANN001
        live = authorize(connection, store.context.actor, store.context.grant_id)
        if live.context.owner_id != store.context.owner_id:
            raise ActionError("not_found", "business_record_not_found")
        live.require("prepare")
        record_legacy_action(connection, live, "receipt_upload", [receipt_id], key)

    return record


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
        "select distinct s.connection_id, e.id, e.state, e.version, e.updated_at, e.attention,"
        " e.activity_id, e.resolution, o.connection_id as duplicate_receipt_id,"
        + MARKER_COLUMNS
        + " from public.business_sources s"
        " join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id"
        " join public.financial_import_events e on e.id=l.draft_id and e.owner_space_id=l.space_id"
        " left join lateral ("
        "   select s2.connection_id from public.business_draft_sources l2"
        "   join public.business_sources s2 on s2.id=l2.source_id and s2.space_id=l2.space_id"
        "   where l2.space_id=e.owner_space_id and l2.draft_id=(e.possible_duplicates)[1]"
        "   and s2.connection_id is not null limit 1"
        " ) o on true"
        + MARKER_JOIN
        + " where s.space_id=%s and s.connection_id = any(%s) and e.user_id=%s"
        " and e.resolution ? 'business' order by e.id",
        (
            tx.context.actor.space_id,
            [UUID(connection_id) for connection_id in connection_ids],
            tx.context.owner_id,
        ),
    )
    found: dict[str, list[dict]] = {}
    for row in rows:
        facts = BusinessResolution.model_validate(row["resolution"]["business"]).facts
        row["marks"] = record_marks(facts, row, tx.context.owner_id)
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
    if not drafts:
        return summary
    row = drafts[0]
    resolution = BusinessResolution.model_validate(row["resolution"]["business"])
    if legacy == str(row["id"]):
        return (
            {**summary, "due_on": resolution.due_on} if "due_on" in summary else summary
        )
    facts = resolution.facts

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
        **row["marks"],
        "document_type": resolution.document_type,
        "document_type_detected": resolution.document_type_detected,
        "document_type_editable": row["state"] == "open",
    }
    for key, item in (
        ("draft_id", str(row["id"])),
        ("version", row["version"]),
        ("due_on", resolution.due_on),
    ):
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

    from argus.api.business_receipt_activity import project

    if not summaries:
        return summaries
    views = project(context, summaries)
    if not isinstance(context.service.imports.store, GrantImportStore):
        return views
    # Anyone who may prepare marks or unmarks Personal; a read-only grant reads it.
    editable = "prepare" in (
        context.record_context.capabilities if context.record_context else ()
    )
    # The overlay names "personal" only for a receipt one draft owns: nothing else to mark.
    # The same people set its document type while that draft is open.
    return [
        {
            **view,
            **({"personal_editable": editable} if "personal" in view else {}),
            **(
                {"document_type_editable": editable}
                if view.get("document_type_editable")
                else {}
            ),
        }
        for view in views
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
    """The home overview with its receipt counts from the Bandeja's own
    projection over the overlaid views: an approved draft is a saved expense
    and the email itself is not a receipt, the same as in the Bandeja."""

    from argus.api.business_receipt_activity import inbox
    from argus.domain.business import ledger

    data = context.service.overview(context.scope, start, end)
    counts = inbox(context, receipt_summaries(context, "all"))
    data["needs_attention"] = counts["needs_attention_count"]
    data["awaiting_review"] = counts["pending_review_count"] - data["needs_attention"]
    data["ready_to_review_count"] = counts["ready_to_review_count"]
    data["por_igualar_count"] = counts["por_igualar_count"]
    # Gastos reales are the receipts the Personal mark admits, by the rule
    # month close and Registros share; con valor fiscal are the real ones that
    # carry an NCF or an e-CF; the rest do not go into the 606. All three from
    # the same rows, so the line never disagrees.
    rows = _with_records(
        context, context.service.expense_rows(context.scope, start, data["to"])
    )
    real = [
        row
        for row in rows
        if personal_mark_admits(bool(row.get("personal")), row.get("include_606"))
    ]
    fiscal = [row for row in real if row.get("fiscal_value")]
    data["totals"] = ledger.totals(real)
    data["fiscal_totals"] = ledger.totals(fiscal)
    data["without_fiscal_totals"] = ledger.totals(
        [row for row in real if not row.get("fiscal_value")]
    )
    return data


def receipt_summary(context: BusinessContext, receipt) -> dict:  # noqa: ANN001
    """One receipt's summary, overlaid: what upload and prepare answer with."""

    return bridged(context, [receipt.summary()])[0]


def linked_records(tx, activity_ids: list[str]) -> dict[str, dict[str, str | None]]:  # noqa: ANN001
    """Activity id to the bridge draft that recorded it and, when the draft is
    linked to exactly one receipt, that receipt. A draft linked to several
    receipts or to none names no receipt: the person opens the draft."""

    if not activity_ids:
        return {}
    rows = tx.rows(
        "select e.activity_id, e.id as draft_id, s.connection_id, e.resolution,"
        + MARKER_COLUMNS
        + " from public.financial_import_events e"
        " left join public.business_draft_sources l on l.draft_id=e.id"
        " and l.space_id=e.owner_space_id"
        " left join public.business_sources s on s.id=l.source_id"
        " and s.space_id=l.space_id and s.connection_id is not null"
        + MARKER_JOIN
        + " where e.owner_space_id=%s and e.user_id=%s and e.activity_id = any(%s)"
        " and e.resolution ? 'business'"
        # The latest revised draft speaks for its activity, whatever order the rows come in.
        " order by e.updated_at desc, e.id desc",
        (
            tx.context.actor.space_id,
            tx.context.owner_id,
            [UUID(activity_id) for activity_id in activity_ids],
        ),
    )
    drafts: dict[str, set[str]] = {}
    receipts: dict[str, set[str]] = {}
    marks: dict[str, dict] = {}
    for row in rows:
        activity = str(row["activity_id"])
        drafts.setdefault(activity, set()).add(str(row["draft_id"]))
        if row["connection_id"]:
            receipts.setdefault(activity, set()).add(str(row["connection_id"]))
        typed = (row.get("resolution") or {}).get("business")
        if typed and activity not in marks:
            facts = BusinessResolution.model_validate(typed).facts
            marks[activity] = record_marks(facts, row, tx.context.owner_id)
    return {
        activity: {
            "draft_id": ids.pop() if len(ids) == 1 else None,
            "receipt_id": (
                receipts[activity].pop() if len(receipts.get(activity, ())) == 1 else None
            ),
            **marks.get(activity, {}),
        }
        for activity, ids in drafts.items()
    }


def _with_records(context: BusinessContext, expenses: list[dict]) -> list[dict]:
    """Saved expenses with the draft that recorded them and the receipt it came
    from. The legacy lookup reaches a receipt through import observations,
    which a bridge draft never has, so an expense approved from a draft had
    nothing to open."""

    store = context.service.imports.store
    if not isinstance(store, GrantImportStore) or not expenses:
        return expenses
    with transaction(store.authority, store.context) as tx:
        found = linked_records(tx, [item["id"] for item in expenses])
    return [
        {
            **item,
            **{
                key: value
                for key, value in found.get(item["id"], {}).items()
                if item.get(key) is None and value is not None
            },
        }
        for item in expenses
    ]


def expenses_with_receipts(
    context: BusinessContext,
    start,  # noqa: ANN001
    end,  # noqa: ANN001
    kind: str = "expense",
) -> list[dict]:
    """The saved expenses (or ventas, as ``income``) of a period, each with the
    receipt that opens its record."""

    return _with_records(
        context, context.service.expenses(context.scope, start, end, kind=kind)
    )


def expense_detail(context: BusinessContext, expense_id: str) -> dict:
    """One saved expense with the records behind it: a receipt to open, the
    draft that recorded it, or neither for an expense entered by hand."""

    [item] = _with_records(context, [context.service.expense(context.scope, expense_id)])
    return item


def search_with_drafts(
    context: BusinessContext,
    query: SearchQuery,
    numbers: dict[str, tuple[str, ...]] | None = None,
) -> dict:
    """Every match, unpaged: receipts overlaid and email-flagged as the Bandeja
    lists them, expenses and ventas linked to their receipts, accounts as found."""

    from argus.api.routers.business import _email_flagged

    receipts = _email_flagged(context, context.service.receipts(context.scope))
    views = {
        item["id"]: item for item in bridged(context, [r.summary() for r in receipts])
    }
    found = context.service.search(context.scope, query, views, numbers)
    found["expenses"] = _with_records(context, found["expenses"])
    found["ventas"] = _with_records(context, found["ventas"])
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


def with_whatsapp_sources(dossier, captured: frozenset[str]):  # noqa: ANN001, ANN201
    """The dossier's attachment sources that arrived by WhatsApp say so, from the
    intake store's captured connections, the fact /business/receipts reads; the
    stored source row says web for every attachment and is never written back."""

    if not captured:
        return dossier
    sources = tuple(
        source.model_copy(update={"channel": "whatsapp"})
        if source.kind == "attachment" and str(source.connection_id) in captured
        else source
        for source in dossier.sources
    )
    return dossier.model_copy(update={"sources": sources})


def with_source_channels(dossier, *, space_id: str, owner_id: str):  # noqa: ANN001, ANN201
    """Every dossier the drafts API returns passes here: WhatsApp first, then
    email, the same order the receipt list decides a channel."""

    return with_email_sources(
        with_whatsapp_sources(dossier, _captured(owner_id)), space_id
    )


def with_email_sources(dossier, space_id: str):  # noqa: ANN001, ANN201
    """The dossier's attachment sources that arrived by email say so, with their
    deliveries, from the email queue; the stored source row says web for every
    attachment, so this is decided here and never written back."""

    from argus.api.email_intake import (
        arrived_by_email,
        email_receipt_flags,
        email_review_note,
    )

    flags = email_receipt_flags(space_id)
    if not flags:
        return dossier
    delivery_ids = {
        delivery_id
        for source in dossier.sources
        if source.kind == "attachment" and str(source.connection_id) in flags
        for delivery_id in flags[str(source.connection_id)][0]
    }
    sources = tuple(
        source.model_copy(
            update={
                "channel": "email"
                if arrived_by_email(
                    source.received_at, flags[str(source.connection_id)][2]
                )
                else source.channel,
                "email_delivery_ids": flags[str(source.connection_id)][0],
            }
        )
        if source.kind == "attachment" and str(source.connection_id) in flags
        else source
        for source in dossier.sources
    )
    return dossier.model_copy(
        update={
            "sources": sources,
            "review_note": email_review_note(space_id, delivery_ids),
        }
    )


def unread_backlog(context: BusinessContext) -> list[str]:
    from argus.api.routers.business import _email_flagged

    documents = context.service.documents
    receipts = _email_flagged(context, context.service.receipts(context.scope))
    ids = []
    for receipt in receipts:
        if (
            receipt.email_original
            or receipt.draft.status != "saved"
            or receipt.draft.error_code is not None
            or not receipt.draft.source_available
        ):
            continue
        if (
            documents.store.get(user_id=context.scope.person_id, connection_id=receipt.id)
            is not None
        ):
            continue
        ids.append(receipt.id)
    return ids
