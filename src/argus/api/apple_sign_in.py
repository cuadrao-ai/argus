"""Exposure gate and process wiring for Sign in with Apple token capture.

Default-off behind ``CUADRAO_APPLE_REVOCATION_CAPTURE_ENABLED``. While off,
:class:`AppleCaptureFlagGateMiddleware` answers the capture path with the plain
404 of a route that doesn't exist, before routing, so before the body is read
or authentication runs: invalid JSON, no session and a valid call all look the
same. When on, it fails closed: without every Apple client-secret input
(``argus.domain.apple_sign_in.config``), the credential key
``ARGUS_INGESTION_SECRET_KEY``, and in durable mode ``DATABASE_URL``, the
service is not built and the route answers 503. Nothing is ever stored
unsealed.

The revoke half (``AppleCredentialService.revoke``) is not exposed by any
route; the account-deletion lane calls it.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from starlette.responses import JSONResponse

from argus.api import state as api_state
from argus.domain.apple_sign_in.client import AppleAuthClient
from argus.domain.apple_sign_in.config import (
    AppleSignInConfig,
    AppleSignInUnconfigured,
)
from argus.domain.apple_sign_in.credentials import (
    AppleCredentialService,
    InMemoryAppleCredentialRepository,
)
from argus.domain.apple_sign_in.identity import (
    AppleIdentityUnavailable,
    LinkedAppleIdentity,
    parse_linked_apple_identity,
)
from argus.domain.ingestion.secrets import SecretBox, SecretBoxUnavailable

FLAG = "CUADRAO_APPLE_REVOCATION_CAPTURE_ENABLED"
CAPTURE_PATH = "/api/v1/auth/apple/authorization-code"
APPLE_NAME_PATH = "/api/v1/me/apple-name"
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

_service: AppleCredentialService | None = None


def capture_enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in TRUE_VALUES


class AppleCaptureFlagGateMiddleware:
    """While capture is off, the capture path answers as if it never existed.

    Same approach as ``EvidenceReceiptFlagGateMiddleware``: a check in the route
    runs after FastAPI has parsed the body and resolved auth, so invalid JSON
    got 422 and a missing session 401 even with the flag off.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if (
            scope.get("type") == "http"
            and scope.get("path", "").rstrip("/") in {CAPTURE_PATH, APPLE_NAME_PATH}
            and not capture_enabled()
        ):
            response = JSONResponse({"detail": "Not Found"}, status_code=404)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def apple_credentials_service() -> AppleCredentialService | None:
    return _service


def configure_apple_credentials_service(service: AppleCredentialService | None) -> None:
    global _service
    _service = service


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def start_apple_sign_in(app) -> None:  # noqa: ANN001
    configure_apple_credentials_service(None)
    if not capture_enabled():
        return
    try:
        config = AppleSignInConfig.from_env()
        box = SecretBox.from_env()
    except (AppleSignInUnconfigured, SecretBoxUnavailable) as exc:
        # Named, not the value: the reason says which variable is missing.
        logger.warning(
            "Apple token capture is unconfigured; failing closed", reason=str(exc)
        )
        return
    try:
        if api_state.PERSISTENCE_MODE == "supabase":
            if not api_state.DATABASE_URL:
                logger.warning("Apple token capture needs DATABASE_URL; failing closed")
                return
            from psycopg_pool import ConnectionPool

            from argus.domain.apple_sign_in.credentials_postgres import (
                PostgresAppleCredentialRepository,
            )

            pool = ConnectionPool(
                api_state.DATABASE_URL, min_size=0, max_size=2, open=True
            )
            app.state.apple_sign_in_pool = pool
            repository = PostgresAppleCredentialRepository(pool)
        else:
            repository = InMemoryAppleCredentialRepository(_memory_linked_identity)
        configure_apple_credentials_service(
            AppleCredentialService(
                repository, box=box, client=AppleAuthClient(config), clock=_clock
            )
        )
    except Exception as exc:
        logger.warning(
            "Apple token capture failed to start; failing closed",
            failure_mode=type(exc).__name__,
        )
        configure_apple_credentials_service(None)


def stop_apple_sign_in(app) -> None:  # noqa: ANN001
    service = apple_credentials_service()
    configure_apple_credentials_service(None)
    if service is not None:
        service.close()
    pool = getattr(app.state, "apple_sign_in_pool", None)
    if pool is not None:
        try:
            pool.close()
        except Exception:
            logger.warning("Apple sign-in pool close failed")
        app.state.apple_sign_in_pool = None


def _memory_linked_identity(user_id: str) -> LinkedAppleIdentity | None:
    gateway = api_state.supabase_gateway
    if gateway is None:
        raise AppleIdentityUnavailable("identity_reader_unconfigured")
    auth_user = gateway.get_auth_user_by_id(user_id)
    identities = auth_user.get("identities")
    if not isinstance(identities, list):
        raise AppleIdentityUnavailable("malformed_identity_response")
    return parse_linked_apple_identity(identities)
