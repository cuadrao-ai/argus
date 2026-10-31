"""WhatsApp intake against in-memory stores; the same cases run on Postgres too."""

from datetime import datetime, timedelta, timezone
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
    UnsupportedMessage,
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
from tests.ingestion.whatsapp_unlinked_cases import UNLINKED_CASES


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


UNLINKED = (
    "Este número aún no está vinculado a un negocio en Cuadrao. "
    "Pídele al administrador el código para vincularlo."
)
RECEIPT_MISSING = "Mándame la foto o el PDF del comprobante."


@pytest.mark.asyncio
async def test_an_unlinked_photo_gets_the_unlinked_line_and_nothing_is_fetched() -> None:
    world = _world()
    await world.deliver(
        cases.image("700000000000991", "wamid.UNKNOWN", cases.STRANGER_PHONE)
    )
    record = world.record("wamid.UNKNOWN")
    assert (record.status, record.error_code, record.connection_id) == (
        "rejected",
        "whatsapp_sender_not_linked",
        None,
    )
    assert world.graph.requests == []
    assert world.transport.bodies() == [UNLINKED]


@pytest.mark.asyncio
async def test_a_repeated_unlinked_delivery_is_not_answered_twice() -> None:
    world = _world()
    message = fixture("text_message.json", id="wamid.U1", text="hola")
    await world.deliver(message)
    await world.deliver(message)
    assert world.transport.bodies() == [UNLINKED]


def test_blocked_file_copy_matches_approved_spanish_and_preserves_english() -> None:
    assert compose_reply("whatsapp_media_invalid", language="es-419") == (
        "No pudimos leer este archivo. Envíalo como foto o PDF."
    )
    assert compose_reply("whatsapp_media_invalid", language="en") == (
        "We couldn't open that file. Send another photo or PDF of the receipt."
    )


@pytest.mark.parametrize("count", [1, 5, 12])
def test_grouped_copy_quotes_one_and_lists_earliest_three(count: int) -> None:
    from argus.domain.ingestion.secrets import SecretBox
    from argus.domain.ingestion.whatsapp.reply_groups import (
        ReplyAttempt,
        ReplyGroup,
        ReplyGroupCodec,
    )
    from argus.domain.ingestion.whatsapp.store import SenderLink

    world = _world()
    codec = ReplyGroupCodec(SecretBox(b"r" * 32), world.keys)
    at = datetime(2026, 10, 16, 19, 42, tzinfo=timezone.utc)
    link = SenderLink(world.alice, "1234", at, "es-419")
    samples = []
    for index in range(count):
        message = MediaMessage(
            f"wamid.GROUP{index}",
            cases.ALICE_PHONE,
            at + timedelta(seconds=index),
            "700000000000991",
            "image/png",
            f"factura_{index}.pdf",
        )
        samples.append(codec.failure(message, link, now=at, wait=120).sample)
    group = ReplyGroup(
        world.keys.sender(cases.ALICE_PHONE),
        world.alice,
        str(uuid4()),
        count,
        samples[:3],
        at,
        at + timedelta(seconds=120),
    )
    payload = codec.payload(ReplyAttempt(str(uuid4()), group, False))
    if count == 1:
        assert payload["context"] == {"message_id": "wamid.GROUP0"}
        assert (
            payload["text"]["body"]
            == "No pudimos leer este archivo. Envíalo como foto o PDF."
        )
    else:
        assert "context" not in payload
        assert payload["text"]["body"] == (
            f"No pudimos leer {count} archivos:\n• factura_0.pdf\n• factura_1.pdf\n• factura_2.pdf\n"
            f"• y {count - 3} más\nEnvíalos como foto o PDF."
        )


@pytest.mark.parametrize(
    "name,mime,expected",
    [
        ("whatsapp-image", "image/png", "foto enviada a las 3:42 p. m."),
        ("", "application/pdf", "archivo enviado a las 3:42 p. m."),
        ("\x00factura\n\u202emayo.pdf", "application/pdf", "facturamayo.pdf"),
        ("a" * 40, "application/pdf", "a" * 29 + "…"),
    ],
)
def test_failed_file_labels_are_safe_and_use_santo_domingo_time(
    name, mime, expected
) -> None:
    from argus.domain.ingestion.whatsapp.reply_groups import file_label

    message = MediaMessage(
        "wamid.LABEL",
        cases.ALICE_PHONE,
        datetime(2026, 10, 16, 19, 42, tzinfo=timezone.utc),
        "700000000000991",
        mime,
        name,
    )
    assert file_label(message) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("fails_twice", [False, True])
async def test_capture_failure_retries_once_before_grouping(fails_twice: bool) -> None:
    from argus.domain.ingestion.whatsapp.intake import CaptureFailed

    from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media

    world = _world()
    await world.link(world.alice, cases.ALICE_PHONE)
    world.transport.sent.clear()
    world.graph.media["700000000000991"] = Media(RECEIPT_PNG, "image/png")
    original = world.intake.destination.capture
    attempts = 0

    async def flaky_capture(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1 or fails_twice:
            raise CaptureFailed("whatsapp_capture_failed")
        return await original(**kwargs)

    world.intake.destination.capture = flaky_capture
    await world.deliver(cases.image("700000000000991", "wamid.RETRY"))
    assert attempts == 2
    assert len(world.store.reply_failures) == int(fails_twice)
    assert len(world.transport.sent) == int(not fails_twice)
    assert world.record("wamid.RETRY").status == (
        "rejected" if fails_twice else "captured"
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
        (FIXTURES / "audio_message.json").read_bytes(), phone_number_id=PHONE_NUMBER_ID
    )
    assert audio.ignored_messages == 0
    assert audio.messages == (
        UnsupportedMessage("wamid.SYNTHETIC0005", "15550101234", recorded, "audio"),
    )
    reaction = parse_delivery(
        encode(fixture("audio_message.json", type="reaction")),
        phone_number_id=PHONE_NUMBER_ID,
    )
    assert (reaction.messages, reaction.ignored_messages) == ((), 1)
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
        "whatsapp_message_unsupported",
        "whatsapp_ai_consent_missing",
        "whatsapp_agent_unavailable",
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
    spanish = "Recibido. Revísalo aquí: https://app.test/biz?receipt=abc"
    assert compose_reply("captured", language="es-419", link=url) == spanish
    assert compose_reply("captured", language=None, link=url) == spanish
    assert compose_reply("captured", language="en", link=url) == (
        "Received. Review it here: https://app.test/biz?receipt=abc"
    )
    assert compose_reply("whatsapp_media_too_large", language="en") == (
        "The file is larger than 10 MB. Send a smaller photo or PDF."
    )
    assert reply_key("captured", None, duplicate=True) == "duplicate"
    assert reply_key("captured", None, reading=True) == "captured_reading"
    assert reply_key("captured", None, duplicate=True, reading=True) == "duplicate"
    assert compose_reply("captured_reading", language="es-419") == (
        "Recibido. Lo estoy leyendo."
    )
    assert compose_reply("captured_reading", language="en") == (
        "Received. I'm reading it."
    )
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


def test_a_reply_that_ends_in_a_link_ends_as_a_sentence_without_one() -> None:
    assert compose_reply("read_ready", language="es-419") == (
        "Ya leímos tu recibo. Revísalo y confírmalo en Cuadrao."
    )


def test_text_only_copy_is_the_fixed_line_in_each_language() -> None:
    assert compose_reply("whatsapp_receipt_missing", language="es-419") == (
        RECEIPT_MISSING
    )
    assert compose_reply("whatsapp_receipt_missing", language="en") == (
        "Send me the photo or PDF of the receipt."
    )


@pytest.mark.parametrize(
    "text",
    [
        "le metí 850 a los materiales",
        "Cuadrao, cuánto llevo gastado este mes?",
        "hola",
        "I paid 400 for paint, as sorry typo",
        "mil pesos de la luz",
    ],
)
@pytest.mark.asyncio
async def test_any_text_from_a_linked_owner_gets_the_same_one_reply(text: str) -> None:
    world = _world()
    await world.link(world.alice, cases.ALICE_PHONE)
    await world.deliver(fixture("text_message.json", id="wamid.ANY", text=text))
    record = world.record("wamid.ANY")
    assert (record.status, record.error_code, record.connection_id) == (
        "rejected",
        "whatsapp_receipt_missing",
        None,
    )
    assert world.transport.bodies()[-1] == RECEIPT_MISSING
    assert world.captures(world.alice) == []


@pytest.mark.asyncio
async def test_a_repeated_linked_text_is_answered_once() -> None:
    world = _world()
    await world.link(world.alice, cases.ALICE_PHONE)
    before = len(world.transport.sent)
    message = fixture("text_message.json", id="wamid.ANY", text="hola")
    await world.deliver(message)
    await world.deliver(message)
    assert world.transport.bodies()[before:] == [RECEIPT_MISSING]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", UNLINKED_CASES, ids=lambda case: case.__name__)
async def test_unlinked_case(case) -> None:  # noqa: ANN001
    await case(_world())
