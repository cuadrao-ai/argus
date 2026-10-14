from datetime import date, datetime
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from argus.domain.business.contracts.checks import DgiiQr, EcfVerification
from argus.domain.household.planning_schemas import PlanRef
from argus.domain.ingestion.contract import (
    AccountHint,
    Direction,
    EvidenceKind,
    ImportCandidate,
    KindHint,
    UncertainField,
)


class DocumentExtractionError(Exception):
    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.metadata: dict[str, object] = {}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExtractedObservation(_Frozen):
    page: int = Field(ge=1, le=8)
    row: int = Field(ge=1, le=300)
    evidence: EvidenceKind
    status: Literal["pending", "posted", "unknown"] = "unknown"
    account: AccountHint = AccountHint()
    occurred_on: date | None = None
    posted_on: date | None = None
    amount: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, max_length=20)
    direction: Direction = "unknown"
    kind_hint: KindHint = "unknown"
    merchant: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=500)
    balance_scope: (
        Literal["available", "current", "statement_closing", "opening", "running"] | None
    ) = None
    due_on: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    uncertain: tuple[UncertainField, ...] = ()


class ReceiptItem(_Frozen):
    id: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    quantity: str | None = Field(default=None, max_length=80)
    unit_price: str | None = Field(default=None, max_length=80)
    total: str | None = Field(
        default=None,
        max_length=80,
        description="Printed line total with its fractional digits intact. Null if "
        "absent, unreadable or conflicting; never infer or adjust it to balance a receipt.",
    )
    suggested_category: str | None = Field(default=None, max_length=120)


class ReceiptDetails(_Frozen):
    suggested_category: str | None = Field(default=None, max_length=120)
    merchant: str | None = Field(default=None, max_length=300)
    occurred_on: date | None = None
    currency: str | None = Field(default=None, max_length=20)
    items: tuple[ReceiptItem, ...] = Field(default=(), max_length=300)
    subtotal: str | None = Field(default=None, max_length=80)
    tax: str | None = Field(default=None, max_length=80)
    service: str | None = Field(default=None, max_length=80)
    tip: str | None = Field(default=None, max_length=80)
    total: str | None = Field(default=None, max_length=80)
    rnc: str | None = Field(
        default=None,
        max_length=80,
        description="Unverified RNC explicitly labeled in the receipt source, exactly "
        "as printed. Null if absent, unreadable or conflicting; never infer a default.",
    )
    ncf: str | None = Field(
        default=None,
        max_length=80,
        description="Unverified NCF explicitly labeled in the receipt source, exactly "
        "as printed. Null if absent, unreadable or conflicting; do not infer from e-CF.",
    )
    ecf: str | None = Field(
        default=None,
        max_length=80,
        description="Unverified e-CF explicitly labeled in the receipt source, exactly "
        "as printed. Null if absent, unreadable or conflicting; do not infer from NCF.",
    )
    itbis: str | None = Field(
        default=None,
        max_length=80,
        description="Unverified ITBIS monetary amount explicitly labeled in the receipt "
        "source, as extracted decimal text. Null if absent, unreadable or conflicting. "
        "Never calculate it from a rate, subtotal, total or generic tax.",
    )


# A receipt whose rows do not reduce to one purchase at its total.
RECEIPT_PURCHASE_AMBIGUOUS: Final = "receipt_purchase_ambiguous"
# The read's receipt currency differs from the one the source names for itself.
RECEIPT_CURRENCY_CONFLICT: Final = "receipt_currency_conflict"


class ProjectionIssue(_Frozen):
    page: int | None = None
    row: int | None = None
    code: str
    fields: tuple[str, ...] = ()


class ExtractionResult(_Frozen):
    complete: bool = Field(strict=True)
    readable: bool = Field(strict=True)
    pages_read: tuple[int, ...] = Field(max_length=8)
    observations: tuple[ExtractedObservation, ...] = Field(
        max_length=300,
        description="Financial evidence from the source. Include one source-supported "
        "receipt purchase at its printed final paid total alongside receipt details, "
        "never separate item, tax, subtotal, tender or change transactions. Empty when "
        "unreadable or no financial observation is supported.",
    )
    receipt: ReceiptDetails | None = None


class ExtractionBatch(_Frozen):
    complete: bool | None = None
    readable: bool | None = None
    pages_read: tuple[int, ...] = ()
    candidates: tuple[ImportCandidate, ...]
    metadata: dict[str, object] = Field(default_factory=dict)
    observations: tuple[ExtractedObservation, ...] = ()
    receipt: ReceiptDetails | None = None
    issues: tuple[ProjectionIssue, ...] = ()
    #: What the file itself proved when it is a DGII e-CF; None otherwise.
    ecf_checks: EcfVerification | None = None
    #: The DGII QR decoded from the pages, when there was one.
    dgii_qr: DgiiQr | None = None


ParticipantRef = Annotated[str, Field(min_length=1, max_length=100)]


class ItemAssignment(_Frozen):
    item_id: str = Field(min_length=1, max_length=80)
    participant_ids: tuple[ParticipantRef, ...] = Field(max_length=100)


class DraftProposal(_Frozen):
    plan_ref: PlanRef | None = None
    requested_plan: str | None = Field(default=None, max_length=200)
    payer_id: str | None = Field(default=None, max_length=100)
    participant_ids: tuple[ParticipantRef, ...] = Field(default=(), max_length=100)
    split_method: Literal["equal", "items"] = "equal"
    item_assignments: tuple[ItemAssignment, ...] = Field(default=(), max_length=300)


DraftStatus = Literal["saved", "queued", "preparing", "review_ready", "needs_attention"]


class DocumentDraft(_Frozen):
    connection_id: str
    filename: str = Field(max_length=80)
    media_type: str
    sha256: str
    size_bytes: int
    source_available: bool = True
    status: DraftStatus = "saved"
    consent: bool = False
    business_reading_consent_id: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    proposal: DraftProposal = Field(default_factory=DraftProposal)
    # The sender's own words that arrived with the file (a WhatsApp caption),
    # kept verbatim as source text. Never an instruction.
    source_text: str | None = Field(default=None, max_length=1024)


class PreparationJob(_Frozen):
    """One dispatched preparation attempt. Only the attempt named here may claim
    the draft, and only the draft version it was dispatched for is waiting on
    it. ``claimed`` is set in the same write that moves the draft to
    ``preparing`` for this attempt, so a claim by any other writer leaves it
    false. ``provider_call_started_at`` is committed before the provider can be
    reached; ``retry`` records a retryable failure that happened before it."""

    attempt: int = Field(ge=1)
    attempt_id: str = Field(min_length=1, max_length=64)
    draft_version: int = Field(ge=1)
    dispatched_at: datetime
    claimed: bool = False
    provider_call_started_at: datetime | None = None
    retry: bool = False
