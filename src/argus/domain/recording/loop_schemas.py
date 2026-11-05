"""Typed wire inputs for the financial loop and its review step."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from argus.domain.recording.money_schemas import ActivityKind
from argus.domain.recording.schemas import (
    BalanceResponse,
    FinancialAccountResponse,
    WriteOpeningRequest,
)

CATEGORY_IDS = (
    "other",
    "groceries",
    "dining",
    "transport",
    "housing",
    "health",
    "shopping",
    "interest_fees",
)


class CoverageAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation_id: str
    included: bool

    @field_validator("observation_id")
    @classmethod
    def canonical_observation(cls, value: str) -> str:
        return str(UUID(value))


class ActivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    expected_revision: int | None = Field(default=None, ge=1)
    amount: str = Field(max_length=40)
    occurred_at: datetime
    time_zone: str = Field(default="America/Santo_Domingo", max_length=64)
    note: str | None = Field(default=None, max_length=200)
    category_id: str | None = None
    reason: str | None = Field(default=None, max_length=200)
    coverage: list[CoverageAnswer] = Field(default_factory=list, max_length=1000)
    preview_token: str | None = Field(default=None, max_length=128)


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    amount: str = Field(max_length=40)
    as_of: datetime
    time_zone: str = Field(default="America/Santo_Domingo", max_length=64)
    source: Literal["manual"] = "manual"
    note: str | None = Field(default=None, max_length=200)
    preview_token: str | None = Field(default=None, max_length=128)


class OpeningCoverageAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_id: str
    included: bool

    @field_validator("activity_id")
    @classmethod
    def canonical_activity(cls, value: str) -> str:
        return str(UUID(value))


class LoopOpeningRequest(WriteOpeningRequest):
    coverage: list[OpeningCoverageAnswer] = Field(default_factory=list, max_length=1000)
    preview_token: str | None = Field(default=None, max_length=128)


class ActivityResponse(BaseModel):
    record_id: str
    revision: int
    kind: ActivityKind = "expense"
    activity_id: str | None = None
    role: str = "single"
    active: bool = True
    amount_minor: int
    amount: str
    balance_movement_minor: int
    occurred_at: datetime
    time_zone: str
    note: str | None
    category_id: str | None
    reason: str | None
    recorded_at: datetime
    recorded_by: str | None
    coverage: list[CoverageAnswer]


class ObservationQuestion(BaseModel):
    observation_id: str
    time_zone: str
    kind: Literal["opening", "balance_check", "value_update"]
    as_of: datetime
    amount_minor: int
    amount: str
    included: bool | None


class ActivityPreviewResponse(BaseModel):
    account_version: int
    ready: bool
    observations: list[ObservationQuestion]
    before: BalanceResponse
    after: BalanceResponse | None
    preview_token: str | None


class CheckPreviewResponse(BaseModel):
    account_version: int
    currency: str
    currency_fraction_digits: int
    expected_amount_minor: int | None
    observed_amount_minor: int
    difference_minor: int | None
    as_of: datetime
    time_zone: str
    preview_token: str


class CheckResponse(BaseModel):
    record_id: str
    revision: int
    kind: Literal["balance_check", "value_update"]
    as_of: datetime
    time_zone: str
    source: Literal["manual"]
    expected_amount_minor: int | None
    observed_amount_minor: int
    difference_minor: int | None
    unexplained_minor: int | None
    note: str | None
    recorded_at: datetime
    recorded_by: str | None


class ActivityOperationResponse(BaseModel):
    account: FinancialAccountResponse
    activity: ActivityResponse
    replayed: bool


class CheckOperationResponse(BaseModel):
    account: FinancialAccountResponse
    check: CheckResponse
    replayed: bool


class ActivityPageResponse(BaseModel):
    items: list[ActivityResponse]
    next_cursor: str | None


class CheckPageResponse(BaseModel):
    items: list[CheckResponse]
    next_cursor: str | None


class OpeningActivityQuestion(BaseModel):
    activity_id: str
    amount_minor: int
    amount: str
    occurred_at: datetime
    note: str | None
    included: bool | None


class OpeningPreviewResponse(BaseModel):
    account_version: int
    ready: bool
    activities: list[OpeningActivityQuestion]
    before: BalanceResponse
    after: BalanceResponse | None
    preview_token: str | None


class CurrencySummaryResponse(BaseModel):
    currency: str
    currency_fraction_digits: int
    assets_minor: str
    cash_minor: str
    other_assets_minor: str
    debts_minor: str
    net_worth_minor: str
    known_accounts: int
    unknown_accounts: int
    gross_income_minor: str = "0"
    gross_purchases_minor: str = "0"
    refunds_minor: str = "0"
    net_spending_minor: str = "0"
    recorded_spending_minor: str
    as_of: datetime | None


class RecentActivityResponse(ActivityResponse):
    account_id: str
    account_nickname: str | None
    currency: str
    currency_fraction_digits: int


class ReportingPeriod(BaseModel):
    month: str
    time_zone: str
    start_at: datetime
    end_at_exclusive: datetime


class HomeResponse(BaseModel):
    period: ReportingPeriod
    coverage: Literal["recorded_only"] = "recorded_only"
    currencies: list[CurrencySummaryResponse]
    recent_activity: list[RecentActivityResponse]
    recorded_at: datetime


class CategoryResponse(BaseModel):
    id: str
    kind: Literal["expense"]


class CategoriesResponse(BaseModel):
    categories: list[CategoryResponse]
