"""Gmail OAuth, sender allowlist, suggestions and sync transport.

Thin: gates, request validation and error shaping. Logic lives in
``argus.domain.ingestion.gmail``. No response carries a Google token, a
cursor, a mailbox address beyond its masked label, or message content; the
only Google value returned is the consent URL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from argus.api.gmail import GmailContext, gmail_problem, require_gmail_context
from argus.api.routers.financial_connections_schemas import (
    FinancialConnectionResponse,
    connection_response,
)
from argus.domain.ingestion.gmail.senders import (
    MAX_SENDERS,
    SenderRule,
    normalize_senders,
)
from argus.domain.ingestion.gmail.sync import SyncMode, SyncStatus

router = APIRouter(prefix="/gmail")

_CODE = r"^[\x21-\x7e]+$"
_STATE = r"^[A-Za-z0-9_-]+$"


class AuthorizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorization_url: str
    expires_at: datetime


class CallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=512, pattern=_CODE)
    state: str = Field(min_length=1, max_length=1024, pattern=_STATE)
    senders: list[str] | None = Field(default=None, max_length=MAX_SENDERS)


class SenderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender: str
    kind: Literal["address", "domain"]
    created_at: datetime
    backfilled_at: datetime | None


class CallbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection: FinancialConnectionResponse
    created: bool
    senders: list[SenderResponse]


class SendersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    senders: list[str] = Field(max_length=MAX_SENDERS)


class SendersResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    senders: list[SenderResponse]


class SuggestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender: str
    domain: str
    messages: int
    authenticated: bool


class SuggestionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[SuggestionResponse]


class SyncSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SyncStatus
    mode: SyncMode | None
    messages: int
    candidates: int
    ignored: int
    skipped: dict[str, int]
    attachments: int
    attachments_skipped: dict[str, int]
    more_pending: bool
    scan_truncated: bool
    error_code: str | None


class SyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection: FinancialConnectionResponse
    sync: SyncSummary


def _senders(rules: list[SenderRule]) -> list[SenderResponse]:
    return [
        SenderResponse(
            sender=r.sender,
            kind=r.kind,
            created_at=r.created_at,
            backfilled_at=r.backfilled_at,
        )
        for r in rules
    ]


@router.post("/authorize", response_model=AuthorizeResponse)
def authorize_gmail(
    context: GmailContext = Depends(require_gmail_context),  # noqa: B008
) -> AuthorizeResponse:
    """Google consent URL for ``gmail.readonly``; valid for ten minutes."""

    started = context.connector.oauth.authorize(user_id=context.user_id)
    return AuthorizeResponse(
        authorization_url=started.authorization_url, expires_at=started.expires_at
    )


@router.post(
    "/callback",
    response_model=CallbackResponse,
    status_code=201,
    responses={200: {"model": CallbackResponse, "description": "Reconnected"}},
)
def complete_gmail_authorization(
    request: Request,
    response: Response,
    body: CallbackRequest,
    context: GmailContext = Depends(require_gmail_context),  # noqa: B008
) -> CallbackResponse:
    """The web app posts Google's ``code`` and ``state`` from the redirect.

    201 creates the connection; 200 reconnects the caller's existing
    connection for the same mailbox (new credential, same cursor)."""

    try:
        senders = None if body.senders is None else normalize_senders(body.senders)
        result = context.connector.oauth.callback(
            user_id=context.user_id, code=body.code, state=body.state, senders=senders
        )
    except Exception as error:
        raise gmail_problem(request, error, exchanging=True) from None
    response.status_code = 201 if result.created else 200
    return CallbackResponse(
        connection=connection_response(result.connection),
        created=result.created,
        senders=_senders(result.senders),
    )


@router.get("/{connection_id}/senders", response_model=SendersResponse)
def list_gmail_senders(
    request: Request,
    connection_id: str,
    context: GmailContext = Depends(require_gmail_context),  # noqa: B008
) -> SendersResponse:
    try:
        rules = context.connector.list_senders(
            user_id=context.user_id, connection_id=connection_id
        )
    except Exception as error:
        raise gmail_problem(request, error) from None
    return SendersResponse(senders=_senders(rules))


@router.put("/{connection_id}/senders", response_model=SendersResponse)
def replace_gmail_senders(
    request: Request,
    connection_id: str,
    body: SendersRequest,
    context: GmailContext = Depends(require_gmail_context),  # noqa: B008
) -> SendersResponse:
    """Replace the allowlist. Newly added senders are searched over the
    lookback window on the next sync."""

    connector = context.connector
    try:
        rules = connector.replace_senders(
            user_id=context.user_id,
            connection_id=connection_id,
            senders=body.senders,
            now=connector.hub.clock(),
        )
    except Exception as error:
        raise gmail_problem(request, error) from None
    return SendersResponse(senders=_senders(rules))


@router.get("/{connection_id}/sender-suggestions", response_model=SuggestionsResponse)
def suggest_gmail_senders(
    request: Request,
    connection_id: str,
    context: GmailContext = Depends(require_gmail_context),  # noqa: B008
) -> SuggestionsResponse:
    """Frequent recent senders from headers only; the person decides."""

    try:
        found = context.connector.suggestions(
            user_id=context.user_id, connection_id=connection_id
        )
    except Exception as error:
        raise gmail_problem(request, error) from None
    return SuggestionsResponse(
        suggestions=[
            SuggestionResponse(
                sender=s.sender,
                domain=s.domain,
                messages=s.messages,
                authenticated=s.authenticated,
            )
            for s in found
        ]
    )


@router.post("/{connection_id}/sync", response_model=SyncResponse)
def sync_gmail_connection(
    request: Request,
    connection_id: str,
    context: GmailContext = Depends(require_gmail_context),  # noqa: B008
) -> SyncResponse:
    connector = context.connector
    try:
        row = connector.live_connection(
            user_id=context.user_id, connection_id=connection_id
        )
    except Exception as error:
        raise gmail_problem(request, error) from None
    outcome = connector.sync(row)
    row = connector.connection(user_id=context.user_id, connection_id=connection_id)
    return SyncResponse(
        connection=connection_response(row),
        sync=SyncSummary(
            status=outcome.status,
            mode=outcome.mode,
            messages=outcome.messages,
            candidates=outcome.candidates,
            ignored=outcome.ignored,
            skipped=outcome.skipped,
            attachments=outcome.attachments,
            attachments_skipped=outcome.attachments_skipped,
            more_pending=outcome.more_pending,
            scan_truncated=outcome.scan_truncated,
            error_code=outcome.error_code,
        ),
    )
