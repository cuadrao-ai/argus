"""Unverifiable webhooks must never drive unbounded Plaid key fetches."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from argus.domain.ingestion.plaid import verification
from argus.domain.ingestion.plaid.client import PlaidError
from argus.domain.ingestion.plaid.verification import (
    VerificationUnavailable,
    WebhookRejected,
    WebhookVerifier,
)

from tests.ingestion.plaid_fakes import Clock
from tests.ingestion.test_plaid_verification import BODY, KID, Keys, sign


@pytest.fixture
def clock():
    return Clock()


def test_unknown_kid_is_remembered_and_not_refetched(clock):
    keys = Keys()
    verifier = WebhookVerifier(keys, clock=clock)
    for _ in range(5):
        with pytest.raises(WebhookRejected):
            verifier.verify(sign(clock, kid="forged"), BODY)
    assert keys.fetched == ["forged"]
    clock.advance(minutes=10)
    with pytest.raises(WebhookRejected):
        verifier.verify(sign(clock, kid="forged"), BODY)
    assert keys.fetched == ["forged", "forged"]


def test_cheap_claim_checks_run_before_any_key_fetch(clock):
    keys = Keys()
    verifier = WebhookVerifier(keys, clock=clock)
    with pytest.raises(WebhookRejected):
        verifier.verify(sign(clock, kid="stale", age=900), BODY)
    with pytest.raises(WebhookRejected):
        verifier.verify(sign(clock, kid="tampered"), BODY + b"x")
    assert keys.fetched == []


def test_concurrent_requests_for_a_new_kid_fetch_it_once(clock):
    gate = threading.Event()

    class SlowKeys(Keys):
        def __call__(self, kid):  # noqa: ANN001
            gate.wait(timeout=5)
            time.sleep(0.05)
            return super().__call__(kid)

    keys = SlowKeys()
    verifier = WebhookVerifier(keys, clock=clock)
    tokens = [sign(clock, nonce=i) for i in range(6)]
    with ThreadPoolExecutor(6) as pool:
        futures = [pool.submit(verifier.verify, token, BODY) for token in tokens]
        gate.set()
        results = [f.result(timeout=10) for f in futures]
    assert all(not r.duplicate for r in results)
    assert keys.fetched == [KID]


def test_process_wide_fetch_budget_turns_floods_into_retryable_refusals(clock):
    keys = Keys()
    verifier = WebhookVerifier(keys, clock=clock)
    budget = verification.FETCH_BUDGET
    for i in range(budget):
        with pytest.raises(WebhookRejected):
            verifier.verify(sign(clock, kid=f"forged-{i}"), BODY)
    with pytest.raises(VerificationUnavailable):
        verifier.verify(sign(clock, kid="forged-over-budget"), BODY)
    assert len(keys.fetched) == budget
    clock.advance(seconds=61)
    # A new window allows the real key again.
    assert not verifier.verify(sign(clock), BODY).duplicate


@pytest.mark.parametrize(
    "error",
    [
        PlaidError(error_type="RATE_LIMIT_EXCEEDED", error_code="RATE_LIMIT", status=429),
        PlaidError(error_type="API_ERROR", error_code="HTTP_429", status=429),
        PlaidError(
            error_type="API_ERROR", error_code="INTERNAL_SERVER_ERROR", status=500
        ),
    ],
)
def test_rate_limits_and_outages_are_retryable_and_not_remembered(clock, error):
    keys = Keys(error=error)
    verifier = WebhookVerifier(keys, clock=clock)
    with pytest.raises(VerificationUnavailable):
        verifier.verify(sign(clock), BODY)
    keys.error = None
    assert not verifier.verify(sign(clock, nonce=1), BODY).duplicate
    assert keys.fetched == [KID, KID]


def test_key_cache_ttl_is_short():
    assert verification.KEY_TTL.total_seconds() <= 15 * 60
    assert verification.UNKNOWN_KID_TTL.total_seconds() >= 60
