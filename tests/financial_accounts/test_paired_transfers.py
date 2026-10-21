from datetime import timedelta

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_schemas import MoneyRequest

from tests.financial_accounts import test_loop_commands as shared
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import account, command

scene = shared.scene


def test_pair_records_independent_actual_amounts(scene, monkeypatch):
    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    source, destination = account(scene, currency="USD"), account(scene, currency="DOP")
    money, request = command(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=destination,
        amount="10.25",
        destination_amount="615.75",
    )
    receipt = money.write(
        user_id=scene[1], request=request, idempotency_key="paired", scope=PERSONAL
    )
    legs = {leg["role"]: leg for leg in receipt["activity"]["legs"]}
    assert (legs["source"]["amount_minor"], legs["source"]["currency"]) == (1025, "USD")
    assert (legs["destination"]["amount_minor"], legs["destination"]["currency"]) == (
        61575,
        "DOP",
    )
    assert legs["source"]["balance_movement_minor"] == -1025
    assert legs["destination"]["balance_movement_minor"] == 61575
    assert (
        money.write(
            user_id=scene[1], request=request, idempotency_key="paired", scope=PERSONAL
        )["activity"]
        == receipt["activity"]
    )


@pytest.mark.parametrize(
    "source_currency,amount,destination_currency,received,expected",
    [
        ("JPY", "25", "USD", "0.17", 17),
        ("USD", "10.25", "KWD", "3.123", 3123),
        ("DOP", "10.25", "DOP", "10.250", None),
    ],
)
def test_account_precision_owns_each_amount(
    scene, monkeypatch, source_currency, amount, destination_currency, received, expected
):
    from argus.domain.recording.errors import RecordingInputError

    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    source = account(scene, currency=source_currency)
    dest = account(scene, currency=destination_currency)
    values = dict(
        kind="transfer",
        source_account_id=source,
        destination_account_id=dest,
        amount=amount,
        destination_amount=received,
    )
    if expected is None:
        with pytest.raises(RecordingInputError, match="amount_precision"):
            command(scene, **values)
    else:
        money, request = command(scene, **values)
        result = money.write(
            user_id=scene[1], request=request, idempotency_key="precision", scope=PERSONAL
        )
        assert (
            next(
                leg for leg in result["activity"]["legs"] if leg["role"] == "destination"
            )["amount_minor"]
            == expected
        )


@pytest.mark.parametrize(
    "received,error",
    [
        (None, "destination_amount_required"),
        ("0", "amount_positive_required"),
        ("-1", "amount_positive_required"),
        ("1.001", "amount_precision"),
        ("bogus", "amount_invalid"),
        ("92233720368547758.08", "amount_out_of_range"),
    ],
)
def test_refused_pair_has_no_account_effect(scene, monkeypatch, received, error):
    from argus.domain.recording.errors import RecordingInputError
    from argus.domain.recording.money_service import MoneyService

    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    source, dest = account(scene, currency="USD"), account(scene, currency="DOP")
    money = MoneyService(scene[0])
    body = MoneyRequest(
        kind="transfer",
        source_account_id=source,
        destination_account_id=dest,
        amount="1",
        destination_amount=received,
        occurred_at=NOW - timedelta(days=2),
    )
    with pytest.raises(RecordingInputError, match=error):
        money.write(
            user_id=scene[1], request=body, idempotency_key="refused", scope=PERSONAL
        )
    for aid in (source, dest):
        stored = scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL)
        assert stored.account.version == 1 and not stored.expenses


def test_gate_blocks_new_mixed_pairs_but_not_same_currency(scene, monkeypatch):
    from argus.domain.recording.errors import RecordingInputError

    monkeypatch.delenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", raising=False)
    source, dest = account(scene, currency="USD"), account(scene, currency="DOP")
    with pytest.raises(RecordingInputError, match="cross_currency_transfers_disabled"):
        command(
            scene,
            kind="transfer",
            source_account_id=source,
            destination_account_id=dest,
            amount="1",
            destination_amount="60",
        )
    same = account(scene, currency="USD")
    money, body = command(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=same,
        amount="1",
        destination_amount="1.00",
    )
    assert (
        money.write(
            user_id=scene[1], request=body, idempotency_key="same", scope=PERSONAL
        )["activity"]["amount"]
        == "1.00"
    )
    with pytest.raises(RecordingInputError, match="transfer_amount_mismatch"):
        command(
            scene,
            kind="transfer",
            source_account_id=source,
            destination_account_id=same,
            amount="1",
            destination_amount="2",
        )


@pytest.mark.parametrize(
    "kind",
    ["expense", "income", "refund", "card_payment", "debt_payment", "payment_reversal"],
)
def test_destination_amount_is_transfer_only(scene, kind):
    from argus.domain.recording.errors import RecordingInputError

    aid = account(scene)
    values = dict(kind=kind, amount="1", destination_amount="1")
    if kind in {"card_payment", "debt_payment", "payment_reversal"}:
        values.update(
            source_account_id=aid,
            destination_account_id=account(
                scene, "credit_card" if kind == "card_payment" else "other_debt"
            ),
        )
    else:
        values["account_id"] = aid
    with pytest.raises(RecordingInputError, match="field_not_applicable"):
        command(scene, **values)


def test_hidden_source_denomination_is_absent_in_both_projections(scene, monkeypatch):
    from argus.domain.household.access import AccountAccess, HouseholdFinancialScope
    from argus.domain.household.projection import activity as household_activity
    from argus.domain.recording.money_reads import (
        groups,
        render_activity,
        visible_activity,
    )

    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    source, dest = account(scene, currency="JPY"), account(scene, currency="USD")
    money, body = command(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=dest,
        amount="100",
        destination_amount="0.70",
    )
    saved = money.write(
        user_id=scene[1], request=body, idempotency_key="privacy", scope=PERSONAL
    )
    records = scene[0].list_accounts(user_id=scene[1], scope=PERSONAL)
    history = groups(records)
    aid = saved["activity"]["activity_id"]
    personal = visible_activity(render_activity(aid, history[aid]), {dest}, history)
    scope = HouseholdFinancialScope(
        scene[1],
        "synthetic",
        "synthetic",
        1,
        {dest: AccountAccess(scene[1], "Synthetic", "view")},
        {},
    )
    household = household_activity(scope, records, aid)
    for view in (personal, household["activity"]):
        assert view["amount"] is None and view["amount_minor"] is None
        assert view["currency"] == "USD" and view["currency_fraction_digits"] == 2
        assert [
            (leg["account_id"], leg["currency"], leg["amount"]) for leg in view["legs"]
        ] == [(dest, "USD", "0.70")]
        assert view["note"] is None and view["recorded_by"] is None
    assert household["private_counterpart"] and not household["can_edit"]


def test_old_serialized_requests_and_nested_envelopes_keep_exact_hashes():
    import json
    from pathlib import Path

    from argus.domain.recording.money_plan import request_identity
    from pydantic import BaseModel

    class Envelope(BaseModel):
        activity: MoneyRequest

    fixtures = json.loads(
        (Path(__file__).parent / "fixtures/paired_transfer_legacy.json").read_text()
    )
    for frozen in fixtures:
        request = MoneyRequest.model_validate(frozen["input"])
        assert request.model_dump(mode="json") == frozen["serialized"]
        assert (
            request_identity(request, "00000000-0000-4000-8000-000000000001")
            == frozen["identity"]
        )
        assert Envelope(activity=request).model_dump(mode="json") == frozen["nested"]
        assert (
            MoneyRequest.model_validate(
                request.model_dump(mode="json") | {"destination_amount": None}
            ).model_dump(mode="json")
            == frozen["serialized"]
        )


def test_changed_destination_conflicts_and_correction_preserves_exact_history(
    scene, monkeypatch
):
    from argus.domain.recording.errors import IdempotencyConflict

    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    source, dest = account(scene, currency="USD"), account(scene, currency="DOP")
    money, body = command(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=dest,
        amount="1",
        destination_amount="60",
    )
    first = money.write(
        user_id=scene[1], request=body, idempotency_key="original", scope=PERSONAL
    )
    with pytest.raises(IdempotencyConflict):
        money.write(
            user_id=scene[1],
            request=body.model_copy(update={"destination_amount": "61"}),
            idempotency_key="original",
            scope=PERSONAL,
        )
    correction = body.model_copy(
        update={
            "amount": "2",
            "destination_amount": "119",
            "expected_revision": 1,
            "expected_versions": {},
            "preview_token": None,
            "reason": "Actual received amount",
        }
    )
    aid = first["activity"]["activity_id"]
    preview = money.preview(
        user_id=scene[1], request=correction, activity_id=aid, scope=PERSONAL
    )
    reviewed = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )
    changed = money.write(
        user_id=scene[1],
        request=reviewed,
        activity_id=aid,
        idempotency_key="corrected",
        scope=PERSONAL,
    )
    assert changed["activity"]["revision"] == 2
    assert [leg["amount_minor"] for leg in changed["activity"]["legs"]] == [200, 11900]
    assert (
        money.write(
            user_id=scene[1], request=body, idempotency_key="original", scope=PERSONAL
        )["activity"]
        == first["activity"]
    )
    assert (
        len(money.history(user_id=scene[1], activity_id=aid, scope=PERSONAL)["items"])
        == 2
    )


def test_plan_matcher_never_credits_source_summary_for_mixed_pair(scene, monkeypatch):
    from argus.domain.planning.goal_model import transfer_matches
    from argus.domain.planning.shared_claims import credit

    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    source, dest = account(scene, currency="USD"), account(scene, currency="DOP")
    money, body = command(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=dest,
        amount="1",
        destination_amount="60",
    )
    actual = money.write(
        user_id=scene[1], request=body, idempotency_key="plan-denied", scope=PERSONAL
    )["activity"]
    assert not transfer_matches(actual, source, dest, "USD")
    assert not transfer_matches(actual, source, dest, "DOP")
    accepted = dict(
        currency="USD",
        kind="transfer",
        legs=[(leg["role"], leg["account_id"]) for leg in actual["legs"]],
    )
    assert credit(actual, accepted, "funding", {}, []) is None


def test_existing_personal_and_household_plan_envelopes_keep_frozen_hashes():
    import importlib
    import json
    from pathlib import Path

    from argus.domain.backtest_admission import canonical_hash

    fixtures = json.loads(
        (
            Path(__file__).parent / "fixtures/paired_transfer_nested_legacy.json"
        ).read_text()
    )
    for frozen in fixtures:
        model = getattr(importlib.import_module(frozen["module"]), frozen["name"])
        serialized = model.model_validate(frozen["input"]).model_dump(mode="json")
        assert serialized == frozen["serialized"]
        assert canonical_hash(serialized) == frozen["identity"]


@pytest.mark.parametrize("kind", ["card_payment", "debt_payment", "payment_reversal"])
def test_mixed_payment_pairs_remain_refused(scene, monkeypatch, kind):
    from argus.domain.recording.errors import RecordingInputError

    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    source = account(scene, currency="USD")
    dest = account(
        scene, "credit_card" if kind == "card_payment" else "other_debt", currency="DOP"
    )
    with pytest.raises(RecordingInputError, match="currency_mismatch"):
        command(
            scene,
            kind=kind,
            source_account_id=source,
            destination_account_id=dest,
            amount="1",
        )
    assert all(
        not scene[0].get(user_id=scene[1], account_id=aid, scope=PERSONAL).expenses
        for aid in [source, dest]
    )


def test_replacing_destination_retires_exact_old_leg_and_preserves_replays(
    scene, monkeypatch
):
    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    source, original = account(scene, currency="USD"), account(scene, currency="DOP")
    replacement = account(scene, currency="USD")
    money, body = command(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=original,
        amount="1",
        destination_amount="60",
    )
    first = money.write(
        user_id=scene[1], request=body, idempotency_key="initial", scope=PERSONAL
    )
    aid = first["activity"]["activity_id"]
    for number, destination, amount in [(1, replacement, "1"), (2, original, "61")]:
        correction = body.model_copy(
            update={
                "destination_account_id": destination,
                "destination_amount": amount,
                "expected_versions": {},
                "expected_revision": number,
                "reason": "Correct bank account",
                "preview_token": None,
            }
        )
        preview = money.preview(
            user_id=scene[1], request=correction, activity_id=aid, scope=PERSONAL
        )
        assert set(preview["expected_versions"]) == {source, original, replacement}
        reviewed = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
            update={"preview_token": preview["preview_token"]}
        )
        result = money.write(
            user_id=scene[1],
            request=reviewed,
            activity_id=aid,
            idempotency_key=f"revision-{number}",
            scope=PERSONAL,
        )
        assert result["activity"]["revision"] == number + 1
        retired = original if destination == replacement else replacement
        old_record = (
            scene[0].get(user_id=scene[1], account_id=retired, scope=PERSONAL).expenses[0]
        )
        assert not old_record.current.active and old_record.current.amount_minor == 0
    assert (
        money.write(
            user_id=scene[1], request=body, idempotency_key="initial", scope=PERSONAL
        )["activity"]
        == first["activity"]
    )
    assert [
        leg["amount_minor"]
        for leg in money.detail(user_id=scene[1], activity_id=aid, scope=PERSONAL)["legs"]
    ] == [100, 6100]


def test_actual_goal_link_refuses_mixed_transfer_without_a_claim(scene, monkeypatch):
    from argus.domain.recording.errors import RecordingInputError

    from tests.financial_accounts.test_goals import link, setup_goal

    monkeypatch.setenv("ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED", "true")
    source, dest = (
        account(scene, currency="USD"),
        account(scene, "savings", currency="DOP"),
    )
    planner, _, goal = setup_goal(scene, dest)
    money, body = command(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=dest,
        amount="1",
        destination_amount="60",
    )
    actual = money.write(
        user_id=scene[1], request=body, idempotency_key="mixed-goal", scope=PERSONAL
    )["activity"]
    before = planner.get(scene[1], goal["id"])
    with pytest.raises(RecordingInputError, match="goal_contribution_mismatch"):
        link(scene, planner, goal, actual)
    assert planner.candidates(scene[1], goal["id"])["items"] == []
    assert planner.get(scene[1], goal["id"]) == before


@pytest.mark.parametrize(
    "roles",
    [
        [],
        ["source"],
        ["destination"],
        ["source", "source"],
        ["source", "destination", "destination"],
    ],
)
def test_incomplete_or_duplicated_transfer_legs_never_match_plan_currency(roles):
    from argus.domain.recording.money_reads import activity_in_currency

    assert not activity_in_currency(
        dict(
            kind="transfer",
            currency="USD",
            legs=[dict(role=role, currency="USD") for role in roles],
        ),
        "USD",
    )


def test_hidden_same_currency_source_never_matches_plan_currency(scene):
    from argus.domain.recording.money_reads import (
        activity_in_currency,
        groups,
        visible_activity,
    )

    source, dest = account(scene, currency="USD"), account(scene, currency="USD")
    money, body = command(
        scene,
        kind="transfer",
        source_account_id=source,
        destination_account_id=dest,
        amount="1",
    )
    full = money.write(
        user_id=scene[1], request=body, idempotency_key="partial-pair", scope=PERSONAL
    )["activity"]
    records = scene[0].list_accounts(user_id=scene[1], scope=PERSONAL)
    partial = visible_activity(full, {dest}, groups(records))
    assert not activity_in_currency(partial, "USD")
