"""Shared commands reuse each original Plan model and its recurrence identity."""

from datetime import date, timedelta
from uuid import uuid4

from argus.domain.planning import budgets, debt_model, goal_model, model, storage
from argus.domain.planning.budget_schemas import BudgetCreate
from argus.domain.planning.debt_schemas import DebtCreate, DebtEdit
from argus.domain.planning.goal_schemas import GoalCreate, GoalEdit
from argus.domain.planning.schemas import ExpectationCreate, ExpectationEdit
from argus.domain.recording.currency import normalize_currency, parse_minor_units

from . import planning_store as store


def create(kind, request, accounts, state):
    fields = request.model_dump(mode="json", exclude={"kind"})
    if kind == "budget":
        body = BudgetCreate.model_validate(fields)
        item = body.model_dump(mode="json", exclude={"limit"}) | dict(
            id=str(uuid4()), version=1, archived=False
        )
        item["currency"] = normalize_currency(body.currency)
        item["limit_minor"] = model.positive(body.limit, item["currency"])
        budgets.validate(item, accounts, state)
        return item
    if kind == "bill":
        return model.create(
            ExpectationCreate.model_validate(fields | {"kind": "bill"}), accounts
        )
    if kind == "goal":
        return goal_model.create(GoalCreate.model_validate(fields), accounts)
    return debt_model.create(DebtCreate.model_validate(fields), accounts, state)


def edit(kind, item, patch, accounts, state, today):
    fields = patch.model_dump(mode="json", exclude_unset=True)
    allowed = {"name", "archived"}
    allowed |= (
        {"month", "category_ids", "include_uncategorized", "amount"}
        if kind == "budget"
        else {"schedule", "effective_date", "amount"}
    )
    if kind == "goal":
        allowed |= {"target_date", "planned_contribution_amount"}
    if fields.keys() - allowed:
        model.fail("plan_edit_invalid", "Review fields for this plan kind.")
    version = item["version"]
    if kind == "budget":
        amount = fields.pop("amount", None)
        item.update(fields)
        if amount is not None:
            item["limit_minor"] = model.positive(amount, item["currency"])
        budgets.validate(item, accounts, state)
        item["version"] += 1
    elif kind == "bill":
        if "name" in fields:
            fields["title"] = fields.pop("name")
        model.edit(
            item,
            ExpectationEdit(expected_version=version, **fields),
            accounts,
            state["links"],
            today,
        )
    elif kind == "goal":
        if "amount" in fields:
            fields["target"] = fields.pop("amount")
        contribution_amount = fields.pop("planned_contribution_amount", None)
        if (
            "planned_contribution_amount" in patch.model_fields_set
            and contribution_amount is None
        ):
            model.fail("amount_invalid", "Enter a planned contribution amount.")
        if "schedule" in fields:
            planned = goal_model.current_plan(item)
            if planned is None:
                model.fail(
                    "goal_setup_required",
                    "Configure the original contribution plan first.",
                )
            fields["contribution_plan"] = planned | {
                "schedule": fields.pop("schedule", planned["schedule"]),
                "amount": contribution_amount
                if contribution_amount is not None
                else planned["amount"],
            }
            contribution_amount = None
        goal_model.edit(
            item,
            GoalEdit(expected_version=version, **fields),
            accounts,
            state,
            today,
            contribution_amount=contribution_amount,
        )
    else:
        debt_model.edit(
            item, DebtEdit(expected_version=version, **fields), accounts, state, today
        )


def occurrence_rows(kind, body, links, end):
    if kind == "budget":
        return {}
    state = storage.empty()
    state[store.table(kind)[1]][body["id"]] = body | {"archived": False}
    state["links"] = links
    resolver = {
        "bill": model.occurrences,
        "goal": goal_model.occurrences,
        "debt": debt_model.occurrences,
    }[kind]
    return resolver(state, end)


def occurrence(kind, body, links, identifier, today):
    ends = [
        date.fromisoformat(s["schedule"]["start_date"]) + timedelta(days=3660)
        for s in body.get("segments", [])
    ]
    found = occurrence_rows(
        kind, body, links, max([today + timedelta(days=366), *ends])
    ).get(identifier)
    if found is None:
        model.fail("plan_occurrence_invalid", "Choose a current occurrence of this plan.")
    return found


def responsibility_rows(c, b, body, proposed, people, today):
    consent = {p["membership_id"] for p in store.participants(c, b, people)}
    result, seen = [], set()
    for row in proposed:
        mid = str(row.membership_id)
        if mid not in consent:
            model.fail(
                "plan_responsibility_invalid", "Choose a current plan participant."
            )
        if row.period is not None:
            if b["kind"] != "budget" or row.period != body["month"]:
                model.fail("plan_period_invalid", "Choose this budget's month.")
        if row.occurrence_id is not None:
            occurrence(b["kind"], body, {}, str(row.occurrence_id), today)
        if row.schedule_id is not None and str(row.schedule_id) not in {
            s["id"] for s in body.get("segments", [])
        }:
            model.fail(
                "plan_schedule_invalid", "Choose a canonical schedule of this plan."
            )
        resolved_occurrence = str(row.occurrence_id) if row.occurrence_id else None
        agreed_date = row.agreed_date
        if agreed_date is not None and b["kind"] in {"bill", "debt"}:
            matching = [
                oid
                for oid, item in occurrence_rows(b["kind"], body, {}, agreed_date).items()
                if item["due_date"] == agreed_date.isoformat()
            ]
            if len(matching) != 1:
                model.fail(
                    "plan_occurrence_invalid",
                    "Choose the due date of this plan's occurrence.",
                )
            resolved_occurrence, agreed_date = matching[0], None
        amount = (
            None
            if row.amount is None
            else parse_minor_units(row.amount, body["currency"])
        )
        if amount is not None and amount < 0:
            model.fail(
                "plan_responsibility_negative", "Enter a nonnegative planned amount."
            )
        fields = (
            mid,
            amount,
            row.period,
            resolved_occurrence,
            str(row.schedule_id) if row.schedule_id else None,
            agreed_date,
        )
        identity = (mid, *fields[2:])
        if identity in seen:
            model.fail("plan_responsibility_duplicate", "Set each person's period once.")
        seen.add(identity)
        result.append(fields)
    return result
