"""Process wiring and request gates for the Apple Shortcuts connector.

The connector exists whenever the ingestion hub exists; it stores no provider
credential, so it does not need ``ARGUS_INGESTION_SECRET_KEY``. Its local
``revoke`` is registered with the hub so disconnect deletes the device token.
Event intake has no user session: it answers 404 while the surface is off and
otherwise authenticates only by the device token.

Limits bound a leaked token or a token-guessing caller, not normal use. They
are process-local (each API process counts on its own; a restart forgets):
failed tokens per client address (checked before authentication), requests
per device per minute and per day (one limiter per window, so compacting one
cannot erase the other's history), and events per device per day so a batch
cannot multiply the request budget.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from loguru import logger

from argus.api import state as api_state
from argus.api.client_ip import resolve_client_ip
from argus.api.dependencies import problem
from argus.api.ingestion import (
    IngestionContext,
    require_ingestion_context,
    require_ingestion_surface,
    unavailable_problem,
)
from argus.api.rate_limits import SlidingWindowLimiter
from argus.api.shortcuts_limits import WeightedWindow
from argus.domain.ingestion.connections import SourceConnection
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.shortcuts.connector import ShortcutsConnector
from argus.domain.ingestion.shortcuts.store import (
    DeviceTokenStore,
    InMemoryDeviceTokenStore,
)

DAY = 24 * 60 * 60
# (limit, window seconds, limiter): requests per device.
REQUEST_LIMITS = (
    (20, 60, SlidingWindowLimiter()),
    (300, DAY, SlidingWindowLimiter()),
)
# Events per device per day, counting every event of a batch.
EVENTS_PER_DAY = 500
# (limit, window seconds): failed device tokens per client address.
FAILED_AUTH_PER_ADDRESS = (30, 10 * 60)

_connector: ShortcutsConnector | None = None
_events = WeightedWindow()
_failed_auth = WeightedWindow()


def shortcuts_connector() -> ShortcutsConnector | None:
    return _connector


def configure_shortcuts_connector(connector: ShortcutsConnector | None) -> None:
    global _connector
    _connector = connector
    for _limit, _window, limiter in REQUEST_LIMITS:
        limiter.reset()
    _events.reset()
    _failed_auth.reset()


def start_shortcuts(app, hub: IngestionHub | None) -> None:  # noqa: ANN001
    if hub is None:
        configure_shortcuts_connector(None)
        return
    store: DeviceTokenStore
    if api_state.PERSISTENCE_MODE == "supabase":
        pool = getattr(app.state, "financial_accounts_pool", None)
        if pool is None:
            configure_shortcuts_connector(None)
            return
        from argus.domain.ingestion.shortcuts.store import PostgresDeviceTokenStore

        store = PostgresDeviceTokenStore(pool)
    else:
        store = InMemoryDeviceTokenStore()
    connector = ShortcutsConnector(hub, store)
    hub.register(connector.adapter)
    configure_shortcuts_connector(connector)
    logger.info("Shortcuts connector ready")


def stop_shortcuts() -> None:
    configure_shortcuts_connector(None)


@dataclass(frozen=True)
class ShortcutsContext:
    connector: ShortcutsConnector
    user_id: str


def require_shortcuts_context(
    request: Request,
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> ShortcutsContext:
    connector = shortcuts_connector()
    if connector is None or connector.hub is not context.hub:
        raise unavailable_problem(request)
    return ShortcutsContext(connector=connector, user_id=context.user_id)


@dataclass(frozen=True)
class DeviceContext:
    connector: ShortcutsConnector
    connection: SourceConnection


def require_shortcuts_device(
    request: Request,
    hub: IngestionHub = Depends(require_ingestion_surface),  # noqa: B008
) -> DeviceContext:
    """Flag first; then the device token is the only accepted credential."""

    connector = shortcuts_connector()
    if connector is None or connector.hub is not hub:
        raise unavailable_problem(request)
    address = resolve_client_ip(request)
    limit, window = FAILED_AUTH_PER_ADDRESS
    wait = _failed_auth.blocked(address, limit=limit, window=window)
    if wait is not None:
        raise too_many_problem(request, wait)
    connection = connector.authenticate(request.headers.get("Authorization"))
    if connection is None:
        _failed_auth.spend(address, 1, limit=limit, window=window)
        raise device_unauthorized_problem(request)
    for limit, window, limiter in REQUEST_LIMITS:
        wait = limiter.record_or_retry_after(
            keys=(f"shortcuts-device:{connection.id}",),
            limit=limit,
            window_seconds=window,
        )
        if wait is not None:
            raise too_many_problem(request, wait)
    return DeviceContext(connector=connector, connection=connection)


def spend_event_budget(request: Request, device: DeviceContext, count: int) -> None:
    wait = _events.spend(device.connection.id, count, limit=EVENTS_PER_DAY, window=DAY)
    if wait is not None:
        raise too_many_problem(request, wait)


def device_unauthorized_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=401,
        code="shortcuts_device_unauthorized",
        title="Unauthorized",
        detail="This device is not connected. Set it up again in Cuadrao.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def too_many_problem(request: Request, wait: int) -> HTTPException:
    return problem(
        request,
        status_code=429,
        code="too_many_requests",
        title="Too Many Requests",
        detail="Too many captures recently. Try again shortly.",
        headers={"Retry-After": str(wait)},
    )


def intake_unavailable_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=503,
        code="shortcuts_intake_unavailable",
        title="Service Unavailable",
        detail="Captures cannot be saved right now. Nothing was saved; try again later.",
        context={"retryable": True},
        headers={"Retry-After": "300"},
    )


def events_not_saved_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=503,
        code="shortcuts_events_not_saved",
        title="Service Unavailable",
        detail=(
            "Some or all captures were not saved. Sending them again is safe; "
            "captures already saved are not duplicated."
        ),
        context={"retryable": True},
        headers={"Retry-After": "300"},
    )
