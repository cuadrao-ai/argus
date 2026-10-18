"""Typed rows for one Business bank account, its lines, and pair decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

MATCH_WINDOW_DAYS = 5

ReaderId = Literal[
    "pilot_bank",
    "banco_popular",
    "bhd",
    "mercury",
    "sandbox_csv",
    "mapped_csv",
]
READER_ORDER: tuple[ReaderId, ...] = (
    "pilot_bank",
    "banco_popular",
    "bhd",
    "mercury",
    "sandbox_csv",
    "mapped_csv",
)

TargetKind = Literal["receipt", "venta"]
SuggestionStatus = Literal["pending", "confirmed", "declined"]
LineSense = Literal["charge", "deposit", "zero"]


class BankMatchingError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AmountAndSignColumns:
    amount: str
    sign: str


@dataclass(frozen=True)
class DebitAndCreditColumns:
    debit: str
    credit: str


CsvMoneyColumns = AmountAndSignColumns | DebitAndCreditColumns


@dataclass(frozen=True)
class CsvMapping:
    """Caller columns for the generic mapped CSV. Money is one convention."""

    date_column: str
    description_column: str
    money: CsvMoneyColumns
    currency_column: str | None = None


@dataclass(frozen=True)
class BankAccountBinding:
    id: UUID
    space_id: UUID
    account_id: UUID
    currency: str
    created_at: datetime


@dataclass(frozen=True)
class BankImport:
    id: UUID
    space_id: UUID
    bank_account_id: UUID
    reader_id: ReaderId
    source_sha256: str
    idempotency_key: str
    inserted_count: int
    unchanged_count: int
    imported_by: UUID
    imported_at: datetime


@dataclass(frozen=True)
class BankLine:
    id: UUID
    space_id: UUID
    bank_account_id: UUID
    first_import_id: UUID
    occurred_on: date
    description: str
    normalized_description: str
    amount: Decimal
    currency: str
    raw_line: Mapping[str, str]
    line_hash: str
    created_at: datetime

    @property
    def sense(self) -> LineSense:
        if self.amount < 0:
            return "charge"
        if self.amount > 0:
            return "deposit"
        return "zero"


@dataclass(frozen=True)
class ScoreParts:
    """The offer that was stored. Confidence is derived from these parts."""

    amount_score: Decimal
    date_score: Decimal
    merchant_score: Decimal


@dataclass(frozen=True)
class Suggestion:
    id: UUID
    space_id: UUID
    line_id: UUID
    target_id: str
    target_kind: TargetKind
    status: SuggestionStatus
    parts: ScoreParts
    created_at: datetime
    decided_at: datetime | None
    decided_by: UUID | None
    decision_key: str | None


@dataclass(frozen=True)
class NormalizedRow:
    occurred_on: date
    description: str
    amount: Decimal
    currency: str
    raw_line: Mapping[str, str]


class MatchTarget(Protocol):
    id: str
    kind: TargetKind
    amount: Decimal
    currency: str
    occurred_on: date
    merchant: str | None
    approved: bool


class TargetCatalog(Protocol):
    def approved_targets(
        self,
        space_id: UUID,
        *,
        kind: TargetKind,
        period_start: date,
        period_end: date,
    ) -> tuple[MatchTarget, ...]: ...

    def get(
        self, space_id: UUID, *, kind: TargetKind, target_id: str
    ) -> MatchTarget | None: ...


@dataclass(frozen=True)
class ImportResult:
    bank_import: BankImport
    created: bool
    lines: tuple[BankLine, ...]
    suggestions: tuple[Suggestion, ...]


@dataclass(frozen=True)
class AccountRef:
    account_id: UUID
    currency: str
