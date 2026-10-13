"""The DGII QR is decoded deterministically from the page images and only a
link to DGII's own consultation pages counts. The two QR rows say whether
one was there and whether it names what the read found; a mismatch is a row
to review with both values, never an overwrite."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from argus.domain.business.contracts.checks import DgiiQr
from argus.domain.ingestion.documents.dgii_qr import (
    fill_from_qr,
    parse_dgii_url,
    qr_checks,
    read_dgii_qr,
    tipo_ecf_of,
    with_qr,
)
from argus.domain.ingestion.documents.models import (
    DocumentExtractionError,
    ReceiptDetails,
)
from argus.domain.ingestion.documents.preparation import prepare_document

from tests.dgii_qr_support import (
    CODE,
    ENCF,
    RNC,
    TOTAL,
    URL,
    blank_png,
    qr_email,
    qr_jpeg,
    qr_page_png,
    qr_pdf,
    qr_png,
)

NOW = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)


def test_a_dgii_link_decodes_to_typed_facts_from_png_jpeg_and_a_full_page():
    for image in (qr_png(), qr_jpeg(), qr_page_png()):
        qr = read_dgii_qr((image,))
        assert qr is not None
        assert (qr.host, qr.rnc_emisor, qr.encf, qr.monto_total, qr.codigo_seguridad) == (
            "fc.dgii.gov.do",
            RNC,
            ENCF,
            TOTAL,
            CODE,
        )
        assert qr.url == URL
        assert (qr.fecha_emision, qr.fecha_firma, qr.rnc_comprador) == (None, None, None)


def test_preparation_decodes_the_qr_from_an_image_a_pdf_page_and_an_email_attachment():
    assert prepare_document(qr_jpeg(), "image/jpeg").dgii_qr.encf == ENCF
    assert prepare_document(qr_email(), "message/rfc822").dgii_qr.encf == ENCF
    try:
        prepared = prepare_document(qr_pdf(), "application/pdf")
    except DocumentExtractionError as error:
        if error.code == "document_tools_unavailable":
            pytest.skip("PDF tools are not installed here")
        raise
    assert prepared.dgii_qr is not None and prepared.dgii_qr.encf == ENCF


@pytest.mark.parametrize(
    "text",
    [
        "https://example.com/eCF/ConsultaTimbreFC?RncEmisor=1&ENCF=E320000000001",
        "http://fc.dgii.gov.do/eCF/ConsultaTimbreFC?RncEmisor=1&ENCF=E320000000001",
        "https://fc.dgii.gov.do.evil.example/x?RncEmisor=1&ENCF=E320000000001",
        "https://fc.dgii.gov.do:8443/x?RncEmisor=1&ENCF=E320000000001",
        "https://fc.dgii.gov.do/eCF/ConsultaTimbreFC?MontoTotal=1",
        "hola",
        "",
    ],
)
def test_anything_but_a_dgii_consultation_link_decodes_to_nothing(text):
    assert parse_dgii_url(text) is None
    if text:
        assert read_dgii_qr((qr_png(text),)) is None


def test_the_other_dgii_page_its_optional_fields_and_case_insensitive_keys():
    text = (
        "https://ecf.dgii.gov.do/ecf/consultatimbre?rncemisor=131111222&RncComprador=101000000"
        "&encf=E310000000777&FechaEmision=09-10-2026&montototal=1500.00"
        "&FechaFirma=09-10-2026%2014:05:00&CODIGOSEGURIDAD=xYz987"
    )
    qr = parse_dgii_url(text)
    assert qr is not None
    assert (qr.host, qr.encf, qr.rnc_comprador, qr.fecha_emision, qr.fecha_firma) == (
        "ecf.dgii.gov.do",
        "E310000000777",
        "101000000",
        date(2026, 10, 9),
        "09-10-2026 14:05:00",
    )
    assert tipo_ecf_of(qr.encf) == "31"
    assert tipo_ecf_of("nope") is None


def test_hostile_values_read_as_absent_and_nothing_raises():
    base = "https://fc.dgii.gov.do/x?RncEmisor=131111222&ENCF=E320000001234"
    assert parse_dgii_url(base + "&MontoTotal=NaN").monto_total is None
    assert parse_dgii_url(base + "&MontoTotal=1e999999999").monto_total is None
    assert parse_dgii_url(base + "&CodigoSeguridad=" + "A" * 65).codigo_seguridad is None
    assert parse_dgii_url(base + "&FechaEmision=31-02-2026").fecha_emision is None
    assert (
        parse_dgii_url("https://fc.dgii.gov.do/x?RncEmisor=" + "1" * 65 + "&ENCF=E1")
        is None
    )
    assert parse_dgii_url("https://fc.dgii.gov.do/" + "a" * 3000) is None
    assert read_dgii_qr((b"not an image", blank_png())) is None
    assert read_dgii_qr(()) is None


def test_the_first_dgii_qr_wins_over_other_codes_on_the_page():
    import io

    from PIL import Image

    page = Image.new("RGB", (1200, 700), "white")
    with Image.open(io.BytesIO(qr_png("https://example.com/not-dgii"))) as other:
        page.paste(other.convert("RGB"), (40, 40))
    with Image.open(io.BytesIO(qr_png())) as dgii:
        page.paste(dgii.convert("RGB"), (700, 40))
    buffer = io.BytesIO()
    page.save(buffer, format="PNG")
    assert read_dgii_qr((buffer.getvalue(),)).encf == ENCF


READ = ReceiptDetails(total=TOTAL, rnc=RNC, ecf=ENCF, currency="DOP")
QR = parse_dgii_url(URL)


def by_name(checks):  # noqa: ANN001
    return {check.name: check for check in checks}


def test_the_qr_rows_say_present_and_match_field_by_field():
    rows = by_name(qr_checks(QR, READ))
    assert rows["qr_present"].state == "verified"
    assert rows["qr_present"].detail["host"] == "fc.dgii.gov.do"
    assert rows["qr_matches_read"].state == "verified"
    assert rows["qr_matches_read"].detail == {
        "rnc": f"read={RNC} qr={RNC}",
        "ecf": f"read={ENCF} qr={ENCF}",
        "total": f"read={TOTAL} qr={TOTAL}",
    }
    # A read that printed nothing comparable: present, nothing to match.
    rows = by_name(qr_checks(QR, ReceiptDetails(merchant="Hotel")))
    assert (rows["qr_matches_read"].state, rows["qr_matches_read"].code) == (
        "not_checked",
        "no_read",
    )
    # No QR at all.
    rows = by_name(qr_checks(None, READ))
    assert (rows["qr_present"].code, rows["qr_matches_read"].code) == ("no_qr", "no_qr")


def test_a_mismatch_is_a_row_to_review_with_both_values():
    rows = by_name(
        qr_checks(QR, ReceiptDetails(total="33254.19", rnc="131111223", ecf=ENCF))
    )
    assert (rows["qr_matches_read"].state, rows["qr_matches_read"].code) == (
        "failed",
        "qr_differs",
    )
    assert rows["qr_matches_read"].detail == {
        "rnc": f"read=131111223 qr={RNC}",
        "total": f"read=33254.19 qr={TOTAL}",
    }
    # The NCF the read found stands in for the e-NCF when that is what it printed.
    rows = by_name(qr_checks(QR, ReceiptDetails(ncf=ENCF)))
    assert rows["qr_matches_read"].state == "verified"


def test_a_qr_without_an_xml_gets_a_verification_of_its_own():
    verification = with_qr(None, QR, READ, NOW)
    assert (verification.encf, verification.tipo_ecf) == (ENCF, "32")
    assert [c.name for c in verification.checks] == [
        "qr_present",
        "qr_matches_read",
        "dgii_accepted",
    ]
    assert with_qr(None, None, READ, NOW) is None


def test_fill_only_what_the_read_left_empty_and_name_the_source():
    unknown = {
        "state": "unknown",
        "value": None,
        "origin": "extracted",
        "verified": False,
        "source_ids": ["s"],
    }
    known = lambda value: {**unknown, "state": "known", "value": value}  # noqa: E731
    qr = DgiiQr.model_validate(
        {**QR.model_dump(mode="json"), "fecha_emision": "2026-10-09"}
    )
    # Everything empty: filled from the QR, each with its origin and source.
    facts = fill_from_qr(
        {
            "amount": dict(unknown),
            "occurred_on": dict(unknown),
            "fiscal": {"rnc": dict(unknown), "ecf": dict(unknown)},
        },
        qr,
        "att-1",
        fill_amount=True,
    )
    assert facts["amount"] == {
        "state": "known",
        "value": TOTAL,
        "origin": "qr_decoded",
        "verified": False,
        "source_ids": ["att-1"],
    }
    assert facts["occurred_on"]["value"] == "2026-10-09"
    assert (facts["fiscal"]["rnc"]["value"], facts["fiscal"]["ecf"]["origin"]) == (
        RNC,
        "qr_decoded",
    )
    # The read's values stay, equal or not: a mismatch is never an overwrite.
    facts = fill_from_qr(
        {
            "amount": known("99.00"),
            "occurred_on": known("2026-01-01"),
            "fiscal": {"rnc": known("101000000"), "ecf": known(ENCF)},
        },
        qr,
        "att-1",
        fill_amount=True,
    )
    assert (
        facts["amount"]["value"],
        facts["fiscal"]["rnc"]["value"],
        facts["amount"]["origin"],
    ) == ("99.00", "101000000", "extracted")
    # Several purchases: the amount is left for a person, the rest still fills.
    facts = fill_from_qr(
        {
            "amount": dict(unknown),
            "occurred_on": dict(unknown),
            "fiscal": {"rnc": dict(unknown), "ecf": dict(unknown)},
        },
        qr,
        "att-1",
        fill_amount=False,
    )
    assert (facts["amount"]["state"], facts["fiscal"]["rnc"]["state"]) == (
        "unknown",
        "known",
    )
    assert (
        fill_from_qr({"amount": dict(unknown)}, None, "att-1", fill_amount=True)[
            "amount"
        ]["state"]
        == "unknown"
    )
