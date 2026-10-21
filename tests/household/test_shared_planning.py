"""Shared plans disclose consented facts while canonical owners retain money."""

import json

import pytest
from argus.domain.household.errors import HouseholdNotFound
from argus.domain.household.planning_schemas import ContributionLink, CreatePlan
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.service import FinancialAccountService

from tests.household.financial_fixtures import DSN, NOW, account, key, setup

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def scope(service, actor, hid, version=None):
    h = service.get(user_id=actor, household_id=hid)
    result = dict(membership_id=h.membership_id, expected_authorization_version=h.version)
    if version is not None:
        result["expected_plan_version"] = version
    return result


def post(records, owner, aid, amount):
    from argus.domain.recording.money_schemas import MoneyRequest

    from tests.household.financial_fixtures import expense

    money = MoneyService(FinancialAccountService(records, clock=lambda: NOW))
    preview = money.preview(
        user_id=owner,
        request=expense(aid, amount).model_copy(update={"occurred_at": NOW}),
        scope=PERSONAL,
    )
    return money.write(
        user_id=owner,
        request=MoneyRequest.model_validate(
            preview["reviewed_request"] | {"preview_token": preview["preview_token"]}
        ),
        idempotency_key=key(),
        scope=PERSONAL,
    )


def test_unequal_budget_responsibilities_are_not_actuals_and_private_source_stays_hidden(
    lane,
):
    from argus.domain.household.planning import SharedPlanningService

    households, records, (a, b, denied) = lane
    hid, bmid, _ = setup(lane)
    am = households.get(user_id=a, household_id=hid).membership_id
    aa, ba = account(records, a), account(records, b)
    plans = SharedPlanningService(households)
    created = plans.create(
        a,
        hid,
        "budget",
        CreatePlan(
            **scope(households, a, hid),
            definition=dict(
                kind="budget",
                name="Shared groceries",
                limit="100",
                currency="DOP",
                month=NOW.strftime("%Y-%m"),
                account_ids=[aa],
                category_ids=[],
                include_uncategorized=True,
            ),
            participants=[dict(membership_id=bmid)],
            responsibilities=[
                dict(membership_id=am, amount="70", period=NOW.strftime("%Y-%m")),
                dict(membership_id=bmid, amount="30", period=NOW.strftime("%Y-%m")),
            ],
        ),
        key(),
    )
    identifier = str(created["plan"]["ref"]["id"])
    assert sorted(r["amount_minor"] for r in created["plan"]["responsibilities"]) == [
        "3000",
        "7000",
    ]
    for actor, aid, amount in [(a, aa, "20"), (b, ba, "10")]:
        receipt = post(records, actor, aid, amount)
        activity = receipt["activity"]
        version = plans.get(actor, hid, "budget", identifier)["version"]
        plans.link(
            actor,
            hid,
            "budget",
            identifier,
            ContributionLink(
                **scope(households, actor, hid, version),
                activity_id=activity["activity_id"],
                activity_revision=activity["revision"],
                expected_account_versions={aid: receipt["accounts"][0].version},
                purpose="spending",
            ),
            key(),
        )
    view = plans.get(b, hid, "budget", identifier)
    assert view["progress"]["spent_minor"] == "3000"
    assert view["progress"]["remaining_minor"] == "7000"
    assert sorted(r["amount_minor"] for r in view["responsibilities"]) == ["3000", "7000"]
    assert sorted(c["applied_minor"] for c in view["contributions"]) == ["1000", "2000"]
    encoded = json.dumps(view, default=str)
    assert aa not in encoded
    assert (
        records.get_account(user_id=a, account_id=aa, scope=PERSONAL).account.nickname
        not in encoded
    )
    with pytest.raises(HouseholdNotFound):
        plans.get(denied, hid, "budget", identifier)
