"""Re-check disconnect (``/item/remove`` with bounded retries) on the Sandbox.

A minimal live run for the revocation path alone: create a Sandbox Item,
exchange it through the connector, disconnect through the hub and confirm
Plaid no longer knows the Item. Records statuses, Plaid codes and call counts
only (no tokens or ids). Credentials as in ``plaid_sandbox_lifecycle.py``.

    PLAID_ENV=sandbox PLAID_CREDENTIALS_INJECTED=true \\
        python scripts/ingestion/plaid_sandbox_disconnect.py
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.plaid.client import PlaidError
from argus.domain.ingestion.plaid.config import plaid_config_from_env
from argus.domain.ingestion.plaid.connector import PlaidConnector
from argus.domain.ingestion.secrets import SecretBox
from loguru import logger

OUT = Path("docs/reports/evidence/ingestion-plaid/sandbox-disconnect.json")
USER_ID = "00000000-0000-4000-8000-0000000000ab"


def run() -> dict[str, Any]:
    config = plaid_config_from_env()
    if config.environment != "sandbox" or not config.configured:
        raise SystemExit("Sandbox credentials are not configured (see module doc).")
    hub = IngestionHub(
        InMemoryConnectionRepository(),
        box=SecretBox(os.urandom(32)),
        sink=None,
        clock=lambda: datetime.now(timezone.utc),
    )
    connector = PlaidConnector(hub, config)
    hub.register(connector.adapter)
    paths: Counter[str] = Counter()
    original = connector.client.post

    def counted(path: str, body: dict[str, Any]) -> dict[str, Any]:
        paths[path] += 1
        return original(path, body)

    connector.client.post = counted  # type: ignore[method-assign]
    public = connector.client.post(
        "/sandbox/public_token/create",
        {"institution_id": "ins_109508", "initial_products": ["transactions"]},
    )["public_token"]
    row = connector.link.exchange(user_id=USER_ID, public_token=public).connection
    token = hub.credential(row)
    assert token
    outcome = hub.disconnect(user_id=USER_ID, connection_id=row.id)
    try:
        connector.client.item_get(token)
        after = "item_still_present"
    except PlaidError as exc:
        after = exc.error_code
    del token
    connector.close()
    return {
        "environment": config.environment,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider_revocation": outcome.provider_revocation,
        "status": outcome.connection.status,
        "credential_deleted": outcome.connection.secret is None,
        "item_get_after_remove": after,
        "item_remove_attempts": paths["/item/remove"],
        "provider_calls": dict(sorted(paths.items())),
        "provider_calls_total": sum(paths.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    summary = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    logger.info("Plaid sandbox disconnect re-check written", path=str(args.out))


if __name__ == "__main__":
    main()
