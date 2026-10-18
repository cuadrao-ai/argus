from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

_IDENT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_.")
_TIMEOUT = re.compile(r"^[0-9]+(ms|s|min|h)$")
_SIZE = re.compile(r"^[0-9]+(B|KB|MB|GB)$")
_SIZE_UNIT = {"B": 1, "KB": 1024, "MB": 1024 * 1024, "GB": 1024**3}
_KEPT_LENGTHS = frozenset({9, 11})


class RncImportError(Exception):
    pass


@dataclass(frozen=True)
class RncRow:
    rnc: str
    name: str
    trade_name: str | None
    status: str
    file_date: date


@dataclass(frozen=True)
class DroppedRecord:
    raw: str
    rnc: str
    reason: str
    name: str


@dataclass(frozen=True)
class ParseResult:
    rows: tuple[RncRow, ...]
    file_date: date
    entry_name: str
    anomaly_count: int
    dropped_count: int = 0
    dropped_sample: tuple[DroppedRecord, ...] = ()
    duplicate_count: int = 0


@dataclass(frozen=True)
class LoadConfig:
    live_table: str = "public.dgii_rnc"
    load_table: str = "public.dgii_rnc_load"
    swap_function: str = "public.dgii_rnc_swap"
    lookup_function: str = "public.dgii_rnc_lookup"
    min_rows: int = 700_000
    anomaly_limit: int = 25
    statement_timeout: str = "5min"
    drop_sample_limit: int = 5
    load_headroom_floor_bytes: int = 200 * 1024 * 1024
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


def parse_zip(source: bytes | str | Path, config: LoadConfig = LOAD) -> ParseResult:
    handle: io.BytesIO | str | Path
    if isinstance(source, bytes):
        handle = io.BytesIO(source)
    else:
        handle = source
    with zipfile.ZipFile(handle) as archive:
        info = _registry_entry(archive)
        text = archive.read(info).decode("iso-8859-1")
    return _parse_registry(
        text,
        file_date=_file_date(info),
        entry_name=info.filename,
        sample_limit=config.drop_sample_limit,
    )


def validate(result: ParseResult, config: LoadConfig) -> None:
    if result.anomaly_count > config.anomaly_limit:
        raise RncImportError(
            f"anomalies {result.anomaly_count} exceed limit {config.anomaly_limit}"
        )
    seen: set[str] = set()
    for row in result.rows:
        if len(row.rnc) not in _KEPT_LENGTHS or not row.rnc.isdigit():
            raise RncImportError(f"rnc is not 9 or 11 digits: {row.rnc}")
        if row.name.strip() == "":
            raise RncImportError(f"blank name for rnc {row.rnc}")
        if row.rnc in seen:
            raise RncImportError(f"duplicate rnc {row.rnc}")
        seen.add(row.rnc)
    if len(result.rows) < config.min_rows:
        raise RncImportError(f"rows {len(result.rows)} below minimum {config.min_rows}")


def summary_lines(result: ParseResult) -> list[str]:
    lines = [
        f"rows={len(result.rows)}",
        f"file_date={result.file_date.isoformat()}",
        f"entry={result.entry_name}",
        f"anomalies={result.anomaly_count}",
        f"dropped={result.dropped_count}",
        f"duplicates={result.duplicate_count}",
        f"parsed_bytes={parsed_byte_estimate(result.rows)}",
        f"trade_name_filled={sum(row.trade_name is not None for row in result.rows)}",
    ]
    for drop in result.dropped_sample:
        name = drop.name.replace("\r", " ").replace("\n", " ")
        lines.append(
            f"dropped_sample raw={drop.raw} rnc={drop.rnc} "
            f"reason={drop.reason} name={name}"
        )
    status_counts: dict[str, int] = {}
    length_counts: dict[int, int] = {}
    for row in result.rows:
        status_counts[row.status] = status_counts.get(row.status, 0) + 1
        length = len(row.rnc)
        length_counts[length] = length_counts.get(length, 0) + 1
    for status in sorted(status_counts):
        lines.append(f"status {status}={status_counts[status]}")
    for length in sorted(length_counts):
        lines.append(f"rnc_length {length}={length_counts[length]}")
    return lines


def parsed_byte_estimate(rows: tuple[RncRow, ...]) -> int:
    return len(copy_text(rows).encode("utf-8"))


def copy_text(rows: tuple[RncRow, ...]) -> str:
    if not rows:
        return ""
    lines = [
        "\t".join(
            (
                _escape_copy(row.rnc),
                _escape_copy(row.name),
                "\\N" if row.trade_name is None else _escape_copy(row.trade_name),
                _escape_copy(row.status),
                row.file_date.isoformat(),
            )
        )
        for row in rows
    ]
    return "\n".join(lines) + "\n"


def load_script(result: ParseResult, config: LoadConfig) -> str:
    table = _sql_ident(config.load_table)
    timeout = _statement_timeout(config.statement_timeout)
    return (
        f"SET statement_timeout = '{timeout}';\n"
        f"TRUNCATE {table};\n"
        f"COPY {table} (rnc, name, trade_name, status, file_date) "
        "FROM STDIN WITH (FORMAT text);\n"
        f"{copy_text(result.rows)}"
        "\\.\n"
    )


def swap_script(config: LoadConfig) -> str:
    function = _sql_ident(config.swap_function)
    timeout = _statement_timeout(config.statement_timeout)
    min_rows = _require_min_rows(config.min_rows)
    return f"SET statement_timeout = '{timeout}';\n" f"SELECT {function}({min_rows});\n"


def headroom_sql(config: LoadConfig) -> str:
    timeout = _statement_timeout(config.statement_timeout)
    live = _sql_ident(config.live_table)
    return (
        f"SET statement_timeout = '{timeout}';\n"
        "SELECT pg_database_size(current_database());\n"
        f"SELECT COALESCE(pg_total_relation_size(to_regclass('{live}')), 0);\n"
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
    parse_command.add_argument("zip_path")

    gate_command = commands.add_parser("gate")
    gate_command.add_argument("--enabled", default=None)
    gate_command.add_argument("--dry-run", default=None)
    gate_command.add_argument("--secret-present", default=None)

    load_command = commands.add_parser("load")
    load_command.add_argument("zip_path")

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
        result = parse_zip(args.zip_path, config)
        validate(result, config)
        if args.command == "parse":
            for line in summary_lines(result):
                print(line)
            return 0
        database_url = os.environ.get("SUPABASE_STAGING_DB_URL", "")
        if database_url == "":
            print("load skipped: SUPABASE_STAGING_DB_URL is absent")
            return 0
        _apply_load(database_url, result, config)
        return 0
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


def _registry_entry(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    matches = [
        info for info in archive.infolist() if info.filename.endswith("DGII_RNC.TXT")
    ]
    if len(matches) != 1:
        raise RncImportError("zip must contain one DGII_RNC.TXT entry")
    return matches[0]


def _file_date(info: zipfile.ZipInfo) -> date:
    year, month, day = info.date_time[:3]
    return date(year, month, day)


def _parse_registry(
    text: str,
    *,
    file_date: date,
    entry_name: str,
    sample_limit: int,
) -> ParseResult:
    accepted: list[RncRow] = []
    anomalies = 0
    dropped_count = 0
    sample: list[DroppedRecord] = []
    buffer: str | None = None
    for line in _physical_lines(text):
        if buffer is None:
            if line.strip() == "":
                continue
            buffer = line
        else:
            buffer = f"{buffer} {line}"
        pipes = buffer.count("|")
        if pipes == 10:
            outcome = _row_from_record(buffer, file_date)
            if isinstance(outcome, DroppedRecord):
                dropped_count += 1
                if len(sample) < sample_limit:
                    sample.append(outcome)
            else:
                accepted.append(outcome)
            buffer = None
        elif pipes > 10:
            anomalies += 1
            buffer = None
    if buffer is not None:
        anomalies += 1
    rows, duplicate_count = _dedupe_last(accepted)
    return ParseResult(
        rows=rows,
        file_date=file_date,
        entry_name=entry_name,
        anomaly_count=anomalies,
        dropped_count=dropped_count,
        dropped_sample=tuple(sample),
        duplicate_count=duplicate_count,
    )


def _physical_lines(text: str) -> list[str]:
    # splitlines() also breaks on U+0085, which Latin-1 must keep inside a name.
    if text == "":
        return []
    return text.split("\r\n")


def _row_from_record(record: str, file_date: date) -> RncRow | DroppedRecord:
    fields = [field.strip() for field in record.split("|")]
    raw = fields[0]
    name = fields[1]
    trade_name = fields[2] if fields[2] != "" else None
    digits = "".join(char for char in raw if char.isdigit())
    if len(digits) not in _KEPT_LENGTHS:
        return DroppedRecord(raw=raw, rnc=digits, reason="rnc_length", name=name)
    if name == "":
        return DroppedRecord(raw=raw, rnc=digits, reason="blank_name", name=name)
    return RncRow(
        rnc=digits,
        name=name,
        trade_name=trade_name,
        status=fields[9],
        file_date=file_date,
    )


def _dedupe_last(rows: list[RncRow]) -> tuple[tuple[RncRow, ...], int]:
    index: dict[str, int] = {}
    kept: list[RncRow] = []
    duplicates = 0
    for row in rows:
        slot = index.get(row.rnc)
        if slot is None:
            index[row.rnc] = len(kept)
            kept.append(row)
            continue
        duplicates += 1
        kept[slot] = row
    return tuple(kept), duplicates


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
    database_size, relation_bytes = _psql_integers(database_url, headroom_sql(config), 2)
    peak = require_load_headroom(database_size, relation_bytes, config)
    print(f"database_bytes={database_size}")
    print(f"live_relation_bytes={relation_bytes}")
    print(f"headroom_bytes={peak - database_size}")
    print(f"peak_bytes={peak}")
    _psql(database_url, load_script(result, config))
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
        detail = _redact(completed.stderr, database_url).strip()
        raise RncImportError(detail or "psql failed")
    return _redact(completed.stdout, database_url)


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
