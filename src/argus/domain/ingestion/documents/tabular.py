"""Bounded, inert flat-file decoding. Values remain evidence, never postings.

No workbook evaluator, network client or filesystem extraction is used. Formula
workbooks are refused rather than trusting potentially stale cached amounts.
"""

from __future__ import annotations

import csv
import io
import json
import posixpath
import time
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from argus.domain.ingestion.documents.models import DocumentExtractionError

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FLAT_MEDIA_TYPES = frozenset({"text/plain", "text/csv", XLSX})
MAX_TEXT_BYTES = 200_000
MAX_ROWS = 300
MAX_COLUMNS = 64
MAX_CELL_CHARS = 4096
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_ENTRY_BYTES = 2 * 1024 * 1024
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
# Built-in Excel number formats that are calendar dates; time-only formats
# (18 to 21) never become a date.
_DATE_FORMATS = frozenset({"14", "15", "16", "17", "22"})


def _fail(code: str = "invalid_document") -> None:
    raise DocumentExtractionError(code)


def _text(content: bytes) -> str:
    if len(content) > MAX_TEXT_BYTES:
        _fail("document_text_limit")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError:
        _fail()
    if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
        _fail()
    return text


def _xml(content: bytes) -> ET.Element:
    # Requiring UTF-8 also prevents UTF-16 encodings concealing declarations.
    try:
        text = content.decode("utf-8-sig")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            _fail("unsupported_spreadsheet_content")
        return ET.fromstring(text)
    except (UnicodeError, ET.ParseError):
        _fail()


def _row(values: list[str]) -> str:
    if len(values) > MAX_COLUMNS or any(len(v) > MAX_CELL_CHARS for v in values):
        _fail("document_cell_limit")
    return json.dumps(values, ensure_ascii=False)


def flat_text(content: bytes, media_type: str) -> tuple[int, str]:
    """Pages and page-labelled text for a TXT, CSV or XLSX source."""
    if media_type == "text/plain":
        return 1, _text(content)
    if media_type == "text/csv":
        try:
            rows = []
            for row in csv.reader(io.StringIO(_text(content)), strict=True):
                if len(rows) >= MAX_ROWS:
                    _fail("document_row_limit")
                rows.append(_row(row))
            return 1, _bounded("Page 1 (CSV rows, including header):\n" + "\n".join(rows))
        except csv.Error:
            _fail()
    if media_type != XLSX:
        _fail("unsupported_media_type")
    try:
        return _workbook(content)
    except DocumentExtractionError:
        raise
    except (
        zipfile.BadZipFile,
        RuntimeError,
        OSError,
        ValueError,
        KeyError,
        IndexError,
        OverflowError,
    ):
        _fail()


def _bounded(text: str) -> str:
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        _fail("document_text_limit")
    return text


def _workbook(content: bytes) -> tuple[int, str]:
    deadline = time.monotonic() + 5
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        if len(entries) > 100 or len(set(names)) != len(names):
            _fail("document_archive_limit")
        if sum(e.file_size for e in entries) > MAX_ARCHIVE_BYTES:
            _fail("document_archive_limit")
        documents = {}
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename:
                _fail()
            if entry.flag_bits & 1 or entry.compress_type not in (0, 8):
                _fail("unsupported_spreadsheet_content")
            if (
                entry.file_size > MAX_ENTRY_BYTES
                or entry.file_size > max(1, entry.compress_size) * 200
            ):
                _fail("document_archive_limit")
            if any(
                x in entry.filename.lower()
                for x in ("vbaproject", "externallinks/", "embeddings/", "activex/")
            ):
                _fail("unsupported_spreadsheet_content")
            if entry.is_dir():
                continue
            with archive.open(entry) as source:
                raw = source.read(MAX_ENTRY_BYTES + 1)
            if len(raw) > MAX_ENTRY_BYTES:
                _fail("document_archive_limit")
            if entry.filename.endswith((".xml", ".rels")):
                root = _xml(raw)
                if any(
                    node.attrib.get("TargetMode", "").lower() == "external"
                    for node in root.iter()
                ):
                    _fail("unsupported_spreadsheet_content")
                documents[entry.filename] = root
            if time.monotonic() > deadline:
                _fail("document_preparation_timeout")
        if "xl/workbook.xml" not in documents or "[Content_Types].xml" not in documents:
            _fail()
        content_types = documents["[Content_Types].xml"]
        if not any(
            n.attrib.get("ContentType") == XLSX + ".main+xml" for n in content_types
        ):
            _fail("unsupported_spreadsheet_content")
        workbook = documents["xl/workbook.xml"]
        relationships = documents.get("xl/_rels/workbook.xml.rels")
        if relationships is None:
            _fail()
        targets = {n.attrib.get("Id"): n.attrib.get("Target", "") for n in relationships}
        sheets = []
        for sheet in workbook.iter(_NS + "sheet"):
            rid = sheet.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            target = targets.get(rid, "")
            path = posixpath.normpath(
                target.lstrip("/") if target.startswith("/") else "xl/" + target
            )
            if not path.startswith("xl/worksheets/") or path not in documents:
                _fail("unsupported_spreadsheet_content")
            sheets.append((path, sheet.attrib.get("name", path)))
        if not 1 <= len(sheets) <= 8:
            _fail("document_page_limit")
        epoch = workbook.find(_NS + "workbookPr")
        date1904 = epoch is not None and epoch.attrib.get("date1904") in ("1", "true")
        styles = documents.get("xl/styles.xml")
        cell_styles = [] if styles is None else list(styles.find(_NS + "cellXfs") or ())
        formats = (
            {}
            if styles is None
            else {
                n.attrib.get("numFmtId"): n.attrib.get("formatCode", "")
                for n in styles.iter(_NS + "numFmt")
            }
        )
        shared = [
            "".join(n.itertext()) for n in documents.get("xl/sharedStrings.xml", ())
        ]
        if len(shared) > MAX_ROWS * MAX_COLUMNS or any(
            len(v) > MAX_CELL_CHARS for v in shared
        ):
            _fail("document_cell_limit")
        output = []
        count = 0
        for page, (name, label) in enumerate(sheets, 1):
            output.append(
                f"Page {page} (sheet {json.dumps(label)}; Excel date epoch {1904 if date1904 else 1900}; source cell references retained):"
            )
            for row in documents[name].iter(_NS + "row"):
                count += 1
                if count > MAX_ROWS:
                    _fail("document_row_limit")
                values = []
                for cell in row.findall(_NS + "c"):
                    if cell.find(_NS + "f") is not None:
                        _fail("spreadsheet_formula_unsupported")
                    value = cell.findtext(_NS + "v", "")
                    if cell.attrib.get("t") == "s":
                        index = int(value)
                        if index < 0:
                            _fail()
                        value = shared[index]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = (
                            "".join(cell.find(_NS + "is").itertext())
                            if cell.find(_NS + "is") is not None
                            else ""
                        )
                    style = cell.attrib.get("s")
                    if style is not None:
                        style_index = int(style)
                        if not 0 <= style_index < len(cell_styles):
                            _fail()
                        format_id = cell_styles[style_index].attrib.get("numFmtId", "0")
                        if (
                            cell.attrib.get("t", "n") == "n"
                            and value
                            and format_id in _DATE_FORMATS
                        ):
                            serial = Decimal(value)
                            if not serial.is_finite() or not 0 <= serial < 2958466:
                                _fail("unsupported_spreadsheet_content")
                            if not date1904 and 60 <= serial < 61:
                                _fail("unsupported_spreadsheet_content")
                            base = (
                                datetime(1904, 1, 1)
                                if date1904
                                else datetime(1899, 12, 30)
                            )
                            if not date1904 and serial < 60:
                                serial += 1
                            date = base + timedelta(days=float(serial))
                            value = (
                                date.date().isoformat()
                                if date.time().isoformat() == "00:00:00"
                                else date.isoformat()
                            )
                        elif format_id != "0":
                            value += f" [number format {format_id}: {formats.get(format_id, 'built-in')}]"
                    values.append(f"{cell.attrib.get('r', '?')}: {value}")
                output.append(_row(values))
            if time.monotonic() > deadline:
                _fail("document_preparation_timeout")
        return len(sheets), _bounded("\n".join(output))
