"""Block production promotion when candidate migrations are not applied."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Mapping, Protocol, Sequence, TypedDict, TypeVar, cast
from urllib.parse import unquote, urlsplit

MigrationClassification = Literal[
    "additive",
    "contract-replacing",
    "destructive",
]

_MIGRATION_PATH = re.compile(
    r"^supabase/migrations/(?P<version>\d{14})_(?P<name>[a-z0-9_]+)\.sql$"
)
_EXACT_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_PROJECT_REF = re.compile(r"^[a-z0-9]{20}$")
_REMOTE_BRANCH_REF = re.compile(
    r"^(?P<remote>[A-Za-z0-9][A-Za-z0-9._-]*)/"
    r"(?P<branch>[A-Za-z0-9][A-Za-z0-9._/-]*)$"
)
_RENDER_PATH = "render.yaml"
_MIGRATION_APPLY = "never"
# Production history was hand-reconciled through this pre-gate migration.
_LEDGER_RECONCILIATION_THROUGH = "20260811210000"
_RECONCILED_CANDIDATE_CATALOG_SHA256 = (
    "f05cf5738ce8b6e0ad74ce2b4b77d773387bc5421bab3a101448241b5431e2c2"
)
_RECONCILED_PRODUCTION_LEDGER_SHA256 = (
    "e352a2c003572611f0fb201305e085e3736eefbfae0d62ef29f4322a18062032"
)


class MigrationGateError(RuntimeError):
    """Raised when the gate cannot prove a safe, exact comparison."""


class DatabaseCursor(Protocol):
    def __enter__(self) -> DatabaseCursor: ...

    def __exit__(self, *args: object) -> object: ...

    def execute(self, query: str) -> object: ...

    def fetchone(self) -> Sequence[object] | None: ...

    def fetchall(self) -> Sequence[Sequence[object]]: ...


class DatabaseConnection(Protocol):
    def cursor(self) -> DatabaseCursor: ...

    def close(self) -> None: ...


class ConnectFactory(Protocol):
    def __call__(
        self,
        database_url: str,
        **kwargs: object,
    ) -> DatabaseConnection: ...


class MigrationRecord(TypedDict):
    version: str
    name: str
    path: str
    sha256: str
    statement_count: int
    statements_sha256: str


class MissingMigrationRecord(MigrationRecord):
    classification: MigrationClassification
    classification_basis: str
    live_requirement: str


class AppliedMigrationRecord(TypedDict):
    version: str
    name: str
    statement_count: int | None
    statements_sha256: str | None


@dataclass(frozen=True)
class ProductionDatabaseTarget:
    """Sanitized production database identity for release evidence."""

    project_ref: str
    database_host: str


@dataclass(frozen=True)
class MigrationGateContract:
    """Production identity derived from the candidate release contract."""

    production_supabase_project_ref: str


@dataclass(frozen=True)
class AppliedMigration:
    """One migration row read from production's Supabase ledger."""

    version: str
    name: str
    statements: tuple[str, ...] | None

    @property
    def statements_sha256(self) -> str | None:
        if self.statements is None:
            return None
        return _statements_sha256(self.statements)

    def as_record(self) -> AppliedMigrationRecord:
        return {
            "version": self.version,
            "name": self.name,
            "statement_count": (
                len(self.statements) if self.statements is not None else None
            ),
            "statements_sha256": self.statements_sha256,
        }


@dataclass(frozen=True)
class CandidateMigration:
    """One migration read from the exact candidate Git tree."""

    version: str
    name: str
    path: str
    sha256: str
    source: str
    statements: tuple[str, ...]

    @classmethod
    def from_source(cls, path: str, source: str) -> CandidateMigration:
        match = _MIGRATION_PATH.fullmatch(path)
        if match is None:
            raise ValueError(f"invalid migration path: {path}")
        return cls(
            version=match.group("version"),
            name=match.group("name"),
            path=path,
            sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            source=source,
            statements=_split_supabase_statements(source),
        )

    @property
    def statements_sha256(self) -> str:
        return _statements_sha256(self.statements)

    def as_record(self) -> MigrationRecord:
        return {
            "version": self.version,
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "statement_count": len(self.statements),
            "statements_sha256": self.statements_sha256,
        }

    def as_missing_record(self) -> MissingMigrationRecord:
        classification, requirement = classify_migration(self.source)
        return {
            **self.as_record(),
            "classification": classification,
            "classification_basis": "conservative_top_level_sql",
            "live_requirement": requirement,
        }


MigrationT = TypeVar("MigrationT", CandidateMigration, AppliedMigration)


def load_gate_contract(
    repo_root: Path,
    candidate_sha: str,
) -> MigrationGateContract:
    """Read the target contract from the exact candidate commit."""

    _verify_candidate_sha(repo_root, candidate_sha)
    raw = _read_git_file(repo_root, candidate_sha, _RENDER_PATH)
    try:
        render_source = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MigrationGateError(f"candidate {_RENDER_PATH} must be valid UTF-8") from exc
    api_block = re.search(
        r"(?ms)^  - type:.*?^    name: argus-api\s*$.*?(?=^  - type:|\Z)",
        render_source,
    )
    if api_block is None:
        raise MigrationGateError("candidate render.yaml does not declare argus-api")
    supabase_url = re.search(
        r"(?m)^      - key: SUPABASE_URL\s*$\n" r"^        value:\s*([^\s#]+)\s*$",
        api_block.group(0),
    )
    if supabase_url is None:
        raise MigrationGateError(
            "candidate argus-api does not declare a literal SUPABASE_URL"
        )
    project_ref = _project_ref_from_supabase_url(
        supabase_url.group(1).strip("'\""),
    )
    return MigrationGateContract(production_supabase_project_ref=project_ref)


def read_candidate_migrations(
    repo_root: Path,
    candidate_sha: str,
) -> list[CandidateMigration]:
    """Enumerate migration sources from an exact candidate Git tree."""

    _verify_candidate_sha(repo_root, candidate_sha)
    listing = _run_git(
        repo_root,
        "ls-tree",
        "-r",
        "--name-only",
        candidate_sha,
        "--",
        "supabase/migrations",
    )
    try:
        paths = listing.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise MigrationGateError("candidate migration paths are not UTF-8") from exc
    migrations: list[CandidateMigration] = []
    for path in paths:
        if not path.endswith(".sql"):
            continue
        source_bytes = _read_git_file(repo_root, candidate_sha, path)
        try:
            source = source_bytes.decode("utf-8")
            migration = CandidateMigration.from_source(path, source)
        except (UnicodeDecodeError, ValueError) as exc:
            raise MigrationGateError(f"candidate migration is malformed: {path}") from exc
        migrations.append(migration)
    migrations.sort(key=lambda migration: (migration.version, migration.path))
    if not migrations:
        raise MigrationGateError("candidate contains no Supabase migrations")
    _unique_by_version(migrations, source="candidate")
    return migrations


def resolve_production_target(
    database_url: str,
    *,
    expected_project_ref: str,
) -> ProductionDatabaseTarget:
    """Verify a direct or pooler URL without retaining its credentials."""

    if not _PROJECT_REF.fullmatch(expected_project_ref):
        raise MigrationGateError("checked-in production project ref is invalid")
    try:
        parsed = urlsplit(database_url)
        host = (parsed.hostname or "").lower()
        _ = parsed.port
    except ValueError as exc:
        raise MigrationGateError("production database URL is malformed") from exc
    if parsed.scheme.lower() not in {"postgres", "postgresql"} or not host:
        raise MigrationGateError(
            "production database URL must be an absolute Postgres URL"
        )
    if parsed.query or parsed.fragment:
        raise MigrationGateError(
            "production database URL must not contain query parameters or fragments"
        )
    username = unquote(parsed.username or "")
    direct_host = f"db.{expected_project_ref}.supabase.co"
    direct_match = host == direct_host
    pooler_match = (
        host.endswith(".pooler.supabase.com")
        and username == f"postgres.{expected_project_ref}"
    )
    if not direct_match and not pooler_match:
        raise MigrationGateError(
            "production database target does not match the checked-in "
            "Supabase project ref"
        )
    return ProductionDatabaseTarget(
        project_ref=expected_project_ref,
        database_host=host,
    )


def read_applied_migrations(
    database_url: str,
    *,
    ssl_root_cert: str,
    connect_factory: ConnectFactory | None = None,
) -> list[AppliedMigration]:
    """Read production's migration ledger in one verified read-only transaction."""

    if connect_factory is None:
        from psycopg import connect

        connect_factory = cast(ConnectFactory, connect)
    connection: DatabaseConnection | None = None
    try:
        connection = connect_factory(
            database_url,
            application_name="argus-production-migration-gate",
            autocommit=True,
            connect_timeout=10,
            gssencmode="disable",
            sslmode="verify-full",
            sslrootcert=ssl_root_cert,
        )
        with connection.cursor() as cursor:
            _begin_read_only_transaction(cursor)
            try:
                cursor.execute(
                    "select version, coalesce(name, ''), statements "
                    "from supabase_migrations.schema_migrations order by version"
                )
                rows = cursor.fetchall()
            finally:
                cursor.execute("rollback")
        if any(len(row) < 3 for row in rows):
            raise MigrationGateError(
                "production migration ledger returned a malformed row"
            )
        applied = [
            AppliedMigration(
                version=str(row[0]),
                name=str(row[1]),
                statements=_read_applied_statements(row[2]),
            )
            for row in rows
        ]
        _unique_by_version(applied, source="production")
    except MigrationGateError:
        raise
    except Exception as exc:
        raise MigrationGateError("production migration ledger read failed") from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
    return applied


def _begin_read_only_transaction(cursor: DatabaseCursor) -> None:
    """Open and verify the transaction that contains the production read."""

    cursor.execute("begin transaction read only")
    try:
        cursor.execute("show transaction_read_only")
        read_only = cursor.fetchone()
        if read_only is None or str(read_only[0]).lower() != "on":
            raise MigrationGateError(
                "production database transaction did not enter read-only mode"
            )
    except Exception:
        cursor.execute("rollback")
        raise


def classify_migration(
    source: str,
) -> tuple[MigrationClassification, str]:
    """Classify top-level SQL conservatively for live-database review."""

    statements = _top_level_statements(source)
    if any(_is_destructive(statement) for statement in statements):
        return (
            "destructive",
            "maintenance_backup_and_founder_approval_required",
        )
    if statements and all(_is_additive(statement) for statement in statements):
        return "additive", "human_review_and_live_readback"
    return (
        "contract-replacing",
        "expand_contract_or_maintenance_required",
    )


def build_migration_report(
    *,
    candidate_sha: str,
    target: ProductionDatabaseTarget,
    candidate_migrations: Sequence[CandidateMigration],
    applied_migrations: Sequence[AppliedMigration],
    reconciled_candidate_catalog_sha256: str | None = None,
    reconciled_production_ledger_sha256: str | None = None,
) -> dict[str, object]:
    """Build a fail-closed comparison report for release evidence."""

    candidate_by_version = _unique_by_version(
        candidate_migrations,
        source="candidate",
    )
    applied_by_version = _unique_by_version(
        applied_migrations,
        source="production",
    )
    candidate_catalog_sha256 = _candidate_catalog_sha256(candidate_migrations)
    candidate_catalog_matches_reconciliation = (
        reconciled_candidate_catalog_sha256 is None
        or candidate_catalog_sha256 == reconciled_candidate_catalog_sha256
    )
    production_ledger_sha256 = _production_ledger_sha256(applied_migrations)
    production_ledger_matches_reconciliation = (
        reconciled_production_ledger_sha256 is None
        or production_ledger_sha256 == reconciled_production_ledger_sha256
    )
    historical_mappings, mapped_candidate_versions, mapped_applied_versions = (
        _historical_migration_mappings(candidate_by_version, applied_by_version)
    )
    missing = [
        migration.as_missing_record()
        for version, migration in candidate_by_version.items()
        if version > _LEDGER_RECONCILIATION_THROUGH and version not in applied_by_version
    ]
    historical_candidate_without_ledger_identity = [
        migration.as_record()
        for version, migration in candidate_by_version.items()
        if version <= _LEDGER_RECONCILIATION_THROUGH
        and version not in applied_by_version
        and version not in mapped_candidate_versions
    ]
    unexpected = [
        migration.as_record()
        for version, migration in applied_by_version.items()
        if version not in candidate_by_version and version not in mapped_applied_versions
    ]
    name_drift = [
        {
            "version": version,
            "candidate_name": candidate.name,
            "applied_name": applied_by_version[version].name,
        }
        for version, candidate in candidate_by_version.items()
        if version > _LEDGER_RECONCILIATION_THROUGH
        if version in applied_by_version
        and applied_by_version[version].name != candidate.name
    ]
    content_drift = [
        _content_drift_record(candidate, applied_by_version[version])
        for version, candidate in candidate_by_version.items()
        if version > _LEDGER_RECONCILIATION_THROUGH
        if version in applied_by_version
        and not _migration_content_matches(candidate, applied_by_version[version])
    ]
    historical_name_drift = [
        {
            "version": version,
            "candidate_name": candidate.name,
            "applied_name": applied_by_version[version].name,
        }
        for version, candidate in candidate_by_version.items()
        if version <= _LEDGER_RECONCILIATION_THROUGH
        if version in applied_by_version
        and applied_by_version[version].name != candidate.name
    ]
    historical_content_drift = [
        _content_drift_record(candidate, applied_by_version[version])
        for version, candidate in candidate_by_version.items()
        if version <= _LEDGER_RECONCILIATION_THROUGH
        if version in applied_by_version
        and not _migration_content_matches(candidate, applied_by_version[version])
    ]
    historical_applied_without_candidate_identity = [
        migration
        for migration in unexpected
        if str(migration["version"]) <= _LEDGER_RECONCILIATION_THROUGH
    ]
    strict_unexpected = [
        migration
        for migration in unexpected
        if str(migration["version"]) > _LEDGER_RECONCILIATION_THROUGH
    ]
    candidate_rows_through_reconciliation = sum(
        version <= _LEDGER_RECONCILIATION_THROUGH for version in candidate_by_version
    )
    applied_rows_through_reconciliation = sum(
        version <= _LEDGER_RECONCILIATION_THROUGH for version in applied_by_version
    )
    applied_row_surplus = max(
        applied_rows_through_reconciliation - candidate_rows_through_reconciliation,
        0,
    )
    has_historical_variance = bool(
        not candidate_catalog_matches_reconciliation
        or not production_ledger_matches_reconciliation
        or historical_mappings
        or historical_candidate_without_ledger_identity
        or historical_applied_without_candidate_identity
        or historical_name_drift
        or historical_content_drift
        or applied_row_surplus
    )
    stop_reasons: list[str] = []
    advisories: list[str] = []
    if not candidate_catalog_matches_reconciliation:
        stop_reasons.append("historical_candidate_catalog_drift")
    if not production_ledger_matches_reconciliation:
        stop_reasons.append("historical_production_ledger_drift")
    if missing:
        stop_reasons.append("missing_candidate_migrations")
    if has_historical_variance:
        advisories.append("historical_migration_ledger_variance")
    if strict_unexpected:
        stop_reasons.append("unexpected_applied_migrations")
    if name_drift:
        stop_reasons.append("applied_migration_name_drift")
    if content_drift:
        stop_reasons.append("applied_migration_content_drift")
    candidate_coverage_verified = not stop_reasons
    return {
        "schema_version": "argus.production_migration_gate.v1",
        "status": "pass" if candidate_coverage_verified else "blocked",
        "candidate_sha": candidate_sha,
        "production_target": {
            "project_ref": target.project_ref,
            "database_host": target.database_host,
        },
        "candidate_migrations": [
            migration.as_record() for migration in candidate_migrations
        ],
        "applied_migrations": [migration.as_record() for migration in applied_migrations],
        "missing_migrations": missing,
        "unexpected_applied_migrations": unexpected,
        "name_drift": name_drift,
        "content_drift": content_drift,
        "historical_ledger_variance": {
            "reconciled_through_version": _LEDGER_RECONCILIATION_THROUGH,
            "candidate_catalog_sha256": candidate_catalog_sha256,
            "candidate_catalog_matches_reconciliation": (
                candidate_catalog_matches_reconciliation
            ),
            "production_ledger_sha256": production_ledger_sha256,
            "production_ledger_matches_reconciliation": (
                production_ledger_matches_reconciliation
            ),
            "version_mappings": historical_mappings,
            "candidate_without_ledger_identity": (
                historical_candidate_without_ledger_identity
            ),
            "applied_without_candidate_identity": (
                historical_applied_without_candidate_identity
            ),
            "name_drift": historical_name_drift,
            "content_drift": historical_content_drift,
            "applied_row_surplus": applied_row_surplus,
        },
        "stop_reasons": stop_reasons,
        "advisories": advisories,
        "latest_candidate_version": max(candidate_by_version, default=None),
        "latest_applied_version": max(applied_by_version, default=None),
        "human_approval": (
            "not_required_no_gap"
            if candidate_coverage_verified
            else (
                "required_before_out_of_band_apply"
                if missing
                else "required_for_migration_drift_reconciliation"
            )
        ),
        "apply_result": "not_performed_by_gate",
        "readback": (
            (
                "candidate_migration_coverage_verified_with_" "historical_ledger_variance"
                if has_historical_variance
                else "migration_ledger_parity_verified"
            )
            if candidate_coverage_verified
            else "blocked_pending_schema_parity"
        ),
        "counts": {
            "candidate": len(candidate_migrations),
            "applied": len(applied_migrations),
            "missing": len(missing),
            "unexpected": len(unexpected),
            "name_drift": len(name_drift),
            "content_drift": len(content_drift),
            "historical_candidate_without_ledger_identity": len(
                historical_candidate_without_ledger_identity
            ),
            "historical_applied_without_candidate_identity": len(
                historical_applied_without_candidate_identity
            ),
            "applied_row_surplus": applied_row_surplus,
        },
        "database_access": "read_only",
        "database_transport": "tls_verify_full",
        "migration_apply": _MIGRATION_APPLY,
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
    connect_factory: ConnectFactory | None = None,
    reconciled_candidate_catalog_sha256: str | None = (
        _RECONCILED_CANDIDATE_CATALOG_SHA256
    ),
    reconciled_production_ledger_sha256: str | None = (
        _RECONCILED_PRODUCTION_LEDGER_SHA256
    ),
) -> int:
    """Run the production migration gate and write its durable JSON report."""

    parser = argparse.ArgumentParser(
        description=(
            "Compare an exact candidate's migrations with production's "
            "read-only Supabase ledger. This command never applies migrations."
        )
    )
    parser.add_argument(
        "--candidate-sha",
        required=True,
        help="Exact 40-character candidate commit SHA.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path for the JSON release-evidence report.",
    )
    parser.add_argument(
        "--verify-landed-ref",
        metavar="REMOTE/BRANCH",
        help=(
            "Fetch and require this remote branch to resolve to the candidate "
            "before reading production. Use for the final post-landing gate."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = repo_root or Path(__file__).resolve().parents[2]
    source = os.environ if environ is None else environ

    try:
        _verify_checkout_head(root, args.candidate_sha)
        landed_sha = (
            verify_landed_ref(root, args.candidate_sha, args.verify_landed_ref)
            if args.verify_landed_ref
            else None
        )
        contract = load_gate_contract(root, args.candidate_sha)
        candidate_migrations = read_candidate_migrations(
            root,
            args.candidate_sha,
        )
        database_url = str(source.get("ARGUS_PRODUCTION_DATABASE_URL") or "").strip()
        if not database_url:
            raise MigrationGateError(
                "ARGUS_PRODUCTION_DATABASE_URL must be set explicitly; "
                "dotenv discovery is disabled"
            )
        target = resolve_production_target(
            database_url,
            expected_project_ref=contract.production_supabase_project_ref,
        )
        ssl_root_cert = _resolve_ssl_root_cert(
            str(source.get("ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT") or "").strip()
        )
        applied_migrations = read_applied_migrations(
            database_url,
            ssl_root_cert=ssl_root_cert,
            connect_factory=connect_factory,
        )
        report = build_migration_report(
            candidate_sha=args.candidate_sha,
            target=target,
            candidate_migrations=candidate_migrations,
            applied_migrations=applied_migrations,
            reconciled_candidate_catalog_sha256=(reconciled_candidate_catalog_sha256),
            reconciled_production_ledger_sha256=(reconciled_production_ledger_sha256),
        )
        report["landing_verification"] = (
            {
                "status": "verified",
                "remote_ref": args.verify_landed_ref,
                "resolved_sha": landed_sha,
            }
            if landed_sha is not None
            else {"status": "not_requested_pre_landing"}
        )
        exit_code = 0 if report["status"] == "pass" else 1
    except MigrationGateError as exc:
        report = {
            "schema_version": "argus.production_migration_gate.v1",
            "status": "blocked",
            "candidate_sha": args.candidate_sha,
            "database_access": "read_only",
            "database_transport": "tls_verify_full",
            "migration_apply": _MIGRATION_APPLY,
            "stop_reasons": ["gate_execution_failed"],
            "error": str(exc),
        }
        exit_code = 2

    report["checked_at"] = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    except OSError:
        report["status"] = "blocked"
        report["stop_reasons"] = ["evidence_write_failed"]
        report["error"] = "migration gate evidence could not be written"
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        exit_code = 2
    sys.stdout.write(rendered)
    return exit_code


def _unique_by_version(
    migrations: Sequence[MigrationT],
    *,
    source: str,
) -> dict[str, MigrationT]:
    by_version: dict[str, MigrationT] = {}
    for migration in migrations:
        if migration.version in by_version:
            raise MigrationGateError(
                f"duplicate {source} migration version: {migration.version}"
            )
        by_version[migration.version] = migration
    return by_version


def _read_applied_statements(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(statement, str) for statement in value
    ):
        raise MigrationGateError(
            "production migration ledger returned malformed statements"
        )
    return tuple(value)


def _resolve_ssl_root_cert(value: str) -> str:
    path = Path(value)
    try:
        if not value or not path.is_absolute():
            raise OSError
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError
        with resolved.open("rb") as certificate:
            if not certificate.read(1):
                raise OSError
    except OSError as exc:
        raise MigrationGateError(
            "ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT must be an absolute " "readable file"
        ) from exc
    return str(resolved)


def _candidate_catalog_sha256(
    candidate_migrations: Sequence[CandidateMigration],
) -> str:
    payload = [
        {
            "version": migration.version,
            "name": migration.name,
            "path": migration.path,
            "sha256": migration.sha256,
        }
        for migration in sorted(
            candidate_migrations,
            key=lambda migration: migration.version,
        )
        if migration.version <= _LEDGER_RECONCILIATION_THROUGH
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _production_ledger_sha256(
    applied_migrations: Sequence[AppliedMigration],
) -> str:
    payload = [
        migration.as_record()
        for migration in sorted(
            applied_migrations,
            key=lambda migration: migration.version,
        )
        if migration.version <= _LEDGER_RECONCILIATION_THROUGH
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _historical_migration_mappings(
    candidate_by_version: Mapping[str, CandidateMigration],
    applied_by_version: Mapping[str, AppliedMigration],
) -> tuple[list[dict[str, object]], set[str], set[str]]:
    mappings: list[dict[str, object]] = []
    mapped_candidate_versions: set[str] = set()
    mapped_applied_versions: set[str] = set()
    available_applied_versions = {
        version
        for version in applied_by_version
        if version <= _LEDGER_RECONCILIATION_THROUGH
        and version not in candidate_by_version
    }
    for candidate_version, candidate in candidate_by_version.items():
        if (
            candidate_version > _LEDGER_RECONCILIATION_THROUGH
            or candidate_version in applied_by_version
        ):
            continue
        accepted_names = {
            candidate.name,
            f"{candidate.version}_{candidate.name}",
        }
        matches = [
            version
            for version in available_applied_versions
            if applied_by_version[version].name in accepted_names
        ]
        if len(matches) != 1:
            continue
        applied_version = matches[0]
        applied = applied_by_version[applied_version]
        mappings.append(
            {
                "candidate_version": candidate.version,
                "candidate_name": candidate.name,
                "applied_version": applied.version,
                "applied_name": applied.name,
                "content_match": _migration_content_matches(candidate, applied),
            }
        )
        mapped_candidate_versions.add(candidate_version)
        mapped_applied_versions.add(applied_version)
        available_applied_versions.remove(applied_version)
    return mappings, mapped_candidate_versions, mapped_applied_versions


def _migration_content_matches(
    candidate: CandidateMigration,
    applied: AppliedMigration,
) -> bool:
    if applied.statements is None:
        return False
    if candidate.statements == applied.statements:
        return True
    return (
        len(applied.statements) == 1
        and candidate.source.strip() == applied.statements[0].strip()
    )


def _content_drift_record(
    candidate: CandidateMigration,
    applied: AppliedMigration,
) -> dict[str, object]:
    return {
        "version": candidate.version,
        "reason": (
            "missing_applied_statements"
            if applied.statements is None
            else "statements_mismatch"
        ),
        "candidate_statement_count": len(candidate.statements),
        "candidate_statements_sha256": candidate.statements_sha256,
        "applied_statement_count": (
            len(applied.statements) if applied.statements is not None else None
        ),
        "applied_statements_sha256": applied.statements_sha256,
    }


def _statements_sha256(statements: Sequence[str]) -> str:
    canonical = json.dumps(
        list(statements),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _split_supabase_statements(source: str) -> tuple[str, ...]:
    """Mirror Supabase CLI SplitAndTrim boundaries for ledger comparison."""

    statements: list[str] = []
    start = 0
    index = 0
    atomic_delimiters: list[str] = []
    while index < len(source):
        if source.startswith("--", index):
            newline = source.find("\n", index + 2)
            if newline == -1:
                index = len(source)
                break
            index = newline + 1
            continue
        if source.startswith("/*", index):
            index = _skip_block_comment(source, index)
            continue
        character = source[index]
        if character in {"'", '"'}:
            index = _skip_quoted(source, index, character)
            continue
        dollar_tag = _supabase_dollar_tag_at(source, index)
        if dollar_tag is not None:
            end = source.find(dollar_tag, index + len(dollar_tag))
            index = len(source) if end == -1 else end + len(dollar_tag)
            continue
        if character == "\\":
            index = min(index + 2, len(source))
            continue
        if character == "(":
            atomic_delimiters.append(")")
            index += 1
            continue
        if _ends_begin_atomic(source, index):
            atomic_delimiters.append("end")
            index += 1
            continue
        if atomic_delimiters:
            delimiter = atomic_delimiters[-1]
            if delimiter == ")" and character == ")":
                atomic_delimiters.pop()
            elif (
                delimiter == "end"
                and source[max(0, index - 2) : index + 1].lower() == "end"
            ):
                atomic_delimiters.pop()
            index += 1
            continue
        if character == ";":
            statement = source[start : index + 1].rstrip(";").strip()
            if statement:
                statements.append(statement)
            start = index + 1
        index += 1
    final_statement = source[start:].rstrip(";").strip()
    if final_statement:
        statements.append(final_statement)
    return tuple(statements)


def _supabase_dollar_tag_at(source: str, index: int) -> str | None:
    if source[index] != "$":
        return None
    end = index + 1
    while end < len(source) and _is_supabase_tag_character(source[end]):
        end += 1
    if end < len(source) and source[end] == "$":
        return source[index : end + 1]
    return None


def _is_supabase_tag_character(character: str) -> bool:
    category = unicodedata.category(character)
    return character == "_" or category.startswith("L") or category == "Nd"


def _ends_begin_atomic(source: str, index: int) -> bool:
    if source[index] not in {"c", "C"}:
        return False
    prefix = source[: index + 1]
    match = re.search(r"(?i)(?<![\w$])begin\s+atomic$", prefix)
    return match is not None


def _top_level_statements(source: str) -> list[str]:
    sanitized = _strip_sql_literals_and_comments(source)
    return [
        " ".join(statement.lower().split())
        for statement in sanitized.split(";")
        if statement.strip()
    ]


def _strip_sql_literals_and_comments(source: str) -> str:
    output: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        if source.startswith("--", index):
            newline = source.find("\n", index + 2)
            if newline == -1:
                break
            output.append("\n")
            index = newline + 1
            continue
        if source.startswith("/*", index):
            index = _skip_block_comment(source, index)
            output.append(" ")
            continue
        if source[index] == "'":
            index = _skip_quoted(source, index, "'")
            output.append(" ")
            continue
        if source[index] == '"':
            index = _skip_quoted(source, index, '"')
            output.append(" quoted_identifier ")
            continue
        dollar_tag = _dollar_tag_at(source, index)
        if dollar_tag is not None:
            end = source.find(dollar_tag, index + len(dollar_tag))
            index = length if end == -1 else end + len(dollar_tag)
            output.append(" ")
            continue
        output.append(source[index])
        index += 1
    return "".join(output)


def _skip_block_comment(source: str, start: int) -> int:
    depth = 1
    index = start + 2
    while index < len(source) and depth:
        if source.startswith("/*", index):
            depth += 1
            index += 2
        elif source.startswith("*/", index):
            depth -= 1
            index += 2
        else:
            index += 1
    return index


def _skip_quoted(source: str, start: int, quote: str) -> int:
    index = start + 1
    while index < len(source):
        if source[index] != quote:
            index += 1
            continue
        if index + 1 < len(source) and source[index + 1] == quote:
            index += 2
            continue
        return index + 1
    return index


def _dollar_tag_at(source: str, index: int) -> str | None:
    if source[index] != "$":
        return None
    match = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", source[index:])
    return match.group(0) if match else None


def _is_destructive(statement: str) -> bool:
    return bool(
        statement == "do"
        or statement.startswith("do ")
        or re.search(r"\b(?:truncate|delete\s+from)\b", statement)
        or re.search(r"\bdrop\b", statement)
    )


def _is_additive(statement: str) -> bool:
    if statement.startswith("create or replace "):
        return False
    additive_prefixes = (
        "create table ",
        "create table if not exists ",
        "create schema ",
        "create schema if not exists ",
        "create type ",
        "create sequence ",
        "create index ",
        "create index if not exists ",
        "create unique index ",
        "create unique index if not exists ",
        "create function ",
        "create policy ",
        "comment on ",
        "grant ",
    )
    if statement.startswith(additive_prefixes):
        return True
    if statement.startswith("alter table "):
        return _alter_table_actions_are_additive(statement)
    return False


def _alter_table_actions_are_additive(statement: str) -> bool:
    match = re.fullmatch(
        r"alter table (?:if exists )?(?:only )?\S+(?: \*)? (?P<actions>.+)",
        statement,
    )
    if match is None:
        return False
    actions = _split_top_level_commas(match.group("actions"))
    return bool(actions) and all(action.startswith("add ") for action in actions)


def _split_top_level_commas(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(value):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return []
        elif character == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    if depth != 0:
        return []
    parts.append(value[start:].strip())
    return parts if all(parts) else []


def _verify_candidate_sha(repo_root: Path, candidate_sha: str) -> None:
    if not _EXACT_COMMIT_SHA.fullmatch(candidate_sha):
        raise MigrationGateError(
            "candidate SHA must be an exact 40-character lowercase commit SHA"
        )
    resolved = (
        _run_git(
            repo_root,
            "rev-parse",
            "--verify",
            f"{candidate_sha}^{{commit}}",
        )
        .decode("ascii", errors="strict")
        .strip()
    )
    if resolved != candidate_sha:
        raise MigrationGateError("candidate SHA did not resolve exactly")


def _verify_checkout_head(repo_root: Path, candidate_sha: str) -> None:
    _verify_candidate_sha(repo_root, candidate_sha)
    head = _run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    if head != candidate_sha:
        raise MigrationGateError("checkout HEAD does not match the candidate SHA")
    tracked_status = _run_git(
        repo_root,
        "status",
        "--porcelain",
        "--untracked-files=no",
    )
    if tracked_status.strip():
        raise MigrationGateError("checkout has tracked changes outside the candidate")


def verify_landed_ref(
    repo_root: Path,
    candidate_sha: str,
    remote_ref: str,
) -> str:
    """Fetch and prove a remote branch resolves to the gated candidate."""

    _verify_candidate_sha(repo_root, candidate_sha)
    match = _REMOTE_BRANCH_REF.fullmatch(remote_ref)
    if (
        match is None
        or ".." in remote_ref
        or "@{" in remote_ref
        or "//" in remote_ref
        or remote_ref.endswith((".", "/"))
    ):
        raise MigrationGateError("landed ref must use a safe REMOTE/BRANCH name")
    remote = match.group("remote")
    branch = match.group("branch")
    tracking_ref = f"refs/remotes/{remote}/{branch}"
    _run_git(
        repo_root,
        "fetch",
        "--quiet",
        "--no-tags",
        remote,
        f"+refs/heads/{branch}:{tracking_ref}",
    )
    resolved = (
        _run_git(
            repo_root,
            "rev-parse",
            "--verify",
            f"{tracking_ref}^{{commit}}",
        )
        .decode("ascii", errors="strict")
        .strip()
    )
    if resolved != candidate_sha:
        raise MigrationGateError("landed ref does not match the candidate SHA")
    return resolved


def _read_git_file(repo_root: Path, candidate_sha: str, path: str) -> bytes:
    return _run_git(repo_root, "show", f"{candidate_sha}:{path}")


def _project_ref_from_supabase_url(supabase_url: str) -> str:
    try:
        parsed = urlsplit(supabase_url)
        host = (parsed.hostname or "").lower()
        _ = parsed.port
    except ValueError as exc:
        raise MigrationGateError("candidate argus-api SUPABASE_URL is malformed") from exc
    host_match = re.fullmatch(r"([a-z0-9]{20})\.supabase\.co", host)
    if parsed.scheme.lower() != "https" or host_match is None:
        raise MigrationGateError(
            "candidate argus-api SUPABASE_URL must identify one Supabase project"
        )
    return host_match.group(1)


def _run_git(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise MigrationGateError(f"Git candidate read failed: git {args[0]}")
    return result.stdout


if __name__ == "__main__":
    raise SystemExit(main())
