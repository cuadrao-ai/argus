"""The Bandeja type of a captured document.

A receipt is a purchase. A Venta is an invoice the business has already issued.
A person may name the type when the file is saved. Otherwise the read sets it:
a document the business itself issued is a Venta. The type stays editable while
the draft is open. The reader is unchanged: the type gives the printed RNC, NCF,
and ITBIS their meaning afterwards.

The type is the one answer to purchase or sale. The kind is never a second
answer: a known kind is always one the type admits. Every reader that places
a record on the 606 or the 607, or under Compras or Ventas, asks ``direction``;
none decides from the kind or from a saved declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from loguru import logger

from argus.domain.business.fiscal_identity import normalized_taxpayer_id

if TYPE_CHECKING:
    from uuid import UUID

    from argus.domain.business.contracts.facts import (
        ActivityKind,
        BusinessFacts,
        FactOrigin,
    )

DocumentType = Literal["recibo", "venta"]
#: The kinds each type admits, the type's own kind first. A receipt is a
#: purchase: an expense, or a refund of one. A Venta is income.
TYPE_KINDS: dict[DocumentType, tuple[ActivityKind, ...]] = {
    "recibo": ("expense", "refund"),
    "venta": ("income",),
}
#: The type a stated kind names. Any other kind is neither a purchase nor a sale.
TYPE_OF_KIND: dict[str, DocumentType] = {
    kind: document_type for document_type, kinds in TYPE_KINDS.items() for kind in kinds
}


@dataclass(frozen=True)
class Direction:
    """What a type is for the Business: the Registros family and the DGII form."""

    family: Literal["purchase", "sale"]
    form: Literal["606", "607"]


PURCHASE = Direction("purchase", "606")
SALE = Direction("sale", "607")


def direction(document_type: DocumentType | None) -> Direction | None:
    """The one answer to purchase or sale. A receipt is a purchase on the 606;
    a Venta is a sale on the 607. Money with no document is on neither form."""

    if document_type is None:
        return None
    return SALE if document_type == "venta" else PURCHASE


def money_document_type(kind: str) -> DocumentType | None:
    """The type a recorded money row with no draft stands under: the one
    whose kinds include it. None for a transfer or any other movement."""

    return TYPE_OF_KIND.get(kind)


def resolved_document_type(
    named: DocumentType | None, issuer_tax_id: str | None, business_tax_id: str | None
) -> tuple[DocumentType, bool]:
    """The type a new draft takes, and whether the read chose it. A named type
    wins. With no Business number nothing tells a sale from a purchase: a
    receipt marked as the read's choice, so the person sees it and may switch
    it. Otherwise the issuer decides: the Business's own number is a Venta,
    any other a receipt. With no issuer to compare, a receipt by default,
    never marked as the read's choice. A number set later types no existing
    draft again."""

    if named is not None:
        return named, False
    own = normalized_taxpayer_id(business_tax_id)
    if own is None:
        return "recibo", True
    issuer = normalized_taxpayer_id(issuer_tax_id)
    if issuer is None:
        return "recibo", False
    return ("venta" if issuer == own else "recibo"), True


def kind_disagrees(document_type: DocumentType, facts: BusinessFacts) -> bool:
    from argus.domain.business.contracts.facts import Known

    kind = facts.kind
    return isinstance(kind, Known) and kind.value not in TYPE_KINDS[document_type]


def kind_follows_type(
    facts: BusinessFacts,
    document_type: DocumentType,
    source_ids: tuple[UUID, ...],
    origin: FactOrigin,
) -> BusinessFacts:
    """The facts with a kind the type admits: the type's own kind in place of
    one it does not. An unknown kind stays unknown: nobody has said yet
    whether the document is a purchase or a sale."""

    if not kind_disagrees(document_type, facts):
        return facts
    expected = TYPE_KINDS[document_type][0]
    logger.info(
        "business_kind_follows_type type={} was={} now={}",
        document_type,
        facts.kind.value,
        expected,
    )
    return _with_kind(facts, expected, source_ids, origin)


def _with_kind(
    facts: BusinessFacts,
    kind: ActivityKind,
    source_ids: tuple[UUID, ...],
    origin: FactOrigin,
) -> BusinessFacts:
    from argus.domain.business.contracts.facts import BusinessFacts

    data = facts.model_dump(mode="json")
    data["kind"] = {
        "state": "known",
        "value": kind,
        "origin": origin,
        "verified": False,
        "source_ids": [str(value) for value in source_ids],
    }
    return BusinessFacts.model_validate(data)


def parse_document_type(value: str | None) -> DocumentType | None:
    """None when the upload names no type: the read decides it."""

    if value is None:
        return None
    if value in ("recibo", "venta"):
        return value
    raise ValueError("document_type_invalid")


def typed_facts(
    facts: BusinessFacts,
    document_type: DocumentType,
    source_ids: tuple[UUID, ...],
    origin: FactOrigin,
    business_tax_id: str | None,
) -> BusinessFacts:
    """The facts with the meaning a type someone set gives them: the type's own
    kind, or the kind as it was when the type admits it. A Venta's RNC is the
    client's: the Business's own number on it is the issuer, so that RNC is not
    known."""

    from argus.domain.business.contracts.facts import BusinessFacts, Known

    if not isinstance(facts.kind, Known) or kind_disagrees(document_type, facts):
        facts = _with_kind(facts, TYPE_KINDS[document_type][0], source_ids, origin)
    data = facts.model_dump(mode="json")
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


def require_type_kind(document_type: DocumentType, facts: BusinessFacts) -> None:
    """A known kind is one the type admits, and a Venta's kind is known."""

    if kind_disagrees(document_type, facts):
        from argus.domain.business.authority import ActionError

        raise ActionError("invalid_input", "activity_kind_unsupported")
    require_venta_kind(document_type, facts)
