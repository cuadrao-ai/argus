"""Registered-owner Plan transport; planning and recording own the facts."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request

from argus.api.financial_accounts import (
    FinancialAccountsContext,
    domain_problem,
    require_financial_accounts_context,
)
from argus.api.routers.financial_loop import _key
from argus.domain.planning.budget_schemas import (
    BudgetCreate,
    BudgetEdit,
    BudgetProgress,
    BudgetReceipt,
)
from argus.domain.planning.budgets import BudgetService
from argus.domain.planning.goal_schemas import (
    AllocationReceipt,
    AllocationWrite,
    ContributionLink,
    ContributionPreview,
    ContributionReceipt,
    ContributionRecord,
    ContributionRelease,
    GoalCreate,
    GoalEdit,
    GoalProgress,
    GoalReceipt,
)
from argus.domain.planning.goals import GoalService
from argus.domain.planning.model import UnsafeCutover
from argus.domain.planning.responses import (
    Candidates,
    Expectation,
    ExpectationReceipt,
    FulfillmentPreview,
    FulfillmentReceipt,
    LinkReceipt,
    PlanResponse,
    SelectionReceipt,
)
from argus.domain.planning.schemas import (
    ExpectationCreate,
    ExpectationEdit,
    Fulfillment,
    LinkWrite,
    SelectionWrite,
)
from argus.domain.planning.service import PlanService

router = APIRouter(prefix="/financial-plan", tags=["financial-plan"])
Context = Annotated[FinancialAccountsContext, Depends(require_financial_accounts_context)]
Key = Annotated[str | None, Header(alias="Idempotency-Key")]


def call(request: Request, action: Any) -> Any:
    try:
        return action()
    except UnsafeCutover as error:
        response = domain_problem(request, error)
        response.detail["earliest_effective_date"] = error.earliest_effective_date
        raise response from None
    except Exception as error:
        raise domain_problem(request, error) from None


@router.get("", response_model=PlanResponse)
def read(
    request: Request,
    context: Context,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Any:
    return call(
        request,
        lambda: PlanService(context.service).read(context.user_id, start_date, end_date),
    )


@router.post("/expectations", response_model=ExpectationReceipt, status_code=201)
def create(
    request: Request,
    context: Context,
    body: ExpectationCreate,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: PlanService(context.service).create(
            context.user_id, body, _key(request, idempotency_key)
        ),
    )


@router.patch("/expectations/{expectation_id}", response_model=ExpectationReceipt)
def edit(
    request: Request,
    context: Context,
    expectation_id: str,
    body: ExpectationEdit,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: PlanService(context.service).edit(
            context.user_id, expectation_id, body, _key(request, idempotency_key)
        ),
    )


@router.put("/selection", response_model=SelectionReceipt)
def selection(
    request: Request, context: Context, body: SelectionWrite, idempotency_key: Key = None
) -> Any:
    return call(
        request,
        lambda: PlanService(context.service).selection(
            context.user_id, body, _key(request, idempotency_key)
        ),
    )


@router.post(
    "/occurrences/{occurrence_id}/fulfillment/preview", response_model=FulfillmentPreview
)
def preview(
    request: Request, context: Context, occurrence_id: str, body: Fulfillment
) -> Any:
    return call(
        request,
        lambda: PlanService(context.service).preview(
            context.user_id, occurrence_id, body
        ),
    )


@router.post(
    "/occurrences/{occurrence_id}/fulfillment", response_model=FulfillmentReceipt
)
def fulfill(
    request: Request,
    context: Context,
    occurrence_id: str,
    body: Fulfillment,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: PlanService(context.service).fulfill(
            context.user_id, occurrence_id, body, _key(request, idempotency_key)
        ),
    )


@router.get("/occurrences/{occurrence_id}/candidates", response_model=Candidates)
def candidates(request: Request, context: Context, occurrence_id: str) -> Any:
    return call(
        request,
        lambda: PlanService(context.service).candidates(context.user_id, occurrence_id),
    )


@router.post("/occurrences/{occurrence_id}/link", response_model=LinkReceipt)
def link(
    request: Request,
    context: Context,
    occurrence_id: str,
    body: LinkWrite,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: PlanService(context.service).link(
            context.user_id, occurrence_id, body, _key(request, idempotency_key)
        ),
    )


@router.get("/expectations/{expectation_id}", response_model=Expectation)
def get_expectation(request: Request, context: Context, expectation_id: str) -> Any:
    return call(
        request, lambda: PlanService(context.service).get(context.user_id, expectation_id)
    )


@router.post("/budgets", response_model=BudgetReceipt, status_code=201)
def create_budget(
    request: Request, context: Context, body: BudgetCreate, idempotency_key: Key = None
) -> Any:
    return call(
        request,
        lambda: BudgetService(PlanService(context.service)).create(
            context.user_id, body, _key(request, idempotency_key)
        ),
    )


@router.patch("/budgets/{budget_id}", response_model=BudgetReceipt)
def edit_budget(
    request: Request,
    context: Context,
    budget_id: str,
    body: BudgetEdit,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: BudgetService(PlanService(context.service)).edit(
            context.user_id, budget_id, body, _key(request, idempotency_key)
        ),
    )


@router.get("/budgets/{budget_id}", response_model=BudgetProgress)
def get_budget(request: Request, context: Context, budget_id: str) -> Any:
    return call(
        request,
        lambda: BudgetService(PlanService(context.service)).get(
            context.user_id, budget_id
        ),
    )


@router.post("/goals", response_model=GoalReceipt)
def create_goal(
    request: Request, context: Context, body: GoalCreate, idempotency_key: Key = None
) -> Any:
    return call(
        request,
        lambda: GoalService(PlanService(context.service)).create(
            context.user_id, body, _key(request, idempotency_key)
        ),
    )


@router.put("/goals/allocations", response_model=AllocationReceipt)
def allocate_goals(
    request: Request, context: Context, body: AllocationWrite, idempotency_key: Key = None
) -> Any:
    return call(
        request,
        lambda: GoalService(PlanService(context.service)).allocate(
            context.user_id, body, _key(request, idempotency_key)
        ),
    )


@router.get("/goals/{goal_id}", response_model=GoalProgress)
def get_goal(request: Request, context: Context, goal_id: str) -> Any:
    return call(
        request,
        lambda: GoalService(PlanService(context.service)).get(context.user_id, goal_id),
    )


@router.patch("/goals/{goal_id}", response_model=GoalReceipt)
def edit_goal(
    request: Request,
    context: Context,
    goal_id: str,
    body: GoalEdit,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: GoalService(PlanService(context.service)).edit(
            context.user_id, goal_id, body, _key(request, idempotency_key)
        ),
    )


@router.get("/goals/{goal_id}/contributions/candidates", response_model=Candidates)
def goal_candidates(request: Request, context: Context, goal_id: str) -> Any:
    return call(
        request,
        lambda: GoalService(PlanService(context.service)).candidates(
            context.user_id, goal_id
        ),
    )


@router.post("/goals/{goal_id}/contributions/link", response_model=GoalReceipt)
def link_goal(
    request: Request,
    context: Context,
    goal_id: str,
    body: ContributionLink,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: GoalService(PlanService(context.service)).link(
            context.user_id, goal_id, body, _key(request, idempotency_key)
        ),
    )


@router.post("/goals/{goal_id}/contributions/preview", response_model=ContributionPreview)
def preview_goal(
    request: Request, context: Context, goal_id: str, body: ContributionRecord
) -> Any:
    return call(
        request,
        lambda: GoalService(PlanService(context.service)).preview(
            context.user_id, goal_id, body
        ),
    )


@router.post("/goals/{goal_id}/contributions", response_model=ContributionReceipt)
def record_goal(
    request: Request,
    context: Context,
    goal_id: str,
    body: ContributionRecord,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: GoalService(PlanService(context.service)).record(
            context.user_id, goal_id, body, _key(request, idempotency_key)
        ),
    )


@router.post(
    "/goals/{goal_id}/contributions/{claim_id}/release", response_model=GoalReceipt
)
def release_goal(
    request: Request,
    context: Context,
    goal_id: str,
    claim_id: str,
    body: ContributionRelease,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: GoalService(PlanService(context.service)).release(
            context.user_id, goal_id, claim_id, body, _key(request, idempotency_key)
        ),
    )
