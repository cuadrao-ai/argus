"""Business spaces migration (20261008140000) on real Postgres.

SQL fixtures only. Each case runs in a transaction that is rolled back, so the
shared disposable database keeps no rows from here beyond the users fixture.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL

from tests import test_financial_accounts_postgres as shared

psycopg = pytest.importorskip("psycopg")

users = shared.users
repository = shared.repository
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def db(users) -> Iterator:  # noqa: ANN001
    # Depends on users so this transaction rolls back before the users go.
    with psycopg.connect(shared.DSN) as connection:
        with connection.transaction(force_rollback=True):
            yield connection


@contextmanager
def _raises(db, error, match: str):  # noqa: ANN001, ANN202
    """Expect the block to fail inside a savepoint, keeping the outer transaction."""
    with pytest.raises(error, match=match), db.transaction():
        yield


def _one(db, sql: str, params: tuple = ()):  # noqa: ANN001, ANN202
    return db.execute(sql, params).fetchone()[0]


def space(db, owner: str) -> str:  # noqa: ANN001
    return str(
        _one(
            db,
            "insert into public.spaces (kind, name, created_by)"
            " values ('business', 'Colmado', %s) returning id",
            (owner,),
        )
    )


def account(db, user: str, owner_space: str | None = None) -> str:  # noqa: ANN001
    return str(
        _one(
            db,
            "insert into public.financial_accounts (user_id, owner_space_id, type, currency)"
            " values (%s, %s, 'cash', 'DOP') returning id",
            (user, owner_space),
        )
    )


def connection(db, user: str, owner_space: str | None = None) -> str:  # noqa: ANN001
    return str(
        _one(
            db,
            "insert into public.financial_source_connections"
            " (user_id, owner_space_id, source, external_ref)"
            " values (%s, %s, 'statement', %s) returning id",
            (user, owner_space, f"spaces-test-{uuid4()}"),
        )
    )


def conversation(db, user: str, owner_space: str | None = None) -> str:  # noqa: ANN001
    return str(
        _one(
            db,
            "insert into public.conversations (user_id, owner_space_id, title)"
            " values (%s, %s, 'spaces test') returning id",
            (user, owner_space),
        )
    )


def event(db, user: str, owner_space: str | None = None) -> str:  # noqa: ANN001
    return str(
        _one(
            db,
            "insert into public.financial_import_events"
            " (id, user_id, owner_space_id, state, evidence, created_at, updated_at, version)"
            " values (gen_random_uuid(), %s, %s, 'open', 'transaction', now(), now(), 1)"
            " returning id",
            (user, owner_space),
        )
    )


def observation(db, user: str, event_id: str, connection_id: str) -> str:  # noqa: ANN001
    return str(
        _one(
            db,
            "insert into public.financial_import_observations"
            " (id, user_id, event_id, connection_id, source, external_id, fingerprint,"
            "  candidate, live, revisions, first_seen_at, updated_at)"
            " values (gen_random_uuid(), %s, %s, %s, 'statement', %s, %s, '{}', true, 1,"
            "  now(), now()) returning id",
            (user, event_id, connection_id, str(uuid4()), "0" * 64),
        )
    )


def _has_reply_language(db) -> bool:  # noqa: ANN001
    return bool(
        db.execute(
            "select 1 from information_schema.columns where table_schema = 'public'"
            " and table_name = 'whatsapp_sender_links' and column_name = 'reply_language'"
        ).fetchone()
    )


def sender_link(db, owner: str, destination_space: str | None = None) -> str:  # noqa: ANN001
    columns = ["destination_owner_id", "destination_space_id", "wa_id_hash", "last4"]
    values = [owner, destination_space, os.urandom(32), "1234"]
    if _has_reply_language(db):
        columns.append("reply_language")
        values.append("es-419")
    return str(
        _one(
            db,
            f"insert into public.whatsapp_sender_links ({', '.join(columns)}, status, linked_at)"
            f" values ({', '.join(['%s'] * len(values))}, 'active', now())"
            " returning destination_space_id",
            tuple(values),
        )
    )


def capture(db, owner: str, connection_id: str) -> None:  # noqa: ANN001
    db.execute(
        "insert into public.whatsapp_inbound_messages"
        " (provider_message_key, sender_hash, destination_owner_id, status,"
        "  connection_id, received_at, updated_at)"
        " values (%s, %s, %s, 'captured', %s, now(), now())",
        (os.urandom(32), os.urandom(32), owner, connection_id),
    )


def test_one_open_business_space_per_owner(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    first = space(db, owner)
    with _raises(db, psycopg.errors.UniqueViolation, "spaces_one_open_business_idx"):
        space(db, owner)
    db.execute("update public.spaces set closed_at = now() where id = %s", (first,))
    second = space(db, owner)
    assert second != first
    assert str(_one(db, "select public.business_space_of(%s)", (owner,))) == second
    assert _one(db, "select public.business_space_of(%s)", (users["other"],)) is None


def test_a_forged_space_fails_every_composite_key(db, users) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    space(db, owner)
    others = space(db, other)
    for write in (account, connection, conversation, event, sender_link):
        with _raises(
            db,
            psycopg.errors.ForeignKeyViolation,
            "owner_space_fkey|destination_space_fkey",
        ):
            write(db, owner, others)


def test_observations_stay_in_their_events_space(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    business = space(db, owner)
    business_connection = connection(db, owner, business)
    personal_connection = connection(db, owner)
    business_event = event(db, owner, business)
    personal_event = event(db, owner)

    with _raises(db, psycopg.errors.RaiseException, "import_observation_space_mismatch"):
        observation(db, owner, personal_event, business_connection)
    with _raises(db, psycopg.errors.RaiseException, "import_observation_space_mismatch"):
        observation(db, owner, business_event, personal_connection)
    observation(db, owner, business_event, business_connection)
    moved = observation(db, owner, personal_event, personal_connection)
    with _raises(db, psycopg.errors.RaiseException, "import_observation_space_mismatch"):
        db.execute(
            "update public.financial_import_observations set event_id = %s where id = %s",
            (business_event, moved),
        )
    assert (
        _one(
            db,
            "select count(*) from public.financial_import_observations where event_id = any(%s::uuid[])",
            ([business_event, personal_event],),
        )
        == 2
    )


def test_a_sender_link_takes_its_owners_business_space(db, users) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    business = space(db, owner)
    assert sender_link(db, owner) == business
    with _raises(db, psycopg.errors.RaiseException, "business_space_missing"):
        sender_link(db, other)


def test_a_whatsapp_capture_lands_in_the_linked_business_space(db, users) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    business = space(db, owner)
    sender_link(db, owner)
    others_business = connection(db, other, space(db, other))

    capture(db, owner, connection(db, owner, business))
    with _raises(db, psycopg.errors.RaiseException, "whatsapp_capture_space_mismatch"):
        capture(db, owner, connection(db, owner))
    with _raises(db, psycopg.errors.RaiseException, "whatsapp_capture_space_mismatch"):
        capture(db, owner, others_business)

    db.execute(
        "update public.whatsapp_sender_links set status = 'revoked', revoked_at = now()"
        " where destination_owner_id = %s",
        (owner,),
    )
    with _raises(db, psycopg.errors.RaiseException, "whatsapp_capture_space_mismatch"):
        capture(db, owner, connection(db, owner, business))


def test_a_business_account_is_never_granted_to_a_household(db, users) -> None:  # noqa: ANN001
    owner, other = users["owner"], users["other"]
    household = _one(
        db,
        "insert into public.households (name, created_by, admin_user_id)"
        " values ('Casa', %s, %s) returning id",
        (owner, owner),
    )
    members = {
        user: _one(
            db,
            "insert into public.household_members (household_id, user_id)"
            " values (%s, %s) returning id",
            (household, user),
        )
        for user in (owner, other)
    }

    def grant(account_id: str) -> None:
        db.execute(
            "insert into public.household_account_grants"
            " (household_id, account_id, owner_user_id, owner_membership_id,"
            "  recipient_membership_id)"
            " values (%s, %s, %s, %s, %s)",
            (household, account_id, owner, members[owner], members[other]),
        )

    with _raises(db, psycopg.errors.RaiseException, "business_account_not_shareable"):
        grant(account(db, owner, space(db, owner)))
    personal = account(db, owner)
    grant(personal)
    assert (
        _one(
            db,
            "select count(*) from public.household_account_grants where household_id = %s",
            (household,),
        )
        == 1
    )


def _create(db, user: str, key: str, identity: str, *space_arg: str):  # noqa: ANN001, ANN202
    return _one(
        db,
        "select public.create_financial_account(%s, %s, %s, 'cash', 'DOP', null, 10000,"
        " null, null, null" + (", %s)" if space_arg else ")"),
        (user, key, identity, *space_arg),
    )


def _space_of_account(db, account_id: str):  # noqa: ANN001, ANN202
    value = _one(
        db,
        "select owner_space_id from public.financial_accounts where id = %s",
        (account_id,),
    )
    return None if value is None else str(value)


def test_create_account_keeps_the_ten_argument_call_personal(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    created = _create(db, owner, "personal-key", "sha256:a")
    assert created["decision"] == "created"
    assert _space_of_account(db, created["account_id"]) is None
    assert _create(db, owner, "personal-key", "sha256:a") == {
        "decision": "replay",
        "account_id": created["account_id"],
    }
    assert _create(db, owner, "personal-key", "sha256:b") == {"decision": "conflict"}


def test_the_current_python_caller_still_creates_personal_accounts(
    repository,
    users,  # noqa: ANN001
) -> None:
    from argus.domain.recording.errors import IdempotencyConflict

    owner = users["owner"]

    def create(identity: str):  # noqa: ANN202
        return repository.create(
            user_id=owner,
            idempotency_key="python-caller",
            identity_hash=identity,
            account=shared.CHECKING,
            opening=shared._opening(1_250_000),
            scope=PERSONAL,
        )

    first = create("sha256:a")
    again = create("sha256:a")
    assert (first.created, again.created) == (True, False)
    assert again.stored == first.stored
    with pytest.raises(IdempotencyConflict):
        create("sha256:b")
    with psycopg.connect(shared.DSN) as check:
        assert check.execute(
            "select owner_space_id from public.financial_accounts where user_id = %s",
            (owner,),
        ).fetchall() == [(None,)]


def test_create_account_fingerprint_includes_the_space(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    business = space(db, owner)
    _create(db, owner, "personal-key", "sha256:a")
    assert _create(db, owner, "personal-key", "sha256:a", business) == {
        "decision": "conflict"
    }

    created = _create(db, owner, "business-key", "sha256:a", business)
    assert created["decision"] == "created"
    assert _space_of_account(db, created["account_id"]) == business
    assert _create(db, owner, "business-key", "sha256:a", business) == {
        "decision": "replay",
        "account_id": created["account_id"],
    }
    assert _create(db, owner, "business-key", "sha256:a") == {"decision": "conflict"}
    with _raises(
        db, psycopg.errors.ForeignKeyViolation, "financial_accounts_owner_space_fkey"
    ):
        _create(db, owner, "forged-key", "sha256:a", space(db, users["other"]))


def test_deleting_the_person_removes_the_space_and_its_rows(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    business = space(db, owner)
    rows = {
        "financial_accounts": account(db, owner, business),
        "financial_source_connections": connection(db, owner, business),
        "conversations": conversation(db, owner, business),
        "financial_import_events": event(db, owner, business),
    }
    sender_link(db, owner)
    db.execute("delete from auth.users where id = %s", (owner,))
    assert _one(db, "select count(*) from public.spaces where id = %s", (business,)) == 0
    for table, row_id in rows.items():
        assert (
            _one(db, f"select count(*) from public.{table} where id = %s", (row_id,)) == 0
        ), table
    assert (
        _one(
            db,
            "select count(*) from public.whatsapp_sender_links where destination_space_id = %s",
            (business,),
        )
        == 0
    )
