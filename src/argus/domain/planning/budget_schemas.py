"""Personal budget definitions and derived progress contracts."""

from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from argus.domain.planning.debt_schemas import DebtProgress
from argus.domain.planning.goal_schemas import GoalProgress
from argus.domain.planning.schemas import Input
from argus.domain.recording.loop_schemas import HomeResponse, ReportingPeriod
from argus.domain.recording.money_responses import MoneyActivityResponse


class BudgetCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    limit: str = Field(max_length=40)
    currency: str = Field(max_length=3)
    month: str = Field(max_length=7)
    account_ids: list[UUID] = Field(min_length=1, max_length=100)
    category_ids: list[str] = Field(max_length=100)
    include_uncategorized: bool


class BudgetEdit(Input):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    limit: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, max_length=3)
    month: str | None = Field(default=None, max_length=7)
    account_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)
    category_ids: list[str] | None = Field(default=None, max_length=100)
    include_uncategorized: bool | None = None
    archived: bool | None = None

    @model_validator(mode="after")
    def reject_null(self) -> "BudgetEdit":
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Budget fields cannot be null.")
        return self


class BudgetDefinition(BaseModel):
    id: str
    version: int
    name: str
    limit_minor: int
    limit: str
    currency: str
    currency_fraction_digits: int
    month: str
    account_ids: list[str]
    category_ids: list[str]
    include_uncategorized: bool
    archived: bool


class BudgetProgress(BaseModel):
    budget: BudgetDefinition
    period: ReportingPeriod
    gross_purchases_minor: str
    refunds_minor: str
    spent_minor: str
    remaining_minor: str
    over_budget_minor: str
    contributors: list[MoneyActivityResponse]


class BudgetReceipt(BaseModel):
    budget: BudgetDefinition
    replayed: bool


class BudgetHomeResponse(HomeResponse):
    budgets: list[BudgetProgress] = Field(default_factory=list)
    debts: list[DebtProgress] = Field(default_factory=list)
    goals: list[GoalProgress] = Field(default_factory=list)
