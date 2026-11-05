"""Allocation changes and contribution claims are one owner-serialized command."""

from datetime import date
from typing import Any
from uuid import UUID, uuid4

from argus.domain.planning import claims, goal_model, goal_projection, model
from argus.domain.planning.goal_schemas import AllocationWrite, ContributionLink
from argus.domain.recording.currency import parse_minor_units
from argus.domain.recording.errors import AccountNotFound, StaleVersion
from argus.domain.recording.loop_reads import personal_share
from argus.domain.recording.money_reads import activity
from argus.domain.recording.repository import StoredAccount


def account_versions(
    accounts: list[StoredAccount], expected: dict[UUID, int], ids: set[str]
) -> None:
    versions = {str(k): v for k, v in expected.items()}
    current = {s.account.id: s.account.version for s in accounts}
    if any(aid not in current for aid in ids):
        raise AccountNotFound()
    if any(versions.get(aid) != current[aid] for aid in ids):
        raise StaleVersion()


def amounts(
    state: dict[str, Any], accounts: list[StoredAccount]
) -> dict[tuple[str, str], int]:
    result = {
        (gid, a["account_id"]): a["unlinked_minor"]
        for gid, item in state["goals"].items()
        for a in item["allocations"]
    }
    for gid, entries in goal_projection.contributions(state, accounts).items():
        for entry in entries:
            if entry["counting"] and entry["current_personal_minor"] is not None:
                key = gid, entry["destination_account_id"]
                result[key] = result.get(key, 0) + int(entry["current_personal_minor"])
    return result


def require_backing(
    state: dict[str, Any],
    accounts: list[StoredAccount],
    before: dict[tuple[str, str], int],
    today: date,
) -> None:
    after = amounts(state, accounts)
    increased = {
        aid for (gid, aid), value in after.items() if value > before.get((gid, aid), 0)
    }
    _, pools = goal_projection.project(state, accounts, today, today)
    for pool in pools:
        if pool["account_id"] in increased and pool["state"] != "backed":
            model.fail(
                "goal_backing_" + pool["state"],
                "Review known available money before increasing an allocation.",
            )


def release(state: dict[str, Any], gid: str, cid: str) -> None:
    link = state["links"].get(cid)
    if link is None or link.get("goal_id") != gid:
        raise AccountNotFound()
    if claims.occurrence_id(cid, link):
        link["attribution"]["counting"] = False
    else:
        del state["links"][cid]


def replace_allocations(
    state: dict[str, Any],
    accounts: list[StoredAccount],
    body: AllocationWrite,
    today: date,
) -> None:
    before = amounts(state, accounts)
    keys = [(str(change.goal_id), str(change.account_id)) for change in body.changes]
    if len(keys) != len(set(keys)):
        model.fail("goal_allocation_duplicate", "Change each goal and account once.")
    account_versions(accounts, body.expected_account_versions, {aid for _, aid in keys})
    for change in body.changes:
        item = goal_model.get(state, str(change.goal_id), change.expected_version)
        aid = str(change.account_id)
        value = parse_minor_units(change.amount, item["currency"])
        if value < 0:
            model.fail("goal_allocation_negative", "Use zero to release an allocation.")
        if value > before.get((item["id"], aid), 0):
            model.cash_account(accounts, aid, item["currency"])
        for cid in change.release_claim_ids:
            link = state["links"].get(str(cid))
            if (
                not link
                or link.get("goal_id") != item["id"]
                or link["attribution"]["destination_account_id"] != aid
            ):
                raise AccountNotFound()
            release(state, item["id"], str(cid))
    current = amounts(state, accounts)
    for change in body.changes:
        item = state["goals"][str(change.goal_id)]
        aid = str(change.account_id)
        allocation = next(
            (a for a in item["allocations"] if a["account_id"] == aid), None
        )
        residual = allocation["unlinked_minor"] if allocation else 0
        linked = current.get((item["id"], aid), 0) - residual
        value = parse_minor_units(change.amount, item["currency"])
        if value < linked:
            model.fail(
                "goal_release_required",
                "Stop counting contributions before reducing below their amount.",
            )
        item["allocations"] = [a for a in item["allocations"] if a["account_id"] != aid]
        if value > linked:
            item["allocations"].append(
                {"account_id": aid, "unlinked_minor": value - linked}
            )
    require_backing(state, accounts, before, today)
    for gid in {gid for gid, _ in keys}:
        state["goals"][gid]["version"] += 1


def attach(
    state: dict[str, Any],
    accounts: list[StoredAccount],
    item: dict[str, Any],
    actual: dict[str, Any],
    treatment: str,
    oid: str | None,
    today: date,
) -> None:
    destination = item["destination_account_id"]
    if not destination:
        model.fail("goal_setup_required", "Choose a contribution destination.")
    source = next(
        (leg["account_id"] for leg in actual["legs"] if leg["role"] == "source"), None
    )
    if not source or not goal_model.transfer_matches(
        actual, source, destination, item["currency"]
    ):
        model.fail(
            "goal_contribution_mismatch",
            "Choose a transfer into this goal's destination.",
        )
    model.cash_account(accounts, source, item["currency"])
    model.cash_account(accounts, destination, item["currency"])
    occurrence = (
        goal_model.find_occurrence(state, item["id"], oid, today) if oid else None
    )
    if occurrence and not goal_model.transfer_matches(
        actual,
        occurrence["source_account_id"],
        occurrence["destination_account_id"],
        occurrence["currency"],
    ):
        model.fail(
            "goal_contribution_mismatch", "Review the scheduled source and destination."
        )
    existing = next(
        (
            (cid, link)
            for cid, link in state["links"].items()
            if link["activity_id"] == actual["activity_id"]
        ),
        None,
    )
    if existing:
        cid, link = existing
        if (
            link.get("goal_id") != item["id"]
            or not oid
            or claims.occurrence_id(cid, link)
        ):
            model.fail(
                "activity_already_linked", "That activity already has an assignment."
            )
        if not link["attribution"]["counting"] or not goal_model.transfer_matches(
            actual,
            link["attribution"]["source_account_id"],
            link["attribution"]["destination_account_id"],
            link["attribution"]["currency"],
        ):
            model.fail("goal_contribution_mismatch", "Review the original contribution.")
        if claims.for_occurrence(state, oid):
            model.fail("occurrence_already_linked", "Open the existing contribution.")
        link["occurrence_id"], link["snapshot"] = oid, occurrence
        return
    if oid and claims.for_occurrence(state, oid):
        model.fail("occurrence_already_linked", "Open the existing contribution.")
    dest = next(s.account for s in accounts if s.account.id == destination)
    amount = personal_share(actual["amount_minor"], dest.ownership_share_bps)
    if treatment == "included":
        residual = next(
            (a for a in item["allocations"] if a["account_id"] == destination), None
        )
        if not residual or residual["unlinked_minor"] < amount:
            model.fail(
                "goal_included_exceeds_allocation",
                "Review how much unlinked money is already assigned.",
            )
        residual["unlinked_minor"] -= amount
    state["links"][str(uuid4())] = {
        "expectation_id": None,
        "goal_id": item["id"],
        "occurrence_id": oid,
        "activity_id": actual["activity_id"],
        "activity_revision": actual["revision"],
        "snapshot": occurrence or {},
        "attribution": {
            "source_account_id": source,
            "destination_account_id": destination,
            "currency": item["currency"],
            "treatment": treatment,
            "reviewed_personal_minor": amount,
            "counting": True,
        },
    }


def link(
    state: dict[str, Any],
    accounts: list[StoredAccount],
    gid: str,
    body: ContributionLink,
    today: date,
) -> None:
    item = goal_model.get(state, gid, body.expected_version)
    actual = activity(accounts, str(body.activity_id))
    if actual["revision"] != body.activity_revision:
        raise StaleVersion()
    account_versions(
        accounts,
        body.expected_account_versions,
        {leg["account_id"] for leg in actual["legs"]},
    )
    before = amounts(state, accounts)
    attach(
        state,
        accounts,
        item,
        actual,
        body.treatment,
        str(body.occurrence_id) if body.occurrence_id else None,
        today,
    )
    require_backing(state, accounts, before, today)
    item["version"] += 1
