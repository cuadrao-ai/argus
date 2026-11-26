"""A local stand-in for the vision provider: one synthetic receipt read.

It projects through ``batch_from_result`` exactly as the real extractor does, so
everything after the provider call is the production path. No network.
"""

from __future__ import annotations

import calendar
import hashlib
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any

from argus.domain.clock import new_york_now
from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import (
    DocumentExtractionError,
    ExtractionBatch,
    ExtractionResult,
)
from argus.domain.ingestion.documents.preparation import PreparedDocument
from argus.domain.ingestion.email_intake.budget import business_day
from argus.llm.local_reader_fixtures import hardware_receipt, purchase


def receipt_date(at: datetime | None = None) -> str:
    """Use the upload clock's Business day, within the accepted date range."""
    return business_day(at if at is not None else new_york_now()).isoformat()


def receipt_day(at: datetime | None = None) -> date:
    return date.fromisoformat(receipt_date(at))


def receipt_month(at: datetime | None = None) -> tuple[date, date]:
    """The first and last day of the calendar month holding the receipt day."""
    day = receipt_day(at)
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1), day.replace(day=last)


def receipt_purchase(at: datetime | None = None) -> dict[str, Any]:
    return purchase(receipt_details(at))


def receipt_details(at: datetime | None = None) -> dict[str, Any]:
    return hardware_receipt(receipt_date(at))


class ReceiptStub:
    """``rows`` replaces the one purchase; ``failure`` makes the next read raise
    that extraction code, the way the real extractor fails; ``complete`` is
    what the read says of itself."""

    def __init__(
        self,
        purchase: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        now = new_york_now()
        self.rows: list[dict[str, Any]] = [purchase or receipt_purchase(now)]
        self.details = details or receipt_details(now)
        self.readable = True
        self.complete = True
        self.failure: str | None = None
        self.calls: list[str] = []

    def prepare(
        self, content: bytes, media_type: str, *, rebuilt_image: bytes | None = None
    ) -> PreparedDocument:
        from argus.domain.ingestion.documents.preparation import prepare_document

        return prepare_document(content, media_type, rebuilt_image=rebuilt_image)

    async def extract(
        self,
        *,
        content: bytes,
        filename: str,
        media_type: str,
        connection_id: str,
        observed_at: datetime,
        prepared: PreparedDocument | None = None,
        before_request: Callable[[], Awaitable[None]] | None = None,
    ) -> ExtractionBatch:
        if before_request is not None:
            await before_request()
        self.calls.append(connection_id)
        if self.failure is not None:
            code, self.failure = self.failure, None
            raise DocumentExtractionError(code)
        digest = hashlib.sha256(content).hexdigest()
        result = ExtractionResult.model_validate(
            {
                "complete": self.complete,
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
