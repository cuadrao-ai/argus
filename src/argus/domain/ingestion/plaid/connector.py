"""One Plaid connector per process: the pieces wired to the shared hub."""

from __future__ import annotations

import httpx
from loguru import logger

from argus.domain.ingestion.connections import ConnectionNotFound, SourceConnection
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.plaid.adapter import PlaidAdapter
from argus.domain.ingestion.plaid.client import PlaidClient
from argus.domain.ingestion.plaid.config import PlaidConfig
from argus.domain.ingestion.plaid.link import PlaidLink
from argus.domain.ingestion.plaid.sync import PlaidSync, SyncOutcome
from argus.domain.ingestion.plaid.verification import WebhookVerifier
from argus.domain.ingestion.plaid.webhooks import PlaidWebhooks, WebhookPlan
from argus.domain.owner_scope import PERSONAL


class PlaidConnector:
    def __init__(
        self,
        hub: IngestionHub,
        config: PlaidConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.hub = hub
        self.config = config
        self.client = PlaidClient(config, transport=transport)
        self.adapter = PlaidAdapter(self.client)
        self.link = PlaidLink(hub, self.client)
        self.syncer = PlaidSync(hub, self.client)
        self.webhooks = PlaidWebhooks(hub, environment=config.environment)
        self.verifier = WebhookVerifier(
            self.client.webhook_verification_key, clock=hub.clock
        )

    def close(self) -> None:
        self.client.close()

    def connection(self, *, user_id: str, connection_id: str) -> SourceConnection:
        row = self.hub.connections.get(
            user_id=user_id, connection_id=connection_id, scope=PERSONAL
        )
        if row.source != "plaid":
            raise ConnectionNotFound()
        return row

    def sync(self, connection: SourceConnection) -> SyncOutcome:
        outcome = self.syncer.sync(connection)
        logger.info(
            "Plaid sync finished",
            outcome=outcome.status,
            added=outcome.added,
            modified=outcome.modified,
            removed=outcome.removed,
            pages=outcome.pages,
            restarts=outcome.restarts,
        )
        return outcome

    def run(self, plan: WebhookPlan) -> list[SyncOutcome]:
        """Follow-up work of a webhook; bounded by the sync's own limits."""

        outcomes: list[SyncOutcome] = []
        for row in plan.connections:
            try:
                if plan.effect == "repair" and row.status == "needs_reauth":
                    row = self.link.reconnected(user_id=row.user_id, connection_id=row.id)
                    if row.status != "active":
                        continue
                if plan.effect in ("sync", "repair"):
                    outcomes.append(self.sync(row))
            except Exception as exc:
                logger.warning(
                    "Plaid webhook follow-up failed",
                    effect=plan.effect,
                    failure_mode=type(exc).__name__,
                )
        return outcomes
