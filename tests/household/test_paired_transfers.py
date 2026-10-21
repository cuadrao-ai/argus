import json
from datetime import timedelta

import pytest
from argus.domain.household.errors import HouseholdNotFound
from argus.domain.household.financial import HouseholdFinancialService
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.service import FinancialAccountService

from tests.household.financial_fixtures import (
    DSN,
    NOW,
    account,
    command,
    key,
    money,
    reviewed,
    setup,
    share,
)
from tests.household.shared_plan_fixtures import (
    create,
    get,
    link,
    personal,
    request,
    scene,
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def test_household_pair_retry_and_revoked_source_are_currency_safe(lane, monkeypatch):
    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    service, records, (a, b, _) = lane
    hid, mid, _ = setup(lane)
    source, dest = (
        account(records, a, currency="USD"),
        account(records, a, currency="DOP"),
    )
    share(service, a, hid, source, mid, "edit")
    share(service, a, hid, dest, mid, "edit")
    body = MoneyRequest(
        kind="transfer",
        source_account_id=source,
        destination_account_id=dest,
        amount="1",
        destination_amount="60",
        occurred_at=NOW - timedelta(days=1),
    )
    body = reviewed(service, a, hid, body)
    operation = key()
    saved = money(service, a, hid, body, k=operation)
    assert money(service, a, hid, body, k=operation)["replayed"]
    aid = saved["activity"]["activity"]["activity_id"]
    command(
        service,
        a,
        "withdraw:" + source,
        lambda: service.replace_grants(
            user_id=a, household_id=hid, account_id=source, recipients=[]
        ),
        hid,
    )
    reader = HouseholdFinancialService(service)
    view = reader.detail(b, hid, dest)["activities"][0]
    assert view["private_counterpart"] and not view["can_edit"]
    assert view["activity"]["currency"] == "DOP"
    assert view["activity"]["amount_minor"] is None
    assert view["activity"]["legs"][0]["amount_minor"] == 6000
    encoded = json.dumps([view, reader.history(b, hid, aid)], default=str)
    assert source not in encoded and '"USD"' not in encoded
    denied = body.model_copy(
        update={
            "expected_revision": 1,
            "expected_versions": {},
            "preview_token": None,
            "reason": "Denied correction",
        }
    )
    with pytest.raises(HouseholdNotFound):
        money(service, b, hid, denied, aid=aid)
    assert (
        records.get_account(user_id=a, account_id=dest, scope=PERSONAL).account.version
        == 2
    )


@pytest.mark.parametrize(
    ("source_currency", "destination_currency", "expected_amount"),
    [("USD", "DOP", None), ("DOP", "USD", None), ("DOP", "DOP", "100")],
)
def test_shared_goal_corrected_private_pair_discloses_only_plan_denomination(
    lane, monkeypatch, source_currency, destination_currency, expected_amount
):
    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    s = scene(lane)
    goal = create(s, "goal")
    original = personal(s, s["b"], request("transfer", s["ba"], "20", s["bd"]))
    linked = link(s, s["b"], goal, original, "goal_saving")["plan"]
    assert linked["contributions"][0]["applied_minor"] == "2000"
    source = account(s["records"], s["b"], currency=source_currency)
    destination = (
        s["bd"]
        if destination_currency == "DOP"
        else account(s["records"], s["b"], currency=destination_currency)
    )
    marker = key()
    activity_id = original["activity"]["activity_id"]
    service = MoneyService(FinancialAccountService(s["records"], clock=lambda: NOW))
    body = request(
        "transfer",
        source,
        "1",
        destination,
        destination_amount="60" if source_currency != destination_currency else "1",
        expected_revision=1,
        reason="Correct original source and actual amounts",
        note=marker,
    )
    preview = service.preview(
        user_id=s["b"], request=body, activity_id=activity_id, scope=PERSONAL
    )
    assert preview["ready"]
    reviewed = MoneyRequest.model_validate(
        preview["reviewed_request"] | {"preview_token": preview["preview_token"]}
    )
    corrected = service.write(
        user_id=s["b"],
        activity_id=activity_id,
        idempotency_key=key(),
        request=reviewed,
        scope=PERSONAL,
    )
    assert corrected["activity"]["revision"] == 2
    before = {
        actor: s["records"].list_accounts(user_id=actor, scope=PERSONAL)
        for actor in (s["a"], s["b"])
    }
    with s["records"]._pool.connection() as c:
        receipts_before = c.execute(
            "select count(*) from financial_activity_receipts where user_id=any(%s::uuid[])",
            (list(before),),
        ).fetchone()
    public = get(s, s["a"], goal)
    contribution = public["contributions"][0]
    assert contribution["amount_minor"] == expected_amount
    assert contribution["currency"] == goal["definition"]["currency"]
    assert contribution["applied_minor"] is None
    assert contribution["status"] == "needs_review"
    assert contribution["original"] is None and not contribution["can_correct"]
    assert public["progress"]["applied_minor"] is None
    encoded = json.dumps(public, default=str)
    assert all(
        value not in encoded for value in (source, destination, activity_id, marker)
    )
    assert '"USD"' not in encoded
    owner = get(s, s["b"], goal)["contributions"][0]
    assert owner["amount_minor"] == expected_amount and owner["applied_minor"] is None
    assert owner["original"]["activity_id"] == activity_id and owner["can_correct"]
    with pytest.raises(HouseholdNotFound):
        service.write(
            user_id=s["a"],
            activity_id=activity_id,
            idempotency_key=key(),
            request=reviewed,
            scope=PERSONAL,
        )
    assert {
        actor: s["records"].list_accounts(user_id=actor, scope=PERSONAL)
        for actor in before
    } == before
    assert (
        service.detail(user_id=s["b"], activity_id=activity_id, scope=PERSONAL)
        == corrected["activity"]
    )
    with s["records"]._pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from financial_activity_receipts where user_id=any(%s::uuid[])",
                (list(before),),
            ).fetchone()
            == receipts_before
        )
