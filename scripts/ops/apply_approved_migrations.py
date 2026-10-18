"""Apply an explicit list of migration versions to a named database.

The Supabase CLI cannot do this job against production's ledger: it stops on
local files older than the remote head and on remote rows with no local file,
and ``--include-all`` would re-run history whose effects already exist. This
tool applies only the versions it is given, in order, and records each ledger
row exactly as ``production_migration_gate.py`` reads it (the file's own
version and name, statements split by the gate's splitter).

A hosted Supabase host is refused unless a committed hosted approval record names
it. The record carries the project ref, the exact host names and database, the
candidate commit, a digest of the exact version list, an expiry and the founder's
approval reference. The tool checks every one of them, requires the record to be
committed after the candidate and unmodified, connects with TLS required, and only
executes when ``--hosted-confirm`` repeats the record's id. With no record the
behaviour is the one for local databases. A name check cannot tell that an IP
literal is a hosted database, so an allow-listed IP literal is not recognised as
hosted; never allow-list one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from scripts.ops import production_migration_gate as gate
except ImportError:  # run as a script from the repository root
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.ops import production_migration_gate as gate

_HOSTED_SUFFIXES = (".supabase.co", ".supabase.com")
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
_REFUSED_ENVIRONMENT = ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE")
_LOCK_TIMEOUT = re.compile(r"[1-9]\d{0,5}(ms|s|min)")
_ADVISORY_LOCK_KEY = 7_340_118_221_605
_BEGIN = {"begin", "start"}
_COMMIT = {"commit", "end"}
_REFUSED_CONTROL = {"rollback", "abort", "savepoint", "release"}
_LEDGER_INSERT = (
    "insert into supabase_migrations.schema_migrations (version, statements, name)"
    " values (%s, %s, %s)"
)


def _plain_host(name: str) -> str:
    """The name libpq would connect to: decoded, lowercase, no trailing dot."""

    return unquote(name).lower().rstrip(".")


def _without_surrounding_quotes(value: str) -> str:
    """Drop one matching pair of quotes around an environment value."""

    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _is_hosted(name: str) -> bool:
    plain = _plain_host(name)
    return plain.endswith(_HOSTED_SUFFIXES) or plain in {"supabase.co", "supabase.com"}


_REF = re.compile(r"[a-z0-9]{20}")
_SHA = re.compile(r"[0-9a-f]{40}")
_RECORD_KEYS = {
    "id", "project_ref", "hosts", "database", "candidate_sha", "versions_sha256",
    "issued_at", "expires_at", "approved_by", "approval_reference",
}  # fmt: skip
_MAX_VALIDITY = timedelta(days=3)


@dataclass(frozen=True)
class HostedApproval:
    id: str
    project_ref: str
    hosts: tuple[str, ...]
    database: str
    candidate_sha: str
    versions_sha256: str
    expires_at: datetime


def versions_digest(
    approved: Sequence[str],
    unrecorded: Sequence[str] = (),
    mid_file_commit: Sequence[str] = (),
) -> str:
    """One digest for the exact run: what is recorded, what runs without a ledger row, and
    which files are allowed to commit in several transactions."""

    text = (
        "recorded:"
        + ",".join(sorted(approved))
        + "|unrecorded:"
        + ",".join(sorted(unrecorded))
        + "|mid-file-commit:"
        + ",".join(sorted(mid_file_commit))
    )
    return hashlib.sha256(text.encode()).hexdigest()


def parse_hosted_approval(
    text: str,
    candidate_sha: str,
    approved: Sequence[str],
    unrecorded: Sequence[str],
    now: datetime,
    mid_file_commit: Sequence[str] = (),
) -> HostedApproval:
    """Validate a hosted approval record against this exact run, or refuse."""

    try:
        raw = json.loads(text)
    except ValueError as error:
        raise ApplyError("the hosted approval record is not valid JSON") from error
    if not isinstance(raw, dict) or set(raw) != _RECORD_KEYS:
        raise ApplyError(
            f"the hosted approval record must have exactly the keys {sorted(_RECORD_KEYS)}"
        )
    if not all(
        isinstance(raw[key], str) and raw[key] for key in _RECORD_KEYS - {"hosts"}
    ):
        raise ApplyError("every hosted approval field must be a non-empty string")
    hosts = raw["hosts"]
    if (
        not isinstance(hosts, list)
        or not hosts
        or not all(isinstance(host, str) for host in hosts)
    ):
        raise ApplyError("the hosted approval record must list at least one host")
    if _REF.fullmatch(raw["project_ref"]) is None:
        raise ApplyError("the hosted approval project ref is not a Supabase project ref")
    direct = f"db.{raw['project_ref']}.supabase.co"
    if not all(
        _plain_host(host) == direct or _plain_host(host).endswith(".pooler.supabase.com")
        for host in hosts
    ):
        raise ApplyError(
            "the hosted approval hosts must be the project's direct host or a Supabase pooler host"
        )
    if (
        _SHA.fullmatch(raw["candidate_sha"]) is None
        or raw["candidate_sha"] != candidate_sha
    ):
        raise ApplyError(
            "the hosted approval was issued for a different candidate commit"
        )
    if raw["versions_sha256"] != versions_digest(approved, unrecorded, mid_file_commit):
        raise ApplyError(
            "the hosted approval was issued for a different list of versions"
        )
    try:
        issued = datetime.fromisoformat(raw["issued_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(raw["expires_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ApplyError(
            "the hosted approval dates must be ISO 8601 with a time zone"
        ) from error
    if issued.tzinfo is None or expires.tzinfo is None:
        raise ApplyError("the hosted approval dates must carry a time zone")
    if expires - issued > _MAX_VALIDITY or expires <= issued:
        raise ApplyError("the hosted approval must be valid for at most three days")
    if not issued <= now < expires:
        raise ApplyError("the hosted approval is not valid now")
    return HostedApproval(
        raw["id"], raw["project_ref"], tuple(_plain_host(host) for host in hosts),
        raw["database"], raw["candidate_sha"], raw["versions_sha256"], expires,
    )  # fmt: skip


def read_committed_record(root: Path, path: str, candidate_sha: str) -> str:
    """The record must be tracked, unmodified, and committed on top of the candidate."""

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        )

    parts = Path(path).parts
    if (
        Path(path).is_absolute()
        or ".." in parts
        or tuple(parts[:2]) != ("docs", "release-manifests")
    ):
        raise ApplyError(
            "the hosted approval record must be a path under docs/release-manifests/"
        )
    staged = git("ls-files", "-s", "--", path)
    if staged.returncode != 0 or not staged.stdout.strip():
        raise ApplyError("the hosted approval record is not tracked by git")
    if staged.stdout.split()[0] == "120000":
        raise ApplyError(
            "the hosted approval record must be a regular file, not a symlink"
        )
    if git("diff", "--quiet", "HEAD", "--", path).returncode != 0:
        raise ApplyError("the hosted approval record has uncommitted changes")
    if candidate_sha == git("rev-parse", "HEAD").stdout.strip() or (
        git("merge-base", "--is-ancestor", candidate_sha, "HEAD").returncode != 0
    ):
        raise ApplyError(
            "the hosted approval record is not committed on top of the candidate"
        )
    blob = git("show", f"HEAD:{path}")
    if blob.returncode != 0:
        raise ApplyError("the hosted approval record could not be read from HEAD")
    return blob.stdout


class ApplyError(RuntimeError):
    """Raised before any statement runs, or to explain why a run stopped."""


@dataclass(frozen=True)
class Step:
    version: str
    name: str
    statements: tuple[str, ...]  # exactly what the ledger row records
    segments: tuple[tuple[str, ...], ...]  # what runs, one transaction each
    record: bool
    classification: str


def check_target(
    url: str,
    allow_hosts: Sequence[str],
    allow_databases: Sequence[str],
    environ: dict[str, str] | None = None,
    hosted: HostedApproval | None = None,
) -> None:
    """Fail closed: one named host and database; a hosted one only with its approval record."""

    environment = os.environ if environ is None else environ
    for name in _REFUSED_ENVIRONMENT:
        if environment.get(name):
            raise ApplyError(f"{name} is set and could redirect the connection")
    parts = urlsplit(url)
    if "," in parts.netloc:
        raise ApplyError("a multi-host database URL is refused")
    host = _plain_host(parts.hostname or "")
    if parts.query or parts.fragment:
        raise ApplyError("the database URL must not carry a query or fragment")
    if "," in host:
        raise ApplyError("a multi-host database URL is refused")
    if hosted is None:
        if (
            not host
            or _is_hosted(host)
            or any(_is_hosted(value) for value in allow_hosts)
        ):
            raise ApplyError(
                "hosted Supabase targets are refused without an approval record"
            )
    else:
        if not _is_hosted(host):
            raise ApplyError(
                "a hosted approval record was given for a target that is not hosted"
            )
        if host not in hosted.hosts:
            raise ApplyError("target host is not named by the hosted approval record")
        if not {_plain_host(value) for value in allow_hosts} <= set(hosted.hosts):
            raise ApplyError("an allowed host is not named by the hosted approval record")
        direct = f"db.{hosted.project_ref}.supabase.co"
        if host != direct and (parts.username or "") != f"postgres.{hosted.project_ref}":
            raise ApplyError("the target does not carry the approved project ref")
        try:
            port = parts.port
        except ValueError:
            port = None
        if port != 5432:
            raise ApplyError(
                "a hosted URL must name port 5432 explicitly (a transaction pooler breaks the run lock)"
            )
        if parts.path.lstrip("/") != hosted.database:
            raise ApplyError(
                "target database is not the one the hosted approval record names"
            )
    if host not in {_plain_host(value) for value in allow_hosts}:
        raise ApplyError("target host is not on the allowed list")
    if parts.path.lstrip("/") not in set(allow_databases):
        raise ApplyError("target database is not on the allowed list")


def verify_connection(
    connection: object,
    allow_hosts: Sequence[str],
    allow_databases: Sequence[str],
    hosted: HostedApproval | None = None,
) -> None:
    """Check where the connection actually went, not where the URL said."""

    info = connection.info  # type: ignore[attr-defined]
    allowed = {_plain_host(value) for value in allow_hosts}
    host = _plain_host(info.host or "")
    hostaddr = _plain_host(info.hostaddr or "")
    if hosted is None:
        if _is_hosted(host) or _is_hosted(hostaddr):
            raise ApplyError("the connection went to a hosted Supabase host")
    elif host not in hosted.hosts:
        raise ApplyError(
            "the connection went to a host the hosted approval record does not name"
        )
    elif int(getattr(info, "port", 0) or 0) != 5432:
        raise ApplyError("the hosted connection is not on port 5432")
    if host not in allowed:
        raise ApplyError("the connection went to a host that is not on the allowed list")
    if (
        hosted is None
        and hostaddr
        and hostaddr not in allowed
        and not (host in _LOOPBACK and hostaddr in _LOOPBACK)
    ):
        raise ApplyError("the connection address is not on the allowed list")
    row = connection.execute("select current_database()").fetchone()  # type: ignore[attr-defined]
    if not row or row[0] not in set(allow_databases):
        raise ApplyError("the connected database is not on the allowed list")


def split_segments(statements: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    """Turn a file's statements into the transactions to run.

    A file wrapped in ``begin`` and ``commit`` is one transaction with the wrapper
    dropped. A ``commit`` in the middle starts a new transaction. Rollbacks and
    savepoints are refused. Comment-only statements are skipped.
    """

    segments: list[list[str]] = [[]]
    seen_statement = False
    for statement in statements:
        text = gate._strip_sql_literals_and_comments(statement).strip()
        if not text:
            continue
        keyword = text.split()[0].lower().rstrip(";")
        if keyword in _REFUSED_CONTROL:
            raise ApplyError(f"transaction control '{keyword}' is not supported")
        if keyword in _BEGIN:
            if seen_statement:
                raise ApplyError("'begin' is only supported as the first statement")
            seen_statement = True
            continue
        seen_statement = True
        if keyword in _COMMIT:
            segments.append([])
        else:
            segments[-1].append(statement)
    return tuple(tuple(segment) for segment in segments if segment)


def plan_steps(
    candidates: Sequence[gate.CandidateMigration],
    applied_versions: Sequence[str],
    approved: Sequence[str],
    unrecorded: Sequence[str] = (),
    allow_mid_file_commit: Sequence[str] = (),
) -> list[Step]:
    """Validate the approved list against the ledger and return ordered steps.

    ``approved`` versions are recorded. They must sit above the gate's
    reconciliation threshold and above everything already applied there, and
    must be the next versions in order with none skipped (a prefix is fine, so a
    run can go in batches). ``unrecorded`` versions run without a ledger row and
    must sit at or below the threshold, where the gate holds a pinned
    hand-reconciliation.
    """

    by_version = {migration.version: migration for migration in candidates}
    applied = set(applied_versions)
    threshold = gate._LEDGER_RECONCILIATION_THROUGH
    if len(set(approved)) != len(approved) or len(set(unrecorded)) != len(unrecorded):
        raise ApplyError("a version is listed more than once")
    overlap = set(approved) & set(unrecorded)
    if overlap:
        raise ApplyError(
            f"versions listed as both recorded and unrecorded: {sorted(overlap)}"
        )
    for version in (*approved, *unrecorded):
        if version not in by_version:
            raise ApplyError(f"version {version} is not a candidate migration")
        if version in applied:
            raise ApplyError(f"version {version} is already in the ledger")
    for version in approved:
        if version <= threshold:
            raise ApplyError(
                f"recorded version {version} is at or below the reconciliation threshold"
            )
    for version in unrecorded:
        if version > threshold:
            raise ApplyError(
                f"unrecorded version {version} is above the reconciliation threshold"
            )
    head = max((version for version in applied if version > threshold), default=threshold)
    for version in approved:
        if version <= head:
            raise ApplyError(
                f"recorded version {version} is not above the ledger head {head}"
            )
    above = sorted(version for version in by_version if version > head)
    if sorted(approved) != above[: len(approved)]:
        skipped = [
            version for version in above[: len(approved)] if version not in approved
        ]
        raise ApplyError(
            f"the approved list skips {skipped or 'versions'} that sit between the ledger head and "
            "its last entry; skipped versions could never be applied afterwards"
        )
    steps: list[Step] = []
    for version in sorted({*approved, *unrecorded}):
        migration = by_version[version]
        segments = split_segments(migration.statements)
        if not segments:
            raise ApplyError(
                f"version {version} has no runnable statement, so it could not be recorded"
            )
        if len(segments) > 1 and version not in allow_mid_file_commit:
            raise ApplyError(
                f"version {version} commits inside the file and would run in {len(segments)} "
                f"transactions; pass --allow-mid-file-commit {version} to accept that"
            )
        classification, _ = gate.classify_migration(migration.source)
        steps.append(
            Step(
                version,
                migration.name,
                migration.statements,
                segments,
                version in approved,
                classification,
            )
        )
    return steps


def _currency_pair_checks_present(rows: Sequence[Sequence[object]]) -> bool:
    return len(rows) == 2 and all("currency_pair" in str(row[1]) for row in rows)


# A version run without a ledger row leaves no trace, so each one needs a read-only probe of its own
# effect. The probe refuses an accidental repeat before the run and verifies the effect after it.
_EFFECT_PROBES = {
    "20260505000001": (
        "select conname, pg_catalog.pg_get_constraintdef(oid) from pg_catalog.pg_constraint"
        " where conrelid in ('public.strategies'::regclass, 'public.backtest_runs'::regclass)"
        " and conname in ('strategies_asset_class_check', 'backtest_runs_asset_class_check')"
        " order by conname",
        _currency_pair_checks_present,
    ),
}  # fmt: skip


def effect_present(connection: object, version: str) -> bool:
    """Read-only: has this unrecorded version's effect already happened?"""

    probe = _EFFECT_PROBES.get(version)
    if probe is None:
        raise ApplyError(
            f"unrecorded version {version} has no effect probe, so a repeat could not be detected"
        )
    query, present = probe
    rows = connection.execute(query).fetchall()  # type: ignore[attr-defined]
    return present(rows)


def check_unrecorded_effects(connection: object, steps: Sequence[Step]) -> None:
    """Refuse an unrecorded step whose effect already exists, before anything runs."""

    for step in steps:
        if not step.record and effect_present(connection, step.version):
            raise ApplyError(
                f"unrecorded version {step.version} already has its effect; take it out of --unrecorded"
            )


def read_ledger_versions(connection: object) -> list[str]:
    rows = connection.execute(  # type: ignore[attr-defined]
        "select version from supabase_migrations.schema_migrations order by version"
    ).fetchall()
    return [str(row[0]) for row in rows]


def check_lock_timeout(value: str) -> str:
    """A file that cannot get its locks in time fails and rolls back instead of queueing behind traffic."""

    if _LOCK_TIMEOUT.fullmatch(value) is None:
        raise ApplyError("the lock timeout must look like 500ms, 5s or 1min")
    return value


def apply_steps(
    connection: object,
    steps: Sequence[Step],
    lock_timeout: str = "5s",
    on_done: object = None,
    on_segment: object = None,
) -> list[str]:
    """Run each file's transactions in order; the ledger row joins the last one.

    Stops at the first failure. Files that already committed stay applied, and
    ``on_segment(step, number, total)`` is called after each committed transaction
    and ``on_done(step)`` after each file, so the operator knows exactly which.
    """

    check_lock_timeout(lock_timeout)
    done: list[str] = []
    for step in steps:
        for index, segment in enumerate(step.segments):
            with connection.transaction():  # type: ignore[attr-defined]
                connection.execute(  # type: ignore[attr-defined]
                    "select set_config('lock_timeout', %s, true)", (lock_timeout,)
                )
                for statement in segment:
                    connection.execute(statement)  # type: ignore[attr-defined]
                if step.record and index == len(step.segments) - 1:
                    connection.execute(  # type: ignore[attr-defined]
                        _LEDGER_INSERT, (step.version, list(step.statements), step.name)
                    )
            if callable(on_segment):
                on_segment(step, index + 1, len(step.segments))
        done.append(step.version)
        if callable(on_done):
            on_done(step)
    return done


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument(
        "--approved-file", required=True, help="JSON list of versions to apply and record"
    )
    parser.add_argument(
        "--unrecorded",
        action="append",
        default=[],
        help="version to run without a ledger row",
    )
    parser.add_argument(
        "--allow-mid-file-commit",
        action="append",
        default=[],
        help="version whose file commits inside itself, applied in several transactions",
    )
    parser.add_argument("--database-url-env", default="ARGUS_APPLY_DATABASE_URL")
    parser.add_argument("--allow-host", action="append", required=True)
    parser.add_argument("--allow-database", action="append", required=True)
    parser.add_argument(
        "--lock-timeout",
        default="5s",
        help="per-transaction lock timeout such as 500ms, 5s or 1min",
    )
    parser.add_argument(
        "--hosted-approval",
        help="repository path of the committed hosted approval record (hosted targets only)",
    )
    parser.add_argument(
        "--ssl-root-cert",
        help="CA bundle used to verify the hosted server (hosted targets only, verify-full)",
    )
    parser.add_argument(
        "--hosted-confirm",
        help="the approval record's id, repeated; required to execute on a hosted target",
    )
    parser.add_argument(
        "--execute", action="store_true", help="apply; the default only prints the plan"
    )
    args = parser.parse_args(argv)

    url = _without_surrounding_quotes(os.environ.get(args.database_url_env, ""))
    if not url:
        raise ApplyError(f"{args.database_url_env} is not set")
    lock_timeout = check_lock_timeout(args.lock_timeout)
    for version in args.unrecorded:
        if version not in _EFFECT_PROBES:
            raise ApplyError(
                f"unrecorded version {version} has no effect probe, so a repeat could not be detected"
            )
    approved = json.loads(Path(args.approved_file).read_text())
    if not isinstance(approved, list) or not all(
        isinstance(value, str) for value in approved
    ):
        raise ApplyError("the approved file must be a JSON list of version strings")
    hosted: HostedApproval | None = None
    if args.hosted_approval:
        hosted = parse_hosted_approval(
            read_committed_record(Path.cwd(), args.hosted_approval, args.candidate_sha),
            args.candidate_sha, approved, args.unrecorded, datetime.now(timezone.utc),
            args.allow_mid_file_commit,
        )  # fmt: skip
        if not args.ssl_root_cert or not Path(args.ssl_root_cert).is_file():
            raise ApplyError(
                "a hosted target needs --ssl-root-cert pointing at the CA bundle"
            )
        if args.execute and args.hosted_confirm != hosted.id:
            raise ApplyError(
                "--hosted-confirm must repeat the hosted approval record's id to execute"
            )
    check_target(url, args.allow_host, args.allow_database, hosted=hosted)
    candidates = gate.read_candidate_migrations(Path.cwd(), args.candidate_sha)

    import psycopg

    if hosted:
        connection_context = psycopg.connect(
            url, autocommit=True, sslmode="verify-full", sslrootcert=args.ssl_root_cert
        )
    else:
        connection_context = psycopg.connect(url, autocommit=True)
    with connection_context as connection:
        verify_connection(connection, args.allow_host, args.allow_database, hosted)
        locked = connection.execute(
            "select pg_try_advisory_lock(%s)", (_ADVISORY_LOCK_KEY,)
        ).fetchone()
        if not locked or not locked[0]:
            raise ApplyError("another run of this tool holds the migration lock")
        steps = plan_steps(
            candidates,
            read_ledger_versions(connection),
            approved,
            args.unrecorded,
            args.allow_mid_file_commit,
        )
        check_unrecorded_effects(connection, steps)
        for step in steps:
            label = "RECORD" if step.record else "NO-LEDGER"
            print(f"{label:9} {step.version} {step.name} [{step.classification}]")
        if not args.execute:
            print(f"dry run: {len(steps)} step(s); nothing applied")
            return 0

        def report(step: Step) -> None:
            print(f"committed {step.version} {step.name}", flush=True)

        def report_segment(step: Step, number: int, total: int) -> None:
            if total > 1:
                print(
                    f"  transaction {number}/{total} of {step.version} committed",
                    flush=True,
                )

        try:
            done = apply_steps(connection, steps, lock_timeout, report, report_segment)
        except Exception as error:
            raise ApplyError(
                f"stopped: {error}. Everything reported as committed stays applied, including "
                "the first transactions of a file that commits inside itself. Recorded files can "
                "be read from the ledger; NO-LEDGER steps leave no trace, so take every one that "
                "was reported committed out of the retry command"
            ) from error
        for step in steps:
            if not step.record and not effect_present(connection, step.version):
                raise ApplyError(
                    f"unrecorded version {step.version} ran but its effect is not visible afterwards"
                )
        print(f"applied {len(done)} step(s)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApplyError as error:
        print(f"refused: {error}", file=sys.stderr)
        raise SystemExit(2) from None
