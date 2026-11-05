"""Shared summaries reduce only consented facts using canonical Plan owners."""

from datetime import date

from argus.domain.planning import budgets
from argus.domain.recording.schemas import account_response


def selected_budget_facts(b, body, claimed, actual):
    selected = {}
    claim_ids = {
        leg["activity_id"]
        for leg in claimed.values()
        if not leg["released"] and leg["purpose"] == "spending"
    }
    for item in actual.values():
        original_item = actual.get(item["purchase_activity_id"]) or actual.get(
            item["reversal_of_activity_id"]
        )
        public_scope = (
            b["publish_budget_scope"]
            and (original_item or item)["legs"][0]["account_id"] in body["account_ids"]
        )
        explicit = (
            item["activity_id"] in claim_ids
            or original_item is not None
            and original_item["activity_id"] in claim_ids
        )
        if public_scope or explicit:
            selected[item["activity_id"]] = item
    return selected


def summary(
    b, body, contributions, allocations, actual, occurrences, access, canonical, today
):
    relevant = [
        v
        for v in contributions
        if v["status"] != "released" and v["purpose"] != "funding"
    ]
    known = all(
        v["applied_minor"] is not None
        for v in relevant + [{"applied_minor": a["supported_minor"]} for a in allocations]
    )
    applied = (
        sum(int(v["applied_minor"]) for v in relevant)
        + sum(int(a["supported_minor"]) for a in allocations)
        if known
        else None
    )
    gross = sum(
        int(v["amount_minor"])
        for v in contributions
        if v["amount_minor"] is not None and v["status"] != "released"
    )
    archived = bool(b["departed_at"] or body["archived"])
    result = dict(
        actual_minor=str(gross)
        if all(
            v["amount_minor"] is not None
            for v in contributions
            if v["status"] != "released"
        )
        else None,
        applied_minor=str(applied) if applied is not None else None,
        remaining_minor=None,
        state="archived" if archived else "active" if known else "needs_review",
        debt_balance_minor=None,
        debt_state=None,
    )
    if b["kind"] == "budget":
        if not known:
            return result | dict(
                actual_minor=None,
                gross_minor=None,
                refunds_minor=None,
                spent_minor=None,
                over_budget=None,
            )
        selected = selected_budget_facts(b, body, b["_links"], actual)
        scope_ids = set(body["account_ids"]) | {
            item["legs"][0]["account_id"] for item in selected.values()
        }
        progress = budgets.progress(
            body | {"account_ids": sorted(scope_ids)},
            list(selected.values()),
            "America/Santo_Domingo",
        )
        result |= dict(
            actual_minor=progress["spent_minor"],
            applied_minor=progress["spent_minor"],
            remaining_minor=progress["remaining_minor"],
            gross_minor=progress["gross_purchases_minor"],
            refunds_minor=progress["refunds_minor"],
            spent_minor=progress["spent_minor"],
            over_budget=int(progress["over_budget_minor"]) > 0,
        )
    elif b["kind"] == "goal":
        future = [r for r in occurrences if date.fromisoformat(r["date"]) >= today]
        planned = (
            0
            if archived
            else (
                sum(int(r["remaining_minor"]) for r in future)
                if all(r["remaining_minor"] is not None for r in future)
                else None
            )
        )
        result |= dict(
            remaining_minor=str(max(0, body["target_minor"] - applied))
            if applied is not None
            else None,
            planned_minor=str(planned) if planned is not None else None,
            projected_minor=str(applied + planned)
            if applied is not None and planned is not None
            else None,
        )
        if not archived and applied is not None and applied >= body["target_minor"]:
            result["state"] = "reached"
    else:
        result["remaining_minor"] = (
            str(sum(int(r["remaining_minor"]) for r in occurrences))
            if all(r["remaining_minor"] is not None for r in occurrences)
            else None
        )
        if b["kind"] == "debt":
            aid = body["debt_account_id"]
            if aid in access:
                stored = next((s for s in canonical.records if s.account.id == aid), None)
                balance = account_response(stored).balance if stored else None
                result["debt_balance_minor"] = (
                    str(balance.amount_minor)
                    if balance and balance.amount_minor is not None
                    else None
                )
                result["debt_state"] = (
                    "recorded_clear"
                    if balance and balance.amount_minor == 0
                    else "active"
                    if balance and balance.amount_minor is not None
                    else "unknown"
                )
            else:
                result["debt_state"] = "unknown"
                if not archived:
                    result["state"] = "unknown"
    return result
