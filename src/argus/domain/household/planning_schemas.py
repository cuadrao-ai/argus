"""Shared Plan wire selects disclosed facts before any financial reduction."""

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Discriminator, Field, Tag, model_validator

from argus.domain.planning.budget_schemas import BudgetCreate
from argus.domain.planning.debt_schemas import DebtCreate
from argus.domain.planning.goal_schemas import GoalCreate
from argus.domain.planning.schemas import ExpectationCreate, Input, Schedule
from argus.domain.recording.money_responses import (
    MoneyActivityResponse,
    MoneyOptionsResponse,
    MoneyPreviewResponse,
)
from argus.domain.recording.money_schemas import MoneyRequest

PlanKind = Literal["budget", "bill", "goal", "debt"]
Purpose = Literal["funding", "spending", "bill_payment", "goal_saving", "debt_payment"]


class PlanRef(Input):
    kind: PlanKind
    id: UUID


class ScopeCommand(Input):
    membership_id: UUID
    expected_authorization_version: int = Field(ge=1)


class PlanCommand(ScopeCommand):
    expected_plan_version: int = Field(ge=1)


class ParticipantWrite(Input):
    membership_id: UUID
    permission: Literal["view", "edit"] = "view"


class ResponsibilityWrite(Input):
    membership_id: UUID
    amount: str | None = Field(default=None, max_length=40)
    period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    occurrence_id: UUID | None = None
    schedule_id: UUID | None = None
    agreed_date: date | None = None

    @model_validator(mode="after")
    def one_period(self) -> "ResponsibilityWrite":
        if (
            sum(
                value is not None
                for value in (
                    self.period,
                    self.occurrence_id,
                    self.schedule_id,
                    self.agreed_date,
                )
            )
            != 1
        ):
            raise ValueError("Choose one month, occurrence, schedule or agreed date.")
        return self


class BudgetInput(BudgetCreate):
    kind: Literal["budget"] = "budget"


class BillInput(ExpectationCreate):
    kind: Literal["bill"] = "bill"


class GoalInput(GoalCreate):
    kind: Literal["goal"] = "goal"


class DebtInput(DebtCreate):
    kind: Literal["debt"] = "debt"


DefinitionInput = Annotated[
    BudgetInput | BillInput | GoalInput | DebtInput, Field(discriminator="kind")
]


class CreatePlan(ScopeCommand):
    definition: DefinitionInput
    participants: list[ParticipantWrite] = Field(default_factory=list, max_length=100)
    responsibilities: list[ResponsibilityWrite] = Field(
        default_factory=list, max_length=100
    )
    publish_budget_scope: bool = False


class SharePlan(PlanCommand):
    participants: list[ParticipantWrite] = Field(default_factory=list, max_length=100)
    responsibilities: list[ResponsibilityWrite] = Field(
        default_factory=list, max_length=100
    )
    publish_budget_scope: bool = False


class DefinitionPatch(Input):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    amount: str | None = Field(default=None, max_length=40)
    target_date: date | None = None
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    category_ids: list[str] | None = Field(default=None, max_length=100)
    include_uncategorized: bool | None = None
    schedule: Schedule | None = None
    effective_date: date | None = None
    archived: bool | None = None
    planned_contribution_amount: str | None = Field(default=None, max_length=40)


class EditPlan(PlanCommand):
    definition: DefinitionPatch | None = None
    responsibilities: list[ResponsibilityWrite] | None = Field(
        default=None, max_length=100
    )


class ReplaceParticipants(PlanCommand):
    participants: list[ParticipantWrite] = Field(max_length=100)
    responsibilities: list[ResponsibilityWrite] | None = Field(
        default=None, max_length=100
    )
    publish_budget_scope: bool | None = None


class ContributionLink(PlanCommand):
    activity_id: UUID
    activity_revision: int = Field(ge=1)
    expected_account_versions: dict[UUID, int]
    purpose: Purpose
    occurrence_id: UUID | None = None
    treatment: Literal["add", "included"] = "add"


class ContributionRecord(PlanCommand):
    activity: MoneyRequest
    purpose: Purpose
    occurrence_id: UUID | None = None


class ContributionCorrection(PlanCommand):
    activity: MoneyRequest


class AllocationWrite(PlanCommand):
    account_id: UUID
    amount: str = Field(max_length=40)
    expected_account_versions: dict[UUID, int]


class Person(Input):
    membership_id: UUID
    display_name: str


class Participant(Person):
    permission: Literal["view", "edit"]
    is_self: bool


class Responsibility(Input):
    person: Person
    amount_minor: str | None
    period: str | None = None
    occurrence_id: UUID | None = None
    schedule_id: UUID | None = None
    agreed_date: date | None = None


class AuthorizedOriginal(Input):
    kind: Literal["activity"] = "activity"
    activity_id: UUID
    account_id: UUID
    household_id: UUID | None = None


class SharedContribution(Input):
    id: UUID
    person: Person
    amount_minor: str | None
    applied_minor: str | None
    currency: str
    currency_fraction_digits: int
    date: date
    status: Literal["current", "released", "needs_review"]
    original: AuthorizedOriginal | None
    purpose: Purpose
    occurrence_id: UUID | None
    can_correct: bool
    can_release: bool


class SharedOccurrence(Input):
    id: UUID
    date: date
    amount_minor: str
    applied_minor: str | None
    remaining_minor: str | None
    status: Literal["pending", "partial", "fulfilled", "needs_review", "archived"]


class SharedAllocation(Input):
    id: UUID
    person: Person
    assigned_minor: str
    supported_minor: str | None
    status: Literal["current", "needs_review"]
    can_edit: bool


class PublicDefinition(Input):
    name: str
    currency: str
    currency_fraction_digits: int
    earliest_effective_date: date


class SharedBudget(PublicDefinition):
    limit_minor: str
    month: str
    category_ids: list[str]
    include_uncategorized: bool
    publish_budget_scope: bool


class SharedBill(PublicDefinition):
    amount_minor: str
    schedule: Schedule


class SharedGoal(PublicDefinition):
    target_minor: str
    target_date: date | None
    schedule: Schedule | None
    planned_contribution_minor: str | None


class SharedDebt(PublicDefinition):
    amount_minor: str
    schedule: Schedule


class SharedProgress(Input):
    actual_minor: str | None
    applied_minor: str | None
    remaining_minor: str | None
    state: Literal["active", "reached", "needs_review", "unknown", "archived"]
    debt_balance_minor: str | None = None
    debt_state: str | None = None


class BudgetProgress(SharedProgress):
    gross_minor: str | None
    refunds_minor: str | None
    spent_minor: str | None
    over_budget: bool | None


class GoalProgress(SharedProgress):
    planned_minor: str | None
    projected_minor: str | None


class PlanBase(Input):
    ref: PlanRef
    version: int
    household_id: UUID
    membership_id: UUID
    authorization_version: int
    owner: Person
    permission: Literal["view", "edit"]
    is_owner: bool
    participants: list[Participant]
    responsibilities: list[Responsibility]
    occurrences: list[SharedOccurrence]
    contributions: list[SharedContribution]
    progress: SharedProgress
    archived: bool
    read_only: bool
    archive_reason: Literal["owner_departed"] | None
    can_restore: bool
    last_edited_by: Person | None = None
    recorded_at: datetime | None = None


class BudgetPlan(PlanBase):
    definition: SharedBudget
    progress: BudgetProgress


class BillPlan(PlanBase):
    definition: SharedBill


class GoalPlan(PlanBase):
    definition: SharedGoal
    progress: GoalProgress
    allocations: list[SharedAllocation]


class DebtPlan(PlanBase):
    definition: SharedDebt


def ref_kind(value: Any) -> str:
    return value["ref"]["kind"] if isinstance(value, dict) else value.ref.kind


SharedPlan = Annotated[
    Annotated[BudgetPlan, Tag("budget")]
    | Annotated[BillPlan, Tag("bill")]
    | Annotated[GoalPlan, Tag("goal")]
    | Annotated[DebtPlan, Tag("debt")],
    Discriminator(ref_kind),
]


class PlanSnapshot(Input):
    household_id: UUID
    membership_id: UUID
    authorization_version: int
    plans: list[SharedPlan]


class PlanReceipt(Input):
    plan: SharedPlan
    replayed: bool


class ContributionPreview(Input):
    plan: SharedPlan
    money: MoneyPreviewResponse


class ContributionCandidates(Input):
    items: list[MoneyActivityResponse]


class PlanHistory(Input):
    items: list[SharedPlan]


class ExistingDefinition(Input):
    ref: PlanRef
    name: str
    version: int
    currency: str


class PlanOptions(Input):
    membership_id: UUID
    authorization_version: int
    people: list[Person]
    money: MoneyOptionsResponse
    owned_account_ids: list[UUID]
    existing_definitions: list[ExistingDefinition]
    purposes: dict[PlanKind, list[Purpose]]
