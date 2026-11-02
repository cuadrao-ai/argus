"""Synthetic copies of the two published zips, one for the CSV and one for the TXT."""

from __future__ import annotations

import io
import zipfile

CSV_ENTRY = "TMP/RNC_Contribuyentes_Actualizado_02_Nov_2026.csv"
TXT_ENTRY = "TMP/DGII_RNC.TXT"
FILE_TIME = (2026, 10, 18, 0, 30, 0)
HEADER = (
    "RNC",
    "RAZÓN SOCIAL",
    "ACTIVIDAD ECONÓMICA",
    "FECHA DE INICIO OPERACIONES",
    "ESTADO",
    "RÉGIMEN DE PAGOS",
)


def _quoted(field: str) -> str:
    return '"' + field.replace('"', '""') + '"'


def csv_record(
    rnc: str,
    name: str,
    status: str = "ACTIVO",
    *,
    activity: str = "",
    started: str = "",
    regime: str = "",
) -> str:
    return ",".join(_quoted(f) for f in (rnc, name, activity, started, status, regime))


def csv_file(*records: str) -> bytes:
    lines = [",".join(_quoted(field) for field in HEADER), *records]
    return ("\r\n".join(lines) + "\r\n").encode("latin-1")


def txt_record(rnc: str, trade_name: str = "", *, name: str = "NOMBRE") -> str:
    return "|".join([rnc, name, trade_name, "4", "5", "6", "7", "8", "9", "ACTIVO", "11"])


def txt_file(*records: str) -> bytes:
    return ("\r\n".join(records) + "\r\n").encode("latin-1")


def _zip(*entries: tuple[str, bytes], date_time: tuple[int, ...] = FILE_TIME) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for entry, payload in entries:
            archive.writestr(zipfile.ZipInfo(entry, date_time=date_time), payload)
    return buffer.getvalue()


def registry_zip(
    csv_payload: bytes,
    *,
    csv_entry: str = CSV_ENTRY,
    date_time: tuple[int, int, int, int, int, int] = FILE_TIME,
) -> bytes:
    return _zip((csv_entry, csv_payload), date_time=date_time)


def trade_name_zip(*entries: tuple[str, bytes]) -> bytes:
    return _zip(*entries)


def txt_zip(*records: str) -> bytes:
    return trade_name_zip((TXT_ENTRY, txt_file(*records)))
