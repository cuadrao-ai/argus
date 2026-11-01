from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.dgii import (
    ExpenseType,
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


def exported_line(tx, event) -> bool:
    """Whether a 606 or 607 TXT a person downloaded carries this record's line."""

    return bool(
        tx.rows(
            "select 1 from public.business_dgii_export_lines"
            " where space_id=%s and activity_id=%s limit 1",
            (tx.context.actor.space_id, event.activity_id),
        )
    )


def require_unexported(tx, event) -> None:
    """A declaration already handed to the DGII in a TXT does not change here."""

    if exported_line(tx, event):
        raise ActionError("invalid_input", "fiscal_declaration_exported")


def remembered_expense_type(tx, draft_id) -> ExpenseType | None:
    """The tipo de gasto a person last chose for this draft's RNC in this
    Business. The only reader of that memory. Nothing stores it: it reaches the
    606 only when a person writes it on the draft."""

    rows = tx.rows(
        "select other.resolution->'business'->'dgii'->>'category' as category"
        " from public.financial_import_events me"
        " join public.financial_import_events other"
        " on other.owner_space_id=me.owner_space_id and other.business_rnc=me.business_rnc"
        " join lateral ("
        "   select max(r.created_at) as chosen_at from public.business_draft_revisions r"
        "   where r.space_id=other.owner_space_id and r.draft_id=other.id"
        "   and (r.after_dgii->>'category') is distinct from (r.before_dgii->>'category')"
        " ) choice on true"
        " where me.id=%s and me.owner_space_id=%s and other.id<>me.id"
        " and other.state in ('open','accepting','accepted')"
        " and other.resolution->'business'->'dgii'->>'form'='606'"
        " and other.resolution->'business'->'dgii'->>'category' is not null"
        " and other.resolution->'business'->'dgii'->>'category_suggested' is distinct from 'true'"
        " order by choice.chosen_at desc nulls last,other.id limit 1",
        (draft_id, tx.context.actor.space_id),
    )
    return rows[0]["category"] if rows else None


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


def require_distinct_fiscal_document(tx, event, facts: BusinessFacts) -> None:
    fiscal = facts.fiscal
    ncf = (
        fiscal.ecf.value
        if fiscal and isinstance(fiscal.ecf, Known)
        else fiscal.ncf.value
        if fiscal and isinstance(fiscal.ncf, Known)
        else None
    )
    rnc = fiscal.rnc.value if fiscal and isinstance(fiscal.rnc, Known) else None
    if ncf is None:
        return
    identity = document_identity(facts.kind.value, rnc, ncf)
    # A purchase is the same comprobante only when the supplier RNC matches too.
    if identity is None or identity[0] == "purchase" and identity[1] is None:
        return
    matches = tx.rows(
        "select id,resolution->'business'->'facts' as facts from public.financial_import_events where owner_space_id=%s"
        " and user_id=%s and id<>%s and state in ('accepting','accepted')"
        " and resolution->'business'->'facts'->'fiscal' is not null order by created_at,id",
        (tx.context.actor.space_id, tx.context.owner_id, event.id),
    )
    for match in matches:
        other = match["facts"]
        other_fiscal = other.get("fiscal") or {}
        number = (other_fiscal.get("ecf") or {}).get("value") or (
            other_fiscal.get("ncf") or {}
        ).get("value")
        taxpayer = (other_fiscal.get("rnc") or {}).get("value")
        if (
            document_identity((other.get("kind") or {}).get("value"), taxpayer, number)
            == identity
        ):
            if identity[0] == "sale":
                raise ActionError("invalid_input", "fiscal_duplicate_document")
            raise ActionError(
                "invalid_input", "duplicate_comprobante", existing_record_id=match["id"]
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
