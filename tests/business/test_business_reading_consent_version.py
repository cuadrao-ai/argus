"""Reading stays on across configuration changes until the owner turns it off.
New commands still bind the displayed disclosure and current scope."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest
from argus.api.documents import documents_service
from argus.domain.business import receipt_consent
from argus.domain.ingestion.email_intake.models import EmailDeliveryPart

from tests.business.test_business_api import RECEIPT, Owner, alice  # noqa: F401
from tests.business.test_business_email_api import runtime  # noqa: F401
from tests.document_reads_support import leave_reads_waiting, read_receipt

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
    spanish = alice.reading_status(language="es-419")
    english = alice.reading_status(language="en")

    assert (spanish["scope_version"], spanish["disclosure"]) == (3, SPANISH)
    assert (english["scope_version"], english["disclosure"]) == (3, ENGLISH)
    assert spanish["disclosure_token"] != english["disclosure_token"]


def test_a_command_for_an_earlier_version_reads_nothing(
    alice: Owner,  # noqa: F811
) -> None:
    shown = alice.reading_status(language="es-419")

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
    assert alice.reading_status()["enabled"] is False


def test_a_new_wording_of_the_same_scope_keeps_reading_on(
    alice: Owner,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    accepted = alice.reading(True)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["enabled"] is True

    monkeypatch.setitem(receipt_consent.DISCLOSURES, "en", "Edited words, same scope.")

    shown = alice.reading_status()
    assert (shown["enabled"], shown["consent_id"]) == (
        True,
        accepted.json()["consent_id"],
    )
    assert shown["disclosure"] == "Edited words, same scope."


@pytest.mark.parametrize("change", ["model", "gateway", "scope", "all"])
def test_configuration_changes_keep_the_same_consent_and_queued_read(
    alice: Owner,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    faker,  # noqa: ANN001
    change: str,
) -> None:
    leave_reads_waiting(monkeypatch)
    accepted = alice.reading(True).json()
    uploaded = alice.upload(content=RECEIPT + faker.uuid4().encode())
    assert uploaded.status_code == 200, uploaded.text
    connection_id = uploaded.json()["id"]
    assert uploaded.json()["status"] == "queued"
    documents = documents_service()
    setting = documents.business_receipt_consent
    scope = alice.scope()
    saved = deepcopy(setting._rows[(scope.owner.space_id, scope.person_id)])
    route = deepcopy(accepted["route"])
    if change in {"model", "all"}:
        route["interpretation"][0]["model"] = faker.uuid4()
    if change in {"gateway", "all"}:
        route["gateway"] = faker.uuid4()
    if change in {"scope", "all"}:
        monkeypatch.setattr(receipt_consent, "SCOPE_VERSION", accepted["scope_version"] + 1)
    monkeypatch.setattr(setting, "route_resolver", lambda: route)

    shown = alice.reading_status()
    assert (shown["enabled"], shown["consent_id"]) == (True, accepted["consent_id"])
    assert setting._rows[(scope.owner.space_id, scope.person_id)] == saved
    assert documents._reading_allowed(scope.person_id, connection_id)
    asyncio.run(read_receipt(documents, scope.person_id, connection_id))
    assert alice.detail(connection_id)["activity"]["state"] == "ready"


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


def test_turning_reading_back_on_never_reads_the_email_itself(
    alice: Owner,  # noqa: F811
    stub,  # noqa: ANN001
    runtime,  # noqa: ANN001, F811
) -> None:
    assert alice.reading(True).status_code == 200
    assert alice.reading(False).status_code == 200
    space_id = alice.scope().owner.space_id
    store = runtime.store
    route = store.create_route(
        recipient="recibos-00000001@recibos.example.test",
        space_id=space_id,
        principal_id=alice.scope().person_id,
        granted_by=alice.scope().person_id,
        grant_id=str(uuid4()),
    )
    store.enqueue(
        "resend",
        str(uuid4()),
        (route.recipient,),
        route_id=route.id,
        space_id=space_id,
        principal_id=route.principal_id,
    )
    claimed = store.claim()
    original = alice.upload(
        content=b"Subject: Factura 0041\r\n\r\nForwarded receipt",
        consent=False,
        name="forwarded.eml",
        media_type="message/rfc822",
    ).json()
    attachment = alice.upload(content=RECEIPT, consent=False).json()
    store.update(claimed, original_document_id=original["id"], subject="Factura 0041")
    store.put_part(
        claimed,
        EmailDeliveryPart(
            "1.2", "recibo.png", "image/png", "captured", attachment["id"], None
        ),
    )
    store.finish(claimed, "captured")
    assert alice.detail(original["id"])["email_original"] is True
    assert alice.detail(attachment["id"])["activity"]["state"] == "saved_unread"
    assert stub.calls == []

    again = alice.reading(True)

    assert again.status_code == 200, again.text
    assert stub.calls == [attachment["id"]]
    assert alice.detail(attachment["id"])["activity"]["state"] == "ready"

    assert alice.reading(False).status_code == 200
    assert alice.reading(True).status_code == 200
    assert stub.calls == [attachment["id"]]
