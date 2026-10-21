from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from argus.domain.account_deletion.service import (
    AccountDeletionRejected,
    AccountDeletionService,
    subject_hash,
)
from argus.domain.apple_sign_in.client import AppleAuthClient
from argus.domain.apple_sign_in.credentials import AppleCredentialService
from argus.domain.apple_sign_in.credentials_postgres import (
    PostgresAppleCredentialRepository,
)
from argus.domain.household.postgres import PostgresHouseholdRepository
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.secrets import SecretBox, SecretUnreadable
from argus.domain.owner_scope import PERSONAL
from faker import Faker
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from tests import apple_sign_in_support as apple
from tests.household.financial_fixtures import DSN

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


@pytest.fixture
def credential_owner():
    user_id = str(uuid4())
    with ConnectionPool(DSN, min_size=1, max_size=2) as pool:
        with pool.connection() as connection:
            connection.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (user_id, Faker().email(domain="example.test")),
            )
        try:
            yield pool, user_id
        finally:
            with pool.connection() as connection:
                connection.execute(
                    "delete from public.apple_sign_in_credentials where user_id=%s",
                    (user_id,),
                )
                connection.execute(
                    "delete from argus_private.account_deletion_runs where user_id=%s",
                    (user_id,),
                )
                connection.execute("delete from auth.users where id=%s", (user_id,))


@pytest.mark.parametrize("source", ["plaid", "gmail"])
@pytest.mark.parametrize("fingerprint", ["new_key", "legacy_writer"])
def test_set_secret_replaces_the_old_fingerprint(credential_owner, source, fingerprint):
    pool, user_id = credential_owner
    now = datetime.now(timezone.utc)
    k1, k2 = SecretBox(bytes(range(32))), SecretBox(bytes(reversed(range(32))))
    repository = PostgresConnectionRepository(pool)
    connection_id = str(uuid4())
    repository.create(
        user_id=user_id,
        source=source,
        external_ref=str(uuid4()),
        label=None,
        now=now,
        connection_id=connection_id,
        secret=k1.seal("synthetic-old", source=source, connection_id=connection_id),
        secret_key=k1.key_id,
        scope=PERSONAL,
    )
    sealed = k2.seal("synthetic-new", source=source, connection_id=connection_id)
    key_id = k2.key_id if fingerprint == "new_key" else None
    repository.set_secret(
        connection_id=connection_id,
        secret=sealed,
        status="active",
        now=now + timedelta(seconds=1),
        secret_key=key_id,
    )
    stored = repository.get(user_id=user_id, connection_id=connection_id, scope=PERSONAL)
    assert stored.secret == sealed
    assert stored.secret_key == key_id
    assert (
        k2.open(stored.secret, source=source, connection_id=connection_id)
        == "synthetic-new"
    )
    with pytest.raises(SecretUnreadable):
        k1.open(stored.secret, source=source, connection_id=connection_id)


@pytest.mark.parametrize("fingerprint", ["new_key", "legacy_writer"])
def test_apple_upsert_replaces_the_old_fingerprint(credential_owner, fingerprint):
    pool, user_id = credential_owner
    now = datetime.now(timezone.utc)
    repository = PostgresAppleCredentialRepository(pool)
    k1, k2 = SecretBox(bytes(range(32))), SecretBox(bytes(reversed(range(32))))
    for key, at, key_id in [
        (k1, now, k1.key_id),
        (k2, now + timedelta(seconds=1), k2.key_id if fingerprint == "new_key" else None),
    ]:
        repository.upsert(
            user_id=user_id,
            client_id=apple.BUNDLE_ID,
            secret_ciphertext=key.seal(
                "synthetic-token", source="apple_sign_in", connection_id=user_id
            ),
            now=at,
            key_id=key_id,
        )
    stored = repository.get(user_id=user_id)
    assert stored.key_id == key_id
    assert stored.captured_at == now
    assert stored.updated_at == now + timedelta(seconds=1)
    assert (
        k2.open(stored.secret_ciphertext, source="apple_sign_in", connection_id=user_id)
        == "synthetic-token"
    )
    with pytest.raises(SecretUnreadable):
        k1.open(stored.secret_ciphertext, source="apple_sign_in", connection_id=user_id)


def test_apple_recapture_passes_the_new_key_to_postgres(credential_owner):
    pool, user_id = credential_owner
    with pool.connection() as connection:
        connection.execute(
            "insert into auth.identities(id,user_id,provider,provider_id,identity_data) "
            "values(%s,%s,'apple',%s,%s)",
            (uuid4(), user_id, apple.SUBJECT, Jsonb({"sub": apple.SUBJECT})),
        )
    repository = PostgresAppleCredentialRepository(pool)
    signing_key = apple.generated_key()
    endpoint = apple.FakeApple(public_key=signing_key.public_key())
    now = datetime.now(timezone.utc)
    keys = [SecretBox(bytes(range(32))), SecretBox(bytes(reversed(range(32))))]
    for index, key in enumerate(keys):
        token = endpoint.grant()
        service = AppleCredentialService(
            repository,
            box=key,
            client=AppleAuthClient(
                apple.config(signing_key), transport=endpoint.transport()
            ),
            clock=lambda: now,
        )
        try:
            service.capture(
                user_id=user_id,
                authorization_code=f"synthetic-code-{index}",
            )
        finally:
            service.close()
        stored = repository.get(user_id=user_id)
        assert stored.key_id == key.key_id
        assert stored.apple_subject == apple.SUBJECT
        assert (
            key.open(
                stored.secret_ciphertext, source="apple_sign_in", connection_id=user_id
            )
            == token
        )
    with pytest.raises(SecretUnreadable):
        keys[0].open(
            stored.secret_ciphertext, source="apple_sign_in", connection_id=user_id
        )


@pytest.mark.parametrize("age_days", [0, 8])
def test_force_refusal_and_dry_run_leave_postgres_and_providers_unchanged(
    credential_owner, age_days
):
    pool, user_id = credential_owner
    now = datetime.now(timezone.utc)
    pending = now - timedelta(days=age_days)
    steps = {
        "analytics": "pending",
        "pending_since": {"analytics": pending.isoformat()},
        "last_error": {"analytics": "analytics_adapter_unconfigured"},
    }
    with pool.connection() as connection:
        run_id = connection.execute(
            "insert into argus_private.account_deletion_runs (user_id,subject_hash,analytics_distinct_id,status,steps) values(%s,%s,%s,'data_deleted',%s) returning id",
            (user_id, subject_hash(user_id), "synthetic-distinct-id", Jsonb(steps)),
        ).fetchone()[0]
        before = connection.execute(
            "select to_jsonb(r) from argus_private.account_deletion_runs r where id=%s",
            (run_id,),
        ).fetchone()
    auth, revoker, analytics = MagicMock(), MagicMock(), MagicMock()
    service = AccountDeletionService(
        households=PostgresHouseholdRepository(pool, MagicMock()),
        auth_admin=auth,
        revoker=revoker,
        analytics=analytics,
        clock=lambda: now,
    )
    request = dict(
        user_id=user_id,
        step="analytics",
        reason="synthetic unavailable provider",
        operator="synthetic-operator",
    )
    if age_days == 0:
        with pytest.raises(AccountDeletionRejected, match="step_pending_under_7_days"):
            service.force_complete_step(**request, confirm=True)
    else:
        assert service.force_complete_step(**request) == {
            "step": "analytics",
            "pending_days": age_days,
            "last_error": "analytics_adapter_unconfigured",
            "dry_run": True,
            "forced": False,
        }
    with pool.connection() as connection:
        assert (
            connection.execute(
                "select to_jsonb(r) from argus_private.account_deletion_runs r where id=%s",
                (run_id,),
            ).fetchone()
            == before
        )
        assert connection.execute(
            "select 1 from auth.users where id=%s", (user_id,)
        ).fetchone() == (1,)
    assert auth.mock_calls == revoker.mock_calls == analytics.mock_calls == []
