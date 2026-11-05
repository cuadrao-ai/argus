"""Compatibility matrix: which code works on which schema (local, synthetic, nothing hosted).

Builds three schema states from a production-equivalent fixture (the ledger rows production has, effects of
main's files): S0 today, S1 after C0 (the website migration alone), S2 after C1 (the consumer files plus the
one unrecorded older file), each through the real applier. Then runs the real-Postgres test files of each
code version (previous production `main` and the candidate) against a fresh copy of each schema.

    ARGUS_REHEARSAL_ADMIN_URL=postgresql://postgres:postgres@127.0.0.1:58902/postgres \
    ARGUS_REHEARSAL_CONTAINER=supabase_db_<project> ARGUS_REHEARSAL_CANDIDATE=<sha> ARGUS_COMPAT_OLD_ROOT=<main checkout> \
    ARGUS_COMPAT_PYTHON=<python with pytest and psycopg> python docs/reports/evidence/cuadrao-compat-matrix-20261008/compat_matrix.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location(
    "rehearse",
    ROOT
    / "docs/reports/evidence/cuadrao-migration-rehearsal-20261007/rehearse_migration_upgrade.py",
)
assert spec and spec.loader
rehearse = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(ROOT))
sys.path.insert(
    0, str(ROOT / "docs/reports/evidence/cuadrao-migration-rehearsal-20261007")
)
spec.loader.exec_module(rehearse)

import psycopg  # noqa: E402

gate = rehearse.gate
CANDIDATE = rehearse.CANDIDATE
OLD_ROOT = Path(os.environ["ARGUS_COMPAT_OLD_ROOT"])
PYTHON = os.environ["ARGUS_COMPAT_PYTHON"]
SCHEMAS = ("compat_s0", "compat_s1", "compat_s2")


def build_s0() -> None:
    main_files = gate.read_candidate_migrations(ROOT, rehearse.MAIN)
    by_version = {m.version: m for m in gate.read_candidate_migrations(ROOT, CANDIDATE)}
    by_name = {m.name: m for m in main_files}
    rehearse.recreate("compat_s0")
    with psycopg.connect(rehearse.url("compat_s0"), autocommit=True) as connection:
        for migration in main_files:
            if migration.version != rehearse.MISSING_OLDER:
                rehearse.run_file(connection, migration, False)
        for version, name, _count, _hash in rehearse.PRODUCTION_ROWS:
            short = name.split("_", 1)[1] if name[:8].isdigit() and "_" in name else name
            match = by_version.get(version) or by_name.get(short)
            statements = (
                []
                if match is None
                else (
                    [match.source]
                    if version == "20260812183000"
                    else list(match.statements)
                )
            )
            connection.execute(
                "insert into supabase_migrations.schema_migrations (version, statements, name) values (%s, %s, %s)",
                (version, statements, name),
            )


def clone(source: str, target: str) -> None:
    with psycopg.connect(rehearse.ADMIN, autocommit=True) as admin:
        admin.execute(f"drop database if exists {target} with (force)")
        admin.execute(f"create database {target} template {source}")


def apply(
    database: str, versions: list[str], *extra: str, candidate: str | None = None
) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(versions, handle)
    env = {**os.environ, "ARGUS_APPLY_DATABASE_URL": rehearse.url(database)}
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/ops/apply_approved_migrations.py"), "--candidate-sha", candidate or CANDIDATE,
         "--approved-file", handle.name, "--allow-host", "127.0.0.1", "--allow-database", database, "--execute", *extra],
        check=True, env=env, cwd=ROOT, stdout=subprocess.DEVNULL,
    )  # fmt: skip


def build_schemas() -> None:
    build_s0()
    pending = sorted(
        m.version
        for m in gate.read_candidate_migrations(ROOT, CANDIDATE)
        if m.version > "20260914120000"
    )
    c0, c1 = ["20260920000000"], [v for v in pending if v != "20260920000000"]
    clone("compat_s0", "compat_s1")
    apply("compat_s1", c0)
    clone("compat_s1", "compat_s2")
    apply(
        "compat_s2",
        c1,
        "--unrecorded",
        rehearse.MISSING_OLDER,
        "--allow-mid-file-commit",
        rehearse.MID_FILE_COMMIT,
    )


def run_tests(code_root: Path, schema: str, label: str) -> dict[str, object]:
    run_db = f"run_{label}"
    clone(schema, run_db)
    env = {
        **os.environ,
        "ARGUS_DISPOSABLE_DATABASE_URL": rehearse.url(run_db),
        "PYTHONPATH": str(code_root / "src"),
    }
    files = sorted(
        str(p.relative_to(code_root)) for p in (code_root / "tests").glob("*postgres*.py")
    )
    result = subprocess.run(
        [PYTHON, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider", "-rfE", *files],
        cwd=code_root, env=env, capture_output=True, text=True, timeout=3600, check=False,
    )  # fmt: skip
    tail = (
        result.stdout.strip().splitlines()[-1]
        if result.stdout.strip()
        else result.stderr[-200:]
    )
    failed = [
        line.split(" ")[1]
        for line in result.stdout.splitlines()
        if line.startswith(("FAILED ", "ERROR "))
    ]
    counts = {
        k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|skipped|error)", tail)
    }
    with psycopg.connect(rehearse.ADMIN, autocommit=True) as admin:
        admin.execute(f"drop database if exists {run_db} with (force)")
    return {
        "code": label.split("__")[0],
        "schema": schema,
        "files": len(files),
        "summary": tail,
        "counts": counts,
        "failed": failed,
    }


def add_storage_schema(database: str) -> None:
    """Hosted Supabase always has the storage schema; the throwaway databases get it from the local container."""

    container = rehearse.CONTAINER
    dump = subprocess.check_output(
        [
            "docker",
            "exec",
            container,
            "pg_dump",
            "-U",
            "postgres",
            "-s",
            "-n",
            "storage",
            "postgres",
        ]
    )
    subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", database, "-q"],
        input=dump, check=True, capture_output=True,
    )  # fmt: skip


def tail_main() -> int:
    """After the freeze: the Business tail applied on top of C1, tested with Build 1 and Build 2 code."""

    build2_root = Path(os.environ["ARGUS_COMPAT_BUILD2_ROOT"])
    build2_sha = os.environ["ARGUS_COMPAT_BUILD2_SHA"]
    tail = os.environ["ARGUS_COMPAT_TAIL"].split(",")
    clone("compat_s2", "compat_s3")
    add_storage_schema("compat_s3")
    apply("compat_s3", tail, candidate=build2_sha)
    results = []
    for label, root in (
        ("previous_main", OLD_ROOT),
        ("build1", ROOT),
        ("build2", build2_root),
    ):
        outcome = run_tests(root, "compat_s3", f"{label}__compat_s3")
        outcome["code"] = label
        print(json.dumps(outcome), flush=True)
        results.append(outcome)
    (HERE / "results_tail.json").write_text(json.dumps(results, indent=2))
    return 0


def main() -> int:
    if os.environ.get("ARGUS_COMPAT_TAIL"):
        return tail_main()
    build_schemas()
    results = []
    for code_label, code_root in (("previous_main", OLD_ROOT), ("candidate", ROOT)):
        for schema in SCHEMAS:
            outcome = run_tests(code_root, schema, f"{code_label}__{schema}")
            outcome["code"] = code_label
            print(json.dumps(outcome), flush=True)
            results.append(outcome)
    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
