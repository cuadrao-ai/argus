"""Drive the Plaid connector through the live Plaid Sandbox, end to end.

Uses the production client, link, sync, webhook-key and revoke code with an
in-memory connection repository and a recording candidate sink. Sandbox-only
helpers (``/sandbox/public_token/create``, ``/transactions/refresh``,
``/sandbox/item/reset_login``) are called here, never from the connector.

Credentials come from the one seam (``PLAID_CLIENT_ID``/``PLAID_SECRET``), or,
where an egress proxy injects them, from the explicit sandbox-only opt-in
``PLAID_CREDENTIALS_INJECTED=true``. The summary records counts, statuses and
Plaid error codes only: no tokens, Item ids, transaction ids or amounts.

    PLAID_ENV=sandbox PLAID_CREDENTIALS_INJECTED=true \\
        python scripts/ingestion/plaid_sandbox_lifecycle.py
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.plaid.client import PlaidError
from argus.domain.ingestion.plaid.config import plaid_config_from_env
from argus.domain.ingestion.plaid.connector import PlaidConnector
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.sink import SubmitResult
from loguru import logger

OUT = Path("docs/reports/evidence/ingestion-plaid/sandbox-lifecycle.json")
INSTITUTION = "ins_109508"  # First Platypus Bank (non-OAuth sandbox institution)
TEST_USER = "user_transactions_dynamic"
USER_ID = "00000000-0000-4000-8000-0000000000aa"
MAX_READY_POLLS = 8
MAX_REFRESH_POLLS = 8
REFRESH_AGAIN_AT = 4
POLL_SECONDS = 8


class Sink:
    """Records candidates by key, like reconciliation's idempotent store."""

    def __init__(self) -> None:
        self.evidence: dict[tuple[str, str, str], ImportCandidate] = {}
        self.history: list[ImportCandidate] = []

    def submit(
        self, *, user_id: str, connection_id: str, candidates: Sequence[ImportCandidate]
    ) -> SubmitResult:
        recorded = unchanged = withdrawn = 0
        for c in candidates:
            known = self.evidence.get(c.key)
            if c.status == "removed":
                withdrawn += known is not None
            elif known is not None and known.fingerprint() == c.fingerprint():
                unchanged += 1
            else:
                recorded += 1
            self.evidence[c.key] = c
            self.history.append(c)
        return SubmitResult(recorded, unchanged, withdrawn)

    def forget_connection(self, *, user_id: str, connection_id: str) -> int:
        return 0


class Calls:
    """Counts provider calls by path (the transport is the real network)."""

    def __init__(self, connector: PlaidConnector) -> None:
        self.paths: Counter[str] = Counter()
        original = connector.client.post

        def counted(path: str, body: dict[str, Any]) -> dict[str, Any]:
            self.paths[path] += 1
            return original(path, body)

        connector.client.post = counted  # type: ignore[method-assign]


def _outcome(outcome) -> dict[str, Any]:  # noqa: ANN001
    return {
        k: getattr(outcome, k)
        for k in (
            "status", "added", "modified", "removed", "pending", "posted",
            "replacing", "skipped", "skipped_accounts", "pages", "restarts", "error_code",
        )
    }  # fmt: skip


def run(page_size: int) -> dict[str, Any]:
    config = plaid_config_from_env()
    if config.environment != "sandbox" or not config.configured:
        raise SystemExit("Sandbox credentials are not configured (see module doc).")
    hub = IngestionHub(
        InMemoryConnectionRepository(),
        box=SecretBox(os.urandom(32)),
        sink=Sink(),
        clock=lambda: datetime.now(timezone.utc),
    )
    connector = PlaidConnector(hub, config)
    hub.register(connector.adapter)
    calls = Calls(connector)
    connector.syncer.page_size = page_size
    sink: Sink = hub.sink  # type: ignore[assignment]
    summary: dict[str, Any] = {
        "environment": config.environment,
        "institution": INSTITUTION,
        "test_user": TEST_USER,
        "page_size": page_size,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    link = connector.link.link_token(user_id=USER_ID, language="en")
    summary["link_token_created"] = link.link_token.startswith("link-sandbox-")
    public = connector.client.post(
        "/sandbox/public_token/create",
        {
            "institution_id": INSTITUTION,
            "initial_products": ["transactions"],
            "options": {"override_username": TEST_USER, "override_password": "pass_good"},
        },
    )["public_token"]
    first = connector.link.exchange(user_id=USER_ID, public_token=public)
    again = connector.link.exchange(user_id=USER_ID, public_token=public)
    row = first.connection
    summary["exchange"] = {
        "created": first.created,
        "retry_created": again.created,
        "retry_same_connection": again.connection.id == row.id,
        "connections": len(hub.list(user_id=USER_ID)),
        "label": row.label,
        "access_token_sealed": row.secret is not None,
    }

    polls = 0
    initial = connector.sync(row)
    while initial.status == "not_ready" and polls < MAX_READY_POLLS:
        polls += 1
        time.sleep(POLL_SECONDS)
        initial = connector.sync(row)
    row = hub.connections.get(user_id=USER_ID, connection_id=row.id)
    summary["initial_sync"] = {**_outcome(initial), "not_ready_polls": polls}
    summary["after_initial"] = {
        "status": row.status,
        "cursor_saved": bool(row.cursor),
        "fresh": row.last_success_at is not None,
    }
    pending_before = {k[2] for k, c in sink.evidence.items() if c.status == "pending"}
    # Let the historical pull settle; a re-sync must then find nothing new.
    time.sleep(POLL_SECONDS)
    resync = connector.sync(hub.connections.get(user_id=USER_ID, connection_id=row.id))
    summary["resync"] = _outcome(resync)

    refreshes = 1
    connector.client.post("/transactions/refresh", {"access_token": _token(hub, row)})
    refresh = None
    for attempt in range(MAX_REFRESH_POLLS):
        time.sleep(POLL_SECONDS)
        if attempt == REFRESH_AGAIN_AT:
            refreshes += 1
            connector.client.post(
                "/transactions/refresh", {"access_token": _token(hub, row)}
            )
        refresh = connector.sync(
            hub.connections.get(user_id=USER_ID, connection_id=row.id)
        )
        if refresh.added or refresh.modified or refresh.removed:
            break
    posted_now = [
        c
        for c in sink.evidence.values()
        if c.status == "posted" and c.source.replaces_external_id in pending_before
    ]
    withdrawn = [
        k
        for k in pending_before
        if sink.evidence[("plaid", row.id, k)].status == "removed"
    ]
    summary["pending_to_posted"] = {
        "refresh_sync": _outcome(refresh) if refresh else None,
        "refresh_polls": attempt + 1,
        "refresh_calls": refreshes,
        "pending_before_refresh": len(pending_before),
        "posted_rows_naming_an_earlier_pending_row": len(posted_now),
        "earlier_pending_rows_now_removed": len(withdrawn),
        "posted_dates_split": sum(1 for c in posted_now if c.posted_on and c.occurred_on),
    }
    evidence = Counter(c.status for c in sink.evidence.values())
    summary["evidence_by_status"] = dict(evidence)
    summary["currency_missing"] = sum(
        1 for c in sink.evidence.values() if c.currency is None and c.status != "removed"
    )

    connector.client.post("/sandbox/item/reset_login", {"access_token": _token(hub, row)})
    current = hub.connections.get(user_id=USER_ID, connection_id=row.id)
    fresh_before = current.last_success_at
    broken = connector.sync(current)
    current = hub.connections.get(user_id=USER_ID, connection_id=row.id)
    summary["reset_login"] = {
        "sync": _outcome(broken),
        "status": current.status,
        "last_error_code": current.last_error_code,
        "freshness_kept": current.last_success_at == fresh_before,
        "cursor_kept": bool(current.cursor),
    }
    update = connector.link.update_link_token(
        user_id=USER_ID, connection_id=row.id, language="en"
    )
    still = connector.link.reconnected(user_id=USER_ID, connection_id=row.id)
    summary["reconnect"] = {
        "update_mode_link_token_created": update.link_token.startswith("link-sandbox-"),
        "status_after_check_without_link_ui": still.status,
        "last_error_code": still.last_error_code,
        "link_update_mode_ui": "not exercised (needs Plaid Link in a browser)",
    }

    try:
        connector.client.webhook_verification_key("00000000-0000-0000-0000-000000000000")
        key_probe = "unexpected_success"
    except PlaidError as exc:
        key_probe = exc.error_code
    summary["webhook_key_unknown_kid"] = key_probe

    token = _token(hub, row)
    outcome = hub.disconnect(user_id=USER_ID, connection_id=row.id)
    try:
        connector.client.item_get(token)
        after_remove = "item_still_present"
    except PlaidError as exc:
        after_remove = exc.error_code
    del token
    summary["disconnect"] = {
        "provider_revocation": outcome.provider_revocation,
        "status": outcome.connection.status,
        "credential_deleted": outcome.connection.secret is None,
        "item_get_after_remove": after_remove,
    }
    summary["provider_calls"] = dict(sorted(calls.paths.items()))
    summary["provider_calls_total"] = sum(calls.paths.values())
    connector.close()
    return summary


def _token(hub: IngestionHub, row) -> str:  # noqa: ANN001
    fresh = hub.connections.get(user_id=row.user_id, connection_id=row.id)
    token = hub.credential(fresh)
    assert token
    return token


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    summary = run(args.page_size)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    logger.info("Plaid sandbox lifecycle written", path=str(args.out))


if __name__ == "__main__":
    main()
