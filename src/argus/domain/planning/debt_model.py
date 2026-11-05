"""Stable debt plans and schedule cutovers preserve accepted payment history."""

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

from argus.domain.planning import claims, goal_model, model
from argus.domain.planning.debt_schemas import DebtCreate, DebtEdit
from argus.domain.planning.recurrence import dates
from argus.domain.planning.schemas import Schedule
from argus.domain.recording.currency import (
    currency_exponent,
    format_minor_units,
    parse_minor_units,
)
from argus.domain.recording.errors import AccountNotFound, StaleVersion
from argus.domain.recording.repository import StoredAccount


def get(state: dict[str, Any], did: str, version: int | None = None) -> dict[str, Any]:
    item: dict[str, Any] | None = state["debts"].get(goal_model.identifier(did))
    if item is None:
        raise AccountNotFound()
    if version is not None and item["version"] != version:
        raise StaleVersion()
    return item


def eligible(item: dict[str, Any], accounts: list[StoredAccount]) -> bool:
    debt = next(
        (s.account for s in accounts if s.account.id == item["debt_account_id"]), None
    )
    source = next(
        (
            s.account
            for s in accounts
            if s.account.id == item["segments"][-1]["source_account_id"]
        ),
        None,
    )
    return bool(
        debt
        and source
        and debt.type in {"credit_card", "other_debt"}
        and source.type in {"cash", "checking", "savings"}
        and debt.currency == source.currency == item["currency"]
        and not debt.archived
        and not source.archived
    )


def setup(item: dict[str, Any], accounts: list[StoredAccount]) -> None:
    if not eligible(item, accounts):
        model.fail(
            "debt_setup_invalid",
            "Choose an active debt and a funding account in the same currency.",
        )
    terms = item["assumptions"]
    if terms and parse_minor_units(terms["recurring_fees"], item["currency"]) < 0:
        model.fail(
            "debt_fees_invalid",
            "Enter nonnegative recurring fees, including explicit zero.",
        )


def active_unique(state: dict[str, Any], item: dict[str, Any]) -> None:
    if not item["archived"] and any(
        d["id"] != item["id"]
        and not d["archived"]
        and d["debt_account_id"] == item["debt_account_id"]
        for d in state["debts"].values()
    ):
        model.fail("debt_plan_exists", "Open the active plan for this debt.")


def segment(source: str, amount: int, schedule: Schedule) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "source_account_id": source,
        "amount_minor": amount,
        "schedule": schedule.model_dump(mode="json"),
        "until": None,
    }


def create(
    body: DebtCreate, accounts: list[StoredAccount], state: dict[str, Any]
) -> dict[str, Any]:
    debt = next(
        (s.account for s in accounts if s.account.id == str(body.debt_account_id)), None
    )
    if debt is None:
        raise AccountNotFound()
    item = {
        "id": str(uuid4()),
        "version": 1,
        "name": body.name,
        "debt_account_id": debt.id,
        "currency": debt.currency,
        "archived": False,
        "assumptions": body.assumptions.model_dump(mode="json")
        if body.assumptions
        else None,
        "segments": [
            segment(
                str(body.source_account_id),
                model.positive(body.amount, debt.currency),
                body.schedule,
            )
        ],
    }
    setup(item, accounts)
    active_unique(state, item)
    return item


def earliest(item: dict[str, Any], state: dict[str, Any], today: date) -> date:
    return max(
        [
            today,
            *[
                date.fromisoformat(link["snapshot"]["due_date"]) + timedelta(days=1)
                for key, link in claims.protected_links(state).items()
                if link.get("debt_plan_id") == item["id"]
                and claims.occurrence_id(key, link)
            ],
        ]
    )


def edit(
    item: dict[str, Any],
    body: DebtEdit,
    accounts: list[StoredAccount],
    state: dict[str, Any],
    today: date,
) -> None:
    if body.expected_version != item["version"]:
        raise StaleVersion()
    if body.name is not None:
        if not body.name.strip():
            model.fail("title_invalid", "Enter a name.")
        item["name"] = body.name.strip()
    if body.archived is not None:
        item["archived"] = body.archived
    if "assumptions" in body.model_fields_set:
        item["assumptions"] = (
            body.assumptions.model_dump(mode="json") if body.assumptions else None
        )
    if body.model_fields_set & {"source_account_id", "amount", "schedule"}:
        cutover = body.effective_date or earliest(item, state, today)
        if cutover < earliest(item, state, today):
            raise model.UnsafeCutover(earliest(item, state, today))
        previous = item["segments"][-1]
        schedule = body.schedule or Schedule.model_validate(previous["schedule"])
        if schedule.start_date < cutover:
            if body.schedule:
                raise model.UnsafeCutover(cutover)
            upcoming = [
                d for d in dates(schedule, cutover + timedelta(days=3660)) if d >= cutover
            ]
            if not upcoming:
                model.fail("schedule_finished", "Choose a future payment schedule.")
            schedule = schedule.model_copy(
                update={
                    "start_date": upcoming[0],
                    "month_days": schedule.month_days
                    or (
                        [schedule.start_date.day] if schedule.cadence == "monthly" else []
                    ),
                }
            )
        source = (
            str(body.source_account_id)
            if body.source_account_id
            else previous["source_account_id"]
        )
        amount = (
            model.positive(body.amount, item["currency"])
            if body.amount is not None
            else previous["amount_minor"]
        )
        boundary = (cutover - timedelta(days=1)).isoformat()
        for part in item["segments"]:
            part["until"] = min(part["until"], boundary) if part["until"] else boundary
        item["segments"].append(segment(source, amount, schedule))
    active_unique(state, item)
    if not item["archived"]:
        setup(item, accounts)
    item["version"] += 1


def definition(
    item: dict[str, Any], state: dict[str, Any], today: date
) -> dict[str, Any]:
    part = item["segments"][-1]
    return {key: value for key, value in item.items() if key != "segments"} | {
        "source_account_id": part["source_account_id"],
        "amount_minor": part["amount_minor"],
        "amount": format_minor_units(part["amount_minor"], item["currency"]),
        "schedule": part["schedule"],
        "currency_fraction_digits": currency_exponent(item["currency"]),
        "earliest_effective_date": earliest(item, state, today).isoformat(),
    }


def occurrences(state: dict[str, Any], until: date) -> dict[str, dict[str, Any]]:
    result = {}
    for item in state["debts"].values():
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
                    "debt_plan_id": item["id"],
                    "expectation_id": None,
                    "expectation_version": item["version"],
                    "kind": "debt_payment",
                    "title": item["name"],
                    "currency": item["currency"],
                    "currency_fraction_digits": currency_exponent(item["currency"]),
                    "amount_minor": part["amount_minor"],
                    "amount": format_minor_units(part["amount_minor"], item["currency"]),
                    "account_id": part["source_account_id"],
                    "source_account_id": part["source_account_id"],
                    "destination_account_id": item["debt_account_id"],
                    "due_date": due.isoformat(),
                }
    for key, link in claims.protected_links(state).items():
        claimed_id = claims.occurrence_id(key, link)
        if link.get("debt_plan_id") and claimed_id:
            result[claimed_id] = link["snapshot"] | {
                "expectation_version": state["debts"][link["debt_plan_id"]]["version"]
            }
    return result


def find_occurrence(
    state: dict[str, Any], did: str, oid: str, today: date
) -> dict[str, Any]:
    horizon = max(
        [
            today + timedelta(days=3660),
            *[
                date.fromisoformat(p["schedule"]["start_date"]) + timedelta(days=3660)
                for p in state["debts"][did]["segments"]
            ],
        ]
    )
    found = occurrences(state, horizon).get(oid)
    if not found or found["debt_plan_id"] != did:
        raise AccountNotFound()
    return found


def matches(actual: dict[str, Any], source: str, destination: str, currency: str) -> bool:
    return (
        actual["kind"] in {"card_payment", "debt_payment"}
        and actual["currency"] == currency
        and {(leg["role"], leg["account_id"]) for leg in actual["legs"]}
        == {("source", source), ("destination", destination)}
    )
