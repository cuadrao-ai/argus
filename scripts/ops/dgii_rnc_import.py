from __future__ import annotations

import argparse
import array
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
import zlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import NamedTuple

_IDENT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_.")
_TIMEOUT = re.compile(r"^[0-9]+(ms|s|min|h)$")
_SIZE = re.compile(r"^[0-9]+(B|KB|MB|GB)$")
_SIZE_UNIT = {"B": 1, "KB": 1024, "MB": 1024 * 1024, "GB": 1024**3}
_KEPT_LENGTHS = frozenset({9, 11})
_ELEVEN_KEY_BASE = 10**10
_COPY_CHUNK = 1 << 20
_CSV_ENTRY = re.compile(r"RNC_Contribuyentes_Actualizado_.*\.csv", re.IGNORECASE)
_TXT_ENTRY = "DGII_RNC.TXT"
_TXT_PIPES = 10
_TXT_WRAP_LINES = 5
_HEADER_WORDS = ("RNC", "RAZON", "ACTIVIDAD", "FECHA", "ESTADO", "REGIMEN")
_OPTIONAL_FIELDS = ("trade_name", "activity", "start_date", "regime")
_LINE_BREAKS = re.compile(r"\s*[\r\n]+\s*")
_LINE_END = re.compile(r"\r?\n")
_NON_DIGITS = re.compile(r"[^0-9]")
_LETTER = re.compile(r"[^\W\d_]")
_DIGIT = re.compile(r"\d")
_SHAPE_CHARS = 24
_SHAPE_LINES = 5
_ZIP_ERRORS = (OSError, EOFError, RuntimeError, zipfile.BadZipFile, zlib.error)


class RncImportError(Exception):
    pass


@dataclass(frozen=True)
class RncRow:
    rnc: str
    name: str
    trade_name: str | None
    status: str
    file_date: date
    activity: str | None = None
    start_date: date | None = None
    regime: str | None = None


class _Columns(NamedTuple):
    rnc: int
    name: int
    activity: int
    start_date: int
    status: int
    regime: int


@dataclass(frozen=True)
class DroppedRecord:
    reason: str
    digits: int


class _TradeNames(NamedTuple):
    names: dict[str, str]
    failure: str | None


@dataclass(frozen=True)
class ParseResult:
    rows: tuple[RncRow, ...]
    file_date: date
    entry_name: str
    anomaly_count: int
    dropped_count: int = 0
    dropped_sample: tuple[DroppedRecord, ...] = ()
    duplicate_count: int = 0
    row_count: int | None = None
    parsed_bytes: int | None = None
    filled_counts: tuple[tuple[str, int], ...] | None = None
    status_counts: tuple[tuple[str, int], ...] | None = None
    length_counts: tuple[tuple[int, int], ...] | None = None
    spill_path: str | None = None
    header: tuple[str, ...] = ()
    date_shapes: tuple[tuple[str, int], ...] = ()
    activity_chars: int = 0
    trade_name_failure: str | None = None
    trade_name_facts: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class LoadConfig:
    live_table: str = "public.dgii_rnc"
    load_table: str = "public.dgii_rnc_load"
    swap_function: str = "public.dgii_rnc_swap"
    lookup_function: str = "public.dgii_rnc_lookup"
    min_rows: int = 700_000
    anomaly_limit: int = 25
    loss_limit: int = 25
    statement_timeout: str = "5min"
    drop_sample_limit: int = 5
    load_headroom_floor_bytes: int = 170 * 1024 * 1024
    size_limit_bytes: int = 450 * 1024 * 1024


LOAD = LoadConfig()


def load_action(*, enabled: str, dry_run: str, secret_present: str) -> str:
    if dry_run == "true":
        return "load skipped: dry run"
    if enabled != "true":
        return "load skipped: DGII_RNC_LOAD_ENABLED is not true"
    if secret_present != "true":
        return "load skipped: SUPABASE_STAGING_DB_URL is absent"
    return "load"


def parse_zip(
    source: bytes | str | Path,
    config: LoadConfig = LOAD,
    *,
    trade_name_zip: bytes | str | Path | None = None,
    keep_rows: bool = True,
    previous_names: Callable[[], dict[str, str]] | None = None,
) -> ParseResult:
    try:
        with zipfile.ZipFile(_zip_source(source)) as archive:
            info = _registry_entry(archive)
            trade_names = _read_trade_names(trade_name_zip)
            if trade_names.failure is not None and previous_names is not None:
                trade_names = trade_names._replace(names=previous_names())
            with io.TextIOWrapper(
                archive.open(info, "r"), encoding="latin-1", newline=""
            ) as text:
                result = _scan_registry(
                    csv.reader(text),
                    trade_names=trade_names,
                    file_date=_file_date(info),
                    entry_name=info.filename,
                    sample_limit=config.drop_sample_limit,
                    keep_rows=keep_rows,
                )
    except (csv.Error, *_ZIP_ERRORS) as exc:
        raise RncImportError(f"csv is unreadable: {exc}") from None
    if keep_rows:
        _discard_spill(result.spill_path)
        return replace(result, spill_path=None)
    return result


def validate(result: ParseResult, config: LoadConfig) -> None:
    if result.anomaly_count > config.anomaly_limit:
        raise RncImportError(
            f"anomalies {result.anomaly_count} exceed limit {config.anomaly_limit}"
        )
    blank_status = _blank_status(result)
    lost = result.dropped_count + blank_status
    if lost > config.loss_limit:
        raise RncImportError(
            f"lost rows {lost} exceed limit {config.loss_limit}: "
            f"dropped {result.dropped_count}, blank estado {blank_status}"
        )
    seen: set[str] = set()
    for row in result.rows:
        if len(row.rnc) not in _KEPT_LENGTHS or not row.rnc.isdigit():
            raise RncImportError("a kept rnc is not 9 or 11 digits")
        if row.name.strip() == "":
            raise RncImportError("a kept row has a blank name")
        if row.rnc in seen:
            raise RncImportError("a kept rnc repeats")
        seen.add(row.rnc)
    count = _kept_count(result)
    if count < config.min_rows:
        raise RncImportError(f"rows {count} below minimum {config.min_rows}")


def summary_lines(result: ParseResult) -> list[str]:
    lines = [
        f"rows={_kept_count(result)}",
        f"file_date={result.file_date.isoformat()}",
        f"entry={result.entry_name}",
        f"anomalies={result.anomaly_count}",
        f"dropped={result.dropped_count}",
        f"blank_status={_blank_status(result)}",
        f"duplicates={result.duplicate_count}",
        f"parsed_bytes={_parsed_bytes(result)}",
    ]
    filled = _filled_counts(result)
    for field, count in filled:
        lines.append(f"{field}_filled={count}")
    activity_rows = dict(filled)["activity"]
    average = result.activity_chars / activity_rows if activity_rows else 0
    lines.append(f"activity_avg_length={average:.1f}")
    lines.append(_trade_names_line(result))
    for fact, count in result.trade_name_facts:
        lines.append(f"trade_name_{fact}={count}")
    lines.append(f"csv_header={ascii(list(result.header))}")
    for shape, count in result.date_shapes:
        lines.append(f"date_shape {shape}={count}")
    for drop in result.dropped_sample:
        lines.append(f"dropped_sample reason={drop.reason} digits={drop.digits}")
    for status, count in _status_counts(result):
        lines.append(f"status {status}={count}")
    for length, count in _length_counts(result):
        lines.append(f"rnc_length {length}={count}")
    return lines


def parsed_byte_estimate(rows: tuple[RncRow, ...]) -> int:
    return len(copy_text(rows).encode("utf-8"))


def copy_text(rows: tuple[RncRow, ...]) -> str:
    if not rows:
        return ""
    return "".join(_copy_line(row) for row in rows)


def load_script(result: ParseResult, config: LoadConfig) -> str:
    return _copy_header(config) + copy_text(result.rows) + "\\.\n"


def swap_script(config: LoadConfig) -> str:
    function = _sql_ident(config.swap_function)
    timeout = _statement_timeout(config.statement_timeout)
    min_rows = _require_min_rows(config.min_rows)
    return f"SET statement_timeout = '{timeout}';\n" f"SELECT {function}({min_rows});\n"


def previous_names_sql(config: LoadConfig) -> str:
    timeout = _statement_timeout(config.statement_timeout)
    live = _sql_ident(config.live_table)
    return (
        f"SET statement_timeout = '{timeout}';\n"
        "SELECT COALESCE(json_object_agg(rnc, trade_name), '{}') "
        f"FROM {live} WHERE trade_name IS NOT NULL;\n"
    )


def headroom_sql(config: LoadConfig) -> str:
    timeout = _statement_timeout(config.statement_timeout)
    live = _sql_ident(config.live_table)
    load = _sql_ident(config.load_table)
    return (
        f"SET statement_timeout = '{timeout}';\n"
        "SELECT pg_database_size(current_database());\n"
        f"SELECT COALESCE(pg_total_relation_size(to_regclass('{live}')), 0);\n"
        f"SELECT COALESCE(pg_total_relation_size(to_regclass('{load}')), 0);\n"
    )


def size_report_sql(config: LoadConfig) -> str:
    timeout = _statement_timeout(config.statement_timeout)
    live = _sql_ident(config.live_table)
    load = _sql_ident(config.load_table)
    return (
        f"SET statement_timeout = '{timeout}';\n"
        "SELECT pg_database_size(current_database());\n"
        f"SELECT pg_total_relation_size('{live}'::regclass);\n"
        f"SELECT pg_total_relation_size('{load}'::regclass);\n"
    )


def swap_row_count(stdout: str) -> int:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1 or not lines[0].isdigit():
        raise RncImportError("swap did not return one row count")
    return int(lines[0])


def require_swap_count(count: int, config: LoadConfig) -> None:
    minimum = _require_min_rows(config.min_rows)
    if count < minimum:
        raise RncImportError(f"swap returned {count}, below minimum {minimum}")


def _require_min_rows(min_rows: object) -> int:
    if isinstance(min_rows, bool) or not isinstance(min_rows, int) or min_rows < 1:
        raise RncImportError("min_rows must be at least 1")
    return min_rows


def require_load_headroom(
    database_size: int, relation_bytes: int, config: LoadConfig
) -> int:
    floor = config.load_headroom_floor_bytes
    if database_size < 0 or relation_bytes < 0 or floor < 0:
        raise RncImportError(
            f"refusing size database_size {database_size} "
            f"relation_bytes {relation_bytes} floor {floor}"
        )
    headroom = max(floor, relation_bytes)
    peak = database_size + headroom
    if peak > config.size_limit_bytes:
        raise RncImportError(
            f"peak {peak} limit {config.size_limit_bytes} "
            f"database_size {database_size} headroom {headroom} "
            f"relation_bytes {relation_bytes}"
        )
    return peak


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dgii_rnc_import")
    commands = parser.add_subparsers(dest="command", required=True)

    parse_command = commands.add_parser("parse")
    parse_command.add_argument("csv_zip")
    parse_command.add_argument("txt_zip")

    gate_command = commands.add_parser("gate")
    gate_command.add_argument("--enabled", default=None)
    gate_command.add_argument("--dry-run", default=None)
    gate_command.add_argument("--secret-present", default=None)

    load_command = commands.add_parser("load")
    load_command.add_argument("csv_zip")
    load_command.add_argument("txt_zip")

    args = parser.parse_args(argv)
    try:
        if args.command == "gate":
            print(
                load_action(
                    enabled=_flag(args.enabled, "ENABLED"),
                    dry_run=_flag(args.dry_run, "DRY_RUN"),
                    secret_present=_flag(args.secret_present, "SECRET_PRESENT"),
                )
            )
            return 0
        config = _config_from_env()
        loading = args.command == "load"
        database_url = os.environ.get("SUPABASE_STAGING_DB_URL", "") if loading else ""
        result = parse_zip(
            args.csv_zip,
            config,
            trade_name_zip=args.txt_zip,
            keep_rows=False,
            previous_names=(
                (lambda: _previous_trade_names(database_url, config))
                if database_url
                else None
            ),
        )
        try:
            for line in summary_lines(result):
                print(line)
            validate(result, config)
            if not loading:
                return 0
            if database_url == "":
                print("load skipped: SUPABASE_STAGING_DB_URL is absent")
                return 0
            _apply_load(database_url, result, config)
            return 0
        finally:
            _discard_spill(result.spill_path)
    except RncImportError as exc:
        print(exc, file=sys.stderr)
        return 1


def _flag(value: str | None, env_name: str) -> str:
    if value is None:
        return os.environ.get(env_name, "")
    return value


def _config_from_env() -> LoadConfig:
    updates: dict[str, str | int] = {}
    timeout = os.environ.get("DGII_RNC_STATEMENT_TIMEOUT", "").strip()
    if timeout != "":
        updates["statement_timeout"] = _statement_timeout(timeout)
    floor = os.environ.get("DGII_RNC_LOAD_HEADROOM_FLOOR", "").strip()
    if floor != "":
        updates["load_headroom_floor_bytes"] = _size_bytes(floor)
    limit = os.environ.get("DGII_RNC_SIZE_LIMIT", "").strip()
    if limit != "":
        updates["size_limit_bytes"] = _size_bytes(limit)
    if updates == {}:
        return LOAD
    return replace(LOAD, **updates)


def _statement_timeout(value: str) -> str:
    if _TIMEOUT.fullmatch(value) is None:
        raise RncImportError(f"refusing statement_timeout {value!r}")
    return value


def _size_bytes(value: str) -> int:
    match = _SIZE.fullmatch(value)
    if match is None:
        raise RncImportError(f"refusing size {value!r}")
    unit = match.group(1)
    return int(value[: -len(unit)]) * _SIZE_UNIT[unit]


def _zip_source(source: bytes | str | Path) -> io.BytesIO | str | Path:
    return io.BytesIO(source) if isinstance(source, bytes) else source


def _registry_entry(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    entries = archive.infolist()
    matches = [
        info
        for info in entries
        if _CSV_ENTRY.fullmatch(PurePosixPath(info.filename).name)
    ]
    if len(matches) != 1:
        names = [info.filename for info in entries]
        raise RncImportError(
            f"zip must contain one RNC_Contribuyentes_Actualizado_<date>.csv: {names}"
        )
    return matches[0]


def _file_date(info: zipfile.ZipInfo) -> date:
    year, month, day = info.date_time[:3]
    return date(year, month, day)


def _text_chunks(archive: zipfile.ZipFile, info: zipfile.ZipInfo):
    with archive.open(info, "r") as raw:
        while True:
            block = raw.read(_COPY_CHUNK)
            if not block:
                break
            yield block.decode("latin-1")


def _physical_lines(chunks):
    # splitlines() also breaks on U+0085, which Latin-1 must keep inside a name.
    pending = ""
    for chunk in chunks:
        parts = _LINE_END.split(pending + chunk)
        pending = parts.pop()
        if len(pending) > _COPY_CHUNK:
            raise RncImportError(f"txt line is over {_COPY_CHUNK} characters")
        yield from parts
    if pending:
        yield pending


def _read_trade_names(source: bytes | str | Path | None) -> _TradeNames:
    """The TXT adds only trade names, so no failure here may stop the load."""
    if source is None:
        return _TradeNames({}, "no file given")
    try:
        with zipfile.ZipFile(_zip_source(source)) as archive:
            names = _trade_names(archive)
        return _TradeNames(names, None if names else "no trade names parsed")
    except RncImportError as exc:
        return _TradeNames({}, str(exc))
    except _ZIP_ERRORS as exc:
        return _TradeNames({}, type(exc).__name__)


def _trade_names(archive: zipfile.ZipFile) -> dict[str, str]:
    """Column 3 of the TXT by RNC. The CSV has no trade name. Blank stays out."""
    matches = [
        info for info in archive.infolist() if info.filename.endswith(_TXT_ENTRY)
    ]
    if len(matches) != 1:
        raise RncImportError(f"zip holds {len(matches)} {_TXT_ENTRY} entries")
    names: dict[str, str] = {}
    record: list[str] = []
    pipes = 0
    for line in _physical_lines(_text_chunks(archive, matches[0])):
        if not record and line.strip() == "":
            continue
        record.append(line)
        pipes += line.count("|")
        if pipes < _TXT_PIPES and len(record) < _TXT_WRAP_LINES:
            continue
        if pipes == _TXT_PIPES:
            raw, _name, trade_name = " ".join(record).split("|", 3)[:3]
            if trade_name.strip() != "":
                names[_digits(raw)] = trade_name.strip()
        record = []
        pipes = 0
    return names


def _columns(header: list[str]) -> _Columns:
    folded = [
        unicodedata.normalize("NFKD", cell).encode("ascii", "ignore").decode().upper()
        for cell in header
    ]
    picks = []
    for word in _HEADER_WORDS:
        hits = [index for index, cell in enumerate(folded) if word in cell]
        if len(hits) != 1:
            found = [item for item in _HEADER_WORDS if any(item in cell for cell in folded)]
            raise RncImportError(
                f"csv header needs one {word} column: {len(header)} columns, found {found}"
            )
        picks.append(hits[0])
    return _Columns(*picks)


def _scan_registry(
    records,
    *,
    trade_names: _TradeNames,
    file_date: date,
    entry_name: str,
    sample_limit: int,
    keep_rows: bool,
) -> ParseResult:
    index = _RncIndex()
    spill = tempfile.NamedTemporaryFile(prefix="dgii-rnc-copy-", delete=False)
    offsets = array.array("I")
    lengths = array.array("I")
    status_ids = array.array("H")
    filled_bits = array.array("B")
    widths = array.array("B")
    activity_sizes = array.array("I")
    date_shapes: Counter[str] = Counter()
    same_as_name = 0
    kept: list[RncRow] | None = [] if keep_rows else None
    status_names: list[str] = []
    status_lookup: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    length_counts = {9: 0, 11: 0}
    filled = [0] * len(_OPTIONAL_FIELDS)
    anomalies = 0
    dropped_count = 0
    sample: list[DroppedRecord] = []
    duplicates = 0
    parsed_bytes = 0
    spill_path = spill.name
    closed = False

    def close_spill() -> None:
        nonlocal closed
        if not closed:
            spill.close()
            closed = True

    try:
        header = next(records, [])
        columns = _columns(header)
        for fields in records:
            if not any(field.strip() for field in fields):
                continue
            if len(fields) != len(header):
                anomalies += 1
                continue
            outcome = _row_from_fields(fields, columns, trade_names.names, file_date)
            if isinstance(outcome, DroppedRecord):
                dropped_count += 1
                if len(sample) < sample_limit:
                    sample.append(outcome)
                continue
            date_shapes[_value_shape(_clean(fields[columns.start_date]))] += 1
            if _same_text(outcome.trade_name, outcome.name):
                same_as_name += 1
            payload = _copy_line(outcome).encode("utf-8")
            width = len(outcome.rnc)
            activity_size = len(outcome.activity or "")
            bits = _optional_bits(outcome)
            status_id = status_lookup.get(outcome.status)
            if status_id is None:
                status_id = len(status_names)
                status_names.append(outcome.status)
                status_lookup[outcome.status] = status_id
                status_counts[outcome.status] = 0
            key = _rnc_key(outcome.rnc)
            seq = index.find(key)
            offset = spill.tell()
            spill.write(payload)
            nbytes = len(payload)
            if seq is None:
                index.put_new(key, len(offsets))
                offsets.append(offset)
                lengths.append(nbytes)
                status_ids.append(status_id)
                filled_bits.append(bits)
                widths.append(width)
                activity_sizes.append(activity_size)
                if kept is not None:
                    kept.append(outcome)
            else:
                duplicates += 1
                parsed_bytes -= lengths[seq]
                _tally(filled, filled_bits[seq], -1)
                status_counts[status_names[status_ids[seq]]] -= 1
                length_counts[widths[seq]] -= 1
                offsets[seq] = offset
                lengths[seq] = nbytes
                status_ids[seq] = status_id
                filled_bits[seq] = bits
                widths[seq] = width
                activity_sizes[seq] = activity_size
                if kept is not None:
                    kept[seq] = outcome
            parsed_bytes += nbytes
            _tally(filled, bits, 1)
            status_counts[outcome.status] += 1
            length_counts[width] += 1
        close_spill()
        if duplicates:
            compacted = _compact_spill(spill_path, offsets, lengths)
            _discard_spill(spill_path)
            spill_path = compacted
        return ParseResult(
            rows=tuple(kept) if kept is not None else (),
            file_date=file_date,
            entry_name=entry_name,
            anomaly_count=anomalies,
            dropped_count=dropped_count,
            dropped_sample=tuple(sample),
            duplicate_count=duplicates,
            row_count=len(offsets),
            parsed_bytes=parsed_bytes,
            filled_counts=tuple(zip(_OPTIONAL_FIELDS, filled, strict=True)),
            status_counts=tuple(
                (name, status_counts[name])
                for name in sorted(status_counts)
                if status_counts[name]
            ),
            length_counts=tuple(
                (length, length_counts[length])
                for length in sorted(length_counts)
                if length_counts[length]
            ),
            spill_path=spill_path,
            header=tuple(header),
            date_shapes=tuple(date_shapes.most_common(_SHAPE_LINES)),
            activity_chars=sum(activity_sizes),
            trade_name_failure=trade_names.failure,
            trade_name_facts=_trade_name_facts(
                {} if trade_names.failure else trade_names.names, same_as_name
            ),
        )
    except Exception:
        close_spill()
        _discard_spill(spill_path)
        raise


class _RncIndex:
    def __init__(self) -> None:
        self._cap = 1024
        self._mask = self._cap - 1
        self._keys = array.array("Q", [0]) * self._cap
        self._seqs = array.array("I", [0]) * self._cap
        self._count = 0

    def find(self, key: int) -> int | None:
        mask = self._mask
        slot = _mix(key) & mask
        keys = self._keys
        seqs = self._seqs
        while True:
            found = keys[slot]
            if found == 0:
                return None
            if found == key:
                return seqs[slot] - 1
            slot = (slot + 1) & mask

    def put_new(self, key: int, seq: int, *, growing: bool = False) -> None:
        if not growing and (self._count + 1) * 5 > self._cap * 4:
            self._grow()
        mask = self._mask
        slot = _mix(key) & mask
        keys = self._keys
        while keys[slot] != 0:
            slot = (slot + 1) & mask
        keys[slot] = key
        self._seqs[slot] = seq + 1
        self._count += 1

    def _grow(self) -> None:
        old_keys = self._keys
        old_seqs = self._seqs
        self._cap *= 2
        self._mask = self._cap - 1
        self._keys = array.array("Q", [0]) * self._cap
        self._seqs = array.array("I", [0]) * self._cap
        self._count = 0
        for index, key in enumerate(old_keys):
            if key:
                self.put_new(key, old_seqs[index] - 1, growing=True)


def _row_from_fields(
    fields: list[str],
    columns: _Columns,
    trade_names: dict[str, str],
    file_date: date,
) -> RncRow | DroppedRecord:
    raw = _clean(fields[columns.rnc])
    name = _clean(fields[columns.name])
    digits = _digits(raw)
    if len(digits) not in _KEPT_LENGTHS:
        return DroppedRecord(reason="rnc_length", digits=len(digits))
    if name == "":
        return DroppedRecord(reason="blank_name", digits=len(digits))
    return RncRow(
        rnc=digits,
        name=name,
        trade_name=trade_names.get(digits),
        status=_clean(fields[columns.status]),
        file_date=file_date,
        activity=_clean(fields[columns.activity]) or None,
        start_date=_start_date(_clean(fields[columns.start_date])),
        regime=_clean(fields[columns.regime]) or None,
    )


def _clean(value: str) -> str:
    return _LINE_BREAKS.sub(" ", value).strip()


def _digits(value: str) -> str:
    return _NON_DIGITS.sub("", value)


def _start_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None


def _value_shape(value: str) -> str:
    """A value with its letters and digits masked, safe to log from a real file."""
    if value == "":
        return "blank"
    return _DIGIT.sub("d", _LETTER.sub("a", value[:_SHAPE_CHARS]))


def _same_text(trade_name: str | None, name: str) -> bool:
    return trade_name is not None and trade_name.casefold() == name.casefold()


def _trade_name_facts(
    names: dict[str, str], same_as_name: int
) -> tuple[tuple[str, int], ...]:
    values = names.values()
    return (
        ("txt_values", len(names)),
        ("txt_distinct", len(set(values))),
        ("txt_avg_length", sum(map(len, values)) // max(len(names), 1)),
        ("txt_no_letters", sum(_LETTER.search(value) is None for value in values)),
        ("same_as_name", same_as_name),
    )


def _trade_names_line(result: ParseResult) -> str:
    if result.trade_name_failure is None:
        return "trade_names=loaded"
    return (
        f"trade_names=unavailable reason={result.trade_name_failure}: previous names stay"
    )


def _optional_bits(row: RncRow) -> int:
    bits = 0
    for position, field in enumerate(_OPTIONAL_FIELDS):
        if getattr(row, field) is not None:
            bits |= 1 << position
    return bits


def _tally(filled: list[int], bits: int, step: int) -> None:
    for position in range(len(filled)):
        if bits >> position & 1:
            filled[position] += step


def _copy_line(row: RncRow) -> str:
    start_date = "\\N" if row.start_date is None else row.start_date.isoformat()
    return (
        f"{_escape_copy(row.rnc)}\t{_escape_copy(row.name)}\t"
        f"{_copy_optional(row.trade_name)}\t{_escape_copy(row.status)}\t"
        f"{row.file_date.isoformat()}\t{_copy_optional(row.activity)}\t"
        f"{start_date}\t{_copy_optional(row.regime)}\n"
    )


def _copy_optional(value: str | None) -> str:
    return "\\N" if value is None else _escape_copy(value)


def _copy_header(config: LoadConfig) -> str:
    table = _sql_ident(config.load_table)
    timeout = _statement_timeout(config.statement_timeout)
    return (
        f"SET statement_timeout = '{timeout}';\n"
        "SET client_encoding = 'UTF8';\n"
        f"TRUNCATE {table};\n"
        f"COPY {table} (rnc, name, trade_name, status, file_date, "
        "activity, start_date, regime) FROM STDIN WITH (FORMAT text);\n"
    )


def _rnc_key(digits: str) -> int:
    value = int(digits) + 1
    if len(digits) == 9:
        return value
    return value + _ELEVEN_KEY_BASE


def _mix(key: int) -> int:
    z = (key + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    return z ^ (z >> 31)


def _compact_spill(source: str, offsets: array.array, lengths: array.array) -> str:
    compacted = tempfile.NamedTemporaryFile(prefix="dgii-rnc-copy-", delete=False)
    try:
        with open(source, "rb") as raw:
            for seq in range(len(offsets)):
                raw.seek(offsets[seq])
                compacted.write(raw.read(lengths[seq]))
        compacted.close()
    except Exception:
        compacted.close()
        _discard_spill(compacted.name)
        raise
    return compacted.name


def _discard_spill(path: str | None) -> None:
    if path is None:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        return


def _previous_trade_names(database_url: str, config: LoadConfig) -> dict[str, str]:
    return json.loads(_psql(database_url, previous_names_sql(config)))


def _kept_count(result: ParseResult) -> int:
    if result.row_count is None:
        return len(result.rows)
    return result.row_count


def _parsed_bytes(result: ParseResult) -> int:
    if result.parsed_bytes is None:
        return parsed_byte_estimate(result.rows)
    return result.parsed_bytes


def _blank_status(result: ParseResult) -> int:
    return dict(_status_counts(result)).get("", 0)


def _filled_counts(result: ParseResult) -> tuple[tuple[str, int], ...]:
    if result.filled_counts is not None:
        return result.filled_counts
    return tuple(
        (field, sum(getattr(row, field) is not None for row in result.rows))
        for field in _OPTIONAL_FIELDS
    )


def _status_counts(result: ParseResult) -> tuple[tuple[str, int], ...]:
    if result.status_counts is not None:
        return result.status_counts
    counts: dict[str, int] = {}
    for row in result.rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return tuple((status, counts[status]) for status in sorted(counts))


def _length_counts(result: ParseResult) -> tuple[tuple[int, int], ...]:
    if result.length_counts is not None:
        return result.length_counts
    counts: dict[int, int] = {}
    for row in result.rows:
        length = len(row.rnc)
        counts[length] = counts.get(length, 0) + 1
    return tuple((length, counts[length]) for length in sorted(counts))


def _escape_copy(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def _sql_ident(value: str) -> str:
    if not value or any(char not in _IDENT_CHARS for char in value):
        raise RncImportError("refusing SQL identifier")
    return value


def _apply_load(database_url: str, result: ParseResult, config: LoadConfig) -> None:
    database_size, relation_bytes, stale_load = _psql_integers(
        database_url, headroom_sql(config), 3
    )
    # The copy truncates the load table first, so its rows are not part of the peak.
    settled_size = database_size - stale_load
    peak = require_load_headroom(settled_size, relation_bytes, config)
    print(f"database_bytes={database_size}")
    print(f"live_relation_bytes={relation_bytes}")
    print(f"load_relation_bytes={stale_load}")
    print(f"headroom_bytes={peak - settled_size}")
    print(f"peak_bytes={peak}")
    if result.spill_path is None:
        _psql(database_url, load_script(result, config))
    else:
        _psql_copy(database_url, _copy_header(config), result.spill_path)
    count = swap_row_count(_psql(database_url, swap_script(config)))
    print(f"swap_rows={count}")
    require_swap_count(count, config)
    database_after, live_bytes, load_bytes = _psql_integers(
        database_url,
        size_report_sql(config),
        3,
    )
    print(f"database_bytes_after={database_after}")
    print(f"relation_bytes {config.live_table}={live_bytes}")
    print(f"relation_bytes {config.load_table}={load_bytes}")


def _psql(database_url: str, script: str) -> str:
    try:
        completed = subprocess.run(
            [
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-X",
                "-q",
                "-t",
                "-A",
                database_url,
            ],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        raise RncImportError("psql is not installed") from None
    if completed.returncode != 0:
        raise RncImportError(_psql_failure(completed.stderr, database_url))
    return _redact(completed.stdout, database_url)


def _psql_failure(stderr: str, database_url: str) -> str:
    """One line only: the DETAIL and CONTEXT lines of a failed COPY quote the row."""
    lines = _redact(stderr, database_url).strip().splitlines()
    errors = [line for line in lines if "ERROR:" in line]
    return (errors or lines or ["psql failed"])[0]


def _write_copy(stdin, header: bytes, payload_path: str, stop=None) -> None:
    stdin.write(header)
    with open(payload_path, "rb") as source:
        while stop is None or not stop():
            chunk = source.read(_COPY_CHUNK)
            if not chunk:
                break
            stdin.write(chunk)
    if stop is None or not stop():
        stdin.write(b"\\.\n")


def _psql_copy(database_url: str, header: str, payload_path: str) -> str:
    try:
        completed = subprocess.Popen(
            [
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-X",
                "-q",
                "-t",
                "-A",
                database_url,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise RncImportError("psql is not installed") from None
    assert completed.stdin is not None
    try:
        _write_copy(
            completed.stdin,
            header.encode("ascii"),
            payload_path,
            stop=lambda: completed.poll() is not None,
        )
    except BrokenPipeError:
        pass
    stdout, stderr = completed.communicate()
    if completed.returncode != 0:
        raise RncImportError(_psql_failure(stderr.decode("utf-8", "replace"), database_url))
    return _redact(stdout.decode("utf-8", "replace"), database_url)


def _psql_integers(database_url: str, script: str, expected: int) -> tuple[int, ...]:
    lines = [
        line.strip() for line in _psql(database_url, script).splitlines() if line.strip()
    ]
    if len(lines) != expected or any(not line.isdigit() for line in lines):
        raise RncImportError(f"expected {expected} integers from psql")
    return tuple(int(line) for line in lines)


def _redact(text: str, secret: str) -> str:
    if secret == "":
        return text
    return text.replace(secret, "[redacted]")


if __name__ == "__main__":
    raise SystemExit(main())
