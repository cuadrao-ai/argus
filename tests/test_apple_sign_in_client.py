"""Apple's token and revoke endpoints through a scripted transport."""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone

import httpx
import pytest
from argus.domain.apple_sign_in.client import (
    DISCARD_TIMEOUT_SECONDS,
    TIMEOUT_SECONDS,
    AppleAuthClient,
    AppleError,
)
from argus.domain.apple_sign_in.credentials import (
    SOURCE,
    AppleCaptureNotStored,
    AppleCredentialService,
    AppleIdentityMismatch,
    AppleRevocationPending,
    DiscardOutcome,
    InMemoryAppleCredentialRepository,
    RevokeOutcome,
)
from argus.domain.apple_sign_in.identity import LinkedAppleIdentity
from argus.domain.ingestion.secrets import SecretBox

from tests.apple_sign_in_support import (
    BUNDLE_ID,
    SUBJECT,
    FakeApple,
    config,
    generated_key,
)

NOW = datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)
USER = "8b0e3f8e-2b4c-4d8e-9a43-3f0c2a1d5e77"


@pytest.fixture
def key():  # noqa: ANN201
    return generated_key()


@pytest.fixture
def apple(key) -> FakeApple:  # noqa: ANN001
    return FakeApple(public_key=key.public_key())


@pytest.fixture
def client(key, apple):  # noqa: ANN001, ANN201
    sleeps: list[float] = []
    made = AppleAuthClient(config(key), transport=apple.transport(), sleep=sleeps.append)
    made.sleeps = sleeps  # type: ignore[attr-defined]
    yield made
    made.close()


def _box() -> SecretBox:
    return SecretBox(os.urandom(32))


def test_exchange_posts_the_code_with_a_fresh_secret_and_reads_the_subject(
    client,
    apple,  # noqa: ANN001
) -> None:
    refresh = apple.grant()
    grant = client.exchange_code("c.one-time-code")

    assert grant.refresh_token == refresh
    assert grant.subject == SUBJECT
    assert refresh not in repr(grant)
    path, form = apple.calls[0]
    assert path == "/auth/token"
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "c.one-time-code"
    assert form["client_id"] == BUNDLE_ID


@pytest.mark.parametrize(
    ("claims", "reason"),
    [
        ({"aud": "ai.someone.else"}, "unexpected_id_token"),
        ({"sub": ""}, "unexpected_id_token"),
        ({"iss": "https://appleid.example.test"}, "unexpected_id_token"),
    ],
)
def test_exchange_refuses_an_identity_token_for_another_client(
    client,
    apple,
    claims,
    reason,  # noqa: ANN001
) -> None:
    apple.grant(**claims)
    with pytest.raises(AppleError) as raised:
        client.exchange_code("c.code")
    assert raised.value.reason == reason


def test_exchange_needs_a_refresh_token(client, apple) -> None:  # noqa: ANN001
    apple.token_responses.append((200, {"access_token": "a", "id_token": "x"}))
    with pytest.raises(AppleError) as raised:
        client.exchange_code("c.code")
    assert raised.value.reason == "missing_refresh_token"


def test_a_used_code_is_invalid_grant_and_is_never_retried(client, apple) -> None:  # noqa: ANN001
    apple.token_responses.append((400, {"error": "invalid_grant"}))
    with pytest.raises(AppleError) as raised:
        client.exchange_code("c.used")
    assert raised.value.invalid_grant
    assert len(apple.calls) == 1


def test_an_unavailable_apple_is_not_retried_for_a_single_use_code(
    client,
    apple,  # noqa: ANN001
) -> None:
    apple.token_responses.append((503, {"error": "server_error"}))
    with pytest.raises(AppleError) as raised:
        client.exchange_code("c.code")
    assert raised.value.status == 503 and not raised.value.invalid_grant
    assert len(apple.calls) == 1


@pytest.mark.parametrize("code", ["", "x" * 513, "código"])
def test_a_malformed_code_never_reaches_apple(client, apple, code) -> None:  # noqa: ANN001
    with pytest.raises(AppleError) as raised:
        client.exchange_code(code)
    assert raised.value.reason == "malformed_code"
    assert apple.calls == []


def test_revoke_names_the_refresh_token_and_retries_transient_failures(
    client,
    apple,  # noqa: ANN001
) -> None:
    apple.revoke_responses += [(503, {"error": "server_error"}), (200, None)]
    client.revoke("r.stored", client_id=BUNDLE_ID)

    assert [path for path, _ in apple.calls] == ["/auth/revoke", "/auth/revoke"]
    form = apple.calls[-1][1]
    assert form == {
        "client_id": BUNDLE_ID,
        "client_secret": form["client_secret"],
        "token": "r.stored",
        "token_type_hint": "refresh_token",
    }
    assert client.sleeps == [0.5]


def test_revoke_failures_carry_no_token(client, apple) -> None:  # noqa: ANN001
    apple.revoke_responses.append(
        (400, {"error": "invalid_client", "detail": "r.stored"})
    )
    with pytest.raises(AppleError) as raised:
        client.revoke("r.stored", client_id=BUNDLE_ID)
    assert raised.value.reason == "invalid_client"
    assert "r.stored" not in str(raised.value)


def test_unreachable_apple_is_bounded(key) -> None:  # noqa: ANN001
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    sleeps: list[float] = []
    made = AppleAuthClient(
        config(key), transport=httpx.MockTransport(down), sleep=sleeps.append
    )
    with pytest.raises(AppleError) as raised:
        made.revoke("r", client_id=BUNDLE_ID)
    assert raised.value.reason == "unreachable"
    assert len(sleeps) == 2


# The capture/revoke service, against the in-memory twin -----------------------


@pytest.fixture
def service(client):  # noqa: ANN001, ANN201
    return AppleCredentialService(
        InMemoryAppleCredentialRepository(lambda _: LinkedAppleIdentity(SUBJECT)),
        box=_box(),
        client=client,
        clock=lambda: NOW,
    )


def test_capture_keeps_only_the_sealed_refresh_token(service, apple) -> None:  # noqa: ANN001
    refresh = apple.grant()
    service.capture(user_id=USER, authorization_code="c.code")

    row = service.repository.get(user_id=USER)
    assert row is not None and row.client_id == BUNDLE_ID
    assert refresh.encode() not in row.secret_ciphertext
    assert (
        service._box.open(row.secret_ciphertext, source=SOURCE, connection_id=USER)
        == refresh
    )
    assert refresh not in repr(row)


def test_capture_for_another_apple_id_stores_nothing_and_revokes_it(
    service, apple
) -> None:  # noqa: ANN001
    refresh = apple.grant(sub="000999.other")
    with pytest.raises(AppleIdentityMismatch):
        service.capture(user_id=USER, authorization_code="c.code")
    assert service.repository.get(user_id=USER) is None
    assert apple.calls[-1] == ("/auth/revoke", apple.calls[-1][1])
    assert apple.calls[-1][1]["token"] == refresh


class _BrokenRepository(InMemoryAppleCredentialRepository):
    def save_capture(self, **_: object) -> None:
        raise ConnectionError("database down")


def test_a_storage_failure_revokes_the_exchanged_token(client, apple) -> None:  # noqa: ANN001
    # Apple already consumed the one-time code, so the token is revoked rather
    # than dropped; the next Apple sign-in yields a fresh code.
    service = AppleCredentialService(
        _BrokenRepository(lambda _: LinkedAppleIdentity(SUBJECT)),
        box=_box(),
        client=client,
        clock=lambda: NOW,
    )
    refresh = apple.grant()
    with pytest.raises(AppleCaptureNotStored) as raised:
        service.capture(user_id=USER, authorization_code="c.code")
    assert refresh not in str(raised.value)
    path, form = apple.calls[-1]
    assert path == "/auth/revoke"
    assert form["token"] == refresh and form["token_type_hint"] == "refresh_token"


def test_a_storage_failure_still_reports_when_the_revoke_fails(client, apple) -> None:  # noqa: ANN001
    service = AppleCredentialService(
        _BrokenRepository(lambda _: LinkedAppleIdentity(SUBJECT)),
        box=_box(),
        client=client,
        clock=lambda: NOW,
    )
    apple.grant()
    apple.revoke_responses.append((400, {"error": "invalid_client"}))
    with pytest.raises(AppleCaptureNotStored):
        service.capture(user_id=USER, authorization_code="c.code")


def test_a_later_sign_in_replaces_the_token_without_revoking_it(service, apple) -> None:  # noqa: ANN001
    apple.grant()
    service.capture(user_id=USER, authorization_code="c.1")
    second = apple.grant()
    service.capture(user_id=USER, authorization_code="c.2")

    row = service.repository.get(user_id=USER)
    assert (
        service._box.open(row.secret_ciphertext, source=SOURCE, connection_id=USER)
        == second
    )
    assert all(path == "/auth/token" for path, _ in apple.calls)


def test_revoke_deletes_the_row_only_after_apple_confirms(service, apple) -> None:  # noqa: ANN001
    refresh = apple.grant()
    service.capture(user_id=USER, authorization_code="c.code")

    assert service.revoke(user_id=USER) is RevokeOutcome.REVOKED
    assert apple.calls[-1][1]["token"] == refresh
    assert service.repository.get(user_id=USER) is None
    assert service.revoke(user_id=USER) is RevokeOutcome.NOTHING_STORED


def test_a_failed_revoke_keeps_the_sealed_token_as_the_pending_revoke(
    service,
    apple,  # noqa: ANN001
) -> None:
    apple.grant()
    service.capture(user_id=USER, authorization_code="c.code")
    apple.revoke_responses += [(503, {"error": "server_error"})] * 3

    with pytest.raises(AppleRevocationPending) as raised:
        service.revoke(user_id=USER)
    assert raised.value.reason == "server_error"
    assert service.repository.get(user_id=USER) is not None

    assert service.revoke(user_id=USER) is RevokeOutcome.REVOKED
    assert service.repository.get(user_id=USER) is None


def test_a_token_replaced_mid_revoke_stays_pending(service, apple) -> None:  # noqa: ANN001
    apple.grant()
    service.capture(user_id=USER, authorization_code="c.1")
    replacement = apple.grant()

    real_revoke = service._client.revoke

    def revoke_then_sign_in_again(token: str, *, client_id: str) -> None:
        real_revoke(token, client_id=client_id)
        service.capture(user_id=USER, authorization_code="c.2")

    service._client.revoke = revoke_then_sign_in_again
    with pytest.raises(AppleRevocationPending) as raised:
        service.revoke(user_id=USER)
    assert raised.value.reason == "credential_replaced"
    row = service.repository.get(user_id=USER)
    assert (
        service._box.open(row.secret_ciphertext, source=SOURCE, connection_id=USER)
        == replacement
    )


def test_a_credential_sealed_under_another_key_is_pending_not_dropped(
    client,
    apple,  # noqa: ANN001
) -> None:
    repository = InMemoryAppleCredentialRepository(lambda _: LinkedAppleIdentity(SUBJECT))
    writer = AppleCredentialService(
        repository, box=_box(), client=client, clock=lambda: NOW
    )
    apple.grant()
    writer.capture(user_id=USER, authorization_code="c.code")
    rotated = AppleCredentialService(
        repository, box=_box(), client=client, clock=lambda: NOW
    )

    with pytest.raises(AppleRevocationPending) as raised:
        rotated.revoke(user_id=USER)
    assert raised.value.reason == "credential_unreadable"
    assert repository.get(user_id=USER) is not None
    assert [path for path, _ in apple.calls] == ["/auth/token"]


def test_a_sealed_token_does_not_open_for_another_user(service, apple) -> None:  # noqa: ANN001
    from argus.domain.ingestion.secrets import SecretUnreadable

    apple.grant()
    service.capture(user_id=USER, authorization_code="c.code")
    row = service.repository.get(user_id=USER)
    with pytest.raises(SecretUnreadable):
        service._box.open(
            row.secret_ciphertext,
            source=SOURCE,
            connection_id=base64.b16encode(os.urandom(16)).decode(),
        )


# Priya's #793 notes ------------------------------------------------------------

LEGACY_CLIENT = "ai.cuadrao.legacy"


def _phases(seconds: float) -> dict[str, float]:
    return {"connect": seconds, "read": seconds, "write": seconds, "pool": seconds}


def test_every_apple_call_carries_the_client_timeout(client, apple) -> None:  # noqa: ANN001
    apple.grant()
    client.exchange_code("c.code")
    client.revoke("r.stored", client_id=BUNDLE_ID)
    assert apple.timeouts == [_phases(TIMEOUT_SECONDS), _phases(TIMEOUT_SECONDS)]


def test_revoke_sends_the_client_the_token_was_issued_to(client, apple) -> None:  # noqa: ANN001
    # The fake also checks that the client secret's sub names this same client.
    client.revoke("r.stored", client_id=LEGACY_CLIENT)
    path, form = apple.calls[-1]
    assert path == "/auth/revoke"
    assert form["client_id"] == LEGACY_CLIENT != BUNDLE_ID


def test_service_revokes_with_the_stored_client_not_the_configured_one(
    service,
    apple,  # noqa: ANN001
) -> None:
    service.repository.upsert(
        user_id=USER,
        client_id=LEGACY_CLIENT,
        secret_ciphertext=service._box.seal(
            "r.legacy", source=SOURCE, connection_id=USER
        ),
        now=NOW,
    )
    assert service.revoke(user_id=USER) is RevokeOutcome.REVOKED
    assert apple.calls[-1][1]["client_id"] == LEGACY_CLIENT
    assert apple.calls[-1][1]["token"] == "r.legacy"


def test_apple_invalid_grant_on_revoke_counts_as_already_revoked(service, apple) -> None:  # noqa: ANN001
    apple.grant()
    service.capture(user_id=USER, authorization_code="c.code")
    apple.revoke_responses.append((400, {"error": "invalid_grant"}))
    assert service.revoke(user_id=USER) is RevokeOutcome.ALREADY_REVOKED
    assert service.repository.get(user_id=USER) is None
    assert service.revoke(user_id=USER) is RevokeOutcome.NOTHING_STORED


def test_other_revoke_refusals_still_keep_the_pending_row(service, apple) -> None:  # noqa: ANN001
    apple.grant()
    service.capture(user_id=USER, authorization_code="c.code")
    apple.revoke_responses.append((400, {"error": "invalid_client"}))
    with pytest.raises(AppleRevocationPending):
        service.revoke(user_id=USER)
    assert service.repository.get(user_id=USER) is not None


@pytest.mark.parametrize("path", ["mismatch", "failed_save"])
def test_the_compensating_revoke_is_one_short_attempt(client, apple, path) -> None:  # noqa: ANN001
    # Inside the person's capture request: no retry, no backoff sleep, and a
    # two-second timeout instead of thirty, even while Apple answers 503.
    repository = (
        _BrokenRepository(lambda _: LinkedAppleIdentity(SUBJECT))
        if path == "failed_save"
        else InMemoryAppleCredentialRepository(lambda _: LinkedAppleIdentity(SUBJECT))
    )
    service = AppleCredentialService(
        repository, box=_box(), client=client, clock=lambda: NOW
    )
    apple.grant(sub="000999.other" if path == "mismatch" else SUBJECT)
    apple.revoke_responses += [(503, None), (503, None), (200, None)]
    expected = AppleIdentityMismatch if path == "mismatch" else AppleCaptureNotStored
    with pytest.raises(expected):
        service.capture(user_id=USER, authorization_code="c.code")
    revokes = [i for i, (p, _) in enumerate(apple.calls) if p == "/auth/revoke"]
    assert len(revokes) == 1
    assert apple.timeouts[revokes[0]] == _phases(DISCARD_TIMEOUT_SECONDS)
    assert client.sleeps == []


@pytest.mark.parametrize("path", ["mismatch", "failed_save"])
def test_an_unexpected_compensating_revoke_error_keeps_the_outcome(
    client, apple, path
) -> None:  # noqa: ANN001
    repository = (
        _BrokenRepository(lambda _: LinkedAppleIdentity(SUBJECT))
        if path == "failed_save"
        else InMemoryAppleCredentialRepository(lambda _: LinkedAppleIdentity(SUBJECT))
    )
    service = AppleCredentialService(
        repository, box=_box(), client=client, clock=lambda: NOW
    )
    apple.grant(sub="000999.other" if path == "mismatch" else SUBJECT)
    apple.revoke_raises = RuntimeError("unexpected")
    expected = AppleIdentityMismatch if path == "mismatch" else AppleCaptureNotStored
    with pytest.raises(expected):
        service.capture(user_id=USER, authorization_code="c.code")


def _logged(records: list) -> str:  # noqa: ANN001
    return "\n".join(str(r) + str(r.record["extra"]) for r in records)


def test_discard_removes_only_an_unreadable_row_and_logs_no_token(service, apple) -> None:  # noqa: ANN001
    from loguru import logger

    # Sealed under this service's key (its key id says so) and damaged: dead.
    stale = SecretBox(os.urandom(32)).seal(
        "r.under-old-key", source=SOURCE, connection_id=USER
    )
    service.repository.upsert(
        user_id=USER,
        client_id=BUNDLE_ID,
        secret_ciphertext=stale,
        now=NOW,
        key_id=service._box.key_id,
    )
    with pytest.raises(AppleRevocationPending) as raised:
        service.revoke(user_id=USER)
    assert raised.value.reason == "credential_unreadable"

    records: list = []
    sink = logger.add(records.append, level="DEBUG")
    try:
        assert service.discard_unreadable(user_id=USER) is DiscardOutcome.DISCARDED
    finally:
        logger.remove(sink)
    assert service.repository.get(user_id=USER) is None
    assert apple.calls == []
    assert "r.under-old-key" not in _logged(records)
    assert service.discard_unreadable(user_id=USER) is DiscardOutcome.NOTHING_STORED


@pytest.mark.parametrize("sealed_by", ["another_key", "no_key_id"])
def test_discard_keeps_a_token_another_key_may_open(service, apple, sealed_by) -> None:  # noqa: ANN001
    """Priya B1: during a rolling rotation the token may be live for a process
    on the other key. Only this key's own fingerprint proves it dead."""
    other = SecretBox(os.urandom(32))
    service.repository.upsert(
        user_id=USER,
        client_id=BUNDLE_ID,
        secret_ciphertext=other.seal("r.live", source=SOURCE, connection_id=USER),
        now=NOW,
        key_id=other.key_id if sealed_by == "another_key" else None,
    )
    with pytest.raises(AppleRevocationPending) as raised:
        service.discard_unreadable(user_id=USER)
    assert raised.value.reason == "key_unproven"
    assert service.repository.get(user_id=USER) is not None
    assert apple.calls == []


def test_discard_never_drops_a_token_that_can_still_be_revoked(service, apple) -> None:  # noqa: ANN001
    apple.grant()
    service.capture(user_id=USER, authorization_code="c.code")
    assert service.repository.get(user_id=USER).key_id == service._box.key_id
    assert service.discard_unreadable(user_id=USER) is DiscardOutcome.READABLE
    assert service.repository.get(user_id=USER) is not None


def test_discard_is_scoped_to_the_given_user(service, apple) -> None:  # noqa: ANN001
    other = "1f6b7c9a-5d3e-4a2b-8c1d-0e9f8a7b6c5d"
    stale = SecretBox(os.urandom(32)).seal("r.other", source=SOURCE, connection_id=other)
    service.repository.upsert(
        user_id=other, client_id=BUNDLE_ID, secret_ciphertext=stale, now=NOW
    )
    assert service.discard_unreadable(user_id=USER) is DiscardOutcome.NOTHING_STORED
    assert service.repository.get(user_id=other) is not None


class _Trickle(httpx.SyncByteStream):
    """A body sent one byte at a time, each just inside the per-read timeout."""

    def __init__(self, clock: list[float], step: float) -> None:
        self._clock = clock
        self._step = step

    def __iter__(self):  # noqa: ANN204
        for byte in b"{}" * 8:
            self._clock[0] += self._step
            yield bytes([byte])


def test_a_trickled_response_still_hits_the_total_deadline(key) -> None:  # noqa: ANN001
    # httpx's read timeout restarts on every chunk; the client's own total
    # deadline does not, so the compensating revoke can't be kept open.
    clock = [0.0]
    sent: list[str] = []

    def trickle(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        return httpx.Response(200, stream=_Trickle(clock, DISCARD_TIMEOUT_SECONDS / 3))

    made = AppleAuthClient(
        config(key),
        transport=httpx.MockTransport(trickle),
        sleep=lambda _s: None,
        monotonic=lambda: clock[0],
    )
    with pytest.raises(AppleError) as raised:
        made.revoke(
            "r.x", client_id=BUNDLE_ID, timeout=DISCARD_TIMEOUT_SECONDS, attempts=1
        )
    assert raised.value.reason == "unreachable"
    assert sent == ["/auth/revoke"]
    assert clock[0] < DISCARD_TIMEOUT_SECONDS * 2
    made.close()


@pytest.mark.parametrize("path", ["mismatch", "failed_save"])
def test_a_hung_compensating_revoke_releases_the_request(key, apple, path) -> None:  # noqa: ANN001
    import threading
    import time

    release = threading.Event()
    revoking = threading.Event()

    def hang_on_revoke(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/revoke":
            revoking.set()
            release.wait(10)
            return httpx.Response(200)
        return apple(request)

    made = AppleAuthClient(
        config(key), transport=httpx.MockTransport(hang_on_revoke), sleep=lambda _s: None
    )
    repository = (
        _BrokenRepository(lambda _: LinkedAppleIdentity(SUBJECT))
        if path == "failed_save"
        else InMemoryAppleCredentialRepository(lambda _: LinkedAppleIdentity(SUBJECT))
    )
    service = AppleCredentialService(
        repository, box=_box(), client=made, clock=lambda: NOW, discard_deadline=0.2
    )
    apple.grant(sub="000999.other" if path == "mismatch" else SUBJECT)
    expected = AppleIdentityMismatch if path == "mismatch" else AppleCaptureNotStored
    started = time.monotonic()
    try:
        with pytest.raises(expected):
            service.capture(user_id=USER, authorization_code="c.code")
        assert time.monotonic() - started < 2.0
        assert revoking.is_set()
    finally:
        release.set()
        made.close()


def test_provider_only_revoke_preserves_credential_until_owner_receipt(service, apple):
    apple.grant()
    service.capture(user_id=USER, authorization_code="c.receipt")
    stored = service.repository.get(user_id=USER)
    assert service.revoke_stored(stored) is RevokeOutcome.REVOKED
    assert service.repository.get(user_id=USER) == stored
