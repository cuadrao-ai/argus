"""Statement readers. Layouts here are synthetic stand-ins, not live exports.

The registry walks ``READER_ORDER``. ``pilot_bank`` is a slot with no layout.
The mapped CSV is the fallback when no earlier reader claims the file.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation

from argus.domain.business.bank.model import (
    READER_ORDER,
    AmountAndSignColumns,
    BankMatchingError,
    CsvMapping,
    NormalizedRow,
    ReaderId,
)

_DATE_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_DMY = re.compile(r"\d{2}/\d{2}/\d{4}")
_POPULAR = ("Fecha", "Descripcion", "Debito", "Credito", "Moneda")
_BHD = ("Fecha Transaccion", "Detalle", "Monto", "Tipo", "Moneda")
_MERCURY = (
    "Date",
    "Description",
    "Amount",
    "Currency",
    "Bank Description",
    "Status",
)
_SANDBOX = ("date", "name", "amount", "iso_currency_code", "pending")
_DEBIT_SIGNS = frozenset({"-", "debit", "d", "cargo"})
_CREDIT_SIGNS = frozenset({"+", "credit", "c", "abono"})


class StatementReader:
    id: ReaderId

    def claims(self, content: bytes) -> bool:
        raise NotImplementedError

    def read(
        self, content: bytes, mapping: CsvMapping | None
    ) -> tuple[NormalizedRow, ...]:
        raise NotImplementedError


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BankMatchingError("invalid_statement") from exc


def _table(content: bytes, delimiter: str) -> tuple[list[str], list[dict[str, str]]]:
    kept = [
        line
        for line in _decode(content).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not kept:
        raise BankMatchingError("invalid_statement")
    reader = csv.DictReader(io.StringIO("\n".join(kept)), delimiter=delimiter)
    if reader.fieldnames is None:
        raise BankMatchingError("invalid_statement")
    header = [name.strip() for name in reader.fieldnames]
    rows: list[dict[str, str]] = []
    for raw in reader:
        rows.append(
            {key.strip(): (value or "").strip() for key, value in raw.items() if key}
        )
    return header, rows


def _header_is(header: Sequence[str], expected: Sequence[str]) -> bool:
    return tuple(header) == tuple(expected)


def _parse_date(value: str) -> date:
    text = value.strip()
    try:
        if _DATE_ISO.fullmatch(text):
            return date.fromisoformat(text)
        if _DATE_DMY.fullmatch(text):
            day, month, year = text.split("/")
            return date(int(year), int(month), int(day))
    except ValueError as exc:
        raise BankMatchingError("invalid_statement") from exc
    raise BankMatchingError("invalid_statement")


def _parse_amount(value: str) -> Decimal:
    text = value.strip().replace(",", "")
    if not text:
        raise BankMatchingError("invalid_statement")
    try:
        return Decimal(text).quantize(Decimal("0.0001"))
    except InvalidOperation as exc:
        raise BankMatchingError("invalid_statement") from exc


def _currency(value: str) -> str:
    text = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", text):
        raise BankMatchingError("invalid_statement")
    return text


def _signed_pair(debit: str, credit: str) -> Decimal:
    if debit and credit:
        raise BankMatchingError("invalid_statement")
    if debit:
        amount = _parse_amount(debit)
        if amount < 0:
            raise BankMatchingError("invalid_statement")
        return -amount
    if credit:
        amount = _parse_amount(credit)
        if amount < 0:
            raise BankMatchingError("invalid_statement")
        return amount
    raise BankMatchingError("invalid_statement")


def _rows(
    table: list[dict[str, str]],
    build,
) -> tuple[NormalizedRow, ...]:
    if not table:
        raise BankMatchingError("invalid_statement")
    return tuple(build(row) for row in table)


class PilotBankReader(StatementReader):
    """Registered slot for the first pilot bank. No layout yet."""

    id: ReaderId = "pilot_bank"

    def claims(self, content: bytes) -> bool:
        del content
        return False

    def read(
        self, content: bytes, mapping: CsvMapping | None
    ) -> tuple[NormalizedRow, ...]:
        del content, mapping
        raise BankMatchingError("layout_not_ready")


class BancoPopularReader(StatementReader):
    id: ReaderId = "banco_popular"

    def claims(self, content: bytes) -> bool:
        try:
            header, _rows = _table(content, ",")
        except BankMatchingError:
            return False
        return _header_is(header, _POPULAR)

    def read(
        self, content: bytes, mapping: CsvMapping | None
    ) -> tuple[NormalizedRow, ...]:
        del mapping
        header, table = _table(content, ",")
        if not _header_is(header, _POPULAR):
            raise BankMatchingError("unsupported_layout")

        def build(row: Mapping[str, str]) -> NormalizedRow:
            return NormalizedRow(
                occurred_on=_parse_date(row["Fecha"]),
                description=row["Descripcion"],
                amount=_signed_pair(row["Debito"], row["Credito"]),
                currency=_currency(row["Moneda"]),
                raw_line=dict(row),
            )

        return _rows(table, build)


class BhdReader(StatementReader):
    id: ReaderId = "bhd"

    def claims(self, content: bytes) -> bool:
        try:
            header, _rows = _table(content, ";")
        except BankMatchingError:
            return False
        return _header_is(header, _BHD)

    def read(
        self, content: bytes, mapping: CsvMapping | None
    ) -> tuple[NormalizedRow, ...]:
        del mapping
        header, table = _table(content, ";")
        if not _header_is(header, _BHD):
            raise BankMatchingError("unsupported_layout")

        def build(row: Mapping[str, str]) -> NormalizedRow:
            kind = row["Tipo"].casefold()
            amount = _parse_amount(row["Monto"])
            if amount < 0:
                raise BankMatchingError("invalid_statement")
            if kind == "d":
                signed = -amount
            elif kind == "c":
                signed = amount
            else:
                raise BankMatchingError("invalid_statement")
            return NormalizedRow(
                occurred_on=_parse_date(row["Fecha Transaccion"]),
                description=row["Detalle"],
                amount=signed,
                currency=_currency(row["Moneda"]),
                raw_line=dict(row),
            )

        return _rows(table, build)


class MercuryReader(StatementReader):
    id: ReaderId = "mercury"

    def claims(self, content: bytes) -> bool:
        try:
            header, _rows = _table(content, ",")
        except BankMatchingError:
            return False
        return _header_is(header, _MERCURY)

    def read(
        self, content: bytes, mapping: CsvMapping | None
    ) -> tuple[NormalizedRow, ...]:
        del mapping
        header, table = _table(content, ",")
        if not _header_is(header, _MERCURY):
            raise BankMatchingError("unsupported_layout")

        def build(row: Mapping[str, str]) -> NormalizedRow:
            return NormalizedRow(
                occurred_on=_parse_date(row["Date"]),
                description=row["Description"],
                amount=_parse_amount(row["Amount"]),
                currency=_currency(row["Currency"]),
                raw_line=dict(row),
            )

        return _rows(table, build)


class SandboxCsvReader(StatementReader):
    id: ReaderId = "sandbox_csv"

    def claims(self, content: bytes) -> bool:
        try:
            header, _rows = _table(content, ",")
        except BankMatchingError:
            return False
        return _header_is(header, _SANDBOX)

    def read(
        self, content: bytes, mapping: CsvMapping | None
    ) -> tuple[NormalizedRow, ...]:
        del mapping
        header, table = _table(content, ",")
        if not _header_is(header, _SANDBOX):
            raise BankMatchingError("unsupported_layout")

        def build(row: Mapping[str, str]) -> NormalizedRow:
            return NormalizedRow(
                occurred_on=_parse_date(row["date"]),
                description=row["name"],
                amount=_parse_amount(row["amount"]),
                currency=_currency(row["iso_currency_code"]),
                raw_line=dict(row),
            )

        return _rows(table, build)


class MappedCsvReader(StatementReader):
    id: ReaderId = "mapped_csv"

    def claims(self, content: bytes) -> bool:
        del content
        return False

    def read(
        self, content: bytes, mapping: CsvMapping | None
    ) -> tuple[NormalizedRow, ...]:
        if mapping is None:
            raise BankMatchingError("invalid_mapping")
        header, table = _table(content, ",")
        needed = [mapping.date_column, mapping.description_column]
        if isinstance(mapping.money, AmountAndSignColumns):
            needed.extend([mapping.money.amount, mapping.money.sign])
        else:
            needed.extend([mapping.money.debit, mapping.money.credit])
        if mapping.currency_column:
            needed.append(mapping.currency_column)
        if any(column not in header for column in needed):
            raise BankMatchingError("invalid_mapping")

        def build(row: Mapping[str, str]) -> NormalizedRow:
            if isinstance(mapping.money, AmountAndSignColumns):
                amount = _apply_sign(
                    _parse_amount(row[mapping.money.amount]),
                    row[mapping.money.sign],
                )
            else:
                amount = _signed_pair(row[mapping.money.debit], row[mapping.money.credit])
            currency = (
                _currency(row[mapping.currency_column]) if mapping.currency_column else ""
            )
            return NormalizedRow(
                occurred_on=_parse_date(row[mapping.date_column]),
                description=row[mapping.description_column],
                amount=amount,
                currency=currency,
                raw_line=dict(row),
            )

        return _rows(table, build)


def _apply_sign(amount: Decimal, sign: str) -> Decimal:
    token = sign.strip().casefold()
    magnitude = abs(amount)
    if token in _DEBIT_SIGNS:
        return -magnitude
    if token in _CREDIT_SIGNS:
        return magnitude
    raise BankMatchingError("invalid_statement")


def default_registry() -> tuple[StatementReader, ...]:
    readers: dict[ReaderId, StatementReader] = {
        "pilot_bank": PilotBankReader(),
        "banco_popular": BancoPopularReader(),
        "bhd": BhdReader(),
        "mercury": MercuryReader(),
        "sandbox_csv": SandboxCsvReader(),
        "mapped_csv": MappedCsvReader(),
    }
    return tuple(readers[reader_id] for reader_id in READER_ORDER)


def select_reader(
    content: bytes,
    mapping: CsvMapping | None,
    reader_id: ReaderId | None,
) -> StatementReader:
    """An explicit reader id wins. Otherwise the first reader that claims the file."""

    by_id = {reader.id: reader for reader in default_registry()}
    if reader_id == "pilot_bank":
        raise BankMatchingError("layout_not_ready")
    if reader_id is not None:
        reader = by_id[reader_id]
        if reader_id == "mapped_csv":
            if mapping is None:
                raise BankMatchingError("invalid_mapping")
            return reader
        if not reader.claims(content):
            raise BankMatchingError("unsupported_layout")
        return reader
    for reader in default_registry():
        if reader.id in {"pilot_bank", "mapped_csv"}:
            continue
        if reader.claims(content):
            return reader
    if mapping is not None:
        return by_id["mapped_csv"]
    raise BankMatchingError("unsupported_layout")
