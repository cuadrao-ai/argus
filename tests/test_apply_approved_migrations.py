"""The applier refuses everything it was not explicitly given."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ops import apply_approved_migrations as applier
from scripts.ops.production_migration_gate import CandidateMigration


def _migration(
    version: str, name: str, sql: str = "create table t (id int);"
) -> CandidateMigration:
    return CandidateMigration.from_source(
        f"supabase/migrations/{version}_{name}.sql", sql
    )


CANDIDATES = [
    _migration(
        "20260505000001", "old_missing", "alter table t drop constraint if exists c;"
    ),
    _migration("20260606000001", "old_effect_exists"),
    _migration("20260914120000", "ledger_head"),
    _migration("20260925120000", "first_new"),
    _migration("20260928200000", "second_new"),
    _migration("20260929090000", "third_new"),
]
APPLIED = ["20260606000001", "20260914120000"]
ALLOW = (["127.0.0.1"], ["rehearsal"])


# --- target guard -----------------------------------------------------------------


def test_only_the_named_local_target_is_accepted() -> None:
    applier.check_target("postgresql://u:p@127.0.0.1:5432/rehearsal", *ALLOW, environ={})


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@db.abcdefghijklmnopqrst.supabase.co:5432/postgres",
        "postgresql://u:p@aws-0-us-east-1.pooler.supabase.com:5432/postgres",
        "postgresql://u:p@127.0.0.1:5432/postgres",
        "postgresql://u:p@10.0.0.9:5432/rehearsal",
        "postgresql://u:p@127.0.0.1:5432/rehearsal?host=elsewhere",
        "postgresql://u:p@127.0.0.1:5432,db.abcdefghijklmnopqrst.supabase.co:5432/rehearsal",
        "postgresql://u:p@db.abcdefghijklmnopqrst.supabase.co,127.0.0.1/rehearsal",
        "postgresql://u:p@DB.ABCDEFGHIJKLMNOPQRST.SUPABASE.CO:5432/rehearsal",
        "postgresql://u:p@db.abcdefghijklmnopqrst.supabase.co.:5432/rehearsal",
        "postgresql://u:p@db%2Eabcdefghijklmnopqrst%2Esupabase%2Eco:5432/rehearsal",
        "postgresql://u:p@supabase.co:5432/rehearsal",
        "postgresql://u:p@db.abcdefghijklmnopqrst.supabase.co%2C127.0.0.1:5432/rehearsal",
    ],
)
def test_hosted_unlisted_and_multi_host_targets_are_refused(url: str) -> None:
    with pytest.raises(applier.ApplyError):
        applier.check_target(url, *ALLOW, environ={})


@pytest.mark.parametrize(
    "allowed",
    [
        "db.abcdefghijklmnopqrst.supabase.co.",
        "DB.ABCDEFGHIJKLMNOPQRST.SUPABASE.CO",
        "db%2Eabcdefghijklmnopqrst%2Esupabase%2Eco",
        "aws-0-us-east-1.pooler.supabase.com",
    ],
)
def test_a_hosted_name_on_the_allow_list_is_refused(allowed: str) -> None:
    with pytest.raises(applier.ApplyError, match="hosted Supabase"):
        applier.check_target(
            "postgresql://u:p@127.0.0.1:5432/rehearsal",
            ["127.0.0.1", allowed],
            ["rehearsal"],
            environ={},
        )


@pytest.mark.parametrize(
    "name", ["PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE"]
)
def test_environment_that_can_redirect_the_connection_is_refused(name: str) -> None:
    with pytest.raises(applier.ApplyError):
        applier.check_target(
            "postgresql://u:p@127.0.0.1:5432/rehearsal", *ALLOW, environ={name: "x"}
        )


class _Row:
    def __init__(self, value: object) -> None:
        self.value = value

    def fetchone(self) -> tuple[object, ...]:
        return (self.value,)


def _connected(host: str, hostaddr: str, database: str) -> SimpleNamespace:
    return SimpleNamespace(
        info=SimpleNamespace(host=host, hostaddr=hostaddr),
        execute=lambda _sql: _Row(database),
    )


def test_the_real_connection_is_checked_not_just_the_url() -> None:
    applier.verify_connection(_connected("127.0.0.1", "127.0.0.1", "rehearsal"), *ALLOW)
    for host, hostaddr, database in (
        ("db.abcdefghijklmnopqrst.supabase.co", "", "rehearsal"),
        ("127.0.0.1", "52.1.2.3", "rehearsal"),
        ("127.0.0.1", "127.0.0.1", "postgres"),
    ):
        with pytest.raises(applier.ApplyError):
            applier.verify_connection(_connected(host, hostaddr, database), *ALLOW)


@pytest.mark.parametrize(
    "host",
    ["db.abcdefghijklmnopqrst.supabase.co.", "DB.ABCDEFGHIJKLMNOPQRST.SUPABASE.CO"],
)
def test_the_connected_host_is_refused_when_it_is_hosted_in_any_spelling(
    host: str,
) -> None:
    with pytest.raises(applier.ApplyError, match="hosted Supabase"):
        applier.verify_connection(
            _connected(host, "127.0.0.1", "rehearsal"), [host, "127.0.0.1"], ["rehearsal"]
        )


# --- plan rules -------------------------------------------------------------------


def test_recorded_steps_are_ordered_and_classified() -> None:
    steps = applier.plan_steps(CANDIDATES, APPLIED, ["20260928200000", "20260925120000"])
    assert [(s.version, s.record) for s in steps] == [
        ("20260925120000", True),
        ("20260928200000", True),
    ]


def test_a_batch_may_stop_early_but_may_not_skip() -> None:
    assert [
        s.version for s in applier.plan_steps(CANDIDATES, APPLIED, ["20260925120000"])
    ] == ["20260925120000"]
    with pytest.raises(applier.ApplyError, match="skips"):
        applier.plan_steps(CANDIDATES, APPLIED, ["20260929090000"])
    with pytest.raises(applier.ApplyError, match="skips"):
        applier.plan_steps(CANDIDATES, APPLIED, ["20260925120000", "20260929090000"])


def test_unrecorded_history_runs_without_a_ledger_row() -> None:
    steps = applier.plan_steps(
        CANDIDATES, APPLIED, ["20260925120000"], ["20260505000001"]
    )
    assert [(s.version, s.record) for s in steps] == [
        ("20260505000001", False),
        ("20260925120000", True),
    ]
    assert steps[0].classification == "destructive"


@pytest.mark.parametrize(
    ("approved", "unrecorded"),
    [
        (["20260999999999"], []),  # not a candidate
        (["20260914120000"], []),  # already applied
        (["20260505000001"], []),  # recorded below the threshold
        (["20260925120000"], ["20260925120000"]),  # both lists
        ([], ["20260925120000"]),  # unrecorded above the threshold
        (["20260925120000", "20260925120000"], []),  # duplicate
        ([], ["20260505000001", "20260505000001"]),  # duplicate
    ],
)
def test_plan_refuses_anything_unapproved(
    approved: list[str], unrecorded: list[str]
) -> None:
    with pytest.raises(applier.ApplyError):
        applier.plan_steps(CANDIDATES, APPLIED, approved, unrecorded)


def test_recorded_versions_must_follow_the_ledger_head() -> None:
    candidates = [*CANDIDATES, _migration("20260915000000", "behind_head")]
    with pytest.raises(applier.ApplyError):
        applier.plan_steps(candidates, ["20260925120000"], ["20260915000000"])


# --- transaction control ------------------------------------------------------------

WRAPPED = "-- note\nbegin;\ncreate table a (id int);\ncreate table b (id int);\ncommit;\n"
MID_COMMIT = (
    "alter table r drop constraint if exists c, add constraint c check (x > 0) not valid;\n"
    "commit;\nalter table r validate constraint c;\n"
)


def test_a_wrapped_file_is_one_transaction_without_its_own_begin_and_commit() -> None:
    migration = _migration("20260925120000", "wrapped", WRAPPED)
    segments = applier.split_segments(migration.statements)
    assert len(segments) == 1
    assert [s.split(";")[0].split("\n")[-1] for s in segments[0]] == [
        "create table a (id int)",
        "create table b (id int)",
    ]
    # the ledger still records the file exactly as the gate splits it, wrapper included
    assert len(migration.statements) == 4


def test_a_commit_in_the_middle_needs_an_explicit_flag() -> None:
    candidates = [*CANDIDATES[:3], _migration("20260925120000", "mid", MID_COMMIT)]
    with pytest.raises(applier.ApplyError, match="allow-mid-file-commit"):
        applier.plan_steps(candidates, APPLIED, ["20260925120000"])
    steps = applier.plan_steps(
        candidates, APPLIED, ["20260925120000"], allow_mid_file_commit=["20260925120000"]
    )
    assert [len(segment) for segment in steps[0].segments] == [1, 1]


@pytest.mark.parametrize(
    "sql",
    [
        "create table t (id int);\nrollback;",
        "begin;\nsavepoint a;\ncommit;",
        "create table t (id int);\nbegin;\ncommit;",
    ],
)
def test_other_transaction_control_is_refused(sql: str) -> None:
    with pytest.raises(applier.ApplyError):
        applier.split_segments(_migration("20260925120000", "x", sql).statements)


# --- applying ---------------------------------------------------------------------------


class _Transaction:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def __enter__(self) -> None:
        self.log.append("begin")

    def __exit__(self, exc_type: object, *_: object) -> bool:
        self.log.append("rollback" if exc_type else "commit")
        return False


class _Connection:
    def __init__(self, fail_on: str | None = None) -> None:
        self.log: list[str] = []
        self.fail_on = fail_on

    def transaction(self) -> _Transaction:
        return _Transaction(self.log)

    def execute(self, statement: str, params: object = None) -> None:
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError("boom")
        if params is not None and "set_config" in statement:
            self.log.append(f"timeout={params[0]}")  # type: ignore[index]
        else:
            self.log.append(
                "ledger" if params is not None else statement.strip().split("\n")[-1]
            )


def test_each_file_is_one_transaction_and_records_its_own_ledger_row() -> None:
    steps = applier.plan_steps(
        CANDIDATES, APPLIED, ["20260925120000"], ["20260505000001"]
    )
    connection = _Connection()
    seen: list[str] = []
    done = applier.apply_steps(
        connection, steps, on_done=lambda step: seen.append(step.version)
    )
    assert done == seen == ["20260505000001", "20260925120000"]
    assert connection.log == [
        "begin", "timeout=5s", "alter table t drop constraint if exists c", "commit",
        "begin", "timeout=5s", "create table t (id int)", "ledger", "commit",
    ]  # fmt: skip


def test_a_wrapped_file_runs_and_records_inside_one_transaction() -> None:
    candidates = [*CANDIDATES[:3], _migration("20260925120000", "wrapped", WRAPPED)]
    steps = applier.plan_steps(candidates, APPLIED, ["20260925120000"])
    connection = _Connection()
    applier.apply_steps(connection, steps)
    assert connection.log == [
        "begin", "timeout=5s", "create table a (id int)", "create table b (id int)", "ledger", "commit",
    ]  # fmt: skip


def test_a_mid_file_commit_records_the_ledger_row_in_the_last_transaction() -> None:
    candidates = [*CANDIDATES[:3], _migration("20260925120000", "mid", MID_COMMIT)]
    steps = applier.plan_steps(
        candidates, APPLIED, ["20260925120000"], allow_mid_file_commit=["20260925120000"]
    )
    connection = _Connection()
    applier.apply_steps(connection, steps)
    assert connection.log.count("ledger") == 1
    assert connection.log[-2:] == ["ledger", "commit"]
    assert connection.log.count("begin") == 2


def test_a_failing_file_rolls_back_and_stops_the_run() -> None:
    steps = applier.plan_steps(CANDIDATES, APPLIED, ["20260925120000", "20260928200000"])
    connection = _Connection(fail_on="create table")
    with pytest.raises(RuntimeError):
        applier.apply_steps(connection, steps)
    assert connection.log == ["begin", "timeout=5s", "rollback"]


def test_a_file_with_nothing_to_run_cannot_be_recorded() -> None:
    candidates = [
        *CANDIDATES[:3],
        _migration("20260925120000", "empty", "begin; commit;"),
    ]
    with pytest.raises(applier.ApplyError, match="no runnable statement"):
        applier.plan_steps(candidates, APPLIED, ["20260925120000"])


def test_each_committed_transaction_is_reported() -> None:
    candidates = [*CANDIDATES[:3], _migration("20260925120000", "mid", MID_COMMIT)]
    steps = applier.plan_steps(
        candidates, APPLIED, ["20260925120000"], allow_mid_file_commit=["20260925120000"]
    )
    seen: list[tuple[str, int, int]] = []
    applier.apply_steps(
        _Connection(), steps, on_segment=lambda s, n, t: seen.append((s.version, n, t))
    )
    assert seen == [("20260925120000", 1, 2), ("20260925120000", 2, 2)]


@pytest.mark.parametrize("value", ["5s", "500ms", "1min"])
def test_lock_timeout_accepts_plain_durations(value: str) -> None:
    assert applier.check_lock_timeout(value) == value


@pytest.mark.parametrize(
    "value", ["", "0", "0s", "0ms", "05s", "5", "5 s; drop table x", "-1s", "1h"]
)
def test_lock_timeout_refuses_anything_else(value: str) -> None:
    with pytest.raises(applier.ApplyError):
        applier.check_lock_timeout(value)


# --- the command line -----------------------------------------------------------------


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows

    def fetchone(self) -> tuple[object, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class _Server:
    """Stands in for psycopg.connect against a local database."""

    def __init__(self, ledger: list[str], lock_free: bool = True) -> None:
        self.ledger, self.lock_free = ledger, lock_free
        self.info = SimpleNamespace(host="127.0.0.1", hostaddr="127.0.0.1")
        self.statements: list[str] = []

    def __enter__(self) -> _Server:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def transaction(self) -> _Transaction:
        return _Transaction([])

    def execute(self, sql: str, params: object = None) -> _Cursor:
        self.statements.append(sql)
        if "current_database" in sql:
            return _Cursor([("rehearsal",)])
        if "pg_try_advisory_lock" in sql:
            return _Cursor([(self.lock_free,)])
        if "schema_migrations order by" in sql:
            return _Cursor([(version,) for version in self.ledger])
        return _Cursor([])


def _run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, server: _Server, *extra: str
) -> int:
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps(["20260925120000"]))
    monkeypatch.setenv(
        "ARGUS_APPLY_DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/rehearsal"
    )
    for name in applier._REFUSED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("psycopg.connect", lambda *_a, **_k: server)
    monkeypatch.setattr(applier.gate, "read_candidate_migrations", lambda *_a: CANDIDATES)
    return applier.main(
        ["--candidate-sha", "x" * 40, "--approved-file", str(approved),
         "--allow-host", "127.0.0.1", "--allow-database", "rehearsal", *extra]
    )  # fmt: skip


def test_the_default_run_only_prints_the_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server = _Server(APPLIED)
    assert _run(monkeypatch, tmp_path, server) == 0
    assert "dry run" in capsys.readouterr().out
    assert not any("create table" in statement for statement in server.statements)


def test_a_held_lock_refuses_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(applier.ApplyError, match="holds the migration lock"):
        _run(monkeypatch, tmp_path, _Server(APPLIED, lock_free=False), "--execute")


def test_the_run_lock_is_taken_before_the_ledger_is_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    server = _Server(APPLIED)
    _run(monkeypatch, tmp_path, server)
    lock = next(
        i for i, sql in enumerate(server.statements) if "pg_try_advisory_lock" in sql
    )
    ledger = next(
        i
        for i, sql in enumerate(server.statements)
        if "schema_migrations order by" in sql
    )
    assert lock < ledger


def test_a_missing_url_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ARGUS_APPLY_DATABASE_URL", raising=False)
    with pytest.raises(applier.ApplyError, match="is not set"):
        applier.main(
            ["--candidate-sha", "x" * 40, "--approved-file", str(tmp_path / "a.json"),
             "--allow-host", "127.0.0.1", "--allow-database", "rehearsal"]
        )  # fmt: skip


# --- hosted approval record -------------------------------------------------------------

REF = "abcdefghijklmnopqrst"
SHA = "a" * 40
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
VERSIONS = ["20260925120000", "20260928200000"]
DIRECT = f"db.{REF}.supabase.co"
POOLER = "aws-0-us-east-2.pooler.supabase.com"


def _record(**changes: object) -> str:
    record: dict[str, object] = {
        "id": "apply-2026-10-20",
        "project_ref": REF,
        "hosts": [DIRECT, POOLER],
        "database": "postgres",
        "candidate_sha": SHA,
        "versions_sha256": applier.versions_digest(VERSIONS),
        "issued_at": "2026-10-20T10:00:00Z",
        "expires_at": "2026-10-21T10:00:00Z",
        "approved_by": "founder",
        "approval_reference": "https://github.com/lagarcess/argus/issues/833#issuecomment-1",
    }
    record.update(changes)
    return json.dumps(record)


def _approval(**changes: object) -> applier.HostedApproval:
    return applier.parse_hosted_approval(_record(**changes), SHA, VERSIONS, (), NOW)


def test_a_matching_record_is_accepted_and_names_its_hosts() -> None:
    approval = _approval()
    assert approval.hosts == (DIRECT, POOLER)
    assert approval.id == "apply-2026-10-20"


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_sha": "b" * 40},
        {"versions_sha256": "0" * 64},
        {"expires_at": "2026-10-20T11:00:00Z"},
        {"issued_at": "2026-10-20T13:00:00Z", "expires_at": "2026-10-21T13:00:00Z"},
        {"issued_at": "2026-10-01T00:00:00Z", "expires_at": "2026-10-22T00:00:00Z"},
        {"issued_at": "2026-10-20T10:00:00", "expires_at": "2026-10-21T10:00:00"},
        {"project_ref": "short"},
        {"hosts": ["db.example.com"]},
        {"hosts": []},
        {"id": ""},
    ],
)
def test_a_record_for_another_run_or_time_or_host_is_refused(
    changes: dict[str, object],
) -> None:
    with pytest.raises(applier.ApplyError):
        _approval(**changes)


def test_a_record_with_missing_or_extra_keys_is_refused() -> None:
    extra = json.loads(_record())
    extra["note"] = "x"
    for text in (json.dumps(extra), json.dumps({"id": "x"}), "not json", "[]"):
        with pytest.raises(applier.ApplyError):
            applier.parse_hosted_approval(text, SHA, VERSIONS, (), NOW)


def test_the_digest_covers_which_versions_run_without_a_ledger_row() -> None:
    assert applier.versions_digest(VERSIONS) != applier.versions_digest(
        VERSIONS, ["20260505000001"]
    )
    assert applier.versions_digest(VERSIONS) == applier.versions_digest(VERSIONS[::-1])


@pytest.mark.parametrize(
    "url",
    [
        f"postgresql://postgres:p@{DIRECT}:5432/postgres",
        f"postgresql://postgres.{REF}:p@{POOLER}:5432/postgres",
    ],
)
def test_a_named_hosted_target_is_accepted_with_its_record(url: str) -> None:
    hosted = _approval()
    applier.check_target(url, [DIRECT, POOLER], ["postgres"], environ={}, hosted=hosted)


@pytest.mark.parametrize(
    ("url", "allow_hosts", "allow_databases"),
    [
        ("postgresql://postgres:p@db.zzzzzzzzzzzzzzzzzzzz.supabase.co:5432/postgres", ["db.zzzzzzzzzzzzzzzzzzzz.supabase.co"], ["postgres"]),
        (f"postgresql://postgres:p@{DIRECT}:5432/other", [DIRECT], ["other"]),
        (f"postgresql://postgres:p@{DIRECT}:5432/postgres", [DIRECT, "db.example.supabase.co"], ["postgres"]),
        (f"postgresql://postgres.zzzzzzzzzzzzzzzzzzzz:p@{POOLER}:5432/postgres", [POOLER], ["postgres"]),
        ("postgresql://u:p@127.0.0.1:5432/postgres", ["127.0.0.1"], ["postgres"]),
    ],
)  # fmt: skip
def test_a_hosted_target_the_record_does_not_name_is_refused(
    url: str, allow_hosts: list[str], allow_databases: list[str]
) -> None:
    with pytest.raises(applier.ApplyError):
        applier.check_target(
            url, allow_hosts, allow_databases, environ={}, hosted=_approval()
        )


def test_a_trailing_dot_is_the_same_named_host() -> None:
    applier.check_target(
        f"postgresql://postgres:p@{DIRECT}.:5432/postgres",
        [DIRECT],
        ["postgres"],
        environ={},
        hosted=_approval(),
    )


def test_a_hosted_target_without_a_record_is_still_refused() -> None:
    with pytest.raises(applier.ApplyError, match="approval record"):
        applier.check_target(
            f"postgresql://postgres:p@{DIRECT}:5432/postgres",
            [DIRECT],
            ["postgres"],
            environ={},
        )


def test_the_hosted_connection_must_reach_a_named_host_and_database() -> None:
    hosted = _approval()
    ok = SimpleNamespace(
        info=SimpleNamespace(host=POOLER, hostaddr="3.4.5.6", port=5432),
        execute=lambda _sql: _Row("postgres"),
    )
    applier.verify_connection(ok, [DIRECT, POOLER], ["postgres"], hosted)
    elsewhere = SimpleNamespace(
        info=SimpleNamespace(
            host="aws-0-eu-west-1.pooler.supabase.com", hostaddr="3.4.5.6"
        ),
        execute=lambda _sql: _Row("postgres"),
    )
    with pytest.raises(applier.ApplyError):
        applier.verify_connection(elsewhere, [DIRECT, POOLER], ["postgres"], hosted)
    wrong_db = SimpleNamespace(
        info=SimpleNamespace(host=POOLER, hostaddr="3.4.5.6", port=5432),
        execute=lambda _sql: _Row("other"),
    )
    with pytest.raises(applier.ApplyError):
        applier.verify_connection(wrong_db, [DIRECT, POOLER], ["postgres"], hosted)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        cwd=root, check=True, capture_output=True,
    )  # fmt: skip


def _repo(tmp_path: Path) -> tuple[Path, str]:
    _git(tmp_path, "init", "-q")
    (tmp_path / "base.txt").write_text("base")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-q", "-m", "candidate")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return tmp_path, sha


def test_the_record_must_be_tracked_clean_and_on_top_of_the_candidate(
    tmp_path: Path,
) -> None:
    root, sha = _repo(tmp_path)
    path = "docs/release-manifests/approval.json"
    record = root / path
    record.parent.mkdir(parents=True)
    record.write_text("{}")
    with pytest.raises(applier.ApplyError, match="not tracked"):
        applier.read_committed_record(root, path, sha)
    _git(root, "add", path)
    with pytest.raises(applier.ApplyError, match="uncommitted"):
        applier.read_committed_record(root, path, sha)
    _git(root, "commit", "-q", "-m", "approval")
    assert applier.read_committed_record(root, path, sha) == "{}"
    record.write_text('{"edited": true}')
    with pytest.raises(applier.ApplyError, match="uncommitted"):
        applier.read_committed_record(root, path, sha)
    record.write_text("{}")
    other = subprocess.run(
        ["git", "commit-tree", "HEAD^{tree}", "-m", "unrelated"], cwd=root, check=True,
        capture_output=True, text=True, env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test"},
    ).stdout.strip()  # fmt: skip
    with pytest.raises(applier.ApplyError, match="on top of the candidate"):
        applier.read_committed_record(root, path, other)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    with pytest.raises(applier.ApplyError, match="on top of the candidate"):
        applier.read_committed_record(root, path, head)


def test_the_record_is_read_from_the_commit_not_the_working_tree_and_never_a_symlink(
    tmp_path: Path,
) -> None:
    root, sha = _repo(tmp_path)
    outside = tmp_path.parent / "outside-record.json"
    outside.write_text("{}")
    link = root / "docs/release-manifests/linked.json"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "linked record")
    with pytest.raises(applier.ApplyError, match="symlink"):
        applier.read_committed_record(root, "docs/release-manifests/linked.json", sha)


@pytest.mark.parametrize(
    "path", ["approval.json", "docs/other/approval.json", "../approval.json", "/etc/passwd",
             "docs/release-manifests/../../approval.json"],
)  # fmt: skip
def test_the_record_path_must_sit_under_release_manifests(
    tmp_path: Path, path: str
) -> None:
    root, sha = _repo(tmp_path)
    with pytest.raises(applier.ApplyError, match="under docs/release-manifests"):
        applier.read_committed_record(root, path, sha)


def test_a_hosted_target_must_use_port_5432() -> None:
    with pytest.raises(applier.ApplyError, match="port 5432"):
        applier.check_target(
            f"postgresql://postgres.{REF}:p@{POOLER}:6543/postgres", [POOLER], ["postgres"],
            environ={}, hosted=_approval(),
        )  # fmt: skip


def test_a_record_cannot_name_another_projects_direct_host() -> None:
    with pytest.raises(applier.ApplyError, match="direct host"):
        _approval(hosts=["db.zzzzzzzzzzzzzzzzzzzz.supabase.co"])


def test_the_pooler_user_must_be_exactly_postgres_dot_the_ref() -> None:
    for user in (f"postgres.x{REF}", f"postgres.{REF}x", REF, "postgres"):
        with pytest.raises(applier.ApplyError):
            applier.check_target(
                f"postgresql://{user}:p@{POOLER}:5432/postgres", [POOLER], ["postgres"],
                environ={}, hosted=_approval(),
            )  # fmt: skip


def test_the_digest_covers_which_files_may_commit_in_several_transactions() -> None:
    assert applier.versions_digest(VERSIONS) != applier.versions_digest(
        VERSIONS, (), ["20261003120001"]
    )


def test_a_hosted_run_needs_the_ca_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record = _record(versions_sha256=applier.versions_digest(["20260925120000"]))
    monkeypatch.setattr(applier, "read_committed_record", lambda *_a: record)
    monkeypatch.setattr(
        applier,
        "datetime",
        SimpleNamespace(now=lambda _tz: NOW, fromisoformat=datetime.fromisoformat),
    )
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps(["20260925120000"]))
    monkeypatch.setenv(
        "ARGUS_APPLY_DATABASE_URL", f"postgresql://postgres:p@{DIRECT}:5432/postgres"
    )
    with pytest.raises(applier.ApplyError, match="ssl-root-cert"):
        applier.main(
            ["--candidate-sha", SHA, "--approved-file", str(approved), "--allow-host", DIRECT,
             "--allow-database", "postgres", "--hosted-approval", "docs/release-manifests/a.json"]
        )  # fmt: skip


def test_a_local_run_leaves_the_ssl_mode_to_libpq(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, object] = {}
    server = _Server(APPLIED)

    def connect(*_a: object, **options: object) -> _Server:
        seen.update(options)
        return server

    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps(["20260925120000"]))
    monkeypatch.setenv(
        "ARGUS_APPLY_DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/rehearsal"
    )
    for name in applier._REFUSED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("psycopg.connect", connect)
    monkeypatch.setattr(applier.gate, "read_candidate_migrations", lambda *_a: CANDIDATES)
    applier.main(
        ["--candidate-sha", "x" * 40, "--approved-file", str(approved),
         "--allow-host", "127.0.0.1", "--allow-database", "rehearsal"]
    )  # fmt: skip
    assert "sslmode" not in seen and "sslrootcert" not in seen


def test_a_hosted_url_without_a_port_or_with_a_bad_one_is_refused() -> None:
    for url in (
        f"postgresql://postgres.{REF}:p@{POOLER}/postgres",
        f"postgresql://postgres.{REF}:p@{POOLER}:abc/postgres",
        f"postgresql://postgres.{REF}:p@{POOLER}:6543/postgres",
    ):
        with pytest.raises(applier.ApplyError, match="port 5432"):
            applier.check_target(
                url, [POOLER], ["postgres"], environ={}, hosted=_approval()
            )


def test_the_hosted_connection_must_be_on_port_5432() -> None:
    wrong = SimpleNamespace(
        info=SimpleNamespace(host=POOLER, hostaddr="3.4.5.6", port=6543),
        execute=lambda _sql: _Row("postgres"),
    )
    with pytest.raises(applier.ApplyError, match="port 5432"):
        applier.verify_connection(wrong, [POOLER], ["postgres"], _approval())


# --- unrecorded versions leave no trace, so each has an effect probe ------------------------


class _EffectConnection:
    def __init__(self, definitions: list[tuple[str, str]]) -> None:
        self.definitions = definitions

    def execute(self, sql: str) -> _Cursor:
        assert "pg_constraint" in sql, "the probe only reads the catalog"
        return _Cursor(list(self.definitions))  # type: ignore[arg-type]


OLD = [
    (
        "backtest_runs_asset_class_check",
        "CHECK (asset_class = ANY (ARRAY['equity', 'crypto']))",
    ),
    (
        "strategies_asset_class_check",
        "CHECK (asset_class = ANY (ARRAY['equity', 'crypto']))",
    ),
]
NEW = [
    (name, definition.replace("'crypto'", "'crypto', 'currency_pair'"))
    for name, definition in OLD
]


def test_the_probe_sees_the_effect_only_when_both_checks_allow_currency_pair() -> None:
    assert not applier.effect_present(_EffectConnection(OLD), "20260505000001")
    assert applier.effect_present(_EffectConnection(NEW), "20260505000001")
    assert not applier.effect_present(_EffectConnection(NEW[:1]), "20260505000001")
    assert not applier.effect_present(_EffectConnection([]), "20260505000001")


def test_an_unrecorded_version_whose_effect_exists_is_refused_before_it_runs() -> None:
    steps = applier.plan_steps(CANDIDATES, APPLIED, [], ["20260505000001"])
    applier.check_unrecorded_effects(_EffectConnection(OLD), steps)
    with pytest.raises(applier.ApplyError, match="already has its effect"):
        applier.check_unrecorded_effects(_EffectConnection(NEW), steps)


def test_an_unrecorded_version_without_a_probe_is_refused() -> None:
    candidates = [*CANDIDATES, _migration("20260101000001", "old_other")]
    steps = applier.plan_steps(candidates, APPLIED, [], ["20260101000001"])
    with pytest.raises(applier.ApplyError, match="no effect probe"):
        applier.check_unrecorded_effects(_EffectConnection(OLD), steps)


def test_recorded_steps_need_no_probe() -> None:
    steps = applier.plan_steps(CANDIDATES, APPLIED, ["20260925120000"])
    applier.check_unrecorded_effects(_EffectConnection(NEW), steps)


def test_an_unrecorded_version_without_a_probe_is_refused_before_connecting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    approved = tmp_path / "approved.json"
    approved.write_text("[]")
    monkeypatch.setenv(
        "ARGUS_APPLY_DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/rehearsal"
    )
    monkeypatch.setattr("psycopg.connect", lambda *_a, **_k: pytest.fail("connected"))
    with pytest.raises(applier.ApplyError, match="no effect probe"):
        applier.main(
            ["--candidate-sha", "x" * 40, "--approved-file", str(approved), "--unrecorded", "20260101000001",
             "--allow-host", "127.0.0.1", "--allow-database", "rehearsal"]
        )  # fmt: skip


def test_the_probe_is_scoped_to_the_two_tables() -> None:
    query, _ = applier._EFFECT_PROBES["20260505000001"]
    assert (
        "public.strategies'::regclass" in query
        and "public.backtest_runs'::regclass" in query
    )


_STAGING_APPROVAL = (
    "docs/release-manifests/2026-10-18-staging-security-waitlist-apply.json"
)
_STAGING_SHA = "c940a8b319086bea023bc63b8b6817a87dbffafd"
_STAGING_VERSIONS = ["20261018030000", "20261018030016", "20261018040000"]


def test_the_staging_security_waitlist_record_holds_inside_its_window() -> None:
    text = (Path(__file__).resolve().parents[1] / _STAGING_APPROVAL).read_text()
    approval = applier.parse_hosted_approval(
        text,
        _STAGING_SHA,
        _STAGING_VERSIONS,
        (),
        datetime.fromisoformat("2026-10-19T15:00:00-05:00"),
    )
    assert approval == applier.HostedApproval(
        "staging-apply-2026-10-18",
        "skedzwocnmrhfigiwyzi",
        (
            "db.skedzwocnmrhfigiwyzi.supabase.co",
            "aws-0-us-east-1.pooler.supabase.com",
        ),
        "postgres",
        _STAGING_SHA,
        "b963585771acb2fd0922a3d8cf9d020e60a5dc14786fe4f032f8764d0d49d866",
        datetime.fromisoformat("2026-10-21T03:38:00-05:00"),
    )
    with pytest.raises(applier.ApplyError, match="not valid now"):
        applier.parse_hosted_approval(
            text,
            _STAGING_SHA,
            _STAGING_VERSIONS,
            (),
            datetime.fromisoformat("2026-10-21T03:38:00-05:00"),
        )


_STAGING_APPROVAL_B = (
    "docs/release-manifests/2026-10-18-staging-invites-bank-matching-registry-apply.json"
)
_STAGING_SHA_B = "fb6d969505f364fa08e4eb89e7317619f7de4781"
_STAGING_VERSIONS_B = [
    "20261018040438",
    "20261018180000",
    "20261018190000",
    "20261018210000",
]


def test_the_staging_invites_bank_matching_registry_record_holds_inside_its_window() -> (
    None
):
    text = (Path(__file__).resolve().parents[1] / _STAGING_APPROVAL_B).read_text()
    approval = applier.parse_hosted_approval(
        text,
        _STAGING_SHA_B,
        _STAGING_VERSIONS_B,
        (),
        datetime.fromisoformat("2026-10-19T15:00:00-05:00"),
    )
    assert approval == applier.HostedApproval(
        "staging-apply-2026-10-18-b",
        "skedzwocnmrhfigiwyzi",
        (
            "db.skedzwocnmrhfigiwyzi.supabase.co",
            "aws-0-us-east-1.pooler.supabase.com",
        ),
        "postgres",
        _STAGING_SHA_B,
        "6832fd3b890048119f8e881a108ca02c2b96445731180f208132bb5327b563fc",
        datetime.fromisoformat("2026-10-21T10:56:00-05:00"),
    )
    for versions in (
        [*_STAGING_VERSIONS_B, "20261018220000"],
        [*_STAGING_VERSIONS_B, "20261018220000", "20261018230000"],
        _STAGING_VERSIONS_B[:3],
    ):
        with pytest.raises(applier.ApplyError, match="different list of versions"):
            applier.parse_hosted_approval(
                text,
                _STAGING_SHA_B,
                versions,
                (),
                datetime.fromisoformat("2026-10-19T15:00:00-05:00"),
            )
    with pytest.raises(applier.ApplyError, match="not valid now"):
        applier.parse_hosted_approval(
            text,
            _STAGING_SHA_B,
            _STAGING_VERSIONS_B,
            (),
            datetime.fromisoformat("2026-10-21T10:56:00-05:00"),
        )


_STAGING_REF = "skedzwocnmrhfigiwyzi"
_STAGING_DIRECT = f"db.{_STAGING_REF}.supabase.co"
_STAGING_POOLER = "aws-0-us-east-1.pooler.supabase.com"
_STAGING_OTHER_POOLER = "aws-0-eu-west-1.pooler.supabase.com"
_STAGING_PASSWORD = "fake-password-do-not-echo"
_STAGING_NOW = datetime.fromisoformat("2026-10-19T15:00:00-05:00")
_STAGING_RECORDS = (
    (_STAGING_APPROVAL, _STAGING_SHA, _STAGING_VERSIONS),
    (_STAGING_APPROVAL_B, _STAGING_SHA_B, _STAGING_VERSIONS_B),
)


def _staging_approval(path: str, sha: str, versions: list[str]) -> applier.HostedApproval:
    text = (Path(__file__).resolve().parents[1] / path).read_text()
    return applier.parse_hosted_approval(text, sha, versions, (), _STAGING_NOW)


def _staging_url(
    user: str, host: str, port: int = 5432, password: str = _STAGING_PASSWORD
) -> str:
    return f"postgresql://{user}:{password}@{host}:{port}/postgres"


@pytest.mark.parametrize(("path", "sha", "versions"), _STAGING_RECORDS)
def test_each_staging_record_accepts_the_session_pooler(
    path: str, sha: str, versions: list[str]
) -> None:
    applier.check_target(
        _staging_url(f"postgres.{_STAGING_REF}", _STAGING_POOLER),
        [_STAGING_DIRECT, _STAGING_POOLER],
        ["postgres"],
        environ={},
        hosted=_staging_approval(path, sha, versions),
    )


@pytest.mark.parametrize(("path", "sha", "versions"), _STAGING_RECORDS)
def test_each_staging_record_still_accepts_the_direct_host(
    path: str, sha: str, versions: list[str]
) -> None:
    hosted = _staging_approval(path, sha, versions)
    url = _staging_url("postgres", _STAGING_DIRECT)
    applier.check_target(url, [_STAGING_DIRECT], ["postgres"], environ={}, hosted=hosted)
    applier.check_target(
        url, [_STAGING_DIRECT, _STAGING_POOLER], ["postgres"], environ={}, hosted=hosted
    )


@pytest.mark.parametrize(
    ("user", "port", "host", "pattern"),
    [
        ("postgres.zzzzzzzzzzzzzzzzzzzz", 5432, _STAGING_POOLER, "project ref"),
        (f"postgres.{_STAGING_REF}", 6543, _STAGING_POOLER, "port 5432"),
        (f"postgres.{_STAGING_REF}", 5432, _STAGING_OTHER_POOLER, "not named"),
    ],
)
@pytest.mark.parametrize(("path", "sha", "versions"), _STAGING_RECORDS)
def test_a_staging_pooler_url_is_refused_for_the_wrong_ref_port_or_host(
    user: str,
    port: int,
    host: str,
    pattern: str,
    path: str,
    sha: str,
    versions: list[str],
) -> None:
    with pytest.raises(applier.ApplyError, match=pattern) as caught:
        applier.check_target(
            _staging_url(user, host, port),
            [_STAGING_DIRECT, _STAGING_POOLER],
            ["postgres"],
            environ={},
            hosted=_staging_approval(path, sha, versions),
        )
    leaked = _STAGING_PASSWORD in str(caught.value)
    assert not leaked


def test_a_quoted_pooler_url_is_accepted_for_either_staging_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for path, sha, versions in _STAGING_RECORDS:
        for quote in ("'", '"'):
            password = "fake'password" if quote == "'" else _STAGING_PASSWORD
            bare = _staging_url(
                f"postgres.{_STAGING_REF}", _STAGING_POOLER, password=password
            )
            _assert_quoted_dry_run(
                monkeypatch,
                tmp_path,
                capsys,
                path,
                sha,
                versions,
                quote + bare + quote,
                password,
            )


def test_mismatched_quotes_around_the_url_are_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path, sha, versions = _STAGING_RECORDS[0]
    bare = _staging_url(f"postgres.{_STAGING_REF}", _STAGING_POOLER)
    monkeypatch.setattr("psycopg.connect", lambda *_a, **_k: pytest.fail("connected"))
    with pytest.raises(applier.ApplyError) as caught:
        _quoted_main(monkeypatch, tmp_path, path, sha, versions, "'" + bare + '"')
    leaked = _STAGING_PASSWORD in str(caught.value)
    assert not leaked


def _assert_quoted_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    path: str,
    sha: str,
    versions: list[str],
    url: str,
    password: str,
) -> None:
    seen: dict[str, object] = {}

    def connect(target: str, **options: object) -> _PlanServer:
        seen["wrapped"] = target[:1] in "'\"" or target[-1:] in "'\""
        seen["inner"] = password in target
        seen["sslmode"] = options.get("sslmode")
        return _PlanServer(["20261018000000"], _STAGING_POOLER)

    monkeypatch.setattr("psycopg.connect", connect)
    assert _quoted_main(monkeypatch, tmp_path, path, sha, versions, url) == 0
    captured = capsys.readouterr()
    leaked = password in captured.out or password in captured.err
    assert seen == {"wrapped": False, "inner": True, "sslmode": "verify-full"}
    assert "dry run" in captured.out
    assert not leaked


def _quoted_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
    sha: str,
    versions: list[str],
    url: str,
) -> int:
    text = (Path(__file__).resolve().parents[1] / path).read_text()
    monkeypatch.setattr(applier, "read_committed_record", lambda *_args: text)
    monkeypatch.setattr(
        applier,
        "datetime",
        SimpleNamespace(
            now=lambda _tz: _STAGING_NOW, fromisoformat=datetime.fromisoformat
        ),
    )
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps(versions))
    cert = tmp_path / "ca.pem"
    cert.write_text("fixture")
    monkeypatch.setenv("ARGUS_APPLY_DATABASE_URL", url)
    for name in applier._REFUSED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    head = "20261018000000"
    candidates = [
        _migration(head, "ledger_head"),
        *[_migration(version, "step") for version in versions],
    ]
    monkeypatch.setattr(applier.gate, "read_candidate_migrations", lambda *_a: candidates)
    return applier.main(
        [
            "--candidate-sha", sha, "--approved-file", str(approved),
            "--allow-host", _STAGING_DIRECT, "--allow-host", _STAGING_POOLER,
            "--allow-database", "postgres", "--hosted-approval", path,
            "--ssl-root-cert", str(cert),
        ]
    )  # fmt: skip


class _PlanServer:
    def __init__(self, ledger: list[str], host: str) -> None:
        self.ledger = ledger
        self.info = SimpleNamespace(host=host, hostaddr="203.0.113.10", port=5432)

    def __enter__(self) -> _PlanServer:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> _Cursor:
        if "current_database" in sql:
            return _Cursor([("postgres",)])
        if "pg_try_advisory_lock" in sql:
            return _Cursor([(True,)])
        if "schema_migrations order by" in sql:
            return _Cursor([(version,) for version in self.ledger])
        return _Cursor([])
