"""The hub's ``SourceAdapter`` for Plaid: provider-side revocation.

Disconnect calls ``/item/remove`` with the Item's access token, which ends
Plaid's access and billing for the Item. Transient failures (unreachable,
429 / ``RATE_LIMIT_EXCEEDED``, 5xx) are retried a bounded number of times with
growing backoff, because a failed revocation leaves a live grant the person
believes is gone. An Item Plaid no longer knows is already revoked, so that
answer counts as success, reported as ``already_revoked``; any other failure
raises and the hub reports it
while still deleting the local credential.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from argus.domain.ingestion.connections import SourceConnection
from argus.domain.ingestion.plaid.client import PlaidClient, PlaidError, is_transient

_ALREADY_GONE = frozenset({"ITEM_NOT_FOUND", "INVALID_ACCESS_TOKEN"})
ATTEMPTS = 3
BACKOFF_SECONDS = (0.5, 2.0)


class PlaidRevocationUnavailable(RuntimeError):
    pass


class PlaidAdapter:
    source = "plaid"

    def __init__(
        self, client: PlaidClient, *, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self.client = client
        self.sleep = sleep

    def revoke(self, connection: SourceConnection, credential: str | None) -> str | None:
        if not credential:
            raise PlaidRevocationUnavailable("no readable access token")
        for attempt in range(ATTEMPTS):
            try:
                self.client.item_remove(credential)
                return None
            except PlaidError as exc:
                if exc.error_code in _ALREADY_GONE:
                    return "already_revoked"
                if not is_transient(exc) or attempt == ATTEMPTS - 1:
                    raise PlaidRevocationUnavailable(exc.error_code) from None
                self.sleep(BACKOFF_SECONDS[attempt])
