from datetime import datetime, timedelta, timezone
from uuid import uuid4

from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.loop import (
    Coverage,
    ExpenseRecord,
    ExpenseRevision,
    position,
)
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.records import OpeningRecord, OpeningRevision
from argus.domain.recording.schemas import CreateFinancialAccountRequest

from tests.financial_accounts import test_loop_commands as shared
from tests.financial_accounts.test_loop_commands import NOW

scene = shared.scene
ZONE = "America/Santo_Domingo"


def opened(scene, as_of):
    service, user, _ = scene
    return service.create(
        user_id=user,
        idempotency_key=str(uuid4()),
        request=CreateFinancialAccountRequest(
            type="checking",
            currency="DOP",
            amount=None if as_of is None else "1000",
            as_of=as_of,
            time_zone=ZONE,
        ),
        scope=PERSONAL,
    ).stored.account.id


def effect(scene, aid, occurred_at):
    service, user, _ = scene
    preview = MoneyService(service).preview(
        user_id=user,
        request=MoneyRequest(
            kind="expense", account_id=aid, amount="200", occurred_at=occurred_at
        ),
        scope=PERSONAL,
    )
    return preview, preview["affected_accounts"][0]


def test_movement_entered_today_after_the_opening_is_not_asked(scene):
    aid = opened(scene, NOW - timedelta(hours=2))
    preview, account = effect(scene, aid, NOW - timedelta(hours=1))
    assert preview["ready"]
    assert account["observations"] == []
    assert [s["reason"] for s in account["skipped_observations"]] == [
        "entered_after_observation"
    ]
    assert account["after"]["amount_minor"] == 80000


def test_movement_entered_today_before_the_opening_time_is_asked(scene):
    aid = opened(scene, NOW)
    preview, account = effect(scene, aid, NOW - timedelta(hours=1))
    assert not preview["ready"]
    assert len(account["observations"]) == 1
    assert account["skipped_observations"] == []


def test_movement_backdated_before_the_opening_day_is_asked(scene):
    aid = opened(scene, NOW - timedelta(hours=2))
    preview, account = effect(scene, aid, NOW - timedelta(days=3))
    assert not preview["ready"]
    assert len(account["observations"]) == 1


def test_movement_backdated_onto_the_opening_day_is_asked(scene):
    opening = (NOW - timedelta(days=3)).replace(hour=10)
    aid = opened(scene, opening)
    preview, account = effect(scene, aid, opening + timedelta(hours=4))
    assert not preview["ready"]
    assert len(account["observations"]) == 1


def test_movement_dated_after_the_opening_day_is_not_asked(scene):
    aid = opened(scene, NOW - timedelta(days=5))
    preview, account = effect(scene, aid, NOW - timedelta(days=2))
    assert preview["ready"]
    assert [s["reason"] for s in account["skipped_observations"]] == [
        "after_observation_day"
    ]
    assert account["after"]["amount_minor"] == 80000


def test_account_without_a_recorded_balance_has_no_question(scene):
    aid = opened(scene, None)
    preview, account = effect(scene, aid, NOW - timedelta(hours=1))
    assert preview["ready"]
    assert account["observations"] == [] and account["skipped_observations"] == []
    assert account["after"]["state"] == "unknown"


def test_answer_given_under_the_earlier_same_day_rule_still_stands():
    day = datetime(2026, 10, 12, 23, tzinfo=timezone.utc)
    opening = OpeningRecord(
        "opening",
        "account",
        (OpeningRevision(1, 100000, day, ZONE, None, None, day),),
    )
    later = day + timedelta(minutes=30)
    expense = ExpenseRecord(
        "expense",
        "account",
        (ExpenseRevision(1, 20000, later, ZONE, None, None, None, None, later),),
    )
    answered = (Coverage("opening", 1, "expense", 1, True),)
    assert position(opening, (), (expense,), answered).amount_minor == 100000
    assert position(opening, (), (expense,), ()).amount_minor == 80000
