"""Wire shapes for ``/api/v1/business``, matching ``web/lib/business-api.ts``."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from argus.api.schemas import Language
from argus.domain.business.contracts.dossier import RecordContext
from argus.domain.business.receipts import Attention
from argus.domain.business.spaces import MAX_NAME_LENGTH
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


class RenameBusinessSpace(_Wire):
    name: SpaceName


class BusinessAccount(_Wire):
    id: str
    nickname: str | None
    type: str
    currency: str


class ReceiptLimits(_Wire):
    max_bytes: int
    media_types: list[str]


class BusinessWorkspace(_Wire):
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


class BusinessAccess(_Wire):
    grants: list[BusinessAccessGrant]
    invites: list[BusinessAccessInvite]


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


class ReceiptActivityCounts(_Wire):
    reading_count: int
    # New activity this person has not opened: the badge's dot, not its number.
    unread_count: int
    presentation: Literal["working", "unread", "none"]
    # Every row the Bandeja lists, opened or not: receipts not yet saved or
    # dismissed (never the email itself) and notes no receipt carries.
    pending_review_count: int
    # Of those receipts, how many need the person's attention.
    needs_attention_count: int


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
    #: "Gastos reales": every approved expense of the period that is not personal.
    totals: list[CurrencyTotal]
    #: "Con valor fiscal": those that carry an NCF or an e-CF.
    fiscal_totals: list[CurrencyTotal] = Field(default_factory=list)
    #: "Sin comprobante fiscal": real minus fiscal, per currency; what does not go into the 606.
    without_fiscal_totals: list[CurrencyTotal] = Field(default_factory=list)
    awaiting_review: int
    needs_attention: int
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


class BusinessSearch(_Wire):
    """Each list is capped at the request's ``limit``; nothing is paged."""

    expenses: list[BusinessExpense]
    receipts: list[ReceiptSummary]
    accounts: list[BusinessAccount]
