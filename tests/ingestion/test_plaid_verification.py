"""Plaid-Verification JWT checks with a locally generated ES256 key."""

import hashlib
import json

import jwt
import pytest
from argus.domain.ingestion.plaid.client import PlaidError
from argus.domain.ingestion.plaid.verification import (
    VerificationUnavailable,
    WebhookRejected,
    WebhookVerifier,
)
from cryptography.hazmat.primitives.asymmetric import ec

from tests.ingestion.plaid_fakes import Clock

KID = "6c5516e1-92dc-479e-a8ff-5a51992e0001"
BODY = json.dumps(
    {
        "webhook_type": "TRANSACTIONS",
        "webhook_code": "SYNC_UPDATES_AVAILABLE",
        "item_id": "item-sandbox-aaaa",
        "environment": "sandbox",
    },
    indent=2,
).encode()


def es256_key():
    private = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(private.public_key(), as_dict=True)
    jwk.update(alg="ES256", kid=KID, use="sig", created_at=1_700_000_000, expired_at=None)
    return private, jwk


PRIVATE, JWK = es256_key()


def sign(
    clock: Clock, body: bytes = BODY, *, age: int = 0, key=PRIVATE, kid=KID, **claims
):  # noqa: ANN001, ANN003
    payload = {
        "iat": int(clock().timestamp()) - age,
        "request_body_sha256": hashlib.sha256(body).hexdigest(),
        **claims,
    }
    return jwt.encode(payload, key, algorithm="ES256", headers={"kid": kid})


class Keys:
    def __init__(self, jwk=JWK, error: PlaidError | None = None) -> None:  # noqa: ANN001
        self.jwk = jwk
        self.error = error
        self.fetched: list[str] = []

    def __call__(self, kid: str) -> dict:
        self.fetched.append(kid)
        if self.error is not None:
            raise self.error
        if kid != self.jwk["kid"]:
            raise PlaidError(
                error_type="INVALID_INPUT",
                error_code="INVALID_WEBHOOK_VERIFICATION_KEY_ID",
                status=400,
            )
        return dict(self.jwk)


@pytest.fixture
def clock():
    return Clock()


def test_valid_webhook_verifies_and_a_replay_is_reported_as_duplicate(clock):
    keys = Keys()
    verifier = WebhookVerifier(keys, clock=clock)
    token = sign(clock)
    first = verifier.verify(token, BODY)
    assert (
        first.payload["webhook_code"] == "SYNC_UPDATES_AVAILABLE" and not first.duplicate
    )
    assert verifier.verify(token, BODY).duplicate
    # A fresh delivery of the same event is a different token: not a duplicate.
    clock.advance(seconds=30)
    assert not verifier.verify(sign(clock), BODY).duplicate
    assert keys.fetched == [KID]  # cached


def test_cached_key_is_refetched_after_its_ttl(clock):
    keys = Keys()
    verifier = WebhookVerifier(keys, clock=clock)
    verifier.verify(sign(clock), BODY)
    clock.advance(hours=2)
    verifier.verify(sign(clock), BODY)
    assert keys.fetched == [KID, KID]


def reject(verifier: WebhookVerifier, token, body: bytes = BODY) -> None:  # noqa: ANN001
    with pytest.raises(WebhookRejected) as caught:
        verifier.verify(token, body)
    assert str(caught.value) == ""  # nothing about why


def test_missing_or_garbage_header_is_rejected(clock):
    verifier = WebhookVerifier(Keys(), clock=clock)
    reject(verifier, None)
    reject(verifier, "")
    reject(verifier, "not-a-jwt")
    reject(verifier, "x" * 5000)


@pytest.mark.parametrize("alg", ["HS256", "none", "RS256", "ES384"])
def test_any_algorithm_but_es256_is_rejected_before_key_lookup(clock, alg):
    keys = Keys()
    verifier = WebhookVerifier(keys, clock=clock)
    header = {"alg": alg, "kid": KID, "typ": "JWT"}
    body = {
        "iat": int(clock().timestamp()),
        "request_body_sha256": hashlib.sha256(BODY).hexdigest(),
    }
    segments = [
        jwt.utils.base64url_encode(json.dumps(part).encode()).decode()
        for part in (header, body)
    ]
    reject(verifier, ".".join([*segments, "c2ln"]))
    assert keys.fetched == []


def test_old_and_future_iat_are_rejected(clock):
    verifier = WebhookVerifier(Keys(), clock=clock)
    reject(verifier, sign(clock, age=301))
    reject(verifier, sign(clock, age=-301))
    assert not verifier.verify(sign(clock, age=290), BODY).duplicate


def test_replay_after_the_window_is_rejected(clock):
    verifier = WebhookVerifier(Keys(), clock=clock)
    token = sign(clock)
    verifier.verify(token, BODY)
    clock.advance(minutes=6)
    reject(verifier, token)


def test_tampered_body_is_rejected(clock):
    verifier = WebhookVerifier(Keys(), clock=clock)
    token = sign(clock)
    reject(verifier, token, BODY.replace(b"SYNC_UPDATES_AVAILABLE", b"DEFAULT_UPDATE"))
    reject(verifier, token, BODY + b" ")


def test_signature_from_another_key_is_rejected(clock):
    other, _ = es256_key()
    reject(WebhookVerifier(Keys(), clock=clock), sign(clock, key=other))


def test_unknown_kid_or_expired_key_is_rejected(clock):
    reject(WebhookVerifier(Keys(), clock=clock), sign(clock, kid="unknown"))
    expired = {**JWK, "expired_at": 1_700_000_100}
    reject(WebhookVerifier(Keys(expired), clock=clock), sign(clock))


def test_missing_body_hash_claim_is_rejected(clock):
    token = jwt.encode(
        {"iat": int(clock().timestamp())},
        PRIVATE,
        algorithm="ES256",
        headers={"kid": KID},
    )
    reject(WebhookVerifier(Keys(), clock=clock), token)


def test_key_endpoint_outage_is_retryable_not_a_rejection(clock):
    down = PlaidError(error_type="TRANSPORT", error_code="PROVIDER_UNREACHABLE")
    with pytest.raises(VerificationUnavailable):
        WebhookVerifier(Keys(error=down), clock=clock).verify(sign(clock), BODY)
