"""``POST /api/v1/auth/apple/authorization-code`` through the real auth dependency."""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from argus.api import state as api_state
from argus.api.apple_sign_in import (
    FLAG,
    apple_credentials_service,
    configure_apple_credentials_service,
)
from argus.api.main import app
from argus.api.routers.auth_apple import reset_apple_capture_limiter_for_tests
from argus.domain.apple_sign_in.client import AppleAuthClient
from argus.domain.apple_sign_in.config import (
    BUNDLE_ID_ENV,
    KEY_ID_ENV,
    PRIVATE_KEY_ENV,
    TEAM_ID_ENV,
)
from argus.domain.apple_sign_in.credentials import SOURCE, AppleCredentialService
from fastapi.testclient import TestClient

from tests.apple_sign_in_support import (
    BUNDLE_ID,
    KEY_ID,
    SUBJECT,
    TEAM_ID,
    FakeApple,
    generated_key,
    pem,
)
from tests.financial_accounts.conftest import (  # noqa: F401
    ALICE,
    BOB,
    GUEST,
    gateway,
    identities,
    surface_env,
)

URL = "/api/v1/auth/apple/authorization-code"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def key():  # noqa: ANN201
    return generated_key()


@pytest.fixture
def apple_env(surface_env, monkeypatch, key) -> None:  # noqa: ANN001, F811
    monkeypatch.setenv(FLAG, "true")
    monkeypatch.setenv(TEAM_ID_ENV, TEAM_ID)
    monkeypatch.setenv(KEY_ID_ENV, KEY_ID)
    monkeypatch.setenv(BUNDLE_ID_ENV, BUNDLE_ID)
    monkeypatch.setenv(PRIVATE_KEY_ENV, pem(key))
    monkeypatch.setenv(
        "ARGUS_INGESTION_SECRET_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )


@pytest.fixture
def linked(identities, gateway):  # noqa: ANN001, ANN201, F811
    """ALICE signed in with Apple; BOB has only an email identity."""

    def by_id(user_id: str) -> dict:
        user = next(u for u in identities.values() if u["id"] == user_id)
        provider = "apple" if user is identities[ALICE] else "email"
        sub = SUBJECT if provider == "apple" else user_id
        return {
            **user,
            "identities": [
                {"provider": provider, "provider_id": sub, "identity_data": {"sub": sub}}
            ],
        }

    gateway.get_auth_user_by_id.side_effect = by_id
    return gateway


def _client(mock_gateway) -> Iterator[TestClient]:  # noqa: ANN001
    assert api_state.PERSISTENCE_MODE == "memory"
    reset_apple_capture_limiter_for_tests()
    with (
        patch.object(api_state, "supabase_gateway", mock_gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        yield test_client


@pytest.fixture
def client(apple_env, linked) -> Iterator[TestClient]:  # noqa: ANN001
    yield from _client(linked)


@pytest.fixture
def apple(client, key) -> FakeApple:  # noqa: ANN001
    started = apple_credentials_service()
    assert started is not None, "flag on and configured must build the service"
    fake = FakeApple(public_key=key.public_key())
    configure_apple_credentials_service(
        AppleCredentialService(
            started.repository,
            box=started._box,
            client=AppleAuthClient(started._client.config, transport=fake.transport()),
            clock=started._clock,
        )
    )
    return fake


def test_flag_off_is_404_before_authentication(surface_env, gateway, monkeypatch) -> None:  # noqa: ANN001, F811
    monkeypatch.delenv(FLAG, raising=False)
    for test_client in _client(gateway):
        response = test_client.post(URL, json={"authorization_code": "c"})
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
        assert apple_credentials_service() is None
    gateway.get_auth_user_from_token.assert_not_called()


@pytest.mark.parametrize(
    ("path", "content", "headers"),
    [
        (URL, b"{not json", {"Content-Type": "application/json"}),
        (URL, b"{not json", {"Content-Type": "application/json", **bearer(ALICE)}),
        (URL, b'{"authorization_code": ""}', {"Content-Type": "application/json"}),
        (URL, b"", {}),
        (URL + "/", b"{not json", {"Content-Type": "application/json"}),
    ],
)
def test_flag_off_gates_before_the_body_is_read(
    surface_env,  # noqa: F811
    gateway,  # noqa: F811
    monkeypatch,
    path,
    content,
    headers,
) -> None:  # noqa: ANN001
    # Same as EvidenceReceiptFlagGateMiddleware: invalid JSON is 404, not 422,
    # so a disabled deployment looks exactly like one without the route.
    monkeypatch.delenv(FLAG, raising=False)
    for test_client in _client(gateway):
        response = test_client.post(path, content=content, headers=headers)
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
        assert response.headers.get("x-request-id")
    gateway.get_auth_user_from_token.assert_not_called()


def test_flag_on_still_validates_the_body(client, apple) -> None:  # noqa: ANN001
    response = client.post(
        URL,
        content=b"{not json",
        headers={"Content-Type": "application/json", **bearer(ALICE)},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "missing",
    [
        TEAM_ID_ENV,
        KEY_ID_ENV,
        BUNDLE_ID_ENV,
        PRIVATE_KEY_ENV,
        "ARGUS_INGESTION_SECRET_KEY",
    ],
)
def test_flag_on_without_every_input_fails_closed(
    apple_env,
    linked,
    monkeypatch,
    missing,  # noqa: ANN001
) -> None:
    monkeypatch.delenv(missing)
    for test_client in _client(linked):
        response = test_client.post(
            URL, json={"authorization_code": "c"}, headers=bearer(ALICE)
        )
        assert response.status_code == 503
        assert response.json()["code"] == "apple_sign_in_unconfigured"


def test_capture_stores_the_sealed_token_for_the_session_user(
    client,
    apple,
    identities,  # noqa: ANN001, F811
) -> None:
    refresh = apple.grant()
    response = client.post(
        URL, json={"authorization_code": "c.one-time"}, headers=bearer(ALICE)
    )

    assert response.status_code == 204, response.text
    assert response.content == b""
    service = apple_credentials_service()
    stored = list(service.repository._rows.values())  # the in-memory twin
    assert len(stored) == 1
    assert stored[0].user_id == identities[ALICE]["id"]
    assert refresh.encode() not in stored[0].secret_ciphertext
    assert (
        service._box.open(
            stored[0].secret_ciphertext, source=SOURCE, connection_id=stored[0].user_id
        )
        == refresh
    )


def test_the_user_id_comes_only_from_the_session(client, apple, identities) -> None:  # noqa: ANN001, F811
    response = client.post(
        URL,
        json={"authorization_code": "c", "user_id": identities[BOB]["id"]},
        headers=bearer(ALICE),
    )
    assert response.status_code == 422
    assert apple.calls == []


def test_unauthenticated_and_guest_callers_are_refused(client, apple) -> None:  # noqa: ANN001
    assert client.post(URL, json={"authorization_code": "c"}).status_code == 401
    guest = client.post(URL, json={"authorization_code": "c"}, headers=bearer(GUEST))
    assert guest.status_code == 403
    assert guest.json()["code"] == "account_conversion_required"
    assert apple.calls == []


def test_an_account_without_an_apple_identity_is_refused(client, apple) -> None:  # noqa: ANN001
    response = client.post(URL, json={"authorization_code": "c"}, headers=bearer(BOB))
    assert response.status_code == 409
    assert response.json()["code"] == "apple_identity_missing"
    assert apple.calls == []


def test_a_code_for_another_apple_id_is_refused_and_not_stored(client, apple) -> None:  # noqa: ANN001
    apple.grant(sub="000999.someone-else")
    response = client.post(URL, json={"authorization_code": "c"}, headers=bearer(ALICE))
    assert response.status_code == 409
    assert response.json()["code"] == "apple_identity_mismatch"
    assert apple_credentials_service().repository._rows == {}


def test_a_storage_failure_is_503_and_revokes_the_token(
    client, apple, monkeypatch
) -> None:  # noqa: ANN001
    repository = apple_credentials_service().repository

    def down(**_: object) -> None:
        raise ConnectionError("database down")

    monkeypatch.setattr(repository, "save_capture", down)
    refresh = apple.grant()
    response = client.post(URL, json={"authorization_code": "c"}, headers=bearer(ALICE))
    assert response.status_code == 503
    assert response.json()["code"] == "apple_sign_in_unavailable"
    assert refresh not in response.text
    assert apple.calls[-1][0] == "/auth/revoke"
    assert repository._rows == {}


@pytest.mark.parametrize("failure", ["unexpected", "apple_down"])
def test_a_failed_save_stays_503_whatever_the_compensating_revoke_does(
    client, apple, monkeypatch, failure
) -> None:  # noqa: ANN001
    repository = apple_credentials_service().repository

    def down(**_: object) -> None:
        raise ConnectionError("database down")

    monkeypatch.setattr(repository, "save_capture", down)
    if failure == "unexpected":
        apple.revoke_raises = RuntimeError("unexpected client failure")
    else:
        apple.revoke_responses += [(503, None), (503, None), (503, None)]
    refresh = apple.grant()
    response = client.post(URL, json={"authorization_code": "c"}, headers=bearer(ALICE))
    assert response.status_code == 503
    assert response.json()["code"] == "apple_sign_in_unavailable"
    assert refresh not in response.text
    assert [path for path, _ in apple.calls].count("/auth/revoke") == 1


@pytest.mark.parametrize("failure", ["unexpected", "apple_down"])
def test_a_mismatch_stays_409_whatever_the_compensating_revoke_does(
    client, apple, failure
) -> None:  # noqa: ANN001
    if failure == "unexpected":
        apple.revoke_raises = RuntimeError("unexpected client failure")
    else:
        apple.revoke_responses += [(503, None), (503, None), (503, None)]
    refresh = apple.grant(sub="000999.someone-else")
    response = client.post(URL, json={"authorization_code": "c"}, headers=bearer(ALICE))
    assert response.status_code == 409
    assert response.json()["code"] == "apple_identity_mismatch"
    assert refresh not in response.text
    assert [path for path, _ in apple.calls].count("/auth/revoke") == 1


def test_a_used_or_expired_code_is_400(client, apple) -> None:  # noqa: ANN001
    apple.token_responses.append((400, {"error": "invalid_grant"}))
    response = client.post(URL, json={"authorization_code": "c"}, headers=bearer(ALICE))
    assert response.status_code == 400
    assert response.json()["code"] == "apple_authorization_invalid"


def test_apple_failures_are_503_and_never_echo_tokens(client, apple) -> None:  # noqa: ANN001
    apple.token_responses.append((400, {"error": "invalid_client"}))
    response = client.post(
        URL, json={"authorization_code": "c.secret-code"}, headers=bearer(ALICE)
    )
    assert response.status_code == 503
    assert response.json()["code"] == "apple_sign_in_unavailable"
    assert "c.secret-code" not in response.text


def test_capture_attempts_are_rate_limited_per_user(client, apple) -> None:  # noqa: ANN001
    for _ in range(5):
        apple.token_responses.append((400, {"error": "invalid_grant"}))
        client.post(URL, json={"authorization_code": "c"}, headers=bearer(ALICE))
    limited = client.post(URL, json={"authorization_code": "c"}, headers=bearer(ALICE))
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers
    assert len(apple.calls) == 5


def test_identity_lookup_failure_is_503(client, apple, linked) -> None:  # noqa: ANN001
    linked.get_auth_user_by_id.side_effect = RuntimeError("down")
    response = client.post(URL, json={"authorization_code": "c"}, headers=bearer(ALICE))
    assert response.status_code == 503
    assert apple.calls == []


def test_gateway_mock_is_spec_bound(linked) -> None:  # noqa: ANN001
    assert isinstance(linked, MagicMock)
    assert hasattr(linked, "get_auth_user_by_id")


def test_conflicting_apple_identities_fail_before_exchange(client, apple, linked):
    linked.get_auth_user_by_id.side_effect = None
    linked.get_auth_user_by_id.return_value = {
        "identities": [
            {
                "provider": "apple",
                "provider_id": SUBJECT,
                "identity_data": {"sub": SUBJECT},
            },
            {
                "provider": "apple",
                "provider_id": "other",
                "identity_data": {"sub": "other"},
            },
        ]
    }
    apple.grant()
    response = client.post(
        URL, headers=bearer(ALICE), json={"authorization_code": "c.code"}
    )
    assert response.status_code == 503
    assert apple.calls == []


@pytest.mark.parametrize("failure", ["mismatch", "storage"])
def test_discard_worker_exception_does_not_change_http_outcome(
    client, apple, monkeypatch, failure
):
    import threading

    escaped = []
    monkeypatch.setattr(threading, "excepthook", escaped.append)
    apple.grant(sub="other" if failure == "mismatch" else SUBJECT)
    apple.revoke_raises = RuntimeError("unexpected_transport_failure")
    if failure == "storage":

        def unavailable(**kwargs):
            raise ConnectionError("unavailable")

        monkeypatch.setattr(
            apple_credentials_service().repository, "save_capture", unavailable
        )
    response = client.post(
        URL, headers=bearer(ALICE), json={"authorization_code": "c.code"}
    )
    assert response.status_code == (409 if failure == "mismatch" else 503)
    assert response.json()["code"] == (
        "apple_identity_mismatch"
        if failure == "mismatch"
        else "apple_sign_in_unavailable"
    )
    assert escaped == []
