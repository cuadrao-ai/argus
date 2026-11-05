"""Typed Plan read models and command receipts."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from argus.domain.planning.budget_schemas import BudgetHomeResponse, BudgetProgress
from argus.domain.planning.debt_schemas import DebtProgress
from argus.domain.planning.goal_schemas import GoalPool, GoalProgress
from argus.domain.planning.schemas import Schedule
from argus.domain.recording.money_responses import (
    MoneyActivityResponse,
    MoneyPreviewResponse,
)
from argus.domain.recording.schemas import FinancialAccountResponse


class Selection(BaseModel):
    version: int
    account_ids: list[str]
    time_zone: str


class Expectation(BaseModel):
    id: str
    version: int
    kind: Literal["income", "bill"]
    title: str
    currency: str
    currency_fraction_digits: int
    amount_minor: int
    amount: str
    account_id: str | None
    schedule: Schedule
    archived: bool
    earliest_effective_date: date


class Occurrence(BaseModel):
    id: str
    expectation_id: str | None
    debt_plan_id: str | None = None
    paid_minor: int | None = None
    remaining_minor: int | None = None
    goal_id: str | None = None
    source_account_id: str | None = None
    destination_account_id: str | None = None
    expectation_version: int
    kind: Literal["income", "bill", "goal_transfer", "debt_payment"]
    title: str
    currency: str
    currency_fraction_digits: int
    amount_minor: int
    amount: str
    account_id: str | None
    due_date: date
    projection_date: date
    status: Literal["planned", "fulfilled", "needs_review"]
    activity_id: str | None
    activity_revision: int | None
    exclusion_reason: (
        Literal[
            "account_unassigned",
            "account_not_selected",
            "link_needs_review",
            "account_changed",
            "recorded_clear",
            "plan_archived",
        ]
        | None
    )
    overdue: bool


class Point(BaseModel):
    date: date
    occurrence_id: str | None
    change_minor: str
    known_balance_minor: str
    balance_minor: str | None


class ForecastCurrency(BaseModel):
    currency: str
    currency_fraction_digits: int
    account_ids: list[str]
    unknown_account_ids: list[str]
    known_starting_minor: str
    starting_minor: str | None
    expected_income_minor: str
    expected_bills_minor: str
    transfer_effect_minor: str
    net_cash_change_minor: str
    ending_minor: str | None
    first_shortfall_date: date | None
    as_of: datetime | None
    points: list[Point]
    order: Literal["bills_before_income"]


class PlanResponse(BaseModel):
    home: BudgetHomeResponse
    budgets: list[BudgetProgress]
    debts: list[DebtProgress] = []
    goals: list[GoalProgress]
    goal_pools: list[GoalPool]
    selection: Selection
    accounts: list[FinancialAccountResponse]
    expectations: list[Expectation]
    occurrences: list[Occurrence]
    currencies: list[ForecastCurrency]
    start_date: date
    end_date: date
    coverage: Literal["recorded_and_expected"]
    has_expectations: bool


class ExpectationReceipt(BaseModel):
    expectation: Expectation
    replayed: bool


class SelectionReceipt(BaseModel):
    selection: Selection
    replayed: bool


class LinkReceipt(BaseModel):
    occurrence: Occurrence
    replayed: bool


class FulfillmentPreview(BaseModel):
    occurrence: Occurrence
    money: MoneyPreviewResponse


class FulfillmentReceipt(LinkReceipt):
    activity: MoneyActivityResponse
    accounts: list[FinancialAccountResponse]


class Candidates(BaseModel):
    items: list[MoneyActivityResponse]
