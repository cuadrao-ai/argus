"""Bounded wire projections derived from canonical financial records."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from argus.domain.recording.currency import currency_exponent, format_minor_units
from argus.domain.recording.errors import (
    AccountNotFound,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.loop import CheckRecord, ExpenseRecord, position, residuals
from argus.domain.recording.loop_storage import OperationResult
from argus.domain.recording.repository import StoredAccount
from argus.domain.recording.schemas import account_response


def activity_response(
    stored: StoredAccount, record: ExpenseRecord, revision: int | None = None
) -> dict[str, Any]:
    r = next((r for r in record.revisions if r.revision == revision), record.current)
    choices = {}
    for link in sorted(stored.coverage, key=lambda c: c.observation_revision):
        if link.activity_id == record.id and link.activity_revision == r.revision:
            choices[link.observation_id] = link.included
    return {
        "record_id": record.id,
        "revision": r.revision,
        "kind": r.kind,
        "activity_id": r.activity_id or record.id,
        "role": r.role,
        "active": r.active,
        "amount_minor": r.amount_minor,
        "amount": format_minor_units(r.amount_minor, stored.account.currency),
        "balance_movement_minor": r.movement_minor,
        "occurred_at": r.occurred_at,
        "time_zone": r.time_zone,
        "note": r.note,
        "category_id": r.category_id,
        "reason": r.reason,
        "recorded_at": r.recorded_at,
        "recorded_by": r.recorded_by,
        "coverage": [
            {"observation_id": key, "included": value}
            for key, value in sorted(choices.items())
        ],
    }


def check_response(stored: StoredAccount, check: CheckRecord) -> dict[str, Any]:
    gaps = residuals(stored.opening, stored.checks, stored.expenses, stored.coverage)
    return {
        "record_id": check.id,
        "revision": check.revision,
        "kind": check.kind,
        "as_of": check.as_of,
        "time_zone": check.time_zone,
        "source": check.source,
        "expected_amount_minor": check.expected_minor,
        "observed_amount_minor": check.amount_minor,
        "difference_minor": check.difference_minor,
        "unexplained_minor": gaps[check.id],
        "note": check.note,
        "recorded_at": check.recorded_at,
        "recorded_by": check.recorded_by,
    }


def operation_response(result: OperationResult) -> dict[str, Any]:
    body = {"account": account_response(result.stored), "replayed": result.replayed}
    if result.kind == "expense":
        record = next(e for e in result.stored.expenses if e.id == result.record_id)
        body["activity"] = activity_response(result.stored, record, result.revision)
    elif result.kind == "balance_check":
        check = next(c for c in result.stored.checks if c.id == result.record_id)
        accepted = next(
            (c for c in (*check.prior_revisions, check) if c.revision == result.revision),
            check,
        )
        body["check"] = check_response(result.stored, accepted)
    return body


def page(
    stored: StoredAccount,
    items: list[dict[str, Any]],
    limit: int,
    cursor: str | None,
    scope: str,
) -> dict[str, Any]:
    offset = 0
    if cursor:
        try:
            data = json.loads(base64.urlsafe_b64decode(cursor))
            if (
                data["account"] != stored.account.id
                or data["scope"] != scope
                or not isinstance(data["offset"], int)
                or isinstance(data["offset"], bool)
                or data["offset"] < 0
            ):
                raise ValueError()
            if data["version"] != stored.account.version:
                raise StaleVersion()
            offset = data["offset"]
        except (ValueError, KeyError, TypeError):
            raise RecordingInputError(
                "cursor_invalid", "Reload this list to continue."
            ) from None
    selected = items[offset : offset + limit]
    next_cursor = None
    if offset + limit < len(items):
        payload = {
            "account": stored.account.id,
            "version": stored.account.version,
            "scope": scope,
            "offset": offset + limit,
        }
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()
    return {"items": selected, "next_cursor": next_cursor}


def expense_record(stored: StoredAccount, record_id: str) -> ExpenseRecord:
    try:
        record_id = str(UUID(record_id))
    except ValueError:
        raise AccountNotFound() from None
    record = next((e for e in stored.expenses if e.id == record_id), None)
    if record is None:
        raise AccountNotFound()
    return record


def personal_share(amount: int, bps: int) -> int:
    quotient, remainder = divmod(abs(amount) * bps, 10000)
    if remainder > 5000 or remainder == 5000 and quotient % 2:
        quotient += 1
    return quotient if amount >= 0 else -quotient


def home_response(
    accounts: list[StoredAccount],
    month: str | None = None,
    time_zone: str = "America/Santo_Domingo",
    now: datetime | None = None,
) -> dict[str, Any]:
    from argus.domain.recording.money_home import period
    from argus.domain.recording.money_reads import current_activities
    from argus.domain.recording.spending import spending

    reporting = period(month, time_zone, now)
    groups = {}
    recent = []
    for stored in accounts:
        facts = stored.account
        group = groups.setdefault(
            facts.currency,
            {
                "currency": facts.currency,
                "currency_fraction_digits": currency_exponent(facts.currency),
                "assets_minor": 0,
                "cash_minor": 0,
                "other_assets_minor": 0,
                "debts_minor": 0,
                "net_worth_minor": 0,
                "known_accounts": 0,
                "unknown_accounts": 0,
                "recorded_spending_minor": 0,
                "gross_income_minor": 0,
                "gross_purchases_minor": 0,
                "refunds_minor": 0,
                "net_spending_minor": 0,
                "as_of": None,
            },
        )
        balance = position(
            stored.opening, stored.checks, stored.expenses, stored.coverage
        )
        group["recorded_spending_minor"] += sum(
            e.current.amount_minor
            for e in stored.expenses
            if e.current.active and e.current.kind == "expense"
        )
        if balance.state == "unknown":
            group["unknown_accounts"] += 1
        else:
            group["known_accounts"] += 1
            amount = personal_share(balance.amount_minor, facts.ownership_share_bps)
            group["net_worth_minor"] += amount
            if amount >= 0:
                group["assets_minor"] += amount
                key = (
                    "cash_minor"
                    if facts.type in {"cash", "checking", "savings"}
                    else "other_assets_minor"
                )
                group[key] += amount
            else:
                group["debts_minor"] -= amount
            if group["as_of"] is None or balance.as_of.astimezone(timezone.utc) > group[
                "as_of"
            ].astimezone(timezone.utc):
                group["as_of"] = balance.as_of
        for expense in stored.expenses:
            r = expense.current
            if not r.active or r.role == "destination":
                continue
            if reporting["start_at"] <= r.occurred_at < reporting["end_at_exclusive"]:
                if r.kind == "income":
                    group["gross_income_minor"] += r.amount_minor
            recent.append(
                {
                    **activity_response(stored, expense),
                    "account_id": facts.id,
                    "account_nickname": facts.nickname,
                    "currency": facts.currency,
                    "currency_fraction_digits": currency_exponent(facts.currency),
                }
            )
    actual = current_activities(accounts)
    for group in groups.values():
        totals = spending(
            actual,
            currency=group["currency"],
            start=reporting["start_at"],
            end=reporting["end_at_exclusive"],
        )
        group["gross_purchases_minor"] = totals.purchases
        group["refunds_minor"] = totals.refunds
        group["net_spending_minor"] = totals.net
        for key in list(group):
            if key.endswith("_minor"):
                group[key] = str(group[key])
    recent.sort(key=lambda item: (item["occurred_at"], item["record_id"]), reverse=True)
    return {
        "currencies": [groups[k] for k in sorted(groups)],
        "recent_activity": recent[:5],
        "recorded_at": now or datetime.now(timezone.utc),
        "period": reporting,
        "coverage": "recorded_only",
    }
