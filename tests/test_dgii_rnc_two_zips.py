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
    assert f"trade_names=unavailable reason={reason}: names stay null" in lines


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
        "trade_names=unavailable reason=FileNotFoundError: names stay null\n"
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
    assert capsys.readouterr().out == "load skipped: SUPABASE_STAGING_DB_URL is absent\n"


FAKE_CURL = """#!/bin/bash
while [ $# -gt 1 ]; do
  [ "$1" = "-o" ] && out="$2"
  shift
done
case "$1" in
  */RNC_CONTRIBUYENTES.zip) code="$CSV_RESPONSE" ;;
  */DGII_RNC.zip) code="$TXT_RESPONSE" ;;
  *) exit 99 ;;
esac
printf 'partial' > "$out"
[ "$code" = "dead" ] && exit 28
printf 'http_code=%s\\n' "$code"
"""


def _run_download_step(tmp_path: Path, csv_response: str, txt_response: str):
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/dgii-rnc-import.yml"
    steps = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]["import"]["steps"]
    script = tmp_path / "step.sh"
    script.write_text(
        next(step["run"] for step in steps if step["name"].startswith("Download"))
    )
    curl = tmp_path / "bin" / "curl"
    curl.parent.mkdir()
    curl.write_text(FAKE_CURL)
    curl.chmod(0o755)
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{curl.parent}:{os.environ['PATH']}",
            "CSV_RESPONSE": csv_response,
            "TXT_RESPONSE": txt_response,
        },
    )


@pytest.mark.parametrize("failure", ["503", "dead"])
def test_a_failed_csv_download_stops_the_job(tmp_path: Path, failure: str) -> None:
    completed = _run_download_step(tmp_path, failure, "200")
    assert completed.returncode != 0
    assert "download failed: rnc-csv.zip" in completed.stdout


@pytest.mark.parametrize("failure", ["503", "dead"])
def test_a_failed_txt_download_leaves_no_file_and_the_job_goes_on(
    tmp_path: Path, failure: str
) -> None:
    completed = _run_download_step(tmp_path, "200", failure)
    assert completed.returncode == 0
    assert (tmp_path / "rnc-csv.zip").exists()
    assert not (tmp_path / "rnc-txt.zip").exists()
    assert "names stay null" in completed.stdout


def test_both_downloads_keep_their_files(tmp_path: Path) -> None:
    completed = _run_download_step(tmp_path, "200", "200")
    assert completed.returncode == 0
    assert (tmp_path / "rnc-csv.zip").exists()
    assert (tmp_path / "rnc-txt.zip").exists()

