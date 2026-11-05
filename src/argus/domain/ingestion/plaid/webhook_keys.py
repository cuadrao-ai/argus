"""Plaid webhook verification keys, fetched without amplification.

The webhook endpoint is public, so the ``kid`` in an unverified header is
attacker-chosen. Every path from a request to ``/webhook_verification_key/get``
is bounded:

- a known key is cached for ``KEY_TTL`` (short, so a rotated or expired key is
  noticed quickly);
- a kid Plaid does not know is remembered for ``UNKNOWN_KID_TTL`` and refused
  without another call;
- concurrent requests for one new kid share a single fetch (per-kid lock);
- at most ``FETCH_BUDGET`` fetches run per minute in the process; beyond that
  the request is answered as retryable (Plaid redelivers), never as a fetch.

A rate limit (429 / ``RATE_LIMIT_EXCEEDED``), a 5xx or an unreachable Plaid is
``VerificationUnavailable`` and is not remembered: the sender should retry.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from argus.domain.ingestion.plaid.client import PlaidError, is_transient

MAX_AGE = timedelta(minutes=5)
KEY_TTL = timedelta(minutes=10)
UNKNOWN_KID_TTL = timedelta(minutes=5)
FETCH_BUDGET = 10
FETCH_WINDOW = timedelta(minutes=1)
_MAX_CACHED_KEYS = 32
_MAX_UNKNOWN = 1024
_MAX_KID_LOCKS = 64


class WebhookRejected(Exception):
    """Not a verified Plaid webhook. Deliberately carries no reason."""


class VerificationUnavailable(Exception):
    """Plaid's key endpoint could not be used now; the sender should retry."""


def reject(reason: str) -> WebhookRejected:
    logger.info("Plaid webhook rejected", reason=reason)
    return WebhookRejected()


class KeyStore:
    def __init__(
        self,
        fetch_key: Callable[[str], dict[str, Any]],
        *,
        clock: Callable[[], datetime],
        key_ttl: timedelta = KEY_TTL,
    ) -> None:
        self._fetch_key = fetch_key
        self._clock = clock
        self._key_ttl = key_ttl
        self._keys: dict[str, tuple[dict[str, Any], datetime]] = {}
        self._unknown: dict[str, datetime] = {}
        self._fetches: deque[datetime] = deque()
        self._kid_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()

    def get(self, kid: str) -> dict[str, Any]:
        with self._lock:
            known = self._known(kid, self._clock())
            if known is not None:
                return known
            kid_lock = self._kid_lock(kid)
        with kid_lock:
            with self._lock:
                now = self._clock()
                known = self._known(kid, now)
                if known is not None:
                    return known
                self._spend(now)
            try:
                jwk = self._fetch_key(kid)
            except PlaidError as exc:
                if is_transient(exc):
                    logger.warning(
                        "Plaid webhook key unavailable", plaid_code=exc.error_code
                    )
                    raise VerificationUnavailable() from None
                with self._lock:
                    if len(self._unknown) >= _MAX_UNKNOWN:
                        self._unknown.pop(next(iter(self._unknown)))
                    self._unknown[kid] = self._clock() + UNKNOWN_KID_TTL
                raise reject("unknown_key") from None
            with self._lock:
                if len(self._keys) >= _MAX_CACHED_KEYS:
                    self._keys.pop(next(iter(self._keys)))
                self._keys[kid] = (jwk, self._clock() + self._key_ttl)
            return jwk

    def _known(self, kid: str, now: datetime) -> dict[str, Any] | None:
        """Cached key, or a refusal for a remembered unknown kid (lock held)."""

        cached = self._keys.get(kid)
        if cached is not None and cached[1] > now:
            return cached[0]
        until = self._unknown.get(kid)
        if until is not None:
            if until > now:
                raise reject("unknown_key")
            del self._unknown[kid]
        return None

    def _spend(self, now: datetime) -> None:
        """Take one fetch from the per-minute budget (lock held)."""

        while self._fetches and self._fetches[0] <= now - FETCH_WINDOW:
            self._fetches.popleft()
        if len(self._fetches) >= FETCH_BUDGET:
            logger.warning("Plaid webhook key fetch budget exhausted")
            raise VerificationUnavailable()
        self._fetches.append(now)

    def _kid_lock(self, kid: str) -> threading.Lock:
        lock = self._kid_locks.get(kid)
        if lock is None:
            if len(self._kid_locks) >= _MAX_KID_LOCKS:
                for other, candidate in list(self._kid_locks.items()):
                    if not candidate.locked():
                        del self._kid_locks[other]
            lock = self._kid_locks[kid] = threading.Lock()
        return lock
