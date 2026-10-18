"""Parse a DGII RNC zip and load the kept rows into staging."""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SANTO_DOMINGO = ZoneInfo("America/Santo_Domingo")
_IDENT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_.")


class RncImportError(Exception):
    pass


@dataclass(frozen=True)
class RncRow:
    rnc: str
    name: str
    status: str
    file_date: date


@dataclass(frozen=True)
class ParseResult:
    rows: tuple[RncRow, ...]
    file_date: date
    entry_name: str
    anomaly_count: int
    dropped_nondigit: int


@dataclass(frozen=True)
class LoadConfig:
    load_table: str = "public.dgii_rnc_load"
    swap_function: str = "public.dgii_rnc_swap"
    min_rows: int = 700_000
    anomaly_limit: int = 25


LOAD = LoadConfig()


def load_action(*, enabled: str, dry_run: str, secret_present: str) -> str:
    if dry_run == "true":
        return "load skipped: dry run"
    if enabled != "true":
        return "load skipped: DGII_RNC_LOAD_ENABLED is not true"
    if secret_present != "true":
        return "load skipped: SUPABASE_STAGING_DB_URL is absent"
    return "load"


def parse_zip(source: bytes | str | Path) -> ParseResult:
    handle: io.BytesIO | str | Path
    if isinstance(source, bytes):
        handle = io.BytesIO(source)
    else:
        handle = source
    with zipfile.ZipFile(handle) as archive:
        info = _registry_entry(archive)
        text = archive.read(info).decode("iso-8859-1")
    return _parse_registry(text, file_date=_file_date(info), entry_name=info.filename)


def validate(result: ParseResult, config: LoadConfig) -> None:
    if result.anomaly_count > config.anomaly_limit:
        raise RncImportError(
            f"anomalies {result.anomaly_count} exceed limit {config.anomaly_limit}"
        )
    seen: set[str] = set()
    for row in result.rows:
        if not row.rnc.isdigit():
            raise RncImportError(f"rnc is not all digits: {row.rnc}")
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
        f"dropped_nondigit={result.dropped_nondigit}",
    ]
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


def copy_text(rows: tuple[RncRow, ...]) -> str:
    if not rows:
        return ""
    lines = [
        "\t".join(
            (
                _escape_copy(row.rnc),
                _escape_copy(row.name),
                _escape_copy(row.status),
                row.file_date.isoformat(),
            )
        )
        for row in rows
    ]
    return "\n".join(lines) + "\n"


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
        result = parse_zip(args.zip_path)
        validate(result, LOAD)
        if args.command == "parse":
            for line in summary_lines(result):
                print(line)
            return 0
        database_url = os.environ.get("SUPABASE_STAGING_DB_URL", "")
        if database_url == "":
            print("load skipped: SUPABASE_STAGING_DB_URL is absent")
            return 0
        _apply_load(database_url, result, LOAD)
        return 0
    except RncImportError as exc:
        print(exc, file=sys.stderr)
        return 1


def _flag(value: str | None, env_name: str) -> str:
    if value is None:
        return os.environ.get(env_name, "")
    return value


def _registry_entry(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    matches = [
        info for info in archive.infolist() if info.filename.endswith("DGII_RNC.TXT")
    ]
    if len(matches) != 1:
        raise RncImportError("zip must contain one DGII_RNC.TXT entry")
    return matches[0]


def _file_date(info: zipfile.ZipInfo) -> date:
    year, month, day, hour, minute, second = info.date_time
    # The zip tuple is already Santo Domingo local time. Attaching the zone
    # keeps that calendar date. Converting from UTC would move midnight back a day.
    local = datetime(
        year,
        month,
        day,
        hour,
        minute,
        second,
        tzinfo=SANTO_DOMINGO,
    )
    return local.date()


def _parse_registry(text: str, *, file_date: date, entry_name: str) -> ParseResult:
    rows: list[RncRow] = []
    anomalies = 0
    dropped = 0
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
            row = _row_from_record(buffer, file_date)
            if row is None:
                dropped += 1
            else:
                rows.append(row)
            buffer = None
        elif pipes > 10:
            anomalies += 1
            buffer = None
    if buffer is not None:
        anomalies += 1
    return ParseResult(
        rows=tuple(rows),
        file_date=file_date,
        entry_name=entry_name,
        anomaly_count=anomalies,
        dropped_nondigit=dropped,
    )


def _physical_lines(text: str) -> list[str]:
    # splitlines() treats some Latin-1 controls, including U+0085, as breaks.
    # The registry is CRLF. A final LF without CR is not a record break.
    if text.endswith("\n") and not text.endswith("\r\n"):
        text = text[:-1]
    if text == "":
        return []
    return text.split("\r\n")


def _row_from_record(record: str, file_date: date) -> RncRow | None:
    fields = [field.strip() for field in record.split("|")]
    rnc = fields[0]
    if not rnc.isdigit():
        return None
    return RncRow(
        rnc=rnc,
        name=fields[1],
        status=fields[9],
        file_date=file_date,
    )


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


def _load_script(result: ParseResult, config: LoadConfig) -> str:
    table = _sql_ident(config.load_table)
    function = _sql_ident(config.swap_function)
    if isinstance(config.min_rows, bool) or not isinstance(config.min_rows, int):
        raise RncImportError("min_rows must be an integer")
    return (
        f"TRUNCATE {table};\n"
        f"COPY {table} (rnc, name, status, file_date) FROM STDIN WITH (FORMAT text);\n"
        f"{copy_text(result.rows)}"
        "\\.\n"
        f"SELECT {function}({config.min_rows});\n"
    )


def _apply_load(database_url: str, result: ParseResult, config: LoadConfig) -> None:
    script = _load_script(result, config)
    try:
        completed = subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=1", "-X", database_url],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        raise RncImportError("psql is not installed") from None
    if completed.stdout:
        sys.stdout.write(_redact(completed.stdout, database_url))
    if completed.returncode != 0:
        detail = _redact(completed.stderr, database_url).strip()
        raise RncImportError(detail or "psql failed")


def _redact(text: str, secret: str) -> str:
    if secret == "":
        return text
    return text.replace(secret, "[redacted]")


if __name__ == "__main__":
    raise SystemExit(main())
