"""Lane 6 on real PostgreSQL, Priya's B1: which key sealed a credential.

During a rolling key rotation (Render overlap) or from an operator on a stale
environment, processes on the old key and the new key seal credentials side by
side. A credential that does not open under one of them may be live for the
other, so account deletion gives it up only when its stored key fingerprint is
the running key's. Nothing about anyone else's credentials counts. Covers
Plaid, Gmail (through the real IngestionHub and GmailAdapter) and Apple, plus
note 1: an already-gone grant records ``already_revoked``.
"""

from __future__ import annotations

import secrets

import psycopg
import pytest
from argus.domain.account_deletion.service import AccountDeletionIncomplete
from argus.domain.ingestion.gmail.adapter import GmailAdapter
from argus.domain.ingestion.gmail.client import GmailError
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.plaid.adapter import PlaidAdapter
from argus.domain.ingestion.plaid.client import PlaidError
from argus.domain.ingestion.secrets import SecretBox, SecretUnreadable

from tests.household.financial_fixtures import DSN, NOW
from tests.household.financial_fixtures import lane as lane  # noqa: F401 - fixture
from tests.test_account_deletion_fk_census_postgres import (
    _invite_code_secret,  # noqa: F401 - autouse fixture (#794 invite codes)
)
from tests.test_account_deletion_postgres import (
    FakeRevoker,
    SqlAuthAdmin,
    _locked,
    _run,
    _run_id,
    _service,
    world,  # noqa: F401 - fixture
)
from tests.test_account_deletion_third_parties_postgres import (
    _Apple,
    _apple_state,
    _other_credential,
    _revocations,
    _seal,
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def _box() -> SecretBox:
    return SecretBox(secrets.token_bytes(32))


def _forget(made: list[str]) -> None:
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "delete from public.financial_source_connections where id = any(%s::uuid[])",
            (made,),
        )


class _Google:
    """Google's revoke endpoint: 200, or a 400 with the given error."""

    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.revoked: list[str] = []

    def revoke(self, token: str) -> None:
        self.revoked.append(token)
        if self.error:
            raise GmailError(status=400, reason=self.error)


class _Plaid:
    """Plaid's /item/remove: success, or the given error code."""

    def __init__(self, code: str | None = None) -> None:
        self.code = code
        self.removed: list[str] = []

    def item_remove(self, token: str) -> None:
        self.removed.append(token)
        if self.code:
            raise PlaidError(error_type="ITEM_ERROR", error_code=self.code, status=400)


def _hub(lane, box: SecretBox, google: _Google, plaid: _Plaid) -> IngestionHub:  # noqa: ANN001, F811
    from argus.domain.ingestion.connections_postgres import (
        PostgresConnectionRepository,
    )

    hub = IngestionHub(
        PostgresConnectionRepository(lane[0]._repository._pool),  # noqa: SLF001
        box=box,
        sink=None,
        clock=lambda: NOW,
    )
    hub.register(GmailAdapter(google, senders=None))  # type: ignore[arg-type]
    hub.register(PlaidAdapter(plaid, sleep=lambda _s: None))  # type: ignore[arg-type]
    return hub


@pytest.mark.parametrize("fingerprint", ["new_key", "none_pre_migration"])
def test_mixed_writers_during_a_rolling_rotation_keep_the_live_token(
    lane,  # noqa: F811
    world,  # noqa: F811
    fingerprint,  # noqa: ANN001
):
    """Priya's probe, ported: a K2 process seals A's Plaid token; afterwards a
    K1 process (not yet replaced) seals someone else's newer link; then the K1
    process runs A's deletion. On 1e1375d0 the newest-other-seal check let K1
    give the live token up as unrecoverable. Now: held, ciphertext kept, and
    the K2 process revokes it."""
    a, b = world["a"], world["b"]
    k1, k2 = _box(), _box()
    made = [_other_credential(k1, b)]
    try:
        plaid, sealed = _seal(
            a, "plaid", k2, key_id=k2.key_id if fingerprint == "new_key" else None
        )
        with pytest.raises(SecretUnreadable):
            k1.open(sealed, source="plaid", connection_id=plaid)
        made.append(_other_credential(k1, b))  # K1 seals a link after A's token
        admin = SqlAuthAdmin()
        with pytest.raises(AccountDeletionIncomplete) as raised:
            _service(
                lane, admin, FakeRevoker(unreadable={"plaid"}), box=k1
            ).delete_account(user_id=a)
        world["placeholders"] += admin.created
        assert raised.value.pending == ["plaid"]
        assert ("plaid", "pending", True, "key_unproven") in _revocations(a)
        assert _locked(a) == (True, True)
        with psycopg.connect(DSN) as c:
            kept = c.execute(
                "select secret_ciphertext, secret_key_fingerprint"
                " from argus_private.account_deletion_revocations where source_ref=%s",
                (plaid,),
            ).fetchone()
        assert bytes(kept[0]) == sealed
        assert kept[1] == (k2.key_id if fingerprint == "new_key" else None)
        revoker = FakeRevoker()
        run_id = _run_id(a)
        outcome = _service(lane, SqlAuthAdmin(), revoker, box=k2).delete_account(
            user_id=a
        )
        assert outcome.status == "done"
        assert ("plaid", plaid, sealed) in revoker.calls
        assert _run(run_id)[4]["revocations"]["plaid"] == {"revoked": 1}
    finally:
        _forget(made)


def test_a_gmail_token_from_another_key_waits_for_that_key(lane, world):  # noqa: F811
    """Gmail through the real hub and adapter: A's Gmail token sealed by a K2
    process, the deletion run by a K1 process. Held (key_unproven) with the
    ciphertext kept; Google is never called with anything; a K2 process
    revokes the live token at Google."""
    a = world["a"]
    k1, k2 = _box(), _box()
    _seal(a, "plaid", k1, token="access-k1")
    gmail, sealed = _seal(a, "gmail", k2, token="r.gmail-live")
    google, plaid = _Google(), _Plaid()
    admin = SqlAuthAdmin()
    with pytest.raises(AccountDeletionIncomplete) as raised:
        _service(lane, admin, _hub(lane, k1, google, plaid), box=k1).delete_account(
            user_id=a
        )
    world["placeholders"] += admin.created
    assert raised.value.pending == ["gmail"]
    assert google.revoked == [] and plaid.removed == ["access-k1"]
    assert ("gmail", "pending", True, "key_unproven") in _revocations(a)
    run_id = _run_id(a)
    outcome = _service(
        lane, SqlAuthAdmin(), _hub(lane, k2, google, plaid), box=k2
    ).delete_account(user_id=a)
    assert outcome.status == "done"
    assert google.revoked == ["r.gmail-live"]
    assert _run(run_id)[4]["revocations"] == {
        "gmail": {"revoked": 1},
        "plaid": {"revoked": 1},
    }


def test_a_damaged_gmail_token_under_its_own_key_is_unrecoverable(lane, world):  # noqa: F811
    """The same key that sealed it (its fingerprint) can't open it: dead, so
    recorded unrecoverable and the run finishes."""
    a = world["a"]
    key = _box()
    _seal(a, "plaid", key)
    _seal(a, "gmail", _box(), key_id=key.key_id)  # damaged: this key's fingerprint
    google = _Google()
    admin = SqlAuthAdmin()
    outcome = _service(
        lane, admin, _hub(lane, key, google, _Plaid()), box=key
    ).delete_account(user_id=a)
    world["placeholders"] += admin.created
    assert outcome.status == "done"
    assert google.revoked == []
    assert _run(outcome.run_id)[4]["revocations"]["gmail"] == {"unrecoverable": 1}


@pytest.mark.parametrize(
    ("provider", "answer"),
    [
        ("plaid", "ITEM_NOT_FOUND"),
        ("plaid", "INVALID_ACCESS_TOKEN"),
        ("gmail", "invalid_grant"),
        ("gmail", "invalid_token"),
    ],
)
def test_an_already_gone_grant_records_already_revoked(lane, world, provider, answer):  # noqa: F811
    """Note 1: Plaid ITEM_NOT_FOUND / INVALID_ACCESS_TOKEN and Google 400
    invalid_grant / invalid_token are recorded already_revoked, counted for
    the spike alert, and the run finishes."""
    a = world["a"]
    key = _box()
    _seal(a, "plaid", key)
    _seal(a, "gmail", key)
    google = _Google(answer if provider == "gmail" else None)
    plaid = _Plaid(answer if provider == "plaid" else None)
    admin = SqlAuthAdmin()
    outcome = _service(
        lane, admin, _hub(lane, key, google, plaid), box=key
    ).delete_account(user_id=a)
    world["placeholders"] += admin.created
    assert outcome.status == "done"
    steps = _run(outcome.run_id)[4]
    assert steps["revocations"][provider] == {"already_revoked": 1}
    assert steps["already_revoked"] == {provider: 1}
    other = "gmail" if provider == "plaid" else "plaid"
    assert steps["revocations"][other] == {"revoked": 1}


@pytest.mark.parametrize("fingerprint", ["new_key", "none_pre_migration"])
def test_an_apple_token_from_another_key_is_never_discarded(
    lane,  # noqa: F811
    world,  # noqa: F811
    monkeypatch,  # noqa: ANN001
    fingerprint,  # noqa: ANN001
):
    """Apple rotation: A signed in with Apple on a K2 process; the deletion
    runs on a K1 process, after a K1 process sealed someone else's newer
    link. The service must not even ask Apple's discard_unreadable; the token
    is kept and a K2 process revokes it at Apple."""
    a, b = world["a"], world["b"]
    k1, k2 = _box(), _box()
    apple = _Apple([])
    apple.service._box = k1  # noqa: SLF001 - the Apple service of a K1 process
    discards: list[str] = []
    real = apple.service.discard_unreadable

    def spy(*, user_id: str):  # noqa: ANN202
        discards.append(user_id)
        return real(user_id=user_id)

    monkeypatch.setattr(apple.service, "discard_unreadable", spy)
    made = []
    try:
        apple.store(
            a, box=k2, key_id=k2.key_id if fingerprint == "new_key" else None, legacy=True
        )
        from tests.test_account_deletion_third_parties_postgres import _legacy_apple_run

        _legacy_apple_run(a)
        made.append(_other_credential(k1, b))
        admin = SqlAuthAdmin()
        with pytest.raises(AccountDeletionIncomplete) as raised:
            _service(lane, admin, apple=apple.service, box=k1).delete_account(user_id=a)
        world["placeholders"] += admin.created
        assert raised.value.pending == ["apple"]
        assert discards == [] and apple.fake.calls == []
        run_id = _run_id(a)
        assert _apple_state(a) == (True, True, "data_deleted", "pending")
        assert _run(run_id)[4]["last_error"] == {"apple": "key_unproven"}
        # A K2 process revokes the kept live token and finishes.
        apple.service._box = k2  # noqa: SLF001
        apple.fake.revoke_responses.append((200, None))
        outcome = _service(
            lane, SqlAuthAdmin(), apple=apple.service, box=k2
        ).delete_account(user_id=a)
        assert outcome.status == "done"
        assert [p for p, _ in apple.fake.calls] == ["/auth/revoke"]
        assert _apple_state(a, run_id) == (False, False, "done", "revoked")
    finally:
        _forget(made)
        apple.close()


@pytest.mark.parametrize(("others", "alerts"), [(3, False), (4, True)])
def test_the_already_revoked_spike_alerts_at_five_runs_in_24_hours(
    lane,  # noqa: F811
    world,  # noqa: F811
    others,  # noqa: ANN001
    alerts,  # noqa: ANN001
):
    """Note 4: the runbook says 5 or more runs updated in the last 24 hours
    that saw an already-gone grant, any provider. Four (three others plus
    this one) stay quiet; five alert. A run older than 24 hours never counts."""
    from datetime import timedelta

    from argus.domain.account_deletion.service import (
        ALREADY_REVOKED_SPIKE,
        ALREADY_REVOKED_WINDOW,
    )
    from loguru import logger

    assert (ALREADY_REVOKED_SPIKE, ALREADY_REVOKED_WINDOW) == (5, timedelta(hours=24))
    a = world["a"]
    key = _box()
    _seal(a, "plaid", key)
    _seal(a, "gmail", key)
    seen = '{"already_revoked": {"plaid": 1}}'
    with psycopg.connect(DSN, autocommit=True) as c:
        # Earlier tests' finished runs are moved out of the window meanwhile.
        moved = [
            r[0]
            for r in c.execute(
                "update argus_private.account_deletion_runs"
                " set updated_at = updated_at - interval '3 days'"
                " where steps ? 'already_revoked' and updated_at >= %s returning id",
                (NOW - ALREADY_REVOKED_WINDOW,),
            ).fetchall()
        ]
        made = [
            r[0]
            for r in c.execute(
                "insert into argus_private.account_deletion_runs"
                " (status, steps, updated_at, completed_at)"
                " select 'done', %s::jsonb, %s - (g * interval '1 hour'), %s"
                " from generate_series(0, %s) g returning id",
                (seen, NOW, NOW, others),
            ).fetchall()
        ]
        # The last one is 2 days old: outside the window.
        c.execute(
            "update argus_private.account_deletion_runs"
            " set updated_at = %s - interval '2 days' where id = %s",
            (NOW, made[-1]),
        )
    records: list[dict] = []
    sink = logger.add(lambda m: records.append(m.record["extra"]), level="INFO")
    try:
        admin = SqlAuthAdmin()
        outcome = _service(
            lane, admin, _hub(lane, key, _Google(), _Plaid("ITEM_NOT_FOUND")), box=key
        ).delete_account(user_id=a)
        world["placeholders"] += admin.created
    finally:
        logger.remove(sink)
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute(
                "delete from argus_private.account_deletion_runs where id = any(%s)",
                (made,),
            )
            c.execute(
                "update argus_private.account_deletion_runs"
                " set updated_at = updated_at + interval '3 days' where id = any(%s)",
                (moved,),
            )
    assert outcome.status == "done"
    spikes = [
        r for r in records if r.get("metric") == "account_deletion.already_revoked_spike"
    ]
    assert bool(spikes) is alerts
    if alerts:
        assert spikes[0]["runs"] == 5 and spikes[0]["window_hours"] == 24
