"""Run the production gate's comparison against a reset database that applied the baseline.

    poetry run python docs/reports/evidence/1890-baseline/gate_on_reset.py <database-url>

The database stands in for production after #1789: emptied, the ledger table
recreated, then both files in supabase/migrations/ applied from the committed tree
by the apply tool. The ledger is read the way the gate reads it, only without TLS,
which a local database has no certificate for. With the gate's pinned fingerprints
the report must be `pass` with no advisory, and one ledger row the tree does not
have must still block it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from psycopg import connect

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts.ops import production_migration_gate as gate  # noqa: E402


def local_connect(database_url: str, **kwargs: object) -> object:
    return connect(database_url, **{k: v for k, v in kwargs.items() if not k.startswith("ssl")})


def report(sha: str, candidates: list, applied: list) -> dict:
    return gate.build_migration_report(
        candidate_sha=sha,
        target=gate.ProductionDatabaseTarget(project_ref="local-reset", database_host="127.0.0.1"),
        candidate_migrations=candidates,
        applied_migrations=applied,
        reconciled_candidate_catalog_sha256=gate._RECONCILED_CANDIDATE_CATALOG_SHA256,
        reconciled_production_ledger_sha256s=gate._RECONCILED_PRODUCTION_LEDGER_SHA256S,
    )


def main() -> None:
    sha = gate._run_git(ROOT, "rev-parse", "HEAD").decode().strip()
    candidates = gate.read_candidate_migrations(ROOT, sha)
    applied = gate.read_applied_migrations(sys.argv[1], ssl_root_cert="", connect_factory=local_connect)
    reset = report(sha, candidates, applied)
    print(f"reset: {reset['status']} stop={reset['stop_reasons']} advisories={reset['advisories']}")
    extra = gate.AppliedMigration("20261110170000", "not_in_the_tree", ("select 1",))
    drifted = report(sha, candidates, [*applied, extra])
    print(f"reset + one extra ledger row: {drifted['status']} stop={drifted['stop_reasons']}")
    ok = (
        (reset["status"], reset["stop_reasons"], reset["advisories"]) == ("pass", [], [])
        and reset["readback"] == "migration_ledger_parity_verified"
        and (drifted["status"], drifted["stop_reasons"]) == ("blocked", ["unexpected_applied_migrations"])
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
