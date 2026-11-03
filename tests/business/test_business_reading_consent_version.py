"""The receipt-reading card's one sentence is the consent the owner agrees to.
It is scope version 2. A command for an earlier version reads nothing."""

from __future__ import annotations

from tests.business.test_business_api import Owner, alice  # noqa: F401

SPANISH = (
    "Leemos con inteligencia artificial los recibos que llegan por correo, por WhatsApp"
    " o que subes en Cuadrao, y preparamos un borrador de cada uno. Tú lo revisas y lo"
    " apruebas. Si lo apagas, se guardan sin leer."
)
ENGLISH = (
    "We use artificial intelligence to read the receipts that come in by email or"
    " WhatsApp, or that you upload to Cuadrao, and prepare a draft of each one. You"
    " review it and approve it. If you turn it off, they are saved unread."
)


def test_the_card_sentence_is_the_consent_in_both_languages(
    alice: Owner,  # noqa: F811
) -> None:
    spanish = alice.get("/receipt-reading", language="es-419").json()
    english = alice.get("/receipt-reading", language="en").json()

    assert (spanish["scope_version"], spanish["disclosure"]) == (2, SPANISH)
    assert (english["scope_version"], english["disclosure"]) == (2, ENGLISH)
    assert spanish["disclosure_token"] != english["disclosure_token"]


def test_a_command_for_the_earlier_version_reads_nothing(
    alice: Owner,  # noqa: F811
) -> None:
    shown = alice.get("/receipt-reading", language="es-419").json()

    stale = alice.post(
        "/receipt-reading",
        {
            "enabled": True,
            "scope_version": 1,
            "disclosure_token": shown["disclosure_token"],
            "language": "es-419",
        },
    )

    assert stale.status_code == 422, stale.text
    assert "business_receipt_consent_changed" in stale.text
    assert alice.get("/receipt-reading").json()["enabled"] is False
