"""The document-reading card's one sentence is the consent the owner agrees to.
It is scope version 3. A command for an earlier version reads nothing, and a
consent counts by its scope version, not by the exact words it stored. The
sentence promises that turning reading back on reads what was saved unread."""

from __future__ import annotations

from argus.domain.business import receipt_consent

from tests.business.test_business_api import RECEIPT, Owner, alice  # noqa: F401

SPANISH = (
    "Leemos con inteligencia artificial los documentos que llegan por correo, por"
    " WhatsApp o que subes en Cuadrao (facturas, recibos y PDF), y preparamos un borrador"
    " de cada uno. Tú lo revisas y lo apruebas. Si lo apagas, se guardan sin leer; si lo"
    " vuelves a activar, también se leen los que quedaron sin leer. Detalles en el aviso"
    " de privacidad."
)
ENGLISH = (
    "We use artificial intelligence to read the documents that come in by email or"
    " WhatsApp, or that you upload to Cuadrao (invoices, receipts and PDFs), and prepare"
    " a draft of each one. You review it and approve it. If you turn it off, they are"
    " saved unread; if you turn it back on, the ones left unread are read too. Details in"
    " the privacy notice."
)


def test_the_card_sentence_is_the_consent_in_both_languages(
    alice: Owner,  # noqa: F811
) -> None:
    spanish = alice.get("/receipt-reading", language="es-419").json()
    english = alice.get("/receipt-reading", language="en").json()

    assert (spanish["scope_version"], spanish["disclosure"]) == (3, SPANISH)
    assert (english["scope_version"], english["disclosure"]) == (3, ENGLISH)
    assert spanish["disclosure_token"] != english["disclosure_token"]


def test_a_command_for_an_earlier_version_reads_nothing(
    alice: Owner,  # noqa: F811
) -> None:
    shown = alice.get("/receipt-reading", language="es-419").json()

    for earlier in (1, 2):
        stale = alice.post(
            "/receipt-reading",
            {
                "enabled": True,
                "scope_version": earlier,
                "disclosure_token": shown["disclosure_token"],
                "language": "es-419",
            },
        )

        assert stale.status_code == 422, stale.text
        assert "business_receipt_consent_changed" in stale.text
    assert alice.get("/receipt-reading").json()["enabled"] is False


def test_a_new_wording_of_the_same_scope_keeps_reading_on(
    alice: Owner,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    accepted = alice.reading(True)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["enabled"] is True

    monkeypatch.setitem(receipt_consent.DISCLOSURES, "en", "Edited words, same scope.")

    shown = alice.get("/receipt-reading").json()
    assert (shown["enabled"], shown["consent_id"]) == (
        True,
        accepted.json()["consent_id"],
    )
    assert shown["disclosure"] == "Edited words, same scope."


def test_turning_reading_back_on_reads_what_was_saved_while_it_was_off(
    alice: Owner,  # noqa: F811
    stub,  # noqa: ANN001
) -> None:
    assert alice.reading(True).status_code == 200
    assert alice.reading(False).status_code == 200
    while_off = alice.upload(content=RECEIPT + b"while-off", consent=False).json()
    assert while_off["activity"]["state"] == "saved_unread"
    assert stub.calls == []

    again = alice.reading(True)

    assert again.status_code == 200, again.text
    assert again.json()["enabled"] is True
    assert alice.detail(while_off["id"])["activity"]["state"] == "ready"
    assert len(stub.calls) == 1
