from datetime import date, datetime
from typing import Annotated, Final, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator

from argus.domain.business.contracts.checks import DgiiQr, EcfVerification
from argus.domain.business.document_type import DocumentType
from argus.domain.household.planning_schemas import PlanRef
from argus.domain.ingestion.contract import (
    AccountHint,
    Direction,
    EvidenceKind,
    ImportCandidate,
    KindHint,
    UncertainField,
)
from argus.domain.ingestion.shortcuts.amounts import marker_currency


class DocumentExtractionError(Exception):
    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.metadata: dict[str, object] = {}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _read_currency(value: object) -> object:
    """The code a printed marker names, where the model's currency text enters."""

    if not isinstance(value, str):
        return value
    code = marker_currency(value)
    if code is None:
        return value
    logger.info("document_read_currency_marker raw={!r} mapped={}", value, code)
    return code


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

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, value: object) -> object:
        return _read_currency(value)

    @field_validator("account", mode="before")
    @classmethod
    def _account_currency(cls, value: object) -> object:
        if isinstance(value, dict) and "currency" in value:
            return {**value, "currency": _read_currency(value["currency"])}
        return value


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
    occurred_on: date | None = Field(
        default=None,
        description='Issue date of the receipt ("Fecha", "Emitido", "Fecha Emisión"). '
        "Never an expiry date or a signature or printing timestamp. Null if no issue "
        "date is printed.",
    )
    issue_date_printed: str | None = Field(
        default=None,
        max_length=60,
        description="The issue date exactly as printed on the receipt, character for "
        "character, before any interpretation. Null if no issue date is printed.",
    )
    currency: str | None = Field(default=None, max_length=20)
    items: tuple[ReceiptItem, ...] = Field(default=(), max_length=300)
    subtotal: str | None = Field(default=None, max_length=80)
    payment_status: Literal["paid", "pending", "unknown"] = "unknown"
    tax: str | None = Field(default=None, max_length=80)
    estimated_tax: str | None = Field(default=None, max_length=80)
    service: str | None = Field(default=None, max_length=80)
    tip: str | None = Field(default=None, max_length=80)
    total: str | None = Field(default=None, max_length=80)
    rnc: str | None = Field(
        default=None,
        max_length=80,
        description="Unverified RNC of the supplier, the business that issued the "
        "receipt, exactly as printed. Usually at the top with the business name. Never "
        "the RNC of the client or buyer. Null if absent or unreadable; never infer a "
        "default.",
    )
    buyer_rnc: str | None = Field(
        default=None,
        max_length=80,
        description="Unverified RNC of the buyer, exactly as printed, when its label "
        'names the client or buyer ("RNC Cliente", "RNC Comprador" or similar). Null '
        "if absent or unreadable.",
    )
    ncf: str | None = Field(
        default=None,
        max_length=80,
        description="Unverified NCF exactly as printed; it normally starts with B. "
        "Null if absent or unreadable. An e-NCF goes in ecf, never here.",
    )
    ecf: str | None = Field(
        default=None,
        max_length=80,
        description="Unverified e-NCF, the electronic fiscal number, exactly as "
        "printed; it normally starts with E. Null if absent or unreadable. An NCF "
        "goes in ncf, never here.",
    )
    itbis: str | None = Field(
        default=None,
        max_length=80,
        description="Unverified ITBIS monetary amount printed next to an ITBIS or "
        'Impuesto label, as decimal text; "0.00" when the receipt prints zero. Null '
        "if absent or unreadable. Never calculate it from a rate, subtotal or total.",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, value: object) -> object:
        return _read_currency(value)


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
    complete: bool = Field(
        strict=True,
        description="For a statement, false if any row or page is cut off, omitted or "
        "unreadable. For a receipt, false only if a fiscal field (supplier RNC, NCF or "
        "e-NCF, issue date, printed ITBIS, total) is visibly cut off or unreadable; "
        "cut, covered or faded item lines do not make it false.",
    )
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


DraftStatus = Literal[
    "saved", "queued", "preparing", "review_ready", "needs_attention", "dismissed"
]


class DocumentDraft(_Frozen):
    resolution: dict[str, object] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )
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
    # The type the person named at upload. None lets the read decide.
    document_type: DocumentType | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    def read_pending(self, reading_allowed: bool) -> bool:
        return self.status == "preparing" or (
            self.status == "queued" and self.consent and reading_allowed
        )


class PreparationJob(_Frozen):
    """One dispatched preparation attempt. Only the attempt named here may claim
    the draft, and only the draft version it was dispatched for is waiting on
    it. ``dispatched_at`` is when a process took the attempt: the hand-off, or
    in pull mode the pull. Until then it is ``None`` and the attempt waits in
    the queue. ``claimed`` is set in the same write that moves the draft to
    ``preparing`` for this attempt, so a claim by any other writer leaves it
    false. ``provider_call_started_at`` is committed before the provider can be
    reached; ``retry`` records a retryable failure that happened before it.
    ``reruns`` counts the attempts of this preparation the sweep started
    because an earlier one died past its provider marker, each paid again.
    ``provider_calls`` counts the provider calls this read was admitted for,
    across every take; ``not_before`` is when a take waiting out a failure may
    be pulled; ``retry_waited`` is the seconds of such waits so far.
    ``asked_at`` is when this read was asked for, kept across every take: the
    upload for the read an upload starts, the person's ask for a later one.
    The read deadline counts from it."""

    attempt: int = Field(ge=1)
    attempt_id: str = Field(min_length=1, max_length=64)
    draft_version: int = Field(ge=1)
    dispatched_at: datetime | None = None
    claimed: bool = False
    provider_call_started_at: datetime | None = None
    retry: bool = False
    reruns: int = Field(default=0, ge=0, exclude_if=lambda value: value == 0)
    provider_calls: int = Field(default=0, ge=0, exclude_if=lambda value: value == 0)
    not_before: datetime | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    retry_waited: float = Field(default=0, ge=0, exclude_if=lambda value: value == 0)
    asked_at: datetime | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
