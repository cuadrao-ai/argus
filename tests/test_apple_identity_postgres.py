# ruff: noqa: F811

import json
from datetime import datetime, timezone
from threading import Event, Thread
from uuid import uuid4

import pytest
from argus.domain.apple_sign_in.client import AppleAuthClient
from argus.domain.apple_sign_in.credentials import (
    AppleCaptureNotStored,
    AppleCredentialService,
    AppleIdentityMismatch,
)
from argus.domain.apple_sign_in.identity import (
    AppleIdentityUnavailable,
    LinkedAppleIdentity,
    linked_apple_identity,
)
from argus.domain.ingestion.secrets import SecretBox

from tests.apple_sign_in_support import (
    BUNDLE_ID,
    SUBJECT,
    FakeApple,
    config,
    generated_key,
)
from tests.test_apple_sign_in_credentials_postgres import (  # noqa: F401
    DSN,
    pool,
    psycopg,
    repo,
    users,
)

pytestmark = pytest.mark.skipif(not DSN, reason="disposable database not configured")
NOW = datetime.now(timezone.utc)


def save(repo, user, expected=None):
    repo.save_capture(
        user_id=user,
        identity=LinkedAppleIdentity(SUBJECT),
        expected_ciphertext=expected,
        client_id=BUNDLE_ID,
        secret_ciphertext=b"x" * 40,
        now=NOW,
        key_id=SecretBox(b"x" * 32).key_id,
    )


def add_identity(connection, user, subject, provider="apple"):
    connection.execute(
        "insert into auth.identities (id,user_id,provider,provider_id,identity_data) "
        "values (%s::uuid,%s::uuid,%s,%s,%s::jsonb)",
        (str(uuid4()), user, provider, subject, json.dumps({"sub": subject})),
    )


def test_reader_rejects_conflicting_and_malformed_auth_rows(repo, users):
    user = users["apple"]
    with psycopg.connect(DSN) as connection:
        assert linked_apple_identity(connection, user) == LinkedAppleIdentity(SUBJECT)
        add_identity(connection, user, "other")
    with pytest.raises(AppleIdentityUnavailable):
        repo.linked_identity(user_id=user)
    with psycopg.connect(DSN) as connection:
        connection.execute(
            "delete from auth.identities where user_id=%s::uuid and provider_id='other'",
            (user,),
        )
        connection.execute(
            "update auth.identities set identity_data='{}'::jsonb where user_id=%s::uuid",
            (user,),
        )
    with pytest.raises(AppleIdentityUnavailable):
        repo.linked_identity(user_id=user)


def test_legacy_metadata_is_unverified_and_capture_records_subject(repo, users):
    user = users["apple"]
    repo.upsert(user_id=user, client_id=BUNDLE_ID, secret_ciphertext=b"old" * 20, now=NOW)
    old = repo.get(user_id=user)
    assert old.apple_subject is None
    save(repo, user, old.secret_ciphertext)
    captured = repo.get(user_id=user)
    assert captured.apple_subject == SUBJECT
    assert SUBJECT not in repr(captured)


@pytest.mark.parametrize("change", ["replace", "remove"])
def test_older_capture_cannot_overwrite_or_recreate_current_row(repo, users, change):
    user = users["apple"]
    save(repo, user)
    snapshot = repo.get(user_id=user)
    if change == "replace":
        repo.upsert(
            user_id=user, client_id=BUNDLE_ID, secret_ciphertext=b"new" * 20, now=NOW
        )
    else:
        repo.delete_if_unchanged(
            user_id=user, secret_ciphertext=snapshot.secret_ciphertext
        )
    with pytest.raises(AppleCaptureNotStored):
        save(repo, user, snapshot.secret_ciphertext)
    current = repo.get(user_id=user)
    assert (
        current.secret_ciphertext == b"new" * 20
        if change == "replace"
        else current is None
    )


def test_identity_change_during_http_is_rejected_without_transaction_across_exchange(
    repo, users
):
    user = users["apple"]
    key = generated_key()
    apple = FakeApple(key.public_key())
    apple.grant()

    def transport(request):
        if request.url.path == "/auth/token":
            with psycopg.connect(DSN) as connection:
                connection.execute("set local lock_timeout='300ms'")
                connection.execute(
                    "update auth.identities set provider_id=%s, identity_data=%s::jsonb where user_id=%s::uuid",
                    ("changed", json.dumps({"sub": "changed"}), user),
                )
        return apple(request)

    import httpx

    service = AppleCredentialService(
        repo,
        box=SecretBox(b"x" * 32),
        client=AppleAuthClient(config(key), transport=httpx.MockTransport(transport)),
        clock=lambda: NOW,
    )
    try:
        with pytest.raises(AppleIdentityMismatch):
            service.capture(user_id=user, authorization_code="c.code")
        assert repo.get(user_id=user) is None
        assert [path for path, _ in apple.calls] == ["/auth/token", "/auth/revoke"]
    finally:
        service.close()


@pytest.mark.parametrize(
    "mutation", ["insert", "update", "delete", "provider_flip", "move", "inbound_move"]
)
def test_storage_locks_fence_all_auth_identity_mutations(
    repo, users, monkeypatch, mutation
):
    import argus.domain.apple_sign_in.credentials_postgres as module

    user = users["apple"]
    with psycopg.connect(DSN) as connection:
        add_identity(connection, user, "email", provider="email")
        add_identity(connection, users["other"], "incoming", provider="email")
    locked, release = Event(), Event()
    original = module.linked_apple_identity
    failures = []

    def gated(connection, user_id, *, lock=False):
        value = original(connection, user_id, lock=lock)
        if lock:
            locked.set()
            assert release.wait(5)
        return value

    monkeypatch.setattr(module, "linked_apple_identity", gated)

    def capture():
        try:
            save(repo, user)
        except BaseException as exc:
            failures.append(exc)

    thread = Thread(target=capture)
    thread.start()
    try:
        assert locked.wait(5)
        with psycopg.connect(DSN) as connection:
            connection.execute("set local lock_timeout='200ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                if mutation == "insert":
                    add_identity(connection, user, "second")
                elif mutation == "update":
                    connection.execute(
                        "update auth.identities set identity_data='{}'::jsonb where user_id=%s::uuid and provider='apple'",
                        (user,),
                    )
                elif mutation == "delete":
                    connection.execute(
                        "delete from auth.identities where user_id=%s::uuid", (user,)
                    )
                elif mutation == "provider_flip":
                    connection.execute(
                        "update auth.identities set provider='apple' where user_id=%s::uuid and provider='email'",
                        (user,),
                    )
                elif mutation == "inbound_move":
                    connection.execute(
                        "update auth.identities set user_id=%s::uuid where user_id=%s::uuid",
                        (user, users["other"]),
                    )
                else:
                    connection.execute(
                        "update auth.identities set user_id=%s::uuid where user_id=%s::uuid",
                        (users["other"], user),
                    )
            connection.rollback()
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert failures == []
    assert repo.get(user_id=user).apple_subject == SUBJECT


def test_identity_insert_committed_while_parent_lock_waits_is_seen(repo, users, pool):
    user = users["apple"]
    failures = []
    started = Event()
    first_poll = Event()

    def capture():
        started.set()
        try:
            assert first_poll.wait(5)
            save(repo, user)
        except BaseException as exc:
            failures.append(exc)

    thread = Thread(target=capture)
    try:
        with psycopg.connect(DSN) as writer:
            add_identity(writer, user, "conflict")
            thread.start()
            assert started.wait(5)
            with psycopg.connect(DSN, autocommit=True) as observer:
                import time

                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    count = observer.execute(
                        "select count(*) from pg_stat_activity where wait_event_type='Lock' "
                        "and query like 'select id from auth.users%%' "
                        "and application_name=%s",
                        (pool.name,),
                    ).fetchone()[0]
                    first_poll.set()
                    if count:
                        break
                    time.sleep(0.02)
                assert count
            writer.commit()
    finally:
        first_poll.set()
        if thread.ident is not None:
            thread.join(5)
    assert not thread.is_alive()
    assert len(failures) == 1 and isinstance(failures[0], AppleIdentityUnavailable)
    assert repo.get(user_id=user) is None
