"""Wire contracts for expectations and explicit fulfillment."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from argus.domain.recording.money_schemas import MoneyRequest

CASH_TYPES = ("cash", "checking", "savings")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Schedule(Input):
    cadence: Literal["once", "weekly", "every_two_weeks", "monthly", "twice_monthly"]
    start_date: date
    end_date: date | None = None
    month_days: list[int] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def valid(self) -> "Schedule":
        if self.start_date.year > 9980:
            raise ValueError("Choose a supported calendar date.")
        if self.end_date and (
            self.end_date < self.start_date
            or (self.end_date - self.start_date).days > 3660
        ):
            raise ValueError("The schedule end must be within ten years of its start.")
        if any(day < 1 or day > 31 for day in self.month_days) or len(
            set(self.month_days)
        ) != len(self.month_days):
            raise ValueError("Choose distinct month days from 1 through 31.")
        if self.cadence == "twice_monthly" and len(self.month_days) != 2:
            raise ValueError("Choose two monthly dates.")
        if self.cadence == "monthly" and len(self.month_days) > 1:
            raise ValueError("Choose one monthly date.")
        if self.cadence not in {"monthly", "twice_monthly"} and self.month_days:
            raise ValueError("Month days require a monthly cadence.")
        return self


class ExpectationCreate(Input):
    kind: Literal["income", "bill"]
    title: str = Field(min_length=1, max_length=100)
    currency: str = Field(max_length=3)
    amount: str = Field(max_length=40)
    account_id: UUID | None = None
    schedule: Schedule

    @field_validator("title")
    @classmethod
    def title_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a title.")
        return value.strip()


class ExpectationEdit(Input):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=100)
    amount: str | None = Field(default=None, max_length=40)
    account_id: UUID | None = None
    schedule: Schedule | None = None
    effective_date: date | None = None
    archived: bool | None = None


class SelectionWrite(Input):
    expected_version: int = Field(ge=0)
    account_ids: list[UUID] = Field(max_length=100)
    time_zone: str = Field(max_length=64)


class Fulfillment(Input):
    expected_version: int = Field(ge=1)
    activity: MoneyRequest


class LinkWrite(Input):
    expected_version: int = Field(ge=1)
    activity_id: UUID
    activity_revision: int = Field(ge=1)
