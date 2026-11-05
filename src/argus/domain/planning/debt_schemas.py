"""Debt intentions, explicit scenarios and canonical payment claims."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from argus.domain.planning.goal_schemas import GoalPool
from argus.domain.planning.schemas import Input, Schedule
from argus.domain.recording.money_responses import (
    MoneyActivityResponse,
    MoneyPreviewResponse,
)
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.schemas import BalanceResponse, FinancialAccountResponse


class PayoffAssumptions(Input):
    annual_rate_percent: Decimal = Field(ge=0, le=1000)
    recurring_fees: str = Field(max_length=40)
    first_period_start: date
    no_new_borrowing: Literal[True]


class DebtCreate(Input):
    debt_account_id: UUID
    name: str = Field(min_length=1, max_length=100)
    source_account_id: UUID
    amount: str = Field(max_length=40)
    schedule: Schedule
    assumptions: PayoffAssumptions | None = None

    @field_validator("name")
    @classmethod
    def named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a name.")
        return value.strip()


class DebtEdit(Input):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    source_account_id: UUID | None = None
    amount: str | None = Field(default=None, max_length=40)
    schedule: Schedule | None = None
    effective_date: date | None = None
    archived: bool | None = None
    assumptions: PayoffAssumptions | None = None


class DebtRecord(Input):
    expected_version: int = Field(ge=1)
    activity: MoneyRequest
    occurrence_id: UUID | None = None


class DebtLink(Input):
    expected_version: int = Field(ge=1)
    activity_id: UUID
    activity_revision: int = Field(ge=1)
    occurrence_id: UUID | None = None
    expected_account_versions: dict[UUID, int]


class DebtDefinition(BaseModel):
    id: str
    version: int
    debt_account_id: str
    name: str
    currency: str
    currency_fraction_digits: int
    source_account_id: str
    amount_minor: int
    amount: str
    schedule: Schedule
    assumptions: PayoffAssumptions | None
    archived: bool
    earliest_effective_date: date


class ConditionalPayoff(BaseModel):
    state: Literal["conditional", "unavailable"]
    reason: str | None = None
    payoff_date: date | None = None
    payments: int | None = None
    total_interest_minor: str | None = None
    total_fees_minor: str | None = None
    assumptions: PayoffAssumptions | None = None


class DebtPayment(BaseModel):
    id: str
    activity_id: str
    occurrence_id: str | None
    status: Literal["current", "needs_review"]
    net_paid_minor: int | None
    activity: MoneyActivityResponse | None


class DebtProgress(BaseModel):
    debt: DebtDefinition
    balance: BalanceResponse
    state: Literal["active", "unknown", "recorded_clear", "needs_review"]
    funding_pool: GoalPool | None = None
    payoff: ConditionalPayoff
    payments: list[DebtPayment]
    occurrences: list[dict[str, Any]]


class DebtReceipt(BaseModel):
    debt: DebtProgress
    replayed: bool


class DebtPaymentPreview(BaseModel):
    debt: DebtProgress
    money: MoneyPreviewResponse


class DebtPaymentReceipt(DebtReceipt):
    activity: MoneyActivityResponse
    accounts: list[FinancialAccountResponse]
