"""Process wiring and request gates for the Gmail connector.

The connector exists only when the ingestion hub exists (flag on, financial
accounts on), credentials can be sealed (``ARGUS_INGESTION_SECRET_KEY``) and
the Google OAuth client is configured (``GOOGLE_OAUTH_CLIENT_ID``,
``GOOGLE_OAUTH_CLIENT_SECRET``, ``GOOGLE_OAUTH_REDIRECT_URI``). Otherwise every
Gmail route answers 404 like the rest of the financial-connections surface.
Its adapter is registered with the hub at startup so disconnect reaches
Google's revocation endpoint and forgets the sender allowlist. When only the
OAuth client is missing (the sealing key exists), a revoke-only adapter is
still registered: Gmail connections made earlier can be disconnected
truthfully while the routes are off.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, Request
from loguru import logger

from argus.api import state as api_state
from argus.api.dependencies import problem
from argus.api.ingestion import (
    IngestionContext,
    connection_problem,
    require_ingestion_context,
    unavailable_problem,
)
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.gmail.adapter import GmailAdapter
from argus.domain.ingestion.gmail.client import GmailClient, GmailError
from argus.domain.ingestion.gmail.config import GmailConfig, gmail_config_from_env
from argus.domain.ingestion.gmail.connector import (
    ConnectionDisconnected,
    GmailConnector,
)
from argus.domain.ingestion.gmail.failures import meaning
from argus.domain.ingestion.gmail.oauth import (
    MailboxOwnedElsewhere,
    RefreshTokenMissing,
    ScopeNotGranted,
)
from argus.domain.ingestion.gmail.senders import (
    InMemorySenderRepository,
    InvalidSender,
    SenderRepository,
)
from argus.domain.ingestion.gmail.state import StateRejected
from argus.domain.ingestion.hub import IngestionHub

_connector: GmailConnector | None = None
_revoke_only: GmailAdapter | None = None


def gmail_connector() -> GmailConnector | None:
    return _connector


def configure_gmail_connector(connector: GmailConnector | None) -> None:
    global _connector
    if _connector is not None and _connector is not connector:
        _connector.close()
    _connector = connector


def revoke_only_adapter() -> GmailAdapter | None:
    return _revoke_only


def _set_revoke_only(adapter: GmailAdapter | None) -> None:
    global _revoke_only
    if _revoke_only is not None and _revoke_only is not adapter:
        _revoke_only.client.close()
    _revoke_only = adapter


def start_gmail(
    hub: IngestionHub | None,
    pool: object | None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> None:
    configure_gmail_connector(None)
    _set_revoke_only(None)
    if hub is None:
        return
    senders = _sender_repository(pool)
    if senders is None:
        return
    try:
        config: GmailConfig | None = gmail_config_from_env()
    except ValueError as exc:
        logger.warning(
            "Gmail configuration is invalid; connector stays off", reason=str(exc)
        )
        config = None
    # Without the sealing key the connector stays off, but the cleanup-only
    # adapter below still forgets sender rows when a connection ends; its
    # revocation reports failed because no stored token can be read.
    if config is not None and config.configured and hub.box is not None:
        try:
            connector = GmailConnector(hub, config, senders=senders, transport=transport)
        except Exception as exc:
            # Gmail failing to start must not take the shared hub down with it.
            logger.warning(
                "Gmail connector construction failed; connector stays off",
                failure_mode=type(exc).__name__,
            )
        else:
            hub.register(connector.adapter)
            configure_gmail_connector(connector)
            return
    # Routes stay off, but stored Gmail grants can still be revoked at Google
    # (revocation needs no client credentials) and sender rows forgotten.
    adapter = GmailAdapter(GmailClient(GmailConfig(), transport=transport), senders)
    hub.register(adapter)
    _set_revoke_only(adapter)


def _sender_repository(pool: object | None) -> SenderRepository | None:
    if api_state.PERSISTENCE_MODE != "supabase":
        return InMemorySenderRepository()
    if pool is None:
        return None
    from argus.domain.ingestion.gmail.senders_postgres import PostgresSenderRepository

    return PostgresSenderRepository(pool)  # type: ignore[arg-type]


def stop_gmail() -> None:
    configure_gmail_connector(None)
    _set_revoke_only(None)


@dataclass(frozen=True)
class GmailContext:
    connector: GmailConnector
    user_id: str


def require_gmail_context(
    request: Request,
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> GmailContext:
    connector = gmail_connector()
    if connector is None or connector.hub is not context.hub:
        raise unavailable_problem(request)
    return GmailContext(connector=connector, user_id=context.user_id)


_FIXED: dict[type, tuple[int, str, str, str]] = {
    ConnectionDisconnected: (
        409, "financial_connection_disconnected", "Conflict",
        "This connection has been disconnected.",
    ),
    ScopeNotGranted: (
        422, "gmail_scope_not_granted", "Unprocessable Content",
        "Cuadrao needs permission to read your Gmail messages. Authorize again "
        "and keep the Gmail permission selected.",
    ),
    RefreshTokenMissing: (
        502, "gmail_refresh_token_missing", "Bad Gateway",
        "Google did not grant ongoing access. Authorize again.",
    ),
    MailboxOwnedElsewhere: (
        409, "gmail_mailbox_unavailable", "Conflict",
        "This mailbox cannot be connected to this account.",
    ),
    InvalidSender: (
        422, "gmail_sender_invalid", "Unprocessable Content",
        "Senders must be email addresses or domain names (at most 20).",
    ),
}  # fmt: skip


def gmail_problem(
    request: Request, error: Exception, *, exchanging: bool = False
) -> HTTPException:
    if isinstance(error, ConnectionNotFound):
        return connection_problem(request, error)
    for kind, (status, code, title, detail) in _FIXED.items():
        if isinstance(error, kind):
            return problem(
                request, status_code=status, code=code, title=title, detail=detail
            )
    if isinstance(error, StateRejected) and error.reason == "rate_limited":
        return problem(
            request,
            status_code=429,
            code="gmail_oauth_rate_limited",
            title="Too Many Requests",
            detail="Too many Gmail authorizations in a short time. Wait a few "
            "minutes and start again.",
        )
    if isinstance(error, StateRejected):
        return problem(
            request,
            status_code=400,
            code="gmail_oauth_state_invalid",
            title="Bad Request",
            detail="This Gmail authorization is no longer valid. Start again.",
            context={"reason": error.reason},
        )
    if isinstance(error, GmailError):
        return _google_problem(request, error, exchanging)
    raise error


def _google_problem(
    request: Request, error: GmailError, exchanging: bool
) -> HTTPException:
    if exchanging and error.status == 400:
        # The code is single-use, expired or not for this verifier.
        return problem(
            request,
            status_code=400,
            code="gmail_authorization_code_invalid",
            title="Bad Request",
            detail="Google did not accept this authorization. Start again.",
        )
    failure = meaning(error)
    if failure.status == "needs_reauth":
        return problem(
            request,
            status_code=409,
            code=failure.code,
            title="Conflict",
            detail="Gmail access needs to be authorized again.",
        )
    return problem(
        request,
        status_code=502,
        code="gmail_unavailable",
        title="Bad Gateway",
        detail="Gmail is unavailable right now. Try again shortly.",
    )
