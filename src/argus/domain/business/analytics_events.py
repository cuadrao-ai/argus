"""The Business pilot's analytics events, registered in ``ANALYTICS_EVENT_MODELS``.

Each property is a literal from the owner that already lists its values, a
bounded integer, a tuple of such literals, or the hashed Business id. No text,
amount, fiscal number, name or file name from a document can be represented.
``cost_micro_usd`` is Cuadrao's own provider cost for one read, never an amount
a customer entered.
"""

from __future__ import annotations

import hashlib
from typing import Annotated, ClassVar, Literal

from pydantic import Field, StringConstraints

from argus.domain.business.bandeja_group import BandejaReason
from argus.domain.business.contracts.facts import FactField
from argus.domain.business.document_type import DocumentType
from argus.domain.business.receipts import Attention
from argus.llm.openrouter_tasks import OpenRouterModelTier
from argus.observability.analytics_event_base import AnalyticsEvent

BUSINESS_HASH_PATTERN = r"^argus_business_[0-9a-f]{32}$"
BusinessHash = Annotated[
    str, StringConstraints(pattern=BUSINESS_HASH_PATTERN, max_length=47)
]


def business_hash_for_id(business_id: str) -> str:
    """The same one-way hash as ``actor_hash_for_user``, under its own prefix."""

    digest = hashlib.sha256(
        f"argus:business:{business_id.strip()}".encode("utf-8")
    ).hexdigest()
    return f"argus_business_{digest[:32]}"


ReceivedChannel = Literal["upload", "note", "email", "whatsapp"]
#: The extensions ``SOURCE_MEDIA_TYPES`` names; a typed note has no file.
FileType = Literal["pdf", "jpg", "png", "txt", "csv", "xlsx", "xml", "eml"]
SizeBucket = Literal["under_100kb", "100kb_to_1mb", "1mb_to_5mb", "5mb_or_more"]
ReadResult = Literal["read", "failed", "unsure"]
#: A recorded field a person can correct: every ``BusinessFacts`` field and
#: every ``FiscalFacts`` field.
FiscalField = Literal["rnc", "ncf", "ecf", "itbis", "include_606"]
RecordField = Literal[FactField, FiscalField]
Direction = Literal["compra", "venta"]
ExportFormat = Literal["excel", "csv"]
ExportScope = Literal["lo_que_ves", "dgii"]

MAX_PAGES = 1_000
MAX_LATENCY_MS = 3_600_000
MAX_TOKENS = 10_000_000
# One read costing a hundred dollars would be a defect, not a price.
MAX_COST_MICRO_USD = 100_000_000
MAX_SECONDS_TO_APPROVE = 3_650 * 86_400
MAX_EXPORT_ROWS = 1_000_000

Pages = Annotated[int, Field(ge=1, le=MAX_PAGES)]
Tokens = Annotated[int, Field(ge=0, le=MAX_TOKENS)]


class BusinessEvent(AnalyticsEvent):
    business_hash: BusinessHash


class BusinessDocumentReceived(BusinessEvent):
    event_name: ClassVar[str] = "business_document_received"

    channel: ReceivedChannel
    file_type: FileType | None = None
    page_count: Pages | None = None
    size_bucket: SizeBucket | None = None


class BusinessDocumentRead(BusinessEvent):
    event_name: ClassVar[str] = "business_document_read"

    result: ReadResult
    failure_reason: Attention | None = None
    latency_ms: Annotated[int, Field(ge=0, le=MAX_LATENCY_MS)]
    model_tier: OpenRouterModelTier | None = None
    input_tokens: Tokens | None = None
    output_tokens: Tokens | None = None
    cost_micro_usd: Annotated[int, Field(ge=0, le=MAX_COST_MICRO_USD)] | None = None


class BusinessDocumentNeedsReview(BusinessEvent):
    event_name: ClassVar[str] = "business_document_needs_review"

    reason_codes: Annotated[tuple[BandejaReason, ...], Field(min_length=1, max_length=40)]


class BusinessRecordApproved(BusinessEvent):
    event_name: ClassVar[str] = "business_record_approved"

    changed_fields: Annotated[tuple[RecordField, ...], Field(max_length=14)] | None = None
    changed_count: Annotated[int, Field(ge=0, le=14)] | None = None
    seconds_to_approve: Annotated[int, Field(ge=0, le=MAX_SECONDS_TO_APPROVE)] | None = (
        None
    )


class BusinessRecordRecorded(BusinessEvent):
    event_name: ClassVar[str] = "business_record_recorded"

    direction: Direction
    document_type: DocumentType


class BusinessRecordsExported(BusinessEvent):
    event_name: ClassVar[str] = "business_records_exported"

    format: ExportFormat
    scope: ExportScope
    row_count: Annotated[int, Field(ge=0, le=MAX_EXPORT_ROWS)]


BUSINESS_EVENT_MODELS: tuple[type[BusinessEvent], ...] = (
    BusinessDocumentReceived,
    BusinessDocumentRead,
    BusinessDocumentNeedsReview,
    BusinessRecordApproved,
    BusinessRecordRecorded,
    BusinessRecordsExported,
)
