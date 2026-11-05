"""Canonical consented credits reduce original intentions without private DTOs."""

from argus.domain.recording.money_reads import activity_in_currency
from argus.domain.recording.payments import net_total

from . import goal_projection


def credit(entry, accepted, purpose, actual, accounts):
    if (
        not entry
        or not activity_in_currency(entry, accepted["currency"])
        or entry["kind"] != accepted["kind"]
    ):
        return None
    if {(leg["role"], leg["account_id"]) for leg in entry["legs"]} != {
        tuple(leg) for leg in accepted["legs"]
    }:
        return None
    if purpose == "goal_saving":
        return goal_projection.contribution_minor(entry, accepted, accounts)
    if purpose == "debt_payment":
        return net_total(entry, list(actual.values()))
    return entry["amount_minor"] if purpose == "bill_payment" else 0


def supported_credit(state, link, actual, records, canonical):
    if link.get("retained"):
        return None if link["purpose"] == "goal_saving" else link["retained_applied"]
    amount = credit(
        actual.get(link["activity_id"]),
        link["attribution"],
        link["purpose"],
        actual,
        records,
    )
    if amount is None or link["purpose"] != "goal_saving" or amount == 0:
        return amount
    owner = link["attribution"]["destination_owner_id"]
    pool_state = (
        state
        if owner == state.get("_owner_id")
        else state.get("_claim_pool_states", {}).get(owner)
    )
    if pool_state is None:
        return None
    from argus.domain.recording.canonical_groups import VisibleAccounts

    owned = [record for record in records if record.account.user_id == owner]
    positions = VisibleAccounts(owned, canonical) if canonical is not None else owned
    pool_state = pool_state | {
        "_canonical_records": records,
        "_canonical_activities": actual,
    }
    amounts, _, __ = goal_projection.pool_assignments(pool_state, positions)
    pools = goal_projection.pool_facts(pool_state, positions, amounts)
    destination = link["attribution"]["destination_account_id"]
    return amount if pools.get(destination, {}).get("state") == "backed" else None


def for_occurrence(state, identifier, accounts=None):
    canonical = getattr(accounts, "canonical", None) or state.get("_canonical_groups")
    actual = state.get("_canonical_activities", {})
    records = state.get("_canonical_records", accounts or [])
    if canonical is not None:
        from argus.domain.recording.money_reads import render_activity

        actual = {
            aid: render_activity(aid, canonical.history[aid], revision)
            for aid, revision in canonical.current.items()
        }
        records = canonical.records
    links = [
        link
        for link in state.get("_shared_links", [])
        if link["occurrence_id"] == identifier
    ]
    if not links:
        return None
    values = [
        0
        if link["released"]
        else supported_credit(state, link, actual, records, canonical)
        for link in links
    ]
    return dict(amount=sum(values) if all(v is not None for v in values) else None)
