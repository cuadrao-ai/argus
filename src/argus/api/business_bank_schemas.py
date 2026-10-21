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
LineState = Literal["igualada", "sugerencia", "falta_comprobante", "no_lleva_comprobante"]
ItemState = Literal[
    "igualada",
    "sugerencia",
    "falta_comprobante",
    "no_lleva_comprobante",
    "sin_movimiento",
]


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


class MovementAccount(BaseModel):
    account_id: UUID
    name: str | None
    type: str


class AccountCoverage(MovementAccount):
    bank_account_id: UUID
    currency: str
    covered_through: date | None = Field(
        description="Newest movement date imported for this account. Later dates are unknown, not missing."
    )


class MatchDocument(BaseModel):
    activity_id: UUID
    kind: Literal["receipt", "venta"]
    counterparty: str | None
    occurred_on: date
    currency: str
    total_minor: int
    total: str
    itbis_minor: int | None
    itbis: str | None
    rnc: str | None
    ncf: str | None
    ecf: str | None
    status: Literal["pendiente", "pagado", "cobrado"]
    settled_on: date | None
    payment_method: str | None
    category_id: str | None


class SuggestionReason(BaseModel):
    code: Literal["monto_exacto", "misma_fecha", "fecha_cercana", "nombre_parecido"]
    days: int | None = Field(
        default=None,
        description="fecha_cercana only: document date minus movement date.",
    )


class MovementSuggestion(BaseModel):
    id: UUID
    confidence: Decimal
    reasons: list[SuggestionReason]
    document: MatchDocument


class MovementItem(BaseModel):
    kind: Literal["movement", "document"]
    id: UUID
    occurred_on: date
    description: str | None
    counterparty: str | None
    sense: LineSense
    currency: str
    amount_minor: int
    amount: str
    state: ItemState
    reason: Literal["monto_cero"] | None
    category_id: str | None
    account: MovementAccount
    method: str | None
    document: MatchDocument | None
    suggestions: list[MovementSuggestion]


class MovementCounts(BaseModel):
    movimientos: int
    igualadas: int
    no_lleva_comprobante: int
    sugerencias: int
    falta_comprobante: int
    sin_movimiento: int
    por_igualar: int


class MovementTotals(BaseModel):
    currency: str
    entradas_minor: int
    entradas: str
    salidas_minor: int
    salidas: str
    por_igualar_minor: int
    por_igualar: str
    counts: MovementCounts


class MovementsResponse(BaseModel):
    period_start: date
    period_end: date
    segment: Literal["por_igualar", "igualadas", "todas"]
    sense: Literal["charge", "deposit"] | None
    accounts: list[AccountCoverage]
    totals: list[MovementTotals]
    items: list[MovementItem]
    next_cursor: str | None
