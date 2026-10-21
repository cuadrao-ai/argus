import json
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.household.access import AccountAccess, HouseholdFinancialScope
from argus.domain.household.errors import HouseholdNotFound
from argus.domain.household.projection import activity
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording import canonical_groups
from argus.domain.recording.errors import AccountNotFound
from argus.domain.recording.money_reads import render_activity
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from faker import Faker

from tests.financial_accounts import test_loop_commands as shared
from tests.financial_accounts.test_personal_money import account, save

fake = Faker()
NOW = shared.NOW
scene = shared.scene


def catalog(owner, receipts, current):
    headers = [
        canonical_groups.Group(identifier, owner, revision)
        for identifier, revision in current.items()
    ]
    memberships = [
        canonical_groups.Membership(
            receipt["activity_id"],
            owner,
            receipt["revision"],
            leg["record_id"],
            leg["record_revision"],
            leg["role"],
        )
        for receipt in receipts
        for leg in receipt["legs"]
    ]
    return headers, memberships


def scope(owner, visible):
    return HouseholdFinancialScope(
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
        1,
        {visible: AccountAccess(owner, fake.first_name(), "view")},
        {owner: fake.first_name()},
    )


def correct(scene, original, **changes):
    money = MoneyService(scene[0])
    request = MoneyRequest(
        kind=original["kind"],
        amount=original["amount"],
        account_id=original["legs"][0]["account_id"],
        occurred_at=NOW - timedelta(days=2),
        expected_revision=original["revision"],
        reason=fake.sentence(),
    ).model_copy(update=changes)
    preview = money.preview(
        user_id=scene[1],
        request=request,
        activity_id=original["activity_id"],
        scope=PERSONAL,
    )
    return money.write(
        user_id=scene[1],
        request=MoneyRequest.model_validate(
            preview["reviewed_request"] | {"preview_token": preview["preview_token"]}
        ),
        activity_id=original["activity_id"],
        idempotency_key=str(uuid4()),
        scope=PERSONAL,
    )["activity"]


def test_current_group_revision_controls_amount_instead_of_latest_visible_history(scene):
    source = account(scene)
    first = save(scene, kind="expense", account_id=source, amount="25")["activity"]
    second = correct(scene, first, amount="15")
    aid = first["activity_id"]
    records = scene[0].list_accounts(user_id=scene[1], scope=PERSONAL)
    headers, memberships = catalog(scene[1], [first, second], {aid: 1})
    resolved = canonical_groups.resolve(records, headers, memberships)

    result = activity(scope(scene[1], source), records, aid, canonical=resolved)

    assert result["activity"]["revision"] == 1
    assert result["activity"]["amount_minor"] == 2500
    assert set(resolved.history[aid]) == {1}


def test_group_without_authoritative_header_cannot_replay_visible_record_history(scene):
    source = account(scene)
    original = save(scene, kind="expense", account_id=source, amount="25")["activity"]
    records = scene[0].list_accounts(user_id=scene[1], scope=PERSONAL)
    _, memberships = catalog(scene[1], [original], {})
    resolved = canonical_groups.resolve(records, [], memberships)

    assert resolved.current_visible({source}) == {}
    with pytest.raises(HouseholdNotFound):
        activity(
            scope(scene[1], source), records, original["activity_id"], canonical=resolved
        )


def test_corrected_away_account_cannot_select_its_obsolete_activity_revision(scene):
    old, destination = account(scene), account(scene)
    first = save(scene, kind="expense", account_id=old, amount="25")["activity"]
    second = correct(scene, first, account_id=destination, amount="15")
    aid = first["activity_id"]
    records = scene[0].list_accounts(user_id=scene[1], scope=PERSONAL)
    headers, memberships = catalog(scene[1], [first, second], {aid: 2})
    resolved = canonical_groups.resolve(records, headers, memberships)

    assert resolved.current_visible({old}) == {}
    assert resolved.current_visible({destination}) == {aid: 2}
    with pytest.raises(HouseholdNotFound):
        activity(scope(scene[1], old), records, aid, canonical=resolved)
    history = activity(scope(scene[1], old), records, aid, 1, canonical=resolved)
    assert history["activity"]["amount_minor"] == 2500


@pytest.mark.parametrize("visible_role", ["source", "destination"])
def test_full_loan_group_is_resolved_before_household_visibility(scene, visible_role):
    source = account(scene, "checking", amount="1000")
    destination = account(scene, "other_debt", amount="1000")
    original = save(
        scene,
        kind="debt_payment",
        source_account_id=source,
        destination_account_id=destination,
        amount="110",
        principal="100",
        interest="8",
        fees="2",
        note=fake.sentence(),
    )["activity"]
    records = scene[0].list_accounts(user_id=scene[1], scope=PERSONAL)
    aid = original["activity_id"]
    headers, memberships = catalog(scene[1], [original], {aid: 1})
    resolved = canonical_groups.resolve(records, headers, memberships)
    canonical = render_activity(aid, resolved.history[aid], resolved.current[aid])

    assert canonical["amount_minor"] == 11000
    assert canonical["principal_minor"] == 10000
    assert canonical["interest_minor"] == 800 and canonical["fees_minor"] == 200
    visible = source if visible_role == "source" else destination
    hidden = destination if visible_role == "source" else source
    result = activity(scope(scene[1], visible), records, aid, canonical=resolved)

    assert result["activity"]["amount_minor"] == (
        11000 if visible_role == "source" else None
    )
    assert result["private_counterpart"] and not result["can_edit"]
    assert result["activity"]["principal_minor"] is None
    assert result["activity"]["interest_minor"] is None
    assert result["activity"]["fees_minor"] is None
    assert hidden not in json.dumps(result, default=str)
    if visible_role == "destination":
        assert result["activity"]["note"] is None


@pytest.mark.parametrize(
    "fault",
    ["missing_record", "wrong_revision", "wrong_owner", "wrong_role", "missing_source"],
)
def test_incomplete_or_mismatched_exact_membership_cannot_be_rendered(scene, fault):
    source, destination = account(scene), account(scene)
    original = save(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=destination,
        amount="25",
    )["activity"]
    records = scene[0].list_accounts(user_id=scene[1], scope=PERSONAL)
    headers, memberships = catalog(
        scene[1], [original], {original["activity_id"]: original["revision"]}
    )
    index = next(i for i, member in enumerate(memberships) if member.role == "source")
    if fault == "missing_record":
        records = [stored for stored in records if stored.account.id != source]
    elif fault == "missing_source":
        memberships.pop(index)
    else:
        changes = {
            "wrong_revision": {"record_revision": memberships[index].record_revision + 1},
            "wrong_owner": {"owner_id": str(uuid4())},
            "wrong_role": {"role": "single"},
        }
        memberships[index] = replace(memberships[index], **changes[fault])

    with pytest.raises(AccountNotFound):
        canonical_groups.resolve(records, headers, memberships)
