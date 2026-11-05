"""Debt progress derives from current Recording activity and dated intentions."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from argus.domain.finance import tvm
from argus.domain.finance.outcomes import NoSolution
from argus.domain.planning import claims, debt_model, goal_projection, shared_claims
from argus.domain.planning.recurrence import dates
from argus.domain.planning.schemas import Schedule
from argus.domain.recording.currency import parse_minor_units
from argus.domain.recording.money_reads import current_activities
from argus.domain.recording.payments import net_total
from argus.domain.recording.schemas import account_response


def payments(
    state: dict[str, Any], did: str, actual: dict[str, Any]
) -> list[dict[str, Any]]:
    item = state["debts"][did]
    rows = []
    for cid, link in state["links"].items():
        if link.get("debt_plan_id") != did:
            continue
        entry = actual.get(link["activity_id"])
        expected = (
            link["snapshot"] if claims.occurrence_id(cid, link) else link["attribution"]
        )
        valid = entry is not None and debt_model.matches(
            entry,
            expected["source_account_id"],
            item["debt_account_id"],
            item["currency"],
        )
        rows.append(
            {
                "id": cid,
                "activity_id": link["activity_id"],
                "occurrence_id": claims.occurrence_id(cid, link),
                "status": "current" if valid else "needs_review",
                "net_paid_minor": net_total(entry, list(actual.values()))
                if valid and entry is not None
                else None,
                "activity": entry,
            }
        )
    return rows


def occurrence(
    item: dict[str, Any], state: dict[str, Any], actual: dict[str, Any], start: date
) -> dict[str, Any]:
    linked = [
        p
        for p in payments(state, item["debt_plan_id"], actual)
        if p["occurrence_id"] == item["id"]
    ]
    invalid = any(p["status"] == "needs_review" for p in linked)
    paid = sum(p["net_paid_minor"] for p in linked if p["net_paid_minor"] is not None)
    shared = shared_claims.for_occurrence(state, item["id"])
    if shared is not None:
        invalid = invalid or shared["amount"] is None
        paid += shared["amount"] or 0
    remaining = max(0, item["amount_minor"] - paid)
    due = date.fromisoformat(item["due_date"])
    return item | {
        "projection_date": max(start, due).isoformat(),
        "status": "needs_review"
        if invalid
        else "fulfilled"
        if remaining == 0
        else "planned",
        "activity_id": linked[0]["activity_id"] if len(linked) == 1 else None,
        "activity_revision": linked[0]["activity"]["revision"]
        if len(linked) == 1 and linked[0]["activity"]
        else None,
        "exclusion_reason": "plan_archived"
        if state["debts"][item["debt_plan_id"]]["archived"]
        else "link_needs_review"
        if invalid
        else "account_not_selected"
        if item["source_account_id"] not in state["selection"]["account_ids"]
        else None,
        "overdue": due < start and remaining > 0,
        "paid_minor": paid,
        "remaining_minor": remaining,
    }


def payoff(
    item: dict[str, Any],
    balance: Any,
    rows: list[dict[str, Any]],
    today: date,
    account_type: str,
) -> dict[str, Any]:
    assumptions = item["assumptions"]

    def unavailable(reason: str) -> dict[str, Any]:
        return {"state": "unavailable", "reason": reason, "assumptions": assumptions}

    if balance.amount_minor is None:
        return unavailable("balance_unknown")
    if balance.amount_minor >= 0:
        return unavailable("recorded_clear")
    if item["archived"]:
        return unavailable("archived")
    if assumptions is None:
        return unavailable("terms_missing")
    part = item["segments"][-1]
    schedule = Schedule.model_validate(part["schedule"])
    if schedule.cadence != "monthly" or len(schedule.month_days) > 1:
        return unavailable("cadence_unsupported")
    if any(r["overdue"] or r["status"] == "needs_review" for r in rows):
        return unavailable("payments_need_review")
    future = [d for d in dates(schedule, today + timedelta(days=36600)) if d >= today]
    boundary = date.fromisoformat(assumptions["first_period_start"])
    import calendar

    month = boundary.month % 12 + 1
    year = boundary.year + (boundary.month == 12)
    expected = date(year, month, min(boundary.day, calendar.monthrange(year, month)[1]))
    if (
        not future
        or expected != future[0]
        or boundary > today
        or balance.as_of is None
        or balance.as_of.date() != boundary
    ):
        return unavailable("period_boundary_required")
    fee = parse_minor_units(assumptions["recurring_fees"], item["currency"])
    payment = part["amount_minor"] - fee
    rate = float(Decimal(assumptions["annual_rate_percent"]) / Decimal(1200))
    principal = -balance.amount_minor
    count = tvm.periods(principal, -payment, 0, rate)
    if isinstance(count, NoSolution) or payment <= 0:
        return unavailable("payment_insufficient")
    interest_total = 0
    for i, due in enumerate(future, 1):
        row = tvm.amortization_schedule(principal, rate, payment, 1)[0]
        interest = int(
            Decimal(str(row.interest)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        )
        if payment <= interest:
            return unavailable("payment_insufficient")
        principal = max(0, principal + interest - payment)
        interest_total += interest
        if principal == 0:
            return {
                "state": "conditional",
                "payoff_date": due.isoformat(),
                "payments": i,
                "total_interest_minor": str(interest_total),
                "total_fees_minor": str(i * fee),
                "assumptions": assumptions,
            }
    return unavailable("schedule_insufficient")


def project(
    state: dict[str, Any], accounts: list[Any], today: date, end: date
) -> list[dict[str, Any]]:
    actual = {a["activity_id"]: a for a in current_activities(accounts)}
    rows = [
        occurrence(r, state, actual, today)
        for r in debt_model.occurrences(state, end).values()
    ]
    by_id = {s.account.id: s for s in accounts}
    result = []
    pools = {
        p["account_id"]: p
        for p in goal_projection.project(state, accounts, today, end)[1]
    }
    for item in state["debts"].values():
        stored = by_id[item["debt_account_id"]]
        balance = account_response(stored).balance
        entries = payments(state, item["id"], actual)
        scheduled = [r for r in rows if r["debt_plan_id"] == item["id"]]
        state_name = (
            "needs_review"
            if not debt_model.eligible(item, accounts)
            or any(p["status"] == "needs_review" for p in entries)
            else "unknown"
            if balance.amount_minor is None
            else "recorded_clear"
            if balance.amount_minor >= 0
            else "active"
        )
        result.append(
            {
                "debt": debt_model.definition(item, state, today),
                "balance": balance.model_dump(mode="json"),
                "funding_pool": pools.get(item["segments"][-1]["source_account_id"]),
                "state": state_name,
                "payoff": payoff(item, balance, scheduled, today, stored.account.type),
                "payments": entries,
                "occurrences": scheduled,
            }
        )
    return result
