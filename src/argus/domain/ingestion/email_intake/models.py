from __future__ import annotations

from dataclasses import dataclass, fields
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
    alias: str | None = None
    alias_normalized: str | None = None
    review_required: bool = False


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
    inbox_group: str | None = None
    auth_result: str | None = None
    review_note: str | None = None
    first_scan: bool = False
    approved: bool = False
    bounce_text: str | None = None
    cap_exempt: bool = False


@dataclass(frozen=True)
class EmailDeliveryPart:
    id: str
    filename: str
    media_type: str
    state: PartState
    document_id: str | None
    error_code: str | None


_ROUTE_BOOL = {"active", "review_required"}
_DELIVERY_TEXT = {
    "id",
    "route_id",
    "space_id",
    "principal_id",
    "original_document_id",
    "lease_token",
}


def route_from_row(row: dict) -> RecipientRoute:
    names = {field.name for field in fields(RecipientRoute)}
    values = {}
    for key, value in row.items():
        if key not in names:
            continue
        if key in _ROUTE_BOOL or value is None:
            values[key] = value
        else:
            values[key] = str(value)
    return RecipientRoute(**values)


def delivery_from_row(row: dict) -> EmailDelivery:
    values = {field.name: row[field.name] for field in fields(EmailDelivery)}
    for key in _DELIVERY_TEXT:
        if values[key] is not None:
            values[key] = str(values[key])
    values["recipients"] = tuple(values["recipients"])
    return EmailDelivery(**values)
