"""The load stops on silent loss, logs no row, and survives a bad TXT."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from faker import Faker

from scripts.ops.dgii_rnc_import import (
    LOAD,
    LoadConfig,
    RncImportError,
    _apply_load,
    _physical_lines,
    _psql,
    headroom_sql,
    parse_zip,
    require_load_headroom,
    size_report_sql,
    summary_lines,
    validate,
)
from tests.dgii_rnc_zip import (
    TXT_ENTRY,
    csv_file,
    csv_record,
    registry_zip,
    trade_name_zip,
    txt_record,
    txt_zip,
)

fake = Faker("es")
Faker.seed(20261103)

MIB = 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]
RELOAD_TABLE_BYTES = 162 * MIB
STAGING_BYTES = 31 * MIB


def rnc9() -> str:
    return fake.numerify("9########")


def company() -> str:
    return fake.company().replace("’", "'")


def small(**limits: int) -> LoadConfig:
    return replace(LOAD, min_rows=1, **limits)


def _csv_with(rnc: str, name: str) -> bytes:
    return registry_zip(csv_file(csv_record(rnc, name)))


@pytest.mark.parametrize("ending", ["\r\n", "\n"], ids=["crlf", "lf"])
def test_either_line_ending_yields_the_trade_names(ending: str) -> None:
    first, second = rnc9(), rnc9()
    trade = company()
    body = ending.join([txt_record(first, trade), txt_record(second, "OTRO")]) + ending
    result = parse_zip(
        _csv_with(first, company()),
        trade_name_zip=trade_name_zip((TXT_ENTRY, body.encode("latin-1"))),
    )
    assert result.rows[0].trade_name == trade
    assert "trade_names=loaded" in summary_lines(result)


def test_a_line_ending_split_across_two_chunks_is_one_ending() -> None:
    assert list(_physical_lines(iter(["uno\r", "\ndos\n", "tres"]))) == [
        "uno",
        "dos",
        "tres",
    ]


def test_a_latin1_control_character_stays_inside_a_line() -> None:
    assert list(_physical_lines(iter(["uno\x85dos\r\n"]))) == ["uno\x85dos"]


def test_a_txt_with_no_pipes_ends_fast_and_counts_as_failed() -> None:
    body = "\r\n".join(f"{index};COMERCIAL;ACTIVO" for index in range(200_000))
    started = time.monotonic()
    result = parse_zip(
        _csv_with(rnc9(), company()),
        trade_name_zip=trade_name_zip((TXT_ENTRY, body.encode("latin-1"))),
    )
    assert time.monotonic() - started < 10
    assert result.trade_name_failure == "no trade names parsed"


def test_a_txt_with_no_line_breaks_counts_as_failed() -> None:
    payload = trade_name_zip((TXT_ENTRY, b"x" * (3 * MIB)))
    result = parse_zip(_csv_with(rnc9(), company()), trade_name_zip=payload)
    assert result.trade_name_failure == "txt line is over 1048576 characters"


def test_a_record_wrapped_past_the_cap_is_dropped_and_the_next_one_reads() -> None:
    rnc = rnc9()
    broken = "\r\n".join(["sin separadores"] * 5)
    result = parse_zip(
        _csv_with(rnc, company()),
        trade_name_zip=txt_zip(broken, txt_record(rnc, "COMERCIAL")),
    )
    assert result.rows[0].trade_name == "COMERCIAL"


@pytest.mark.parametrize(
    "payload",
    [None, b"not a zip", txt_zip(), txt_zip("sin separadores")],
    ids=["missing", "not_a_zip", "empty", "no_pipes"],
)
def test_a_failed_txt_takes_the_names_it_is_given(payload: bytes | None) -> None:
    rnc = rnc9()
    kept = company()
    result = parse_zip(
        _csv_with(rnc, company()),
        trade_name_zip=payload,
        previous_names=lambda: {rnc: kept},
    )
    assert result.rows[0].trade_name == kept
    assert "trade_name_filled=1" in summary_lines(result)
    assert "trade_name_txt_values=0" in summary_lines(result)


def test_a_good_txt_never_reads_the_previous_names() -> None:
    def refuse() -> dict[str, str]:
        raise AssertionError("previous names read")

    rnc = rnc9()
    result = parse_zip(
        _csv_with(rnc, company()),
        trade_name_zip=txt_zip(txt_record(rnc, "COMERCIAL")),
        previous_names=refuse,
    )
    assert result.rows[0].trade_name == "COMERCIAL"


def test_a_failed_read_of_the_previous_names_stops_the_load() -> None:
    def fail() -> dict[str, str]:
        raise RncImportError("psql failed")

    with pytest.raises(RncImportError, match="psql failed"):
        parse_zip(_csv_with(rnc9(), company()), previous_names=fail)


def test_a_headerless_csv_fails_with_no_cell_of_its_first_row() -> None:
    rnc, name = rnc9(), company()
    payload = registry_zip(f'"{rnc}","{name}","","","ACTIVO","NORMAL"\r\n'.encode("latin-1"))
    with pytest.raises(RncImportError) as caught:
        parse_zip(payload)
    message = str(caught.value)
    assert message == "csv header needs one RNC column: 6 columns, found []"
    assert rnc not in message
    assert name not in message


@pytest.mark.parametrize(
    ("rnc", "name"), [("12345678", "X"), ("123456789", " "), ("123456789", "X")]
)
def test_a_refused_row_is_not_quoted(rnc: str, name: str) -> None:
    result = parse_zip(
        registry_zip(csv_file(csv_record("123456789", "X"), csv_record("987654321", "Y")))
    )
    bad = replace(result.rows[0], rnc=rnc, name=name)
    with pytest.raises(RncImportError) as caught:
        validate(replace(result, rows=(bad, result.rows[1], bad)), small())
    assert rnc not in str(caught.value)


class _Failed:
    returncode = 1
    stdout = ""

    def __init__(self, stderr: str) -> None:
        self.stderr = stderr


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (
            'ERROR:  new row violates check constraint "c"\n'
            "DETAIL:  Failing row contains (123456789, ACME).\n"
            'CONTEXT:  COPY dgii_rnc_load, line 2: "123456789\tACME"\n',
            'ERROR:  new row violates check constraint "c"',
        ),
        (
            'psql:<stdin>:4: ERROR:  invalid byte sequence\nCONTEXT:  COPY x, line 2: "ACME"\n',
            "psql:<stdin>:4: ERROR:  invalid byte sequence",
        ),
        (
            'FATAL:  terminating connection\nCONTEXT:  COPY x, line 2: "ACME"\n',
            "FATAL:  terminating connection",
        ),
        ("", "psql failed"),
    ],
    ids=["error_line", "located_error", "no_error_line", "silent"],
)
def test_a_psql_failure_keeps_only_its_error_line(
    monkeypatch, stderr: str, expected: str
) -> None:
    monkeypatch.setattr(
        "scripts.ops.dgii_rnc_import.subprocess.run", lambda *a, **k: _Failed(stderr)
    )
    with pytest.raises(RncImportError) as caught:
        _psql("postgres://db", "select 1;")
    assert str(caught.value) == expected


def test_a_real_file_with_one_dropped_row_passes() -> None:
    result = parse_zip(
        registry_zip(csv_file(csv_record(rnc9(), company()), csv_record("12345678", "X")))
    )
    assert result.dropped_count == 1
    validate(result, small())


def _dropped_file(count: int) -> bytes:
    records = [csv_record(rnc9(), company())]
    records += [csv_record(f"{index:08d}", "X") for index in range(count)]
    return registry_zip(csv_file(*records))


def _blank_estado_file(count: int) -> bytes:
    records = [csv_record(rnc9(), company())]
    records += [
        csv_record(fake.unique.numerify("9########"), company(), "") for _ in range(count)
    ]
    return registry_zip(csv_file(*records))


@pytest.mark.parametrize(
    ("build", "dropped", "blank"),
    [(_dropped_file, 26, 0), (_blank_estado_file, 0, 26)],
    ids=["dropped", "blank_estado"],
)
def test_loss_past_the_limit_refuses_the_load(build, dropped: int, blank: int) -> None:
    validate(parse_zip(build(25)), small())
    with pytest.raises(RncImportError) as caught:
        validate(parse_zip(build(26)), small())
    assert str(caught.value) == (
        f"lost rows 26 exceed limit 25: dropped {dropped}, blank estado {blank}"
    )


def test_dropped_and_blank_estado_rows_count_together() -> None:
    records = [csv_record(rnc9(), company())]
    records += [csv_record(f"{index:08d}", "X") for index in range(13)]
    records += [
        csv_record(fake.unique.numerify("9########"), company(), "") for _ in range(13)
    ]
    result = parse_zip(registry_zip(csv_file(*records)))
    assert "blank_status=13" in summary_lines(result)
    with pytest.raises(RncImportError, match="lost rows 26 exceed limit 25"):
        validate(result, small())


def test_a_blank_activity_or_date_is_not_loss() -> None:
    rows = [csv_record(fake.unique.numerify("9########"), company()) for _ in range(40)]
    validate(parse_zip(registry_zip(csv_file(*rows))), small())


def test_the_defaults_pass_a_reload_at_staging_size() -> None:
    database = STAGING_BYTES + RELOAD_TABLE_BYTES
    peak = require_load_headroom(database, RELOAD_TABLE_BYTES, LOAD)
    assert peak - (database + RELOAD_TABLE_BYTES) < 10 * MIB
    assert peak <= LOAD.size_limit_bytes


def test_the_defaults_pass_a_first_load_at_staging_size() -> None:
    peak = require_load_headroom(STAGING_BYTES, 0, LOAD)
    assert 0 <= peak - (STAGING_BYTES + RELOAD_TABLE_BYTES) < 10 * MIB


def test_the_defaults_refuse_a_load_that_would_pass_the_limit() -> None:
    overfull = LOAD.size_limit_bytes - RELOAD_TABLE_BYTES + 1
    with pytest.raises(RncImportError):
        require_load_headroom(overfull, RELOAD_TABLE_BYTES, LOAD)
    with pytest.raises(RncImportError):
        require_load_headroom(overfull, 0, LOAD)


def test_a_table_past_the_floor_sets_the_headroom() -> None:
    table = LOAD.load_headroom_floor_bytes + 50 * MIB
    assert require_load_headroom(100 * MIB, table, LOAD) == 100 * MIB + table


class _Completed:
    returncode = 0
    stderr = ""

    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def test_a_stale_load_table_does_not_count_against_the_check(monkeypatch, capsys) -> None:
    """The copy truncates it first, so one failed swap must not block the next day."""
    live = 162 * MIB
    stale = 137 * MIB
    database = 31 * MIB + live + stale
    config = small()
    assert database + LOAD.load_headroom_floor_bytes > LOAD.size_limit_bytes

    def fake_run(args, *, input, text, capture_output, check):
        if input == headroom_sql(config):
            return _Completed(f"{database}\n{live}\n{stale}\n")
        if input == size_report_sql(config):
            return _Completed("1\n2\n3\n")
        return _Completed("1\n")

    monkeypatch.setattr("scripts.ops.dgii_rnc_import.subprocess.run", fake_run)
    result = parse_zip(_csv_with(rnc9(), company()))
    _apply_load("postgres://db", result, config)
    output = capsys.readouterr().out
    assert f"load_relation_bytes={stale}\n" in output
    assert f"peak_bytes={database - stale + LOAD.load_headroom_floor_bytes}\n" in output


def _blueprint() -> dict[str, dict]:
    config = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    return {service["name"]: service for service in config["services"]}


def test_the_refresh_is_manual_with_no_hosted_service() -> None:
    blueprint = _blueprint()
    assert not [service for service in blueprint.values() if service["type"] == "cron"]
    for service in blueprint.values():
        assert service.get("startCommand") != "bash scripts/ops/dgii_rnc_daily.sh"
    assert (ROOT / "scripts/ops/dgii_rnc_daily.sh").is_file()


def test_no_production_service_can_reach_the_daily_job() -> None:
    blueprint = _blueprint()
    for name in (
        "cuadrao-api",
        "cuadrao-app",
        "cuadrao-marketing",
        "cuadrao-documents-worker",
    ):
        assert blueprint[name]["branch"] == "main"
        keys = {entry["key"] for entry in blueprint[name].get("envVars", [])}
        assert not {key for key in keys if key.startswith("DGII_")}
        assert "SUPABASE_STAGING_DB_URL" not in keys


def test_the_runbook_names_the_loss_limit() -> None:
    runbook = (ROOT / "docs/runbooks/dgii-rnc-import.md").read_text(encoding="utf-8")
    assert f"More than {LOAD.loss_limit} lost rows fail the job" in runbook
