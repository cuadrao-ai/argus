from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import RecordingInputError
from argus.domain.recording.loop import (
    Coverage,
    ExpenseRecord,
    ExpenseRevision,
    position,
)
from argus.domain.recording.loop_schemas import CheckRequest, LoopOpeningRequest
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.records import OpeningRecord, OpeningRevision
from argus.domain.recording.repository import InMemoryFinancialAccountRepository
from argus.domain.recording.schemas import CreateFinancialAccountRequest
from argus.domain.recording.service import FinancialAccountService

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


SD = ZoneInfo(ZONE)


def local(day, hour, minute=0, second=0):
    return datetime(2026, 10, day, hour, minute, second, tzinfo=SD)


class Clock:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at


def world(at):
    clock = Clock(at)
    service = FinancialAccountService(InMemoryFinancialAccountRepository(clock), clock)
    return service, str(uuid4()), clock


def open_at(service, user, as_of, amount="1000"):
    return service.create(
        user_id=user,
        idempotency_key=str(uuid4()),
        request=CreateFinancialAccountRequest(
            type="checking",
            currency="DOP",
            amount=amount,
            as_of=as_of,
            time_zone=ZONE,
        ),
        scope=PERSONAL,
    ).stored.account.id


def preview_at(service, user, aid, occurred_at):
    preview = MoneyService(service).preview(
        user_id=user,
        request=MoneyRequest(
            kind="expense", account_id=aid, amount="200", occurred_at=occurred_at
        ),
        scope=PERSONAL,
    )
    return preview, preview["affected_accounts"][0]


def test_entered_before_a_2359_check_on_the_same_day_is_asked():
    service, user, _ = world(local(12, 23, 59, 30))
    aid = open_at(service, user, local(12, 23, 59))
    preview, account = preview_at(service, user, aid, local(12, 23, 58))
    assert not preview["ready"] and len(account["observations"]) == 1


def test_entered_after_a_2359_check_on_the_same_day_is_not_asked():
    service, user, _ = world(local(12, 23, 59, 50))
    aid = open_at(service, user, local(12, 23, 59))
    preview, account = preview_at(service, user, aid, local(12, 23, 59, 40))
    assert preview["ready"]
    assert [s["reason"] for s in account["skipped_observations"]] == [
        "entered_after_observation"
    ]


def test_entered_at_0001_the_next_day_is_after_the_check_day():
    service, user, clock = world(local(12, 23, 59, 30))
    aid = open_at(service, user, local(12, 23, 59))
    clock.at = local(13, 0, 1)
    preview, account = preview_at(service, user, aid, local(13, 0, 1))
    assert preview["ready"]
    assert [s["reason"] for s in account["skipped_observations"]] == [
        "after_observation_day"
    ]


def test_backdated_at_0001_onto_the_check_day_is_asked_whatever_its_clock_time():
    service, user, clock = world(local(12, 23, 59, 30))
    aid = open_at(service, user, local(12, 23, 59))
    clock.at = local(13, 0, 1)
    for time in (local(12, 0, 1), local(12, 23, 59, 45)):
        preview, account = preview_at(service, user, aid, time)
        assert not preview["ready"] and len(account["observations"]) == 1


def test_preview_before_midnight_and_confirm_after_keep_the_decided_day():
    service, user, clock = world(local(12, 23, 59, 50))
    aid = open_at(service, user, local(12, 23, 59))
    money = MoneyService(service)
    preview, account = preview_at(service, user, aid, local(12, 23, 59, 40))
    assert preview["ready"] and preview["reviewed_request"]["entered_on"] == "2026-10-12"
    reviewed = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )
    clock.at = local(13, 0, 0, 10)
    stripped = reviewed.model_copy(update={"entered_on": None})
    with pytest.raises(RecordingInputError):
        money.write(
            user_id=user, request=stripped, idempotency_key="late", scope=PERSONAL
        )
    receipt = money.write(
        user_id=user, request=reviewed, idempotency_key="decided", scope=PERSONAL
    )
    assert receipt["accounts"][0].balance.amount_minor == 80000
    stored = service.get(user_id=user, account_id=aid, scope=PERSONAL)
    revision = stored.expenses[0].current
    assert revision.entered_on == date(2026, 10, 12)
    assert revision.coverage_skips == ((stored.opening.id, "entered_after_observation"),)


def test_balance_check_still_includes_same_day_activity_entered_after_its_time():
    service, user, clock = world(local(12, 15))
    aid = open_at(service, user, local(10, 9))
    money = MoneyService(service)
    preview, _ = preview_at(service, user, aid, local(12, 14))
    money.write(
        user_id=user,
        request=MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
            update={"preview_token": preview["preview_token"]}
        ),
        idempotency_key="spend",
        scope=PERSONAL,
    )
    clock.at = local(12, 16)
    current = service.get(user_id=user, account_id=aid, scope=PERSONAL)
    body = CheckRequest(
        expected_version=current.account.version,
        amount="800",
        as_of=local(12, 9),
        time_zone=ZONE,
    )
    check = service.loop.preview_check(user_id=user, account_id=aid, request=body)
    result = service.loop.write_check(
        user_id=user,
        account_id=aid,
        request=body.model_copy(update={"preview_token": check["preview_token"]}),
        idempotency_key="check",
    )
    expense = result.stored.expenses[0]
    assert [
        link.included
        for link in result.stored.coverage
        if link.activity_id == expense.id and link.observation_id != current.opening.id
    ] == [True]


def test_opening_correction_still_asks_about_same_day_activity():
    service, user, clock = world(local(12, 15))
    aid = open_at(service, user, local(10, 9))
    money = MoneyService(service)
    preview, _ = preview_at(service, user, aid, local(12, 14))
    money.write(
        user_id=user,
        request=MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
            update={"preview_token": preview["preview_token"]}
        ),
        idempotency_key="spend",
        scope=PERSONAL,
    )
    current = service.get(user_id=user, account_id=aid, scope=PERSONAL)
    opening = service.loop.preview_opening(
        user_id=user,
        account_id=aid,
        request=LoopOpeningRequest(
            expected_version=current.account.version,
            expected_revision=current.opening.current.revision,
            amount="1000",
            as_of=local(12, 9),
            time_zone=ZONE,
            reason="dated wrong",
        ),
    )
    assert not opening["ready"] and len(opening["activities"]) == 1


def test_date_only_import_at_midnight_on_the_check_day_is_asked():
    service, user, _ = world(local(12, 15))
    aid = open_at(service, user, local(12, 9))
    preview, account = preview_at(service, user, aid, local(12, 0))
    assert not preview["ready"] and len(account["observations"]) == 1


def test_skip_reason_and_entered_day_are_stored_on_the_revision(scene):
    service, user, _ = scene
    aid = opened(scene, NOW - timedelta(hours=2))
    preview, _ = effect(scene, aid, NOW - timedelta(hours=1))
    MoneyService(service).write(
        user_id=user,
        request=MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
            update={"preview_token": preview["preview_token"]}
        ),
        idempotency_key=str(uuid4()),
        scope=PERSONAL,
    )
    stored = service.get(user_id=user, account_id=aid, scope=PERSONAL)
    revision = stored.expenses[0].current
    assert revision.entered_on == NOW.astimezone(SD).date()
    assert revision.coverage_skips == ((stored.opening.id, "entered_after_observation"),)
