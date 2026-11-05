# ruff: noqa: F811

from __future__ import annotations

import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from argus.domain.account_deletion.service import (
    AccountDeletionIncomplete,
    AccountDeletionService,
    subject_hash,
)
from argus.domain.apple_sign_in.credentials import AppleCaptureNotStored
from argus.domain.ingestion.secrets import SecretBox
from argus.observability.product_events import actor_hash_for_user

from tests.apple_sign_in_support import SUBJECT
from tests.household.financial_fixtures import DSN
from tests.household.financial_fixtures import lane as lane  # noqa: F401
from tests.test_account_deletion_fk_census_postgres import (
    _invite_code_secret,  # noqa: F401
)
from tests.test_account_deletion_postgres import (  # noqa: F401
    SqlAuthAdmin,
    _service,
    world,
)
from tests.test_account_deletion_third_parties_postgres import _Apple

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def link(user_id, subject=SUBJECT):
    with psycopg.connect(DSN) as c:
        c.execute(
            "insert into auth.identities (id,user_id,provider,provider_id,identity_data) values (%s,%s,'apple',%s,%s::jsonb)",
            (str(uuid4()), user_id, subject, json.dumps({"sub": subject})),
        )


@pytest.fixture
def apple(lane, monkeypatch):
    made = _Apple([])
    run_ids = set()
    original_claim = AccountDeletionService._claim

    def tracked_claim(self, *args, **kwargs):
        run = original_claim(self, *args, **kwargs)
        if run is not None:
            run_ids.add(run["id"])
        return run

    monkeypatch.setattr(AccountDeletionService, "_claim", tracked_claim)
    yield made
    with psycopg.connect(DSN) as c:
        c.execute(
            "delete from public.apple_sign_in_credentials where user_id = any(%s::uuid[])",
            (lane[2],),
        )
        c.execute(
            "delete from argus_private.account_deletion_runs where user_id = any(%s::uuid[])",
            (lane[2],),
        )
        c.execute(
            "delete from argus_private.account_deletion_runs where id = any(%s::uuid[])",
            (list(run_ids),),
        )
        assert not c.execute(
            "select 1 from public.apple_sign_in_credentials where user_id = any(%s::uuid[])",
            (lane[2],),
        ).fetchall()
        assert not c.execute(
            "select 1 from argus_private.account_deletion_runs where id = any(%s::uuid[])",
            (list(run_ids),),
        ).fetchall()
    made.close()


def capture(apple, user):
    apple.fake.grant()
    apple.service.capture(user_id=user, authorization_code="fresh")


def pending(user):
    with psycopg.connect(DSN) as c:
        return str(
            c.execute(
                "insert into argus_private.account_deletion_runs (user_id,subject_hash,analytics_distinct_id,status) values (%s,%s,%s,'data_deleted') returning id",
                (user, subject_hash(user), actor_hash_for_user(user)),
            ).fetchone()[0]
        )


def test_missing_apple_credential_refuses_before_any_protected_effect(lane, apple):
    user = lane[2][0]
    link(user)
    admin = SqlAuthAdmin()
    service = _service(lane, admin, apple=apple.service)
    try:
        service.delete_account(user_id=user)
    except Exception as exc:
        assert getattr(exc, "code", None) == "apple_reauthorization_required"
    else:
        pytest.fail(
            f"Deletion admitted without credential; banned={len(admin.locked)}, deleted={len(admin.deleted)}"
        )
    assert admin.locked == admin.created == admin.deleted == []
    assert service._analytics.calls == []
    assert service._revoker.calls == []
    assert apple.fake.calls == []
    with psycopg.connect(DSN) as c:
        assert (
            c.execute(
                "select 1 from argus_private.account_deletion_runs where user_id=%s",
                (user,),
            ).fetchone()
            is None
        )
        assert c.execute("select 1 from auth.users where id=%s", (user,)).fetchone()


@pytest.mark.parametrize(
    "invalid", ["unbound", "mismatch", "unreadable", "unavailable", "malformed"]
)
def test_bad_admission_keeps_account_intact(lane, apple, invalid):
    user = lane[2][0]
    link(user)
    capture(apple, user)
    with psycopg.connect(DSN) as c:
        if invalid == "unbound":
            c.execute(
                "update public.apple_sign_in_credentials set apple_subject=null where user_id=%s",
                (user,),
            )
        elif invalid == "mismatch":
            c.execute(
                "update public.apple_sign_in_credentials set apple_subject='changed' where user_id=%s",
                (user,),
            )
        elif invalid == "unreadable":
            c.execute(
                "update public.apple_sign_in_credentials set secret_ciphertext=%s where user_id=%s",
                (
                    SecretBox(secrets.token_bytes(32)).seal(
                        "synthetic", source="apple_sign_in", connection_id=user
                    ),
                    user,
                ),
            )
        elif invalid == "malformed":
            c.execute(
                "update auth.identities set identity_data='{}' where user_id=%s", (user,)
            )
    admin = SqlAuthAdmin()
    service = _service(
        lane, admin, apple=None if invalid == "unavailable" else apple.service
    )
    with pytest.raises(Exception) as raised:
        service.delete_account(user_id=user)
    assert getattr(raised.value, "code", None) == (
        "account_deletion_unavailable"
        if invalid in {"unavailable", "malformed"}
        else "apple_reauthorization_required"
    )
    assert not admin.locked and not admin.created and not admin.deleted


def test_pending_missing_credential_requires_recovery_and_fresh_code_completes(
    lane, apple
):
    user = lane[2][0]
    link(user)
    run_id = pending(user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    with pytest.raises(AccountDeletionIncomplete) as raised:
        service.delete_account(user_id=user)
    assert raised.value.pending == ["apple"]
    apple.fake.grant()
    assert (
        service.delete_account(user_id=user, apple_authorization_code="fresh").status
        == "done"
    )
    with psycopg.connect(DSN) as c:
        assert (
            c.execute(
                "select steps->>'apple_revoke' from argus_private.account_deletion_runs where id=%s",
                (run_id,),
            ).fetchone()[0]
            == "revoked"
        )
        c.execute(
            "delete from argus_private.account_deletion_runs where id=%s", (run_id,)
        )


def test_ordinary_capture_cannot_replace_after_admission(lane, apple):
    user = lane[2][0]
    link(user)
    capture(apple, user)
    original = apple.service.repository.get(user_id=user)
    pending(user)
    apple.fake.grant()
    with pytest.raises(AppleCaptureNotStored):
        apple.service.capture(user_id=user, authorization_code="fresh")
    assert apple.service.repository.get(user_id=user) == original


@pytest.mark.parametrize("claim_lost", [False, True])
def test_provider_success_without_receipt_commit_keeps_token(
    lane, apple, monkeypatch, claim_lost
):
    user = lane[2][0]
    link(user)
    capture(apple, user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    run = service._claim(user, subject_hash(user))
    original = apple.service.repository.get(user_id=user)
    revoke = apple.service.revoke_stored

    def interrupted(row):
        result = revoke(row)
        if claim_lost:
            with psycopg.connect(DSN) as c:
                c.execute(
                    "update argus_private.account_deletion_runs set claim_id=null,claimed_until=null where id=%s",
                    (run["id"],),
                )
            return result
        raise RuntimeError("crash before commit")

    monkeypatch.setattr(apple.service, "revoke_stored", interrupted)
    with pytest.raises((RuntimeError, AccountDeletionIncomplete)):
        service._revoke_apple(user, subject_hash(user), run)
    assert apple.service.repository.get(user_id=user) == original
    with psycopg.connect(DSN) as c:
        assert (
            c.execute(
                "select steps->>'apple_revoke' from argus_private.account_deletion_runs where id=%s",
                (run["id"],),
            ).fetchone()[0]
            is None
        )


def test_receipt_commit_survives_retry_without_token(lane, apple):
    user = lane[2][0]
    link(user)
    capture(apple, user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    run = service._claim(user, subject_hash(user))
    assert service._revoke_apple(user, subject_hash(user), run) is None
    assert apple.service.repository.get(user_id=user) is None
    calls = len(apple.fake.calls)
    assert service._revoke_apple(user, subject_hash(user), run) is None
    assert len(apple.fake.calls) == calls


@pytest.mark.parametrize("change", ["update", "insert"])
def test_subject_update_while_admission_waits_is_seen(lane, apple, monkeypatch, change):
    from threading import Event

    from argus.domain.account_deletion import service as deletion_module

    user = lane[2][0]
    if change == "update":
        link(user)
        capture(apple, user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    entered = Event()
    original = deletion_module.lock_apple_state

    def locking(connection, uid):
        entered.set()
        return original(connection, uid)

    monkeypatch.setattr(deletion_module, "lock_apple_state", locking)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(DSN) as c:
            c.execute("select id from auth.users where id=%s for update", (user,))
            future = pool.submit(service.delete_account, user_id=user)
            assert entered.wait(10)
            if change == "update":
                c.execute(
                    "update auth.identities set provider_id='changed',identity_data='{\"sub\":\"changed\"}' where user_id=%s",
                    (user,),
                )
            else:
                c.execute(
                    "insert into auth.identities (id,user_id,provider,provider_id,identity_data) values (%s,%s,'apple',%s,%s::jsonb)",
                    (str(uuid4()), user, SUBJECT, json.dumps({"sub": SUBJECT})),
                )
        with pytest.raises(Exception) as raised:
            future.result(timeout=10)
        assert getattr(raised.value, "code", None) == "apple_reauthorization_required"


@pytest.mark.parametrize("finish", [False, True])
def test_exchange_failure_after_concurrent_deletion_never_says_account_intact(
    lane, apple, monkeypatch, finish
):
    from threading import Event

    from argus.domain.account_deletion.service import AccountDeletionRejected
    from argus.domain.apple_sign_in.client import AppleError

    user = lane[2][0]
    link(user)
    capture(apple, user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    entered, release = Event(), Event()

    def failing_exchange(code):
        entered.set()
        assert release.wait(10)
        raise AppleError(reason="invalid_grant", status=400)

    monkeypatch.setattr(apple.service._client, "exchange_code", failing_exchange)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            service.delete_account, user_id=user, apple_authorization_code="fresh"
        )
        assert entered.wait(10)
        if finish:
            assert service.delete_account(user_id=user).status == "done"
        else:
            service._claim(user, subject_hash(user))
        release.set()
        with pytest.raises(
            AccountDeletionRejected if finish else AccountDeletionIncomplete
        ) as raised:
            future.result(timeout=10)
        if finish:
            assert str(raised.value) == "unknown_user"


def test_capture_exchange_in_flight_cannot_cross_admission(lane, apple, monkeypatch):
    from threading import Event

    user = lane[2][0]
    link(user)
    capture(apple, user)
    original = apple.service.repository.get(user_id=user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    apple.fake.grant()
    exchange = apple.service._client.exchange_code
    entered, release = Event(), Event()

    def paused(code):
        grant = exchange(code)
        entered.set()
        assert release.wait(10)
        return grant

    monkeypatch.setattr(apple.service._client, "exchange_code", paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            apple.service.capture, user_id=user, authorization_code="fresh"
        )
        assert entered.wait(10)
        service._claim(user, subject_hash(user))
        release.set()
        with pytest.raises(AppleCaptureNotStored):
            future.result(timeout=10)
    assert apple.service.repository.get(user_id=user) == original


@pytest.mark.parametrize("code", [None, "fresh"])
def test_failed_admission_inspection_is_unavailable_before_provider(
    lane, apple, monkeypatch, code
):
    user = lane[2][0]
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)

    def unavailable(*args, **kwargs):
        raise RuntimeError("database inspection failed")

    monkeypatch.setattr(service, "_claim", unavailable)
    with pytest.raises(Exception) as raised:
        service.delete_account(user_id=user, apple_authorization_code=code)
    assert getattr(raised.value, "code", None) == "account_deletion_unavailable"
    assert apple.fake.calls == []
    assert service._auth.locked == []


def test_duplicate_delete_claim_runs_no_protected_effect(lane, apple):
    user = lane[2][0]
    link(user)
    capture(apple, user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    run = service._claim(user, subject_hash(user))
    with pytest.raises(AccountDeletionIncomplete, match="in_progress"):
        service.delete_account(user_id=user)
    assert service._auth.locked == []
    service._release(run["id"], run["claim"])


def test_receipt_transaction_rolls_back_removed_row_on_write_failure(
    lane, apple, monkeypatch
):
    from argus.domain.apple_sign_in.credentials_postgres import (
        PostgresAppleCredentialRepository,
    )

    user = lane[2][0]
    link(user)
    capture(apple, user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    run = service._claim(user, subject_hash(user))
    original = apple.service.repository.get(user_id=user)
    delete = PostgresAppleCredentialRepository.delete_exact_on

    def interrupted(connection, row):
        assert delete(connection, row)
        raise RuntimeError("interrupted before receipt")

    monkeypatch.setattr(PostgresAppleCredentialRepository, "delete_exact_on", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        service._revoke_apple(user, subject_hash(user), run)
    assert apple.service.repository.get(user_id=user) == original


def test_legacy_unbound_pending_credential_revokes_with_receipt(lane, apple):
    user = lane[2][0]
    link(user)
    apple.store(user, legacy=True)
    run_id = pending(user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    assert service.delete_account(user_id=user).status == "done"
    with psycopg.connect(DSN) as c:
        assert (
            c.execute(
                "select steps->>'apple_revoke' from argus_private.account_deletion_runs where id=%s",
                (run_id,),
            ).fetchone()[0]
            == "revoked"
        )


def test_recovery_capture_rechecks_live_claim_after_waiting_for_auth_lock(
    lane, apple, monkeypatch
):
    from datetime import timedelta
    from threading import Event

    from tests.household.financial_fixtures import NOW

    user = lane[2][0]
    link(user)
    capture(apple, user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    run = service._claim(user, subject_hash(user))
    original = apple.service.repository.get(user_id=user)
    apple.fake.grant()
    entered = Event()
    save = apple.service.repository.save_capture

    def waiting(**kwargs):
        entered.set()
        return save(**kwargs)

    monkeypatch.setattr(apple.service.repository, "save_capture", waiting)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(DSN) as c:
            c.execute("select id from auth.users where id=%s for update", (user,))
            future = pool.submit(
                apple.service.capture,
                user_id=user,
                authorization_code="fresh",
                deletion_claim=run["claim"],
            )
            assert entered.wait(10)
            c.execute(
                "update argus_private.account_deletion_runs set claimed_until=%s where id=%s",
                (NOW + timedelta(microseconds=1), run["id"]),
            )
        with pytest.raises(AppleCaptureNotStored):
            future.result(timeout=10)
    assert apple.service.repository.get(user_id=user) == original


def test_denial_preserves_current_and_foreign_household_money(lane, apple, world):
    from tests.test_account_deletion_fk_census_postgres import _primary_keys, _snapshot

    user = world["a"]
    link(user)
    with psycopg.connect(DSN) as c:
        names = [
            row[0]
            for row in c.execute(
                "select quote_ident(schemaname)||'.'||quote_ident(tablename) from pg_tables where schemaname='public' and (tablename like 'financial_%' or tablename like 'household_%')"
            ).fetchall()
        ]
        tables = {name: _primary_keys(c, name) for name in names}
        before = _snapshot(c, tables)
    admin = SqlAuthAdmin()
    service = _service(lane, admin, apple=apple.service)
    with pytest.raises(Exception) as raised:
        service.delete_account(user_id=user)
    assert getattr(raised.value, "code", None) == "apple_reauthorization_required"
    with psycopg.connect(DSN) as c:
        assert _snapshot(c, tables) == before
    assert admin.locked == admin.created == admin.deleted == []
    assert service._analytics.calls == service._revoker.calls == apple.fake.calls == []


def test_live_recovery_replacement_is_preserved_after_old_revoke(
    lane, apple, monkeypatch
):
    user = lane[2][0]
    link(user)
    capture(apple, user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    run = service._claim(user, subject_hash(user))
    revoke = apple.service.revoke_stored

    def replace(row):
        result = revoke(row)
        apple.fake.grant()
        apple.service.capture(
            user_id=user, authorization_code="fresh", deletion_claim=run["claim"]
        )
        return result

    monkeypatch.setattr(apple.service, "revoke_stored", replace)
    assert service._revoke_apple(user, subject_hash(user), run) == "credential_replaced"
    assert apple.service.repository.get(user_id=user) is not None


@pytest.mark.parametrize("outcome", ["invalid", "mismatch", "unavailable"])
def test_failed_fresh_code_on_pending_run_remains_pending(lane, apple, outcome):
    user = lane[2][0]
    link(user)
    pending(user)
    service = _service(lane, SqlAuthAdmin(), apple=apple.service)
    if outcome == "mismatch":
        apple.fake.grant(sub="other")
    else:
        apple.fake.token_responses.append(
            (
                400 if outcome == "invalid" else 503,
                {"error": "invalid_grant" if outcome == "invalid" else "server_error"},
            )
        )
    with pytest.raises(AccountDeletionIncomplete) as raised:
        service.delete_account(user_id=user, apple_authorization_code="fresh")
    assert raised.value.pending == ["apple"]
    assert not service._auth.deleted
