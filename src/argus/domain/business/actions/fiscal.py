from __future__ import annotations

from uuid import UUID

from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.dgii import FiscalReview, PurchaseDeclaration
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    BusinessResolution,
    FiscalFacts,
    Known,
    Unknown,
)
from argus.domain.business.fiscal_identity import document_identity


def reviewed_fiscal_facts(
    facts: BusinessFacts, review: FiscalReview, source_ids: tuple[UUID, ...], origin: str
) -> BusinessFacts:
    values = facts.fiscal.model_dump() if facts.fiscal else FiscalFacts().model_dump()
    for name, value in review.fiscal.model_dump().items():
        name = "ecf" if name == "ncf" and value and value.startswith("E") else name
        values[name] = (
            Known(
                value=value, origin=origin, verified=False, source_ids=source_ids
            ).model_dump()
            if value is not None
            else Unknown(origin=origin, source_ids=source_ids).model_dump()
        )
    if review.fiscal.ncf:
        values["ncf" if review.fiscal.ncf.startswith("E") else "ecf"] = Unknown(
            origin=origin, source_ids=source_ids
        ).model_dump()
    return facts.model_copy(update={"fiscal": FiscalFacts.model_validate(values)})


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
