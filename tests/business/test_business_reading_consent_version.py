"""The document-reading card's one sentence is the consent the owner agrees to.
It is scope version 3. A command for an earlier version reads nothing, and a
consent counts by its scope version, not by the exact words it stored."""

from __future__ import annotations

from argus.domain.business import receipt_consent

from tests.business.test_business_api import Owner, alice  # noqa: F401

SPANISH = "PENDIENTE: frase de consentimiento de Iris"
ENGLISH = "PENDING: consent sentence from Iris"


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
