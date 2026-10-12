import io
import zipfile
from pathlib import Path

import pytest
from argus.domain.ingestion.documents.config import SOURCE_MEDIA_TYPES
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.preparation import prepare_document, validate_source
from argus.domain.ingestion.documents.tabular import document_currency, xml_text

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ECF = Path(__file__).parents[1] / "document_extraction_fixtures" / "hotel-ecf.xml"


def workbook(
    sheet='<row r="1"><c r="A1" t="inlineStr"><is><t>Receipt</t></is></c></row>',
    extra=None,
):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Expenses DOP" sheetId="1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + sheet
            + "</sheetData></worksheet>",
        )
        if "xl/_rels/workbook.xml.rels" not in (extra or {}):
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
            )
        for name, value in (extra or {}).items():
            archive.writestr(name, value)
    return stream.getvalue()


def test_every_accepted_source_type_has_a_download_suffix():
    assert SOURCE_MEDIA_TYPES == {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
        "text/plain": "txt",
        "text/csv": "csv",
        XLSX: "xlsx",
        "application/xml": "xml",
        "text/xml": "xml",
        "message/rfc822": "eml",
    }


@pytest.mark.parametrize(
    "content,media,expected",
    [
        (b"Compra en efectivo DOP 150", "text/plain", "DOP 150"),
        (b"date,amount,currency\n2026-10-09,150,DOP\n", "text/csv", "150"),
        (workbook(), XLSX, "Receipt"),
        (ECF.read_bytes(), "text/xml", "E320000001234"),
        (
            b"<recibo><total>150</total><moneda>DOP</moneda></recibo>",
            "application/xml",
            "recibo/total: 150",
        ),
    ],
)
def test_flat_files_feed_shared_preparation_without_execution(content, media, expected):
    validate_source(content, media)
    prepared = prepare_document(content, media)
    assert prepared.pages == 1
    assert not prepared.images
    assert expected in prepared.text


def test_csv_rows_stay_separate_evidence_rows():
    content = (
        b"date,amount,merchant\n2026-10-09,150,Colmado\n2026-10-10,2300,Ferreteria\n"
    )
    prepared = prepare_document(content, "text/csv")
    assert prepared.text.startswith("Page 1 (CSV rows, including header):")
    assert '["2026-10-09", "150", "Colmado"]' in prepared.text
    assert '["2026-10-10", "2300", "Ferreteria"]' in prepared.text


@pytest.mark.parametrize(
    "content,media,code",
    [
        (b"\x00binary", "text/plain", "invalid_document"),
        (b"a,b\n" + b"1,2\n" * 301, "text/csv", "document_row_limit"),
        (
            workbook('<row><c><f>WEBSERVICE("https://evil.test")</f><v>1</v></c></row>'),
            XLSX,
            "spreadsheet_formula_unsupported",
        ),
        (
            workbook(extra={"xl/vbaProject.bin": b"code"}),
            XLSX,
            "unsupported_spreadsheet_content",
        ),
        (workbook(extra={"../escape.xml": b"<x/>"}), XLSX, "invalid_document"),
        (b"not a spreadsheet", XLSX, "invalid_document"),
        (
            b'<!DOCTYPE r [<!ENTITY e SYSTEM "file:///etc/passwd">]><r>&e;</r>',
            "text/xml",
            "unsupported_spreadsheet_content",
        ),
        (
            b'<?xml version="1.0"?><r><a>' + b"x" * 5000 + b"</a></r>",
            "text/xml",
            "document_cell_limit",
        ),
        (b"<r>" + b"<a>1</a>" * 2001 + b"</r>", "text/xml", "document_row_limit"),
        ("<r>\u00e9</r>".encode("utf-16"), "application/xml", "invalid_document"),
        (b"<r><unclosed></r>", "text/xml", "invalid_document"),
    ],
)
def test_unsafe_or_excessive_inputs_fail_before_capture(content, media, code):
    with pytest.raises(DocumentExtractionError, match=code):
        validate_source(content, media)


@pytest.mark.parametrize(
    "extra,code",
    [
        (
            {"xl/sharedStrings.xml": '<!DOCTYPE x [<!ENTITY x "boom">]><sst>&x;</sst>'},
            "unsupported_spreadsheet_content",
        ),
        (
            {
                "xl/_rels/workbook.xml.rels": '<Relationships><Relationship TargetMode="External" Target="https://example.test"/></Relationships>'
            },
            "unsupported_spreadsheet_content",
        ),
        ({"xl/padding.xml": "<x>" + "a" * 100000 + "</x>"}, "document_archive_limit"),
    ],
)
def test_archive_payloads_are_not_trusted(extra, code):
    with pytest.raises(DocumentExtractionError, match=code):
        validate_source(workbook(extra=extra), XLSX)


@pytest.mark.parametrize(
    "epoch,serial,expected",
    [(False, "45292", "2024-01-01"), (True, "43830", "2024-01-01")],
)
def test_workbook_date_styles_and_sheet_currency_are_retained(epoch, serial, expected):
    # Rewrite just workbookPr to exercise both Excel date systems.
    raw = workbook(
        sheet=f'<row><c r="A1" s="0"><v>{serial}</v></c></row>',
        extra={
            "xl/styles.xml": '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cellXfs><xf numFmtId="14"/></cellXfs></styleSheet>'
        },
    )
    stream = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(raw)) as original,
        zipfile.ZipFile(stream, "w") as archive,
    ):
        for entry in original.infolist():
            content = original.read(entry)
            if entry.filename == "xl/workbook.xml":
                content = content.replace(
                    b"<sheets>", f'<workbookPr date1904="{int(epoch)}"/><sheets>'.encode()
                )
            archive.writestr(entry.filename, content)
    prepared = prepare_document(stream.getvalue(), XLSX)
    assert expected in prepared.text
    assert "Expenses DOP" in prepared.text


def test_spreadsheet_honors_configured_page_budget():
    from argus.domain.ingestion.documents.config import DocumentExtractionSettings

    raw = workbook()
    stream = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(raw)) as original,
        zipfile.ZipFile(stream, "w") as archive,
    ):
        for entry in original.infolist():
            content = original.read(entry)
            if entry.filename == "xl/workbook.xml":
                content = content.replace(
                    b"</sheets>",
                    b'<sheet name="Second" sheetId="2" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId2"/></sheets>',
                )
            if entry.filename == "xl/_rels/workbook.xml.rels":
                content = content.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>',
                )
            archive.writestr(entry.filename, content)
        archive.writestr(
            "xl/worksheets/sheet2.xml", original.read("xl/worksheets/sheet1.xml")
        )
    with pytest.raises(DocumentExtractionError, match="document_page_limit"):
        prepare_document(stream.getvalue(), XLSX, DocumentExtractionSettings(max_pages=1))


def test_time_only_excel_style_does_not_invent_a_calendar_date():
    raw = workbook(
        sheet='<row><c r="A1" s="0"><v>0.5</v></c></row>',
        extra={
            "xl/styles.xml": '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cellXfs><xf numFmtId="20"/></cellXfs></styleSheet>'
        },
    )
    prepared = prepare_document(raw, XLSX)
    assert "0.5 [number format 20:" in prepared.text
    assert "1899-" not in prepared.text
    assert "1900-" not in prepared.text


def test_an_ecf_says_its_dop_total_first_and_its_other_currency_as_informational():
    text = xml_text(ECF.read_bytes())
    lines = text.splitlines()
    assert lines[0] == "Page 1 (XML elements, path: value):"
    assert lines[1] == "DGII e-CF electronic invoice. Invoice currency: DOP."
    assert lines[2] == "Total paid in DOP (MontoTotal): 33254.91"
    assert lines[3] == (
        "Total in another currency, informational only (USD, MontoTotalOtraMoneda): 567.30"
    )
    assert "e-NCF (eNCF): E320000001234" in lines
    assert "Issuer RNC (RNCEmisor): 131111222" in lines
    assert "ITBIS (TotalITBIS): 4676.47" in lines
    assert "Propina legal (MontoPropinaLegal): 2598.04" in lines
    # Every element stays as evidence, in document order, with its path.
    assert "ECF/Encabezado/Totales/MontoTotal: 33254.91" in lines
    assert "ECF/DetallesItems/Item/NombreItem: Room Charge" in lines
    assert lines.index("ECF/DetallesItems/Item/NombreItem: Room Charge") < lines.index(
        "ECF/DetallesItems/Item/NombreItem: Minibar"
    )
    assert document_currency(ECF.read_bytes(), "text/xml") == "DOP"


def test_a_plain_xml_names_no_currency_and_keeps_only_its_elements():
    content = b"<recibo><comercio>Colmado</comercio><total>150</total></recibo>"
    assert document_currency(content, "application/xml") is None
    assert document_currency(content, "text/plain") is None
    assert xml_text(content).splitlines() == [
        "Page 1 (XML elements, path: value):",
        "recibo/comercio: Colmado",
        "recibo/total: 150",
    ]
    # An e-CF root without a MontoTotal names nothing either.
    assert document_currency(b"<ECF><Encabezado/></ECF>", "text/xml") is None
