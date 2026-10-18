"""Wire shapes for Business bank matching. The contract doc is the frontend source."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ReaderId = Literal[
    "pilot_bank",
    "banco_popular",
    "bhd",
    "mercury",
    "sandbox_csv",
    "mapped_csv",
]
SuggestionStatus = Literal["pending", "confirmed", "declined"]
LineSense = Literal["charge", "deposit", "zero"]
LineState = Literal["matched", "sin_comprobante", "unmatched"]


class BankLineResponse(BaseModel):
    id: UUID
    occurred_on: date
    description: str
    amount: Decimal
    currency: str
    sense: LineSense
    state: LineState


class BankSuggestionResponse(BaseModel):
    id: UUID
    line_id: UUID
    target_id: str
    target_kind: Literal["receipt", "venta"]
    status: SuggestionStatus
    amount_score: Decimal
    date_score: Decimal
    merchant_score: Decimal
    confidence: Decimal
    actionable: bool


class BankImportResponse(BaseModel):
    id: UUID
    reader_id: ReaderId
    inserted_count: int
    unchanged_count: int
    created: bool
    imported_at: datetime
    lines: list[BankLineResponse]
    suggestions: list[BankSuggestionResponse]


class UnmatchedChargesResponse(BaseModel):
    count: int = Field(
        description="Same number as unmatched_charge_count for this period."
    )
    period_start: date
    period_end: date
    lines: list[BankLineResponse]
