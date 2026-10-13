from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import RecordingInputError, StaleVersion
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.schemas import CreateFinancialAccountRequest, account_response

from tests.financial_accounts import test_loop_commands as shared
from tests.financial_accounts.test_loop_commands import NOW

scene = shared.scene


def account(scene, kind="cash", currency="DOP", amount="100"):
    service, user, _ = scene
    return service.create(
        user_id=user,
        idempotency_key=str(uuid4()),
        request=CreateFinancialAccountRequest(
            type=kind,
            currency=currency,
            amount=amount,
            as_of=NOW - timedelta(days=10) if amount else None,
        ),
        scope=PERSONAL,
    ).stored.account.id


def command(scene, **values):
    service, user, _ = scene
    money = MoneyService(service)
    request = MoneyRequest(occurred_at=NOW - timedelta(days=2), **values)
    preview = money.preview(user_id=user, request=request, scope=PERSONAL)
    assert preview["ready"]
    reviewed = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )
    return money, reviewed


def save(scene, **values):
    money, request = command(scene, **values)
    return money.write(
        user_id=scene[1], request=request, idempotency_key=str(uuid4()), scope=PERSONAL
    )


@pytest.mark.parametrize("kind", ["income", "refund"])
@pytest.mark.usefixtures("legacy_blank_accounts")
def test_incoming_preserves_unknown_and_credits_card(scene, kind):
    aid = account(scene, "cash", amount=None)
    receipt = save(scene, kind=kind, account_id=aid, amount="25")
    balance = receipt["accounts"][0].balance
    assert balance.state == "unknown" and balance.amount_minor is None
    assert balance.activity_since_tracking_minor == 2500


def test_pair_is_one_activity_with_two_opposing_movements_and_replays(scene):
    first, second = account(scene), account(scene)
    money, request = command(
        scene,
        kind="transfer",
        source_account_id=first,
        destination_account_id=second,
        amount="25",
    )
    result = money.write(
        user_id=scene[1], request=request, idempotency_key="pair", scope=PERSONAL
    )
    assert sorted(a.balance.amount_minor for a in result["accounts"]) == [7500, 12500]
    assert len(result["activity"]["legs"]) == 2
    replay = money.write(
        user_id=scene[1], request=request, idempotency_key="pair", scope=PERSONAL
    )
    assert replay["replayed"] and replay["activity"] == result["activity"]


def test_refunds_cap_and_wrong_account_correction(scene):
    first, second = account(scene), account(scene)
    purchase = save(
        scene, kind="expense", account_id=first, amount="40", category_id="shopping"
    )["activity"]
    refund = save(
        scene,
        kind="refund",
        account_id=second,
        amount="30",
        purchase_activity_id=purchase["activity_id"],
    )["activity"]
    assert refund["category_id"] == "shopping"
    with pytest.raises(RecordingInputError, match="refund_limit"):
        save(
            scene,
            kind="refund",
            account_id=second,
            amount="11",
            purchase_activity_id=purchase["activity_id"],
        )
    money = MoneyService(scene[0])
    request = MoneyRequest(
        kind="expense",
        account_id=second,
        amount="40",
        occurred_at=NOW - timedelta(days=2),
        category_id="shopping",
        expected_revision=1,
        reason="Wrong account",
    )
    preview = money.preview(
        user_id=scene[1],
        request=request,
        activity_id=purchase["activity_id"],
        scope=PERSONAL,
    )
    assert set(preview["expected_versions"]) == {first, second}
    fixed = money.write(
        user_id=scene[1],
        request=MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
            update={"preview_token": preview["preview_token"]}
        ),
        activity_id=purchase["activity_id"],
        idempotency_key="fix",
        scope=PERSONAL,
    )
    assert fixed["activity"]["legs"][0]["account_id"] == second
    assert (
        account_response(
            scene[0].get(user_id=scene[1], account_id=first, scope=PERSONAL)
        ).balance.amount_minor
        == 10000
    )


def test_month_received_refund_can_make_net_negative_and_card_credit(scene):
    from argus.domain.recording.loop_reads import home_response

    aid = account(scene, "credit_card", amount="10")
    save(scene, kind="refund", account_id=aid, amount="25")
    card = account_response(
        scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL)
    )
    assert card.balance.amount_minor == 1500 and card.balance.credit_minor == 1500
    home = home_response(
        scene[0].list_accounts(user_id=scene[1], scope=PERSONAL),
        "2026-09",
        "America/Santo_Domingo",
        NOW,
    )
    dop = next(g for g in home["currencies"] if g["currency"] == "DOP")
    assert dop["refunds_minor"] == "2500" and dop["net_spending_minor"] == "-2500"
    assert dop["gross_income_minor"] == "0" and dop["gross_purchases_minor"] == "0"


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("amount", "20", "refund_limit"),
        ("category_id", "dining", "linked_refund_category"),
        ("occurred_at", NOW - timedelta(days=1), "refund_before_purchase"),
    ],
)
def test_linked_purchase_corrections_preserve_refund_truth(scene, field, value, error):
    aid = account(scene)
    purchase = save(
        scene, kind="expense", account_id=aid, amount="40", category_id="shopping"
    )["activity"]
    save(
        scene,
        kind="refund",
        account_id=aid,
        amount="30",
        purchase_activity_id=purchase["activity_id"],
    )
    body = {
        "kind": "expense",
        "account_id": aid,
        "amount": "40",
        "category_id": "shopping",
        "occurred_at": NOW - timedelta(days=2),
        "expected_revision": 1,
        "reason": "Fix",
    }
    body[field] = value
    with pytest.raises(RecordingInputError, match=error):
        MoneyService(scene[0]).preview(
            user_id=scene[1],
            request=MoneyRequest(**body),
            activity_id=purchase["activity_id"],
            scope=PERSONAL,
        )


def test_linked_purchase_cannot_change_currency(scene):
    first, foreign = account(scene), account(scene, currency="USD")
    purchase = save(scene, kind="expense", account_id=first, amount="40")["activity"]
    save(
        scene,
        kind="refund",
        account_id=first,
        amount="30",
        purchase_activity_id=purchase["activity_id"],
    )
    with pytest.raises(RecordingInputError, match="linked_refund_currency"):
        MoneyService(scene[0]).preview(
            user_id=scene[1],
            activity_id=purchase["activity_id"],
            request=MoneyRequest(
                kind="expense",
                account_id=foreign,
                amount="40",
                occurred_at=NOW - timedelta(days=2),
                expected_revision=1,
                reason="Fix",
            ),
            scope=PERSONAL,
        )


def test_stale_one_side_and_incomplete_version_set_do_not_write(scene):
    from argus.domain.recording.schemas import EditFinancialAccountRequest

    first, second = account(scene), account(scene)
    money, request = command(
        scene,
        kind="transfer",
        source_account_id=first,
        destination_account_id=second,
        amount="25",
    )
    incomplete = request.model_copy(update={"expected_versions": {first: 1}})
    with pytest.raises(StaleVersion):
        money.write(
            user_id=scene[1],
            request=incomplete,
            idempotency_key="missing",
            scope=PERSONAL,
        )
    scene[0].edit(
        user_id=scene[1],
        account_id=second,
        request=EditFinancialAccountRequest(expected_version=1, nickname="Changed"),
        scope=PERSONAL,
    )
    with pytest.raises(StaleVersion):
        money.write(
            user_id=scene[1], request=request, idempotency_key="stale", scope=PERSONAL
        )
    assert not scene[0].get(user_id=scene[1], account_id=first, scope=PERSONAL).expenses


def test_paired_coverage_answers_are_independent(scene):
    first, second = account(scene), account(scene)
    service, user, _ = scene
    money = MoneyService(service)
    body = MoneyRequest(
        kind="transfer",
        source_account_id=first,
        destination_account_id=second,
        amount="20",
        occurred_at=NOW - timedelta(days=10),
    )
    preview = money.preview(user_id=user, request=body, scope=PERSONAL)
    assert not preview["ready"]
    answers = [
        {
            "account_id": effect["account_id"],
            "observation_id": q["observation_id"],
            "included": effect["account_id"] == first,
        }
        for effect in preview["affected_accounts"]
        for q in effect["observations"]
    ]
    preview = money.preview(
        user_id=user,
        request=body.model_copy(
            update={
                "coverage": [
                    __import__(
                        "argus.domain.recording.money_schemas", fromlist=["MoneyCoverage"]
                    ).MoneyCoverage(**a)
                    for a in answers
                ]
            }
        ),
        scope=PERSONAL,
    )
    result = money.write(
        user_id=user,
        request=MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
            update={"preview_token": preview["preview_token"]}
        ),
        idempotency_key="covered-pair",
        scope=PERSONAL,
    )
    balances = {a.id: a.balance.amount_minor for a in result["accounts"]}
    assert balances == {first: 10000, second: 12000}


def test_omitted_refund_link_preserves_cap_and_explicit_null_unlinks(scene):
    aid = account(scene)
    purchase = save(
        scene, kind="expense", account_id=aid, amount="40", category_id="shopping"
    )["activity"]
    refund = save(
        scene,
        kind="refund",
        account_id=aid,
        amount="30",
        purchase_activity_id=purchase["activity_id"],
    )["activity"]
    money = MoneyService(scene[0])
    replacement = dict(
        kind="refund",
        account_id=aid,
        amount="50",
        occurred_at=NOW - timedelta(days=2),
        expected_revision=1,
        reason="Correct received amount",
    )
    with pytest.raises(RecordingInputError, match="refund_limit"):
        money.preview(
            user_id=scene[1],
            request=MoneyRequest(**replacement),
            activity_id=refund["activity_id"],
            scope=PERSONAL,
        )
    replacement["amount"] = "25"
    preview = money.preview(
        user_id=scene[1],
        request=MoneyRequest(**replacement),
        activity_id=refund["activity_id"],
        scope=PERSONAL,
    )
    assert preview["reviewed_request"]["purchase_activity_id"] == purchase["activity_id"]
    assert preview["reviewed_request"]["category_id"] == "shopping"
    replacement.update(amount="50", purchase_activity_id=None)
    preview = money.preview(
        user_id=scene[1],
        request=MoneyRequest(**replacement),
        activity_id=refund["activity_id"],
        scope=PERSONAL,
    )
    assert (
        preview["ready"] and preview["reviewed_request"]["purchase_activity_id"] is None
    )


def test_each_pair_observation_keeps_its_own_source_zone(scene):
    service, user, _ = scene
    ids = []
    for zone in ("Pacific/Honolulu", "Pacific/Kiritimati"):
        stored = service.create(
            user_id=user,
            idempotency_key=str(uuid4()),
            request=CreateFinancialAccountRequest(
                type="cash",
                currency="DOP",
                amount="100",
                as_of=NOW - timedelta(days=10),
                time_zone=zone,
            ),
            scope=PERSONAL,
        ).stored
        ids.append(stored.account.id)
    preview = MoneyService(service).preview(
        user_id=user,
        request=MoneyRequest(
            kind="transfer",
            source_account_id=ids[0],
            destination_account_id=ids[1],
            amount="10",
            occurred_at=NOW - timedelta(days=11),
        ),
        scope=PERSONAL,
    )
    zones = {
        effect["account_id"]: effect["observations"][0]["time_zone"]
        for effect in preview["affected_accounts"]
    }
    assert zones == dict(
        zip(ids, ("Pacific/Honolulu", "Pacific/Kiritimati"), strict=True)
    )


def test_refund_preserve_link_and_explicit_unlink_have_distinct_receipt_identity(scene):
    from argus.domain.recording.errors import IdempotencyConflict

    aid = account(scene)
    purchase = save(scene, kind="expense", account_id=aid, amount="40")["activity"]
    refund = save(
        scene,
        kind="refund",
        account_id=aid,
        amount="30",
        purchase_activity_id=purchase["activity_id"],
    )["activity"]
    money = MoneyService(scene[0])
    body = MoneyRequest(
        kind="refund",
        account_id=aid,
        amount="25",
        occurred_at=NOW - timedelta(days=2),
        expected_revision=1,
        reason="Correct amount",
    )
    preview = money.preview(
        user_id=scene[1], request=body, activity_id=refund["activity_id"], scope=PERSONAL
    )
    omitted = body.model_copy(
        update={
            "expected_versions": preview["expected_versions"],
            "preview_token": preview["preview_token"],
        }
    )
    first = money.write(
        user_id=scene[1],
        request=omitted,
        activity_id=refund["activity_id"],
        idempotency_key="omitted-link",
        scope=PERSONAL,
    )
    assert first["activity"]["purchase_activity_id"] == purchase["activity_id"]
    replay = money.write(
        user_id=scene[1],
        request=omitted,
        activity_id=refund["activity_id"],
        idempotency_key="omitted-link",
        scope=PERSONAL,
    )
    assert replay["replayed"] and replay["activity"] == first["activity"]
    with pytest.raises(IdempotencyConflict):
        money.write(
            user_id=scene[1],
            request=omitted.model_copy(update={"purchase_activity_id": None}),
            activity_id=refund["activity_id"],
            idempotency_key="omitted-link",
            scope=PERSONAL,
        )
