"""WhatsApp intake against in-memory stores; the same cases run on Postgres too."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.business.spaces import InMemorySpaceStore
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.whatsapp.identity import code_candidates, signature_matches
from argus.domain.ingestion.whatsapp.media import trusted_download_url
from argus.domain.ingestion.whatsapp.payload import (
    MediaMessage,
    PayloadInvalid,
    TextMessage,
    parse_delivery,
)
from argus.domain.ingestion.whatsapp.replies import (
    REPLIES,
    compose_reply,
    reply_key,
    reply_payload,
)
from argus.domain.ingestion.whatsapp.store import InMemoryWhatsAppStore

from tests.ingestion import whatsapp_cases as cases
from tests.ingestion.whatsapp_support import (
    FIXTURES,
    PHONE_NUMBER_ID,
    RefusingExtractor,
    encode,
    fixture,
    sign,
)


def _world() -> cases.World:
    clock = cases.Clock()
    connections = InMemoryConnectionRepository()
    hub = IngestionHub(connections, box=None, sink=None, clock=clock)
    documents = DocumentsService(
        hub, InMemoryDocumentStore(connections), RefusingExtractor()
    )
    return cases.build_world(
        documents=documents,
        store=InMemoryWhatsAppStore(),
        clock=clock,
        alice=str(uuid4()),
        bob=str(uuid4()),
        spaces=InMemorySpaceStore(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("case", cases.CASES, ids=lambda case: case.__name__)
async def test_intake_case(case) -> None:  # noqa: ANN001
    await case(_world())


@pytest.mark.asyncio
async def test_english_link_gets_english_only() -> None:
    await cases.english_owner_gets_english_only(_world())


def test_signature_is_hmac_of_the_raw_body() -> None:
    raw = encode(fixture("image_message.json"))
    assert signature_matches("test-app-secret", sign(raw), raw)
    assert not signature_matches("test-app-secret", sign(raw, "other"), raw)
    assert not signature_matches("test-app-secret", sign(raw), raw + b" ")
    assert not signature_matches("test-app-secret", sign(raw)[7:], raw)
    assert not signature_matches("test-app-secret", None, raw)
    assert not signature_matches("test-app-secret", "sha256=ünïcode", raw)


def test_payload_projects_handled_types_and_ignores_the_rest() -> None:
    recorded = datetime(2026, 10, 7, 11, 0, tzinfo=timezone.utc)
    image = parse_delivery(
        (FIXTURES / "image_message.json").read_bytes(), phone_number_id=PHONE_NUMBER_ID
    )
    assert image.messages == (
        MediaMessage(
            id="wamid.SYNTHETIC0001",
            sender="15550101234",
            sent_at=recorded,
            media_id="700000000000001",
            mime_type="image/png",
            filename="whatsapp-image",
            caption="Recibo",
        ),
    )
    text = parse_delivery(
        (FIXTURES / "text_link_code.json").read_bytes(), phone_number_id=PHONE_NUMBER_ID
    )
    assert text.messages == (
        TextMessage("wamid.SYNTHETIC0003", "15550101234", recorded, "CUADRAO ABCD2345"),
    )
    audio = parse_delivery(
        encode(fixture("audio_message.json")), phone_number_id=PHONE_NUMBER_ID
    )
    assert (audio.messages, audio.ignored_messages) == ((), 1)
    status = parse_delivery(
        encode(fixture("status_delivered.json")), phone_number_id=PHONE_NUMBER_ID
    )
    assert (status.messages, status.statuses) == ((), 1)
    other = parse_delivery(
        encode(fixture("image_message.json")), phone_number_id="100000000000002"
    )
    assert (other.messages, other.other_numbers) == ((), 1)
    with pytest.raises(PayloadInvalid):
        parse_delivery(
            b'{"object": "page", "entry": []}', phone_number_id=PHONE_NUMBER_ID
        )
    with pytest.raises(PayloadInvalid):
        parse_delivery(
            encode(fixture("image_message.json", sender="+1 555")),
            phone_number_id=PHONE_NUMBER_ID,
        )


def test_code_candidates_are_structure_only() -> None:
    assert code_candidates("CUADRAO ABCD2345") == ("ABCD2345",)
    assert code_candidates("  cuadrao   abcd2345 ") == ("ABCD2345",)
    assert code_candidates("hola, este es mi código abcd2345 gracias") == ("ABCD2345",)
    assert code_candidates("Cuadrao, le metí 850 a los materiales") == ()
    assert code_candidates("ABCD234O") == ()
    assert code_candidates("15550101234") == ()
    assert code_candidates("ABCD2345 abcd2345 EFGH6789") == ("ABCD2345", "EFGH6789")


def test_every_outcome_code_has_a_reply_without_long_dashes() -> None:
    codes = {
        "captured",
        "duplicate",
        "linked",
        "whatsapp_link_code_invalid",
        "whatsapp_sender_not_linked",
        "whatsapp_receipt_missing",
        "whatsapp_media_unsupported",
        "whatsapp_media_too_large",
        "whatsapp_media_invalid",
        "whatsapp_media_expired",
        "whatsapp_media_unavailable",
        "whatsapp_media_untrusted",
        "whatsapp_capture_failed",
        "whatsapp_processing_failed",
    }
    for code in codes:
        status = code if code in ("captured", "linked") else "rejected"
        assert reply_key(status, None if status != "rejected" else code) in REPLIES
    assert not any(
        "—" in line or "–" in line for pair in REPLIES.values() for line in pair
    )


def test_reply_uses_one_language_spanish_unless_the_owner_is_english() -> None:
    url = "https://app.test/biz?receipt=abc"
    spanish = (
        "Recibimos tu recibo y lo guardamos en tu bandeja. "
        "Revísalo y confírmalo en Cuadrao: https://app.test/biz?receipt=abc"
    )
    assert compose_reply("captured", language="es-419", link=url) == spanish
    assert compose_reply("captured", language=None, link=url) == spanish
    assert compose_reply("captured", language="en", link=url) == (
        "We got your receipt and saved it to your inbox. "
        "Review and confirm it in Cuadrao: https://app.test/biz?receipt=abc"
    )
    assert compose_reply("whatsapp_media_too_large", language="en") == (
        "The file is larger than 10 MB. Send a smaller photo or PDF."
    )
    assert reply_key("captured", None, duplicate=True) == "duplicate"
    assert reply_payload(to="15550101234", in_reply_to="wamid.X", body="Hola") == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "15550101234",
        "context": {"message_id": "wamid.X"},
        "type": "text",
        "text": {"preview_url": False, "body": "Hola"},
    }


def test_trusted_download_url_is_https_on_a_meta_cdn_host_only() -> None:
    assert trusted_download_url("https://lookaside.fbsbx.com/whatsapp_business/a?mid=1")
    assert trusted_download_url("https://scontent.xx.fbcdn.net/v/t1/a.jpg")
    for url in (
        "http://lookaside.fbsbx.com/a",
        "https://attacker.example/a",
        "https://lookaside.fbsbx.com.attacker.example/a",
        "https://fbcdn.net.attacker.example/a",
        "https://lookaside.fbsbx.com:8443/a",
        "https://user:pw@lookaside.fbsbx.com/a",
        "https://user@lookaside.fbsbx.com/a",
    ):
        assert not trusted_download_url(url), url
