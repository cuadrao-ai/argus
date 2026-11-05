"""Goal definitions and schedules own intentions, never account balances."""

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

from argus.domain.planning import claims, model
from argus.domain.planning.goal_schemas import GoalCreate, GoalEdit
from argus.domain.planning.recurrence import dates
from argus.domain.planning.schemas import Schedule
from argus.domain.recording.currency import (
    currency_exponent,
    format_minor_units,
    normalize_currency,
)
from argus.domain.recording.errors import AccountNotFound, StaleVersion
from argus.domain.recording.money_reads import activity_in_currency
from argus.domain.recording.repository import StoredAccount


def identifier(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise AccountNotFound() from None


def get(state: dict[str, Any], gid: str, version: int | None = None) -> dict[str, Any]:
    item = state["goals"].get(identifier(gid))
    if item is None:
        raise AccountNotFound()
    if version is not None and version != item["version"]:
        raise StaleVersion()
    return item


def earliest(item: dict[str, Any], state: dict[str, Any], today: date) -> date:
    return max(
        [
            today,
            *[
                date.fromisoformat(link["snapshot"]["due_date"]) + timedelta(days=1)
                for key, link in claims.protected_links(state).items()
                if link.get("goal_id") == item["id"] and claims.occurrence_id(key, link)
            ],
        ]
    )


def current_plan(item: dict[str, Any]) -> dict[str, Any] | None:
    active = next(
        (part for part in reversed(item["segments"]) if part["until"] is None), None
    )
    if active is None:
        return None
    return {
        "source_account_id": active["source_account_id"],
        "amount": format_minor_units(active["amount_minor"], item["currency"]),
        "schedule": active["schedule"],
    }


def setup(
    item: dict[str, Any], accounts: list[StoredAccount], plan: dict[str, Any] | None
) -> None:
    destination = item["destination_account_id"]
    model.cash_account(accounts, destination, item["currency"])
    if plan:
        if not destination or plan["source_account_id"] == destination:
            model.fail(
                "goal_setup_invalid", "Choose different funding and destination accounts."
            )
        model.cash_account(accounts, plan["source_account_id"], item["currency"])
        model.positive(plan["amount"], item["currency"])


def segment(item: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "source_account_id": plan["source_account_id"],
        "destination_account_id": item["destination_account_id"],
        "amount_minor": model.positive(plan["amount"], item["currency"]),
        "schedule": plan["schedule"],
        "until": None,
    }


def create(body: GoalCreate, accounts: list[StoredAccount]) -> dict[str, Any]:
    item = body.model_dump(mode="json", exclude={"target", "contribution_plan"}) | {
        "id": str(uuid4()),
        "version": 1,
        "archived": False,
        "allocations": [],
        "segments": [],
    }
    item["currency"] = normalize_currency(body.currency)
    item["target_minor"] = model.positive(body.target, item["currency"])
    plan = (
        body.contribution_plan.model_dump(mode="json") if body.contribution_plan else None
    )
    setup(item, accounts, plan)
    if plan:
        item["segments"].append(segment(item, plan))
    return item


def edit(
    item: dict[str, Any],
    body: GoalEdit,
    accounts: list[StoredAccount],
    state: dict[str, Any],
    today: date,
    *,
    contribution_amount: str | None = None,
) -> None:
    if body.expected_version != item["version"]:
        raise StaleVersion()
    if body.name is not None:
        if not body.name.strip():
            model.fail("title_invalid", "Enter a name.")
        item["name"] = body.name.strip()
    if body.target is not None:
        item["target_minor"] = model.positive(body.target, item["currency"])
    if "target_date" in body.model_fields_set:
        item["target_date"] = body.model_dump(mode="json")["target_date"]
    if body.archived is not None:
        item["archived"] = body.archived
    if contribution_amount is not None or body.model_fields_set & {
        "destination_account_id",
        "contribution_plan",
    }:
        cutover = body.effective_date or earliest(item, state, today)
        if cutover < earliest(item, state, today):
            raise model.UnsafeCutover(earliest(item, state, today))
        plan = current_plan(item)
        if "destination_account_id" in body.model_fields_set:
            item["destination_account_id"] = (
                str(body.destination_account_id) if body.destination_account_id else None
            )
        if "contribution_plan" in body.model_fields_set:
            plan = (
                body.contribution_plan.model_dump(mode="json")
                if body.contribution_plan
                else None
            )
        if contribution_amount is not None:
            if plan is None:
                model.fail(
                    "goal_setup_required",
                    "Configure the original contribution plan first.",
                )
            plan = plan | {"amount": contribution_amount}
        setup(item, accounts, plan)
        if plan:
            schedule = Schedule.model_validate(plan["schedule"])
            if schedule.start_date < cutover:
                if body.contribution_plan is not None:
                    raise model.UnsafeCutover(cutover)
                upcoming = [
                    d
                    for d in dates(schedule, schedule.start_date + timedelta(days=3660))
                    if d >= cutover
                ]
                if not upcoming:
                    model.fail(
                        "schedule_finished", "Choose a future contribution schedule."
                    )
                plan["schedule"] = schedule.model_copy(
                    update={
                        "start_date": upcoming[0],
                        "month_days": schedule.month_days
                        or (
                            [schedule.start_date.day]
                            if schedule.cadence == "monthly"
                            else []
                        ),
                    }
                ).model_dump(mode="json")
        for old in item["segments"]:
            boundary = (cutover - timedelta(days=1)).isoformat()
            old["until"] = min(old["until"], boundary) if old["until"] else boundary
        if plan:
            item["segments"].append(segment(item, plan))
    item.pop("contribution_plan", None)
    item["version"] += 1


def definition(
    item: dict[str, Any], state: dict[str, Any], today: date
) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in {"segments", "contribution_plan"}
    } | {
        "contribution_plan": current_plan(item),
        "target": format_minor_units(item["target_minor"], item["currency"]),
        "currency_fraction_digits": currency_exponent(item["currency"]),
        "earliest_effective_date": earliest(item, state, today).isoformat(),
    }


def occurrences(state: dict[str, Any], until: date) -> dict[str, dict[str, Any]]:
    result = {}
    for item in state["goals"].values():
        if item["archived"]:
            continue
        for part in item["segments"]:
            end = (
                min(until, date.fromisoformat(part["until"])) if part["until"] else until
            )
            for due in dates(Schedule.model_validate(part["schedule"]), end):
                oid = str(uuid5(UUID(item["id"]), part["id"] + ":" + due.isoformat()))
                result[oid] = {
                    "id": oid,
                    "goal_id": item["id"],
                    "expectation_id": None,
                    "expectation_version": item["version"],
                    "kind": "goal_transfer",
                    "title": item["name"],
                    "currency": item["currency"],
                    "currency_fraction_digits": currency_exponent(item["currency"]),
                    "amount_minor": part["amount_minor"],
                    "amount": format_minor_units(part["amount_minor"], item["currency"]),
                    "account_id": part["destination_account_id"],
                    "source_account_id": part["source_account_id"],
                    "destination_account_id": part["destination_account_id"],
                    "due_date": due.isoformat(),
                }
    for key, link in claims.protected_links(state).items():
        oid = claims.occurrence_id(key, link)
        if link.get("goal_id") and oid:
            result[oid] = link["snapshot"] | {
                "expectation_version": state["goals"][link["goal_id"]]["version"]
            }
    return result


def find_occurrence(
    state: dict[str, Any], gid: str, oid: str, today: date
) -> dict[str, Any]:
    ends = [
        date.fromisoformat(s["schedule"]["start_date"]) + timedelta(days=3660)
        for s in state["goals"][gid]["segments"]
    ]
    item = occurrences(state, max([today + timedelta(days=366), *ends])).get(oid)
    if item is None or item["goal_id"] != gid:
        raise AccountNotFound()
    return item


def transfer_matches(
    actual: dict[str, Any], source: str, destination: str, currency: str
) -> bool:
    return (
        actual["kind"] == "transfer"
        and activity_in_currency(actual, currency)
        and {(leg["role"], leg["account_id"]) for leg in actual["legs"]}
        == {("source", source), ("destination", destination)}
    )
