"""Process wiring and request gates for the Plaid connector.

The connector exists only when the ingestion hub exists (flag on, financial
accounts on), credentials can be sealed (``ARGUS_INGESTION_SECRET_KEY``) and
Plaid is configured. Otherwise every Plaid route answers 404 like the rest of
the financial-connections surface. Its ``revoke`` is registered with the hub at
startup so disconnect reaches ``/item/remove``.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from loguru import logger

from argus.api.dependencies import problem
from argus.api.ingestion import (
    IngestionContext,
    connection_problem,
    require_ingestion_context,
    require_ingestion_surface,
    unavailable_problem,
)
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.plaid.client import PlaidError
from argus.domain.ingestion.plaid.config import plaid_config_from_env
from argus.domain.ingestion.plaid.connector import PlaidConnector
from argus.domain.ingestion.plaid.link import (
    ConnectionNotReauthorizable,
    PlaidItemOwnedElsewhere,
)

_connector: PlaidConnector | None = None


def plaid_connector() -> PlaidConnector | None:
    return _connector


def configure_plaid_connector(connector: PlaidConnector | None) -> None:
    global _connector
    if _connector is not None and _connector is not connector:
        _connector.close()
    _connector = connector


def start_plaid(hub: IngestionHub | None) -> None:
    if hub is None or hub.box is None:
        configure_plaid_connector(None)
        return
    try:
        config = plaid_config_from_env()
    except ValueError as exc:
        logger.warning(
            "Plaid configuration is invalid; connector stays off", reason=str(exc)
        )
        configure_plaid_connector(None)
        return
    if not config.configured:
        configure_plaid_connector(None)
        return
    connector = PlaidConnector(hub, config)
    hub.register(connector.adapter)
    configure_plaid_connector(connector)


def stop_plaid() -> None:
    configure_plaid_connector(None)


@dataclass(frozen=True)
class PlaidContext:
    connector: PlaidConnector
    user_id: str


def require_plaid_context(
    request: Request,
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> PlaidContext:
    connector = plaid_connector()
    if connector is None or connector.hub is not context.hub:
        raise unavailable_problem(request)
    return PlaidContext(connector=connector, user_id=context.user_id)


def require_plaid_webhook_surface(
    request: Request,
    hub: IngestionHub = Depends(require_ingestion_surface),  # noqa: B008
) -> PlaidConnector:
    """Flag first; no user auth. The webhook authenticates by its signature."""

    connector = plaid_connector()
    if connector is None or connector.hub is not hub:
        raise unavailable_problem(request)
    return connector


def plaid_problem(request: Request, error: Exception) -> HTTPException:
    if isinstance(error, ConnectionNotFound):
        return connection_problem(request, error)
    if isinstance(error, ConnectionNotReauthorizable):
        return problem(
            request,
            status_code=409,
            code="financial_connection_not_reauthorizable",
            title="Conflict",
            detail="This connection does not need to be reconnected.",
        )
    if isinstance(error, PlaidItemOwnedElsewhere):
        return problem(
            request,
            status_code=409,
            code="plaid_item_unavailable",
            title="Conflict",
            detail="This bank login cannot be connected to this account.",
        )
    if isinstance(error, PlaidError):
        invalid = error.error_type in ("INVALID_INPUT", "INVALID_REQUEST")
        return problem(
            request,
            status_code=422 if invalid else 502,
            code="plaid_request_invalid" if invalid else "plaid_unavailable",
            title="Unprocessable Content" if invalid else "Bad Gateway",
            detail="Plaid did not accept the request."
            if invalid
            else "Plaid is unavailable right now. Try again shortly.",
            context={"plaid_error_code": error.error_code},
        )
    raise error
