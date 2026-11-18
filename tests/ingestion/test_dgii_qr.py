"""The DGII QR is decoded deterministically from the page images and only a
link to DGII's own consultation pages counts. What it carries replaces what
the reader found; a value anyone else gave stays. The two QR rows say whether
one was there and whether it names what the record holds."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.business.contracts.checks import DgiiQr
from argus.domain.business.contracts.facts import BusinessFacts
from argus.domain.ingestion.documents.dgii_qr import (
    fill_from_qr,
    parse_dgii_url,
    read_dgii_qr,
    record_qr_checks,
    tipo_ecf_of,
    with_qr,
)
from argus.domain.ingestion.documents.models import DocumentExtractionError
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
    small_soft_photo,
    timbre_url,
    washed_out_photo,
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
        # Userinfo, in both spellings, is refused, never stripped.
        "https://user:pass@fc.dgii.gov.do/x?RncEmisor=1&ENCF=E320000000001",
        "https://fc.dgii.gov.do@evil.example/x?RncEmisor=1&ENCF=E320000000001",
        "https://evil.example\\@fc.dgii.gov.do/x?RncEmisor=1&ENCF=E320000000001",
        "https://fc.dgii.gov.do\\@evil.example/x?RncEmisor=1&ENCF=E320000000001",
        # A trailing dot, punycode and a look-alike suffix are other hosts.
        "https://fc.dgii.gov.do./x?RncEmisor=1&ENCF=E320000000001",
        "https://xn--fc-dgii-gov-do.example/x?RncEmisor=1&ENCF=E320000000001",
        "https://fc.dgii.gov.do.example/x?RncEmisor=1&ENCF=E320000000001",
        "https://fcdgii.gov.do/x?RncEmisor=1&ENCF=E320000000001",
        "https://fc.dgii.gov.do:443/x?RncEmisor=1&ENCF=E320000000001",
        # Text that does not even split as a URL is not a link, and nothing raises.
        "https://fc.dgii.gov.do:99999/x?RncEmisor=1&ENCF=E320000000001",
        "https://fc.dgii.gov.do:abc/x?RncEmisor=1&ENCF=E320000000001",
        "https://[x/",
        "https://[x/?RncEmisor=1&ENCF=E320000000001",
    ],
)
def test_anything_but_a_dgii_consultation_link_decodes_to_nothing(text):
    assert parse_dgii_url(text) is None
    if text:
        assert read_dgii_qr((qr_png(text),)) is None


@pytest.mark.parametrize(
    "text",
    [
        "https://fc.dgii.gov.do:99999/x?RncEmisor=1&ENCF=E320000000001",
        "https://fc.dgii.gov.do:abc/x?RncEmisor=1&ENCF=E320000000001",
        "https://[x/",
    ],
)
def test_a_qr_that_does_not_split_as_a_url_never_fails_the_capture(text):
    prepared = prepare_document(qr_jpeg(text), "image/jpeg")
    assert prepared.dgii_qr is None
    assert prepare_document(qr_email(text), "message/rfc822").dgii_qr is None


def test_the_model_itself_refuses_a_link_that_is_not_dgii_when_read_back():
    import pydantic

    good = parse_dgii_url(URL).model_dump(mode="json")
    assert DgiiQr.model_validate(good).host == "fc.dgii.gov.do"
    for bad in (
        {**good, "url": "https://evil.example/x?RncEmisor=1&ENCF=E1"},
        {**good, "url": "http://fc.dgii.gov.do/x?RncEmisor=1&ENCF=E1"},
        {**good, "url": "https://u:p@fc.dgii.gov.do/x?RncEmisor=1&ENCF=E1"},
        {**good, "url": "https://fc.dgii.gov.do:8443/x?RncEmisor=1&ENCF=E1"},
        {**good, "url": "https://fc.dgii.gov.do:abc/x"},
        {**good, "host": "evil.example"},
        {**good, "host": "ecf.dgii.gov.do"},  # the host must be the link's host
    ):
        with pytest.raises(pydantic.ValidationError):
            DgiiQr.model_validate(bad)


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


QR = parse_dgii_url(URL)


def by_name(checks):  # noqa: ANN001
    return {check.name: check for check in checks}


def test_the_qr_rows_say_present_and_compare_nothing_before_the_merge():
    verification = with_qr(None, QR, NOW)
    assert (verification.encf, verification.tipo_ecf) == (ENCF, "32")
    assert [c.name for c in verification.checks] == [
        "qr_present",
        "qr_matches_read",
        "dgii_accepted",
    ]
    rows = by_name(verification.checks)
    assert rows["qr_present"].state == "verified"
    assert rows["qr_present"].detail["host"] == "fc.dgii.gov.do"
    assert (rows["qr_matches_read"].state, rows["qr_matches_read"].code) == (
        "not_checked",
        "no_read",
    )
    assert rows["qr_matches_read"].read_vs_qr == {}
    # No QR beside an e-CF: both rows say so. No QR and no e-CF: nothing.
    rows = by_name(with_qr(verification, None, NOW).checks)
    assert (rows["qr_present"].code, rows["qr_matches_read"].code) == ("no_qr", "no_qr")
    assert with_qr(None, None, NOW) is None


@pytest.mark.parametrize("photo", [small_soft_photo, washed_out_photo])
def test_a_code_the_plain_decode_misses_is_read_on_a_retry(photo, faker):  # noqa: ANN001
    issued = date(2026, 11, 5)
    url = timbre_url(faker, issued=issued)
    qr = read_dgii_qr((photo(url),))
    assert qr is not None
    assert (qr.url, qr.fecha_emision) == (url, issued)
    assert prepare_document(photo(url), "image/png").dgii_qr == qr


@pytest.mark.parametrize("photo", [small_soft_photo, washed_out_photo])
def test_a_retry_still_ignores_a_code_that_is_not_dgii(photo, faker):  # noqa: ANN001
    assert read_dgii_qr((photo(f"https://{faker.domain_name()}/app?mesa=12"),)) is None
    assert read_dgii_qr((blank_png((1600, 1200)),)) is None


def retry_attempts(image: bytes) -> list[str]:
    """The retry passes the decoder logged for one page, as their names."""

    from loguru import logger

    lines: list[str] = []
    sink = logger.add(lines.append, format="{message}")
    try:
        read_dgii_qr((image,))
    finally:
        logger.remove(sink)
    return [
        line.strip().rpartition("attempt=")[2]
        for line in lines
        if "dgii_qr_decoded_on_retry" in line
    ]


def test_the_cheapest_retry_runs_first_and_a_hit_builds_no_enlargement(
    faker,  # noqa: ANN001
    monkeypatch,  # noqa: ANN001
):
    from PIL import Image

    enlarged: list[tuple[int, int]] = []
    resize = Image.Image.resize

    def spy(self, size, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        enlarged.append(size)
        return resize(self, size, *args, **kwargs)

    url = timbre_url(faker, issued=date(2026, 11, 5))
    faded, soft, clear = washed_out_photo(url), small_soft_photo(url), qr_page_png(url)
    monkeypatch.setattr(Image.Image, "resize", spy)
    assert retry_attempts(faded) == ["autocontrast"]
    assert enlarged == []
    # A code only the enlargement reads pays for the cheaper retry first.
    assert retry_attempts(soft) == ["x2"]
    assert enlarged == [(3200, 2400)]
    assert retry_attempts(clear) == []


def test_a_page_without_a_code_is_enlarged_once_and_only_within_the_limit(
    monkeypatch,  # noqa: ANN001
):
    from PIL import Image

    enlarged: list[tuple[int, int]] = []
    resize = Image.Image.resize

    def spy(self, size, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        enlarged.append(size)
        return resize(self, size, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "resize", spy)
    assert read_dgii_qr((blank_png((1600, 1200)),)) is None
    assert enlarged == [(3200, 2400)]
    # An enlargement over the pixel limit is never built.
    assert read_dgii_qr((blank_png((3300, 3100)),)) is None
    assert enlarged == [(3200, 2400)]


SOURCE = str(uuid4())
UNKNOWN = {
    "state": "unknown",
    "value": None,
    "origin": "extracted",
    "verified": False,
    "source_ids": [SOURCE],
}
DATED = DgiiQr.model_validate(
    {**QR.model_dump(mode="json"), "fecha_emision": "2026-11-05"}
)


def known(value: object, origin: str = "extracted") -> dict:
    return {**UNKNOWN, "state": "known", "value": value, "origin": origin}


def read_facts(**fiscal: dict) -> dict:
    """A read whose date, amount and RNC differ from the QR; its e-NCF agrees."""

    return {
        "amount": known("99.00"),
        "occurred_on": known("2027-12-31"),
        "fiscal": {"rnc": known("101000000"), "ecf": known(ENCF), **fiscal},
    }


def merge(
    facts: dict,
    qr: DgiiQr | None = DATED,
    source: object = SOURCE,
    *,
    fill_amount: bool = True,
    fill_rnc: bool = True,
) -> dict:
    return fill_from_qr(facts, qr, source, fill_amount=fill_amount, fill_rnc=fill_rnc)


def test_the_qr_fills_what_the_read_left_empty_and_names_the_source():
    source = uuid4()
    facts = merge(
        {
            "amount": dict(UNKNOWN),
            "occurred_on": dict(UNKNOWN),
            "fiscal": {"rnc": dict(UNKNOWN), "ecf": dict(UNKNOWN)},
        },
        source=source,
    )
    assert facts["amount"] == {
        "state": "known",
        "value": TOTAL,
        "origin": "qr_decoded",
        "verified": False,
        "source_ids": [str(source)],
    }
    assert facts["occurred_on"]["value"] == "2026-11-05"
    assert (facts["fiscal"]["rnc"]["value"], facts["fiscal"]["ecf"]["origin"]) == (
        RNC,
        "qr_decoded",
    )
    assert merge({"amount": dict(UNKNOWN)}, None)["amount"]["state"] == "unknown"


def test_the_qr_replaces_what_the_reader_found_and_keeps_what_agrees():
    facts = merge(read_facts())
    assert {
        name: (fact["value"], fact["origin"])
        for name, fact in (
            ("amount", facts["amount"]),
            ("occurred_on", facts["occurred_on"]),
            ("rnc", facts["fiscal"]["rnc"]),
            ("ecf", facts["fiscal"]["ecf"]),
        )
    } == {
        "amount": (TOTAL, "qr_decoded"),
        "occurred_on": ("2026-11-05", "qr_decoded"),
        "rnc": (RNC, "qr_decoded"),
        # The reader had the e-NCF right: its value and its origin stand.
        "ecf": (ENCF, "extracted"),
    }
    # Several purchases: no one amount is the total, so the amount is left.
    facts = merge(read_facts(), fill_amount=False)
    assert (facts["amount"]["value"], facts["occurred_on"]["origin"]) == (
        "99.00",
        "qr_decoded",
    )
    # A sale: the record's RNC is the client's, so the QR's issuer leaves it.
    facts = merge(read_facts(), fill_rnc=False)
    assert (facts["fiscal"]["rnc"]["value"], facts["fiscal"]["rnc"]["origin"]) == (
        "101000000",
        "extracted",
    )


@pytest.mark.parametrize("origin", ["member_set", "owner_stated", "matched"])
def test_the_qr_never_replaces_a_value_the_reader_did_not_give(origin):  # noqa: ANN001
    facts = read_facts(rnc=known("101000000", origin))
    facts["occurred_on"] = known("2027-12-31", origin)
    facts["amount"] = {**UNKNOWN, "origin": origin}
    after = merge(facts)
    assert (after["occurred_on"]["value"], after["occurred_on"]["origin"]) == (
        "2027-12-31",
        origin,
    )
    assert (after["fiscal"]["rnc"]["value"], after["amount"]["state"]) == (
        "101000000",
        "unknown",
    )


def test_a_qr_value_the_fact_cannot_hold_leaves_the_read():
    hostile = DATED.model_copy(update={"rnc_emisor": "000000000", "monto_total": "-5"})
    facts = merge(read_facts(), hostile)
    assert (facts["fiscal"]["rnc"]["value"], facts["amount"]["value"]) == (
        "101000000",
        "99.00",
    )
    BusinessFacts.model_validate(facts)


def test_a_disagreement_is_logged_by_field_name_and_never_by_value():
    from loguru import logger

    lines: list[str] = []
    sink = logger.add(lines.append, format="{message}")
    try:
        facts = read_facts(rnc=known("101000000", "member_set"))
        merge(facts)
    finally:
        logger.remove(sink)
    [line] = [line for line in lines if "qr_over_read" in line]
    assert "replaced=2" in line and "kept=1" in line
    assert "amount" in line and "occurred_on" in line and "rnc" in line
    for value in (RNC, TOTAL, "101000000", "99.00", "2026-11-05", "2027-12-31"):
        assert value not in line


def test_the_record_row_compares_what_the_record_holds_after_the_qr_won():
    facts = BusinessFacts.model_validate(merge(read_facts()))
    saved = record_qr_checks(
        with_qr(None, DATED, NOW), DATED, facts, None, amount_is_total=True
    )
    row = by_name(saved.checks)["qr_matches_read"]
    # Only the e-NCF still comes from the read; what the QR gave is not
    # compared with itself, and nothing is left to review.
    assert (row.state, row.code) == ("verified", None)
    assert {k: v.model_dump() for k, v in row.read_vs_qr.items()} == {
        "ecf": {"read": ENCF, "qr": ENCF}
    }
    assert [c.name for c in saved.checks] == [
        "qr_present",
        "qr_matches_read",
        "dgii_accepted",
    ]
    # A value a person holds that differs from the QR is still a row to review.
    held = facts.model_copy(
        update={
            "occurred_on": facts.occurred_on.model_copy(
                update={"value": date(2027, 12, 31), "origin": "member_set"}
            )
        }
    )
    row = by_name(
        record_qr_checks(saved, DATED, held, None, amount_is_total=True).checks
    )["qr_matches_read"]
    assert (row.state, row.code) == ("failed", "qr_differs")
    assert {k: v.model_dump() for k, v in row.read_vs_qr.items()} == {
        "occurred_on": {"read": "2027-12-31", "qr": "2026-11-05"}
    }
    # Several purchases: the total the read showed is what the record holds.
    row = by_name(
        record_qr_checks(saved, DATED, facts, "33254.19", amount_is_total=False).checks
    )["qr_matches_read"]
    assert row.read_vs_qr["total"].model_dump() == {"read": "33254.19", "qr": TOTAL}
    # The NCF the record holds stands in for the e-NCF, and the row carries
    # every field the record holds of its own.
    read = BusinessFacts.model_validate(
        {
            "amount": known(TOTAL),
            "fiscal": {"rnc": known(RNC), "ncf": known(ENCF)},
        }
    )
    row = by_name(
        record_qr_checks(saved, DATED, read, None, amount_is_total=True).checks
    )["qr_matches_read"]
    assert (row.state, row.detail) == ("verified", {})
    assert {k: v.model_dump() for k, v in row.read_vs_qr.items()} == {
        "rnc": {"read": RNC, "qr": RNC},
        "ecf": {"read": ENCF, "qr": ENCF},
        "total": {"read": TOTAL, "qr": TOTAL},
    }
    # A record that holds nothing of its own has nothing to compare.
    row = by_name(
        record_qr_checks(saved, DATED, BusinessFacts(), None, amount_is_total=True).checks
    )["qr_matches_read"]
    assert (row.state, row.code) == ("not_checked", "no_read")
    assert record_qr_checks(None, None, facts, None, amount_is_total=True) is None


OTHER_ENCF = "E320000009999"


@pytest.mark.parametrize(
    ("field", "read"),
    [
        ("rnc", read_facts()),
        ("ecf", read_facts(ecf=known(OTHER_ENCF))),
        ("ecf", read_facts(ecf=dict(UNKNOWN), ncf=known("B0100000099"))),
        ("ecf", read_facts(ecf=known(OTHER_ENCF), ncf=known("B0100000099"))),
        ("total", read_facts()),
        ("occurred_on", read_facts()),
    ],
)
def test_a_fact_the_qr_gave_is_never_compared_nor_stood_in_for_by_the_read(
    field: str, read: dict
):
    facts = BusinessFacts.model_validate(merge(read))
    # The total the read showed is passed as the save passes it: superseded.
    saved = record_qr_checks(
        with_qr(None, DATED, NOW), DATED, facts, "99.00", amount_is_total=True
    )
    row = by_name(saved.checks)["qr_matches_read"]
    assert field not in row.read_vs_qr
    assert row.state != "failed"
