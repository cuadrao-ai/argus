"""A local stand-in for the vision provider: one fixed, realistic receipt read.

It projects through ``batch_from_result`` exactly as the real extractor does, so
everything after the provider call is the production path. No network.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import (
    DocumentExtractionError,
    ExtractionBatch,
    ExtractionResult,
)
from argus.domain.ingestion.documents.preparation import PreparedDocument

PURCHASE: dict[str, Any] = {
    "page": 1,
    "row": 1,
    "evidence": "transaction",
    "status": "posted",
    "amount": "3450.00",
    "currency": "DOP",
    "occurred_on": "2026-10-06",
    "direction": "outflow",
    "kind_hint": "expense",
    "merchant": "FERRETERIA LA ESQUINA SRL",
}
DETAILS: dict[str, Any] = {
    "payment_status": "paid",
    "merchant": "FERRETERIA LA ESQUINA SRL",
    "occurred_on": "2026-10-06",
    "currency": "DOP",
    "items": [
        {"id": "1", "description": "Pintura blanca 1 gal", "total": "1850.00"},
        {"id": "2", "description": "Brochas x3", "total": "1073.73"},
    ],
    "subtotal": "2923.73",
    "tax": "526.27",
    "total": "3450.00",
}


class ReceiptStub:
    """``rows`` replaces the one purchase; ``failure`` makes the next read raise
    that extraction code, the way the real extractor fails."""

    def __init__(
        self,
        purchase: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.rows: list[dict[str, Any]] = [purchase or PURCHASE]
        self.details = details or DETAILS
        self.readable = True
        self.failure: str | None = None
        self.calls: list[str] = []

    async def extract(
        self,
        *,
        content: bytes,
        filename: str,
        media_type: str,
        connection_id: str,
        observed_at: datetime,
        prepared: PreparedDocument | None = None,
    ) -> ExtractionBatch:
        self.calls.append(connection_id)
        if self.failure is not None:
            code, self.failure = self.failure, None
            raise DocumentExtractionError(code)
        digest = hashlib.sha256(content).hexdigest()
        result = ExtractionResult.model_validate(
            {
                "complete": True,
                "readable": self.readable,
                "pages_read": [1],
                "observations": self.rows,
                "receipt": self.details,
            }
        )
        # The real extractor hands the projection the currency the source
        # names for itself; the stub does the same so the guard is exercised.
        from argus.domain.ingestion.documents.preparation import prepare_document

        if prepared is None:
            prepared = prepare_document(content, media_type)
        batch = batch_from_result(
            result,
            digest,
            connection_id,
            observed_at,
            1,
            document_currency=prepared.document_currency,
            ecf=prepared.ecf,
            dgii_qr=prepared.dgii_qr,
        )
        attachment = Attachment(
            external_id=digest,
            sha256=digest,
            media_type=media_type,
            size_bytes=len(content),
            filename=filename,
        )
        return batch.model_copy(
            update={
                "candidates": tuple(
                    c.model_copy(update={"attachments": (attachment,)})
                    for c in batch.candidates
                ),
                "metadata": {
                    "pages": 1,
                    "media_type": media_type,
                    "sha256": digest,
                    "document_currency": prepared.document_currency,
                },
            }
        )
