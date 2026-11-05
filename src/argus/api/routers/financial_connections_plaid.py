"""Plaid Link, sync, reconnect and webhook transport.

Thin: gates, request validation and error shaping. Logic lives in
``argus.domain.ingestion.plaid``. No response ever carries an access token,
cursor or provider payload; a link token is the only Plaid value returned.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from argus.api.dependencies import problem
from argus.api.plaid import (
    PlaidContext,
    plaid_problem,
    require_plaid_context,
    require_plaid_webhook_surface,
)
from argus.api.routers.financial_connections_schemas import (
    FinancialConnectionResponse,
    connection_response,
)
from argus.domain.ingestion.plaid.connector import PlaidConnector
from argus.domain.ingestion.plaid.sync import SyncStatus
from argus.domain.ingestion.plaid.verification import (
    MAX_BODY_BYTES,
    VerificationUnavailable,
    WebhookRejected,
)

router = APIRouter(prefix="/plaid")


class LinkTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["en", "es"] = "en"


class LinkTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_token: str
    expiration: datetime | None


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_token: str = Field(
        min_length=1, max_length=200, pattern=r"^public-[A-Za-z0-9-]+$"
    )


class ExchangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection: FinancialConnectionResponse
    created: bool


class SyncSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SyncStatus
    added: int
    modified: int
    removed: int
    error_code: str | None


class SyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection: FinancialConnectionResponse
    sync: SyncSummary


class WebhookReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    received: bool


@router.post("/link-token", response_model=LinkTokenResponse)
def create_plaid_link_token(
    request: Request,
    body: LinkTokenRequest | None = None,
    context: PlaidContext = Depends(require_plaid_context),  # noqa: B008
) -> LinkTokenResponse:
    language = body.language if body else "en"
    try:
        token = context.connector.link.link_token(
            user_id=context.user_id, language=language
        )
    except Exception as error:
        raise plaid_problem(request, error) from None
    return LinkTokenResponse(link_token=token.link_token, expiration=token.expiration)


@router.post(
    "/exchange",
    response_model=ExchangeResponse,
    status_code=201,
    responses={200: {"model": ExchangeResponse, "description": "Already connected"}},
)
def exchange_plaid_public_token(
    request: Request,
    response: Response,
    body: ExchangeRequest,
    background: BackgroundTasks,
    context: PlaidContext = Depends(require_plaid_context),  # noqa: B008
) -> ExchangeResponse:
    """Idempotent: a retried exchange or a re-linked Item returns the existing
    connection with ``created=false``."""

    try:
        result = context.connector.link.exchange(
            user_id=context.user_id, public_token=body.public_token
        )
    except Exception as error:
        raise plaid_problem(request, error) from None
    if result.created:
        # First sync initializes Transactions so Plaid starts sending
        # SYNC_UPDATES_AVAILABLE; it runs after the response is sent.
        background.add_task(context.connector.sync, result.connection)
    response.status_code = 201 if result.created else 200
    return ExchangeResponse(
        connection=connection_response(result.connection), created=result.created
    )


@router.post("/{connection_id}/sync", response_model=SyncResponse)
def sync_plaid_connection(
    request: Request,
    connection_id: str,
    context: PlaidContext = Depends(require_plaid_context),  # noqa: B008
) -> SyncResponse:
    connector = context.connector
    try:
        row = connector.connection(user_id=context.user_id, connection_id=connection_id)
    except Exception as error:
        raise plaid_problem(request, error) from None
    if row.status == "disconnected":
        raise problem(
            request,
            status_code=409,
            code="financial_connection_disconnected",
            title="Conflict",
            detail="This connection has been disconnected.",
        )
    outcome = connector.sync(row)
    row = connector.connection(user_id=context.user_id, connection_id=connection_id)
    return SyncResponse(
        connection=connection_response(row),
        sync=SyncSummary(
            status=outcome.status,
            added=outcome.added,
            modified=outcome.modified,
            removed=outcome.removed,
            error_code=outcome.error_code,
        ),
    )


@router.post("/{connection_id}/link-token", response_model=LinkTokenResponse)
def create_plaid_update_link_token(
    request: Request,
    connection_id: str,
    body: LinkTokenRequest | None = None,
    context: PlaidContext = Depends(require_plaid_context),  # noqa: B008
) -> LinkTokenResponse:
    """Link update mode for a connection that needs the person's login again."""

    try:
        token = context.connector.link.update_link_token(
            user_id=context.user_id,
            connection_id=connection_id,
            language=body.language if body else "en",
        )
    except Exception as error:
        raise plaid_problem(request, error) from None
    return LinkTokenResponse(link_token=token.link_token, expiration=token.expiration)


@router.post("/{connection_id}/reconnected", response_model=FinancialConnectionResponse)
def confirm_plaid_reconnected(
    request: Request,
    connection_id: str,
    background: BackgroundTasks,
    context: PlaidContext = Depends(require_plaid_context),  # noqa: B008
) -> FinancialConnectionResponse:
    """After Link update mode succeeds: re-check the Item, then resume syncing."""

    try:
        row = context.connector.link.reconnected(
            user_id=context.user_id, connection_id=connection_id
        )
    except Exception as error:
        raise plaid_problem(request, error) from None
    if row.status == "active":
        background.add_task(context.connector.sync, row)
    return connection_response(row)


@router.post("/webhook", response_model=WebhookReceipt)
async def receive_plaid_webhook(
    request: Request,
    background: BackgroundTasks,
    connector: PlaidConnector = Depends(require_plaid_webhook_surface),  # noqa: B008
) -> WebhookReceipt:
    """Plaid-signed; no user session. Answers quickly and syncs afterwards."""

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            raise _rejected(request)
    token = request.headers.get("Plaid-Verification")
    try:
        verified = await run_in_threadpool(connector.verifier.verify, token, bytes(body))
    except WebhookRejected:
        raise _rejected(request) from None
    except VerificationUnavailable:
        raise problem(
            request,
            status_code=503,
            code="plaid_webhook_unverifiable",
            title="Service Unavailable",
            detail="Webhook could not be verified right now.",
        ) from None
    if verified.duplicate:
        return WebhookReceipt(received=True)
    try:
        plan = await run_in_threadpool(connector.webhooks.plan, verified.payload)
    except Exception:
        # Not handled: Plaid's retry of this delivery must be processed.
        connector.verifier.release(token or "")
        raise
    if plan.effect in ("sync", "repair"):
        background.add_task(connector.run, plan)
    return WebhookReceipt(received=True)


def _rejected(request: Request):  # noqa: ANN202
    return problem(
        request,
        status_code=400,
        code="plaid_webhook_rejected",
        title="Bad Request",
        detail="Webhook could not be verified.",
    )
