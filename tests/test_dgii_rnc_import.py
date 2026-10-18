from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from scripts.ops.dgii_rnc_import import (
    LoadConfig,
    ParseResult,
    RncImportError,
    RncRow,
    copy_text,
    load_action,
    main,
    parse_zip,
    summary_lines,
    validate,
)


def record(rnc: str, name: str, status: str = "ACTIVO") -> str:
    return "|".join([rnc, name, "3", "4", "5", "6", "7", "8", "9", status, "11"])


def zip_bytes(
    payload: bytes,
    *,
    date_time: tuple[int, int, int, int, int, int] = (2026, 10, 18, 0, 30, 0),
    entry_name: str = "DGII_RNC.TXT",
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo(filename=entry_name, date_time=date_time)
        archive.writestr(info, payload)
    return buffer.getvalue()


def test_latin1_byte_90_survives_in_the_name() -> None:
    name = "EMPRESA" + bytes([0x90]).decode("latin-1") + "SA"
    payload = (record("12345678", name) + "\r\n").encode("latin-1")
    assert b"\x90" in payload
    result = parse_zip(zip_bytes(payload))
    assert result.rows[0].name == "EMPRESA\u0090SA"
    assert "\u0090" in result.rows[0].name


def test_wrapped_name_rejoins_with_one_space_and_trims() -> None:
    payload = ("123456789|  ACME\r\nDOMINICANA  |3|4|5|6|7|8|9|ACTIVO|11\r\n").encode(
        "latin-1"
    )
    result = parse_zip(zip_bytes(payload))
    assert len(result.rows) == 1
    assert result.rows[0].rnc == "123456789"
    assert result.rows[0].name == "ACME DOMINICANA"
    assert result.anomaly_count == 0


def test_literal_double_quote_stays_in_the_name() -> None:
    payload = (record("12345678", 'FIRMA "ABC" SRL') + "\r\n").encode("latin-1")
    result = parse_zip(zip_bytes(payload))
    assert result.rows[0].name == 'FIRMA "ABC" SRL'


def test_keeps_digit_rncs_and_drops_nondigit() -> None:
    payload = (
        "\r\n".join(
            [
                record("40212345678", "CEDULA"),
                record("12345678", "EIGHT"),
                record("12A45678", "BAD"),
                record("123456789", "NINE"),
            ]
        )
        + "\r\n"
    ).encode("latin-1")
    result = parse_zip(zip_bytes(payload))
    assert [row.rnc for row in result.rows] == [
        "40212345678",
        "12345678",
        "123456789",
    ]
    assert result.dropped_nondigit == 1
    assert result.anomaly_count == 0


def test_trims_surrounding_spaces_on_rnc_and_name() -> None:
    payload = (record("  12345678  ", "  Nombre Comercial  ") + "\r\n").encode("latin-1")
    result = parse_zip(zip_bytes(payload))
    assert result.rows[0].rnc == "12345678"
    assert result.rows[0].name == "Nombre Comercial"


def test_zip_date_time_stays_on_the_santo_domingo_calendar_date() -> None:
    payload = (record("12345678", "ACME") + "\r\n").encode("latin-1")
    result = parse_zip(zip_bytes(payload, date_time=(2026, 10, 18, 0, 30, 0)))
    assert result.file_date == date(2026, 10, 18)
    assert result.rows[0].file_date == date(2026, 10, 18)
    assert result.entry_name == "DGII_RNC.TXT"


def test_duplicate_rnc_fails_validation() -> None:
    payload = (
        "\r\n".join(
            [
                record("12345678", "ONE"),
                record("12345678", "TWO"),
            ]
        )
        + "\r\n"
    ).encode("latin-1")
    result = parse_zip(zip_bytes(payload))
    assert [row.rnc for row in result.rows] == ["12345678", "12345678"]
    with pytest.raises(RncImportError):
        validate(result, LoadConfig(min_rows=1, anomaly_limit=25))


def test_anomaly_count_above_the_limit_fails_and_the_limit_passes() -> None:
    payload = (record("12345678", "ONE") + "\r\n12345679|ONLY\r\n").encode("latin-1")
    result = parse_zip(zip_bytes(payload))
    assert result.anomaly_count == 1
    assert [row.rnc for row in result.rows] == ["12345678"]
    validate(result, LoadConfig(min_rows=1, anomaly_limit=1))
    with pytest.raises(RncImportError):
        validate(result, LoadConfig(min_rows=1, anomaly_limit=0))


def test_overlong_line_is_one_anomaly_and_the_buffer_resets() -> None:
    payload = (
        "1|2|3|4|5|6|7|8|9|10|11|12\r\n" + record("12345678", "OK") + "\r\n"
    ).encode("latin-1")
    result = parse_zip(zip_bytes(payload))
    assert result.anomaly_count == 1
    assert [row.rnc for row in result.rows] == ["12345678"]


def test_summary_lines_list_each_fact() -> None:
    payload = (
        "\r\n".join(
            [
                record("12345678", "A", "ACTIVO"),
                record("123456789", "B", "SUSPENDIDO"),
                record("40212345678", "C", "ACTIVO"),
                record("NOPE", "D", "ACTIVO"),
            ]
        )
        + "\r\n"
    ).encode("latin-1")
    result = parse_zip(zip_bytes(payload, date_time=(2026, 10, 18, 0, 30, 0)))
    assert summary_lines(result) == [
        "rows=3",
        "file_date=2026-10-18",
        "entry=DGII_RNC.TXT",
        "anomalies=0",
        "dropped_nondigit=1",
        "status ACTIVO=2",
        "status SUSPENDIDO=1",
        "rnc_length 8=1",
        "rnc_length 9=1",
        "rnc_length 11=1",
    ]


def test_copy_text_escapes_backslash_tab_cr_and_lf() -> None:
    row = RncRow(
        rnc="12345678",
        name="A\\B\tC\rD\nE",
        status="ACTIVO",
        file_date=date(2026, 10, 18),
    )
    assert copy_text((row,)) == "12345678\tA\\\\B\\tC\\rD\\nE\tACTIVO\t2026-10-18\n"


def test_load_action_literals() -> None:
    assert load_action(enabled="true", dry_run="false", secret_present="true") == "load"
    assert (
        load_action(enabled="true", dry_run="true", secret_present="true")
        == "load skipped: dry run"
    )
    assert (
        load_action(enabled="", dry_run="false", secret_present="true")
        == "load skipped: DGII_RNC_LOAD_ENABLED is not true"
    )
    assert (
        load_action(enabled="true", dry_run="false", secret_present="false")
        == "load skipped: SUPABASE_STAGING_DB_URL is absent"
    )
    assert load_action(enabled="true", dry_run="", secret_present="true") == "load"


def test_validate_rejects_a_kept_nondigit_rnc() -> None:
    result = ParseResult(
        rows=(RncRow("12A45678", "X", "ACTIVO", date(2026, 10, 18)),),
        file_date=date(2026, 10, 18),
        entry_name="DGII_RNC.TXT",
        anomaly_count=0,
        dropped_nondigit=0,
    )
    with pytest.raises(RncImportError):
        validate(result, LoadConfig(min_rows=1, anomaly_limit=25))


def test_parse_cli_uses_production_minimum(tmp_path, capsys) -> None:
    path = tmp_path / "rnc.zip"
    path.write_bytes(zip_bytes((record("12345678", "A") + "\r\n").encode("latin-1")))
    assert main(["parse", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.err == "rows 1 below minimum 700000\n"
    assert captured.out == ""


def test_gate_cli_reads_env_when_flags_are_omitted(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ENABLED", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("SECRET_PRESENT", "true")
    assert main(["gate"]) == 0
    assert capsys.readouterr().out == "load\n"


def test_gate_cli_prints_the_decision(capsys) -> None:
    assert (
        main(
            [
                "gate",
                "--enabled",
                "true",
                "--dry-run",
                "false",
                "--secret-present",
                "true",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "load\n"
