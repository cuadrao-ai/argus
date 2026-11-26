from __future__ import annotations

from copy import copy
from dataclasses import dataclass, replace
from functools import partial
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
    marker_people,
    record_marks,
)
from argus.domain.business.actions.receipts import draft_for_receipt
from argus.domain.business.annotations import (
    OWN_SOURCE_SQL,
    own_source_sql,
    supporting_uploads,
)
from argus.domain.business.authority import ActionContext, ActionError, authorize
from argus.domain.business.bandeja_group import confirmable_gaps
from argus.domain.business.contracts.actions import Refused
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.deletion import DeletedDocument, deletion
from argus.domain.business.contracts.dossier import (
    AccountChoice,
    BusinessDossier,
    RecordContext,
)
from argus.domain.business.contracts.facts import (
    BusinessAccountFunding,
    BusinessResolution,
    Known,
    personal_mark_admits,
)
from argus.domain.business.people import named_deletion, people
from argus.domain.business.receipt_consent import RECEIPT_READING_PERMISSION
from argus.domain.business.receipts import Receipt, draft_row, record_title
from argus.domain.business.record_origin import (
    OriginUpload,
    UploadIntake,
    draft_arrivals,
    record_origins,
)
from argus.domain.business.roles import Permission, legacy_capabilities, legacy_role
from argus.domain.business.scope import BusinessScope, resolve_business_scope
from argus.domain.business.search import SearchQuery
from argus.domain.business.service import BusinessService
from argus.domain.business.transactions import (
    GrantImportStore,
    LegacyAction,
    record_legacy_action,
    transaction,
)
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.receipt_review import duplicate_warning
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
        context=refusal.context or ({"existing_record_id": str(refusal.existing_record_id)}
        if refusal.existing_record_id
        else {
            "gaps": list(refusal.gaps),
            "confirmable": list(confirmable_gaps(refusal.gaps)),
        }
        if refusal.gaps
        else None),
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


def _legacy_permission(request: Request) -> Permission:
    path = request.url.path
    if path.endswith("/source"):
        return "download"
    if request.method == "GET" or _needs_only_read(request):
        return "read"
    if path.endswith("/receipt-reading"):
        return RECEIPT_READING_PERMISSION
    if path.endswith("/confirm"):
        return "approve"
    return "prepare"


def scoped_legacy(request, documents, hub, user_id, scope):
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None:
        if not isinstance(hub.sink.money.repository, InMemoryFinancialAccountRepository):
            raise unavailable_problem(request)
        account_rows = hub.sink.money.accounts.list_accounts(
            user_id=scope.person_id, scope=scope.owner
        )
        space = business_spaces().get(scope.owner.space_id)
        if _legacy_permission(request) not in scope.permissions:
            raise action_problem(
                request,
                Refused(outcome="permission_denied", code="business_permission_denied"),
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
            capabilities=legacy_capabilities(scope.business_role),
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
        capability = _legacy_permission(request)
        if capability not in context.permissions:
            raise ActionError("permission_denied", "business_permission_denied")
    except ValueError:
        raise action_problem(
            request, Refused(outcome="not_found", code="business_record_not_found")
        ) from None
    except ActionError as error:
        raise action_problem(request, error.result) from None
    return _granted(
        documents,
        hub,
        actions,
        context,
        capability,
        record,
        scope,
        legacy_action(request),
        request_key(request),
    )


def _granted(  # noqa: ANN202
    documents, hub, actions, context, capability, record, scope=None, action=None, key=None  # noqa: ANN001
):
    scoped_documents, imports = bind_to_grant(
        documents, hub, actions, context, capability, action, key
    )
    return BusinessContext(
        BusinessScope(
            context.owner_id,
            context.scope,
            actor_id=str(context.actor.actor_id),
            grant_id=str(context.grant_id),
            role=legacy_role(context.business_role),
            business_role=context.business_role,
            **({"country": scope.country, "currency": scope.currency} if scope else {}),
        ),
        BusinessService(scoped_documents, imports, _captured),
        record,
    )


def grant_reader(
    request: Request, actions: BusinessActions, context: ActionContext
) -> BusinessContext:
    """The saved receipts of the Business a route already resolved, read as
    that same grant. It adds no check of its own: the route's own rule decides
    who may call it."""

    from argus.api.documents import documents_service
    from argus.api.ingestion import ingestion_hub

    documents, hub = documents_service(), ingestion_hub()
    if documents is None or hub is None or documents.hub is not hub:
        raise unavailable_problem(request)
    return _granted(
        documents, hub, actions, context, "read", actions.record_context(context)
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
            # A supporting file is no receipt, whatever record holds it.
            if supporting_uploads(tx.rows, tx.context.actor.space_id, receipt_id):
                raise ConnectionNotFound()
            rows = tx.rows(
                "select draft from public.financial_document_extractions where connection_id=%s and user_id=%s",
                (receipt_id, tx.context.owner_id),
            )
            if rows and deletion(
                rows[0]["draft"]["status"], rows[0]["draft"].get("resolution", {})
            ):
                raise ActionError("invalid_input", "business_document_deleted")
            draft_id, ambiguous = draft_for_receipt(tx, UUID(receipt_id), None)
            if draft_id is not None or ambiguous:
                raise ActionError("invalid_input", "business_action_required")


def linked_drafts(tx, connection_ids: list[str]) -> dict[str, list[dict]]:  # noqa: ANN001
    """The bridge drafts each receipt is linked to, one query for all of them.
    A row's ``attention`` is its duplicate warning while nobody settled it."""

    if not connection_ids:
        return {}
    rows = tx.rows(
        "select distinct s.connection_id, e.id, e.state, e.version, e.updated_at, e.attention,"
        " e.possible_duplicates, e.activity_id, e.resolution,"
        " o.connection_id as duplicate_receipt_id,"
        + MARKER_COLUMNS
        + " from public.business_sources s"
        " join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id"
        " join public.financial_import_events e on e.id=l.draft_id and e.owner_space_id=l.space_id"
        " left join lateral ("
        "   select s2.connection_id from public.business_draft_sources l2"
        "   join public.business_sources s2 on s2.id=l2.source_id and s2.space_id=l2.space_id"
        "   where l2.space_id=e.owner_space_id and l2.draft_id=(e.possible_duplicates)[1]"
        f"   and s2.connection_id is not null and {own_source_sql('s2')} limit 1"
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
    markers = marker_people(tx, rows)
    arrivals = draft_arrivals(tx, list({row["id"] for row in rows}))
    for row in rows:
        row["arrival"] = arrivals.get(row["id"])
        if not duplicate_warning(
            row["attention"], row["possible_duplicates"], partial(_pending, tx, row)
        ):
            row["attention"] = None
        facts = BusinessResolution.model_validate(row["resolution"]["business"]).facts
        row["marks"] = record_marks(facts, row, markers)
        found.setdefault(str(row["connection_id"]), []).append(row)
    return found


def _pending(tx, row: dict) -> tuple[str, ...]:  # noqa: ANN001
    from argus.domain.business.actions.duplicate_resolution import attachment_signature
    from argus.domain.business.duplicates import pending_duplicates

    return pending_duplicates(
        tx.imports,
        tx.imports.event(str(row["id"])),
        lambda event_id: attachment_signature(tx, event_id),
    )


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
            "delete_available": False,
            "preparable": False,
            "enterable": False,
        }
        if "draft_id" in summary:
            out["draft_id"] = None
        return out
    if not drafts:
        return summary
    row = drafts[0]
    summary = {**summary, "deleted": deletion(row["state"], row["resolution"])}
    type_editable = row["state"] in ("open", "accepted")
    resolution = BusinessResolution.model_validate(row["resolution"]["business"])
    counterparty = resolution.facts.counterparty.value
    if "merchant" in summary:
        summary["merchant"] = counterparty
    arrival = row.get("arrival")
    if arrival and "received_at" in summary:
        summary["received_at"] = arrival.received_at
    if "title" in summary:
        summary["title"] = record_title(counterparty, arrival.filename if arrival else summary.get("filename"))
    if legacy == str(row["id"]):
        if "document_type_editable" in summary:
            summary["document_type_editable"] = type_editable
        return (
            {**summary, "due_on": resolution.due_on} if "due_on" in summary else summary
        )
    facts = resolution.facts

    def value(fact):  # noqa: ANN001, ANN202
        return fact.value if isinstance(fact, Known) else None

    funding = value(facts.funding)
    out = {
        **summary,
        **draft_row(
            SimpleNamespace(state=row["state"], resolution=row["resolution"]),
            duplicate=row["attention"] is not None,
        ),
        "preparable": False,
        "enterable": False,
        "expense_id": str(row["activity_id"]) if row["activity_id"] else None,
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
        "document_type_editable": type_editable,
        "delete_available": summary.get("delete_available", True)
        and row["state"] == "open",
    }
    for key, item in (
        ("draft_id", str(row["id"])),
        ("version", row["version"]),
        ("due_on", resolution.due_on),
    ):
        if key in summary:
            out[key] = item
    if out["attention"] == "duplicate":
        original = row.get("duplicate_receipt_id")
        out["duplicate_of"] = str(original) if original else None
    return out


def _named_deletions(context: BusinessContext, views: list[dict]) -> list[dict]:
    """Who deleted each document, named live, never by a label a marker stored."""

    markers = [
        DeletedDocument.model_validate(view["deleted"]) if view.get("deleted") else None
        for view in views
    ]
    if not any(markers):
        return views
    found = {}
    store = context.service.imports.store
    if isinstance(store, GrantImportStore):
        with transaction(store.authority, store.context) as tx:
            found = people(
                tx.connection,
                tx.authorization,
                [marker.actor.actor_id for marker in markers if marker],
            )
    return [
        {**view, "deleted": named_deletion(marker, found)} if marker else view
        for view, marker in zip(views, markers, strict=False)
    ]


def bridged(context: BusinessContext, summaries: list[dict]) -> list[dict]:
    """Every receipt view the API returns passes here: with the hosted bridge,
    a linked draft owns the receipt's state."""

    from argus.api.business_receipt_activity import project

    if not summaries:
        return summaries
    views = _named_deletions(context, project(context, summaries))
    can_delete = "approve" in (
        context.record_context.capabilities if context.record_context else ()
    )
    views = [
        {
            **view,
            "delete_available": can_delete
            and view.get("delete_available", True)
            and view["status"] not in ("confirmed", "dismissed")
            and not view.get("read_pending")
            and (view.get("bandeja_group") or {}).get("group") is not None,
            "restore_available": can_delete
            and view.get("deleted") is not None
            and view["deleted"].can_restore(),
        }
        for view in views
    ]
    if not isinstance(context.service.imports.store, GrantImportStore):
        return views
    # Anyone who may prepare marks or unmarks Personal; a read-only grant reads it.
    editable = "prepare" in (
        context.record_context.capabilities if context.record_context else ()
    )
    # The overlay names "personal" only for a receipt one draft owns: nothing else to mark.
    # An accepted draft also requires approval permission for correction.
    return [
        {
            **view,
            **({"personal_editable": editable} if "personal" in view else {}),
            **(
                {"document_type_editable": editable and (view["status"] != "confirmed" or can_delete)}
                if view.get("document_type_editable")
                else {}
            ),
        }
        for view in views
    ]


def _receipt_views(
    context: BusinessContext, receipts: list[Receipt], *, detail: bool = False
) -> list[dict]:
    from argus.api.email_intake import email_receipt_flags

    if not receipts:
        return []
    uploads = [OriginUpload.model_validate(receipt.draft) for receipt in receipts]
    store = context.service.imports.store
    if isinstance(store, GrantImportStore):
        with transaction(store.authority, store.context) as tx:
            intake = UploadIntake.stored(tx)
            origins = record_origins(tx, uploads, intake)
    else:
        intake = UploadIntake(
            frozenset(r.id for r in receipts if r.captured),
            email_receipt_flags(str(context.scope.owner.space_id)),
        )
        origins = record_origins(None, uploads, intake)
    views = []
    for receipt in receipts:
        if receipt.id in intake.emails:
            delivery_ids, original, _ = intake.emails[receipt.id]
            receipt = replace(receipt, email_delivery_ids=delivery_ids, email_original=original)
        origin = origins[receipt.id]
        views.append(receipt.detail(origin) if detail else receipt.summary(origin))
    return bridged(context, views)


def receipt_summaries(context: BusinessContext, view: str) -> list[dict]:
    """The receipt list, overlaid; the inbox leaves out what is saved or dismissed."""

    from argus.domain.business.receipts import CLOSED

    receipts = context.service.receipts(context.scope)
    items = _receipt_views(context, receipts)
    if view == "inbox":
        items = [item for item in items if item["status"] not in CLOSED]
    return sorted(items, key=lambda row: row["received_at"], reverse=True)


def receipt_read_dates(context: BusinessContext) -> dict[str, str]:
    """Each receipt's own read date by id, for the month close of a receipt
    whose proposal has none (an ambiguous purchase)."""

    from argus.domain.business.receipts import read_date

    return {
        receipt.id: day
        for receipt in context.service.receipts(context.scope)
        if (day := read_date(receipt.review))
    }


def overview_with_drafts(context: BusinessContext, start, end) -> dict:  # noqa: ANN001
    """The home overview with its receipt counts from the Bandeja's own
    projection over the overlaid views: an approved draft is a saved expense
    and the email itself is not a receipt, the same as in the Bandeja."""

    from argus.api.business_receipt_activity import receipts_now
    from argus.domain.business import ledger

    data = context.service.overview(context.scope, start, end)
    views, counts = receipts_now(context)
    data["last_received_at"] = max((view["received_at"] for view in views), default=None)
    data["ready_to_review_count"] = counts["ready_to_review_count"]
    data["bandeja_listo_count"] = counts["bandeja_listo_count"]
    data["bandeja_attention_count"] = counts["bandeja_attention_count"]
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

    return _receipt_views(context, [receipt])[0]


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
        f" and s.space_id=l.space_id and s.connection_id is not null and {OWN_SOURCE_SQL}"
        + MARKER_JOIN
        + " where e.owner_space_id=%s and e.user_id=%s and e.activity_id = any(%s)"
        " and e.resolution ? 'business'"
        # The latest revised draft speaks for its activity, whatever order the rows come in.
        " order by e.updated_at desc, e.id desc, s.received_at, s.id",
        (
            tx.context.actor.space_id,
            tx.context.owner_id,
            [UUID(activity_id) for activity_id in activity_ids],
        ),
    )
    drafts: dict[str, set[str]] = {}
    receipts: dict[str, set[str]] = {}
    marks: dict[str, dict] = {}
    arrivals = draft_arrivals(tx, list({row["draft_id"] for row in rows}))
    markers = marker_people(tx, rows)
    for row in rows:
        activity = str(row["activity_id"])
        drafts.setdefault(activity, set()).add(str(row["draft_id"]))
        if row["connection_id"]:
            receipts.setdefault(activity, set()).add(str(row["connection_id"]))
        typed = (row.get("resolution") or {}).get("business")
        if typed and activity not in marks:
            facts = BusinessResolution.model_validate(typed).facts
            arrival = arrivals.get(row["draft_id"])
            marks[activity] = {
                **record_marks(facts, row, markers),
                "merchant": record_title(facts.counterparty.value, arrival.filename if arrival else None),
            }
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
                if key == "merchant" or (item.get(key) is None and value is not None)
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


def answers_606(
    context: BusinessContext, activity_ids: list[str]
) -> dict[str, dict | None]:
    """The 606 answers each approved record's Registros row shows, by activity
    id, from the same ``purchase_606`` (null for a record the 606 never lists).
    An id with no Registros row, or a Business without the Postgres record
    store, has none."""

    from argus.domain.business.reporting_store import read_606

    store = context.service.imports.store
    if not isinstance(store, GrantImportStore) or not activity_ids:
        return {}
    return {
        identifier: answer.model_dump(mode="json") if answer else None
        for identifier, answer in read_606(
            store.authority, store.context, activity_ids
        ).items()
    }


def expense_detail(context: BusinessContext, expense_id: str) -> dict:
    """One saved expense with the records behind it: a receipt to open, the
    draft that recorded it, or neither for an expense entered by hand, and the
    606 answers its Registros row shows."""

    from argus.domain.business.contracts.dossier import DetailReadiness
    from argus.domain.business.reporting_store import read_record_detail

    [item] = _with_records(context, [context.service.expense(context.scope, expense_id)])
    store = context.service.imports.store
    row = None
    if isinstance(store, GrantImportStore):
        with transaction(store.authority, store.context) as tx:
            row = read_record_detail(tx, expense_id)
    return {
        **item,
        "dgii_606": row.dgii_606.model_dump(mode="json") if row and row.dgii_606 else None,
        **DetailReadiness.from_codes(row.missing if row else ()).model_dump(mode="json"),
    }


def search_with_drafts(
    context: BusinessContext,
    query: SearchQuery,
    numbers: dict[str, tuple[str, ...]] | None = None,
) -> dict:
    """Every match, unpaged: receipts overlaid and email-flagged as the Bandeja
    lists them, expenses and ventas linked to their receipts, accounts as found."""


    receipts = context.service.receipts(context.scope)
    views = {
        item["id"]: item for item in _receipt_views(context, receipts)
    }
    return context.service.search(
        context.scope, query, views, numbers, with_records=partial(_with_records, context)
    )


def updates_with_drafts(context: BusinessContext) -> list[dict]:
    """The updates feed built from the overlaid receipt views, so a linked draft's
    state (ready, needs attention, saved) is the one the feed reports."""


    receipts = context.service.receipts(context.scope)
    views = {
        item["id"]: item for item in _receipt_views(context, receipts)
    }
    return context.service.updates(context.scope, views)


def receipt_detail(context: BusinessContext, receipt) -> dict:
    [detail] = _receipt_views(context, [receipt], detail=True)
    store = context.service.imports.store
    if isinstance(store, GrantImportStore):
        with transaction(store.authority, store.context) as tx:
            detail["record_context"] = record_context(tx).model_dump(mode="json")
        return detail
    if context.record_context is not None:
        detail["record_context"] = context.record_context.model_dump(mode="json")
    return detail


def with_review_note(
    dossier: BusinessDossier, *, space_id: str, service: BusinessActions
) -> BusinessDossier:
    """The first saved delivery note, including while email receiving is off."""
    from argus.domain.ingestion.email_intake.store import PostgresEmailStore

    deliveries = {
        delivery for source in dossier.sources if source.kind == "attachment"
        for delivery in source.email_delivery_ids
    }
    if deliveries:
        store = PostgresEmailStore(service.authority.pool)
        for delivery_id in sorted(deliveries):
            delivery = store.get(delivery_id, space_id)
            if delivery and delivery.review_note:
                return dossier.model_copy(update={"review_note": delivery.review_note})
    return dossier


def unread_backlog(context: BusinessContext) -> list[str]:
    from argus.api.email_intake import email_receipt_flags

    flags = email_receipt_flags(str(context.scope.owner.space_id))
    documents = context.service.documents
    receipts = context.service.receipts(context.scope)
    ids = []
    for receipt in receipts:
        if (
            (receipt.id in flags and flags[receipt.id][1])
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
