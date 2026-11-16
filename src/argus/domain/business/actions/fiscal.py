from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from argus.domain.business.accepted_dates import reader_date_reason
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.dgii import (
    DgiiDeclaration,
    FiscalReview,
    PurchaseDeclaration,
    printed_identifier,
)
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    BusinessResolution,
    FiscalFacts,
    Known,
    OwnerDoesNotKnow,
    Unknown,
)
from argus.domain.business.fiscal_identity import document_identity
from argus.domain.ingestion.reconcile.model import ImportEvent


def validate_changed_dates(before: DgiiDeclaration | None, after: DgiiDeclaration | None) -> None:
    """Full reviews resubmit saved dates; only changed values are fresh input."""
    if after is None:
        return
    field = "paid_on" if isinstance(after, PurchaseDeclaration) else "withheld_on"
    value = getattr(after, field)
    previous = getattr(before, field, None) if before is not None else None
    if value == previous:
        return
    reason = reader_date_reason(value)
    if reason is not None:
        raise ActionError("invalid_input", reason.code, context={
            "field": field, "min_date": reason.min_date, "today": reason.today,
        })


def _held(fact: Known | Unknown | OwnerDoesNotKnow) -> str | None:
    return fact.value if isinstance(fact, Known) else None


def _money(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def reviewed_fiscal_facts(
    facts: BusinessFacts, review: FiscalReview, source_ids: tuple[UUID, ...], origin: str
) -> BusinessFacts:
    """The fiscal facts after a person's review. A review always carries the
    RNC, the fiscal number and the ITBIS, so only a value that differs from the
    record is written. The others keep their origin, check and sources."""

    current = facts.fiscal or FiscalFacts()
    values = current.model_dump()

    def stated(name: str, value: str | None) -> None:
        values[name] = (
            Known(value=value, origin=origin, verified=False, source_ids=source_ids)
            if value is not None
            else Unknown(origin=origin, source_ids=source_ids)
        ).model_dump()

    typed = review.fiscal
    if printed_identifier(_held(current.rnc)) != typed.rnc:
        stated("rnc", typed.rnc)
    # Readers trim and upper-case a fiscal number but keep its separators, so a
    # stored separator is malformed and a typed clean number is a real change.
    number = _held(current.ecf) or _held(current.ncf)
    if (number and number.strip().upper()) != typed.ncf:
        electronic = typed.ncf is not None and typed.ncf.startswith("E")
        stated("ecf", typed.ncf if electronic else None)
        stated("ncf", None if electronic else typed.ncf)
    if _money(_held(current.itbis)) != _money(typed.itbis):
        stated("itbis", typed.itbis)
    return facts.model_copy(update={"fiscal": FiscalFacts.model_validate(values)})


#: The 606 answers a person gives one by one, each remembered per supplier RNC.
RememberedField = Literal["category", "payment_method"]


def last_choice(tx, draft_id, field: RememberedField) -> str | None:
    """The answer a person last gave for this draft's RNC in this Business.
    The only reader of that memory. Nothing stores it: it reaches the 606 only
    when a person writes it on the draft.

    A tipo de gasto nobody confirmed is no answer.
    """

    value = f"other.resolution->'business'->'dgii'->>'{field}'"
    confirmed = (
        " and other.resolution->'business'->'dgii'->>'category_suggested'"
        " is distinct from 'true'"
        if field == "category"
        else ""
    )
    rows = tx.rows(
        f"select {value} as value"
        " from public.financial_import_events me"
        " join public.financial_import_events other"
        " on other.owner_space_id=me.owner_space_id and other.business_rnc=me.business_rnc"
        " left join lateral ("
        "   select r.created_at as chosen_at from public.business_draft_revisions r"
        "   where r.space_id=other.owner_space_id and r.draft_id=other.id"
        f"   and (r.after_dgii->>'{field}') is distinct from (r.before_dgii->>'{field}')"
        "   order by r.version desc limit 1"
        " ) choice on true"
        " where me.id=%s and me.owner_space_id=%s and other.id<>me.id"
        " and other.state in ('open','accepting','accepted')"
        " and other.resolution->'business'->'dgii'->>'form'='606'"
        f" and {value} is not null{confirmed}"
        " order by choice.chosen_at desc nulls last,other.id limit 1",
        (draft_id, tx.context.actor.space_id),
    )
    return rows[0]["value"] if rows else None


# The database's copy of the rules below: one accepting or accepted sale per
# Business and comprobante, and one accepting or accepted purchase per
# Business, supplier RNC and comprobante. They refuse what two approvals read
# past.
SALE_NCF_INDEX = "financial_import_events_sale_ncf_idx"
PURCHASE_COMPROBANTE_INDEX = "financial_import_events_purchase_comprobante_idx"


def colliding_purchase_record(db, space_id, draft_id) -> str | None:
    """The accepting or accepted purchase that holds this draft's supplier RNC
    and comprobante, read from the generated columns the index is built on."""

    row = db.execute(
        "select other.id::text from public.financial_import_events me"
        " join public.financial_import_events other on other.owner_space_id=me.owner_space_id"
        " and other.business_rnc=me.business_rnc"
        " and other.business_fiscal_number=me.business_fiscal_number"
        " where me.id=%s and me.owner_space_id=%s and other.id<>me.id"
        " and other.state in ('accepting','accepted')"
        " and other.business_kind is distinct from 'income'"
        " order by other.created_at,other.id limit 1",
        (str(draft_id), str(space_id)),
    ).fetchone()
    return row[0] if row else None


def comprobante_identity(facts: Mapping[str, Any]) -> tuple[str, ...] | None:
    """The one comprobante these stored facts are, by the DGII rule: a sale by
    its number, a purchase by supplier RNC and number. None while a part is
    missing."""

    fiscal = facts.get("fiscal") or {}
    number = (fiscal.get("ecf") or {}).get("value") or (fiscal.get("ncf") or {}).get(
        "value"
    )
    identity = document_identity(
        (facts.get("kind") or {}).get("value"),
        (fiscal.get("rnc") or {}).get("value"),
        number,
    )
    if identity is None or identity[0] == "purchase" and identity[1] is None:
        return None
    return identity


def same_comprobante(
    tx, drafts: Mapping[str, Mapping[str, Any]], states: Sequence[str]
) -> dict[str, tuple[UUID, ...]]:
    """For each draft, by id, the other documents of this Business in
    ``states`` that are its comprobante, oldest first. ``drafts`` maps each id
    to its stored facts. Approval refuses a second recorded one, and readiness
    and the duplicate review hold back the same pairs: all read this."""

    wanted: dict[tuple[str, ...], list[str]] = {}
    for draft_id, facts in drafts.items():
        identity = comprobante_identity(facts)
        if identity is not None:
            wanted.setdefault(identity, []).append(draft_id)
    if not wanted:
        return {}
    rows = tx.rows(
        "select id,resolution->'business'->'facts' as facts"
        " from public.financial_import_events where owner_space_id=%s"
        " and state=any(%s) and resolution->'business'->'facts'->'fiscal' is not null"
        " order by created_at,id",
        (tx.context.actor.space_id, list(states)),
    )
    found: dict[str, tuple[UUID, ...]] = {}
    for row in rows:
        for draft_id in wanted.get(comprobante_identity(row["facts"]), ()):
            if draft_id != str(row["id"]):
                found[draft_id] = (*found.get(draft_id, ()), row["id"])
    return found


def repeated_purchases(
    tx, events: Iterable[ImportEvent]
) -> dict[UUID, tuple[UUID, ...]]:
    """For each purchase draft, the other purchases, open or recorded, that
    are its comprobante. Only one of them can be approved, so a stored
    different-purchases answer settles none of these pairs."""

    drafts = {
        event.id: event.resolution["business"]["facts"]
        for event in events
        if "business" in event.resolution
    }
    return {
        UUID(draft_id): others
        for draft_id, others in same_comprobante(
            tx, drafts, ("open", "accepting", "accepted")
        ).items()
        if comprobante_identity(drafts[draft_id])[0] == "purchase"
    }


def require_distinct_fiscal_document(tx, event, facts: BusinessFacts) -> None:
    stored = facts.model_dump(mode="json")
    identity = comprobante_identity(stored)
    matches = same_comprobante(tx, {event.id: stored}, ("accepting", "accepted"))
    if identity is None or event.id not in matches:
        return
    if identity[0] == "sale":
        raise ActionError("invalid_input", "fiscal_duplicate_document")
    raise ActionError(
        "invalid_input", "duplicate_comprobante", existing_record_id=matches[event.id][0]
    )


def refund_reference(event):
    declaration = BusinessResolution.model_validate(event.resolution["business"]).dgii
    if (
        not isinstance(declaration, PurchaseDeclaration)
        or not declaration.actual_refund
        or declaration.purchase_activity_id is None
    ):
        raise ActionError("invalid_input", "fiscal_credit_settlement_required")
    return str(declaration.purchase_activity_id)
