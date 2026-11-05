"""Returns, currentness, unknown facts, safe cutover and atomic recovery."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from argus.domain.household import planning_schemas as wire
from argus.domain.household.errors import HouseholdNotFound
from argus.domain.household.financial import HouseholdFinancialService
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning.debts import DebtService
from argus.domain.planning.goal_schemas import AllocationWrite, GoalEdit
from argus.domain.planning.goals import GoalService
from argus.domain.recording.errors import RecordingInputError
from argus.domain.recording.money_schemas import MoneyRequest

from tests.household.financial_fixtures import DSN, NOW, account, key, share
from tests.household.financial_fixtures import command as household_command
from tests.household.shared_plan_fixtures import (
    command,
    create,
    get,
    link,
    money,
    personal,
    request,
    scene,
)
from tests.household.test_shared_planning_money import planners

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def correct(s, p, cid, activity):
    body = command(s, s["b"], p, wire.ContributionCorrection, activity=activity)
    args = (s["b"], s["hid"], p["ref"]["kind"], str(p["ref"]["id"]))
    review = s["plans"].money(*args, body, cid=cid)["money"]
    assert review["ready"]
    return s["plans"].money(
        *args,
        body.model_copy(
            update={
                "activity": MoneyRequest.model_validate(
                    review["reviewed_request"]
                    | {"preview_token": review["preview_token"]}
                )
            }
        ),
        key(),
        cid=cid,
    )["plan"]


@pytest.mark.parametrize("payment", ["card_payment", "debt_payment"])
def test_current_return_reduces_original_debt_credit_without_second_claim(lane, payment):
    s = scene(lane)
    if payment == "card_payment":
        s["loan"] = account(s["records"], s["a"], kind="credit_card")
    p = create(s, "debt")
    share(s["households"], s["a"], s["hid"], s["loan"], s["bmid"], "edit")
    paid, _ = money(
        s,
        s["b"],
        p,
        request(
            payment,
            s["ba"],
            "20",
            s["loan"],
            **(
                dict(principal="16", interest="3", fees="1")
                if payment == "debt_payment"
                else {}
            ),
        ),
        "debt_payment",
        p["occurrences"][0]["id"],
    )
    original = paid["plan"]["contributions"][0]
    returned, _ = money(
        s,
        s["b"],
        p,
        request(
            "payment_reversal",
            s["ba"],
            "5",
            s["loan"],
            reversal_of_activity_id=original["original"]["activity_id"],
            **(
                dict(principal="4", interest="0.5", fees="0.5")
                if payment == "debt_payment"
                else {}
            ),
        ),
        "debt_payment",
    )
    view = returned["plan"]
    assert len(view["contributions"]) == 1
    assert view["contributions"][0]["id"] == original["id"]
    assert view["contributions"][0]["amount_minor"] == "2000"
    assert view["contributions"][0]["applied_minor"] == "1500"
    assert view["occurrences"][0]["remaining_minor"] == "8500"
    # Owned destination Personal cannot reveal the foreign original source or return note.
    shared = get(s, s["a"], p)
    assert s["ba"] not in json.dumps(shared, default=str)


def test_corrected_away_budget_claim_is_unknown_and_never_uses_old_revision(lane):
    s = scene(lane)
    p = create(s, "budget")
    saved, _ = money(s, s["b"], p, request("expense", s["ba"], "20"), "spending")
    claim = saved["plan"]["contributions"][0]
    view = correct(
        s,
        p,
        claim["id"],
        request(
            "expense",
            s["bd"],
            "25",
            expected_revision=1,
            reason="Different original account",
        ),
    )
    assert view["contributions"][0]["amount_minor"] == "2500"
    assert view["contributions"][0]["status"] == "needs_review"
    assert view["contributions"][0]["applied_minor"] is None
    assert view["progress"]["state"] == "needs_review"
    assert all(
        view["progress"][k] is None
        for k in (
            "actual_minor",
            "applied_minor",
            "remaining_minor",
            "gross_minor",
            "refunds_minor",
            "spent_minor",
            "over_budget",
        )
    )
    assert s["ba"] not in json.dumps(get(s, s["a"], p), default=str)


@pytest.mark.parametrize("kind", ["bill", "goal", "debt"])
def test_fulfilled_today_edit_uses_canonical_tomorrow_cutover_and_keeps_occurrence(
    lane, kind
):
    s = scene(lane)
    p = create(s, kind)
    oid = p["occurrences"][0]["id"]
    activity = request(
        "transfer" if kind == "goal" else "debt_payment" if kind == "debt" else "expense",
        s["aa"],
        "100",
        s["ad"] if kind == "goal" else s["loan"] if kind == "debt" else None,
        **(dict(principal="100", interest="0", fees="0") if kind == "debt" else {}),
    )
    money(
        s,
        s["a"],
        p,
        activity,
        dict(bill="bill_payment", goal="goal_saving", debt="debt_payment")[kind],
        oid,
    )
    view = get(s, s["a"], p)
    tomorrow = NOW.date() + timedelta(days=1)
    assert view["definition"]["earliest_effective_date"] == tomorrow.isoformat()
    identifier = str(p["ref"]["id"])
    planner = planners(s, s["a"])
    personal_definition = (
        planner.get(s["a"], identifier)
        if kind == "bill"
        else GoalService(planner).get(s["a"], identifier)["goal"]
        if kind == "goal"
        else DebtService(planner).get(s["a"], identifier)["debt"]
    )
    assert personal_definition["earliest_effective_date"] == tomorrow.isoformat()
    fields = dict(
        schedule=dict(cadence="once", start_date=tomorrow.isoformat()),
        effective_date=tomorrow,
    )
    if kind == "goal":
        fields["planned_contribution_amount"] = "60"
    edited = s["plans"].edit(
        s["a"],
        s["hid"],
        kind,
        str(p["ref"]["id"]),
        command(s, s["a"], p, wire.EditPlan, definition=fields),
        key(),
    )["plan"]
    retained = next(o for o in edited["occurrences"] if o["id"] == oid)
    assert retained["applied_minor"] == "10000" and retained["remaining_minor"] == "0"
    assert len(edited["occurrences"]) == 2
    if kind == "goal":
        assert edited["definition"]["planned_contribution_minor"] == "6000"


def test_ungranted_household_member_and_currency_mismatch_never_discover_or_post(lane):
    s = scene(lane)
    p = create(s, "budget")
    invited = household_command(
        s["households"],
        s["a"],
        "invite",
        lambda: s["households"].invite(user_id=s["a"], household_id=s["hid"]),
        s["hid"],
    ).invitation
    household_command(
        s["households"],
        s["c"],
        "accept",
        lambda: s["households"].accept(
            user_id=s["c"], token=invited.token, display_name="Carol"
        ),
    )
    assert s["plans"].snapshot(s["c"], s["hid"])["plans"] == []
    assert (
        HouseholdFinancialService(s["households"]).search(
            s["c"], s["hid"], "Shared", None, 20
        )["items"]
        == []
    )
    with pytest.raises(HouseholdNotFound):
        get(s, s["c"], p)
    usd = account(s["records"], s["b"], currency="USD")
    private = personal(s, s["b"], request("expense", usd, "5"))
    with pytest.raises(RecordingInputError):
        link(s, s["b"], p, private, "spending")
    assert get(s, s["a"], p)["progress"]["spent_minor"] == "0"
    assert get(s, s["a"], p)["contributions"] == []


def test_funding_is_not_bill_payment_and_private_paid_debt_stays_unknown(lane):
    s = scene(lane)
    p = create(s, "bill")
    money(s, s["b"], p, request("transfer", s["ba"], "20", s["bd"]), "funding")
    view = get(s, s["a"], p)
    assert view["progress"]["actual_minor"] == "2000"
    assert view["progress"]["applied_minor"] == "0"
    assert view["occurrences"][0]["remaining_minor"] == "10000"
    s["loan"] = account(s["records"], s["a"], amount=-1000, kind="other_debt")
    debt = create(s, "debt")
    money(
        s,
        s["a"],
        debt,
        request(
            "debt_payment",
            s["aa"],
            "1000",
            s["loan"],
            principal="1000",
            interest="0",
            fees="0",
        ),
        "debt_payment",
    )
    own, participant = get(s, s["a"], debt), get(s, s["b"], debt)
    assert own["progress"]["debt_balance_minor"] == "0"
    assert own["progress"]["debt_state"] == "recorded_clear"
    assert participant["progress"]["debt_balance_minor"] is None
    assert participant["progress"]["debt_state"] == "unknown"


def test_failed_post_claim_rolls_back_money_versions_receipt_and_link(lane):
    s = scene(lane)
    s["bd"] = account(s["records"], s["b"], amount=None)
    p = create(s, "goal")
    before = s["records"].get_account(user_id=s["b"], account_id=s["ba"], scope=PERSONAL)
    with pytest.raises(RecordingInputError, match="known available"):
        money(s, s["b"], p, request("transfer", s["ba"], "20", s["bd"]), "goal_saving")
    after = s["records"].get_account(user_id=s["b"], account_id=s["ba"], scope=PERSONAL)
    assert after.account.version == before.account.version
    assert len(after.expenses) == len(before.expenses)
    view = get(s, s["a"], p)
    assert view["version"] == p["version"] and view["contributions"] == []
    with s["records"]._pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from financial_activity_groups where user_id=%s",
                (s["b"],),
            ).fetchone()[0]
            == 0
        )


def test_concurrent_record_retry_posts_exactly_one_fact_and_one_claim(lane):
    s = scene(lane)
    p = create(s, "budget")
    body = command(
        s,
        s["b"],
        p,
        wire.ContributionRecord,
        activity=request("expense", s["ba"], "20"),
        purpose="spending",
    )
    args = (s["b"], s["hid"], "budget", str(p["ref"]["id"]))
    review = s["plans"].money(*args, body)["money"]
    reviewed = body.model_copy(
        update={
            "activity": MoneyRequest.model_validate(
                review["reviewed_request"] | {"preview_token": review["preview_token"]}
            )
        }
    )
    barrier, k = Barrier(2), key()

    def write(_):
        barrier.wait()
        return s["plans"].money(*args, reviewed, k)

    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(write, range(2)))
    assert sorted(r["replayed"] for r in responses) == [False, True]
    assert get(s, s["a"], p)["progress"]["spent_minor"] == "2000"
    with s["records"]._pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from financial_activity_groups where user_id=%s",
                (s["b"],),
            ).fetchone()[0]
            == 1
        )


def test_personal_owned_shared_residual_preserves_identity_and_consent(lane):
    s = scene(lane)
    p = create(s, "goal")
    aid = s["ad"]
    version = (
        s["records"]
        .get_account(user_id=s["a"], account_id=aid, scope=PERSONAL)
        .account.version
    )
    shared = s["plans"].allocate(
        s["a"],
        s["hid"],
        "goal",
        str(p["ref"]["id"]),
        command(
            s,
            s["a"],
            p,
            wire.AllocationWrite,
            account_id=aid,
            amount="30",
            expected_account_versions={aid: version},
        ),
        key(),
    )["plan"]
    stable = shared["allocations"][0]["id"]
    goals = GoalService(planners(s, s["a"]))
    current = goals.get(s["a"], str(p["ref"]["id"]))["goal"]
    goals.edit(
        s["a"],
        current["id"],
        GoalEdit(expected_version=current["version"], name="Still same owner"),
        key(),
    )
    assert get(s, s["b"], p)["allocations"][0]["id"] == stable
    assert sorted(r["amount_minor"] for r in get(s, s["b"], p)["responsibilities"]) == [
        "3000",
        "7000",
    ]
    current = goals.get(s["a"], current["id"])["goal"]
    goals.allocate(
        s["a"],
        AllocationWrite(
            changes=[
                dict(
                    goal_id=current["id"],
                    expected_version=current["version"],
                    account_id=aid,
                    amount="0",
                )
            ],
            expected_account_versions={aid: version},
        ),
        key(),
    )
    now = get(s, s["b"], p)["allocations"][0]
    assert now["id"] == stable and now["assigned_minor"] == "0"


def test_raw_shared_contract_tables_deny_registered_owner_and_foreign_member(lane):
    s = scene(lane)
    create(s, "goal")
    tables = [
        "household_plan_bindings",
        "household_plan_participants",
        "financial_plan_responsibilities",
        "household_plan_receipts",
        "financial_plan_definition_revisions",
        "financial_goal_allocation_revisions",
        "household_plan_archived_claims",
        "household_plan_archived_allocations",
        "household_plan_archived_activities",
    ]
    for actor in (s["a"], s["b"], s["c"]):
        with s["records"]._pool.connection() as c, c.transaction(force_rollback=True):
            c.execute("set local role authenticated")
            c.execute(
                "select set_config('request.jwt.claims',%s,true)",
                (json.dumps(dict(sub=actor, role="authenticated")),),
            )
            for table in tables:
                from psycopg.errors import InsufficientPrivilege

                with pytest.raises(InsufficientPrivilege), c.transaction():
                    c.execute(f"select * from public.{table}").fetchall()


def test_old_foreign_leg_correction_requires_live_original_account_authority(lane):
    s = scene(lane)
    p = create(s, "goal")
    share(s["households"], s["a"], s["hid"], s["ad"], s["bmid"], "edit")
    saved, _ = money(
        s, s["b"], p, request("transfer", s["ba"], "20", s["ad"]), "goal_saving"
    )
    claim = saved["plan"]["contributions"][0]
    aid = claim["original"]["activity_id"]
    changed = correct(
        s,
        p,
        claim["id"],
        request(
            "transfer",
            s["ba"],
            "20",
            s["bd"],
            expected_revision=1,
            reason="Correct destination",
        ),
    )
    assert changed["contributions"][0]["status"] == "needs_review"
    from argus.domain.recording.errors import AccountNotFound
    from argus.domain.recording.money_service import MoneyService

    with pytest.raises(AccountNotFound):
        MoneyService(planners(s, s["a"]).accounts).detail(
            user_id=s["a"], activity_id=aid, scope=PERSONAL
        )
    household_command(
        s["households"],
        s["a"],
        "withdraw",
        lambda: s["households"].replace_grants(
            user_id=s["a"], household_id=s["hid"], account_id=s["ad"], recipients=[]
        ),
        s["hid"],
    )
    for account_id in (s["ba"], s["bd"]):
        share(s["households"], s["b"], s["hid"], account_id, s["amid"], "view")
    current = s["households"].get(user_id=s["b"], household_id=s["hid"])
    with pytest.raises(HouseholdNotFound):
        HouseholdFinancialService(s["households"]).money(
            s["b"],
            s["hid"],
            request(
                "transfer",
                s["ba"],
                "25",
                s["bd"],
                expected_revision=2,
                reason="Previous account permission missing",
            ),
            aid,
            membership_id=current.membership_id,
            expected_household_version=current.version,
        )
