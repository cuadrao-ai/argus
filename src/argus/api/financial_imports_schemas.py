"""Wire shapes for the import review queue."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from argus.domain.recording.money_responses import (
    MoneyActivityResponse,
    MoneyPreviewResponse,
)
from argus.domain.recording.money_schemas import MoneyRequest


class ImportAttachmentResponse(BaseModel):
    media_type: str | None
    size_bytes: int | None
    sha256: str | None
    filename: str | None


class ImportObservationResponse(BaseModel):
    id: str
    source: Literal["plaid", "gmail", "shortcuts", "statement"]
    connection_id: str
    external_id: str
    evidence: str | None
    status: str | None
    live: bool
    revisions: int
    observed_at: str | None
    occurred_on: str | None
    posted_on: str | None
    due_on: str | None
    amount: str | None
    currency: str | None
    direction: str | None
    merchant: str | None
    description: str | None
    excerpt: str | None
    balance_scope: str | None
    institution: str | None
    account_name: str | None
    account_mask: str | None
    attachments: list[ImportAttachmentResponse]
    redacted: bool


class ImportFactsResponse(BaseModel):
    amount: str | None
    currency: str | None
    direction: str | None
    occurred_on: str | None
    account_id: str | None
    kind: str | None


class ImportEventResponse(BaseModel):
    id: str
    state: Literal["open", "accepting", "accepted", "dismissed"]
    evidence: str
    version: int
    attention: str | None
    attention_detail: dict[str, Any] | None
    possible_duplicates: list[str]
    existing_activity_matches: list[str]
    recorded_duplicates: list[str]
    activity_id: str | None
    facts: ImportFactsResponse
    resolution: dict[str, Any]
    unresolved: list[str]
    account_shared_with_household: bool | None
    observations: list[ImportObservationResponse]
    created_at: datetime
    updated_at: datetime


class ImportEventListResponse(BaseModel):
    items: list[ImportEventResponse]


class VersionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)


class ResolveBody(VersionBody):
    changes: dict[str, Any]


class MergeBody(VersionBody):
    into_event_id: str
    into_version: int = Field(ge=1)


class LinkActivityBody(VersionBody):
    activity_id: str


class PreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overrides: dict[str, Any] = Field(default_factory=dict)


class AcceptBody(VersionBody):
    request: MoneyRequest


class ImportPreviewResponse(BaseModel):
    event: ImportEventResponse
    preview: MoneyPreviewResponse


class ImportAcceptResponse(BaseModel):
    event: ImportEventResponse
    activity: MoneyActivityResponse
    replayed: bool


class BatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    version: int = Field(ge=1)


class AcceptBatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[BatchItem] = Field(min_length=1, max_length=100)


class BatchOutcome(BaseModel):
    event_id: str
    outcome: Literal["accepted", "needs_review"]
    activity_id: str | None = None
    replayed: bool | None = None
    code: str | None = None


class AcceptBatchResponse(BaseModel):
    items: list[BatchOutcome]
