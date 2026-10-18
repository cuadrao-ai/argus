from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

DeliveryState = Literal["received", "processing", "partial", "captured", "rejected"]
PartState = Literal["pending", "captured", "rejected"]


@dataclass(frozen=True)
class RecipientRoute:
    """One receiving address bound to one Business, through one live grant.

    ``principal_id`` owns the captured documents. ``grant_id`` is the client
    grant checked again on every capture; a revoked grant stops the route."""

    id: str
    recipient: str
    space_id: str
    principal_id: str
    granted_by: str
    grant_id: str
    active: bool


@dataclass(frozen=True)
class EmailDelivery:
    id: str
    provider: str
    external_id: str
    recipients: tuple[str, ...]
    route_id: str | None
    space_id: str | None
    principal_id: str | None
    state: DeliveryState
    original_document_id: str | None
    received_at: datetime
    updated_at: datetime
    lease_token: str | None
    attempts: int
    error_code: str | None
    subject: str | None
    sender: str | None
    sent_at: str | None
    text_body: str | None
    available_at: datetime | None = None


@dataclass(frozen=True)
class EmailDeliveryPart:
    id: str
    filename: str
    media_type: str
    state: PartState
    document_id: str | None
    error_code: str | None
