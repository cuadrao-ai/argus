from __future__ import annotations

import io
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from faker import Faker

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
from tests.dgii_rnc_zip import (
    CSV_ENTRY,
    HEADER,
    csv_file,
    csv_record,
    registry_zip,
    txt_record,
    txt_zip,
)

fake = Faker("es")
Faker.seed(20261102)

ESTADOS = (
    "ACTIVO",
    "SUSPENDIDO",
    "DADO DE BAJA",
    "CESE TEMPORAL",
    "ANULADO",
    "RECHAZADO",
)


def rnc9() -> str:
    return fake.numerify("9########")


def rnc11() -> str:
    return fake.numerify("99#########")


def company() -> str:
    return fake.company().replace("’", "'")


def parsed(*records: str, txt: tuple[str, ...] | None = None) -> ParseResult:
    names = None if txt is None else txt_zip(*txt)
    return parse_zip(registry_zip(csv_file(*records)), trade_name_zip=names)


def test_latin1_byte_90_survives_in_the_name() -> None:
    name = "EMPRESA" + bytes([0x90]).decode("latin-1") + "SA"
    payload = csv_file(csv_record(rnc9(), name))
    assert b"\x90" in payload
    result = parse_zip(registry_zip(payload))
    assert result.rows[0].name == "EMPRESA\u0090SA"


def test_accented_names_decode_as_latin1() -> None:
    result = parsed(csv_record(rnc9(), "PANADERÍA PEÑA"))
    assert result.rows[0].name == "PANADERÍA PEÑA"


def test_a_name_broken_across_lines_rejoins_with_one_space_and_trims() -> None:
    result = parsed(csv_record(rnc9(), "  ACME\r\nDOMINICANA  "))
    assert len(result.rows) == 1
    assert result.rows[0].name == "ACME DOMINICANA"
    assert result.anomaly_count == 0


def test_quote_aware_parser_keeps_commas_and_doubled_quotes_in_a_name() -> None:
    comma = csv_record(rnc9(), "FIRMA, ABC Y ASOCIADOS, SRL")
    quote = csv_record(rnc9(), 'FIRMA "ABC" SRL')
    result = parsed(comma, quote)
    assert [row.name for row in result.rows] == [
        "FIRMA, ABC Y ASOCIADOS, SRL",
        'FIRMA "ABC" SRL',
    ]
    assert result.anomaly_count == 0


def test_keeps_nine_and_eleven_and_drops_the_rest() -> None:
    nine, eleven = rnc9(), rnc11()
    short = fake.numerify("9#######")
    result = parsed(
        csv_record(eleven, "CEDULA"),
        csv_record(short, "EIGHT"),
        csv_record("9A1234567", "LETTERS"),
        csv_record(nine, "NINE"),
        csv_record("991-234-56789", "DASHED"),
        csv_record(rnc9(), "   "),
    )
    assert [(row.rnc, row.name) for row in result.rows] == [
        (eleven, "CEDULA"),
        (nine, "NINE"),
        ("99123456789", "DASHED"),
    ]
    assert result.dropped_count == 3
    assert [drop.reason for drop in result.dropped_sample] == [
        "rnc_length",
        "rnc_length",
        "blank_name",
    ]
    assert result.dropped_sample[0].digits == 8
    assert result.anomaly_count == 0


def test_eight_digit_rnc_is_quarantined_without_padding() -> None:
    short = fake.numerify("9#######")
    name = company()
    result = parsed(csv_record(short, name), txt=(txt_record(short, company()),))
    assert result.rows == ()
    assert result.dropped_count == 1
    assert result.dropped_sample == (DroppedRecord("rnc_length", 8),)
    lines = summary_lines(result)
    assert "rows=0" in lines
    assert "dropped=1" in lines
    assert "dropped_sample reason=rnc_length digits=8" in lines


def test_the_summary_prints_no_name_rnc_or_raw_value() -> None:
    short, kept, trade = "90000001", rnc9(), company()
    legal, activity = company(), fake.bs()
    result = parsed(
        csv_record(short, company()),
        csv_record(kept, legal, activity=activity, started="07/03/2019", regime="RST"),
        txt=(txt_record(kept, trade),),
    )
    summary = "\n".join(summary_lines(result))
    for secret in (short, kept, legal, trade, activity, "07/03/2019"):
        assert secret not in summary


def test_trims_surrounding_spaces_on_rnc_and_name() -> None:
    rnc = rnc9()
    result = parsed(csv_record(f"  {rnc}  ", "  Nombre Fiscal  "))
    assert result.rows[0].rnc == rnc
    assert result.rows[0].name == "Nombre Fiscal"


def test_keeps_activity_start_date_and_regime() -> None:
    activity = fake.bs()
    result = parsed(
        csv_record(
            rnc9(),
            company(),
            activity=f"  {activity}  ",
            started="07/03/2019",
            regime=" RST ",
        )
    )
    row = result.rows[0]
    assert row.activity == activity
    assert row.start_date == date(2019, 3, 7)
    assert row.regime == "RST"


@pytest.mark.parametrize(
    "value",
    ["", "   ", "31/02/2020", "2020-01-02", "13/13/2020", "00/00/0000", "sin fecha"],
)
def test_a_bad_start_date_loads_as_null(value: str) -> None:
    result = parsed(csv_record(rnc9(), company(), started=value))
    assert len(result.rows) == 1
    assert result.rows[0].start_date is None
    assert result.anomaly_count == 0


def test_blank_activity_and_regime_copy_as_null() -> None:
    rnc = rnc9()
    result = parsed(csv_record(rnc, "LEGAL", activity="   ", regime=""))
    assert result.rows[0].activity is None
    assert result.rows[0].regime is None
    assert copy_text(result.rows) == (
        f"{rnc}\tLEGAL\t\\N\tACTIVO\t2026-10-18\t\\N\t\\N\t\\N\n"
    )


def test_column_order_comes_from_the_header() -> None:
    rnc = rnc9()
    moved = ",".join(reversed(HEADER))
    body = ",".join(["NORMAL", "ANULADO", "01/02/2003", "VENTAS", "LEGAL", rnc])
    result = parse_zip(
        registry_zip(f"{moved}\r\n{body}\r\n".encode("latin-1")),
    )
    row = result.rows[0]
    assert (row.rnc, row.name, row.activity, row.status, row.regime) == (
        rnc,
        "LEGAL",
        "VENTAS",
        "ANULADO",
        "NORMAL",
    )
    assert row.start_date == date(2003, 2, 1)


@pytest.mark.parametrize("missing", HEADER)
def test_a_header_without_a_kept_column_refuses_the_file(missing: str) -> None:
    header = ",".join(cell for cell in HEADER if cell != missing)
    with pytest.raises(RncImportError, match="csv header needs one") as caught:
        parse_zip(registry_zip(f"{header}\r\n".encode("latin-1")))
    assert header.split(",")[0] in str(caught.value)


def test_trade_name_comes_from_txt_column_3_joined_by_rnc() -> None:
    filled, blank, absent = rnc9(), rnc11(), rnc9()
    trade = company()
    result = parsed(
        csv_record(filled, "LEGAL"),
        csv_record(blank, "LEGAL"),
        csv_record(absent, "LEGAL"),
        txt=(
            txt_record(rnc9(), company()),
            txt_record(blank, "   "),
            txt_record(filled, f"  {trade}  "),
        ),
    )
    assert [row.trade_name for row in result.rows] == [trade, None, None]
    assert "trade_name_filled=1" in summary_lines(result)


def test_the_txt_never_adds_a_row_or_changes_a_csv_field() -> None:
    rnc = rnc9()
    only_in_txt = rnc9()
    legal = company()
    result = parsed(
        csv_record(rnc, legal, "SUSPENDIDO"),
        txt=(
            txt_record(only_in_txt, company()),
            txt_record(rnc, company(), name=company()),
        ),
    )
    assert [row.rnc for row in result.rows] == [rnc]
    assert result.rows[0].name == legal
    assert result.rows[0].status == "SUSPENDIDO"


def test_a_wrapped_txt_record_still_yields_its_trade_name() -> None:
    rnc = rnc9()
    trade = company()
    wrapped = f"{rnc}|PRIMERA\r\nLINEA|{trade}|4|5|6|7|8|9|ACTIVO|11"
    result = parsed(csv_record(rnc, company()), txt=(wrapped,))
    assert result.rows[0].trade_name == trade


def test_a_malformed_txt_record_costs_only_its_trade_name() -> None:
    rnc = rnc9()
    result = parsed(
        csv_record(rnc, company()),
        txt=("1|2|3|4|5|6|7|8|9|10|11|12", txt_record(rnc, "COMERCIAL")),
    )
    assert result.rows[0].trade_name == "COMERCIAL"
    assert result.anomaly_count == 0


def test_the_summary_describes_the_trade_name_column() -> None:
    same, other = rnc9(), rnc9()
    result = parsed(
        csv_record(same, "LEGAL SRL"),
        csv_record(other, "OTRA SRL"),
        txt=(
            txt_record(same, "legal srl"),
            txt_record(other, "COLMADO"),
            txt_record(rnc9(), "2024"),
        ),
    )
    lines = summary_lines(result)
    assert "trade_names=loaded" in lines
    assert "trade_name_filled=2" in lines
    assert "trade_name_txt_values=3" in lines
    assert "trade_name_txt_distinct=3" in lines
    assert "trade_name_txt_avg_length=6" in lines
    assert "trade_name_txt_no_letters=1" in lines
    assert "trade_name_same_as_name=1" in lines


@pytest.mark.parametrize("payload", [b"<html>busy</html>", b""])
def test_a_csv_source_that_is_not_a_zip_refuses_the_file(payload: bytes) -> None:
    with pytest.raises(RncImportError, match="csv is unreadable"):
        parse_zip(payload)


@pytest.mark.parametrize(
    "entry",
    [
        "RNC_Contribuyentes_Actualizado_02_Nov_2026.csv",
        "TMP/RNC_Contribuyentes_Actualizado_20261102.csv",
        "TMP/rnc_contribuyentes_actualizado_2026-11-02.CSV",
    ],
)
def test_finds_the_csv_by_pattern_whatever_its_date(entry: str) -> None:
    result = parse_zip(
        registry_zip(csv_file(csv_record(rnc9(), company())), csv_entry=entry)
    )
    assert result.entry_name == entry
    assert len(result.rows) == 1


@pytest.mark.parametrize("entry", ["DGII_RNC.csv", "TMP/._RNC_Contribuyentes_Actualizado_1.csv"])
def test_a_zip_without_the_csv_refuses_the_file_and_names_its_entries(entry: str) -> None:
    payload = registry_zip(csv_file(), csv_entry=entry)
    with pytest.raises(RncImportError, match="must contain one") as caught:
        parse_zip(payload)
    assert entry in str(caught.value)


def test_unterminated_quote_refuses_the_file_and_leaves_no_spill(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    runaway = f'"{rnc9()}' + "\r\n123456789" * 20_000
    with pytest.raises(RncImportError, match="csv is unreadable"):
        parse_zip(registry_zip(csv_file(runaway)))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("status", ESTADOS)
def test_every_estado_loads_as_written(status: str) -> None:
    result = parsed(csv_record(rnc9(), company(), status))
    assert [row.status for row in result.rows] == [status]


def test_the_rows_keep_the_csv_entry_date_and_name() -> None:
    payload = csv_file(csv_record(rnc9(), company()))
    result = parse_zip(registry_zip(payload, date_time=(2026, 10, 18, 0, 30, 0)))
    assert result.file_date == date(2026, 10, 18)
    assert result.rows[0].file_date == date(2026, 10, 18)
    assert result.entry_name == CSV_ENTRY


def test_duplicate_rnc_keeps_the_last_row() -> None:
    repeated, other = rnc9(), rnc11()
    result = parsed(
        csv_record(repeated, "ONE", "ACTIVO"),
        csv_record(other, "OTHER"),
        csv_record(repeated, "TWO", "SUSPENDIDO"),
        csv_record(repeated, "THREE", "ANULADO"),
    )
    assert [(row.rnc, row.name, row.status) for row in result.rows] == [
        (repeated, "THREE", "ANULADO"),
        (other, "OTHER", "ACTIVO"),
    ]
    assert result.duplicate_count == 2
    validate(result, LoadConfig(min_rows=1, anomaly_limit=25))


def test_anomaly_count_above_the_limit_fails_and_the_limit_passes() -> None:
    rnc = rnc9()
    result = parsed(csv_record(rnc, company()), f'"{rnc9()}","ONLY"')
    assert result.anomaly_count == 1
    assert [row.rnc for row in result.rows] == [rnc]
    validate(result, LoadConfig(min_rows=1, anomaly_limit=1))
    with pytest.raises(RncImportError):
        validate(result, LoadConfig(min_rows=1, anomaly_limit=0))


def test_overlong_row_is_one_anomaly() -> None:
    rnc = rnc9()
    result = parsed(",".join("1234567"), csv_record(rnc, "OK"))
    assert result.anomaly_count == 1
    assert [row.rnc for row in result.rows] == [rnc]


def test_blank_lines_are_not_anomalies() -> None:
    result = parsed("", csv_record(rnc9(), "OK"), "   ")
    assert len(result.rows) == 1
    assert result.anomaly_count == 0


def test_summary_lines_list_each_fact() -> None:
    short, nine, eleven = "90000001", rnc9(), rnc11()
    result = parsed(
        csv_record(short, "A", "ACTIVO"),
        csv_record(nine, "B", "SUSPENDIDO", activity="VENTAS", regime="NORMAL"),
        csv_record(eleven, "C", "ACTIVO", started="01/02/2003", regime="RST"),
        csv_record("NOPE", "D", "ACTIVO"),
        txt=(txt_record(eleven, "COMERCIAL"),),
    )
    assert summary_lines(result) == [
        "rows=2",
        "file_date=2026-10-18",
        f"entry={CSV_ENTRY}",
        "anomalies=0",
        "dropped=2",
        "duplicates=0",
        f"parsed_bytes={parsed_byte_estimate(result.rows)}",
        "trade_name_filled=1",
        "activity_filled=1",
        "start_date_filled=1",
        "regime_filled=2",
        "activity_avg_length=6.0",
        "trade_names=loaded",
        "trade_name_txt_values=1",
        "trade_name_txt_distinct=1",
        "trade_name_txt_avg_length=9",
        "trade_name_txt_no_letters=0",
        "trade_name_same_as_name=0",
        f"csv_header={ascii(list(HEADER))}",
        "date_shape blank=1",
        "date_shape dd/dd/dddd=1",
        "dropped_sample reason=rnc_length digits=8",
        "dropped_sample reason=rnc_length digits=0",
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
        activity="X\tY",
        start_date=date(2019, 3, 7),
        regime="RST",
    )
    assert copy_text((row,)) == (
        "123456789\tA\\\\B\\tC\\rD\\nE\t\\N\tACTIVO\t2026-10-18\t"
        "X\\tY\t2019-03-07\tRST\n"
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
        "COPY public.dgii_rnc_load (rnc, name, trade_name, status, file_date, "
        "activity, start_date, regime) FROM STDIN WITH (FORMAT text);\n"
    ) in sql
    assert "123456789\tACME\t\\N\tACTIVO\t2026-10-18\t\\N\t\\N\t\\N\n" in sql
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
        csv_record("000000001", "NINE"),
        csv_record("00000000001", "ELEVEN"),
        csv_record("000000001", "NINE2"),
    )
    assert [(row.rnc, row.name) for row in result.rows] == [
        ("000000001", "NINE2"),
        ("00000000001", "ELEVEN"),
    ]
    assert result.duplicate_count == 1


def test_unretained_parse_reports_the_same_summary() -> None:
    repeated, other, short = rnc9(), rnc11(), "90000001"
    payload = registry_zip(
        csv_file(
            csv_record(short, "A", "ACTIVO"),
            csv_record(repeated, "B", "SUSPENDIDO", activity="VENTAS", regime="RST"),
            csv_record(repeated, "B2", "ACTIVO", started="01/02/2003"),
            csv_record(other, "C", "ACTIVO"),
            csv_record("NOPE", "D", "ACTIVO"),
        ),
    )
    names = txt_zip(txt_record(other, "COMERCIAL"))
    result = parse_zip(payload, trade_name_zip=names, keep_rows=False)
    assert result.spill_path is not None
    try:
        expected_copy = (
            f"{repeated}\tB2\t\\N\tACTIVO\t2026-10-18\t\\N\t2003-02-01\t\\N\n"
            f"{other}\tC\tCOMERCIAL\tACTIVO\t2026-10-18\t\\N\t\\N\t\\N\n"
        )
        assert result.rows == ()
        assert summary_lines(result) == [
            "rows=2",
            "file_date=2026-10-18",
            f"entry={CSV_ENTRY}",
            "anomalies=0",
            "dropped=2",
            "duplicates=1",
            f"parsed_bytes={len(expected_copy.encode('utf-8'))}",
            "trade_name_filled=1",
            "activity_filled=0",
            "start_date_filled=1",
            "regime_filled=0",
            "activity_avg_length=0.0",
            "trade_names=loaded",
            "trade_name_txt_values=1",
            "trade_name_txt_distinct=1",
            "trade_name_txt_avg_length=9",
            "trade_name_txt_no_letters=0",
            "trade_name_same_as_name=0",
            f"csv_header={ascii(list(HEADER))}",
            "date_shape blank=2",
            "date_shape dd/dd/dddd=1",
            "dropped_sample reason=rnc_length digits=8",
            "dropped_sample reason=rnc_length digits=0",
            "status ACTIVO=2",
            "rnc_length 9=1",
            "rnc_length 11=1",
        ]
        assert Path(result.spill_path).read_text(encoding="utf-8") == expected_copy
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
        b"SET client_encoding = 'UTF8';\n"
        b"TRUNCATE public.dgii_rnc_load;\n"
        b"COPY public.dgii_rnc_load (rnc, name, trade_name, status, file_date, "
        b"activity, start_date, regime) FROM STDIN WITH (FORMAT text);\n"
        + body
        + b"\\.\n"
    )


def test_parse_of_a_large_registry_stays_under_80_mib(tmp_path: Path) -> None:
    path = tmp_path / "rnc.zip"
    count = 150_000
    records = [
        csv_record(
            f"{i:09d}",
            "NAME",
            activity="VENTA AL POR MENOR",
            started="01/02/2003",
            regime="NORMAL",
        )
        for i in range(count)
    ]
    names = tmp_path / "rnc-txt.zip"
    names.write_bytes(txt_zip(*[txt_record(f"{i:09d}", "TRADE") for i in range(count)]))
    path.write_bytes(registry_zip(csv_file(*records)))
    script = (
        "import re, runpy, sys\n"
        "sys.argv = ['dgii_rnc_import', 'parse', sys.argv[1], sys.argv[2]]\n"
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
        [sys.executable, "-S", "-c", script, str(path), str(names)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0
    assert completed.stderr == f"rows {count} below minimum 700000\n"
    rss_kb = int(completed.stdout.strip().splitlines()[-1])
    assert rss_kb < 80 * 1024
