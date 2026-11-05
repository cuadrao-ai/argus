"""The only public projection of granted accounts and their linked activity."""

from typing import Any

from argus.domain.recording.canonical_groups import ResolvedGroups
from argus.domain.recording.currency import currency_exponent
from argus.domain.recording.loop import position
from argus.domain.recording.loop_reads import personal_share
from argus.domain.recording.money_reads import groups, render_activity
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.repository import StoredAccount
from argus.domain.recording.schemas import account_response

from .access import HouseholdFinancialScope, dependencies, require_edit
from .errors import HouseholdNotFound as HouseholdUnavailable


def account(scope: HouseholdFinancialScope, stored: StoredAccount) -> dict[str, Any]:
    access = scope.accounts[stored.account.id]
    body = account_response(stored).model_dump(mode="json")

    def redact(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "recorded_by":
                    value[key] = None
                elif "debt_account_id" in key and item not in scope.accounts:
                    value[key] = None
                else:
                    redact(item)
        elif isinstance(value, list):
            for item in value:
                redact(item)

    redact(body)
    return {
        "account": body,
        "owner_name": access.owner_name,
        "permission": access.permission,
        "is_owner": access.owner_id == scope.actor_id,
    }


def activity(
    scope: HouseholdFinancialScope,
    records: list[StoredAccount],
    aid: str,
    revision: int | None = None,
    *,
    all_owner_records: list[StoredAccount] | None = None,
    canonical: ResolvedGroups | None = None,
) -> dict[str, Any]:
    history = canonical.history if canonical is not None else groups(records)
    if canonical is not None and revision is None:
        revision = canonical.current.get(aid)
        if revision is None:
            raise HouseholdUnavailable()
    if aid not in history or revision is not None and revision not in history[aid]:
        raise HouseholdUnavailable()
    body = render_activity(aid, history[aid], revision)
    visible_legs = [leg for leg in body["legs"] if leg["account_id"] in scope.accounts]
    if not visible_legs:
        raise HouseholdUnavailable()
    private = len(visible_legs) != len(body["legs"])
    primary_hidden = body["legs"][0]["account_id"] not in scope.accounts
    body["legs"] = visible_legs
    for field, rev_field in (
        ("purchase_activity_id", "purchase_revision"),
        ("reversal_of_activity_id", "reversal_of_revision"),
    ):
        ref = body[field]
        if not ref:
            continue
        linked = history.get(ref, {}).get(body[rev_field], [])
        if not linked or any(s.account.id not in scope.accounts for s, _, __ in linked):
            body[field] = body[rev_field] = None
            private = True
    if primary_hidden:
        body["currency"] = visible_legs[0]["currency"]
        body["currency_fraction_digits"] = visible_legs[0]["currency_fraction_digits"]
        body["amount"] = body["amount_minor"] = None
        body["note"] = body["reason"] = body["source_id"] = body["category_id"] = None

    author = scope.authors.get(body["recorded_by"], "")
    body["recorded_by"] = None
    if private:
        body["principal_minor"] = body["interest_minor"] = body["fees_minor"] = None
        body["counted_spending_minor"] = None
    editable = False
    if not private and all_owner_records is not None:
        request = MoneyRequest(
            kind=body["kind"], amount=body["amount"], occurred_at=body["occurred_at"]
        )
        try:
            require_edit(scope, dependencies(all_owner_records, request, aid))
            editable = True
        except HouseholdUnavailable:
            pass
    return {
        "activity": body,
        "author_name": author,
        "can_edit": editable,
        "private_counterpart": private,
    }


def positions(records: list[StoredAccount]) -> list[dict[str, Any]]:
    result = {}
    for s in records:
        group = result.setdefault(
            s.account.currency,
            {
                "currency": s.account.currency,
                "currency_fraction_digits": currency_exponent(s.account.currency),
                "amount_minor": 0,
                "unknown_count": 0,
            },
        )
        balance = position(s.opening, s.checks, s.expenses, s.coverage)
        if balance.amount_minor is None:
            group["unknown_count"] += 1
        else:
            group["amount_minor"] += personal_share(
                balance.amount_minor, s.account.ownership_share_bps
            )
    return [result[key] for key in sorted(result)]
