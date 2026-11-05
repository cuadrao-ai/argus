"""Personal savings intentions and their account-backed read contract."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from argus.domain.planning.schemas import Input, Schedule
from argus.domain.recording.money_responses import (
    MoneyActivityResponse,
    MoneyPreviewResponse,
)
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.schemas import FinancialAccountResponse


class ContributionPlan(Input):
    source_account_id: UUID
    amount: str = Field(max_length=40)
    schedule: Schedule


class GoalCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    currency: str = Field(max_length=3)
    target: str = Field(max_length=40)
    target_date: date | None = None
    destination_account_id: UUID | None = None
    contribution_plan: ContributionPlan | None = None

    @field_validator("name")
    @classmethod
    def named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a name.")
        return value.strip()


class GoalEdit(Input):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    target: str | None = Field(default=None, max_length=40)
    target_date: date | None = None
    destination_account_id: UUID | None = None
    contribution_plan: ContributionPlan | None = None
    effective_date: date | None = None
    archived: bool | None = None


class AllocationChange(Input):
    goal_id: UUID
    expected_version: int = Field(ge=1)
    account_id: UUID
    amount: str = Field(max_length=40)
    release_claim_ids: list[UUID] = Field(default_factory=list, max_length=100)


class AllocationWrite(Input):
    changes: list[AllocationChange] = Field(min_length=1, max_length=100)
    expected_account_versions: dict[UUID, int]


class ContributionLink(Input):
    expected_version: int = Field(ge=1)
    activity_id: UUID
    activity_revision: int = Field(ge=1)
    treatment: Literal["add", "included"]
    occurrence_id: UUID | None = None
    expected_account_versions: dict[UUID, int]


class ContributionRecord(Input):
    expected_version: int = Field(ge=1)
    activity: MoneyRequest
    occurrence_id: UUID | None = None


class ContributionRelease(Input):
    expected_version: int = Field(ge=1)


class GoalAllocation(BaseModel):
    account_id: str
    unlinked_minor: int


class GoalDefinition(BaseModel):
    id: str
    version: int
    name: str
    currency: str
    currency_fraction_digits: int
    target_minor: int
    target: str
    target_date: date | None
    destination_account_id: str | None
    contribution_plan: ContributionPlan | None
    allocations: list[GoalAllocation]
    archived: bool
    earliest_effective_date: date


class GoalPool(BaseModel):
    account_id: str
    account_name: str | None
    currency: str
    account_version: int
    ownership_share_bps: int
    as_of: datetime | None
    backing_minor: str | None
    assigned_minor: str
    available_minor: str | None
    shortfall_minor: str | None
    state: Literal["backed", "shortfall", "unknown", "ineligible"]
    affected_goal_ids: list[str]
    affected_goal_names: list[str]


class GoalContribution(BaseModel):
    id: str
    activity_id: str
    activity_revision: int | None
    occurrence_id: str | None
    source_account_id: str
    destination_account_id: str
    treatment: Literal["add", "included"]
    reviewed_personal_minor: str
    current_personal_minor: str | None
    counting: bool
    status: Literal["current", "needs_review", "released"]
    reason: str | None
    activity: MoneyActivityResponse | None


class GoalComponent(BaseModel):
    account_id: str
    assigned_minor: str
    supported_minor: str | None


class GoalProgress(BaseModel):
    goal: GoalDefinition
    assigned_minor: str
    supported_minor: str | None
    independently_backed_minor: str
    remaining_minor: str | None
    state: Literal["unconfigured", "active", "reached", "needs_review"]
    reasons: list[str]
    pools: list[GoalPool]
    contributions: list[GoalContribution]
    components: list[GoalComponent]
    planned_minor: str
    projected_minor: str | None
    projection_end_date: date


class GoalReceipt(BaseModel):
    goal: GoalProgress
    replayed: bool


class AllocationReceipt(BaseModel):
    goals: list[GoalProgress]
    pools: list[GoalPool]
    replayed: bool


class ContributionPreview(BaseModel):
    goal: GoalProgress
    pools: list[GoalPool]
    money: MoneyPreviewResponse


class ContributionReceipt(GoalReceipt):
    activity: MoneyActivityResponse
    accounts: list[FinancialAccountResponse]
