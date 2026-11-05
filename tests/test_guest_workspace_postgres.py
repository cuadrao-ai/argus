"""Real-Postgres guest identity, workspace, cardinality, and RLS proofs."""

from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)
psycopg = pytest.importorskip("psycopg")


def _connect(*, autocommit: bool = True):
    return psycopg.connect(DSN, autocommit=autocommit)


def _seed_identity(
    connection,
    *,
    anonymous: bool,
    email: str | None = None,
) -> str:
    user_id = str(uuid.uuid4())
    verified_email = email if not anonymous else None
    if not anonymous and verified_email is None:
        verified_email = f"registered-{user_id[:8]}@example.com"
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into auth.users (id, email, is_anonymous) values (%s, %s, %s)",
            (user_id, verified_email, anonymous),
        )
        cursor.execute(
            "insert into public.profiles (id, email) values (%s, %s)",
            (user_id, verified_email),
        )
    return user_id


def _create_workspace(connection, user_id: str, created_at: datetime) -> dict:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into public.guest_workspaces (user_id, created_at, expires_at)"
            " values (%s, %s, %s) returning to_jsonb(guest_workspaces)",
            (user_id, created_at, created_at + timedelta(days=7)),
        )
        return cursor.fetchone()[0]


@pytest.fixture
def identities():
    with _connect() as connection:
        guest = _seed_identity(connection, anonymous=True)
        other_guest = _seed_identity(connection, anonymous=True)
        registered = _seed_identity(connection, anonymous=False)
        created_at = datetime.now(timezone.utc).replace(microsecond=0)
        _create_workspace(connection, guest, created_at)
        _create_workspace(connection, other_guest, created_at)
    try:
        yield {
            "guest": guest,
            "other_guest": other_guest,
            "registered": registered,
            "created_at": created_at,
        }
    finally:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from auth.users where id = any(%s::uuid[])",
                    ([guest, other_guest, registered],),
                )


def _visible_workspace_ids(
    connection,
    *,
    user_id: str,
    is_anonymous: bool,
) -> list[str]:
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("set local role authenticated")
            cursor.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (
                    json.dumps(
                        {
                            "sub": user_id,
                            "role": "authenticated",
                            "is_anonymous": is_anonymous,
                        }
                    ),
                ),
            )
            cursor.execute(
                "select user_id::text from public.guest_workspaces order by user_id"
            )
            return [row[0] for row in cursor.fetchall()]


def _visible_row_ids(
    connection,
    *,
    table: str,
    user_id: str,
    is_anonymous: bool,
) -> list[str]:
    allowed_tables = {"backtest_jobs"}
    assert table in allowed_tables
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("set local role authenticated")
            cursor.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (
                    json.dumps(
                        {
                            "sub": user_id,
                            "role": "authenticated",
                            "is_anonymous": is_anonymous,
                        }
                    ),
                ),
            )
            cursor.execute(f"select id::text from public.{table} order by id")
            return [row[0] for row in cursor.fetchall()]


def _assert_table_read_denied(
    connection,
    *,
    table: str,
    user_id: str,
    is_anonymous: bool,
) -> None:
    denied_tables = {
        "backtest_runs",
        "conversations",
        "feedback",
        "messages",
        "usage_counters",
    }
    assert table in denied_tables
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("set local role authenticated")
                cursor.execute(
                    "select set_config('request.jwt.claims', %s, true)",
                    (
                        json.dumps(
                            {
                                "sub": user_id,
                                "role": "authenticated",
                                "is_anonymous": is_anonymous,
                            }
                        ),
                    ),
                )
                cursor.execute(f"select id::text from public.{table}")


def test_guest_profile_is_nullable_only_without_a_fake_email() -> None:
    with _connect() as connection:
        guest_id = _seed_identity(connection, anonymous=True)
        with connection.cursor() as cursor:
            cursor.execute(
                "select email from public.profiles where id = %s",
                (guest_id,),
            )
            assert cursor.fetchone()[0] is None

        fake_id = str(uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id, email, is_anonymous)"
                " values (%s, null, true)",
                (fake_id,),
            )
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.profiles (id, email)"
                    " values (%s, 'guest@placeholder.invalid')",
                    (fake_id,),
                )
        with connection.cursor() as cursor:
            cursor.execute(
                "delete from auth.users where id = any(%s::uuid[])",
                ([guest_id, fake_id],),
            )


def test_workspace_expiry_is_exactly_seven_days_and_activity_cannot_extend_it(
    identities,
) -> None:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into public.conversations (user_id, title)"
                " values (%s, 'guest proof') returning id",
                (identities["guest"],),
            )
            conversation_id = cursor.fetchone()[0]
            cursor.execute(
                "insert into public.messages"
                " (conversation_id, user_id, role, content)"
                " values (%s, %s, 'user', 'activity')",
                (conversation_id, identities["guest"]),
            )
            cursor.execute(
                "select created_at, expires_at, conversation_id"
                " from public.guest_workspaces where user_id = %s",
                (identities["guest"],),
            )
            created_at, expires_at, bound_conversation = cursor.fetchone()

        assert expires_at == created_at + timedelta(days=7)
        assert str(bound_conversation) == str(conversation_id)

        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.cursor() as cursor:
                cursor.execute(
                    "update public.guest_workspaces"
                    " set expires_at = expires_at + interval '1 day'"
                    " where user_id = %s",
                    (identities["guest"],),
                )


def test_owner_scoped_rls_separates_guests_and_registered_users(identities) -> None:
    with _connect() as connection:
        assert _visible_workspace_ids(
            connection,
            user_id=identities["guest"],
            is_anonymous=True,
        ) == [identities["guest"]]
        assert _visible_workspace_ids(
            connection,
            user_id=identities["other_guest"],
            is_anonymous=True,
        ) == [identities["other_guest"]]
        assert (
            _visible_workspace_ids(
                connection,
                user_id=identities["registered"],
                is_anonymous=False,
            )
            == []
        )


def test_owner_scoped_rls_separates_guest_and_registered_product_rows(
    identities,
) -> None:
    conversation_ids: dict[str, str] = {}
    job_ids: dict[str, str] = {}
    with _connect() as connection:
        with connection.cursor() as cursor:
            for owner in ("guest", "other_guest", "registered"):
                cursor.execute(
                    "insert into public.conversations (user_id, title)"
                    " values (%s, %s) returning id::text",
                    (identities[owner], f"{owner} private row"),
                )
                conversation_ids[owner] = cursor.fetchone()[0]
                cursor.execute(
                    "insert into public.backtest_jobs"
                    " (user_id, conversation_id, payload_hash, launch_payload)"
                    " values (%s, %s, %s, '{}'::jsonb) returning id::text",
                    (
                        identities[owner],
                        conversation_ids[owner],
                        f"{owner}-payload",
                    ),
                )
                job_ids[owner] = cursor.fetchone()[0]

        for owner, is_anonymous in (
            ("guest", True),
            ("other_guest", True),
            ("registered", False),
        ):
            assert _visible_row_ids(
                connection,
                table="backtest_jobs",
                user_id=identities[owner],
                is_anonymous=is_anonymous,
            ) == [job_ids[owner]]
            _assert_table_read_denied(
                connection,
                table="conversations",
                user_id=identities[owner],
                is_anonymous=is_anonymous,
            )


def test_expired_guest_cannot_read_or_write_product_rows() -> None:
    with _connect() as connection:
        guest_id = _seed_identity(connection, anonymous=True)
        created_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=8)
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into public.conversations (user_id, title)"
                " values (%s, 'expired private row') returning id",
                (guest_id,),
            )
            conversation_id = cursor.fetchone()[0]
            cursor.execute(
                "insert into public.messages"
                " (conversation_id, user_id, role, content)"
                " values (%s, %s, 'user', 'expired private message')"
                " returning id",
                (conversation_id, guest_id),
            )
            user_message_id = cursor.fetchone()[0]
            cursor.execute(
                "insert into public.messages"
                " (conversation_id, user_id, role, content)"
                " values (%s, %s, 'assistant', 'expired private reply')"
                " returning id",
                (conversation_id, guest_id),
            )
            assistant_message_id = cursor.fetchone()[0]
            cursor.execute(
                "insert into public.chat_turn_lifecycles"
                " (turn_id,user_id,conversation_id,assistant_message_id,request_id,"
                "  status,accepted_at,terminal_at)"
                " values (%s,%s,%s,%s,'expired-request','completed',%s,%s)",
                (
                    user_message_id,
                    guest_id,
                    conversation_id,
                    assistant_message_id,
                    created_at,
                    created_at,
                ),
            )
            cursor.execute(
                "insert into public.backtest_runs"
                " (user_id, conversation_id, status, asset_class, symbols,"
                "  benchmark_symbol, config_snapshot)"
                " values (%s, %s, 'completed', 'equity', array['AAPL'],"
                "  'SPY', '{}'::jsonb)",
                (guest_id, conversation_id),
            )
            cursor.execute(
                "insert into public.backtest_jobs"
                " (user_id, conversation_id, payload_hash, launch_payload)"
                " values (%s, %s, 'expired-payload', '{}'::jsonb)",
                (guest_id, conversation_id),
            )
            cursor.execute(
                "insert into public.feedback (user_id, type, message)"
                " values (%s, 'general', 'expired private feedback')",
                (guest_id,),
            )
            cursor.execute(
                "insert into public.usage_counters"
                " (user_id, resource, period, period_start, period_end,"
                "  used_count, limit_count)"
                " values (%s, 'chat_messages', 'guest_session', %s, %s, 1, 10)",
                (guest_id, created_at, created_at + timedelta(days=7)),
            )
            cursor.execute(
                "insert into public.guest_workspaces"
                " (user_id, conversation_id, created_at, expires_at)"
                " values (%s, %s, %s, %s)",
                (
                    guest_id,
                    conversation_id,
                    created_at,
                    created_at + timedelta(days=7),
                ),
            )

        assert (
            _visible_row_ids(
                connection,
                table="backtest_jobs",
                user_id=guest_id,
                is_anonymous=True,
            )
            == []
        )
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("set local role authenticated")
                cursor.execute(
                    "select set_config('request.jwt.claims', %s, true)",
                    (
                        json.dumps(
                            {
                                "sub": guest_id,
                                "role": "authenticated",
                                "is_anonymous": True,
                            }
                        ),
                    ),
                )
                cursor.execute(
                    "select turn_id::text from public.chat_turn_lifecycles"
                    " order by turn_id"
                )
                assert cursor.fetchall() == []
        for table in (
            "conversations",
            "messages",
            "backtest_runs",
            "feedback",
            "usage_counters",
        ):
            _assert_table_read_denied(
                connection,
                table=table,
                user_id=guest_id,
                is_anonymous=True,
            )

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("set local role authenticated")
                    cursor.execute(
                        "select set_config('request.jwt.claims', %s, true)",
                        (
                            json.dumps(
                                {
                                    "sub": guest_id,
                                    "role": "authenticated",
                                    "is_anonymous": True,
                                }
                            ),
                        ),
                    )
                    cursor.execute(
                        "insert into public.messages"
                        " (conversation_id, user_id, role, content)"
                        " values (%s, %s, 'user', 'late write')",
                        (conversation_id, guest_id),
                    )

        with connection.cursor() as cursor:
            cursor.execute("delete from auth.users where id = %s", (guest_id,))


def test_authenticated_browser_cannot_mutate_guest_policy_state(identities) -> None:
    with _connect(autocommit=False) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.cursor() as cursor:
                cursor.execute("set local role authenticated")
                cursor.execute(
                    "select set_config('request.jwt.claims', %s, true)",
                    (
                        json.dumps(
                            {
                                "sub": identities["guest"],
                                "role": "authenticated",
                                "is_anonymous": True,
                            }
                        ),
                    ),
                )
                cursor.execute(
                    "update public.guest_workspaces set status = 'claimed'"
                    " where user_id = %s",
                    (identities["guest"],),
                )


def test_concurrent_guest_conversation_creation_allows_exactly_one(identities) -> None:
    barrier = Barrier(2)

    def create(index: int) -> str:
        try:
            with _connect() as connection:
                barrier.wait(timeout=10)
                with connection.cursor() as cursor:
                    cursor.execute(
                        "insert into public.conversations (user_id, title)"
                        " values (%s, %s) returning id",
                        (identities["guest"], f"guest-{index}"),
                    )
                    return f"created:{cursor.fetchone()[0]}"
        except psycopg.errors.DatabaseError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, range(2)))

    assert sum(outcome.startswith("created:") for outcome in outcomes) == 1
    assert outcomes.count("rejected") == 1
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.conversations where user_id = %s",
                (identities["guest"],),
            )
            assert cursor.fetchone()[0] == 1


def test_in_place_converted_guest_can_create_additional_conversation(
    identities,
) -> None:
    converted_email = f"converted-{identities['guest'][:8]}@example.com"
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into public.conversations (user_id,title)"
                " values (%s,'temporary conversation') returning id::text",
                (identities["guest"],),
            )
            original_conversation_id = cursor.fetchone()[0]
            cursor.execute(
                "update auth.users" " set is_anonymous=false,email=%s" " where id=%s",
                (converted_email, identities["guest"]),
            )
            cursor.execute(
                "select status,claimed_by::text,conversation_id::text"
                " from public.guest_workspaces where user_id=%s",
                (identities["guest"],),
            )
            assert cursor.fetchone() == (
                "claimed",
                identities["guest"],
                original_conversation_id,
            )
            cursor.execute(
                "insert into public.conversations (user_id,title)"
                " values (%s,'registered conversation') returning id::text",
                (identities["guest"],),
            )
            additional_conversation_id = cursor.fetchone()[0]
            cursor.execute(
                "select id::text from public.conversations"
                " where user_id=%s order by created_at,id",
                (identities["guest"],),
            )
            assert {row[0] for row in cursor.fetchall()} == {
                original_conversation_id,
                additional_conversation_id,
            }
