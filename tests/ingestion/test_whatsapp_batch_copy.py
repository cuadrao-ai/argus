from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys
from argus.domain.ingestion.whatsapp.payload import MediaMessage
from argus.domain.ingestion.whatsapp.replies import compose_reply
from argus.domain.ingestion.whatsapp.reply_groups import (
    BatchOutcomes,
    ReplyAttempt,
    ReplyGroup,
    ReplyGroupCodec,
)
from argus.domain.ingestion.whatsapp.store import SenderLink


def body(
    total: int,
    outcomes: BatchOutcomes,
    *,
    language: str = "es-419",
    names: tuple[str, ...] = (),
    final: bool = False,
    suppressed: bool = False,
    legacy: bool = False,
) -> str:
    at = datetime(2026, 11, 27, 21, 20, tzinfo=timezone.utc)
    sender = "15550107890"
    codec = ReplyGroupCodec(SecretBox(b"w" * 32), WhatsAppKeys("synthetic-sender-secret"))
    link = SenderLink(str(uuid4()), sender[-4:], at, language, str(uuid4()))
    samples = []
    for i, name in enumerate(names or ("whatsapp-image",)):
        msg = MediaMessage(f"wamid.TEST{i}", sender, at, "123", "image/png", name)
        sample = codec.pending(msg, link).sample
        if legacy:
            # Before W11 the encrypted label could include a link.
            envelope = {
                "sender": sender,
                "message_id": msg.id,
                "label": name,
                "language": language,
            }
            sealed = codec.box.seal(
                json.dumps(envelope), source="whatsapp-reply", connection_id=sample["key"]
            )
            sample = {**sample, "sealed": base64.b64encode(sealed).decode("ascii")}
        samples.append(sample)
    if names:
        outcomes = replace(outcomes, failure_keys=tuple(s["key"] for s in samples))
    group = ReplyGroup(
        codec.keys.sender(sender),
        link.destination_owner_id,
        link.id,
        total,
        samples,
        at,
        at,
    )
    attempt = ReplyAttempt(str(uuid4()), group, final, outcomes, suppressed)
    return codec.payload(attempt)["text"]["body"]


def test_drawn_mixed_ten_has_one_exact_reply() -> None:
    result = body(
        10,
        BatchOutcomes(
            businesses=(("Colmado Doña Rosa", 4), ("Taller Hermanos Peña", 2)),
            held=1,
            duplicates=1,
            not_received=2,
        ),
        names=("whatsapp-image", "whatsapp-image"),
    )
    assert result == (
        "Recibimos 10 facturas, gracias.\nYa están en la Bandeja:\n"
        "• Colmado Doña Rosa: 4\n• Taller Hermanos Peña: 2\n"
        "1 quedó sin negocio. Te espera en Cuadrao.\n1 ya la teníamos.\n"
        "Disculpa, no pudimos recibir 2 archivos:\n"
        "• foto enviada a las 5:20 p. m.\n• foto enviada a las 5:20 p. m.\n"
        "Envíalos como foto o PDF."
    )


def test_forty_files_have_only_five_business_lines() -> None:
    businesses = (
        ("I", 2),
        ("H", 2),
        ("G", 3),
        ("F", 3),
        ("E", 4),
        ("D", 5),
        ("C", 5),
        ("B", 6),
        ("A", 8),
    )
    assert body(40, BatchOutcomes(businesses=businesses, held=2)) == (
        "Recibimos 40 facturas, gracias.\nYa están en la Bandeja:\n"
        "• A: 8\n• B: 6\n• C: 5\n• D: 5\n• E: 4\ny 4 negocios más: 10 facturas\n"
        "2 quedaron sin negocio. Te esperan en Cuadrao."
    )


def test_reading_closes_after_read_limit_and_failed_files() -> None:
    result = body(
        8,
        BatchOutcomes(businesses=(("A", 4),), reading=2, read_tomorrow=3, not_received=2),
        names=("factura.pdf", "whatsapp-image"),
    )
    assert result.splitlines()[-3:] == [
        "Envíalos como foto o PDF.",
        "Hoy llegamos al límite de lecturas. 3 se leerán mañana y no hace falta enviarlas de nuevo.",
        "Las demás se están leyendo. Puedes seguirlas en Cuadrao.",
    ]


@pytest.mark.parametrize(
    "language,notice",
    [
        (
            "es-419",
            "Por hoy no avisaremos más sobre archivos que no podamos recibir. Las facturas válidas siguen entrando.",
        ),
        (
            "en",
            "We won't send more alerts today about files we can't receive. Valid invoices keep coming in.",
        ),
    ],
)
def test_daily_cap_is_the_approved_notice(language: str, notice: str) -> None:
    assert body(1, BatchOutcomes(not_received=1), final=True, language=language) == notice


def test_failure_daily_cap_keeps_saved_counts_in_english() -> None:
    outcomes = BatchOutcomes(businesses=(("A", 1),), not_received=1)
    received = "We received 2 invoices, thank you.\nIt's in your Inbox:\n• A: 1"
    assert body(2, outcomes, final=True, language="en") == (
        received
        + "\nWe won't send more alerts today about files we can't receive. Valid invoices keep coming in."
    )
    assert body(2, outcomes, suppressed=True, language="en") == received


def test_single_result_copy_in_english() -> None:
    assert (
        body(1, BatchOutcomes(duplicates=1), language="en")
        == "We already had this one, thank you. It wasn't saved twice."
    )
    assert body(1, BatchOutcomes(held=1), language="en") == (
        "We received your invoice, thank you.\n1 has no business yet. It's waiting for you in Cuadrao."
    )
    assert body(
        1, BatchOutcomes(not_received=1), names=("invoice.pdf",), language="en"
    ) == (
        "Sorry, we couldn't receive this file.\n• invoice.pdf\nSend it as a photo or PDF."
    )
    assert body(1, BatchOutcomes(reading=1), language="en").endswith(
        "The other one is still being read. You can follow it in Cuadrao."
    )


@pytest.mark.parametrize(
    "language,prefix,suffix",
    [
        (
            "es-419",
            "Hola. Por aquí no respondemos mensajes, solo recibimos facturas.",
            "Envía aquí la foto o el PDF de tus facturas.",
        ),
        (
            "en",
            "Hi. We don't answer messages here, we only receive invoices.",
            "Send a photo or PDF of your invoices here.",
        ),
    ],
)
def test_guidance_and_link_confirmation_share_the_closing_line(
    language: str, prefix: str, suffix: str
) -> None:
    assert (
        compose_reply("whatsapp_receipt_missing", language=language)
        == f"{prefix} {suffix}"
    )
    assert compose_reply("linked", language=language).endswith(" " + suffix)


def test_links_in_names_never_reach_a_reply() -> None:
    result = body(
        2,
        BatchOutcomes(businesses=(("https://example.test", 1),), not_received=1),
        names=("www.example.test/invoice.pdf",),
    )
    assert "example.test" not in result
    assert "1 negocio más" in result
    assert "foto enviada" in result


def test_queued_failure_from_before_the_update_cannot_expose_a_link() -> None:
    result = body(
        1,
        BatchOutcomes(not_received=1),
        names=("https://example.test/file",),
        legacy=True,
    )
    assert result == (
        "Disculpa, no pudimos recibir este archivo.\n"
        "• archivo enviado a las 5:20 p. m.\nEnvíalo como foto o PDF."
    )


def test_full_english_forward_and_failure_sample_cap() -> None:
    result = body(
        21,
        BatchOutcomes(
            businesses=(("A", 2), ("B", 2), ("C", 2), ("D", 2), ("E", 2), ("F", 2)),
            held=2,
            duplicates=2,
            not_received=4,
            reading=1,
            read_tomorrow=2,
        ),
        language="en",
        names=("one.pdf", "two.pdf", "three.pdf"),
    )
    assert result == (
        "We received 21 invoices, thank you.\nThey're in your Inbox:\n"
        "• A: 2\n• B: 2\n• C: 2\n• D: 2\n• E: 2\nand 1 more business: 2 invoices\n"
        "2 have no business yet. They're waiting for you in Cuadrao.\nWe already had 2.\n"
        "Sorry, we couldn't receive 4 files:\n• one.pdf\n• two.pdf\n• three.pdf\n• and 1 more\nSend them as a photo or PDF.\n"
        "We reached today's reading limit. 2 will be read tomorrow, and you don't need to send them again.\n"
        "The other one is still being read. You can follow it in Cuadrao."
    )


def test_recovered_samples_are_not_listed_for_the_remaining_failed_file() -> None:
    result = body(4, BatchOutcomes(businesses=(("A", 3),), not_received=1))
    assert result.splitlines() == [
        "Recibimos 4 facturas, gracias.",
        "Ya están en la Bandeja:",
        "• A: 3",
        "Disculpa, no pudimos recibir este archivo.",
        "Envíalo como foto o PDF.",
    ]
