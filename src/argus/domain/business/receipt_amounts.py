from __future__ import annotations

from uuid import UUID

from pydantic import TypeAdapter

from argus.domain.business.contracts.facts import Amount, Known, Unknown
from argus.domain.ingestion.contract import plain_decimal
from argus.domain.ingestion.documents.models import ReceiptDetails

_FACT_AMOUNT = TypeAdapter(Amount)


def read_amount(text: str | None) -> str | None:
    """The one parse of a model's amount text into the facts' amount, or None.

    The model's output is external data. A leading zero is dropped. A negative,
    a thousands separator, or text the facts cannot hold is unknown. Zero is an
    amount here; a caller that books a purchase also requires it positive.
    """

    if text is None:
        return None
    try:
        return _FACT_AMOUNT.validate_python(plain_decimal(text))
    except ValueError:
        return None


def read_amount_facts(
    receipt: ReceiptDetails | None, source_id: UUID
) -> dict[str, Known[str] | Unknown]:
    raw = {
        "net_amount": receipt.subtotal if receipt else None,
        "legal_tip": (receipt.service if receipt.service is not None else receipt.tip) if receipt else None,
    }
    facts = {}
    for name, value in raw.items():
        amount = read_amount(value)
        facts[name] = (
            Unknown(origin="extracted", source_ids=(source_id,))
            if amount is None
            else Known(value=amount, origin="extracted", source_ids=(source_id,))
        )
    return facts
