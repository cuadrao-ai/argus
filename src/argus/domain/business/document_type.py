"""The Bandeja type of a captured document.

A receipt is a purchase. A Venta is an invoice the business has already issued.
The type is chosen when the file is saved. The reader is unchanged: the type
gives the printed RNC, NCF, and ITBIS their meaning afterwards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from argus.domain.business.contracts.facts import BusinessFacts

DocumentType = Literal["recibo", "venta"]


def parse_document_type(value: str | None) -> DocumentType:
    if value is None:
        return "recibo"
    if value in ("recibo", "venta"):
        return value
    raise ValueError("document_type_invalid")


def require_venta_kind(document_type: str | None, facts: BusinessFacts) -> None:
    """A Venta stays an income document. The capture type owns that kind."""

    from argus.domain.business.contracts.facts import Known

    if document_type != "venta":
        return
    kind = facts.kind
    if not isinstance(kind, Known) or kind.value != "income":
        from argus.domain.business.authority import ActionError

        raise ActionError("invalid_input", "activity_kind_unsupported")
