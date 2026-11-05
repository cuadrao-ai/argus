"""All four canonical plan kinds, consent, private actuals and durable lifecycle."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from argus.domain.household import planning_schemas as wire
from argus.domain.household.errors import HouseholdNotFound
from argus.domain.household.financial import HouseholdFinancialService
from argus.domain.household.planning import SharedPlanningService
from argus.domain.recording.errors import RecordingInputError, StaleVersion

from tests.household.financial_fixtures import DSN, key, share
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


@pytest.mark.parametrize("kind", ["budget", "bill", "goal", "debt"])
def test_all_kinds_create_actuals_edit_archive_restore_and_safe_home_search(lane, kind):
    s = scene(lane)
    p = create(s, kind)
    assert sorted(r["amount_minor"] for r in p["responsibilities"]) == ["3000", "7000"]
    oid = p["occurrences"][0]["id"] if p["occurrences"] else None
    purpose = dict(
        budget="spending", bill="bill_payment", goal="goal_saving", debt="debt_payment"
    )[kind]
    if kind == "debt":
        share(s["households"], s["a"], s["hid"], s["loan"], s["bmid"], "edit")
    for actor, src, dest, amount in [
        (s["a"], s["aa"], s["ad"], "20"),
        (s["b"], s["ba"], s["bd"], "10"),
    ]:
        body = request(
            "transfer"
            if kind == "goal"
            else "debt_payment"
            if kind == "debt"
            else "expense",
            src,
            amount,
            dest if kind == "goal" else s["loan"] if kind == "debt" else None,
            **(
                dict(
                    principal="16" if amount == "20" else "8",
                    interest="3" if amount == "20" else "1",
                    fees="1",
                )
                if kind == "debt"
                else {}
            ),
        )
        money(s, actor, p, body, purpose, oid)
    view = get(s, s["b"], p)
    assert view["progress"]["applied_minor"] == "3000"
    assert view["progress"]["remaining_minor"] == "7000"
    if kind in {"bill", "debt", "goal"}:
        assert view["occurrences"][0]["applied_minor"] == "3000"
    assert all(
        not c["can_correct"]
        for c in view["contributions"]
        if c["person"]["membership_id"] == s["amid"]
    )
    with pytest.raises(HouseholdNotFound):
        s["plans"].edit(
            s["b"],
            s["hid"],
            kind,
            str(p["ref"]["id"]),
            command(s, s["b"], p, wire.EditPlan, definition=dict(name="Unauthorized")),
            key(),
        )
    updated = s["plans"].edit(
        s["a"],
        s["hid"],
        kind,
        str(p["ref"]["id"]),
        command(s, s["a"], p, wire.EditPlan, definition=dict(name="Updated shared")),
        key(),
    )["plan"]
    assert updated["definition"]["name"] == "Updated shared"
    archived = s["plans"].edit(
        s["a"],
        s["hid"],
        kind,
        str(p["ref"]["id"]),
        command(s, s["a"], p, wire.EditPlan, definition=dict(archived=True)),
        key(),
    )["plan"]
    assert archived["read_only"] and archived["can_restore"]
    assert not get(s, s["b"], p)["can_restore"]
    with pytest.raises(RecordingInputError, match="read-only"):
        s["plans"].release(
            s["b"],
            s["hid"],
            kind,
            str(p["ref"]["id"]),
            view["contributions"][-1]["id"],
            command(s, s["b"], p),
            key(),
        )
    restored = s["plans"].edit(
        s["a"],
        s["hid"],
        kind,
        str(p["ref"]["id"]),
        command(s, s["a"], p, wire.EditPlan, definition=dict(archived=False)),
        key(),
    )["plan"]
    assert not restored["read_only"]
    assert restored["progress"]["applied_minor"] == "3000"
    financial = HouseholdFinancialService(s["households"])
    home = financial.snapshot(s["b"], s["hid"])
    assert len(home["plans"]) == 1
    hits = financial.search(s["b"], s["hid"], "Updated shared", None, 10)
    assert hits["items"] == [
        dict(
            id=str(p["ref"]["id"]),
            kind="plan",
            title="Updated shared",
            account_id=None,
            activity_id=None,
            plan_ref=p["ref"],
        )
    ]
    encoded = json.dumps([view, home, hits], default=str)
    for private in (s["aa"], s["ad"]):
        assert private not in encoded
    with pytest.raises(HouseholdNotFound):
        get(s, s["c"], p)
    # A fresh adapter reconstructs the same canonical facts after response loss/reopen.
    fresh = SharedPlanningService(s["households"])
    assert (
        fresh.get(s["b"], s["hid"], kind, str(p["ref"]["id"]))["progress"]
        == restored["progress"]
    )


def test_refund_only_consent_does_not_publish_private_purchase(lane):
    s = scene(lane)
    p = create(s, "budget")
    bought = personal(
        s, s["b"], request("expense", s["ba"], "80", note="Private purchase marker")
    )
    returned = personal(
        s,
        s["b"],
        request(
            "refund", s["ba"], "5", purchase_activity_id=bought["activity"]["activity_id"]
        ),
    )
    link(s, s["b"], p, returned, "spending")
    progress = get(s, s["a"], p)["progress"]
    assert (
        progress["gross_minor"],
        progress["refunds_minor"],
        progress["spent_minor"],
        progress["remaining_minor"],
    ) == ("0", "500", "-500", "10500")
    assert "Private purchase marker" not in json.dumps(get(s, s["a"], p), default=str)


def test_release_extra_reassign_preserves_history_and_one_active_claim(lane):
    s = scene(lane)
    p = create(s, "budget")
    actual = personal(s, s["b"], request("expense", s["ba"], "20"))
    first = link(s, s["b"], p, actual, "spending")["plan"]
    with pytest.raises(RecordingInputError):
        link(s, s["b"], p, actual, "spending")
    cid = first["contributions"][0]["id"]
    s["plans"].release(
        s["b"], s["hid"], "budget", str(p["ref"]["id"]), cid, command(s, s["b"], p), key()
    )
    second = link(s, s["b"], p, actual, "spending")["plan"]
    assert sorted(c["status"] for c in second["contributions"]) == ["current", "released"]
    assert second["progress"]["spent_minor"] == "2000"
    with s["records"]._pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from financial_plan_links where activity_id=%s and released_at is null",
                (actual["activity"]["activity_id"],),
            ).fetchone()[0]
            == 1
        )


def test_cas_racing_definition_writes_and_retry_are_durable(lane):
    s = scene(lane)
    p = create(s, "budget")
    body = command(s, s["a"], p, wire.EditPlan, definition=dict(name="Reviewed change"))
    barrier = Barrier(2)

    def write(k):
        barrier.wait()
        try:
            return s["plans"].edit(
                s["a"], s["hid"], "budget", str(p["ref"]["id"]), body, k
            )
        except StaleVersion:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as workers:
        result = list(workers.map(write, [key(), key()]))
    assert sum(r == "stale" for r in result) == 1
    replay_key = key()
    body = command(s, s["a"], p, wire.EditPlan, definition=dict(name="Response lost"))
    first = s["plans"].edit(
        s["a"], s["hid"], "budget", str(p["ref"]["id"]), body, replay_key
    )
    retry = SharedPlanningService(s["households"]).edit(
        s["a"], s["hid"], "budget", str(p["ref"]["id"]), body, replay_key
    )
    assert retry["replayed"] and retry["plan"]["version"] == first["plan"]["version"]
