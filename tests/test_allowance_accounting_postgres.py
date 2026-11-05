"""Real-Postgres proofs for #247 allowance accounting.

Skip-gated on ``ARGUS_DISPOSABLE_DATABASE_URL``: point it at a disposable
Supabase-Postgres database that has every ``supabase/migrations`` file
applied, never at production. These proofs cover the behavior mocks cannot:
same-transaction settlement, barriered admission concurrency, replay and
collision against durable reservations, stale direct-job reconciliation,
owner isolation, and exact UTC window boundaries.
"""

from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from argus.domain.usage_limits import (
    GUEST_SIMULATION_ALLOWANCE,
    SIMULATION_USAGE_RESOURCE,
)

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)

psycopg = pytest.importorskip("psycopg")

MESSAGE_LIMITS = [{"period": "hour", "limit": 60}, {"period": "day", "limit": 200}]
SIMULATION_LIMITS = [{"period": "hour", "limit": 10}, {"period": "day", "limit": 50}]


def _connect():
    return psycopg.connect(DSN, autocommit=True)


@pytest.fixture
def owner():
    """One disposable auth user + profile + conversation per test."""
    with _connect() as connection:
        yield _seed_owner(connection)


def _seed_owner(connection) -> dict[str, str]:
    user_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    email = f"proof-{user_id[:8]}@argus.local"
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into auth.users (id, email) values (%s, %s)",
            (user_id, email),
        )
        cursor.execute(
            "insert into public.profiles (id, email) values (%s, %s)",
            (user_id, email),
        )
        cursor.execute(
            "insert into public.conversations (id, user_id, title)"
            " values (%s, %s, 'proof')",
            (conversation_id, user_id),
        )
    return {"user_id": user_id, "conversation_id": conversation_id}


def _seed_guest_owner(connection) -> dict[str, str]:
    user_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into auth.users (id, email, is_anonymous)" " values (%s, null, true)",
            (user_id,),
        )
        cursor.execute(
            "insert into public.profiles (id, email) values (%s, null)",
            (user_id,),
        )
        cursor.execute(
            "insert into public.guest_workspaces"
            " (user_id, created_at, expires_at)"
            " values (%s, %s, %s)",
            (user_id, created_at, created_at + timedelta(days=7)),
        )
        cursor.execute(
            "insert into public.conversations (user_id, title)"
            " values (%s, 'guest proof') returning id",
            (user_id,),
        )
        conversation_id = str(cursor.fetchone()[0])
    return {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "period_start": created_at.isoformat(),
        "period_end": (created_at + timedelta(days=7)).isoformat(),
    }


@pytest.fixture
def guest_owner():
    with _connect() as connection:
        guest = _seed_guest_owner(connection)
    try:
        yield guest
    finally:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from auth.users where id = %s",
                    (guest["user_id"],),
                )


def _guest_limits(owner, limit: int) -> list[dict[str, object]]:
    return [
        {
            "period": "guest_session",
            "limit": limit,
            "period_start": owner["period_start"],
            "period_end": owner["period_end"],
        }
    ]


def _usage_rows(connection, user_id: str, resource: str) -> dict[str, dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select period, period_start, period_end, used_count, limit_count"
            " from public.usage_counters"
            " where user_id = %s and resource = %s",
            (user_id, resource),
        )
        return {
            row[0]: {
                "period_start": row[1],
                "period_end": row[2],
                "used_count": row[3],
                "limit_count": row[4],
            }
            for row in cursor.fetchall()
        }


def _settle_message(connection, owner, message_id: str, *, limits=None):
    with connection.cursor() as cursor:
        cursor.execute(
            "select * from public.append_conversation_message_settling_usage("
            " %s, %s, %s, 'assistant', 'terminal product response',"
            " %s::jsonb, now(), 'preview', 'chat_messages', %s::jsonb)",
            (
                owner["user_id"],
                owner["conversation_id"],
                message_id,
                json.dumps(
                    {
                        "agent_runtime_turn": {
                            "status": "succeeded",
                            "terminal": True,
                        }
                    }
                ),
                json.dumps(limits if limits is not None else MESSAGE_LIMITS),
            ),
        )
        return cursor.fetchone()


def _admit(connection, owner, **overrides):
    # Ceilings default high for determinism on a reused disposable database;
    # capacity is proven via the per-user ceiling on a fresh user.
    arguments = {
        "user_id": owner["user_id"],
        "operation_scope": "chat.run_backtest",
        "idempotency_key": overrides.pop("idempotency_key", str(uuid.uuid4())),
        "identity_hash": overrides.pop("identity_hash", f"sha256:{'a' * 64}"),
        "payload_hash": f"sha256:{'b' * 64}",
        "launch_payload": json.dumps({"kind": "proof"}),
        "initial_status": "queued",
        "conversation_id": owner["conversation_id"],
        "user_running_limit": 1000,
        "user_queued_limit": 1000,
        "global_running_limit": 1000000,
        "global_queued_limit": 1000000,
        "allowance_limits": json.dumps(SIMULATION_LIMITS),
    }
    arguments.update(overrides)
    with connection.cursor() as cursor:
        cursor.execute(
            "select public.admit_backtest_job("
            " %(user_id)s, %(operation_scope)s, %(idempotency_key)s,"
            " %(identity_hash)s, %(payload_hash)s, %(launch_payload)s::jsonb,"
            " %(initial_status)s, %(conversation_id)s, null, null,"
            " '{}'::jsonb, %(user_running_limit)s, %(user_queued_limit)s,"
            " %(global_running_limit)s, %(global_queued_limit)s,"
            " %(allowance_limits)s::jsonb)",
            arguments,
        )
        return cursor.fetchone()[0]


def _submit_feedback(
    connection,
    owner,
    feedback_id: str,
    *,
    message: str = "guest feedback",
    context: dict | None = None,
) -> dict:
    with connection.cursor() as cursor:
        cursor.execute(
            "select public.create_feedback_settling_usage("
            " %s, %s, 'general', %s, %s::jsonb,"
            " 'feedback', %s::jsonb)",
            (
                feedback_id,
                owner["user_id"],
                message,
                json.dumps(context or {}),
                json.dumps(_guest_limits(owner, 5)),
            ),
        )
        return cursor.fetchone()[0]


def test_settlement_charges_both_windows_once_and_replays_zero(owner):
    with _connect() as connection:
        message_id = str(uuid.uuid4())
        row = _settle_message(connection, owner, message_id)
        assert row[2] is False  # not a replay

        windows = _usage_rows(connection, owner["user_id"], "chat_messages")
        now = datetime.now(timezone.utc)
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        assert windows["hour"]["used_count"] == 1
        assert windows["hour"]["limit_count"] == 60
        assert windows["hour"]["period_start"] == hour_start
        assert windows["hour"]["period_end"] == hour_start + timedelta(hours=1)
        assert windows["day"]["used_count"] == 1
        assert windows["day"]["limit_count"] == 200
        assert windows["day"]["period_start"] == day_start
        assert windows["day"]["period_end"] == day_start + timedelta(days=1)

        replay = _settle_message(connection, owner, message_id)
        assert replay[2] is True
        windows = _usage_rows(connection, owner["user_id"], "chat_messages")
        assert windows["hour"]["used_count"] == 1
        assert windows["day"]["used_count"] == 1


def test_guest_completed_terminals_stop_atomically_at_limit(guest_owner):
    with _connect() as connection:
        for _ in range(10):
            _settle_message(
                connection,
                guest_owner,
                str(uuid.uuid4()),
                limits=_guest_limits(guest_owner, 10),
            )
        windows = _usage_rows(
            connection,
            guest_owner["user_id"],
            "chat_messages",
        )
        assert set(windows) == {"guest_session"}
        assert windows["guest_session"]["used_count"] == 10
        assert windows["guest_session"]["limit_count"] == 10

        overage_message_id = str(uuid.uuid4())
        with pytest.raises(
            psycopg.Error,
            match="guest message allowance exhausted",
        ):
            _settle_message(
                connection,
                guest_owner,
                overage_message_id,
                limits=_guest_limits(guest_owner, 10),
            )
        windows = _usage_rows(
            connection,
            guest_owner["user_id"],
            "chat_messages",
        )
        assert windows["guest_session"]["used_count"] == 10
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.messages where id=%s",
                (overage_message_id,),
            )
            assert cursor.fetchone()[0] == 0


def test_registered_completed_terminals_settle_truthful_small_overage(owner):
    now = datetime.now(timezone.utc)
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                "insert into public.usage_counters"
                " (user_id, resource, period, period_start, period_end,"
                "  used_count, limit_count)"
                " values (%s, 'chat_messages', %s, %s, %s, %s, %s)",
                [
                    (
                        owner["user_id"],
                        "hour",
                        hour_start,
                        hour_start + timedelta(hours=1),
                        59,
                        60,
                    ),
                    (
                        owner["user_id"],
                        "day",
                        day_start,
                        day_start + timedelta(days=1),
                        199,
                        200,
                    ),
                ],
            )
        message_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        for message_id in message_ids:
            settled = _settle_message(connection, owner, message_id)
            assert settled[2] is False
        replay = _settle_message(connection, owner, message_ids[-1])
        assert replay[2] is True

        windows = _usage_rows(connection, owner["user_id"], "chat_messages")
        assert windows["hour"]["used_count"] == 61
        assert windows["day"]["used_count"] == 201
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.messages" " where id = any(%s::uuid[])",
                (message_ids,),
            )
            assert cursor.fetchone()[0] == 2


def test_guest_failure_interruption_and_exact_replay_add_no_unit(guest_owner):
    with _connect() as connection:
        message_id = str(uuid.uuid4())
        _settle_message(
            connection,
            guest_owner,
            message_id,
            limits=_guest_limits(guest_owner, 10),
        )
        _settle_message(
            connection,
            guest_owner,
            message_id,
            limits=_guest_limits(guest_owner, 10),
        )

        # Failure, recoverable failure, and interruption never call the
        # terminal settlement owner. The durable count therefore stays exact.
        windows = _usage_rows(
            connection,
            guest_owner["user_id"],
            "chat_messages",
        )
        assert windows["guest_session"]["used_count"] == 1


def test_guest_cannot_bypass_lifetime_policy_with_registered_windows(guest_owner):
    with _connect() as connection:
        message_id = str(uuid.uuid4())
        with pytest.raises(psycopg.errors.CheckViolation):
            _settle_message(
                connection,
                guest_owner,
                message_id,
                limits=MESSAGE_LIMITS,
            )
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.messages where id = %s",
                (message_id,),
            )
            assert cursor.fetchone()[0] == 0
        assert (
            _usage_rows(
                connection,
                guest_owner["user_id"],
                "chat_messages",
            )
            == {}
        )


@pytest.mark.parametrize("prior_admissions", range(GUEST_SIMULATION_ALLOWANCE + 1))
def test_first_run_after_start_over_uses_preserved_workspace_allowance(
    guest_owner, prior_admissions: int
) -> None:
    """Zero remaining jobs is not zero historical admissions (DOCN incident)."""
    with _connect() as connection:
        limits = json.dumps(_guest_limits(guest_owner, GUEST_SIMULATION_ALLOWANCE))
        for _ in range(prior_admissions):
            admitted = _admit(connection, guest_owner, allowance_limits=limits)
            assert admitted["decision"] == "admitted"
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.backtest_runs"
                    " (user_id,conversation_id,status,asset_class,symbols,"
                    "  benchmark_symbol,config_snapshot,conversation_result_card)"
                    " values (%s,%s,'completed','equity',array['DOCN'],'SPY',"
                    " '{}'::jsonb,'{}'::jsonb) returning id",
                    (guest_owner["user_id"], guest_owner["conversation_id"]),
                )
                run_id = cursor.fetchone()[0]
                cursor.execute(
                    "update public.backtest_jobs set status='succeeded',"
                    " result_run_id=%s,finished_at=now() where id=%s",
                    (run_id, admitted["job"]["id"]),
                )

        with connection.cursor() as cursor:
            cursor.execute(
                "select id::text from public.replace_guest_conversation("
                "%s,'New idea','system_default','en')",
                (guest_owner["user_id"],),
            )
            replacement = {**guest_owner, "conversation_id": cursor.fetchone()[0]}
            for table in ("backtest_jobs", "backtest_runs"):
                cursor.execute(
                    f"select count(*) from public.{table} where user_id=%s",
                    (guest_owner["user_id"],),
                )
                assert cursor.fetchone()[0] == 0

        before = _usage_rows(
            connection, guest_owner["user_id"], SIMULATION_USAGE_RESOURCE
        )
        assert before.get("guest_session", {}).get("used_count", 0) == prior_admissions
        outcome = _admit(connection, replacement, allowance_limits=limits)
        after = _usage_rows(connection, guest_owner["user_id"], SIMULATION_USAGE_RESOURCE)
        if prior_admissions == GUEST_SIMULATION_ALLOWANCE:
            assert outcome == {"decision": "conversion_required"}
            assert after == before
        else:
            assert outcome["decision"] == "admitted"
            assert after["guest_session"]["used_count"] == prior_admissions + 1


def test_guest_unique_simulation_charges_once_replay_zero_and_third_stops(
    guest_owner,
):
    with _connect() as connection:
        key = str(uuid.uuid4())
        first = _admit(
            connection,
            guest_owner,
            idempotency_key=key,
            allowance_limits=json.dumps(_guest_limits(guest_owner, 2)),
        )
        replay = _admit(
            connection,
            guest_owner,
            idempotency_key=key,
            allowance_limits=json.dumps(_guest_limits(guest_owner, 2)),
        )
        second = _admit(
            connection,
            guest_owner,
            allowance_limits=json.dumps(_guest_limits(guest_owner, 2)),
        )
        third = _admit(
            connection,
            guest_owner,
            allowance_limits=json.dumps(_guest_limits(guest_owner, 2)),
        )

        assert first["decision"] == "admitted"
        assert replay["decision"] == "replay"
        assert second["decision"] == "admitted"
        assert third == {"decision": "conversion_required"}
        windows = _usage_rows(
            connection,
            guest_owner["user_id"],
            "backtest_runs",
        )
        assert windows["guest_session"]["used_count"] == 2
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.backtest_jobs where user_id = %s",
                (guest_owner["user_id"],),
            )
            assert cursor.fetchone()[0] == 2


def test_guest_five_feedback_submissions_allowed_and_sixth_rejected(guest_owner):
    with _connect() as connection:
        for _ in range(5):
            outcome = _submit_feedback(connection, guest_owner, str(uuid.uuid4()))
            assert outcome["decision"] == "accepted"

        sixth = _submit_feedback(connection, guest_owner, str(uuid.uuid4()))
        assert sixth == {"decision": "conversion_required"}
        windows = _usage_rows(connection, guest_owner["user_id"], "feedback")
        assert windows["guest_session"]["used_count"] == 5
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.feedback where user_id = %s",
                (guest_owner["user_id"],),
            )
            assert cursor.fetchone()[0] == 5


def test_guest_feedback_concurrency_accepts_only_the_fifth_unit(guest_owner):
    with _connect() as connection:
        for _ in range(4):
            assert (
                _submit_feedback(connection, guest_owner, str(uuid.uuid4()))["decision"]
                == "accepted"
            )
    barrier = Barrier(2)

    def submit(feedback_id: str) -> dict:
        with _connect() as connection:
            barrier.wait(timeout=10)
            return _submit_feedback(connection, guest_owner, feedback_id)

    feedback_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, feedback_ids))

    assert sorted(outcome["decision"] for outcome in outcomes) == [
        "accepted",
        "conversion_required",
    ]
    with _connect() as connection:
        windows = _usage_rows(connection, guest_owner["user_id"], "feedback")
        assert windows["guest_session"]["used_count"] == 5
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.feedback where user_id = %s",
                (guest_owner["user_id"],),
            )
            assert cursor.fetchone()[0] == 5


def test_guest_feedback_concurrent_exact_replay_charges_once(guest_owner):
    with _connect() as connection:
        for _ in range(4):
            _submit_feedback(connection, guest_owner, str(uuid.uuid4()))
    barrier = Barrier(2)
    feedback_id = str(uuid.uuid4())

    def submit() -> dict:
        with _connect() as connection:
            barrier.wait(timeout=10)
            return _submit_feedback(connection, guest_owner, feedback_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: submit(), range(2)))

    assert {outcome["decision"] for outcome in outcomes} == {"accepted"}
    assert sorted(outcome["replayed"] for outcome in outcomes) == [False, True]
    with _connect() as connection:
        windows = _usage_rows(connection, guest_owner["user_id"], "feedback")
        assert windows["guest_session"]["used_count"] == 5
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.feedback where id = %s",
                (feedback_id,),
            )
            assert cursor.fetchone()[0] == 1


def test_guest_feedback_concurrent_identity_collision_is_rejected(guest_owner):
    with _connect() as connection:
        for _ in range(4):
            _submit_feedback(connection, guest_owner, str(uuid.uuid4()))
    barrier = Barrier(2)
    feedback_id = str(uuid.uuid4())

    def submit(message: str) -> tuple[str, dict | None]:
        try:
            with _connect() as connection:
                barrier.wait(timeout=10)
                outcome = _submit_feedback(
                    connection,
                    guest_owner,
                    feedback_id,
                    message=message,
                )
                return "accepted", outcome
        except psycopg.errors.UniqueViolation:
            return "collision", None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, ("first payload", "different payload")))

    assert sorted(kind for kind, _ in outcomes) == ["accepted", "collision"]
    accepted = next(outcome for kind, outcome in outcomes if kind == "accepted")
    assert accepted is not None and accepted["decision"] == "accepted"
    with _connect() as connection:
        windows = _usage_rows(connection, guest_owner["user_id"], "feedback")
        assert windows["guest_session"]["used_count"] == 5
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.feedback where id = %s",
                (feedback_id,),
            )
            assert cursor.fetchone()[0] == 1


@pytest.mark.parametrize(
    "instant",
    [
        datetime(2026, 3, 8, 8, 30, tzinfo=timezone.utc),
        datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc),
    ],
)
def test_registered_allowance_windows_remain_utc_across_dst(instant):
    with psycopg.connect(DSN, autocommit=False) as connection:
        owner = _seed_owner(connection)
        with connection.cursor() as cursor:
            cursor.execute("set local time zone 'America/Chicago'")
            cursor.execute("show timezone")
            assert cursor.fetchone()[0] == "America/Chicago"
            cursor.execute(
                "select window_period, period_start, period_end"
                " from argus_private.validated_usage_windows("
                " %s, 'chat_messages', %s::jsonb, %s)",
                (owner["user_id"], json.dumps(MESSAGE_LIMITS), instant),
            )
            windows = {
                period: (
                    start.astimezone(timezone.utc),
                    end.astimezone(timezone.utc),
                )
                for period, start, end in cursor.fetchall()
            }
            cursor.execute("show timezone")
            assert cursor.fetchone()[0] == "America/Chicago"
        connection.rollback()

    hour_start = instant.replace(minute=0, second=0, microsecond=0)
    day_start = instant.replace(hour=0, minute=0, second=0, microsecond=0)
    assert windows["hour"] == (hour_start, hour_start + timedelta(hours=1))
    assert windows["day"] == (day_start, day_start + timedelta(hours=24))


def test_settlement_rolls_back_with_its_message(owner):
    with _connect() as connection:
        message_id = str(uuid.uuid4())
        with pytest.raises(psycopg.errors.DatabaseError):
            _settle_message(
                connection,
                owner,
                message_id,
                limits=[{"period": "week", "limit": 1}],
            )
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.messages where id = %s",
                (message_id,),
            )
            assert cursor.fetchone()[0] == 0
        assert _usage_rows(connection, owner["user_id"], "chat_messages") == {}


def test_concurrent_settlements_of_distinct_turns_count_exactly(owner):
    barrier = Barrier(10)

    def settle(_: int) -> None:
        with _connect() as connection:
            barrier.wait(timeout=30)
            _settle_message(connection, owner, str(uuid.uuid4()))

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(settle, range(10)))

    with _connect() as connection:
        windows = _usage_rows(connection, owner["user_id"], "chat_messages")
        assert windows["hour"]["used_count"] == 10
        assert windows["day"]["used_count"] == 10


def test_guest_concurrent_terminal_settlement_stops_atomically_at_limit(
    guest_owner,
) -> None:
    message_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    barrier = Barrier(2)
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into public.usage_counters"
                " (user_id,resource,period,period_start,period_end,"
                "  used_count,limit_count)"
                " values (%s,'chat_messages','guest_session',%s,%s,9,10)",
                (
                    guest_owner["user_id"],
                    guest_owner["period_start"],
                    guest_owner["period_end"],
                ),
            )

    def settle(message_id: str) -> str:
        try:
            with _connect() as connection:
                barrier.wait(timeout=30)
                _settle_message(
                    connection,
                    guest_owner,
                    message_id,
                    limits=_guest_limits(guest_owner, 10),
                )
            return "settled"
        except psycopg.Error as exc:
            assert "guest message allowance exhausted" in str(exc)
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(settle, message_ids))

    assert sorted(outcomes) == ["rejected", "settled"]
    with _connect() as connection:
        windows = _usage_rows(
            connection,
            guest_owner["user_id"],
            "chat_messages",
        )
        assert windows["guest_session"]["used_count"] == 10
        with connection.cursor() as cursor:
            cursor.execute(
                "select id::text from public.messages"
                " where id=any(%s::uuid[]) order by id",
                (message_ids,),
            )
            durable_ids = [row[0] for row in cursor.fetchall()]
        assert len(durable_ids) == 1
        replay = _settle_message(
            connection,
            guest_owner,
            durable_ids[0],
            limits=_guest_limits(guest_owner, 10),
        )
        assert replay[2] is True
        assert (
            _usage_rows(
                connection,
                guest_owner["user_id"],
                "chat_messages",
            )["guest_session"]["used_count"]
            == 10
        )


def test_ten_concurrent_same_identity_admissions_charge_once(owner):
    idempotency_key = str(uuid.uuid4())
    identity_hash = f"sha256:{'c' * 64}"
    barrier = Barrier(10)

    def admit(_: int) -> str:
        with _connect() as connection:
            barrier.wait(timeout=30)
            return _admit(
                connection,
                owner,
                idempotency_key=idempotency_key,
                identity_hash=identity_hash,
            )["decision"]

    with ThreadPoolExecutor(max_workers=10) as pool:
        decisions = list(pool.map(admit, range(10)))

    assert sorted(decisions) == ["admitted"] + ["replay"] * 9
    with _connect() as connection:
        windows = _usage_rows(connection, owner["user_id"], "backtest_runs")
        assert windows["hour"]["used_count"] == 1
        assert windows["day"]["used_count"] == 1
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.backtest_jobs where user_id = %s",
                (owner["user_id"],),
            )
            assert cursor.fetchone()[0] == 1


def test_concurrent_distinct_identities_respect_capacity_atomically(owner):
    barrier = Barrier(10)

    def admit(_: int) -> str:
        with _connect() as connection:
            barrier.wait(timeout=30)
            return _admit(connection, owner, user_queued_limit=2)["decision"]

    with ThreadPoolExecutor(max_workers=10) as pool:
        decisions = list(pool.map(admit, range(10)))

    assert decisions.count("admitted") == 2  # user_queued_limit=2
    assert decisions.count("per_user_capacity") == 8
    with _connect() as connection:
        windows = _usage_rows(connection, owner["user_id"], "backtest_runs")
        assert windows["hour"]["used_count"] == 2
        assert windows["day"]["used_count"] == 2


def test_same_key_different_identity_conflicts_without_disclosure(owner):
    with _connect() as connection:
        idempotency_key = str(uuid.uuid4())
        first = _admit(connection, owner, idempotency_key=idempotency_key)
        assert first["decision"] == "admitted"
        conflict = _admit(
            connection,
            owner,
            idempotency_key=idempotency_key,
            identity_hash=f"sha256:{'d' * 64}",
        )
        assert conflict == {"decision": "conflict"}
        windows = _usage_rows(connection, owner["user_id"], "backtest_runs")
        assert windows["hour"]["used_count"] == 1


def test_hourly_and_daily_exhaustion_reject_before_any_charge(owner):
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into public.usage_counters"
                " (user_id, resource, period, period_start, period_end,"
                "  used_count, limit_count)"
                " values (%s, 'backtest_runs', 'hour',"
                "  date_trunc('hour', now()),"
                "  date_trunc('hour', now()) + interval '1 hour', 10, 10)",
                (owner["user_id"],),
            )
        outcome = _admit(connection, owner)
        assert outcome == {"decision": "allowance_exhausted"}

        with connection.cursor() as cursor:
            cursor.execute(
                "update public.usage_counters set used_count = 0"
                " where user_id = %s and period = 'hour'",
                (owner["user_id"],),
            )
            cursor.execute(
                "insert into public.usage_counters"
                " (user_id, resource, period, period_start, period_end,"
                "  used_count, limit_count)"
                " values (%s, 'backtest_runs', 'day',"
                "  date_trunc('day', now()),"
                "  date_trunc('day', now()) + interval '1 day', 50, 50)",
                (owner["user_id"],),
            )
        outcome = _admit(connection, owner)
        assert outcome == {"decision": "allowance_exhausted"}
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.backtest_jobs where user_id = %s",
                (owner["user_id"],),
            )
            assert cursor.fetchone()[0] == 0


def test_post_admission_failure_keeps_exactly_one_unit(owner):
    with _connect() as connection:
        outcome = _admit(
            connection,
            owner,
            operation_scope="backtests.run",
            initial_status="running",
            conversation_id=None,
        )
        assert outcome["decision"] == "admitted"
        job_id = outcome["job"]["id"]
        with connection.cursor() as cursor:
            cursor.execute(
                "update public.backtest_jobs set status = 'failed',"
                " failure_code = 'execution_failed', retryable = false,"
                " finished_at = now() where id = %s",
                (job_id,),
            )
        windows = _usage_rows(connection, owner["user_id"], "backtest_runs")
        assert windows["hour"]["used_count"] == 1
        assert windows["day"]["used_count"] == 1

        replay = _admit(
            connection,
            owner,
            operation_scope="backtests.run",
            initial_status="running",
            conversation_id=None,
            idempotency_key=outcome["job"]["idempotency_key"],
        )
        assert replay["decision"] == "replay"
        assert replay["job"]["status"] == "failed"
        windows = _usage_rows(connection, owner["user_id"], "backtest_runs")
        assert windows["hour"]["used_count"] == 1


def test_stale_running_direct_job_reconciles_on_new_admission(owner):
    with _connect() as connection:
        stale = _admit(
            connection,
            owner,
            operation_scope="backtests.run",
            initial_status="running",
            conversation_id=None,
        )
        assert stale["decision"] == "admitted"
        with connection.cursor() as cursor:
            cursor.execute(
                "update public.backtest_jobs"
                " set started_at = now() - interval '20 minutes'"
                " where id = %s",
                (stale["job"]["id"],),
            )
        fresh = _admit(
            connection,
            owner,
            operation_scope="backtests.run",
            initial_status="running",
            conversation_id=None,
        )
        assert fresh["decision"] == "admitted"
        with connection.cursor() as cursor:
            cursor.execute(
                "select status, failure_code, retryable"
                " from public.backtest_jobs where id = %s",
                (stale["job"]["id"],),
            )
            status, failure_code, retryable = cursor.fetchone()
        assert status == "failed"
        assert failure_code == "direct_execution_abandoned"
        assert retryable is True


def test_owner_isolation_for_reservations_and_counters(owner):
    with _connect() as connection:
        other = _seed_owner(connection)
        shared_key = str(uuid.uuid4())
        first = _admit(connection, owner, idempotency_key=shared_key)
        second = _admit(connection, other, idempotency_key=shared_key)
        assert first["decision"] == "admitted"
        assert second["decision"] == "admitted"
        assert first["job"]["id"] != second["job"]["id"]
        assert first["job"]["user_id"] == owner["user_id"]
        assert second["job"]["user_id"] == other["user_id"]
        owner_windows = _usage_rows(connection, owner["user_id"], "backtest_runs")
        other_windows = _usage_rows(connection, other["user_id"], "backtest_runs")
        assert owner_windows["day"]["used_count"] == 1
        assert other_windows["day"]["used_count"] == 1


def test_admission_functions_are_service_role_executable():
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select"
                " has_function_privilege('service_role',"
                "  'public.admit_backtest_job(uuid,text,text,text,text,jsonb,"
                "text,uuid,uuid,uuid,jsonb,integer,integer,integer,integer,"
                "jsonb)', 'execute'),"
                " has_function_privilege('service_role',"
                "  'public.finalize_direct_backtest_success(uuid,uuid,text,"
                "jsonb,jsonb,jsonb,jsonb)', 'execute')"
            )
            assert cursor.fetchone() == (True, True)


def test_legacy_reservation_replays_on_exact_payload_and_adopts_identity(owner):
    with _connect() as connection:
        key = str(uuid.uuid4())
        legacy_payload_hash = f"sha256:{'1' * 64}"
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into public.backtest_jobs"
                " (user_id, conversation_id, operation_scope, idempotency_key,"
                "  identity_hash, payload_hash, launch_payload, status,"
                "  priority, attempts, max_attempts, queued_at)"
                " values (%s, %s, 'chat.run_backtest', %s, null, %s,"
                "  '{}'::jsonb, 'queued', 'normal', 0, 1, now())"
                " returning id",
                (
                    owner["user_id"],
                    owner["conversation_id"],
                    key,
                    legacy_payload_hash,
                ),
            )
            legacy_job_id = cursor.fetchone()[0]

        canonical_identity = f"sha256:{'2' * 64}"
        replay = _admit(
            connection,
            owner,
            idempotency_key=key,
            identity_hash=canonical_identity,
            payload_hash=legacy_payload_hash,
        )
        assert replay["decision"] == "replay"
        assert str(replay["job"]["id"]) == str(legacy_job_id)
        with connection.cursor() as cursor:
            cursor.execute(
                "select identity_hash from public.backtest_jobs where id = %s",
                (legacy_job_id,),
            )
            assert cursor.fetchone()[0] == canonical_identity

        second = _admit(
            connection,
            owner,
            idempotency_key=key,
            identity_hash=canonical_identity,
            payload_hash=legacy_payload_hash,
        )
        assert second["decision"] == "replay"
        windows = _usage_rows(connection, owner["user_id"], "backtest_runs")
        assert windows == {}  # replays never charge


def test_legacy_reservation_with_different_payload_conflicts(owner):
    with _connect() as connection:
        key = str(uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into public.backtest_jobs"
                " (user_id, conversation_id, operation_scope, idempotency_key,"
                "  identity_hash, payload_hash, launch_payload, status,"
                "  priority, attempts, max_attempts, queued_at)"
                " values (%s, %s, 'chat.run_backtest', %s, null, %s,"
                "  '{}'::jsonb, 'queued', 'normal', 0, 1, now())",
                (
                    owner["user_id"],
                    owner["conversation_id"],
                    key,
                    f"sha256:{'3' * 64}",
                ),
            )
        outcome = _admit(
            connection,
            owner,
            idempotency_key=key,
            payload_hash=f"sha256:{'4' * 64}",
        )
        assert outcome == {"decision": "conflict"}
        assert _usage_rows(connection, owner["user_id"], "backtest_runs") == {}


def _finalize_direct_success(connection, owner, *, job_id: str, run_id: str):
    idea_id = str(uuid.uuid4())
    idea_version_id = str(uuid.uuid4())
    artifact_id = str(uuid.uuid4())
    run = {
        "id": run_id,
        "status": "completed",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "allocation_method": "equal_weight",
        "benchmark_symbol": "SPY",
        "metrics": {"total_return": 0.1},
        "config_snapshot": {"template": "buy_and_hold"},
        "conversation_result_card": {},
    }
    idea = {"id": idea_id, "title": "Proof idea"}
    idea_version = {
        "id": idea_version_id,
        "idea_id": idea_id,
        "source_run_id": run_id,
        "title": "Proof idea",
    }
    artifact = {
        "id": artifact_id,
        "idea_id": idea_id,
        "idea_version_id": idea_version_id,
        "source_run_id": run_id,
        "title": "Proof evidence",
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "select public.finalize_direct_backtest_success("
            " %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)",
            (
                owner["user_id"],
                job_id,
                f"direct:{job_id}",
                json.dumps(run),
                json.dumps(idea),
                json.dumps(idea_version),
                json.dumps(artifact),
            ),
        )
        return cursor.fetchone()[0]


def test_direct_success_commits_tuple_and_job_flip_in_one_boundary(owner):
    with _connect() as connection:
        admitted = _admit(
            connection,
            owner,
            operation_scope="backtests.run",
            initial_status="running",
            conversation_id=None,
        )
        job_id = admitted["job"]["id"]
        run_id = str(uuid.uuid4())

        finalized = _finalize_direct_success(
            connection, owner, job_id=job_id, run_id=run_id
        )

        assert finalized is not None
        assert finalized["run"]["id"] == run_id
        with connection.cursor() as cursor:
            cursor.execute(
                "select status, result_run_id from public.backtest_jobs" " where id = %s",
                (job_id,),
            )
            status, result_run_id = cursor.fetchone()
            cursor.execute(
                "select count(*) from public.backtest_runs where id = %s",
                (run_id,),
            )
            run_rows = cursor.fetchone()[0]
        assert status == "succeeded"
        assert str(result_run_id) == run_id
        assert run_rows == 1


def test_reconciled_direct_job_blocks_late_success_without_a_tuple(owner):
    with _connect() as connection:
        admitted = _admit(
            connection,
            owner,
            operation_scope="backtests.run",
            initial_status="running",
            conversation_id=None,
        )
        job_id = admitted["job"]["id"]
        run_id = str(uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.execute(
                "update public.backtest_jobs set status='failed',"
                " failure_code='direct_execution_abandoned', retryable=true,"
                " finished_at=now() where id = %s",
                (job_id,),
            )

        finalized = _finalize_direct_success(
            connection, owner, job_id=job_id, run_id=run_id
        )

        assert finalized is None
        with connection.cursor() as cursor:
            cursor.execute(
                "select status, failure_code, result_run_id"
                " from public.backtest_jobs where id = %s",
                (job_id,),
            )
            status, failure_code, result_run_id = cursor.fetchone()
            cursor.execute(
                "select count(*) from public.backtest_runs where id = %s",
                (run_id,),
            )
            run_rows = cursor.fetchone()[0]
        assert status == "failed"
        assert failure_code == "direct_execution_abandoned"
        assert result_run_id is None
        assert run_rows == 0
