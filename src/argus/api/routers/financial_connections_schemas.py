"""Connected-source response shapes, shared by the connections router and the
connector sub-routers it includes (kept apart so neither imports the other)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from argus.domain.ingestion.connections import SourceConnection


class FinancialConnectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: Literal["plaid", "gmail", "shortcuts", "statement"]
    status: Literal["active", "needs_reauth", "error", "disconnected"]
    label: str | None
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error_code: str | None
    attention_code: str | None
    attention_at: datetime | None
    created_at: datetime
    disconnected_at: datetime | None


class FinancialConnectionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FinancialConnectionResponse]


class DisconnectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection: FinancialConnectionResponse
    provider_revocation: Literal["revoked", "failed", "not_applicable"]
    unreviewed_removed: int


def connection_response(row: SourceConnection) -> FinancialConnectionResponse:
    return FinancialConnectionResponse(
        id=row.id,
        source=row.source,
        status=row.status,
        label=row.label,
        last_success_at=row.last_success_at,
        last_attempt_at=row.last_attempt_at,
        last_error_code=row.last_error_code,
        attention_code=row.attention_code,
        attention_at=row.attention_at,
        created_at=row.created_at,
        disconnected_at=row.disconnected_at,
    )
