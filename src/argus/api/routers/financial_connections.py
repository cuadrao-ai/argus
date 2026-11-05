"""Connected sources: what is connected, how fresh it is, and disconnect.

Thin transport over ``IngestionHub``. Credentials, cursors and leases are never
part of a response. Connector-specific routes (Plaid Link, Gmail OAuth,
Shortcuts device setup) live with their connector packages.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from argus.api.documents import require_connection_removal
from argus.api.ingestion import (
    IngestionContext,
    connection_problem,
    require_ingestion_context,
)
from argus.api.routers.financial_connections_schemas import (
    DisconnectResponse,
    FinancialConnectionListResponse,
    connection_response,
)
from argus.domain.owner_scope import PERSONAL

router = APIRouter(prefix="/financial-connections", tags=["financial-connections"])


@router.get("", response_model=FinancialConnectionListResponse)
def list_financial_connections(
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> FinancialConnectionListResponse:
    rows = context.hub.list(user_id=context.user_id, scope=PERSONAL)
    return FinancialConnectionListResponse(items=[connection_response(r) for r in rows])


@router.post("/{connection_id}/disconnect", response_model=DisconnectResponse)
def disconnect_financial_connection(
    request: Request,
    connection_id: str,
    context: IngestionContext = Depends(require_connection_removal),  # noqa: B008
) -> DisconnectResponse:
    """Idempotent: disconnecting an ended connection returns it unchanged.

    With ingestion off only a saved document can be disconnected."""

    try:
        outcome = context.hub.disconnect(
            user_id=context.user_id, connection_id=connection_id, scope=PERSONAL
        )
    except Exception as error:
        raise connection_problem(request, error) from None
    return DisconnectResponse(
        connection=connection_response(outcome.connection),
        provider_revocation=outcome.provider_revocation,
        unreviewed_removed=outcome.unreviewed_removed,
    )


# Connector sub-routers are included after this router's own routes; they
# take their response shapes from financial_connections_schemas.
from argus.api.routers.financial_connections_gmail import (  # noqa: E402
    router as gmail_router,
)
from argus.api.routers.financial_connections_plaid import (  # noqa: E402
    router as plaid_router,
)

router.include_router(gmail_router)
router.include_router(plaid_router)
from argus.api.routers.ingestion_shortcuts import (  # noqa: E402
    devices_router as shortcuts_devices_router,
)

router.include_router(shortcuts_devices_router)
