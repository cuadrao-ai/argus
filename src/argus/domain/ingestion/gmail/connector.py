"""One Gmail connector per process: the pieces wired to the shared hub."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

import httpx
from loguru import logger

from argus.domain.ingestion.connections import (
    LIVE,
    ConnectionNotFound,
    SourceConnection,
)
from argus.domain.ingestion.gmail import failures
from argus.domain.ingestion.gmail.adapter import GmailAdapter
from argus.domain.ingestion.gmail.client import GmailClient, GmailError
from argus.domain.ingestion.gmail.config import GmailConfig
from argus.domain.ingestion.gmail.extract import (
    EmailExtractor,
    UnreviewedEmailExtractor,
)
from argus.domain.ingestion.gmail.oauth import GmailOAuth
from argus.domain.ingestion.gmail.senders import (
    SenderRepository,
    SenderRule,
    normalize_senders,
)
from argus.domain.ingestion.gmail.state import (
    InMemoryStateLedger,
    OAuthStates,
    StateLedger,
)
from argus.domain.ingestion.gmail.suggestions import SenderSuggestion, suggest_senders
from argus.domain.ingestion.gmail.sync import GmailSync, SyncOutcome
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import PERSONAL


class ConnectionDisconnected(RuntimeError):
    pass


class GmailConnector:
    def __init__(
        self,
        hub: IngestionHub,
        config: GmailConfig,
        *,
        senders: SenderRepository,
        ledger: StateLedger | None = None,
        extractor: EmailExtractor | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if hub.box is None:
            raise ValueError("Gmail needs credential sealing")
        self.hub = hub
        self.config = config
        self.senders = senders
        self.client = GmailClient(config, transport=transport, sleep=sleep)
        self.adapter = GmailAdapter(self.client, senders)
        self.oauth = GmailOAuth(
            hub,
            self.client,
            config,
            OAuthStates(hub.box, ledger or InMemoryStateLedger(), hub.clock),
            senders,
        )
        self.syncer = GmailSync(
            hub,
            self.client,
            senders,
            extractor or UnreviewedEmailExtractor(),
            lookback_days=config.lookback_days,
        )

    def close(self) -> None:
        self.client.close()

    def connection(self, *, user_id: str, connection_id: str) -> SourceConnection:
        row = self.hub.connections.get(
            user_id=user_id, connection_id=connection_id, scope=PERSONAL
        )
        if row.source != "gmail":
            raise ConnectionNotFound()
        return row

    def live_connection(self, *, user_id: str, connection_id: str) -> SourceConnection:
        row = self.connection(user_id=user_id, connection_id=connection_id)
        if row.status not in LIVE:
            raise ConnectionDisconnected()
        return row

    def sync(self, connection: SourceConnection) -> SyncOutcome:
        outcome = self.syncer.sync(connection)
        logger.info(
            "Gmail sync finished",
            outcome=outcome.status,
            mode=outcome.mode,
            messages=outcome.messages,
            candidates=outcome.candidates,
            skipped=outcome.skipped,
            attachments=outcome.attachments,
        )
        return outcome

    def list_senders(self, *, user_id: str, connection_id: str) -> list[SenderRule]:
        row = self.connection(user_id=user_id, connection_id=connection_id)
        return self.senders.list(connection_id=row.id)

    def replace_senders(
        self, *, user_id: str, connection_id: str, senders: list[str], now: datetime
    ) -> list[SenderRule]:
        values = normalize_senders(senders)
        row = self.live_connection(user_id=user_id, connection_id=connection_id)
        return self.senders.replace(
            user_id=user_id, connection_id=row.id, senders=values, now=now
        )

    def suggestions(self, *, user_id: str, connection_id: str) -> list[SenderSuggestion]:
        row = self.live_connection(user_id=user_id, connection_id=connection_id)
        rules = self.senders.list(connection_id=row.id)
        try:
            refresh = self.hub.credential(row)
        except Exception:
            refresh = None
        if not refresh:
            raise GmailError(status=None, reason="credential_unavailable")
        try:
            access = self.client.refresh(refresh)
            return suggest_senders(self.client, access, rules)
        except GmailError as exc:
            failure = failures.meaning(exc)
            if failure.status == "needs_reauth":
                self.hub.connections.record_failure(
                    connection_id=row.id,
                    code=failure.code,
                    status=failure.status,
                    now=self.hub.clock(),
                )
            raise
