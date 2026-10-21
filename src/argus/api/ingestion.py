"""Exposure gate and process wiring for connected-source ingestion.

Default-off behind ``CUADRAO_INGESTION_ENABLED`` (or the older ``ARGUS_`` name) and nested inside the financial
accounts surface: imports only ever feed that canonical ledger, so ingestion
cannot be on while it is off. Durable mode reuses the financial accounts pool
rather than opening a second one. Connector packages register their adapters
with the hub at startup; reconciliation provides the candidate sink.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from loguru import logger

from argus.api import state as api_state
from argus.api.dependencies import problem
from argus.api.financial_accounts import (
    TRUE_VALUES,
    FinancialAccountsContext,
    financial_accounts_service,
    require_financial_accounts_context,
)
from argus.domain.ingestion.connections import (
    ConnectionNotFound,
    InMemoryConnectionRepository,
)
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.secrets import SecretBox, SecretBoxUnavailable
from argus.settings_names import setting_value

FLAG = "CUADRAO_INGESTION_ENABLED"

_hub: IngestionHub | None = None


def ingestion_enabled() -> bool:
    return (setting_value("INGESTION_ENABLED") or "").strip().lower() in TRUE_VALUES


def ingestion_hub() -> IngestionHub | None:
    return _hub


def configure_ingestion_hub(hub: IngestionHub | None) -> None:
    global _hub
    _hub = hub


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def start_ingestion(app) -> None:  # noqa: ANN001
    """Build the hub after financial accounts; any missing piece keeps it off.

    With the flag off, saved documents still get a hub of their own that no
    connector or intake route reaches, so their owner can read and remove them.
    """

    configure_ingestion_hub(None)
    if financial_accounts_service() is None:
        return
    if not ingestion_enabled():
        _start_saved_documents(app)
        return
    try:
        box: SecretBox | None
        try:
            box = SecretBox.from_env()
        except SecretBoxUnavailable:
            # Connectors that store provider credentials refuse to start
            # without a key; credential-free surfaces still list/disconnect.
            box = None
        hub = _build_hub(app, box)
        if hub is None:
            return
        configure_ingestion_hub(hub)
        from argus.api.plaid import start_plaid

        start_plaid(ingestion_hub())
        from argus.api.gmail import start_gmail

        start_gmail(ingestion_hub(), getattr(app.state, "financial_accounts_pool", None))
        from argus.api.shortcuts import start_shortcuts

        start_shortcuts(app, ingestion_hub())
        from argus.api.documents import start_documents

        start_documents(app, ingestion_hub())
        from argus.api.business_spaces import start_business_spaces

        start_business_spaces(app)
        from argus.api.whatsapp import start_whatsapp

        start_whatsapp(app)
    except Exception as exc:
        logger.warning(
            "Ingestion hub construction failed; surface stays off",
            failure_mode=type(exc).__name__,
        )
        configure_ingestion_hub(None)


def _build_hub(app, box: SecretBox | None) -> IngestionHub | None:  # noqa: ANN001
    pool = getattr(app.state, "financial_accounts_pool", None)
    if api_state.PERSISTENCE_MODE == "supabase":
        if pool is None:
            return None
        from argus.domain.ingestion.connections_postgres import (
            PostgresConnectionRepository,
        )

        connections = PostgresConnectionRepository(pool)
    else:
        connections = InMemoryConnectionRepository()
    return IngestionHub(
        connections, box=box, sink=_reconciliation(pool, connections), clock=_clock
    )


def _start_saved_documents(app) -> None:  # noqa: ANN001
    from argus.api.documents import configure_documents, start_saved_documents

    try:
        start_saved_documents(app, _build_hub(app, None))
    except Exception as exc:
        logger.warning(
            "Saved documents failed to start; they stay unreachable",
            failure_mode=type(exc).__name__,
        )
        configure_documents(None)


def _reconciliation(pool, connections):  # noqa: ANN001, ANN202
    """The one candidate sink: every connector's evidence reaches review here."""

    from argus.domain.ingestion.reconcile.service import ReconciliationService
    from argus.domain.ingestion.reconcile.store import InMemoryImportStore
    from argus.domain.recording.money_service import MoneyService

    accounts = financial_accounts_service()
    if api_state.PERSISTENCE_MODE == "supabase":
        from argus.domain.ingestion.reconcile.store_postgres import (
            PostgresImportStore,
        )

        store = PostgresImportStore(pool)
    else:
        store = InMemoryImportStore()
    return ReconciliationService(
        store, MoneyService(accounts), _clock, connections=connections
    )


def stop_ingestion(app) -> None:  # noqa: ANN001
    from argus.api.plaid import stop_plaid

    stop_plaid()
    from argus.api.gmail import stop_gmail

    stop_gmail()
    from argus.api.shortcuts import stop_shortcuts

    stop_shortcuts()
    from argus.api.whatsapp import configure_whatsapp

    configure_whatsapp(None)
    from argus.api.business_spaces import (
        configure_business_access,
        configure_business_spaces,
    )

    configure_business_spaces(None)
    configure_business_access(None)
    from argus.api.documents import configure_documents

    configure_documents(None)
    configure_ingestion_hub(None)


@dataclass(frozen=True)
class IngestionContext:
    hub: IngestionHub
    user_id: str


def require_ingestion_surface(request: Request) -> IngestionHub:
    """Flag first, before authentication, so an off surface looks absent."""

    hub = ingestion_hub()
    if not ingestion_enabled() or hub is None:
        raise unavailable_problem(request)
    return hub


def require_ingestion_context(
    hub: IngestionHub = Depends(require_ingestion_surface),  # noqa: B008
    accounts: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> IngestionContext:
    return IngestionContext(hub=hub, user_id=accounts.user_id)


def unavailable_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=404,
        code="financial_connections_unavailable",
        title="Not Found",
        detail="Financial connections are not available.",
        # The answer changes with a flag, so no cache may keep it.
        headers={"Cache-Control": "no-store"},
    )


def connection_problem(request: Request, error: Exception) -> HTTPException:
    if isinstance(error, ConnectionNotFound):
        return problem(
            request,
            status_code=404,
            code="financial_connection_not_found",
            title="Not Found",
            detail="No such financial connection.",
        )
    raise error
