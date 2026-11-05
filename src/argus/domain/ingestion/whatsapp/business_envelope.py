from __future__ import annotations

import hmac
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from argus.domain.ingestion.secrets import SecretBox, SecretUnreadable
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys
from argus.domain.ingestion.whatsapp.payload import (
    InboundMessage,
    MediaMessage,
    TextMessage,
    UnsupportedMessage,
)


class TextEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    message_id: str = Field(min_length=1, max_length=256)
    sender: str = Field(pattern=r"^[0-9]{1,32}$")
    text: str = Field(min_length=1, max_length=4096)
    sent_at: AwareDatetime

    @classmethod
    def from_message(cls, message: TextMessage) -> TextEnvelope:
        return cls(
            message_id=message.id,
            sender=message.sender,
            text=message.body,
            sent_at=message.sent_at,
        )


class EnvelopeCodec:
    def __init__(self, box: SecretBox, keys: WhatsAppKeys) -> None:
        self.box, self.keys = box, keys

    def seal(self, message: TextMessage) -> bytes:
        return self.box.seal(
            TextEnvelope.from_message(message).model_dump_json(),
            source="whatsapp",
            connection_id=self.keys.message(message.id).hex(),
        )

    def open(
        self, sealed: bytes, *, message_key: bytes, sender_hash: bytes
    ) -> TextEnvelope:
        envelope = TextEnvelope.model_validate_json(
            self.box.open(sealed, source="whatsapp", connection_id=message_key.hex())
        )
        if not hmac.compare_digest(self.keys.message(envelope.message_id), message_key):
            raise SecretUnreadable("whatsapp_message_identity_mismatch")
        if not hmac.compare_digest(self.keys.sender(envelope.sender), sender_hash):
            raise SecretUnreadable("whatsapp_sender_identity_mismatch")
        return envelope


class ClaimEnvelope(BaseModel):
    """One inbound message as it arrived, kept only while its claim is unsettled
    so a lapsed claim can be run again after the process died."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    kind: Literal["text", "media", "unsupported"]
    message_id: str = Field(min_length=1, max_length=256)
    sender: str = Field(min_length=1, max_length=32)
    sent_at: AwareDatetime
    body: str | None = Field(default=None, max_length=4096)
    media_id: str | None = Field(default=None, max_length=64)
    mime_type: str | None = Field(default=None, max_length=128)
    filename: str | None = Field(default=None, max_length=512)
    caption: str | None = Field(default=None, max_length=1024)
    unsupported_kind: str | None = Field(default=None, max_length=32)

    @classmethod
    def from_message(cls, message: InboundMessage) -> ClaimEnvelope:
        common = {
            "message_id": message.id,
            "sender": message.sender,
            "sent_at": message.sent_at,
        }
        if isinstance(message, TextMessage):
            return cls(kind="text", body=message.body, **common)
        if isinstance(message, MediaMessage):
            return cls(
                kind="media",
                media_id=message.media_id,
                mime_type=message.mime_type,
                filename=message.filename,
                caption=message.caption,
                **common,
            )
        return cls(kind="unsupported", unsupported_kind=message.kind, **common)

    def message(self) -> InboundMessage:
        if self.kind == "text":
            return TextMessage(
                self.message_id, self.sender, self.sent_at, self.body or ""
            )
        if self.kind == "media":
            return MediaMessage(
                self.message_id,
                self.sender,
                self.sent_at,
                self.media_id or "",
                self.mime_type or "",
                self.filename or "",
                self.caption,
            )
        return UnsupportedMessage(
            self.message_id, self.sender, self.sent_at, self.unsupported_kind or ""
        )


class ClaimCodec:
    """Seals a claimed message with the ingestion box, bound to its message key."""

    def __init__(self, box: SecretBox, keys: WhatsAppKeys) -> None:
        self.box, self.keys = box, keys

    def seal(self, message: InboundMessage) -> bytes:
        return self.box.seal(
            ClaimEnvelope.from_message(message).model_dump_json(),
            source="whatsapp_claim",
            connection_id=self.keys.message(message.id).hex(),
        )

    def open(
        self, sealed: bytes, *, message_key: bytes, sender_hash: bytes
    ) -> InboundMessage:
        envelope = ClaimEnvelope.model_validate_json(
            self.box.open(
                sealed, source="whatsapp_claim", connection_id=message_key.hex()
            )
        )
        if not hmac.compare_digest(self.keys.message(envelope.message_id), message_key):
            raise SecretUnreadable("whatsapp_message_identity_mismatch")
        if not hmac.compare_digest(self.keys.sender(envelope.sender), sender_hash):
            raise SecretUnreadable("whatsapp_sender_identity_mismatch")
        return envelope.message()
