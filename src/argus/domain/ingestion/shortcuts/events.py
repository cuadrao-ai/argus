"""What a shortcut may send, and the evidence it becomes.

Two kinds of event:

- ``transaction`` from the Wallet trigger: a formatted amount, merchant and
  card or pass name. It becomes ``transaction`` evidence with
  ``status=unknown`` (a tap is not settlement) and ``direction=unknown`` (the
  trigger also fires for declined taps and does not say refund or purchase).
- ``message_capture`` from the Messages trigger or the iOS 27 notification
  trigger: inert text for review, emitted as ``unclassified`` evidence. No
  money field is read from it; the person says what it is.

The shortcut sends the capture time, not a transaction time (Wallet does not
provide one), so a tap's ``occurred_on`` is the capture day in the phone's own
time zone and ``occurred_at`` stays empty.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from argus.domain.ingestion.contract import (
    AccountHint,
    ImportCandidate,
    SourceRef,
    inert_text,
)
from argus.domain.ingestion.shortcuts.amounts import MAX_AMOUNT_TEXT, parse_amount

EventKind = Literal["transaction", "message_capture"]
SourceApp = Literal["wallet", "messages", "notifications"]
MAX_EVENT_BYTES = 4 * 1024
MAX_BATCH_EVENTS = 200
MAX_BATCH_BYTES = 256 * 1024

_PREFIX = {"wallet": "wallet", "messages": "message", "notifications": "notification"}
_MONEY_FIELDS = ("amount", "currency", "merchant", "card", "card_last4")
_TEXT_FIELDS = ("text", "sender")


class ShortcutEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # The shortcut makes one per run (e.g. ISO date plus a random number).
    # Optional: without it the id is derived from the content (see external_id).
    event_id: str | None = Field(default=None, min_length=1, max_length=100)
    kind: EventKind
    source_app: SourceApp
    captured_at: datetime
    amount: str | None = Field(default=None, max_length=MAX_AMOUNT_TEXT)
    currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    merchant: str | None = Field(default=None, max_length=200)
    card: str | None = Field(default=None, max_length=120)
    card_last4: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    sender: str | None = Field(default=None, max_length=120)
    text: str | None = Field(default=None, max_length=1000)

    @field_validator(
        "event_id",
        "amount",
        "currency",
        "merchant",
        "card",
        "card_last4",
        "sender",
        "text",
        mode="before",
    )
    @classmethod
    def _blank_is_missing(cls, value: object) -> object:
        # Shortcuts sends "" for a variable that had no value.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("captured_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must carry a time zone")
        return value

    @model_validator(mode="after")
    def _shape(self) -> ShortcutEvent:
        if self.kind == "transaction":
            if self.source_app != "wallet":
                raise ValueError("transaction events come from the wallet trigger")
            if any(getattr(self, name) is not None for name in _TEXT_FIELDS):
                raise ValueError("transaction events carry no message text")
            return self
        if self.source_app == "wallet":
            raise ValueError("message captures come from messages or notifications")
        if any(getattr(self, name) is not None for name in _MONEY_FIELDS):
            raise ValueError("message captures carry text only; money stays unresolved")
        if inert_text(self.text, 1000) is None:
            raise ValueError("message captures need text")
        return self


class ShortcutEventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    events: list[ShortcutEvent] = Field(min_length=1, max_length=MAX_BATCH_EVENTS)


def external_id(event: ShortcutEvent) -> str:
    """Stable per device: same event id, or same content, is the same evidence.

    Without an event id the content and the capture second name the event.
    Two real purchases with the same card, merchant and amount captured in the
    same second would then collapse into one; a retried run whose capture time
    moved would not. The setup guide always sends an event id for this reason.
    """

    prefix = _PREFIX[event.source_app]
    if event.event_id is not None:
        return f"{prefix}:e:{_digest(event.event_id)}"
    second = event.captured_at.astimezone(timezone.utc).replace(microsecond=0)
    content = {
        "kind": event.kind,
        "at": second.isoformat(),
        "amount": " ".join((event.amount or "").split()),
        "currency": (event.currency or "").upper(),
        "merchant": inert_text(event.merchant, 200),
        "card": inert_text(event.card, 120),
        "last4": event.card_last4,
        "sender": inert_text(event.sender, 120),
        "text": inert_text(event.text, 1000),
    }
    return f"{prefix}:d:{_digest(json.dumps(content, sort_keys=True))}"


def to_candidate(event: ShortcutEvent, *, connection_id: str) -> ImportCandidate:
    source = SourceRef(
        source="shortcuts",
        connection_id=connection_id,
        external_id=external_id(event),
        observed_at=event.captured_at,
    )
    if event.kind == "message_capture":
        return ImportCandidate(
            source=source,
            evidence="unclassified",
            status="unknown",
            description=event.sender,
            excerpt=event.text,
        )
    parsed = parse_amount(event.amount, currency_code=event.currency)
    return ImportCandidate(
        source=source,
        evidence="transaction",
        status="unknown",
        account=AccountHint(name=event.card, mask=event.card_last4),
        occurred_on=event.captured_at.date(),
        amount=parsed.amount,
        currency=parsed.currency,
        direction="unknown",
        kind_hint="unknown",
        merchant=event.merchant,
        # What the phone literally showed, so review can explain any doubt.
        excerpt=event.amount,
        uncertain=parsed.uncertain,
    )


def receipt_id(*, connection_id: str, external_id: str) -> str:
    return _digest(f"{connection_id}|{external_id}")[:24]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]
