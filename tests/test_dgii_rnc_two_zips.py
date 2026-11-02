"""The job's two zips: the CSV is required, and the TXT must never stop the load."""

from __future__ import annotations

import io
import os
import subprocess
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from faker import Faker

from scripts.ops.dgii_rnc_import import LOAD, main, parse_zip, summary_lines
from tests.dgii_rnc_zip import (
    TXT_ENTRY,
    csv_file,
    csv_record,
    registry_zip,
    trade_name_zip,
    txt_file,
    txt_record,
    txt_zip,
)

fake = Faker("es")
Faker.seed(20261102)


def rnc9() -> str:
    return fake.numerify("9########")


def company() -> str:
    return fake.company().replace("\u2019", "'")


def _torn_txt_zip() -> bytes:
    payload = bytearray(txt_zip(txt_record(rnc9(), company())))
    payload[len(TXT_ENTRY) + 35] ^= 0xFF
    return bytes(payload)


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        (None, "no file given"),
        ("/nonexistent/rnc-txt.zip", "FileNotFoundError"),
        (b"<html>not a zip</html>", "BadZipFile"),
        (_torn_txt_zip(), "BadZipFile"),
        (trade_name_zip(("OTHER.TXT", b"")), "zip holds 0 DGII_RNC.TXT entries"),
        (
            trade_name_zip((TXT_ENTRY, b""), ("OTHER/DGII_RNC.TXT", b"")),
            "zip holds 2 DGII_RNC.TXT entries",
        ),
    ],
)
def test_a_failed_txt_zip_loads_every_row_and_the_summary_says_so(
    source: bytes | str | None, reason: str
) -> None:
    rnc = rnc9()
    legal = company()
    result = parse_zip(
        registry_zip(csv_file(csv_record(rnc, legal))), trade_name_zip=source
    )
    assert [(row.rnc, row.name, row.trade_name) for row in result.rows] == [
        (rnc, legal, None)
    ]
    lines = summary_lines(result)
    assert "trade_name_filled=0" in lines
    assert f"trade_names=unavailable reason={reason}: previous names stay" in lines


def test_a_txt_inside_the_csv_zip_is_not_read() -> None:
    rnc = rnc9()
    archive = io.BytesIO(registry_zip(csv_file(csv_record(rnc, company()))))
    with zipfile.ZipFile(archive, "a") as extra:
        extra.writestr(TXT_ENTRY, txt_file(txt_record(rnc, company())))
    result = parse_zip(archive.getvalue())
    assert result.rows[0].trade_name is None


def test_parse_cli_prints_the_file_facts_and_then_applies_the_minimum(
    tmp_path, capsys
) -> None:
    path = tmp_path / "rnc-csv.zip"
    path.write_bytes(registry_zip(csv_file(csv_record(rnc9(), company()))))
    assert main(["parse", str(path), str(tmp_path / "rnc-txt.zip")]) == 1
    captured = capsys.readouterr()
    assert captured.err == "rows 1 below minimum 700000\n"
    assert "rows=1\n" in captured.out
    assert (
        "trade_names=unavailable reason=FileNotFoundError: previous names stay\n"
        in captured.out
    )


def test_parse_cli_joins_the_names_from_the_second_zip(
    tmp_path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr(
        "scripts.ops.dgii_rnc_import.LOAD", replace(LOAD, min_rows=1)
    )
    rnc = rnc9()
    csv_path = tmp_path / "rnc-csv.zip"
    txt_path = tmp_path / "rnc-txt.zip"
    csv_path.write_bytes(registry_zip(csv_file(csv_record(rnc, company()))))
    txt_path.write_bytes(txt_zip(txt_record(rnc, company())))
    assert main(["parse", str(csv_path), str(txt_path)]) == 0
    assert "trade_name_filled=1\n" in capsys.readouterr().out


def test_load_cli_keeps_going_when_the_txt_zip_is_missing(
    tmp_path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr(
        "scripts.ops.dgii_rnc_import.LOAD", replace(LOAD, min_rows=1)
    )
    monkeypatch.delenv("SUPABASE_STAGING_DB_URL", raising=False)
    path = tmp_path / "rnc-csv.zip"
    path.write_bytes(registry_zip(csv_file(csv_record(rnc9(), company()))))
    assert main(["load", str(path), str(tmp_path / "rnc-txt.zip")]) == 0
    output = capsys.readouterr().out
    assert "rows=1\n" in output
    assert output.endswith("load skipped: SUPABASE_STAGING_DB_URL is absent\n")


DAILY_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ops/dgii_rnc_daily.sh"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/dgii-rnc-import.yml"
FAKE_CURL = """#!/bin/bash
echo called >> "$CURL_LOG"
while [ $# -gt 1 ]; do
  [ "$1" = "-o" ] && out="$2"
  shift
done
case "$1" in
  */RNC_CONTRIBUYENTES.zip) code="$CSV_RESPONSE"; body="$CSV_BODY" ;;
  */DGII_RNC.zip) code="$TXT_RESPONSE"; body="$TXT_BODY" ;;
  *) exit 99 ;;
esac
if [ -n "$body" ]; then cp "$body" "$out"; else printf 'partial' > "$out"; fi
[ "$code" = "dead" ] && exit 28
printf 'http_code=%s\\n' "$code"
"""


def _run_daily(
    tmp_path: Path, *args: str, csv_response: str = "200", txt_response: str = "200", **env: str
) -> subprocess.CompletedProcess[str]:
    curl = tmp_path / "bin" / "curl"
    curl.parent.mkdir(exist_ok=True)
    curl.write_text(FAKE_CURL)
    curl.chmod(0o755)
    return subprocess.run(
        ["bash", "--noprofile", "--norc", str(DAILY_SCRIPT), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{curl.parent}:{os.environ['PATH']}",
            "CURL_LOG": str(tmp_path / "curl.log"),
            "CSV_RESPONSE": csv_response,
            "TXT_RESPONSE": txt_response,
            "CSV_BODY": "",
            "TXT_BODY": "",
            **env,
        },
    )


def test_the_workflow_downloads_through_the_daily_script() -> None:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["import"]["steps"]
    step = next(step for step in steps if step["name"].startswith("Download"))
    assert step["run"].strip() == "bash scripts/ops/dgii_rnc_daily.sh download"


@pytest.mark.parametrize("failure", ["503", "dead"])
def test_a_failed_csv_download_stops_the_job(tmp_path: Path, failure: str) -> None:
    completed = _run_daily(tmp_path, "download", csv_response=failure)
    assert completed.returncode != 0
    assert "download failed: rnc-csv.zip" in completed.stdout


@pytest.mark.parametrize("failure", ["503", "dead"])
def test_a_failed_txt_download_leaves_no_file_and_the_job_goes_on(
    tmp_path: Path, failure: str
) -> None:
    completed = _run_daily(tmp_path, "download", txt_response=failure)
    assert completed.returncode == 0
    assert (tmp_path / "rnc-csv.zip").exists()
    assert not (tmp_path / "rnc-txt.zip").exists()
    assert "previous names stay" in completed.stdout


def test_both_downloads_keep_their_files(tmp_path: Path) -> None:
    completed = _run_daily(tmp_path, "download")
    assert completed.returncode == 0
    assert (tmp_path / "rnc-csv.zip").exists()
    assert (tmp_path / "rnc-txt.zip").exists()


@pytest.mark.parametrize(
    ("env", "decision"),
    [
        ({}, "load skipped: DGII_RNC_LOAD_ENABLED is not true"),
        (
            {"DGII_RNC_LOAD_ENABLED": "false", "SUPABASE_STAGING_DB_URL": "postgres://db"},
            "load skipped: DGII_RNC_LOAD_ENABLED is not true",
        ),
        (
            {"DGII_RNC_LOAD_ENABLED": "true"},
            "load skipped: SUPABASE_STAGING_DB_URL is absent",
        ),
    ],
)
def test_the_daily_job_downloads_nothing_until_it_may_load(
    tmp_path: Path, env: dict[str, str], decision: str
) -> None:
    completed = _run_daily(tmp_path, **env)
    assert completed.returncode == 0
    assert completed.stdout.strip() == decision
    assert not (tmp_path / "curl.log").exists()


def test_the_daily_job_runs_the_load_and_leaves_no_file_behind(tmp_path: Path) -> None:
    csv_zip = tmp_path / "source-csv.zip"
    csv_zip.write_bytes(registry_zip(csv_file(csv_record(rnc9(), company()))))
    txt = tmp_path / "source-txt.zip"
    txt.write_bytes(txt_zip(txt_record(rnc9(), company())))
    before = sorted(path.name for path in tmp_path.iterdir())
    completed = _run_daily(
        tmp_path,
        DGII_RNC_LOAD_ENABLED="true",
        SUPABASE_STAGING_DB_URL="postgres://db",
        CSV_BODY=str(csv_zip),
        TXT_BODY=str(txt),
        TMPDIR=str(tmp_path),
    )
    assert completed.returncode == 1
    assert "rows=1\n" in completed.stdout
    assert completed.stderr == "rows 1 below minimum 700000\n"
    after = {path.name for path in tmp_path.iterdir()} - {"bin", "curl.log"}
    assert sorted(after) == [name for name in before if name != "bin"]
