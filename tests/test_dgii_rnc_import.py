from __future__ import annotations

import io
import os
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

from scripts.ops.dgii_rnc_import import (
    LOAD,
    DroppedRecord,
    LoadConfig,
    ParseResult,
    RncImportError,
    RncRow,
    _apply_load,
    _config_from_env,
    _copy_header,
    _psql_copy,
    _write_copy,
    copy_text,
    headroom_sql,
    load_action,
    load_script,
    main,
    parse_zip,
    parsed_byte_estimate,
    require_load_headroom,
    require_swap_count,
    size_report_sql,
    summary_lines,
    swap_row_count,
    swap_script,
    validate,
)


def record(rnc: str, name: str, status: str = "ACTIVO", trade_name: str = "") -> str:
    return "|".join([rnc, name, trade_name, "4", "5", "6", "7", "8", "9", status, "11"])


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


def parsed(payload: str) -> ParseResult:
    return parse_zip(zip_bytes((payload + "\r\n").encode("latin-1")))


def test_latin1_byte_90_survives_in_the_name() -> None:
    name = "EMPRESA" + bytes([0x90]).decode("latin-1") + "SA"
    payload = (record("123456789", name) + "\r\n").encode("latin-1")
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
    result = parsed(record("123456789", 'FIRMA "ABC" SRL'))
    assert result.rows[0].name == 'FIRMA "ABC" SRL'


def test_keeps_nine_and_eleven_and_drops_the_rest() -> None:
    payload = "\r\n".join(
        [
            record("40212345678", "CEDULA"),
            record("12345678", "EIGHT"),
            record("12A456789", "LETTERS"),
            record("123456789", "NINE"),
            record("123-456-78901", "DASHED"),
            record("123456789", "   "),
        ]
    )
    result = parsed(payload)
    assert [(row.rnc, row.name) for row in result.rows] == [
        ("40212345678", "CEDULA"),
        ("123456789", "NINE"),
        ("12345678901", "DASHED"),
    ]
    assert result.dropped_count == 3
    assert result.dropped_sample == (
        DroppedRecord("12345678", "12345678", "rnc_length", "EIGHT"),
        DroppedRecord("12A456789", "12456789", "rnc_length", "LETTERS"),
        DroppedRecord("123456789", "123456789", "blank_name", ""),
    )
    assert "012345678" not in {row.rnc for row in result.rows}
    assert result.anomaly_count == 0


def test_eight_digit_rnc_is_dropped_without_padding() -> None:
    result = parsed(record("12345678", "SOLO"))
    assert result.rows == ()
    assert result.dropped_count == 1
    assert result.dropped_sample == (
        DroppedRecord("12345678", "12345678", "rnc_length", "SOLO"),
    )


def test_trims_surrounding_spaces_on_rnc_and_name() -> None:
    result = parsed(record("  123456789  ", "  Nombre Comercial  "))
    assert result.rows[0].rnc == "123456789"
    assert result.rows[0].name == "Nombre Comercial"


def test_column_3_parses_as_the_commercial_name() -> None:
    result = parsed(record("123456789", "LEGAL", trade_name="COMERCIAL"))
    assert result.rows[0].trade_name == "COMERCIAL"


def test_blank_commercial_name_copies_as_null() -> None:
    spaces = parsed(record("123456789", "LEGAL", trade_name="   "))
    empty = parsed(record("40212345678", "LEGAL", trade_name=""))
    assert spaces.rows[0].trade_name is None
    assert empty.rows[0].trade_name is None
    assert copy_text(spaces.rows) == "123456789\tLEGAL\t\\N\tACTIVO\t2026-10-18\n"
    assert copy_text(empty.rows) == "40212345678\tLEGAL\t\\N\tACTIVO\t2026-10-18\n"


def test_status_is_stored_as_written() -> None:
    baja = parsed(record("123456789", "ONE", "DADO DE BAJA"))
    cese = parsed(record("40212345678", "TWO", "CESE TEMPORAL"))
    assert baja.rows[0].status == "DADO DE BAJA"
    assert cese.rows[0].status == "CESE TEMPORAL"


def test_zip_date_time_stays_on_the_santo_domingo_calendar_date() -> None:
    payload = (record("123456789", "ACME") + "\r\n").encode("latin-1")
    result = parse_zip(zip_bytes(payload, date_time=(2026, 10, 18, 0, 30, 0)))
    assert result.file_date == date(2026, 10, 18)
    assert result.rows[0].file_date == date(2026, 10, 18)
    assert result.entry_name == "DGII_RNC.TXT"


def test_duplicate_rnc_keeps_the_last_row() -> None:
    payload = "\r\n".join(
        [
            record("123456789", "ONE", "ACTIVO"),
            record("40212345678", "OTHER"),
            record("123456789", "TWO", "SUSPENDIDO"),
            record("123456789", "THREE", "ANULADO"),
        ]
    )
    result = parsed(payload)
    assert [(row.rnc, row.name, row.status) for row in result.rows] == [
        ("123456789", "THREE", "ANULADO"),
        ("40212345678", "OTHER", "ACTIVO"),
    ]
    assert result.duplicate_count == 2
    validate(result, LoadConfig(min_rows=1, anomaly_limit=25))


def test_anomaly_count_above_the_limit_fails_and_the_limit_passes() -> None:
    payload = (record("123456789", "ONE") + "\r\n12345679|ONLY\r\n").encode("latin-1")
    result = parse_zip(zip_bytes(payload))
    assert result.anomaly_count == 1
    assert [row.rnc for row in result.rows] == ["123456789"]
    validate(result, LoadConfig(min_rows=1, anomaly_limit=1))
    with pytest.raises(RncImportError):
        validate(result, LoadConfig(min_rows=1, anomaly_limit=0))


def test_overlong_line_is_one_anomaly_and_the_buffer_resets() -> None:
    payload = (
        "1|2|3|4|5|6|7|8|9|10|11|12\r\n" + record("123456789", "OK") + "\r\n"
    ).encode("latin-1")
    result = parse_zip(zip_bytes(payload))
    assert result.anomaly_count == 1
    assert [row.rnc for row in result.rows] == ["123456789"]


def test_summary_lines_list_each_fact() -> None:
    payload = "\r\n".join(
        [
            record("12345678", "A", "ACTIVO"),
            record("123456789", "B", "SUSPENDIDO"),
            record("40212345678", "C", "ACTIVO"),
            record("NOPE", "D", "ACTIVO"),
        ]
    )
    result = parse_zip(zip_bytes((payload + "\r\n").encode("latin-1")))
    assert summary_lines(result) == [
        "rows=2",
        "file_date=2026-10-18",
        "entry=DGII_RNC.TXT",
        "anomalies=0",
        "dropped=2",
        "duplicates=0",
        "parsed_bytes=72",
        "trade_name_filled=0",
        "dropped_sample raw=12345678 rnc=12345678 reason=rnc_length name=A",
        "dropped_sample raw=NOPE rnc= reason=rnc_length name=D",
        "status ACTIVO=1",
        "status SUSPENDIDO=1",
        "rnc_length 9=1",
        "rnc_length 11=1",
    ]


def test_copy_text_escapes_backslash_tab_cr_and_lf() -> None:
    row = RncRow(
        rnc="123456789",
        name="A\\B\tC\rD\nE",
        trade_name=None,
        status="ACTIVO",
        file_date=date(2026, 10, 18),
    )
    assert copy_text((row,)) == (
        "123456789\tA\\\\B\\tC\\rD\\nE\t\\N\tACTIVO\t2026-10-18\n"
    )


def test_load_script_sets_the_session_timeout_and_calls_swap() -> None:
    row = RncRow(
        "123456789",
        "ACME",
        trade_name=None,
        status="ACTIVO",
        file_date=date(2026, 10, 18),
    )
    result = ParseResult(
        rows=(row,),
        file_date=date(2026, 10, 18),
        entry_name="DGII_RNC.TXT",
        anomaly_count=0,
    )
    sql = load_script(result, LOAD)
    assert sql.startswith("SET statement_timeout = '5min';\n")
    assert "TRUNCATE public.dgii_rnc_load;\n" in sql
    assert (
        "COPY public.dgii_rnc_load (rnc, name, trade_name, status, file_date) "
        "FROM STDIN WITH (FORMAT text);\n"
    ) in sql
    assert "123456789\tACME\t\\N\tACTIVO\t2026-10-18\n" in sql
    assert "dgii_rnc_swap" not in sql
    assert "dgii_rnc_lookup" not in sql
    assert sql.endswith("\\.\n")
    swap = swap_script(LOAD)
    assert swap == (
        "SET statement_timeout = '5min';\n" "SELECT public.dgii_rnc_swap(700000);\n"
    )
    assert "TRUNCATE" not in swap
    assert "COPY" not in swap
    assert "dgii_rnc_lookup" not in swap
    with pytest.raises(RncImportError, match="min_rows must be at least 1"):
        swap_script(LoadConfig(min_rows=0))
    with pytest.raises(RncImportError, match="min_rows must be at least 1"):
        swap_script(LoadConfig(min_rows=None))
    with pytest.raises(RncImportError):
        load_script(result, LoadConfig(statement_timeout="5min; drop table t"))


def test_timeout_env_changes_the_session_setting(monkeypatch) -> None:
    row = RncRow(
        "123456789",
        "ACME",
        trade_name=None,
        status="ACTIVO",
        file_date=date(2026, 10, 18),
    )
    result = ParseResult(
        rows=(row,),
        file_date=date(2026, 10, 18),
        entry_name="DGII_RNC.TXT",
        anomaly_count=0,
    )
    monkeypatch.setenv("DGII_RNC_STATEMENT_TIMEOUT", "10min")
    assert load_script(result, _config_from_env()).startswith(
        "SET statement_timeout = '10min';\n"
    )
    assert swap_script(_config_from_env()).startswith(
        "SET statement_timeout = '10min';\n"
    )
    monkeypatch.setenv("DGII_RNC_STATEMENT_TIMEOUT", "")
    assert load_script(result, _config_from_env()).startswith(
        "SET statement_timeout = '5min';\n"
    )
    assert swap_script(_config_from_env()) == (
        "SET statement_timeout = '5min';\n" "SELECT public.dgii_rnc_swap(700000);\n"
    )
    monkeypatch.setenv("DGII_RNC_STATEMENT_TIMEOUT", "5min; drop table t")
    with pytest.raises(RncImportError):
        _config_from_env()


def test_parsed_byte_estimate_counts_one_escaped_row() -> None:
    row = RncRow(
        rnc="123456789",
        name="A\\B\tC\rD\nE",
        trade_name=None,
        status="ACTIVO",
        file_date=date(2026, 10, 18),
    )
    assert parsed_byte_estimate((row,)) == len(copy_text((row,)).encode("utf-8"))
    assert parsed_byte_estimate(()) == 0


def test_empty_load_uses_the_floor_and_a_large_table_uses_its_own_size() -> None:
    floor = 200 * 1024 * 1024
    assert require_load_headroom(0, 0, LOAD) == floor
    assert require_load_headroom(0, floor - 1, LOAD) == floor
    large = 250 * 1024 * 1024
    assert require_load_headroom(0, large, LOAD) == large
    assert require_load_headroom(250 * 1024 * 1024, 0, LOAD) == 450 * 1024 * 1024
    with pytest.raises(RncImportError) as one_over:
        require_load_headroom(250 * 1024 * 1024 + 1, 0, LOAD)
    assert str(one_over.value) == (
        "peak 471859201 limit 471859200 "
        "database_size 262144001 headroom 209715200 relation_bytes 0"
    )


def test_a_350_mib_database_fails_the_450_mib_gate() -> None:
    with pytest.raises(RncImportError) as caught:
        require_load_headroom(350 * 1024 * 1024, 0, LOAD)
    assert str(caught.value) == (
        "peak 576716800 limit 471859200 "
        "database_size 367001600 headroom 209715200 relation_bytes 0"
    )
    with pytest.raises(RncImportError) as negative_size:
        require_load_headroom(-1, 0, LOAD)
    assert str(negative_size.value) == (
        "refusing size database_size -1 relation_bytes 0 floor 209715200"
    )
    with pytest.raises(RncImportError) as negative_relation:
        require_load_headroom(5, -2, LoadConfig(size_limit_bytes=100))
    assert str(negative_relation.value) == (
        "refusing size database_size 5 relation_bytes -2 floor 209715200"
    )
    with pytest.raises(RncImportError) as negative_floor:
        require_load_headroom(
            5, 0, LoadConfig(load_headroom_floor_bytes=-2, size_limit_bytes=100)
        )
    assert str(negative_floor.value) == (
        "refusing size database_size 5 relation_bytes 0 floor -2"
    )


def test_size_sql_reads_sizes_and_does_not_truncate_or_copy() -> None:
    gate_sql = headroom_sql(LOAD)
    assert gate_sql == (
        "SET statement_timeout = '5min';\n"
        "SELECT pg_database_size(current_database());\n"
        "SELECT COALESCE(pg_total_relation_size(to_regclass('public.dgii_rnc')), 0);\n"
    )
    assert "TRUNCATE" not in gate_sql
    assert "COPY" not in gate_sql
    report_sql = size_report_sql(LOAD)
    assert "pg_total_relation_size('public.dgii_rnc'::regclass)" in report_sql
    assert "pg_total_relation_size('public.dgii_rnc_load'::regclass)" in report_sql
    assert "TRUNCATE" not in report_sql
    assert "COPY" not in report_sql


def test_size_env_changes_headroom_and_rejects_injected_sql(monkeypatch) -> None:
    monkeypatch.setenv("DGII_RNC_STATEMENT_TIMEOUT", "10min")
    monkeypatch.setenv("DGII_RNC_LOAD_HEADROOM_FLOOR", "80MB")
    monkeypatch.setenv("DGII_RNC_SIZE_LIMIT", "200MB")
    config = _config_from_env()
    assert headroom_sql(config).startswith("SET statement_timeout = '10min';\n")
    assert require_load_headroom(120 * 1024 * 1024, 0, config) == 200 * 1024 * 1024
    with pytest.raises(RncImportError):
        require_load_headroom(150 * 1024 * 1024, 0, config)
    assert (
        require_load_headroom(50 * 1024 * 1024, 100 * 1024 * 1024, config)
        == 150 * 1024 * 1024
    )
    monkeypatch.setenv("DGII_RNC_LOAD_HEADROOM_FLOOR", "80MB; drop table t")
    with pytest.raises(RncImportError):
        _config_from_env()
    monkeypatch.setenv("DGII_RNC_STATEMENT_TIMEOUT", "")
    monkeypatch.setenv("DGII_RNC_LOAD_HEADROOM_FLOOR", "")
    monkeypatch.setenv("DGII_RNC_SIZE_LIMIT", "")
    with pytest.raises(RncImportError, match="peak 576716800"):
        require_load_headroom(350 * 1024 * 1024, 0, _config_from_env())


def test_size_units_scale_by_1024(monkeypatch) -> None:
    monkeypatch.setenv("DGII_RNC_LOAD_HEADROOM_FLOOR", "1B")
    monkeypatch.setenv("DGII_RNC_SIZE_LIMIT", "1KB")
    assert require_load_headroom(1023, 0, _config_from_env()) == 1024
    monkeypatch.setenv("DGII_RNC_LOAD_HEADROOM_FLOOR", "1KB")
    monkeypatch.setenv("DGII_RNC_SIZE_LIMIT", "1MB")
    assert require_load_headroom(1024 * 1024 - 1024, 0, _config_from_env()) == 1024 * 1024
    monkeypatch.setenv("DGII_RNC_LOAD_HEADROOM_FLOOR", "1MB")
    monkeypatch.setenv("DGII_RNC_SIZE_LIMIT", "1GB")
    assert require_load_headroom(1024**3 - 1024 * 1024, 0, _config_from_env()) == 1024**3


def test_apply_load_stops_before_truncate_when_the_peak_is_over(
    monkeypatch, capsys
) -> None:
    calls: list[str] = []

    def fake_run(args, *, input, text, capture_output, check):
        calls.append(input)
        assert args == [
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-X",
            "-q",
            "-t",
            "-A",
            "postgres://user:secret@db/postgres",
        ]
        if input == headroom_sql(LOAD):
            return _Completed(stdout="500000000\n0\n")
        raise AssertionError("load ran after the size check failed")

    monkeypatch.setattr("scripts.ops.dgii_rnc_import.subprocess.run", fake_run)
    with pytest.raises(RncImportError) as caught:
        _apply_load("postgres://user:secret@db/postgres", _one_row(), LOAD)
    assert len(calls) == 1
    assert calls[0] == headroom_sql(LOAD)
    assert "peak 709715200" in str(caught.value)
    assert "secret" not in str(caught.value)
    assert capsys.readouterr().out == ""


def test_apply_load_prints_sizes_around_the_swap(monkeypatch, capsys) -> None:
    calls: list[str] = []
    url = "postgres://user:secret@db/postgres"

    def fake_run(args, *, input, text, capture_output, check):
        calls.append(input)
        assert args[-1] == url
        if input == headroom_sql(LOAD):
            return _Completed(stdout="1000\n0\n")
        if input == load_script(_one_row(), LOAD):
            return _Completed(stdout="")
        if input == swap_script(LOAD):
            return _Completed(stdout="700000\n")
        if input == size_report_sql(LOAD):
            return _Completed(stdout="100\n200\n300\n")
        raise AssertionError(input)

    monkeypatch.setattr("scripts.ops.dgii_rnc_import.subprocess.run", fake_run)
    _apply_load(url, _one_row(), LOAD)
    assert calls == [
        headroom_sql(LOAD),
        load_script(_one_row(), LOAD),
        swap_script(LOAD),
        size_report_sql(LOAD),
    ]
    sent = "\n".join(calls).lower()
    assert "dgii_rnc_lookup" not in sent
    assert "authenticated" not in sent
    assert "set role" not in sent
    assert capsys.readouterr().out == (
        "database_bytes=1000\n"
        "live_relation_bytes=0\n"
        "headroom_bytes=209715200\n"
        "peak_bytes=209716200\n"
        "swap_rows=700000\n"
        "database_bytes_after=100\n"
        "relation_bytes public.dgii_rnc=200\n"
        "relation_bytes public.dgii_rnc_load=300\n"
    )


def test_apply_load_redacts_the_database_url(monkeypatch) -> None:
    url = "postgres://user:secret@db/postgres"

    def fake_run(args, *, input, text, capture_output, check):
        return _Completed(returncode=1, stderr=f"password failed {url}")

    monkeypatch.setattr("scripts.ops.dgii_rnc_import.subprocess.run", fake_run)
    with pytest.raises(RncImportError) as caught:
        _apply_load(url, _one_row(), LOAD)
    assert url not in str(caught.value)
    assert str(caught.value) == "password failed [redacted]"


class _Completed:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _one_row() -> ParseResult:
    return ParseResult(
        rows=(
            RncRow(
                "123456789",
                "ACME",
                trade_name=None,
                status="ACTIVO",
                file_date=date(2026, 10, 18),
            ),
        ),
        file_date=date(2026, 10, 18),
        entry_name="DGII_RNC.TXT",
        anomaly_count=0,
    )


def test_swap_row_count_reads_one_integer_and_rejects_a_short_swap() -> None:
    assert swap_row_count("795000\n") == 795000
    with pytest.raises(RncImportError):
        swap_row_count("SET\n795000\n")
    require_swap_count(700000, LOAD)
    with pytest.raises(RncImportError, match="swap returned 699999"):
        require_swap_count(699999, LOAD)


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


def test_validate_rejects_a_kept_short_rnc() -> None:
    result = ParseResult(
        rows=(
            RncRow(
                "12345678",
                "X",
                trade_name=None,
                status="ACTIVO",
                file_date=date(2026, 10, 18),
            ),
        ),
        file_date=date(2026, 10, 18),
        entry_name="DGII_RNC.TXT",
        anomaly_count=0,
    )
    with pytest.raises(RncImportError):
        validate(result, LoadConfig(min_rows=1, anomaly_limit=25))


def test_parse_cli_uses_production_minimum(tmp_path, capsys) -> None:
    path = tmp_path / "rnc.zip"
    path.write_bytes(zip_bytes((record("123456789", "A") + "\r\n").encode("latin-1")))
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


def test_leading_zeros_keep_nine_and_eleven_apart() -> None:
    result = parsed(
        "\r\n".join(
            [
                record("000000001", "NINE"),
                record("00000000001", "ELEVEN"),
                record("000000001", "NINE2"),
            ]
        )
    )
    assert [(row.rnc, row.name) for row in result.rows] == [
        ("000000001", "NINE2"),
        ("00000000001", "ELEVEN"),
    ]
    assert result.duplicate_count == 1


def test_unretained_parse_reports_the_same_summary() -> None:
    payload = "\r\n".join(
        [
            record("12345678", "A", "ACTIVO"),
            record("123456789", "B", "SUSPENDIDO"),
            record("123456789", "B2", "ACTIVO"),
            record("40212345678", "C", "ACTIVO"),
            record("NOPE", "D", "ACTIVO"),
        ]
    )
    result = parse_zip(
        zip_bytes((payload + "\r\n").encode("latin-1")),
        keep_rows=False,
    )
    assert result.spill_path is not None
    try:
        assert result.rows == ()
        assert summary_lines(result) == [
            "rows=2",
            "file_date=2026-10-18",
            "entry=DGII_RNC.TXT",
            "anomalies=0",
            "dropped=2",
            "duplicates=1",
            "parsed_bytes=69",
            "trade_name_filled=0",
            "dropped_sample raw=12345678 rnc=12345678 reason=rnc_length name=A",
            "dropped_sample raw=NOPE rnc= reason=rnc_length name=D",
            "status ACTIVO=2",
            "rnc_length 9=1",
            "rnc_length 11=1",
        ]
        assert Path(result.spill_path).read_text(encoding="utf-8") == (
            "123456789\tB2\t\\N\tACTIVO\t2026-10-18\n"
            "40212345678\tC\t\\N\tACTIVO\t2026-10-18\n"
        )
    finally:
        os.unlink(result.spill_path)


def test_copy_session_reaps_a_real_child(tmp_path: Path, monkeypatch) -> None:
    payload = tmp_path / "copy.txt"
    payload.write_bytes(b"123456789\tACME\t\\N\tACTIVO\t2026-10-18\n")
    real_popen = subprocess.Popen

    def popen(args, **kwargs):
        assert kwargs["stdin"] is subprocess.PIPE
        assert kwargs["stdout"] is subprocess.PIPE
        assert kwargs["stderr"] is subprocess.PIPE
        return real_popen(["sh", "-c", "cat >/dev/null"], **kwargs)

    monkeypatch.setattr("scripts.ops.dgii_rnc_import.subprocess.Popen", popen)
    assert (
        _psql_copy(
            "postgres://user:secret@db/postgres",
            _copy_header(LOAD),
            str(payload),
        )
        == ""
    )


def test_copy_stream_writes_header_rows_and_terminator(tmp_path: Path) -> None:
    payload = tmp_path / "copy.txt"
    body = b"123456789\tACME\t\\N\tACTIVO\t2026-10-18\n" * 30_000
    payload.write_bytes(body)
    sink = io.BytesIO()
    _write_copy(sink, _copy_header(LOAD).encode("ascii"), payload)
    assert sink.getvalue() == (
        b"SET statement_timeout = '5min';\n"
        b"TRUNCATE public.dgii_rnc_load;\n"
        b"COPY public.dgii_rnc_load (rnc, name, trade_name, status, file_date) "
        b"FROM STDIN WITH (FORMAT text);\n"
        + body
        + b"\\.\n"
    )


def test_parse_of_a_large_registry_stays_under_80_mib(tmp_path: Path) -> None:
    path = tmp_path / "rnc.zip"
    count = 150_000
    payload = "".join(
        f"{i:09d}|NAME|TRADE|4|5|6|7|8|9|ACTIVO|11\r\n" for i in range(count)
    )
    path.write_bytes(zip_bytes(payload.encode("latin-1")))
    script = (
        "import re, runpy, sys\n"
        "sys.argv = ['dgii_rnc_import', 'parse', sys.argv[1]]\n"
        "try:\n"
        "    runpy.run_path('scripts/ops/dgii_rnc_import.py', run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "status = open('/proc/self/status', encoding='ascii').read()\n"
        "print(re.search(r'VmHWM:\\s+(\\d+)', status).group(1))\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COVERAGE_")
    }
    completed = subprocess.run(
        [sys.executable, "-S", "-c", script, str(path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0
    assert completed.stderr == f"rows {count} below minimum 700000\n"
    rss_kb = int(completed.stdout.strip())
    assert rss_kb < 80 * 1024
