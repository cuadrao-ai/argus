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


class CreateBusinessAccount(_Wire):
    nickname: str = Field(min_length=1, max_length=200)
    type: ExpenseAccountType
    currency: str = Field(min_length=3, max_length=3)


class ReceiptSummary(_Wire):
    id: str
    channel: Literal["web", "whatsapp"]
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
    totals: list[CurrencyTotal]
    awaiting_review: int
    needs_attention: int
    last_received_at: datetime | None
    last_confirmed_at: datetime | None


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
