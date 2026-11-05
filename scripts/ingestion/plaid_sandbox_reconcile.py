"""Live Plaid Sandbox through reconciliation into one reviewed canonical record.

Drives a real Sandbox Item through the Plaid connector into the real
``ReconciliationService`` (in-memory stores, synthetic person), then plays the
person's review: confirm the account once, preview and accept one purchase,
re-sync, and disconnect. Writes counts and states only (no tokens, ids or
transaction text) to ``docs/reports/evidence/ingestion-reconciliation/``.

Sandbox only. Credentials come from ``PLAID_CLIENT_ID``/``PLAID_SECRET`` or,
in an environment whose egress proxy injects them, ``PLAID_CREDENTIALS_INJECTED=true``.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.plaid.config import plaid_config_from_env
from argus.domain.ingestion.plaid.connector import PlaidConnector
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store import InMemoryImportStore
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.repository import InMemoryFinancialAccountRepository
from argus.domain.recording.schemas import CreateFinancialAccountRequest
from argus.domain.recording.service import FinancialAccountService
from loguru import logger

INSTITUTION = "ins_109508"
TEST_USER = "user_transactions_dynamic"
USER = str(uuid4())
OUT = (
    Path(__file__).resolve().parents[2]
    / "docs/reports/evidence/ingestion-reconciliation/plaid-sandbox-reconcile.json"
)
MAX_READY_POLLS = 6
POLL_SECONDS = 10


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def run() -> dict[str, Any]:
    config = plaid_config_from_env()
    if config.environment != "sandbox" or not config.configured:
        raise SystemExit("Sandbox credentials are not configured (see module doc).")
    accounts = FinancialAccountService(InMemoryFinancialAccountRepository(_clock), _clock)
    money = MoneyService(accounts)
    recon = ReconciliationService(InMemoryImportStore(), money, _clock)
    hub = IngestionHub(
        InMemoryConnectionRepository(),
        box=SecretBox(os.urandom(32)),
        sink=recon,
        clock=_clock,
    )
    connector = PlaidConnector(hub, config)
    hub.register(connector.adapter)
    summary: dict[str, Any] = {
        "environment": config.environment,
        "institution": INSTITUTION,
        "test_user": TEST_USER,
        "run_at": _clock().isoformat(timespec="seconds"),
    }

    public = connector.client.post(
        "/sandbox/public_token/create",
        {
            "institution_id": INSTITUTION,
            "initial_products": ["transactions"],
            "options": {"override_username": TEST_USER, "override_password": "pass_good"},
        },
    )["public_token"]
    row = connector.link.exchange(user_id=USER, public_token=public).connection
    outcome = connector.sync(row)
    polls = 0
    while outcome.status == "not_ready" and polls < MAX_READY_POLLS:
        polls += 1
        time.sleep(POLL_SECONDS)
        outcome = connector.sync(hub.connections.get(user_id=USER, connection_id=row.id))
    events = recon.list(user_id=USER, states=("open",))
    summary["after_sync"] = {
        "sync_status": outcome.status,
        "not_ready_polls": polls,
        "open_events": len(events),
        "observations": sum(len(e["observations"]) for e in events),
        "by_status": dict(Counter(e["observations"][0]["status"] for e in events)),
        "drafts_affect_ledger": bool(money.purchases(user_id=USER)["items"]),
        "unresolved_account": sum("account_id" in e["unresolved"] for e in events),
    }

    today = date.today().isoformat()
    target = next(
        e
        for e in events
        if e["observations"][0]["status"] == "posted"
        and e["facts"]["direction"] == "outflow"
        and e["facts"]["occurred_on"] <= today
    )
    account_type = {"credit": "credit_card"}.get(_type_hint(recon, target), "checking")
    account_id = accounts.create(
        user_id=USER,
        idempotency_key="sandbox-account",
        request=CreateFinancialAccountRequest(
            type=account_type, currency=target["facts"]["currency"], nickname="Sandbox"
        ),
    ).stored.account.id
    resolved = recon.resolve(
        user_id=USER,
        event_id=target["id"],
        version=target["version"],
        changes={"account_id": account_id},
    )
    preview = recon.preview(user_id=USER, event_id=target["id"])["preview"]
    request = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )
    accepted = recon.accept(
        user_id=USER,
        event_id=target["id"],
        idempotency_key="sandbox-accept",
        version=resolved["version"],
        request=request,
    )
    replay = recon.accept(
        user_id=USER,
        event_id=target["id"],
        idempotency_key="sandbox-accept",
        version=resolved["version"],
        request=request,
    )
    same_account = [
        e
        for e in recon.list(user_id=USER, states=("open",))
        if e["facts"]["account_id"] == account_id
    ]
    summary["review"] = {
        "accepted_kind": accepted["activity"]["kind"],
        "ledger_activities": len(money.purchases(user_id=USER)["items"]),
        "replay_same_activity": replay["activity"]["activity_id"]
        == accepted["activity"]["activity_id"]
        and replay["replayed"],
        "account_link_reused_by_other_drafts": len(same_account),
    }

    resync = connector.sync(hub.connections.get(user_id=USER, connection_id=row.id))
    after = recon.list(user_id=USER, states=("open", "accepted"))
    summary["resync"] = {
        "status": resync.status,
        "events_before": len(events),
        "events_after": len(after),
        "ledger_activities": len(money.purchases(user_id=USER)["items"]),
    }

    ended = hub.disconnect(user_id=USER, connection_id=row.id)
    kept = recon.list(user_id=USER, states=("accepted",))
    summary["disconnect"] = {
        "provider_revocation": ended.provider_revocation,
        "unreviewed_removed": ended.unreviewed_removed,
        "open_after": len(recon.list(user_id=USER, states=("open",))),
        "accepted_kept": len(kept),
        "accepted_redacted": all(o["redacted"] for e in kept for o in e["observations"]),
        "ledger_activities": len(money.purchases(user_id=USER)["items"]),
    }
    return summary


def _type_hint(recon: ReconciliationService, event: dict[str, Any]) -> str:
    with recon.store.transaction(USER) as tx:
        [observation] = tx.observations(event["id"])[:1]
        return (observation.candidate.get("account") or {}).get("type_hint", "unknown")


def main() -> None:
    summary = run()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    logger.info("Sandbox reconciliation evidence written", path=str(OUT))


if __name__ == "__main__":
    main()
