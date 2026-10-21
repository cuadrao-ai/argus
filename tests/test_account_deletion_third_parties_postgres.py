"""Lane 6 on real PostgreSQL: the third-party steps (provider keys, PostHog,
Apple) of the account deletion command, over the same world as
test_account_deletion_postgres.py."""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest
from argus.domain.account_deletion.service import (
    AccountDeletionIncomplete,
    AccountDeletionRejected,
    subject_hash,
)
from argus.domain.apple_sign_in.client import AppleAuthClient
from argus.domain.apple_sign_in.credentials import AppleCredentialService
from argus.domain.apple_sign_in.credentials_postgres import (
    PostgresAppleCredentialRepository,
)
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.models import DocumentDraft
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.owner_scope import PERSONAL
from loguru import logger
from psycopg_pool import ConnectionPool

from tests import apple_sign_in_support as apple_support
from tests.document_sources_support import LOCAL_STORAGE, source_objects, stored_paths
from tests.household.financial_fixtures import DSN, NOW, key
from tests.household.financial_fixtures import lane as lane  # noqa: F401 - fixture
from tests.test_account_deletion_fk_census_postgres import (
    _invite_code_secret,  # noqa: F401 - autouse fixture (#794 invite codes)
)
from tests.test_account_deletion_postgres import (
    FakeRevoker,
    SqlAuthAdmin,
    _age,
    _locked,
    _run,
    _run_id,
    _service,
    world,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def _other_credential(box: SecretBox, user_id: str) -> str:
    """Someone else's Gmail connection, sealed under box by a process holding
    it (so with box's key fingerprint), stored last. Since Priya's B1 it is
    evidence of nothing for anyone else's credential; the tests keep it to
    show that."""
    repo = PostgresConnectionRepository(ConnectionPool(DSN, min_size=0, max_size=1))
    try:
        made = repo.create(
            user_id=user_id,
            source="gmail",
            external_ref="mbx-" + key(),
            label="Gmail",
            now=NOW,
            secret=b"x",
            scope=PERSONAL,
        )
    finally:
        repo._pool.close()  # noqa: SLF001
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "update public.financial_source_connections"
            " set secret_ciphertext=%s, secret_key_fingerprint=%s,"
            "     updated_at=now() + interval '1 day' where id=%s",
            (
                box.seal("r.other", source="gmail", connection_id=made.id),
                box.key_id,
                made.id,
            ),
        )
    return made.id


def _seal(
    user_id: str, source: str, box: SecretBox, *, token: str = "access-live", key_id=...
) -> tuple[str, bytes]:  # noqa: ANN001
    """Seal the person's own Plaid or Gmail credential under box, the way a
    process holding box does: with box's fingerprint (or key_id, to model a
    damaged envelope or a row sealed before the fingerprint existed)."""
    with psycopg.connect(DSN, autocommit=True) as c:
        row = c.execute(
            "select id from public.financial_source_connections"
            " where user_id=%s and source=%s order by created_at limit 1",
            (user_id, source),
        ).fetchone()[0]
        sealed = box.seal(token, source=source, connection_id=str(row))
        c.execute(
            "update public.financial_source_connections"
            " set secret_ciphertext=%s, secret_key_fingerprint=%s where id=%s",
            (sealed, box.key_id if key_id is ... else key_id, row),
        )
    return str(row), sealed


def _revocations(user_id: str) -> list[tuple]:
    with psycopg.connect(DSN) as c:
        return c.execute(
            "select provider, status, secret_ciphertext is not null, last_error"
            " from argus_private.account_deletion_revocations"
            " where subject_hash=%s order by provider",
            (subject_hash(user_id),),
        ).fetchall()


def test_a_wrong_or_missing_key_never_drops_a_live_token(lane, world):  # noqa: F811
    """B1: a credential that does not open is given up only when its key
    fingerprint is the running key's. No key, or a different one, keeps it
    pending with its ciphertext; the key that sealed it records it
    unrecoverable."""
    a = world["a"]
    current = SecretBox(secrets.token_bytes(32))
    _seal(a, "plaid", current)
    admin = SqlAuthAdmin()
    # No key on this process.
    with pytest.raises(AccountDeletionIncomplete) as raised:
        _service(lane, admin, FakeRevoker(unreadable={"plaid"})).delete_account(user_id=a)
    world["placeholders"] += admin.created
    assert raised.value.pending == ["plaid"]
    assert ("plaid", "pending", True, "key_unavailable") in _revocations(a)
    # A different key: the sweep runs with the wrong ARGUS_INGESTION_SECRET_KEY.
    wrong = _service(
        lane,
        SqlAuthAdmin(),
        FakeRevoker(unreadable={"plaid"}),
        box=SecretBox(secrets.token_bytes(32)),
        clock=lambda: NOW + timedelta(hours=1),
    )
    _age(a)
    assert wrong.resume_pending()["pending"] == 1
    assert ("plaid", "pending", True, "key_unproven") in _revocations(a)
    assert _locked(a) == (True, True)
    # The key that sealed it can't open it either: only now is it dead.
    run_id = _run_id(a)
    outcome = _service(
        lane, SqlAuthAdmin(), FakeRevoker(unreadable={"plaid"}), box=current
    ).delete_account(user_id=a)
    assert outcome.status == "done"
    assert _run(run_id)[4]["revocations"]["plaid"] == {"unrecoverable": 1}


def test_the_recording_fake_is_never_done_outside_tests(lane, world, monkeypatch):  # noqa: F811
    """Priya 2: deleted nothing at PostHog, so where the fake is not explicitly
    the adapter the step stays pending; only an operator can close it, with a
    reason kept in the run record."""
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "synthetic-event-token")
    a = world["a"]
    admin = SqlAuthAdmin()
    with pytest.raises(AccountDeletionIncomplete) as raised:
        _service(lane, admin, allow_fake=False).delete_account(user_id=a)
    world["placeholders"] += admin.created
    assert raised.value.pending == ["analytics"]
    run_id = _run_id(a)
    assert _run(run_id)[4]["last_error"] == {
        "analytics": "analytics_adapter_unconfigured"
    }
    with pytest.raises(AccountDeletionIncomplete):
        _service(lane, SqlAuthAdmin(), allow_fake=False).delete_account(user_id=a)
    service = _service(lane, SqlAuthAdmin(), allow_fake=False)
    with pytest.raises(ValueError, match="reason"):
        service.force_complete_step(
            user_id=a, step="analytics", reason=" ", operator="ops"
        )
    forced = {"user_id": a, "step": "analytics", "operator": "ops"}
    forced["reason"] = "PostHog adapter not shipped"
    # Note 2: refused until the step has waited 7 days, even with confirm.
    with pytest.raises(AccountDeletionRejected, match="step_pending_under_7_days"):
        service.force_complete_step(**forced, confirm=True)
    with pytest.raises(AccountDeletionRejected, match="step_not_pending"):
        service.force_complete_step(**{**forced, "step": "plaid"}, confirm=True)
    later = _service(
        lane,
        SqlAuthAdmin(),
        allow_fake=False,
        clock=lambda: NOW + timedelta(days=7, minutes=1),
    )
    # Without confirm it only reports.
    assert later.force_complete_step(**forced) == {
        "step": "analytics",
        "pending_days": 7,
        "last_error": "analytics_adapter_unconfigured",
        "dry_run": True,
        "forced": False,
    }
    assert _run(run_id)[4]["analytics"] == "pending"
    assert "forced" not in _run(run_id)[4]
    report = later.force_complete_step(**forced, confirm=True)
    assert report["forced"] is True
    assert report["revoke_attempt"] == "analytics_adapter_unconfigured"
    assert later.delete_account(user_id=a).status == "done"
    steps = _run(run_id)[4]
    assert steps["analytics"] == "operator_forced"
    assert steps["forced"]["analytics"]["reason"] == "PostHog adapter not shipped"


class _Apple:
    """#793's real AppleCredentialService over the real table, with a scripted
    Apple endpoint."""

    def __init__(self, revoke_responses):  # noqa: ANN001
        key = apple_support.generated_key()
        self.fake = apple_support.FakeApple(
            public_key=key.public_key(), revoke_responses=list(revoke_responses)
        )
        self.box = SecretBox(secrets.token_bytes(32))
        self.pool = ConnectionPool(DSN, min_size=0, max_size=2, open=True)
        self.service = AppleCredentialService(
            PostgresAppleCredentialRepository(self.pool),
            box=self.box,
            client=AppleAuthClient(
                apple_support.config(key),
                transport=self.fake.transport(),
                sleep=lambda _s: None,
            ),
            clock=lambda: NOW,
        )

    def store(
        self,
        user_id: str,
        *,
        box: SecretBox | None = None,
        key_id=...,
        legacy: bool = False,
    ) -> None:  # noqa: ANN001
        """As capture stores it: sealed under box with box's fingerprint, or
        key_id (None: stored before the fingerprint existed)."""
        if not legacy:
            with psycopg.connect(DSN) as c:
                c.execute(
                    "insert into auth.identities (id,user_id,provider,provider_id,identity_data) "
                    "values (%s,%s,'apple',%s,%s::jsonb)",
                    (
                        str(uuid4()),
                        user_id,
                        apple_support.SUBJECT,
                        json.dumps({"sub": apple_support.SUBJECT}),
                    ),
                )
            self.fake.grant()
            self.service.capture(user_id=user_id, authorization_code="fresh")
            self.fake.calls.clear()
            return
        sealed = (box or self.box).seal(
            "r.apple-refresh-0", source="apple_sign_in", connection_id=user_id
        )
        self.service.repository.upsert(
            user_id=user_id,
            client_id=apple_support.BUNDLE_ID,
            secret_ciphertext=sealed,
            now=NOW,
            key_id=(box or self.box).key_id if key_id is ... else key_id,
        )

    def close(self) -> None:
        self.service.close()
        self.pool.close()


def _legacy_apple_run(user_id: str) -> None:
    from argus.observability.product_events import actor_hash_for_user

    with psycopg.connect(DSN) as c:
        c.execute(
            "insert into argus_private.account_deletion_runs "
            "(user_id,subject_hash,analytics_distinct_id,status) values (%s,%s,%s,'started')",
            (user_id, subject_hash(user_id), actor_hash_for_user(user_id)),
        )


def _apple_state(
    user_id: str, run_id: str | None = None
) -> tuple[bool, bool, str | None, str | None]:
    with psycopg.connect(DSN) as conn:
        stored = conn.execute(
            "select 1 from public.apple_sign_in_credentials where user_id=%s", (user_id,)
        ).fetchone()
        user = conn.execute("select 1 from auth.users where id=%s", (user_id,)).fetchone()
        run = conn.execute(
            "select status, steps->>'apple_revoke' from argus_private.account_deletion_runs"
            " where subject_hash=%s or id=%s",
            (subject_hash(user_id), run_id),
        ).fetchone()
    return bool(stored), bool(user), run[0], run[1]


@pytest.mark.parametrize(
    ("answer", "step"),
    [((200, None), "revoked"), ((400, {"error": "invalid_grant"}), "already_revoked")],
)
def test_apple_is_revoked_before_the_account_delete(lane, world, answer, step):  # noqa: F811
    a = world["a"]
    apple = _Apple([answer])
    try:
        apple.store(a)
        admin = SqlAuthAdmin()
        outcome = _service(lane, admin, apple=apple.service).delete_account(user_id=a)
        world["placeholders"] += admin.created
    finally:
        apple.close()
    assert outcome.status == "done"
    assert [path for path, _ in apple.fake.calls] == ["/auth/revoke"]
    stored, user, status, recorded = _apple_state(a, outcome.run_id)
    assert (stored, user, status, recorded) == (False, False, "done", step)
    already = _run(outcome.run_id)[4].get("already_revoked")
    assert already == ({"apple": 1} if step == "already_revoked" else None)


def test_a_transient_apple_failure_holds_the_account_delete(lane, world):  # noqa: F811
    a = world["a"]
    apple = _Apple([(400, {"error": "invalid_request"})])
    try:
        apple.store(a)
        admin = SqlAuthAdmin()
        with pytest.raises(AccountDeletionIncomplete):
            _service(lane, admin, apple=apple.service).delete_account(user_id=a)
        world["placeholders"] += admin.created
        run_id = _run_id(a)
        # The data is gone, the account waits for Apple, the token is kept.
        assert _apple_state(a) == (True, True, "data_deleted", "pending")
        assert admin.deleted == []
        # No Apple service on this process: still pending, never dropped.
        with pytest.raises(AccountDeletionIncomplete):
            _service(lane, SqlAuthAdmin()).delete_account(user_id=a)
        assert _apple_state(a)[:3] == (True, True, "data_deleted")
        assert _run(run_id)[4]["last_error"] == {"apple": "apple_unconfigured"}
        # The retry gets Apple's 200 and finishes.
        retry = SqlAuthAdmin()
        assert (
            _service(lane, retry, apple=apple.service).delete_account(user_id=a).status
            == "done"
        )
        assert retry.creates == 0
    finally:
        apple.close()
    assert _apple_state(a, run_id) == (False, False, "done", "revoked")


def test_an_apple_step_pending_a_week_needs_an_operator(lane, world):  # noqa: F811
    """Priya (#802 eval): Apple invalid_request (the person revoked the app,
    TN3107) never turns into a 200. After 7 days the run alerts; only an
    operator force-completes it, and the reason stays in the run record."""
    from loguru import logger

    a = world["a"]
    alerts: list[dict] = []
    sink = logger.add(lambda m: alerts.append(m.record["extra"]), level="ERROR")
    apple = _Apple([(400, {"error": "invalid_request"})] * 3)
    try:
        apple.store(a)
        admin = SqlAuthAdmin()
        with pytest.raises(AccountDeletionIncomplete):
            _service(lane, admin, apple=apple.service).delete_account(user_id=a)
        world["placeholders"] += admin.created
        run_id = _run_id(a)
        assert not [
            x for x in alerts if x.get("metric") == "account_deletion.needs_operator"
        ]
        later = NOW + timedelta(days=7, minutes=1)
        with pytest.raises(AccountDeletionIncomplete):
            _service(
                lane, SqlAuthAdmin(), apple=apple.service, clock=lambda: later
            ).delete_account(user_id=a)
        needs = [
            x for x in alerts if x.get("metric") == "account_deletion.needs_operator"
        ]
        assert needs and needs[0]["step"] == "apple" and needs[0]["pending_days"] == 7
        service = _service(lane, SqlAuthAdmin(), apple=apple.service, clock=lambda: later)
        with pytest.raises(ValueError):
            service.force_complete_step(
                user_id=a, step="apple", reason="", operator="ops"
            )
        with pytest.raises(ValueError):
            service.force_complete_step(
                user_id=a, step="email", reason="x", operator="ops"
            )
        report = service.force_complete_step(
            user_id=a,
            step="apple",
            reason="Person removed the app in Apple ID settings (TN3107)",
            operator="ops",
            confirm=True,
        )
        # Note 2: one more revoke first, recorded, and only then dropped.
        assert [p for p, _ in apple.fake.calls] == ["/auth/revoke"] * 3
        assert report["revoke_attempt"] == "invalid_request"
        assert report["forced"] is True
        assert service.delete_account(user_id=a).status == "done"
    finally:
        logger.remove(sink)
        apple.close()
    steps = _run(run_id)[4]
    assert steps["apple_revoke"] == "operator_forced"
    assert steps["forced"]["apple"]["reason"].startswith("Person removed the app")
    assert _apple_state(a, run_id)[:3] == (False, False, "done")


def test_an_unreadable_apple_token_is_discarded_only_under_its_own_key(lane, world):  # noqa: F811
    """A damaged Apple token this key sealed: a process on another key keeps
    it (key_unproven); the key whose fingerprint it carries discards it via
    #802's discard_unreadable. Fails if upsert drops the fingerprint."""
    a = world["a"]
    apple = _Apple([])
    try:
        apple.store(
            a,
            box=SecretBox(secrets.token_bytes(32)),
            key_id=apple.box.key_id,
            legacy=True,
        )
        _legacy_apple_run(a)
        admin = SqlAuthAdmin()
        with pytest.raises(AccountDeletionIncomplete) as raised:
            _service(
                lane, admin, apple=apple.service, box=SecretBox(secrets.token_bytes(32))
            ).delete_account(user_id=a)
        assert raised.value.pending == ["apple"]
        world["placeholders"] += admin.created
        assert apple.fake.calls == []
        run_id = _run_id(a)
        assert _apple_state(a) == (True, True, "data_deleted", "pending")
        assert _run(run_id)[4]["last_error"] == {"apple": "key_unproven"}
        outcome = _service(
            lane, SqlAuthAdmin(), apple=apple.service, box=apple.box
        ).delete_account(user_id=a)
        assert outcome.status == "done"
        assert _apple_state(a, run_id) == (False, False, "done", "unrecoverable")
    finally:
        apple.close()


class _StorageDown:
    bucket = "financial-document-sources"

    def delete(self, prefix: str) -> None:
        raise ConnectionError("storage unavailable")


@pytest.mark.skipif(not LOCAL_STORAGE, reason="Local Supabase Storage required")
def test_document_sources_are_erased_before_the_account_delete(lane, world):  # noqa: F811
    """#778: every object under the person's prefix goes, a referenced capture
    and an unreferenced one alike; anyone else's stays. Storage down keeps the
    run pending and the account locked, like any third party."""
    from hashlib import sha256

    a, b = world["a"], world["b"]
    digest = sha256(b"%PDF-fixture").hexdigest()
    objects = source_objects()
    orphan, theirs = f"{a}/{uuid4()}/{digest}", f"{b}/{uuid4()}/{digest}"
    for path in (orphan, theirs):
        objects.put(path, b"%PDF-fixture", "application/pdf")
    with ConnectionPool(DSN, min_size=0, max_size=2) as pool:
        statement = PostgresConnectionRepository(pool).create(
            user_id=a,
            source="statement",
            external_ref=key(),
            label=None,
            now=NOW,
            scope=PERSONAL,
        )
        draft = DocumentDraft(
            connection_id=statement.id,
            filename="statement.pdf",
            media_type="application/pdf",
            sha256=digest,
            size_bytes=12,
            created_at=NOW,
            updated_at=NOW,
        )
        assert PostgresDocumentStore(pool, objects).capture(
            user_id=a, draft=draft, content=b"%PDF-fixture"
        )
    with psycopg.connect(DSN) as c:
        assert stored_paths(c, f"{a}/") == [orphan]
        assert stored_paths(c, f"sealed/{a}/") == [f"sealed/{a}/{digest}"]
        assert stored_paths(c, f"rebuilt/{a}/") == []
    try:
        admin = SqlAuthAdmin()
        with pytest.raises(AccountDeletionIncomplete) as raised:
            _service(lane, admin, source_objects=_StorageDown()).delete_account(user_id=a)
        world["placeholders"] += admin.created
        assert raised.value.pending == ["storage"]
        assert _locked(a) == (True, True)
        assert admin.deleted == []
        run_id = _run_id(a)
        assert _run(run_id)[4]["last_error"] == {"storage": "storage_delete_failed"}
        # A week later: our own Storage gets its own alert, and no operator
        # can force the step closed.
        lines: list[str] = []
        metrics: list[object] = []
        sink = logger.add(
            lambda message: (
                lines.append(str(message)),
                metrics.append(message.record["extra"].get("metric")),
            ),
            level="ERROR",
        )
        week = _service(
            lane,
            SqlAuthAdmin(),
            source_objects=_StorageDown(),
            clock=lambda: NOW + timedelta(days=7, minutes=1),
        )
        try:
            with pytest.raises(AccountDeletionIncomplete):
                week.delete_account(user_id=a)
        finally:
            logger.remove(sink)
        assert any("fix Storage" in line for line in lines)
        assert "account_deletion.storage_failing" in metrics
        assert "account_deletion.needs_operator" not in metrics
        assert not any("needs an operator" in line for line in lines)
        with pytest.raises(ValueError, match="step must be one of"):
            week.force_complete_step(
                user_id=a, step="storage", reason="down", operator="ops", confirm=True
            )

        done = _service(lane, SqlAuthAdmin(), source_objects=objects).delete_account(
            user_id=a
        )
        assert done.status == "done"
        assert _run(run_id)[4]["storage"] == "deleted"
        with psycopg.connect(DSN) as c:
            for prefix in (f"{a}/", f"sealed/{a}/", f"rebuilt/{a}/"):
                assert stored_paths(c, prefix) == []
            assert stored_paths(c, f"{b}/") == [theirs]
    finally:
        objects.delete(f"{a}/")
        objects.delete(f"{b}/")


class _LateUpload:
    """Storage that sees an upload, authenticated before the lock, land
    right after the run's first erase."""

    bucket = "financial-document-sources"

    def __init__(self, objects, late: str) -> None:  # noqa: ANN001
        self._objects, self._late, self.erases = objects, late, 0

    def delete(self, prefix: str) -> None:
        self._objects.delete(prefix)
        self.erases += 1
        if self.erases == 1:
            self._objects.put(self._late, b"%PDF-late", "application/pdf")


@pytest.mark.skipif(not LOCAL_STORAGE, reason="Local Supabase Storage required")
def test_a_source_written_after_the_first_erase_is_gone_before_the_auth_delete(
    lane,  # noqa: ANN001, F811
    world,  # noqa: ANN001, F811
) -> None:
    a = world["a"]
    objects = source_objects()
    late = _LateUpload(objects, f"{a}/{uuid4()}/{'d' * 64}")
    try:
        admin = SqlAuthAdmin()
        done = _service(lane, admin, source_objects=late).delete_account(user_id=a)
        world["placeholders"] += admin.created
        assert done.status == "done"
        assert late.erases == 2
        with psycopg.connect(DSN) as c:
            assert stored_paths(c, f"{a}/") == []
    finally:
        objects.delete(f"{a}/")
