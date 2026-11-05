import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import (
    IdempotencyConflict,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.loop_schemas import (
    ActivityRequest,
    CheckRequest,
    LoopOpeningRequest,
)
from argus.domain.recording.repository import InMemoryFinancialAccountRepository
from argus.domain.recording.schemas import (
    CreateFinancialAccountRequest,
    EditFinancialAccountRequest,
    account_response,
)
from argus.domain.recording.service import FinancialAccountService

NOW = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


@pytest.fixture(params=["memory", "postgres"])
def scene(request):
    if request.param == "postgres":
        dsn = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL")
        if not dsn:
            pytest.skip("ARGUS_DISPOSABLE_DATABASE_URL is not configured")
        from argus.domain.recording.postgres_repository import (
            PostgresFinancialAccountRepository,
        )
        from psycopg_pool import ConnectionPool

        pool = ConnectionPool(dsn, min_size=0, max_size=4, open=True)
        repository = PostgresFinancialAccountRepository(pool)
    else:
        pool = None
        repository = InMemoryFinancialAccountRepository(lambda: NOW)
    service = FinancialAccountService(repository, lambda: NOW)
    user = str(uuid4())
    if pool:
        with pool.connection() as connection:
            connection.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (user, f"loop-{user}@example.test"),
            )
    account = service.create(
        user_id=user,
        idempotency_key="create",
        request=CreateFinancialAccountRequest(
            type="checking",
            currency="DOP",
            amount="10000",
            as_of=NOW - timedelta(days=10),
        ),
        scope=PERSONAL,
    ).stored
    yield service, user, account.account.id
    if pool:
        with pool.connection() as connection:
            from tests.household.shared_cleanup import cleanup

            cleanup(connection, [user])
            connection.execute("delete from auth.users where id=%s", (user,))
        pool.close()


def expense(scene, amount, day, coverage=None, record_id=None, reason=None):
    service, user, account = scene
    current = service.get(user_id=user, account_id=account, scope=PERSONAL)
    body = ActivityRequest(
        expected_version=current.account.version,
        expected_revision=1 if record_id else None,
        amount=amount,
        occurred_at=NOW - timedelta(days=day),
        coverage=coverage or [],
        reason=reason,
    )
    preview = service.loop.preview_activity(
        user_id=user, account_id=account, request=body, record_id=record_id
    )
    body = body.model_copy(update={"preview_token": preview["preview_token"]})
    return service.loop.write_activity(
        user_id=user,
        account_id=account,
        request=body,
        idempotency_key=str(uuid4()),
        record_id=record_id,
    ), body


def checked(scene, amount, day):
    service, user, account = scene
    current = service.get(user_id=user, account_id=account, scope=PERSONAL)
    body = CheckRequest(
        expected_version=current.account.version,
        amount=amount,
        as_of=NOW - timedelta(days=day),
    )
    preview = service.loop.preview_check(user_id=user, account_id=account, request=body)
    return service.loop.write_check(
        user_id=user,
        account_id=account,
        request=body.model_copy(update={"preview_token": preview["preview_token"]}),
        idempotency_key=str(uuid4()),
    )


def test_complete_loop_correction_late_partial_and_new_spending(scene):
    e, _ = expense(scene, "2000", 8)
    c = checked(scene, "7500", 5)
    expense(scene, "200", 7, [{"observation_id": c.record_id, "included": True}])
    result, _ = expense(scene, "500", 2)
    assert account_response(result.stored).balance.amount_minor == 700000
    fixed, _ = expense(
        scene,
        "1800",
        8,
        [{"observation_id": c.record_id, "included": True}],
        e.record_id,
        "wrong amount",
    )
    assert account_response(fixed.stored).balance.amount_minor == 700000
    assert (
        len(next(x for x in fixed.stored.expenses if x.id == e.record_id).revisions) == 2
    )


def test_response_loss_replay_precedes_stale_version_and_does_not_repeat_expense(scene):
    service, user, account = scene
    result, body = expense(scene, "500", 8)
    key = "response-loss"
    current = service.get(user_id=user, account_id=account, scope=PERSONAL)
    request = ActivityRequest(
        expected_version=current.account.version,
        amount="100",
        occurred_at=NOW - timedelta(days=6),
    )
    preview = service.loop.preview_activity(
        user_id=user, account_id=account, request=request
    )
    request = request.model_copy(update={"preview_token": preview["preview_token"]})
    first = service.loop.write_activity(
        user_id=user, account_id=account, request=request, idempotency_key=key
    )
    expense(scene, "200", 3)
    replay = service.loop.write_activity(
        user_id=user, account_id=account, request=request, idempotency_key=key
    )
    assert replay.replayed and replay.record_id == first.record_id
    assert len(replay.stored.expenses) == 3
    with pytest.raises(IdempotencyConflict):
        service.loop.write_activity(
            user_id=user,
            account_id=account,
            request=request.model_copy(update={"amount": "101"}),
            idempotency_key=key,
        )


def test_missing_coverage_is_previewable_but_cannot_commit(scene):
    service, user, account = scene
    body = ActivityRequest(
        expected_version=1, amount="10", occurred_at=NOW - timedelta(days=10)
    )
    preview = service.loop.preview_activity(
        user_id=user, account_id=account, request=body
    )
    assert not preview["ready"] and preview["observations"][0]["included"] is None
    with pytest.raises(RecordingInputError, match="coverage_required"):
        service.loop.write_activity(
            user_id=user, account_id=account, request=body, idempotency_key="no"
        )
    assert (
        service.get(user_id=user, account_id=account, scope=PERSONAL).account.version == 1
    )


def test_later_confirmed_same_day_check_becomes_current(scene):
    checked(scene, "9000", 5)
    service, user, account = scene
    current = service.get(user_id=user, account_id=account, scope=PERSONAL)
    request = CheckRequest(
        expected_version=current.account.version,
        amount="8000",
        as_of=(NOW - timedelta(days=5)).replace(hour=8),
    )
    preview = service.loop.preview_check(
        user_id=user, account_id=account, request=request
    )
    result = service.loop.write_check(
        user_id=user,
        account_id=account,
        request=request.model_copy(update={"preview_token": preview["preview_token"]}),
        idempotency_key="same-day",
    )
    assert account_response(result.stored).balance.amount_minor == 800000


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_unknown_opening_after_spending_requires_review_and_preserves_inclusion(scene):
    service, user, _ = scene
    account = service.create(
        user_id=user,
        idempotency_key="unknown",
        request=CreateFinancialAccountRequest(type="cash", currency="USD"),
        scope=PERSONAL,
    ).stored
    local = (service, user, account.account.id)
    e, _ = expense(local, "20", 5)
    request = LoopOpeningRequest(
        expected_version=2, amount="100", as_of=NOW - timedelta(days=3)
    )
    preview = service.loop.preview_opening(
        user_id=user, account_id=account.account.id, request=request
    )
    assert not preview["ready"] and preview["before"]["state"] == "unknown"
    request = LoopOpeningRequest.model_validate(
        {
            **request.model_dump(),
            "coverage": [{"activity_id": e.record_id, "included": True}],
        }
    )
    preview = service.loop.preview_opening(
        user_id=user, account_id=account.account.id, request=request
    )
    result = service.loop.write_opening(
        user_id=user,
        account_id=account.account.id,
        request=request.model_copy(update={"preview_token": preview["preview_token"]}),
        idempotency_key="opening",
    )
    assert account_response(result.stored).balance.amount_minor == 10000
    assert account_response(result.stored).balance.activity_since_tracking_minor == -2000


def test_timezone_transition_cannot_exclude_already_included_activity(scene):
    service, user, _ = scene
    start = datetime(2026, 1, 2, 0, tzinfo=timezone.utc)
    account = service.create(
        user_id=user,
        idempotency_key="zone",
        request=CreateFinancialAccountRequest(
            type="cash", currency="USD", amount="100", as_of=start, time_zone="UTC"
        ),
        scope=PERSONAL,
    ).stored
    body = ActivityRequest(
        expected_version=1,
        amount="10",
        occurred_at=start + timedelta(hours=20),
        time_zone="UTC",
        coverage=[{"observation_id": account.opening.id, "included": True}],
    )
    preview = service.loop.preview_activity(
        user_id=user, account_id=account.account.id, request=body
    )
    service.loop.write_activity(
        user_id=user,
        account_id=account.account.id,
        request=body.model_copy(update={"preview_token": preview["preview_token"]}),
        idempotency_key="zone-expense",
    )
    check = CheckRequest(
        expected_version=2,
        amount="100",
        as_of=start + timedelta(hours=1),
        time_zone="Pacific/Kiritimati",
    )
    with pytest.raises(RecordingInputError, match="coverage_date_conflict"):
        service.loop.preview_check(
            user_id=user, account_id=account.account.id, request=check
        )
    assert (
        service.get(
            user_id=user, account_id=account.account.id, scope=PERSONAL
        ).account.version
        == 2
    )


def test_opening_correction_cannot_overflow_current_residual(scene):
    service, user, _ = scene
    account = service.create(
        user_id=user,
        idempotency_key="range",
        request=CreateFinancialAccountRequest(
            type="cash", currency="USD", amount="0", as_of=NOW - timedelta(days=10)
        ),
        scope=PERSONAL,
    ).stored
    local = (service, user, account.account.id)
    checked(local, "-92233720368547758.07", 5)
    body = LoopOpeningRequest(
        expected_version=2,
        expected_revision=1,
        amount="92233720368547758.07",
        reason="Correct starting amount",
    )
    with pytest.raises(RecordingInputError, match="amount_out_of_range"):
        service.loop.preview_opening(
            user_id=user, account_id=account.account.id, request=body
        )
    current = service.get(user_id=user, account_id=account.account.id, scope=PERSONAL)
    assert current.account.version == 2 and current.opening.current.amount_minor == 0


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_home_aggregates_exact_strings_beyond_int64_and_preserves_archived_unknown(scene):
    from argus.domain.recording.loop_reads import home_response

    service, user, _ = scene
    for key in ("one", "two"):
        service.create(
            user_id=user,
            idempotency_key=key,
            request=CreateFinancialAccountRequest(
                type="cash", currency="USD", amount="92233720368547758.07"
            ),
            scope=PERSONAL,
        )
    service.create(
        user_id=user,
        idempotency_key="blank",
        request=CreateFinancialAccountRequest(type="cash", currency="USD"),
        scope=PERSONAL,
    )
    usd = next(
        row
        for row in home_response(service.list_accounts(user_id=user, scope=PERSONAL))[
            "currencies"
        ]
        if row["currency"] == "USD"
    )
    assert usd["net_worth_minor"] == str(2 * (2**63 - 1))
    assert usd["unknown_accounts"] == 1 and usd["known_accounts"] == 2


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_edit_cannot_apply_currency_rules_from_a_different_version(scene, monkeypatch):
    service, user, _ = scene
    account = service.create(
        user_id=user,
        idempotency_key="race-account",
        request=CreateFinancialAccountRequest(type="cash", currency="DOP"),
        scope=PERSONAL,
    ).stored
    original_get = service.get
    fired = False

    def interleaved_get(*, user_id, account_id, scope):
        nonlocal fired
        old = original_get(user_id=user_id, account_id=account_id, scope=scope)
        if not fired:
            fired = True
            expense((service, user, account.account.id), "100", 5)
        return old

    monkeypatch.setattr(service, "get", interleaved_get)
    with pytest.raises(StaleVersion):
        service.edit(
            user_id=user,
            account_id=account.account.id,
            request=EditFinancialAccountRequest(expected_version=2, currency="JPY"),
            scope=PERSONAL,
        )
    stored = original_get(user_id=user, account_id=account.account.id, scope=PERSONAL)
    assert stored.account.version == 2 and stored.account.currency == "DOP"
    assert stored.expenses[0].current.amount_minor == 10000


@pytest.mark.parametrize("with_opening", [False, True])
@pytest.mark.parametrize("source_kind", ["balance_check", "expense"])
@pytest.mark.usefixtures("legacy_blank_accounts")
def test_balance_date_uses_latest_source_zone_after_reopen(
    scene, with_opening, source_kind
):
    from zoneinfo import ZoneInfo

    from argus.domain.recording.loop import position
    from argus.domain.recording.loop_reads import home_response

    service, user, original = scene
    if with_opening:
        account_id = original
    else:
        account_id = service.create(
            user_id=user,
            idempotency_key=str(uuid4()),
            request=CreateFinancialAccountRequest(type="checking", currency="DOP"),
            scope=PERSONAL,
        ).stored.account.id
    current = service.get(user_id=user, account_id=account_id, scope=PERSONAL)
    source_time = (NOW - timedelta(days=5)).replace(hour=1)
    source_zone = "America/Chicago"
    body = CheckRequest(
        expected_version=current.account.version,
        amount="100",
        as_of=source_time,
        time_zone=source_zone,
    )
    preview = service.loop.preview_check(
        user_id=user, account_id=account_id, request=body
    )
    result = service.loop.write_check(
        user_id=user,
        account_id=account_id,
        request=body.model_copy(update={"preview_token": preview["preview_token"]}),
        idempotency_key=str(uuid4()),
    )
    if source_kind == "expense":
        source_time = (NOW - timedelta(days=2)).replace(hour=1)
        source_zone = "Pacific/Honolulu"
        body = ActivityRequest(
            expected_version=result.stored.account.version,
            amount="1",
            occurred_at=source_time,
            time_zone=source_zone,
        )
        preview = service.loop.preview_activity(
            user_id=user, account_id=account_id, request=body
        )
        assert (
            preview["after"]["as_of"]
            == source_time.astimezone(ZoneInfo(source_zone)).isoformat()
        )
        result = service.loop.write_activity(
            user_id=user,
            account_id=account_id,
            request=body.model_copy(update={"preview_token": preview["preview_token"]}),
            idempotency_key=str(uuid4()),
        )
    expected = source_time.astimezone(ZoneInfo(source_zone)).isoformat()
    reopened = service.get(user_id=user, account_id=account_id, scope=PERSONAL)
    for stored in (result.stored, reopened):
        balance = position(
            stored.opening, stored.checks, stored.expenses, stored.coverage
        )
        assert balance.as_of.isoformat() == expected
        assert account_response(stored).balance.as_of.isoformat() == expected
        assert home_response([stored])["currencies"][0]["as_of"].isoformat() == expected


@pytest.mark.parametrize("with_opening", [False, True])
@pytest.mark.parametrize(
    "initial_type,target_type,record_kind",
    [
        ("checking", "investment", "balance_check"),
        ("investment", "checking", "value_update"),
    ],
)
@pytest.mark.usefixtures("legacy_blank_accounts")
def test_observation_locks_account_type_without_expenses(
    scene, with_opening, initial_type, target_type, record_kind
):
    service, user, _ = scene
    account = service.create(
        user_id=user,
        idempotency_key=str(uuid4()),
        request=CreateFinancialAccountRequest(
            type=initial_type,
            currency="DOP",
            amount="100" if with_opening else None,
            as_of=NOW - timedelta(days=10) if with_opening else None,
        ),
        scope=PERSONAL,
    ).stored
    observed = checked((service, user, account.account.id), "90", 5).stored
    assert not observed.expenses and observed.checks[0].kind == record_kind
    with pytest.raises(RecordingInputError, match="type_locked"):
        service.edit(
            user_id=user,
            account_id=account.account.id,
            request=EditFinancialAccountRequest(
                expected_version=observed.account.version, type=target_type
            ),
            scope=PERSONAL,
        )
    reopened = service.get(user_id=user, account_id=account.account.id, scope=PERSONAL)
    assert reopened.account.type == initial_type
    assert reopened.account.version == observed.account.version
    assert reopened.checks == observed.checks


def test_home_freshness_compares_instants_across_source_zone_clock_change(scene):
    from argus.domain.recording.loop_reads import home_response

    service, user, _ = scene
    accounts = [
        service.create(
            user_id=user,
            idempotency_key=str(uuid4()),
            request=CreateFinancialAccountRequest(
                type="checking",
                currency="DOP",
                amount="100",
                as_of=datetime(2025, 11, 2, hour, minute, tzinfo=timezone.utc),
                time_zone="America/Chicago",
            ),
            scope=PERSONAL,
        ).stored
        for hour, minute in ((6, 45), (7, 15))
    ]
    assert home_response(accounts)["currencies"][0]["as_of"].isoformat() == (
        "2025-11-02T01:15:00-06:00"
    )
