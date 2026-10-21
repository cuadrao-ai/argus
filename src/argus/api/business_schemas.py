"""Wire shapes for ``/api/v1/business``, matching ``web/lib/business-api.ts``."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from argus.api.schemas import Language
from argus.domain.business.contracts.dossier import RecordContext
from argus.domain.business.country import CountryCode
from argus.domain.business.document_type import DocumentType
from argus.domain.business.receipts import Attention
from argus.domain.business.search import SearchKind
from argus.domain.business.spaces import MAX_NAME_LENGTH
from argus.domain.financial_search import query_text
from argus.domain.ingestion.receipt_review import ReceiptStatus

ExpenseAccountType = Literal["cash", "checking", "savings", "credit_card"]


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


SpaceName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH),
]


class BusinessSpaceInfo(_Wire):
    id: str
    name: str
    country: str
    currency: str


class BusinessNamingState(BusinessSpaceInfo):
    name_required: bool
    name_prompt_seen: bool


class BusinessNamePrompt(BusinessNamingState):
    show_prompt: bool


class BusinessNameTarget(_Wire):
    space_id: UUID


class SaveBusinessName(BusinessNameTarget):
    name: SpaceName


class GrantedSpaceInfo(_Wire):
    """One Business the caller may enter through one live grant of theirs."""

    space_id: str
    name: str
    grant_id: str
    role: Literal["owner", "accountant"]
    capabilities: list[Literal["read", "prepare", "approve"]]
    #: Whether the one-time "you now have access" line was dismissed; always true for the own Business.
    access_seen: bool


class BusinessSpaces(_Wire):
    spaces: list[GrantedSpaceInfo]


class StartBusinessSpace(_Wire):
    """No name starts the space with the default name in ``language``."""

    name: SpaceName | None = None
    language: Language | None = None
    country: CountryCode | None = None


class RenameBusinessSpace(_Wire):
    name: SpaceName


#: Names one wording of the Business consent screen; the web derives it from the copy.
ConsentVersion = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]


class AcceptBusinessConsent(_Wire):
    version: ConsentVersion


class BusinessConsent(_Wire):
    """The caller's acceptance of one wording; ``accepted_at`` is null until then."""

    version: ConsentVersion
    accepted_at: datetime | None


class BusinessAccount(_Wire):
    id: str
    nickname: str | None
    type: str
    currency: str


class ReceiptLimits(_Wire):
    max_bytes: int
    media_types: list[str]


class BusinessWorkspace(_Wire):
    country: str
    currency: str
    accounts: list[BusinessAccount]
    currencies: list[str]
    assistant_available: bool
    chat_available: bool
    receipt_limits: ReceiptLimits


class BusinessAccessGrant(_Wire):
    id: str
    email: str | None
    display_name: str
    capabilities: list[Literal["read", "prepare", "approve"]]
    created_at: datetime
    #: The owner's own grant; it cannot be revoked here.
    owner: bool


class BusinessAccessInvite(_Wire):
    id: str
    email: str
    created_at: datetime
    expires_at: datetime
    state: Literal["pending", "expired"]


class BusinessAccess(_Wire):
    grants: list[BusinessAccessGrant]
    invites: list[BusinessAccessInvite]
    invite_delivery: Literal["not_configured", "accepted", "failed"] | None = None


class GiveBusinessAccess(_Wire):
    email: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)
    ]


class CreateBusinessAccount(_Wire):
    nickname: str = Field(min_length=1, max_length=200)
    type: ExpenseAccountType
    currency: str = Field(min_length=3, max_length=3)


class ReceiptActivity(_Wire):
    state: Literal[
        "saved_unread", "reading", "ready", "read_failed", "blocked", "inactive"
    ]
    unread: bool
    completion_cursor: str | None


class BandejaMembership(_Wire):
    # Which Bandeja buckets this receipt sits in, from the same predicates the
    # counts sum: "por revisar", "con problema" and "leyendo". A closed receipt
    # and the email itself sit in none.
    por_revisar: bool
    con_problema: bool
    leyendo: bool


class ReceiptActivityCounts(_Wire):
    # Receipts being read, plus emails still being read with nothing saved yet.
    reading_count: int
    # New activity this person has not opened: the badge's dot, not its number.
    unread_count: int
    presentation: Literal["working", "unread", "none"]
    # Every row the Bandeja lists, opened or not: receipts not yet saved or
    # dismissed (never the email itself), notes no receipt carries and each
    # email that is a row of its own (being read, or brought no receipt).
    pending_review_count: int
    # Of those rows, how many need the person's attention; an email that
    # brought no receipt always does, an email being read does not.
    needs_attention_count: int
    # "Por revisar": the receipts a person can review now (not being read,
    # not unreadable) plus those notes. An email never counts here.
    ready_to_review_count: int
    # Transacciones "Por igualar": every movement and document still to
    # igualar, from any period. Null while bank matching is off.
    por_igualar_count: int | None
    # Receipts that left the Bandeja each way, whichever view is read: saved as
    # a record, or dismissed. The email itself never counts.
    confirmed_count: int = 0
    dismissed_count: int = 0


class ReceiptReadingBody(_Wire):
    enabled: bool = Field(strict=True)
    scope_version: int = Field(strict=True, ge=1, le=1)
    disclosure_token: str | None = Field(default=None, min_length=64, max_length=64)
    language: Literal["en", "es-419"] = "en"


class ReceiptReadBody(_Wire):
    completion_cursor: str = Field(min_length=64, max_length=64, pattern="^[a-f0-9]{64}$")


class ReceiptSummary(_Wire):
    id: str
    activity: ReceiptActivity | None = None
    bandeja: BandejaMembership | None = None
    # ``email`` is decided at the API boundary from the email queue.
    channel: Literal["web", "whatsapp", "email"]
    filename: str | None
    # The sender's own words sent with the file (a WhatsApp caption), verbatim.
    source_text: str | None = None
    media_type: str
    size_bytes: int
    received_at: datetime
    status: ReceiptStatus
    error_code: str | None
    # Why a needs_attention receipt needs the owner; null otherwise.
    attention: Attention | None
    # With attention ``duplicate``: the receipt this one may repeat.
    duplicate_of: str | None = None
    # The upload found the same bytes already saved; this is that receipt.
    replayed: bool = False
    # A read is in flight or will start: queued with consent and the owner's
    # reading allowed now. False for a queued receipt nothing will read.
    read_pending: bool = False
    # The owner may ask for a consented AI read now.
    preparable: bool
    # The owner may fill in the one purchase by hand from version 0.
    enterable: bool
    # Email deliveries this document arrived in, if any.
    email_delivery_ids: list[str] = Field(default_factory=list)
    # The whole message of an email whose attachment is already a receipt. It
    # cannot be prepared or approved; its attachment is the receipt.
    email_original: bool = False
    document_type: DocumentType = "recibo"
    # The read set the type because the upload named none.
    document_type_detected: bool = Field(
        default=False, exclude_if=lambda value: value is False
    )
    # The caller may change the type now: its draft is open and they hold prepare.
    document_type_editable: bool = Field(
        default=False, exclude_if=lambda value: value is False
    )
    expense_id: str | None
    merchant: str | None
    occurred_on: str | None
    amount: str | None
    currency: str | None
    category_id: str | None
    account_id: str | None
    # Marked by a person as no part of the Business: left out of the totals, kept visible.
    personal: bool = Field(default=False, exclude_if=lambda value: value is False)
    # Who marked it, when that was someone other than the owner; absent otherwise.
    personal_marked_by: str | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    # The receipt's facts exist (a draft owns it), so an absent fiscal_value
    # means no fiscal number; absent while nothing is read yet.
    fiscal_known: bool = Field(default=False, exclude_if=lambda value: value is False)
    # The fiscal number the draft carries today (NCF or e-CF), absent without one or before a read.
    fiscal_value: Literal["ncf", "ecf"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    # The accountant's 606 answer for a personal receipt with a fiscal number; absent until given or not applicable.
    include_606: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    # Who gave that answer; absent while there is none.
    include_606_by: str | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    # Marked in review as having no comprobante fiscal; absent otherwise.
    sin_comprobante: bool = Field(default=False, exclude_if=lambda value: value is False)
    # Whether the caller may mark or unmark it: anyone holding prepare.
    personal_editable: bool = Field(
        default=False, exclude_if=lambda value: value is False
    )


class ReceiptEvidenceLine(_Wire):
    description: str
    amount: str | None


class ReceiptEvidence(_Wire):
    merchant: str | None
    occurred_on: str | None
    total: str | None
    currency: str | None
    tax: str | None
    tip: str | None
    service: str | None
    lines: list[ReceiptEvidenceLine]


ReviewField = Literal[
    "merchant", "occurred_on", "amount", "currency", "category_id", "account_id"
]


class ReceiptDetail(ReceiptSummary):
    draft_id: UUID | None = None
    record_context: RecordContext | None = None
    version: int
    evidence: ReceiptEvidence | None
    missing_fields: list[ReviewField]
    # The due date its draft holds; null while unknown or without a draft.
    due_on: date | None = None


class ReceiptPage(_Wire):
    items: list[ReceiptSummary]
    activity: ReceiptActivityCounts | None = None


class ReceiptReviewBody(_Wire):
    version: int = Field(ge=0)
    fields: dict[ReviewField, str | None]


class ConfirmBody(_Wire):
    version: int = Field(ge=0)


class BusinessExpense(_Wire):
    id: str
    merchant: str | None
    amount: str
    currency: str
    category_id: str | None
    account_id: str | None
    funding: Literal["owner_funds"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    occurred_on: date
    receipt_id: str | None
    # The bridge draft that recorded it, when one did: the record to open when
    # the expense names no single receipt.
    draft_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    personal: bool = Field(default=False, exclude_if=lambda value: value is False)
    personal_marked_by: str | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    # A saved expense's fiscal standing is settled on the server: the number it
    # carries, or none, the same split the overview's totals make.
    fiscal_known: bool = True
    fiscal_value: Literal["ncf", "ecf"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    include_606: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    include_606_by: str | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    sin_comprobante: bool = Field(default=False, exclude_if=lambda value: value is False)


class ExpenseDetail(BusinessExpense):
    # When the activity was recorded and its current revision; null when the
    # money read does not say.
    recorded_at: datetime | None = None
    revision: int | None = None


class ExpensePage(_Wire):
    items: list[BusinessExpense]


class ExpenseInput(_Wire):
    account_id: UUID
    amount: str = Field(min_length=1, max_length=40)
    occurred_on: date
    merchant: str | None = Field(default=None, max_length=200)
    category_id: str | None = None


class CurrencyTotal(_Wire):
    currency: str
    amount: str
    count: int


class BusinessOverview(_Wire):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: date = Field(alias="from")
    to: date
    # The server's day in the recording time zone: the one clock for "today".
    today: date
    country: str
    currency: str
    #: "Gastos reales": every approved expense of the period that is not personal.
    totals: list[CurrencyTotal]
    #: "Con valor fiscal": those that carry an NCF or an e-CF.
    fiscal_totals: list[CurrencyTotal] = Field(default_factory=list)
    #: "Sin comprobante fiscal": real minus fiscal, per currency; what does not go into the 606.
    without_fiscal_totals: list[CurrencyTotal] = Field(default_factory=list)
    awaiting_review: int
    needs_attention: int
    #: "Por revisar": the Bandeja's ``ready_to_review_count``.
    ready_to_review_count: int
    #: "Por igualar": the same ``por_igualar_count`` the Bandeja counts carry.
    por_igualar_count: int | None = None
    last_received_at: datetime | None
    last_confirmed_at: datetime | None
    # Saved expenses the chosen period leaves out, so none looks vanished.
    outside_period_count: int = 0
    outside_period_latest_on: date | None = None


class BusinessUpdate(_Wire):
    id: str
    kind: Literal["receipt_ready", "receipt_needs_attention", "expense_confirmed"]
    occurred_at: datetime
    receipt_id: str | None
    expense_id: str | None
    error_code: str | None
    attention: Attention | None
    label: str | None


class UpdatePage(_Wire):
    items: list[BusinessUpdate]


class EmailDeliveryHit(_Wire):
    """One email delivery; ``/business/email/deliveries/{id}`` opens it."""

    id: str
    sender: str | None
    subject: str | None
    received_at: datetime
    state: Literal["received", "processing", "partial", "captured", "rejected"]
    inbox_group: Literal["bandeja", "remitentes_nuevos"] | None


class EmailSenderHit(_Wire):
    """One sender rule, as ``/business/email/senders`` lists it."""

    id: str
    kind: Literal["address", "domain"]
    value: str
    status: Literal["authorized", "blocked"]


class SearchCursors(_Wire):
    """Per list, the cursor to its next page; null when it has no more."""

    expenses: str | None
    ventas: str | None
    receipts: str | None
    accounts: str | None
    email_deliveries: str | None
    email_senders: str | None


class BusinessSearch(_Wire):
    """A page of each list, or only of the ``kind`` asked for."""

    expenses: list[BusinessExpense]
    # Saved ventas (income); ``merchant`` is the client, as on a venta's receipt.
    ventas: list[BusinessExpense]
    receipts: list[ReceiptSummary]
    accounts: list[BusinessAccount]
    email_deliveries: list[EmailDeliveryHit]
    email_senders: list[EmailSenderHit]
    next_cursors: SearchCursors


def _searchable(value: str) -> str:
    if not query_text(value):
        raise ValueError("a search needs a letter, a digit or a sign")
    return value


class RememberSearch(_Wire):
    q: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
        AfterValidator(_searchable),
    ]


class RecentSearch(_Wire):
    id: str
    q: str
    searched_at: datetime


class RecentSearches(_Wire):
    """The member's newest distinct searches in this Business, newest first."""

    items: list[RecentSearch]


class OpenSearchResult(_Wire):
    """A record the member opened from a search result."""

    kind: SearchKind
    id: UUID
