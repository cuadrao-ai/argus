"""The Apple client secret and its environment inputs (no network)."""

from __future__ import annotations

from datetime import datetime, timezone

import jwt
import pytest
from argus.domain.apple_sign_in.client_secret import client_secret
from argus.domain.apple_sign_in.config import (
    BUNDLE_ID_ENV,
    KEY_ID_ENV,
    PRIVATE_KEY_ENV,
    TEAM_ID_ENV,
    AppleSignInConfig,
    AppleSignInUnconfigured,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from tests.apple_sign_in_support import (
    BUNDLE_ID,
    KEY_ID,
    TEAM_ID,
    config,
    generated_key,
    pem,
)

NOW = datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)


def test_client_secret_is_an_es256_jwt_apple_accepts() -> None:
    key = generated_key()
    secret = client_secret(config(key), now=NOW)

    header = jwt.get_unverified_header(secret)
    assert header["alg"] == "ES256"
    assert header["kid"] == KEY_ID
    claims = jwt.decode(
        secret,
        key.public_key(),
        algorithms=["ES256"],
        audience="https://appleid.apple.com",
        issuer=TEAM_ID,
        options={"verify_exp": False},
    )
    assert claims["sub"] == BUNDLE_ID
    assert claims["iat"] == int(NOW.timestamp())
    # Apple allows up to six months; each call mints a five-minute secret.
    assert claims["exp"] - claims["iat"] == 300


def test_client_secret_names_the_stored_client_for_revocation() -> None:
    key = generated_key()
    secret = client_secret(config(key), client_id="ai.cuadrao.web", now=NOW)
    claims = jwt.decode(
        secret,
        key.public_key(),
        algorithms=["ES256"],
        audience="https://appleid.apple.com",
        options={"verify_exp": False},
    )
    assert claims["sub"] == "ai.cuadrao.web"


def test_client_secret_does_not_verify_under_another_key() -> None:
    secret = client_secret(config(generated_key()), now=NOW)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(
            secret,
            generated_key().public_key(),
            algorithms=["ES256"],
            audience="https://appleid.apple.com",
            options={"verify_exp": False},
        )


@pytest.fixture
def apple_env(monkeypatch: pytest.MonkeyPatch) -> ec.EllipticCurvePrivateKey:
    key = generated_key()
    monkeypatch.setenv(TEAM_ID_ENV, TEAM_ID)
    monkeypatch.setenv(KEY_ID_ENV, KEY_ID)
    monkeypatch.setenv(BUNDLE_ID_ENV, BUNDLE_ID)
    monkeypatch.setenv(PRIVATE_KEY_ENV, pem(key))
    return key


def test_config_reads_every_input_from_the_environment(apple_env) -> None:  # noqa: ANN001
    loaded = AppleSignInConfig.from_env()
    assert (loaded.team_id, loaded.key_id, loaded.client_id) == (
        TEAM_ID,
        KEY_ID,
        BUNDLE_ID,
    )
    assert loaded.private_key.private_numbers() == apple_env.private_numbers()
    assert "PRIVATE" not in repr(loaded)


def test_config_accepts_a_single_line_escaped_key(apple_env, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv(PRIVATE_KEY_ENV, pem(apple_env).replace("\n", "\\n"))
    assert AppleSignInConfig.from_env().key_id == KEY_ID


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (TEAM_ID_ENV, ""),
        (TEAM_ID_ENV, "team123456"),
        (KEY_ID_ENV, ""),
        (KEY_ID_ENV, "SHORT"),
        (BUNDLE_ID_ENV, ""),
        (BUNDLE_ID_ENV, "nodots"),
        (PRIVATE_KEY_ENV, ""),
        (PRIVATE_KEY_ENV, "not a pem"),
    ],
)
def test_config_fails_closed_on_a_missing_or_malformed_input(
    apple_env,
    monkeypatch,
    name,
    value,  # noqa: ANN001
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(AppleSignInUnconfigured) as raised:
        AppleSignInConfig.from_env()
    assert name in str(raised.value)
    assert "BEGIN" not in str(raised.value)


def test_config_refuses_a_key_apple_cannot_use(apple_env, monkeypatch) -> None:  # noqa: ANN001
    for wrong in (
        rsa.generate_private_key(public_exponent=65537, key_size=2048),
        ec.generate_private_key(ec.SECP384R1()),
    ):
        monkeypatch.setenv(
            PRIVATE_KEY_ENV,
            wrong.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
        )
        with pytest.raises(AppleSignInUnconfigured):
            AppleSignInConfig.from_env()
