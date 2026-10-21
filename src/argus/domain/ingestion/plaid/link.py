"""Plaid Link on the server: link tokens, public-token exchange, update mode.

The person's browser only ever sees a ``link_token`` and returns a
``public_token``. The ``access_token`` is sealed under the new connection's id
before the row exists and is never returned.

Exchange is safe to retry: Plaid returns the same Item for a repeated public
token, and a second link of an Item this person already has resolves to the
existing connection instead of creating a duplicate.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from loguru import logger

from argus.domain.ingestion.connections import (
    ConnectionNotFound,
    DuplicateConnection,
    SourceConnection,
)
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.plaid.client import PlaidClient, PlaidError
from argus.domain.ingestion.plaid.failures import meaning
from argus.domain.ingestion.secrets import SecretBoxUnavailable
from argus.domain.owner_scope import PERSONAL

LinkLanguage = Literal["en", "es"]


class PlaidItemOwnedElsewhere(RuntimeError):
    """The exchanged Item is already connected by a different person."""


class ConnectionNotReauthorizable(RuntimeError):
    """Update mode is only offered to a live Plaid connection that needs it."""


@dataclass
class _Stored:
    # A live connection already holds the exchanged Item: never remove it.
    held: bool = False


@dataclass(frozen=True)
class LinkToken:
    link_token: str
    expiration: datetime | None


@dataclass(frozen=True)
class ExchangeResult:
    connection: SourceConnection
    created: bool


def client_user_id(user_id: str) -> str:
    """Stable and opaque: Plaid never learns the Cuadrao user id."""

    return hashlib.sha256(f"cuadrao-plaid-user:{user_id}".encode()).hexdigest()


class PlaidLink:
    def __init__(self, hub: IngestionHub, client: PlaidClient) -> None:
        self.hub = hub
        self.client = client

    def link_token(self, *, user_id: str, language: LinkLanguage) -> LinkToken:
        payload = self.client.link_token_create(
            client_user_id=client_user_id(user_id), language=language
        )
        return _link_token(payload)

    def exchange(self, *, user_id: str, public_token: str) -> ExchangeResult:
        box = self.hub.box
        if box is None:
            raise SecretBoxUnavailable("credential sealing is not configured")
        access_token, item_id = self.client.exchange_public_token(public_token)
        stored = _Stored()
        try:
            return self._store(user_id, access_token, item_id, stored)
        except Exception:
            # Unless a live connection (this person's or someone else's)
            # already holds the Item, nothing stored the token: end the Item
            # rather than leave Plaid access (and billing) the person cannot
            # see or disconnect.
            if not stored.held:
                self._abandon(access_token)
            raise

    def _store(
        self, user_id: str, access_token: str, item_id: str, stored: _Stored
    ) -> ExchangeResult:
        box = self.hub.box
        assert box is not None
        live = self.hub.connections.find_live(source="plaid", external_ref=item_id)
        if live:
            stored.held = True
            mine = [row for row in live if row.user_id == user_id]
            if mine:
                return ExchangeResult(mine[0], created=False)
            # Never revoke here: removing the Item would end the other
            # person's connection too.
            raise PlaidItemOwnedElsewhere()
        connection_id = str(uuid.uuid4())
        sealed = box.seal(access_token, source="plaid", connection_id=connection_id)
        label = self._institution_label(access_token)
        try:
            row = self.hub.connections.create(
                user_id=user_id,
                source="plaid",
                external_ref=item_id,
                label=label,
                now=self.hub.clock(),
                secret=sealed,
                connection_id=connection_id,
                secret_key=box.key_id,
                scope=PERSONAL,
            )
        except DuplicateConnection as duplicate:
            # A concurrent exchange of the same Item won the insert.
            stored.held = True
            if duplicate.elsewhere:
                raise PlaidItemOwnedElsewhere() from None
            existing = self.hub.connections.get(
                user_id=user_id, connection_id=duplicate.existing_id, scope=PERSONAL
            )
            return ExchangeResult(existing, created=False)
        return ExchangeResult(row, created=True)

    def _abandon(self, access_token: str) -> None:
        try:
            self.client.item_remove(access_token)
        except PlaidError as exc:
            logger.warning(
                "Unstored Plaid Item could not be removed", plaid_code=exc.error_code
            )

    def update_link_token(
        self, *, user_id: str, connection_id: str, language: LinkLanguage
    ) -> LinkToken:
        row = self._plaid_connection(user_id, connection_id)
        if row.status not in ("needs_reauth", "error") and not row.attention_code:
            raise ConnectionNotReauthorizable()
        token = self._credential(row)
        payload = self.client.link_token_create(
            client_user_id=client_user_id(user_id),
            language=language,
            access_token=token,
        )
        return _link_token(payload)

    def reconnected(self, *, user_id: str, connection_id: str) -> SourceConnection:
        """After Link update mode: re-check the Item and restore the connection.

        The cursor and ``last_success_at`` are kept. Re-sealing the same
        envelope through ``set_secret`` also clears any attention warning
        (consent renewed). A still-broken Item keeps (or updates) its
        actionable failure instead of claiming health.
        """

        row = self._plaid_connection(user_id, connection_id)
        token = self._credential(row)
        try:
            item = self.client.item_get(token)
        except PlaidError as exc:
            return self._record(row, exc.error_code)
        error = item.get("error")
        if isinstance(error, dict) and error.get("error_code"):
            return self._record(row, str(error["error_code"]))
        if row.secret is None:
            raise ConnectionNotReauthorizable()
        assert self.hub.box is not None
        return self.hub.connections.set_secret(
            connection_id=row.id,
            secret=row.secret,
            status="active",
            now=self.hub.clock(),
            # The token just opened under this key, so this key sealed it.
            secret_key=self.hub.box.key_id,
        )

    def _institution_label(self, access_token: str) -> str | None:
        try:
            item = self.client.item_get(access_token)
            institution_id = item.get("institution_id")
            if not isinstance(institution_id, str) or not institution_id:
                return None
            name = self.client.institution_name(institution_id)
        except PlaidError as exc:
            logger.info("Plaid institution label unavailable", plaid_code=exc.error_code)
            return None
        return (name[:80].strip() or None) if name else None

    def _plaid_connection(self, user_id: str, connection_id: str) -> SourceConnection:
        row = self.hub.connections.get(
            user_id=user_id, connection_id=connection_id, scope=PERSONAL
        )
        if row.source != "plaid":
            raise ConnectionNotFound()
        if row.status == "disconnected":
            raise ConnectionNotReauthorizable()
        return row

    def _credential(self, row: SourceConnection) -> str:
        try:
            token = self.hub.credential(row)
        except Exception:
            token = None
        if not token:
            raise ConnectionNotReauthorizable()
        return token

    def _record(self, row: SourceConnection, error_code: str) -> SourceConnection:
        failure = meaning(error_code)
        return self.hub.connections.record_failure(
            connection_id=row.id,
            code=failure.code,
            status=failure.status or row.status,
            now=self.hub.clock(),
        )


def _link_token(payload: dict) -> LinkToken:
    token = payload.get("link_token")
    if not isinstance(token, str) or not token:
        raise PlaidError(error_type="API_ERROR", error_code="MALFORMED_RESPONSE")
    expiration = payload.get("expiration")
    parsed: datetime | None = None
    if isinstance(expiration, str):
        try:
            parsed = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    return LinkToken(token, parsed)
