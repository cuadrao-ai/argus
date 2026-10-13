"""Response contracts consumed by the native reviewed-command flow."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from argus.domain.recording.loop_schemas import CoverageAnswer, ObservationQuestion
from argus.domain.recording.money_schemas import ActivityKind, MoneyRequest
from argus.domain.recording.schemas import BalanceResponse, FinancialAccountResponse


class MoneyLegResponse(BaseModel):
    record_id: str
    record_revision: int
    account_id: str
    role: Literal["single", "source", "destination"]
    amount_minor: int
    amount: str
    currency: str
    currency_fraction_digits: int
    balance_movement_minor: int
    coverage: list[CoverageAnswer]


class MoneyActivityResponse(BaseModel):
    activity_id: str
    revision: int
    kind: ActivityKind
    amount_minor: int | None
    amount: str | None
    currency: str
    currency_fraction_digits: int
    occurred_at: datetime
    time_zone: str
    note: str | None
    category_id: str | None
    source_id: str | None
    purchase_activity_id: str | None
    purchase_revision: int | None
    principal_minor: int | None = None
    interest_minor: int | None = None
    fees_minor: int | None = None
    reversal_of_activity_id: str | None = None
    reversal_of_revision: int | None = None
    counted_spending_minor: int | None = None
    reason: str | None
    recorded_at: datetime
    recorded_by: str | None
    funding: Literal["owner_funds"] | None = None
    legs: list[MoneyLegResponse]


class SkippedObservation(BaseModel):
    observation_id: str
    reason: Literal["after_observation_day", "entered_after_observation"]


class MoneyAccountEffect(BaseModel):
    account_id: str
    currency: str
    currency_fraction_digits: int
    before: BalanceResponse
    after: BalanceResponse | None
    observations: list[ObservationQuestion]
    skipped_observations: list[SkippedObservation] = []
    unexplained_before: dict[str, int | None]
    unexplained_after: dict[str, int | None] | None


class MoneyPreviewResponse(BaseModel):
    ready: bool
    expected_versions: dict[str, int]
    affected_accounts: list[MoneyAccountEffect]
    reviewed_request: MoneyRequest | None
    preview_token: str | None


class MoneyReceiptResponse(BaseModel):
    activity: MoneyActivityResponse
    accounts: list[FinancialAccountResponse]
    replayed: bool


class MoneyHistoryResponse(BaseModel):
    items: list[MoneyActivityResponse]
    next_cursor: str | None


class PurchaseResponse(MoneyActivityResponse):
    refunded_minor: int
    refundable_minor: int


class PurchasePageResponse(BaseModel):
    items: list[PurchaseResponse]


class MoneyOptionsResponse(BaseModel):
    accounts: list[FinancialAccountResponse]
    eligibility: dict[str, list[str]]
    destination_eligibility: dict[str, list[str]]
    categories: list[str]
    sources: list[str]
