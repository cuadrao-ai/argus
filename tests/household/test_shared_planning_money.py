"""True original leg owners, private-source projections and one allocation pool."""

import json

import pytest
from argus.domain.household import planning_schemas as wire
from argus.domain.household.errors import HouseholdNotFound
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning import storage
from argus.domain.planning.budgets import BudgetService
from argus.domain.planning.goal_schemas import AllocationWrite, GoalCreate, GoalEdit
from argus.domain.planning.goals import GoalService
from argus.domain.planning.service import PlanService
from argus.domain.recording.errors import AccountNotFound, RecordingInputError
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.service import FinancialAccountService

from tests.household.financial_fixtures import DSN, NOW, account, key, share
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

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def planners(s, actor):
    return PlanService(FinancialAccountService(s["records"], clock=lambda: NOW))


@pytest.mark.parametrize("kind", ["transfer", "card_payment", "debt_payment"])
def test_cross_owner_original_is_canonical_and_personal_destination_hides_funding(
    lane, kind
):
    s = scene(lane)
    if kind == "transfer":
        p = create(s, "goal")
        dest = s["ad"]
        purpose = "goal_saving"
    else:
        if kind == "card_payment":
            s["loan"] = account(s["records"], s["a"], kind="credit_card")
        p = create(s, "debt")
        dest = s["loan"]
        purpose = "debt_payment"
    share(s["households"], s["a"], s["hid"], dest, s["bmid"], "edit")
    marker = "PRIVATE-B-FUNDING-" + key()
    body = request(
        kind,
        s["ba"],
        "20",
        dest,
        note=marker,
        **(
            dict(principal="16", interest="3", fees="1") if kind == "debt_payment" else {}
        ),
    )
    saved, reviewed = money(s, s["b"], p, body, purpose, p["occurrences"][0]["id"])
    contribution = saved["plan"]["contributions"][0]
    assert (
        contribution["amount_minor"] == "2000" and contribution["applied_minor"] == "2000"
    )
    assert contribution["can_correct"]
    original = MoneyService(planners(s, s["a"]).accounts)
    aid = contribution["original"]["activity_id"]
    destination = original.detail(user_id=s["a"], activity_id=aid, scope=PERSONAL)
    assert destination["amount_minor"] is None
    assert destination["principal_minor"] is None
    assert [leg["account_id"] for leg in destination["legs"]] == [dest]
    encoded = json.dumps(
        [
            destination,
            original.history(user_id=s["a"], activity_id=aid, scope=PERSONAL),
            planners(s, s["a"]).read(s["a"]),
        ],
        default=str,
    )
    assert s["ba"] not in encoded and marker not in encoded
    with s["records"]._pool.connection() as c, c.transaction(force_rollback=True):
        rows = c.execute(
            "select record_owner_id,role from financial_activity_memberships where activity_id=%s and activity_revision=1 order by role",
            (aid,),
        ).fetchall()
        assert [(str(owner), role) for owner, role in rows] == [
            (s["a"], "destination"),
            (s["b"], "source"),
        ]
        ids = [
            row[0]
            for row in c.execute(
                "select record_id from financial_activity_memberships where activity_id=%s",
                (aid,),
            ).fetchall()
        ]
        c.execute("set local role authenticated")
        c.execute(
            "select set_config('request.jwt.claims',%s,true)",
            (json.dumps(dict(sub=s["a"], role="authenticated")),),
        )
        raw = c.execute(
            "select r.account_id,rr.details,rr.reason from financial_records r join financial_record_revisions rr on rr.record_id=r.id and rr.user_id=r.user_id where r.id=any(%s::uuid[])",
            (ids,),
        ).fetchall()
        assert len(raw) == 1 and str(raw[0][0]) == dest
        raw_encoded = json.dumps(raw, default=str)
        assert s["ba"] not in raw_encoded and marker not in raw_encoded
    # Personal writers retain their same-owner boundary.
    with pytest.raises((AccountNotFound, HouseholdNotFound)):
        original.preview(user_id=s["a"], request=body, scope=PERSONAL)
    # Source-only Personal spending keeps the full loan cost, never destination principal.
    for actor, expected in [
        (s["a"], "0"),
        (s["b"], "400" if kind == "debt_payment" else "0"),
    ]:
        home = BudgetService(planners(s, actor)).home(actor, NOW.strftime("%Y-%m"), "UTC")
        dop = next((c for c in home["currencies"] if c["currency"] == "DOP"), None)
        assert dop is not None
        assert str(dop["net_spending_minor"]) == expected
    # Unrelated Personal write preserves full canonical groups and shared claim currentness.
    private = GoalService(planners(s, s["b"])).create(
        s["b"], GoalCreate(name="Private side goal", currency="DOP", target="10"), key()
    )
    assert private["goal"]["supported_minor"] == "0"
    assert get(s, s["a"], p)["contributions"][0]["applied_minor"] == "2000"


def test_view_only_own_correction_currentness_release_and_retry_revocation(lane):
    s = scene(lane)
    p = create(s, "budget")
    saved, body = money(
        s,
        s["b"],
        p,
        request("expense", s["ba"], "10", note="Private original note"),
        "spending",
    )
    cid = saved["plan"]["contributions"][0]["id"]
    correction = command(
        s,
        s["b"],
        p,
        wire.ContributionCorrection,
        activity=request(
            "expense", s["ba"], "15", expected_revision=1, reason="Receipt amount"
        ),
    )
    preview = s["plans"].money(
        s["b"], s["hid"], "budget", str(p["ref"]["id"]), correction, cid=cid
    )
    corrected = correction.model_copy(
        update={
            "activity": MoneyRequest.model_validate(
                preview["money"]["reviewed_request"]
                | {"preview_token": preview["money"]["preview_token"]}
            )
        }
    )
    k = key()
    first = s["plans"].money(
        s["b"], s["hid"], "budget", str(p["ref"]["id"]), corrected, k, cid=cid
    )
    assert first["plan"]["progress"]["spent_minor"] == "1500"
    assert "Private original note" not in json.dumps(get(s, s["a"], p), default=str)
    assert s["plans"].money(
        s["b"], s["hid"], "budget", str(p["ref"]["id"]), corrected, k, cid=cid
    )["replayed"]
    with pytest.raises(HouseholdNotFound):
        s["plans"].money(
            s["a"],
            s["hid"],
            "budget",
            str(p["ref"]["id"]),
            command(
                s, s["a"], p, wire.ContributionCorrection, activity=corrected.activity
            ),
            cid=cid,
        )
    s["plans"].replace_participants(
        s["a"],
        s["hid"],
        "budget",
        str(p["ref"]["id"]),
        command(s, s["a"], p, wire.ReplaceParticipants, participants=[]),
        key(),
    )
    with pytest.raises(HouseholdNotFound):
        s["plans"].money(
            s["b"], s["hid"], "budget", str(p["ref"]["id"]), corrected, k, cid=cid
        )


def test_one_pool_foreign_residuals_claims_private_write_included_and_unknown(lane):
    s = scene(lane)
    p = create(s, "goal")
    goals = GoalService(planners(s, s["b"]))
    private = goals.create(
        s["b"],
        GoalCreate(
            name="PRIVATE-OTHER-GOAL",
            currency="DOP",
            target="2000",
            destination_account_id=s["bd"],
        ),
        key(),
    )["goal"]["goal"]
    version = (
        s["records"]
        .get_account(user_id=s["b"], account_id=s["bd"], scope=PERSONAL)
        .account.version
    )
    goals.allocate(
        s["b"],
        AllocationWrite(
            changes=[
                dict(
                    goal_id=private["id"],
                    expected_version=private["version"],
                    account_id=s["bd"],
                    amount="800",
                )
            ],
            expected_account_versions={s["bd"]: version},
        ),
        key(),
    )
    # One actual account pool: 800 Personal + 150 explicitly shared = 950 of 1000.
    allocated = s["plans"].allocate(
        s["b"],
        s["hid"],
        "goal",
        str(p["ref"]["id"]),
        command(
            s,
            s["b"],
            p,
            wire.AllocationWrite,
            account_id=s["bd"],
            amount="150",
            expected_account_versions={s["bd"]: version},
        ),
        key(),
    )["plan"]
    allocation_id = allocated["allocations"][0]["id"]
    encoded = json.dumps(allocated, default=str)
    assert (
        private["id"] not in encoded
        and private["name"] not in encoded
        and s["bd"] not in encoded
    )
    with pytest.raises(RecordingInputError):
        s["plans"].allocate(
            s["b"],
            s["hid"],
            "goal",
            str(p["ref"]["id"]),
            command(
                s,
                s["b"],
                p,
                wire.AllocationWrite,
                account_id=s["bd"],
                amount="250",
                expected_account_versions={s["bd"]: version},
            ),
            key(),
        )
    # Personal unrelated definition update cannot recreate or privatize shared rows.
    current = goals.get(s["b"], private["id"])["goal"]
    goals.edit(
        s["b"],
        private["id"],
        GoalEdit(expected_version=current["version"], name="PRIVATE-RENAMED"),
        key(),
    )
    assert get(s, s["a"], p)["allocations"][0]["id"] == allocation_id
    state, accounts = storage.read(s["records"], s["b"])
    assert str(p["ref"]["id"]) not in state["goals"]
    assert state["links"] == {}
    transfer = personal(s, s["b"], request("transfer", s["ba"], "20", s["bd"]))
    added = link(s, s["b"], p, transfer, "goal_saving", treatment="included")["plan"]
    assert added["allocations"][0]["assigned_minor"] == "13000"
    assert added["progress"]["applied_minor"] == "15000"
    # A real later withdrawal creates unknown shared support, never min(balance,claim).
    personal(s, s["b"], request("expense", s["bd"], "200"))
    now = get(s, s["a"], p)
    assert now["progress"]["applied_minor"] is None
    assert now["contributions"][0]["applied_minor"] is None
    assert now["allocations"][0]["supported_minor"] is None
    assert "PRIVATE-RENAMED" not in json.dumps(now, default=str)
