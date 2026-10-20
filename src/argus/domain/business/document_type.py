"""The Bandeja type of a captured document.

A receipt is a purchase. A Venta is an invoice the business has already issued.
A person may name the type when the file is saved. Otherwise the read sets it:
a document the business itself issued is a Venta. The type stays editable while
the draft is open. The reader is unchanged: the type gives the printed RNC, NCF,
and ITBIS their meaning afterwards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from argus.domain.business.fiscal_identity import normalized_taxpayer_id

if TYPE_CHECKING:
    from uuid import UUID

    from argus.domain.business.contracts.facts import BusinessFacts, FactOrigin

DocumentType = Literal["recibo", "venta"]


def parse_document_type(value: str | None) -> DocumentType | None:
    """None when the upload names no type: the read decides it."""

    if value is None:
        return None
    if value in ("recibo", "venta"):
        return value
    raise ValueError("document_type_invalid")


def detected_document_type(
    issuer_tax_id: str | None, business_tax_id: str | None
) -> DocumentType:
    issuer = normalized_taxpayer_id(issuer_tax_id)
    if issuer is not None and issuer == normalized_taxpayer_id(business_tax_id):
        return "venta"
    return "recibo"


def typed_facts(
    facts: BusinessFacts,
    document_type: DocumentType,
    source_ids: tuple[UUID, ...],
    origin: FactOrigin,
    business_tax_id: str | None,
) -> BusinessFacts:
    """The facts with the meaning the type gives them. A receipt is a purchase.
    A Venta is income, and its RNC is the client's: the Business's own number
    on it is the issuer, so that RNC is not known."""

    from argus.domain.business.contracts.facts import BusinessFacts

    data = facts.model_dump(mode="json")
    data["kind"] = {
        "state": "known",
        "value": "income" if document_type == "venta" else "expense",
        "origin": origin,
        "verified": False,
        "source_ids": [str(value) for value in source_ids],
    }
    rnc = (data.get("fiscal") or {}).get("rnc") or {}
    own = normalized_taxpayer_id(business_tax_id)
    if (
        document_type == "venta"
        and own is not None
        and normalized_taxpayer_id(rnc.get("value")) == own
    ):
        data["fiscal"]["rnc"] = {"state": "unknown", "origin": origin}
    return BusinessFacts.model_validate(data)


def require_venta_kind(document_type: str | None, facts: BusinessFacts) -> None:
    """A Venta stays an income document. The capture type owns that kind."""

    from argus.domain.business.contracts.facts import Known

    if document_type != "venta":
        return
    kind = facts.kind
    if not isinstance(kind, Known) or kind.value != "income":
        from argus.domain.business.authority import ActionError

        raise ActionError("invalid_input", "activity_kind_unsupported")
