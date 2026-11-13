from __future__ import annotations

import re
from decimal import Decimal
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from argus.domain.business.contracts.facts import Amount, Known, Unknown
from argus.domain.ingestion.documents.models import ReceiptDetails


def read_amount_facts(
    receipt: ReceiptDetails | None, source_id: UUID
) -> dict[str, Known[str] | Unknown]:
    raw = {
        "net_amount": receipt.subtotal if receipt else None,
        "legal_tip": (receipt.service if receipt.service is not None else receipt.tip) if receipt else None,
    }
    facts = {}
    for name, value in raw.items():
        clean = value.strip() if value is not None else None
        if clean is not None and re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?", clean):
            try:
                amount = TypeAdapter(Amount).validate_python(format(Decimal(clean.replace(",", "")), "f"))
            except ValidationError:
                facts[name] = Unknown(origin="extracted", source_ids=(source_id,))
            else:
                facts[name] = Known(value=amount, origin="extracted", source_ids=(source_id,))
        else:
            facts[name] = Unknown(origin="extracted", source_ids=(source_id,))
    return facts
