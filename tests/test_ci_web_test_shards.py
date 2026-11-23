"""The web shard proof passes only when the shards ran every file bun found once."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "web_test_shards.py"
FAKE = Faker()


def web_files(count: int) -> list[str]:
    names = {f"__tests__/{FAKE.unique.slug()}.test.ts" for _ in range(count)}
    return sorted(names)


def write_shard(
    folder: Path,
    index: int,
    files: list[str],
    *,
    count: int = 3,
    total: int,
    reported: list[str] | None = None,
    failures: int = 0,
    shard_line: bool = True,
) -> Path:
    suites = "".join(
        f'  <testsuite name="{name}" file="{name}" tests="1" failures="0">\n'
        f'    <testcase name="{FAKE.sentence()}" file="{name}" />\n'
        "  </testsuite>\n"
        for name in (files if reported is None else reported)
    )
    report = folder / f"web-{index - 1}.xml"
    report.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuites name="bun test" failures="{failures}">\n{suites}</testsuites>\n',
        encoding="utf-8",
    )
    line = f"\x1b[2m--shard={index}/{count}:\x1b[0m running {len(files)}/{total} test files\n"
    report.with_suffix(".log").write_text(
        f"bun test v1.3.14\n{line if shard_line else ''}Ran {len(files)} tests.\n",
        encoding="utf-8",
    )
    return report


def round_robin(files: list[str], count: int = 3) -> list[list[str]]:
    return [files[index::count] for index in range(count)]


def prove(tmp_path: Path, reports: list[Path]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            *map(str, reports),
            "--output",
            str(tmp_path / "proof.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_exact_union_writes_the_full_file_list(tmp_path: Path) -> None:
    files = web_files(10)
    reports = [
        write_shard(tmp_path, index + 1, shard, total=len(files))
        for index, shard in enumerate(round_robin(files))
    ]

    result = prove(tmp_path, reports)

    assert result.returncode == 0, result.stderr
    proof = json.loads((tmp_path / "proof.json").read_text())
    assert proof["files"] == files
    assert proof["file_count"] == 10
    assert proof["selected_counts"] == {"1": 4, "2": 3, "3": 3}
    assert proof["union_exact"] is True


def test_a_missing_shard_fails(tmp_path: Path) -> None:
    files = web_files(9)
    reports = [
        write_shard(tmp_path, index + 1, shard, total=len(files))
        for index, shard in enumerate(round_robin(files))
    ]

    result = prove(tmp_path, reports[:2])

    assert result.returncode == 1
    assert "missing or repeated shard" in result.stderr


def test_a_file_in_two_shards_fails(tmp_path: Path) -> None:
    files = web_files(9)
    shards = round_robin(files)
    shards[1] = [*shards[1][:-1], shards[0][0]]
    reports = [
        write_shard(tmp_path, index + 1, shard, total=len(files))
        for index, shard in enumerate(shards)
    ]

    result = prove(tmp_path, reports)

    assert result.returncode == 1
    assert f"{shards[0][0]} ran in shards 1 and 2" in result.stderr


def test_a_file_bun_found_but_no_shard_ran_fails(tmp_path: Path) -> None:
    files = web_files(9)
    reports = [
        write_shard(tmp_path, index + 1, shard, total=len(files) + 1)
        for index, shard in enumerate(round_robin(files))
    ]

    result = prove(tmp_path, reports)

    assert result.returncode == 1
    assert "shards ran 9 files but bun found 10" in result.stderr


def test_a_report_missing_a_selected_file_fails(tmp_path: Path) -> None:
    files = web_files(9)
    shards = round_robin(files)
    reports = [
        write_shard(
            tmp_path,
            index + 1,
            shard,
            total=len(files),
            reported=shard[:-1] if index == 2 else None,
        )
        for index, shard in enumerate(shards)
    ]

    result = prove(tmp_path, reports)

    assert result.returncode == 1
    assert "shard 3 ran 3 files but its report names 2" in result.stderr


def test_shards_that_disagree_on_the_full_count_fail(tmp_path: Path) -> None:
    files = web_files(9)
    reports = [
        write_shard(tmp_path, index + 1, shard, total=len(files) + index)
        for index, shard in enumerate(round_robin(files))
    ]

    result = prove(tmp_path, reports)

    assert result.returncode == 1
    assert "disagree" in result.stderr


@pytest.mark.parametrize(
    "broken",
    [{"failures": 1}, {"shard_line": False}],
    ids=["failed-test", "no-shard-line"],
)
def test_failed_or_unlabelled_shard_fails(tmp_path: Path, broken: dict) -> None:
    files = web_files(9)
    reports = [
        write_shard(
            tmp_path, index + 1, shard, total=len(files), **(broken if index == 0 else {})
        )
        for index, shard in enumerate(round_robin(files))
    ]

    result = prove(tmp_path, reports)

    assert result.returncode == 1
    assert "Web shard evidence failed" in result.stderr
