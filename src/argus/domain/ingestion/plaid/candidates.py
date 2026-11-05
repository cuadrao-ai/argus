"""One complete ``/transactions/sync`` update as a candidate batch.

Malformed provider data is contained per item: a row or an account the
contract refuses is dropped and counted (``skipped``, ``skipped_accounts``),
never failing the batch. Accounts missing from the pages are looked up once
with ``/accounts/get``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from loguru import logger

from argus.domain.ingestion.connections import SourceConnection
from argus.domain.ingestion.contract import ImportCandidate
from argus.domain.ingestion.plaid import mapping
from argus.domain.ingestion.plaid.client import PlaidClient

_MALFORMED = (ValueError, TypeError, AttributeError)


def build_candidates(
    client: PlaidClient,
    current: SourceConnection,
    token: str,
    payloads: Sequence[dict[str, Any]],
    *,
    now: datetime,
) -> tuple[list[ImportCandidate], dict[str, int]]:
    counts = dict.fromkeys(
        ("added", "modified", "removed", "skipped", "skipped_accounts"), 0
    )
    counts.update(pending=0, posted=0, replacing=0)
    raw_accounts = [a for p in payloads for a in _items(p, "accounts")]
    hints, dropped = mapping.account_hints(raw_accounts, institution=current.label)
    counts["skipped_accounts"] += dropped
    groups = {k: [r for p in payloads for r in _items(p, k)] for k in _LISTS}
    for name, group in groups.items():
        kept = [r for r in group if isinstance(r, dict)]
        counts["skipped"] += len(group) - len(kept)
        groups[name] = kept
    if any(
        r.get("account_id") not in hints for r in groups["added"] + groups["modified"]
    ):
        extra, dropped = mapping.account_hints(
            client.accounts_get(token), institution=current.label
        )
        counts["skipped_accounts"] += dropped
        hints = {**extra, **hints}
    candidates: list[ImportCandidate] = []
    for name in ("added", "modified"):
        for row in groups[name]:
            try:
                candidate = mapping.transaction_candidate(
                    row, connection_id=current.id, accounts=hints, observed_at=now
                )
            except _MALFORMED as exc:
                counts["skipped"] += 1
                logger.warning(
                    "Skipped a Plaid row the contract refuses",
                    failure_mode=type(exc).__name__,
                )
                continue
            candidates.append(candidate)
            counts[name] += 1
            counts[candidate.status] += 1
            counts["replacing"] += candidate.source.replaces_external_id is not None
    for row in groups["removed"]:
        try:
            candidates.append(
                mapping.removed_candidate(row, connection_id=current.id, observed_at=now)
            )
            counts["removed"] += 1
        except _MALFORMED:
            counts["skipped"] += 1
    if counts["skipped_accounts"]:
        logger.warning(
            "Dropped Plaid accounts the contract refuses",
            skipped_accounts=counts["skipped_accounts"],
        )
    return candidates, counts


def _items(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


_LISTS = ("added", "modified", "removed")
