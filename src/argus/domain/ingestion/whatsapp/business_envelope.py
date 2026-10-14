from __future__ import annotations

import hmac
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from argus.domain.ingestion.secrets import SecretBox, SecretUnreadable
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys
from argus.domain.ingestion.whatsapp.payload import TextMessage


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
