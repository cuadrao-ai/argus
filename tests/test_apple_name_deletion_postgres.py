# ruff: noqa: F811

from __future__ import annotations

import secrets
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Event
from time import monotonic, sleep

import psycopg
import pytest
from argus.api.account_deletion_runtime import household_repository
from argus.domain.account_deletion.service import (
    AccountDeletionIncomplete,
    AccountDeletionService,
    subject_hash,
)
from argus.domain.apple_sign_in.client import AppleAuthClient
from argus.domain.apple_sign_in.credentials import SOURCE, AppleCredentialService
from argus.domain.apple_sign_in.credentials_postgres import (
    PostgresAppleCredentialRepository,
)
from argus.domain.apple_sign_in.identity import linked_apple_identity
from argus.domain.apple_sign_in.name import (
    AppleNameAccountUnavailable,
    initialize_apple_display_name,
)
from argus.domain.ingestion.secrets import SecretBox
from argus.observability.analytics_deletion import RecordingAnalyticsDeletion

from tests.apple_sign_in_support import BUNDLE_ID, FakeApple, config, generated_key
from tests.test_account_deletion_postgres import SqlAuthAdmin
from tests.test_apple_name_postgres import DSN, apple_profile, fake, pool  # noqa: F401

pytestmark = pytest.mark.skipif(not DSN, reason="isolated Postgres required")


class InterruptedRequest(Exception):
    pass


@pytest.fixture
def apple_service(apple_profile, pool):
    service, provider = build_apple_service(apple_profile, pool)
    try:
        yield service, provider
    finally:
        service.close()
        with psycopg.connect(DSN) as connection:
            connection.execute(
                "delete from public.apple_sign_in_credentials where user_id=%s",
                (apple_profile,),
            )
    assert provider.calls == []


def build_apple_service(user_id, pool):
    key = generated_key()
    provider = FakeApple(key.public_key())
    box = SecretBox(secrets.token_bytes(32))
    repository = PostgresAppleCredentialRepository(pool)
    identity = repository.linked_identity(user_id=user_id)
    repository.save_capture(
        user_id=user_id,
        identity=identity,
        expected_ciphertext=None,
        client_id=BUNDLE_ID,
        secret_ciphertext=box.seal(
            "synthetic-refresh", source=SOURCE, connection_id=user_id
        ),
        now=datetime.now(timezone.utc),
        key_id=box.key_id,
    )
    service = AppleCredentialService(
        repository,
        box=box,
        client=AppleAuthClient(config(key), transport=provider.transport()),
        clock=lambda: datetime.now(timezone.utc),
    )
    return service, provider


def deletion_service(pool, apple):
    return AccountDeletionService(
        households=household_repository(pool),
        auth_admin=SqlAuthAdmin(),
        revoker=None,
        analytics=RecordingAnalyticsDeletion(),
        apple=apple,
        allow_fake_analytics=True,
    )


def profile(connection, user_id):
    return connection.execute(
        "select display_name,preferred_name,name_initialization_closed,updated_at "
        "from public.profiles where id=%s",
        (user_id,),
    ).fetchone()


@pytest.mark.parametrize("name_first", [False, True])
@pytest.mark.parametrize("interrupt_first", [False, True])
def test_name_and_actual_deletion_admission_linearize_at_parent_lock(
    apple_profile, pool, apple_service, name_first, interrupt_first
):
    apple, provider = apple_service
    first_written, release = Event(), Event()
    name = fake.name()
    subject = subject_hash(apple_profile)

    class HeldPool:
        @contextmanager
        def connection(self):
            with pool.connection() as connection, connection.transaction():
                yield connection
                first_written.set()
                assert release.wait(5)
                if interrupt_first:
                    raise InterruptedRequest

    def save_name(held=False):
        return initialize_apple_display_name(
            HeldPool() if held else pool,
            user_id=apple_profile,
            display_name=name,
        )

    def admit_deletion(held=False):
        return deletion_service(HeldPool() if held else pool, apple)._claim(
            apple_profile, subject
        )

    with psycopg.connect(DSN) as connection:
        before = profile(connection, apple_profile)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(save_name if name_first else admit_deletion, True)
        try:
            assert first_written.wait(5)
            second = executor.submit(admit_deletion if name_first else save_name)
            deadline = monotonic() + 3
            with psycopg.connect(DSN, autocommit=True) as observer:
                while monotonic() < deadline:
                    waiting = observer.execute(
                        "select count(*) from pg_stat_activity where application_name=%s "
                        "and cardinality(pg_blocking_pids(pid)) > 0",
                        (pool.kwargs["application_name"],),
                    ).fetchone()[0]
                    if waiting:
                        break
                    sleep(0.01)
                assert waiting == 1
        finally:
            release.set()
        if interrupt_first:
            with pytest.raises(InterruptedRequest):
                first.result(timeout=5)
        else:
            first.result(timeout=5)
        if not name_first and not interrupt_first:
            with pytest.raises(AppleNameAccountUnavailable):
                second.result(timeout=5)
        else:
            second.result(timeout=5)

    with psycopg.connect(DSN) as connection:
        saved = profile(connection, apple_profile)
        if name_first == interrupt_first:
            assert saved == before
        else:
            assert saved[:3] == (name, None, True)
        runs = connection.execute(
            "select id::text,claim_id::text from argus_private.account_deletion_runs "
            "where user_id=%s",
            (apple_profile,),
        ).fetchall()
    service = deletion_service(pool, apple)
    if not name_first and interrupt_first:
        assert runs == []
        run = service._claim(apple_profile, subject)
    else:
        assert len(runs) == 1
        with pytest.raises(AccountDeletionIncomplete) as duplicate:
            service._claim(apple_profile, subject)
        assert duplicate.value.reason == "in_progress"
        service._release(*runs[0])
        run = service._claim(apple_profile, subject)
        assert run["id"] == runs[0][0]
    with psycopg.connect(DSN) as connection:
        after_admission = profile(connection, apple_profile)
    for _ in range(2):
        with pytest.raises(AppleNameAccountUnavailable):
            save_name()
    with psycopg.connect(DSN) as connection:
        assert profile(connection, apple_profile) == after_admission
        assert connection.execute(
            "select count(*) from argus_private.account_deletion_runs where user_id=%s",
            (apple_profile,),
        ).fetchone() == (1,)
        assert linked_apple_identity(connection, apple_profile) is not None
    assert provider.calls == []
    service._release(run["id"], run["claim"])
