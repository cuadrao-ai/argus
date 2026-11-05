"""Budget definitions own limits; Recording owns every actual amount."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from argus.domain.planning import debt_projection, goal_projection, model, storage
from argus.domain.planning.budget_schemas import BudgetCreate, BudgetEdit
from argus.domain.recording.currency import (
    currency_exponent,
    format_minor_units,
    normalize_currency,
)
from argus.domain.recording.errors import (
    AccountNotFound,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.loop_reads import home_response
from argus.domain.recording.loop_schemas import CATEGORY_IDS
from argus.domain.recording.money_home import period
from argus.domain.recording.money_reads import current_activities
from argus.domain.recording.money_schemas import ELIGIBILITY
from argus.domain.recording.repository import StoredAccount
from argus.domain.recording.spending import spending


class BudgetScopeConflict(RecordingInputError):
    def __init__(self) -> None:
        super().__init__(
            "budget_scope_conflict",
            "An active budget already covers this scope and month.",
        )


def definition(item: dict[str, Any]) -> dict[str, Any]:
    return item | {
        "limit": format_minor_units(item["limit_minor"], item["currency"]),
        "currency_fraction_digits": currency_exponent(item["currency"]),
    }


def scope(item: dict[str, Any]) -> tuple:
    return (
        item["month"],
        item["currency"],
        tuple(item["account_ids"]),
        tuple(item["category_ids"]),
        item["include_uncategorized"],
    )


def validate(
    item: dict[str, Any], accounts: list[StoredAccount], state: dict[str, Any]
) -> None:
    item["name"] = item["name"].strip()
    if not item["name"]:
        model.fail("title_invalid", "Enter a name.")
    period(item["month"], state["selection"]["time_zone"])
    by_id = {a.account.id: a.account for a in accounts}
    for key in ("account_ids", "category_ids"):
        if len(item[key]) != len(set(item[key])):
            model.fail("budget_scope_duplicate", "Choose each scope member once.")
        item[key] = sorted(item[key])
    if not item["category_ids"] and not item["include_uncategorized"]:
        model.fail("budget_category_required", "Choose a category or Uncategorized.")
    if any(category not in CATEGORY_IDS for category in item["category_ids"]):
        model.fail("category_invalid", "Choose a supported expense category.")
    for aid in item["account_ids"]:
        account = by_id.get(aid)
        if account is None:
            raise AccountNotFound()
        if item["archived"]:
            continue
        if account.type not in ELIGIBILITY["expense"]:
            model.fail("account_ineligible", "Choose an account that supports expenses.")
        if account.currency != item["currency"]:
            model.fail("currency_mismatch", "Choose accounts in the budget currency.")
    if not item["archived"] and any(
        other["id"] != item["id"]
        and not other["archived"]
        and scope(other) == scope(item)
        for other in state["budgets"].values()
    ):
        raise BudgetScopeConflict()


def progress(
    item: dict[str, Any], activities: list[dict[str, Any]], zone: str
) -> dict[str, Any]:
    interval = period(item["month"], zone)
    actual = spending(
        activities,
        currency=item["currency"],
        start=interval["start_at"],
        end=interval["end_at_exclusive"],
        account_ids=set(item["account_ids"]),
        category_ids=set(item["category_ids"]),
        include_uncategorized=item["include_uncategorized"],
    )
    remaining = item["limit_minor"] - actual.net
    return {
        "budget": definition(item),
        "period": interval,
        "gross_purchases_minor": str(actual.purchases),
        "refunds_minor": str(actual.refunds),
        "spent_minor": str(actual.net),
        "remaining_minor": str(remaining),
        "over_budget_minor": str(max(0, -remaining)),
        "contributors": actual.contributors,
    }


def all_progress(
    state: dict[str, Any], accounts: list[StoredAccount]
) -> list[dict[str, Any]]:
    actual = current_activities(accounts)
    return [
        progress(item, actual, state["selection"]["time_zone"])
        for item in sorted(
            state["budgets"].values(),
            key=lambda item: (item["month"], item["name"], item["id"]),
        )
    ]


class BudgetService:
    def __init__(self, planner: Any) -> None:
        self.planner = planner

    def create(self, owner: str, body: BudgetCreate, key: str) -> dict[str, Any]:
        def action(state: dict[str, Any], accounts: list[StoredAccount]) -> tuple:
            item = body.model_dump(mode="json", exclude={"limit"}) | {
                "id": str(uuid4()),
                "version": 1,
                "archived": False,
            }
            item["currency"] = normalize_currency(body.currency)
            item["limit_minor"] = model.positive(body.limit, item["currency"])
            validate(item, accounts, state)
            state["budgets"][item["id"]] = item
            return {"budget": definition(item)}, None

        return self.planner._write(owner, "budget.create", body, key, action)

    def edit(
        self, owner: str, identifier: str, body: BudgetEdit, key: str
    ) -> dict[str, Any]:
        identifier = self.identifier(identifier)

        def action(state: dict[str, Any], accounts: list[StoredAccount]) -> tuple:
            previous = state["budgets"].get(identifier)
            if previous is None:
                raise AccountNotFound()
            if previous["version"] != body.expected_version:
                raise StaleVersion()
            item = previous | body.model_dump(
                mode="json", exclude_unset=True, exclude={"limit", "expected_version"}
            )
            item["currency"] = normalize_currency(item["currency"])
            if item["currency"] != previous["currency"] and body.limit is None:
                model.fail(
                    "budget_limit_required", "Review the limit in the new currency."
                )
            if body.limit is not None:
                item["limit_minor"] = model.positive(body.limit, item["currency"])
            validate(item, accounts, state)
            item["version"] += 1
            state["budgets"][identifier] = item
            return {"budget": definition(item)}, None

        return self.planner._write(owner, "budget.edit:" + identifier, body, key, action)

    @staticmethod
    def identifier(raw: str) -> str:
        try:
            return str(UUID(raw))
        except ValueError:
            raise AccountNotFound() from None

    def get(self, owner: str, identifier: str) -> dict[str, Any]:
        identifier = self.identifier(identifier)
        state, accounts = storage.read(self.planner.repository, owner)
        item = state["budgets"].get(identifier)
        if item is None:
            raise AccountNotFound()
        return progress(
            item, current_activities(accounts), state["selection"]["time_zone"]
        )

    def home(self, owner: str, month: str | None, zone: str | None) -> dict[str, Any]:
        state, accounts = storage.read(self.planner.repository, owner)
        return home_response(
            accounts,
            month,
            zone or state["selection"]["time_zone"],
            self.planner.accounts._clock(),
        ) | {
            "debts": [
                p
                for p in debt_projection.project(
                    state,
                    accounts,
                    self.planner.today(state),
                    self.planner.today(state) + timedelta(days=30),
                )
                if not p["debt"]["archived"]
            ],
            "goals": [
                p
                for p in goal_projection.project(
                    state,
                    accounts,
                    self.planner.today(state),
                    self.planner.today(state) + timedelta(days=30),
                )[0]
                if not p["goal"]["archived"]
            ],
            "budgets": [
                p for p in all_progress(state, accounts) if not p["budget"]["archived"]
            ],
        }
