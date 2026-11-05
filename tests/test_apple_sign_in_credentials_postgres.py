"""Real-Postgres proof for stored Sign in with Apple refresh tokens.

Runs against ``ARGUS_DISPOSABLE_DATABASE_URL`` with every migration applied.
Proves what the in-memory twin cannot: no client role can read or write the
table, RLS is on with no policy, the service role can, the restrict key keeps
an auth user with an unrevoked token from being deleted, the full capture
and revoke run against the migration, and the two ways a row ends without a
200 from Apple: ``invalid_grant`` (already revoked) and ``discard_unreadable``
for a token this key sealed that no longer opens. A token sealed under another
key, or with no key fingerprint, is kept (Priya B1).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.apple_sign_in.client import AppleAuthClient
from argus.domain.apple_sign_in.credentials import (
    SOURCE,
    AppleCredentialService,
    AppleRevocationPending,
    DiscardOutcome,
    RevokeOutcome,
)
from argus.domain.ingestion.secrets import SecretBox

from tests.apple_sign_in_support import (
    BUNDLE_ID,
    SUBJECT,
    FakeApple,
    config,
    generated_key,
)

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)
psycopg = pytest.importorskip("psycopg")
psycopg_pool = pytest.importorskip("psycopg_pool")

NOW = datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)
TABLE = "public.apple_sign_in_credentials"


@pytest.fixture
def users():  # noqa: ANN201
    ids = {label: str(uuid4()) for label in ("apple", "other")}
    with psycopg.connect(DSN) as connection:
        for label, user_id in ids.items():
            connection.execute(
                "insert into auth.users (id, email) values (%s, %s)",
                (user_id, f"siwa-{label}-{user_id}@example.test"),
            )
        connection.execute(
            "insert into auth.identities (id, user_id, provider, provider_id, identity_data) "
            "values (%s::uuid, %s::uuid, 'apple', %s, %s::jsonb)",
            (str(uuid4()), ids["apple"], SUBJECT, json.dumps({"sub": SUBJECT})),
        )
    yield ids
    with psycopg.connect(DSN) as connection:
        connection.execute(
            f"delete from {TABLE} where user_id = any(%s::uuid[])", (list(ids.values()),)
        )
        connection.execute(
            "delete from auth.users where id = any(%s::uuid[])", (list(ids.values()),)
        )


@pytest.fixture
def pool():  # noqa: ANN201
    application_name = f"apple-credentials-test-{uuid4()}"
    made = psycopg_pool.ConnectionPool(
        DSN,
        min_size=0,
        max_size=4,
        open=True,
        name=application_name,
        kwargs={"application_name": application_name},
    )
    yield made
    made.close()


@pytest.fixture
def repo(pool):  # noqa: ANN001, ANN201
    from argus.domain.apple_sign_in.credentials_postgres import (
        PostgresAppleCredentialRepository,
    )

    return PostgresAppleCredentialRepository(pool)


def _as(cursor, role: str, user_id: str | None = None) -> None:  # noqa: ANN001
    cursor.execute(f"set local role {role}")
    if user_id:
        cursor.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps({"sub": user_id, "role": role}),),
        )


def test_repository_upserts_one_row_and_compare_deletes(repo, users) -> None:  # noqa: ANN001
    user = users["apple"]
    repo.upsert(
        user_id=user, client_id=BUNDLE_ID, secret_ciphertext=b"\x01" + b"a" * 40, now=NOW
    )
    later = NOW + timedelta(days=3)
    repo.upsert(
        user_id=user,
        client_id=BUNDLE_ID,
        secret_ciphertext=b"\x01" + b"b" * 40,
        now=later,
    )

    row = repo.get(user_id=user)
    assert row.secret_ciphertext == b"\x01" + b"b" * 40
    assert (row.captured_at, row.updated_at) == (NOW, later)
    assert repo.get(user_id=users["other"]) is None

    assert (
        repo.delete_if_unchanged(user_id=user, secret_ciphertext=b"\x01" + b"a" * 40)
        is False
    )
    assert repo.get(user_id=user) is not None
    assert (
        repo.delete_if_unchanged(user_id=user, secret_ciphertext=b"\x01" + b"b" * 40)
        is True
    )
    assert repo.get(user_id=user) is None


def test_rls_is_on_with_no_policy_and_no_client_privilege(repo, users) -> None:  # noqa: ANN001
    user = users["apple"]
    repo.upsert(
        user_id=user, client_id=BUNDLE_ID, secret_ciphertext=b"\x01" + b"a" * 40, now=NOW
    )
    with psycopg.connect(DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select relrowsecurity from pg_class where oid = %s::regclass", (TABLE,)
            )
            assert cursor.fetchone() == (True,)
            cursor.execute(
                "select count(*) from pg_policies where schemaname = 'public' "
                "and tablename = 'apple_sign_in_credentials'"
            )
            assert cursor.fetchone() == (0,)
        for role in ("anon", "authenticated"):
            for statement in (
                f"select client_id from {TABLE}",
                f"select secret_ciphertext from {TABLE}",
                f"insert into {TABLE} (user_id, client_id, secret_ciphertext) "
                f"values ('{user}', 'x.y', '\\x00')",
                f"update {TABLE} set client_id = 'x.y'",
                f"delete from {TABLE}",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with connection.transaction(), connection.cursor() as cursor:
                        _as(cursor, role, user)
                        cursor.execute(statement)


def test_the_service_role_reads_and_writes(users) -> None:  # noqa: ANN001
    user = users["apple"]
    with psycopg.connect(DSN) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            _as(cursor, "service_role")
            cursor.execute(
                f"insert into {TABLE} (user_id, client_id, secret_ciphertext) values (%s, %s, %s)",
                (user, BUNDLE_ID, b"\x01" + b"z" * 40),
            )
            cursor.execute(
                f"update {TABLE} set updated_at = now() where user_id = %s", (user,)
            )
            cursor.execute(f"select count(*) from {TABLE} where user_id = %s", (user,))
            assert cursor.fetchone() == (1,)
            cursor.execute(f"delete from {TABLE} where user_id = %s", (user,))
            assert cursor.rowcount == 1


@pytest.mark.parametrize(
    ("client_id", "ciphertext", "key_id"),
    [
        ("", b"\x01" + b"a" * 40, None),
        ("bad id", b"\x01" + b"a" * 40, None),
        (BUNDLE_ID, b"short", None),
        # The fingerprint is 32 hex characters, never anything key-like.
        (BUNDLE_ID, b"\x01" + b"a" * 40, "k" * 32),
    ],
)
def test_constraints_refuse_malformed_rows(
    repo, users, client_id, ciphertext, key_id
) -> None:  # noqa: ANN001
    with pytest.raises(psycopg.errors.CheckViolation):
        repo.upsert(
            user_id=users["apple"],
            client_id=client_id,
            secret_ciphertext=ciphertext,
            now=NOW,
            key_id=key_id,
        )


def test_an_unrevoked_token_blocks_deleting_the_auth_user(repo, users) -> None:  # noqa: ANN001
    user = users["apple"]
    repo.upsert(
        user_id=user, client_id=BUNDLE_ID, secret_ciphertext=b"\x01" + b"a" * 40, now=NOW
    )
    with psycopg.connect(DSN) as connection:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with connection.transaction():
                connection.execute("delete from auth.users where id = %s", (user,))
        assert repo.delete_if_unchanged(
            user_id=user, secret_ciphertext=b"\x01" + b"a" * 40
        )
        with connection.transaction():
            connection.execute("delete from auth.users where id = %s", (user,))
        with connection.cursor() as cursor:
            cursor.execute("select count(*) from auth.users where id = %s", (user,))
            assert cursor.fetchone() == (0,)


def test_capture_then_revoke_against_the_migration(repo, users) -> None:  # noqa: ANN001
    key = generated_key()
    apple = FakeApple(public_key=key.public_key())
    box = SecretBox(os.urandom(32))
    client = AppleAuthClient(
        config(key), transport=apple.transport(), sleep=lambda _s: None
    )
    service = AppleCredentialService(repo, box=box, client=client, clock=lambda: NOW)
    user = users["apple"]

    refresh = apple.grant()
    service.capture(user_id=user, authorization_code="c.code")
    row = repo.get(user_id=user)
    assert refresh.encode() not in row.secret_ciphertext
    assert row.key_id == box.key_id  # secret_key_fingerprint, read back
    assert box.open(row.secret_ciphertext, source=SOURCE, connection_id=user) == refresh

    apple.revoke_responses += [(400, {"error": "invalid_client"})]
    with pytest.raises(AppleRevocationPending):
        service.revoke(user_id=user)
    assert repo.get(user_id=user) is not None

    assert service.revoke(user_id=user) is RevokeOutcome.REVOKED
    assert apple.calls[-1][1]["token"] == refresh
    assert repo.get(user_id=user) is None
    client.close()


def _service(repo, box: SecretBox) -> tuple[AppleCredentialService, FakeApple]:  # noqa: ANN001
    key = generated_key()
    apple = FakeApple(public_key=key.public_key())
    client = AppleAuthClient(
        config(key), transport=apple.transport(), sleep=lambda _s: None
    )
    return AppleCredentialService(repo, box=box, client=client, clock=lambda: NOW), apple


def _delete_auth_user(user: str) -> None:
    with psycopg.connect(DSN) as connection, connection.transaction():
        connection.execute("delete from auth.users where id = %s", (user,))


def _auth_user_exists(user: str) -> bool:
    with psycopg.connect(DSN) as connection, connection.cursor() as cursor:
        cursor.execute("select count(*) from auth.users where id = %s", (user,))
        return cursor.fetchone() == (1,)


def test_invalid_grant_on_revoke_deletes_the_row_and_frees_the_user(repo, users) -> None:  # noqa: ANN001
    service, apple = _service(repo, SecretBox(os.urandom(32)))
    user = users["apple"]
    apple.grant()
    service.capture(user_id=user, authorization_code="c.code")

    apple.revoke_responses.append((400, {"error": "invalid_grant"}))
    assert service.revoke(user_id=user) is RevokeOutcome.ALREADY_REVOKED
    assert repo.get(user_id=user) is None
    _delete_auth_user(user)
    assert not _auth_user_exists(user)


@pytest.mark.parametrize("sealed_by", ["rotated_away_key", "no_fingerprint"])
def test_a_row_another_key_may_open_is_kept(repo, users, sealed_by) -> None:  # noqa: ANN001
    """Priya B1: the key rotated, or a process on the old key is still
    running. The row may be live for the key that sealed it, so it is kept
    and the restrict key still holds the auth user."""
    user = users["apple"]
    old_box = SecretBox(os.urandom(32))
    repo.upsert(
        user_id=user,
        client_id=BUNDLE_ID,
        secret_ciphertext=old_box.seal("r.live", source=SOURCE, connection_id=user),
        now=NOW,
        key_id=old_box.key_id if sealed_by == "rotated_away_key" else None,
    )
    service, apple = _service(repo, SecretBox(os.urandom(32)))

    with pytest.raises(AppleRevocationPending) as pending:
        service.revoke(user_id=user)
    assert pending.value.reason == "credential_unreadable"
    with pytest.raises(AppleRevocationPending) as pending:
        service.discard_unreadable(user_id=user)
    assert pending.value.reason == "key_unproven"
    assert repo.get(user_id=user) is not None
    assert apple.calls == []
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _delete_auth_user(user)


def test_an_unreadable_row_this_key_sealed_is_discarded(repo, users) -> None:  # noqa: ANN001
    """Sealed under this key (the fingerprint round-trips through the table)
    and it still doesn't open: dead, so discarded, and the user can go."""
    user = users["apple"]
    box = SecretBox(os.urandom(32))
    damaged = SecretBox(os.urandom(32)).seal("r.x", source=SOURCE, connection_id=user)
    repo.upsert(
        user_id=user,
        client_id=BUNDLE_ID,
        secret_ciphertext=damaged,
        now=NOW,
        key_id=box.key_id,
    )
    assert repo.get(user_id=user).key_id == box.key_id
    service, apple = _service(repo, box)

    assert service.discard_unreadable(user_id=user) is DiscardOutcome.DISCARDED
    assert repo.get(user_id=user) is None
    assert apple.calls == []
    _delete_auth_user(user)
    assert not _auth_user_exists(user)
    assert service.discard_unreadable(user_id=user) is DiscardOutcome.NOTHING_STORED


def test_discard_keeps_a_readable_row_and_the_restrict_key(repo, users) -> None:  # noqa: ANN001
    service, apple = _service(repo, SecretBox(os.urandom(32)))
    user = users["apple"]
    apple.grant()
    service.capture(user_id=user, authorization_code="c.code")

    assert service.discard_unreadable(user_id=user) is DiscardOutcome.READABLE
    assert repo.get(user_id=user) is not None
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _delete_auth_user(user)
    assert (
        service.discard_unreadable(user_id=users["other"])
        is DiscardOutcome.NOTHING_STORED
    )
