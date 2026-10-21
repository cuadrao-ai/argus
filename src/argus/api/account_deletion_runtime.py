"""Builds the account deletion command from durable dependencies only.

Deletion owns its own small Postgres pool, so it works whatever other features
are switched on: households, financial accounts, ingestion and Apple capture
all being off doesn't stop a person from deleting their account. The running
surfaces are reused when they're up (the ingestion hub, #793's Apple service);
when they're off, revoke-only stand-ins are built from the same environment, so
a token stored while a feature was on is still revoked rather than stranded.
"""

from __future__ import annotations

import atexit
import threading
from datetime import datetime, timezone
from typing import Any

from loguru import logger

_lock = threading.Lock()
_pools: dict[str, Any] = {}
_revokers: dict[str, Any] = {}
_apple: dict[str, Any] = {}


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def deletion_pool(database_url: str) -> Any:
    from psycopg_pool import ConnectionPool

    with _lock:
        pool = _pools.get(database_url)
        if pool is None:
            pool = ConnectionPool(
                database_url,
                min_size=0,
                # A request and a sweep pass, or two requests, each need a
                # connection for the run and one for the Apple service.
                max_size=4,
                open=True,
                name="argus-account-deletion",
            )
            atexit.register(pool.close)
            _pools[database_url] = pool
        return pool


def household_repository(pool: Any) -> Any:
    """The household repository deletion runs its transaction through; it
    needs the accounts repository for archive copies, nothing gated."""

    from argus.domain.household.postgres import PostgresHouseholdRepository
    from argus.domain.household.repository import FinancialAccountLookup
    from argus.domain.recording.postgres_repository import (
        PostgresFinancialAccountRepository,
    )

    return PostgresHouseholdRepository(
        pool, FinancialAccountLookup(PostgresFinancialAccountRepository(pool))
    )


def standalone_revoker() -> Any:
    """Revoke-only Plaid and Gmail adapters over a hub with no connections.

    Deletion revokes from the ciphertext it captured, so it needs only the
    sealing key and each provider's revoke call. A provider that isn't
    configured has no adapter, and its revocation stays pending."""

    from argus.domain.ingestion.gmail.adapter import GmailAdapter
    from argus.domain.ingestion.gmail.client import GmailClient
    from argus.domain.ingestion.gmail.config import GmailConfig
    from argus.domain.ingestion.hub import IngestionHub
    from argus.domain.ingestion.plaid.adapter import PlaidAdapter
    from argus.domain.ingestion.plaid.client import PlaidClient
    from argus.domain.ingestion.plaid.config import plaid_config_from_env
    from argus.domain.ingestion.secrets import SecretBox, SecretBoxUnavailable

    with _lock:
        if "hub" in _revokers:
            return _revokers["hub"]
        try:
            box: SecretBox | None = SecretBox.from_env()
        except SecretBoxUnavailable:
            box = None
        hub = IngestionHub(None, box=box, sink=None, clock=_clock)  # type: ignore[arg-type]
        # Google's revoke endpoint needs no client credentials.
        hub.register(GmailAdapter(GmailClient(GmailConfig()), None))  # type: ignore[arg-type]
        try:
            plaid = plaid_config_from_env()
            if plaid.configured:
                hub.register(PlaidAdapter(PlaidClient(plaid)))
        except ValueError as exc:
            logger.warning("Plaid revoke for deletion unavailable", reason=str(exc))
        _revokers["hub"] = hub
        return hub


def standalone_apple(pool: Any) -> Any | None:
    """#793's service over deletion's pool, for revoking a stored token while
    the capture surface is off. None when Apple isn't configured."""

    from argus.domain.apple_sign_in.client import AppleAuthClient
    from argus.domain.apple_sign_in.config import (
        AppleSignInConfig,
        AppleSignInUnconfigured,
    )
    from argus.domain.apple_sign_in.credentials import AppleCredentialService
    from argus.domain.apple_sign_in.credentials_postgres import (
        PostgresAppleCredentialRepository,
    )
    from argus.domain.ingestion.secrets import SecretBox, SecretBoxUnavailable

    with _lock:
        if "service" in _apple:
            return _apple["service"]
        try:
            config = AppleSignInConfig.from_env()
            box = SecretBox.from_env()
        except (AppleSignInUnconfigured, SecretBoxUnavailable) as exc:
            logger.warning("Apple revoke for deletion unavailable", reason=str(exc))
            service = None
        else:
            service = AppleCredentialService(
                PostgresAppleCredentialRepository(pool),
                box=box,
                client=AppleAuthClient(config),
                clock=_clock,
            )
        _apple["service"] = service
        return service


def build_service(
    *,
    database_url: str,
    supabase_client: Any,
    revoker: Any | None = None,
    apple: Any | None = None,
) -> Any:
    from argus.domain.account_deletion.auth_admin import SupabaseAuthAdmin
    from argus.domain.account_deletion.service import AccountDeletionService
    from argus.domain.ingestion.documents.objects import SupabaseSourceObjects
    from argus.domain.ingestion.secrets import SecretBox, SecretBoxUnavailable
    from argus.observability.analytics_deletion import (
        analytics_deletion_from_env,
        fake_analytics_allowed,
    )

    pool = deletion_pool(database_url)
    try:
        # Only for the key check: with no key, an unreadable token is never
        # treated as unrecoverable; it stays pending and alerts.
        box: SecretBox | None = SecretBox.from_env()
    except SecretBoxUnavailable:
        box = None
    return AccountDeletionService(
        households=household_repository(pool),
        auth_admin=SupabaseAuthAdmin(supabase_client),
        revoker=revoker or standalone_revoker(),
        analytics=analytics_deletion_from_env(),
        apple=apple or standalone_apple(pool),
        secret_box=box,
        # The recording fake finishes a run only in tests and local dev.
        allow_fake_analytics=fake_analytics_allowed(),
        source_objects=SupabaseSourceObjects(supabase_client.storage),
    )
