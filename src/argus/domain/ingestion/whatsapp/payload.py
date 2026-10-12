"""Meta webhook payloads parsed into the three message shapes intake handles.

Only ``messages`` changes for the configured business number are read. Text,
image and document messages become typed values; every other message type and
every delivery status is counted and ignored. Meta adds fields over time, so
unknown fields are ignored rather than rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class PayloadInvalid(ValueError):
    pass


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class _Text(_Loose):
    body: str = Field(max_length=4096)


class _Media(_Loose):
    id: str = Field(min_length=1, max_length=64)
    mime_type: str = Field(default="", max_length=128)
    filename: str | None = Field(default=None, max_length=512)
    caption: str | None = Field(default=None, max_length=1024)


class _Message(_Loose):
    id: str = Field(min_length=1, max_length=256)
    sender: str = Field(alias="from", min_length=1, max_length=32)
    timestamp: str = Field(min_length=1, max_length=12)
    type: str = Field(max_length=32)
    text: _Text | None = None
    image: _Media | None = None
    document: _Media | None = None


class _Metadata(_Loose):
    phone_number_id: str = Field(max_length=64)


class _Value(_Loose):
    metadata: _Metadata
    messages: tuple[_Message, ...] = Field(default=(), max_length=100)
    statuses: tuple[dict, ...] = Field(default=(), max_length=1000)


class _Change(_Loose):
    field: str
    value: _Value | None = None


class _Entry(_Loose):
    changes: tuple[_Change, ...] = Field(default=(), max_length=100)


class _Envelope(_Loose):
    object: Literal["whatsapp_business_account"]
    entry: tuple[_Entry, ...] = Field(max_length=100)


@dataclass(frozen=True)
class TextMessage:
    id: str
    sender: str
    sent_at: datetime
    body: str


@dataclass(frozen=True)
class MediaMessage:
    id: str
    sender: str
    sent_at: datetime
    media_id: str
    mime_type: str
    filename: str
    caption: str | None = None


@dataclass(frozen=True)
class UnsupportedMessage:
    """A message kind intake does not read yet: the sender is told so."""

    id: str
    sender: str
    sent_at: datetime
    kind: str


InboundMessage = TextMessage | MediaMessage | UnsupportedMessage

# Meta's message type names for kinds the owner may send but intake cannot read
# yet. Reactions, system and unknown types stay ignored: they need no answer.
UNSUPPORTED_KINDS = frozenset({"audio", "sticker", "video"})


@dataclass(frozen=True)
class Delivery:
    messages: tuple[InboundMessage, ...]
    ignored_messages: int
    statuses: int
    other_numbers: int


_DEFAULT_NAMES = {"image": "whatsapp-image", "document": "whatsapp-document"}


def _project(message: _Message) -> InboundMessage | None:
    if not message.sender.isascii() or not message.sender.isdigit():
        raise PayloadInvalid("sender")
    if not message.timestamp.isascii() or not message.timestamp.isdigit():
        raise PayloadInvalid("timestamp")
    sent_at = datetime.fromtimestamp(int(message.timestamp), timezone.utc)
    if message.type == "text" and message.text is not None:
        return TextMessage(message.id, message.sender, sent_at, message.text.body)
    if message.type in UNSUPPORTED_KINDS:
        return UnsupportedMessage(message.id, message.sender, sent_at, message.type)
    media = {"image": message.image, "document": message.document}.get(message.type)
    if media is None:
        return None
    return MediaMessage(
        id=message.id,
        sender=message.sender,
        sent_at=sent_at,
        media_id=media.id,
        mime_type=media.mime_type.split(";", 1)[0].strip().lower(),
        filename=(media.filename or _DEFAULT_NAMES[message.type])[:80],
        caption=(media.caption or "").strip() or None,
    )


def parse_delivery(body: bytes, *, phone_number_id: str) -> Delivery:
    try:
        envelope = _Envelope.model_validate_json(body)
    except ValidationError:
        raise PayloadInvalid("envelope") from None
    messages: list[InboundMessage] = []
    ignored = statuses = other = 0
    for entry in envelope.entry:
        for change in entry.changes:
            if change.field != "messages" or change.value is None:
                continue
            value = change.value
            if value.metadata.phone_number_id != phone_number_id:
                other += len(value.messages) + len(value.statuses)
                continue
            statuses += len(value.statuses)
            for message in value.messages:
                projected = _project(message)
                if projected is None:
                    ignored += 1
                else:
                    messages.append(projected)
    return Delivery(tuple(messages), ignored, statuses, other)
