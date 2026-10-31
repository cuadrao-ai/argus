"""#789: keyed code digests, code entropy, fail-closed secret, lookup limits.

No database here, so these run in backend-checks. The real-Postgres side
(private digest table, rotation, rehash, client exposure) is in
tests/test_invite_code_security_postgres.py.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from argus.api import households as surface
from argus.api import invite_limits
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers.ops import _invite_code_check
from argus.api.shortcuts_limits import WeightedWindow
from argus.domain.household.errors import InvitationNotFound, InviteCodesUnavailable
from argus.domain.household.invite_codes import (
    CODE_ALPHABET,
    CODE_LENGTH,
    CodeHasher,
    InviteSettings,
    format_code,
    new_code,
    normalize_code,
)
from argus.domain.household.repository import (
    FinancialAccountLookup,
    InMemoryHouseholdRepository,
)
from argus.domain.recording.repository import InMemoryFinancialAccountRepository
from fastapi import HTTPException
from fastapi.testclient import TestClient

from tests.household.conftest import ALICE, TEST_CODE_SECRET

SECRET_A = "test-secret-a-7Qm2Vx9Lp4Rt8Wz3Ny6Kb1Hd5"
SECRET_B = "test-secret-b-3Fj8Ns2Gc7Yq5Ue9Ta4Lw6Mx1"


# -- Digests ------------------------------------------------------------------


def test_digest_is_keyed_versioned_and_names_its_key():
    a = CodeHasher.from_secrets(SECRET_A)
    b = CodeHasher.from_secrets(SECRET_B)
    code = new_code()
    digest = a.digest(code)
    version, key_id, mac = digest.split(".")
    assert version == "v2" and len(key_id) == 8 and len(mac) == 64
    assert key_id == a.current.key_id and SECRET_A not in digest
    # The same code under another secret is a different digest: a stolen table
    # cannot be matched without the secret, and one secret cannot find another's.
    assert b.digest(code) != digest
    assert a.digest(code) == digest  # deterministic, so it can be looked up
    import hmac

    expected = hmac.new(
        SECRET_A.encode(), f"argus-invite-code:v2:{code}".encode(), hashlib.sha256
    ).hexdigest()
    assert mac == expected  # HMAC-SHA-256 under the secret, nothing else
    assert b.digest(code).split(".")[2] != mac

    assert (
        hashlib.sha256(f"argus-invite-code:v1:{code}".encode()).hexdigest() not in digest
    )
    assert "secret" not in repr(a.current) and SECRET_A not in repr(a)


def test_rotation_looks_up_under_current_then_previous():
    rotated = CodeHasher.from_secrets(SECRET_B, SECRET_A)
    code = new_code()
    assert rotated.candidates(code) == [
        CodeHasher.from_secrets(SECRET_B).digest(code),
        CodeHasher.from_secrets(SECRET_A).digest(code),
    ]
    assert rotated.digest(code) == rotated.candidates(code)[0]
    same = CodeHasher.from_secrets(SECRET_A, SECRET_A)
    assert same.previous is None and len(same.candidates(code)) == 1


@pytest.mark.parametrize("secret", [None, "", "   ", "short-secret"])
def test_missing_or_short_secret_fails_closed(secret, monkeypatch):
    with pytest.raises(InviteCodesUnavailable):
        CodeHasher.from_secrets(secret)
    if secret is None:
        monkeypatch.delenv("CUADRAO_INVITE_CODE_SECRET", raising=False)
    else:
        monkeypatch.setenv("CUADRAO_INVITE_CODE_SECRET", secret)
    with pytest.raises(InviteCodesUnavailable):
        CodeHasher.from_env()
    # No unkeyed fallback: the repository refuses to make or look up a code.
    repo = InMemoryHouseholdRepository(
        FinancialAccountLookup(InMemoryFinancialAccountRepository())
    )
    household = repo.create_household(user_id="u1", name="Casa")
    with pytest.raises(InviteCodesUnavailable):
        repo.create_invitation(user_id="u1", household_id=household.id)
    with pytest.raises(InviteCodesUnavailable):
        repo.preview_invitation(user_id="u2", code="ABCD-EFGH-JKMN")


def test_skewed_secret_fails_the_entropy_floor():
    """Ten distinct characters cannot substitute for the 96-bit estimate."""
    secret = "a" * 23 + "bcdefghij"
    assert len(secret) == 32 and len(set(secret)) == 10
    with pytest.raises(InviteCodesUnavailable, match="placeholder"):
        CodeHasher.from_secrets(secret)
    with pytest.raises(InviteCodesUnavailable, match="placeholder"):
        CodeHasher.from_secrets(SECRET_A, secret)


def test_short_previous_secret_also_fails_closed():
    with pytest.raises(InviteCodesUnavailable):
        CodeHasher.from_secrets(SECRET_A, "too-short")


@pytest.mark.parametrize(
    "placeholder",
    ["a" * 32, "a" * 64, "ab" * 24, "changeme" * 6, "secret12" * 5],
)
def test_placeholder_secrets_are_refused(placeholder, monkeypatch):
    """Priya: a long but trivial secret must not pass the length check alone."""
    assert len(placeholder) >= 32
    with pytest.raises(InviteCodesUnavailable, match="placeholder"):
        CodeHasher.from_secrets(placeholder)
    with pytest.raises(InviteCodesUnavailable, match="placeholder"):
        CodeHasher.from_secrets(SECRET_A, placeholder)
    monkeypatch.setenv("CUADRAO_INVITE_CODE_SECRET", placeholder)
    from argus.domain.household.invite_codes import code_secret_problem

    assert "placeholder" in (code_secret_problem() or "")


@pytest.mark.parametrize(
    "generated",
    [
        "3q2+7wB9xY0kLmN4pQrStUvWxYz1A2b3C4d5E6f7G8h9I0jK1lM2nO3pQ4rS5tU6",  # base64
        "9f86d081884c7d659a2feaa0c55ad015",  # 32 hex characters
        TEST_CODE_SECRET,
    ],
)
def test_generated_secrets_pass_the_floor(generated):
    assert CodeHasher.from_secrets(generated).current.key_id


# -- Entropy ------------------------------------------------------------------


def test_code_has_sixty_bits_in_a_typeable_shape():
    assert len(CODE_ALPHABET) == 32 and CODE_LENGTH == 12
    assert math.log2(len(CODE_ALPHABET) ** CODE_LENGTH) == 60
    code = new_code()
    shown = format_code(code)
    assert len(shown) == 14 and shown[4] == shown[9] == "-"
    assert normalize_code(shown.lower().replace("-", " ")) == code
    assert normalize_code("ABCD-EFGH") is None  # #788's 8-character shape


# -- Fail closed at startup and readiness -------------------------------------


@pytest.fixture
def secretless_client(surface_env, gateway, monkeypatch) -> Iterator[TestClient]:  # noqa: ANN001
    monkeypatch.delenv("CUADRAO_INVITE_CODE_SECRET", raising=False)
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        yield test_client


def test_households_stay_off_without_the_secret(secretless_client):
    assert surface.households_service() is None
    response = secretless_client.get(
        "/api/v1/households", headers={"Authorization": f"Bearer {ALICE}"}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "households_unavailable"


def test_readiness_fails_when_a_code_flag_is_on_without_the_secret(monkeypatch):
    for flag in (
        "CUADRAO_HOUSEHOLDS_ENABLED",
        "CUADRAO_BETA_INVITES_ENABLED",
        "CUADRAO_BETA_INVITE_GATE_ENABLED",
    ):
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.delenv("CUADRAO_INVITE_CODE_SECRET", raising=False)
    assert _invite_code_check() is None  # every code flag off: no extra check
    monkeypatch.setenv("CUADRAO_BETA_INVITE_GATE_ENABLED", "true")
    check = _invite_code_check()
    assert check["status"] == "degraded"
    assert check["reason"] == "invite_code_secret_unusable"
    monkeypatch.setenv("CUADRAO_INVITE_CODE_SECRET", TEST_CODE_SECRET)
    assert _invite_code_check()["status"] == "ready"


def test_beta_invites_start_closed_without_the_secret(monkeypatch):
    """Priya: start_invites (beta, group link, gate) must fail closed too."""
    monkeypatch.setenv("CUADRAO_BETA_INVITES_ENABLED", "true")
    monkeypatch.setattr(api_state, "PERSISTENCE_MODE", "supabase")
    monkeypatch.setattr(api_state, "DATABASE_URL", "postgresql://unused/argus")
    pools: list[object] = []

    def _pool(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        pools.append(args)
        return MagicMock()

    monkeypatch.setattr("psycopg_pool.ConnectionPool", _pool)
    application = MagicMock()
    try:
        monkeypatch.delenv("CUADRAO_INVITE_CODE_SECRET", raising=False)
        surface.start_invites(application)
        assert surface.invites_store() is None and pools == []

        monkeypatch.setenv("CUADRAO_INVITE_CODE_SECRET", "a" * 40)  # placeholder
        surface.start_invites(application)
        assert surface.invites_store() is None and pools == []

        # Control: with a usable secret the same start does open the store.
        monkeypatch.setenv("CUADRAO_INVITE_CODE_SECRET", TEST_CODE_SECRET)
        surface.start_invites(application)
        assert surface.invites_store() is not None and len(pools) == 1
    finally:
        surface.configure_invites_store(None)


def test_readiness_runs_the_invite_code_check(monkeypatch):
    """Priya: prove /internal/readiness itself calls _invite_code_check."""
    from types import SimpleNamespace

    from argus.api.routers import ops

    gateway = MagicMock()
    gateway.health_check.return_value = {"status": "ready", "duration_ms": 1}
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setattr(api_state, "get_agent_runtime_workflow", lambda request: None)
    monkeypatch.setattr(
        ops,
        "warm_asset_universe",
        lambda force: SimpleNamespace(
            status="ready",
            duration_ms=1,
            provider_mode="test",
            alias_count=0,
            required_symbols=(),
            resolved_symbols=(),
            missing_symbols=(),
        ),
    )
    monkeypatch.setenv("CUADRAO_OPS_TOKEN", "test-ops-token")
    monkeypatch.setenv("CUADRAO_HOUSEHOLDS_ENABLED", "true")
    monkeypatch.delenv("CUADRAO_INVITE_CODE_SECRET", raising=False)
    calls: list[object] = []
    real_check = ops._invite_code_check  # noqa: SLF001

    def _spy():  # noqa: ANN202
        result = real_check()
        calls.append(result)
        return result

    monkeypatch.setattr(ops, "_invite_code_check", _spy)
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-ops-token"}

    response = client.get("/internal/readiness", headers=headers)
    assert calls, "readiness never ran the invite code check"
    assert response.status_code == 503
    checks = {check["name"]: check for check in response.json()["checks"]}
    assert checks["invite_codes"]["status"] == "degraded"
    assert checks["invite_codes"]["reason"] == "invite_code_secret_unusable"
    assert all(
        check["status"] == "ready"
        for name, check in checks.items()
        if name != "invite_codes"
    )

    monkeypatch.setenv("CUADRAO_INVITE_CODE_SECRET", TEST_CODE_SECRET)
    response = client.get("/internal/readiness", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_secret_removed_after_start_answers_503(client, alice, bob, monkeypatch):
    hid = alice.create_household({"name": "Casa"}).json()["household_id"]
    monkeypatch.delenv("CUADRAO_INVITE_CODE_SECRET")
    created = alice.invite(hid)
    assert created.status_code == 503
    assert created.json()["code"] == "invite_codes_unavailable"
    by_code = bob.write("/household-invitations/preview", {"code": "ABCD-EFGH-JKMN"})
    assert by_code.status_code == 503


# -- Lookup rate limits -------------------------------------------------------


def _ip(address: str) -> dict[str, str]:
    return {"CF-Connecting-IP": address}


def _post(api, path, body, *, ip):  # noqa: ANN001, ANN202
    return api._client.post(  # noqa: SLF001
        "/api/v1" + path,
        json=body,
        headers=api._headers | _ip(ip) | {"Idempotency-Key": new_code()},  # noqa: SLF001
    )


def _guess() -> dict[str, str]:
    return {"code": format_code(new_code()), "display_name": "Guess"}


def _invite_code(api) -> str:  # noqa: ANN001
    hid = api.create_household({"name": "Casa"}).json()["household_id"]
    return api.invite(hid).json()["invitation"]["code"]


@pytest.mark.parametrize(
    "path", ["/household-invitations/accept", "/household-invitations/preview"]
)
def test_failed_guesses_trip_the_account_limit_with_retry_after(alice, bob, path):
    code = _invite_code(alice)
    limit = invite_limits.FAILED_PER_ACCOUNT[0][0]
    for _ in range(limit):
        assert _post(bob, path, _guess(), ip="198.51.100.1").status_code == 404
    # Blocked before the lookup: even a real code from a fresh IP is refused.
    blocked = _post(bob, path, {"code": code, "display_name": "Bob"}, ip="198.51.100.9")
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "invite_rate_limited"
    assert 0 < int(blocked.headers["Retry-After"]) <= 3600
    # Another account behind the same IP is unaffected (IP budget is larger).
    mine = _post(alice, path, {"code": code, "display_name": "Alice"}, ip="198.51.100.1")
    assert mine.status_code != 429


def test_failed_guesses_trip_the_ip_limit_and_spare_other_ips(alice, bob, monkeypatch):
    # Raise the account budget so the IP budget is the one that trips.
    monkeypatch.setattr(
        invite_limits, "FAILED_PER_ACCOUNT", ((1000, 3600, WeightedWindow()),)
    )
    code = _invite_code(alice)
    limit = invite_limits.FAILED_PER_IP[0][0]
    path = "/household-invitations/accept"
    for _ in range(limit):
        assert _post(bob, path, _guess(), ip="203.0.113.7").status_code == 404
    assert _post(bob, path, _guess(), ip="203.0.113.7").status_code == 429
    same_ip_other_account = _post(alice, path, _guess(), ip="203.0.113.7")
    assert same_ip_other_account.status_code == 429
    # A valid code still works for the same account from another IP.
    accepted = _post(bob, path, {"code": code, "display_name": "Bob"}, ip="203.0.113.8")
    assert accepted.status_code == 200, accepted.text


def test_token_guesses_count_too(alice, bob):
    for _ in range(invite_limits.FAILED_PER_ACCOUNT[0][0]):
        response = _post(
            bob,
            "/household-invitations/accept",
            {"token": "x" * 43, "display_name": "Bob"},
            ip="198.51.100.2",
        )
        assert response.status_code == 404
    again = _post(
        bob, "/household-invitations/accept", {"token": "y" * 43}, ip="198.51.100.3"
    )
    assert again.status_code == 429


def test_found_but_closed_invites_cost_no_failure(alice, bob):
    code = _invite_code(alice)
    assert alice.write("/household-invitations/accept", {"code": code}).status_code in {
        200,
        409,
    }
    for _ in range(invite_limits.FAILED_PER_ACCOUNT[0][0] + 2):
        # Used up for Bob (consumed by Alice): found, so not a failed guess.
        response = _post(
            bob, "/household-invitations/preview", {"code": code}, ip="198.51.100.4"
        )
        assert response.status_code == 200


def test_request_budget_caps_lookups_of_any_outcome(alice, bob):
    code = _invite_code(alice)
    for _ in range(invite_limits.REQUESTS_PER_MINUTE):
        response = _post(
            bob, "/household-invitations/preview", {"code": code}, ip="192.0.2.10"
        )
        assert response.status_code == 200
    capped = _post(bob, "/household-invitations/preview", {"code": code}, ip="192.0.2.11")
    assert capped.status_code == 429 and "Retry-After" in capped.headers


class _FakeInviteStore:
    """Beta preview and redeem without Postgres: every lookup misses."""

    def __init__(self, founder: str) -> None:
        self.settings = InviteSettings(founder_user_id=founder)
        self.calls = 0

    def preview(self, *, token, code):  # noqa: ANN001, ANN201
        self.calls += 1
        raise InvitationNotFound()

    def redeem(self, *, user_id, token, code):  # noqa: ANN001, ANN201
        self.calls += 1
        raise InvitationNotFound()


@pytest.mark.parametrize("path", ["/invites/preview", "/invites/redeem"])
def test_beta_lookups_are_limited_with_no_founder_bypass(
    client, alice, identities, monkeypatch, path
):
    monkeypatch.setenv("CUADRAO_BETA_INVITES_ENABLED", "true")
    # Alice is the founder; the limit still applies to her.
    store = _FakeInviteStore(founder=identities[ALICE]["id"])
    surface.configure_invites_store(store)
    try:
        limit = invite_limits.FAILED_PER_ACCOUNT[0][0]
        for _ in range(limit):
            assert (
                _post(
                    alice, path, {"code": format_code(new_code())}, ip="192.0.2.20"
                ).status_code
                == 404
            )
        refused = _post(alice, path, {"code": format_code(new_code())}, ip="192.0.2.21")
        assert (
            refused.status_code == 429 and refused.json()["code"] == "invite_rate_limited"
        )
        assert store.calls == limit  # the refused attempt never reached the store
    finally:
        surface.configure_invites_store(None)


def test_limiter_keys_use_the_trusted_client_ip_helper():
    request = MagicMock()
    request.headers = {"CF-Connecting-IP": "198.51.100.77", "X-Forwarded-For": "10.0.0.1"}
    request.client.host = "127.0.0.1"
    ip_key, user_key = invite_limits._keys(request, "user-1")  # noqa: SLF001
    assert (
        ip_key == "invite-code:ip:198.51.100.77" and user_key == "invite-code:user:user-1"
    )


def _mock_request(ip: str) -> MagicMock:
    request = MagicMock()
    request.headers = {"CF-Connecting-IP": ip}
    request.client.host = "127.0.0.1"
    return request


def test_concurrent_guesses_cannot_run_past_the_failure_budget():
    """Codex P2 on #794: every lookup reserves its failure before it runs.

    All guesses start together and stay in flight until every one has been
    admitted or refused, so a check-then-charge limiter would let all of them
    through. Exactly the account budget may be in flight at once.
    """
    limit = invite_limits.FAILED_PER_ACCOUNT[0][0]
    total = limit + 5
    start = threading.Barrier(total)
    release = threading.Event()
    outcomes: list[object] = []
    lock = threading.Lock()

    def unknown() -> None:
        raise InvitationNotFound()

    def guess(n: int) -> None:
        start.wait(timeout=5)
        try:
            with invite_limits.attempt(_mock_request(f"192.0.2.{n}"), "user-1") as lookup:
                with lock:
                    outcomes.append("in_flight")
                release.wait(timeout=5)
                lookup.wrap(unknown)()
        except InvitationNotFound:
            pass
        except HTTPException as refused:
            with lock:
                outcomes.append(refused.status_code)

    threads = [threading.Thread(target=guess, args=(n,)) for n in range(total)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 5
    while len(outcomes) < total and time.monotonic() < deadline:
        time.sleep(0.01)
    release.set()
    for thread in threads:
        thread.join(timeout=5)

    assert outcomes.count("in_flight") == limit
    assert outcomes.count(429) == total - limit
    with pytest.raises(HTTPException) as after:
        with invite_limits.attempt(_mock_request("192.0.2.200"), "user-1"):
            pass
    assert after.value.status_code == 429  # the reservations were kept as failures


def test_a_reservation_is_refunded_when_the_lookup_finds_or_never_runs():
    limit = invite_limits.FAILED_PER_ACCOUNT[0][0]
    request = _mock_request("192.0.2.50")
    # Found an invitation, or never ran (an idempotent replay): no charge.
    # (Within the 30 a minute request budget.)
    for n in range(limit + 2):
        with invite_limits.attempt(request, "user-2") as lookup:
            if n % 2:
                lookup.wrap(lambda: "found")()
    for _ in range(limit):
        with pytest.raises(InvitationNotFound):
            with invite_limits.attempt(request, "user-2") as lookup:
                lookup.wrap(_raise_not_found)()
    with pytest.raises(HTTPException):
        with invite_limits.attempt(request, "user-2"):
            pass


def _raise_not_found() -> None:
    raise InvitationNotFound()


def test_weighted_window_refund_gives_back_the_newest_matching_spend():
    window = WeightedWindow()
    assert window.spend("k", 1, limit=2, window=60) is None
    assert window.spend("k", 1, limit=2, window=60) is None
    assert window.spend("k", 1, limit=2, window=60) is not None
    window.refund("k", 1, window=60)
    assert window.spend("k", 1, limit=2, window=60) is None
    window.refund("missing", 1, window=60)  # nothing to give back is a no-op


def test_secrets_load_through_pydantic_settings_and_never_show(monkeypatch):
    """Codex P1 on #794: the secrets come from one validated settings model."""
    from argus.domain.household.invite_codes import (
        CODE_SECRET_ENV,
        CODE_SECRET_PREVIOUS_ENV,
        InviteCodeSecretSettings,
    )

    old = "previous-invite-code-secret-0123456789abcdef"
    monkeypatch.setenv(CODE_SECRET_PREVIOUS_ENV, old)
    settings = InviteCodeSecretSettings()
    assert settings.secret is not None
    assert settings.secret.get_secret_value() == TEST_CODE_SECRET
    assert settings.secret_previous is not None
    assert settings.secret_previous.get_secret_value() == old
    assert TEST_CODE_SECRET not in repr(settings) and old not in repr(settings)
    hasher = CodeHasher.from_env()
    assert hasher.current == CodeHasher.from_secrets(TEST_CODE_SECRET).current
    assert hasher.previous is not None
    monkeypatch.delenv(CODE_SECRET_ENV)
    assert InviteCodeSecretSettings().secret is None
    with pytest.raises(InviteCodesUnavailable):
        CodeHasher.from_env()


def test_hasher_reads_only_the_settings_model(monkeypatch):
    """No raw environment read: from_env uses whatever the settings model loads."""
    from argus.domain.household import invite_codes
    from pydantic import SecretStr

    loaded = "settings-model-invite-code-secret-0123456789"

    class _Loaded(invite_codes.InviteCodeSecretSettings):
        def __init__(self) -> None:
            super().__init__(secret=SecretStr(loaded), secret_previous=None)

    monkeypatch.setattr(invite_codes, "InviteCodeSecretSettings", _Loaded)
    assert CodeHasher.from_env() == CodeHasher.from_secrets(loaded)
