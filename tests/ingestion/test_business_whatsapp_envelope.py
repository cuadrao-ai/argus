from datetime import datetime, timezone

import pytest
from argus.domain.ingestion.secrets import SecretBox, SecretUnreadable
from argus.domain.ingestion.whatsapp.business_envelope import EnvelopeCodec, TextEnvelope
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys
from argus.domain.ingestion.whatsapp.payload import TextMessage
from faker import Faker


def test_original_text_and_routing_identity_survive_encrypted_restart():
    fake = Faker()
    keys = WhatsAppKeys(fake.password(length=32))
    codec = EnvelopeCodec(SecretBox(bytes(range(32))), keys)
    message = TextMessage(
        fake.uuid4(),
        "15550101234",
        datetime.now(timezone.utc),
        "Pagué 850. No sé la cuenta.",
    )
    sealed = codec.seal(message)
    assert message.body.encode() not in sealed
    assert message.id.encode() not in sealed
    assert message.sender.encode() not in sealed
    restarted = EnvelopeCodec(SecretBox(bytes(range(32))), keys)
    restored = restarted.open(
        sealed,
        message_key=keys.message(message.id),
        sender_hash=keys.sender(message.sender),
    )
    assert restored == TextEnvelope.from_message(message)
    with pytest.raises(SecretUnreadable):
        restarted.open(
            sealed,
            message_key=keys.message(fake.uuid4()),
            sender_hash=keys.sender(message.sender),
        )
    with pytest.raises(SecretUnreadable, match="whatsapp_sender_identity_mismatch"):
        restarted.open(
            sealed,
            message_key=keys.message(message.id),
            sender_hash=keys.sender("15550104321"),
        )
    changed = EnvelopeCodec(SecretBox(bytes(reversed(range(32)))), keys)
    with pytest.raises(SecretUnreadable):
        changed.open(
            sealed,
            message_key=keys.message(message.id),
            sender_hash=keys.sender(message.sender),
        )
