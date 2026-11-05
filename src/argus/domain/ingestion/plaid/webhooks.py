"""What a verified Plaid webhook does to the connections of its Item.

Webhooks name an Item, not a person, so the Item's live connections are
found by ``external_ref``. Status changes are recorded immediately; syncs and
health checks are returned as follow-up work so the HTTP response is not held
on provider calls. Repeated deliveries are harmless: status writes are
idempotent and syncs are serialized by the connection lease and cursor CAS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from argus.domain.ingestion.connections import ConnectionNotFound, SourceConnection
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.plaid.failures import meaning

SYNC_CODES = frozenset(
    {
        "SYNC_UPDATES_AVAILABLE",
        "DEFAULT_UPDATE",
        "INITIAL_UPDATE",
        "HISTORICAL_UPDATE",
        "TRANSACTIONS_REMOVED",
    }
)
# Item webhooks whose code is itself the condition the person must resolve.
ITEM_CONDITION_CODES = frozenset(
    {"PENDING_EXPIRATION", "PENDING_DISCONNECT", "USER_PERMISSION_REVOKED"}
)

WebhookEffect = Literal["sync", "status", "repair", "ignored"]


@dataclass(frozen=True)
class WebhookPlan:
    effect: WebhookEffect
    connections: tuple[SourceConnection, ...] = ()


class PlaidWebhooks:
    def __init__(self, hub: IngestionHub, *, environment: str) -> None:
        self.hub = hub
        self.environment = environment

    def plan(self, payload: dict[str, Any]) -> WebhookPlan:
        webhook_type = payload.get("webhook_type")
        code = payload.get("webhook_code")
        item_id = payload.get("item_id")
        environment = payload.get("environment")
        if not all(isinstance(v, str) for v in (webhook_type, code, item_id)):
            return WebhookPlan("ignored")
        if isinstance(environment, str) and environment != self.environment:
            return WebhookPlan("ignored")
        live = tuple(
            row
            for row in self.hub.connections.find_live(
                source="plaid", external_ref=item_id
            )
        )
        if not live:
            return WebhookPlan("ignored")
        if webhook_type == "TRANSACTIONS" and code in SYNC_CODES:
            return WebhookPlan("sync", live)
        if webhook_type != "ITEM":
            return WebhookPlan("ignored")
        if code == "LOGIN_REPAIRED":
            return WebhookPlan("repair", live)
        error_code = _condition(code, payload.get("error"))
        if error_code is None:
            return WebhookPlan("ignored")
        failure = meaning(error_code)
        for row in live:
            try:
                if failure.attention:
                    self.hub.connections.flag_attention(
                        connection_id=row.id, code=failure.code, now=self.hub.clock()
                    )
                    continue
                self.hub.connections.record_failure(
                    connection_id=row.id,
                    code=failure.code,
                    status=failure.status or row.status,
                    now=self.hub.clock(),
                )
            except ConnectionNotFound:
                continue
        return WebhookPlan("status", live)


def _condition(code: str, error: object) -> str | None:
    if code in ITEM_CONDITION_CODES:
        return code
    if code == "ERROR" and isinstance(error, dict):
        nested = error.get("error_code")
        if isinstance(nested, str) and nested:
            return nested
    return None
