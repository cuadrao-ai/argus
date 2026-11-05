"""Reproduce the gate's view of production's ledger from statement hashes alone (no database).

`production_ledger_hashes.py` holds, per production ledger row, the version, name, statement
count and a hash of the statements, read from production on 2026-10-07 with catalog SELECTs
(`encode(sha256(convert_to(to_json(statements)::text, 'UTF8')), 'hex')`). This script:

1. rebuilds the gate's production ledger hash and compares it with the gate's pinned
   hand-reconciliation hash, and
2. runs the gate's comparison for the candidate and writes `offline-gate-summary.json`.

    poetry run python docs/reports/evidence/cuadrao-migration-rehearsal-20261007/verify_production_ledger_pin.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from production_ledger_hashes import ROWS  # noqa: E402

from scripts.ops import production_migration_gate as gate  # noqa: E402

CANDIDATE = os.environ.get(
    "ARGUS_REHEARSAL_CANDIDATE", "93571e593e1677561e1dd38f63b6475574942e2d"
)


class Applied:
    """A ledger row known only by its hashes."""

    def __init__(self, version: str, name: str, count: int, digest: str) -> None:
        self.version, self.name, self.count, self.statements_sha256 = (
            version,
            name,
            count,
            digest,
        )
        self.statements = None

    def as_record(self) -> dict[str, object]:
        return {
            "version": self.version,
            "name": self.name,
            "statement_count": self.count,
            "statements_sha256": self.statements_sha256,
        }


def hash_match(candidate: gate.CandidateMigration, applied: Applied) -> bool:
    """The gate's equality, on hashes; a one-statement row may hold the whole file."""

    if (
        gate._statements_sha256(candidate.statements) == applied.statements_sha256
        and len(candidate.statements) == applied.count
    ):
        return True
    return (
        applied.count == 1
        and gate._statements_sha256([candidate.source]) == applied.statements_sha256
    )


def main() -> int:
    applied = [Applied(*row) for row in ROWS]
    payload = [
        row.as_record()
        for row in sorted(applied, key=lambda row: row.version)
        if row.version <= gate._LEDGER_RECONCILIATION_THROUGH
    ]
    rebuilt = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    pin_matches = rebuilt == gate._RECONCILED_PRODUCTION_LEDGER_SHA256
    print("production ledger rows:", len(applied))
    print("rebuilt ledger hash    :", rebuilt)
    print("gate's pinned hash     :", gate._RECONCILED_PRODUCTION_LEDGER_SHA256)
    print("pin matches            :", pin_matches)
    gate._migration_content_matches = hash_match  # type: ignore[assignment]
    candidates = gate.read_candidate_migrations(ROOT, CANDIDATE)
    report = gate.build_migration_report(
        candidate_sha=CANDIDATE,
        target=gate.ProductionDatabaseTarget(
            "lgdhvepyrzbnscqssgqq", "db.lgdhvepyrzbnscqssgqq.supabase.co"
        ),
        candidate_migrations=candidates,
        applied_migrations=applied,  # type: ignore[arg-type]
        reconciled_candidate_catalog_sha256=gate._RECONCILED_CANDIDATE_CATALOG_SHA256,
        reconciled_production_ledger_sha256=gate._RECONCILED_PRODUCTION_LEDGER_SHA256,
    )
    summary = {
        "candidate_sha": CANDIDATE,
        "status": report["status"],
        "stop_reasons": report["stop_reasons"],
        "advisories": report["advisories"],
        "production_ledger_pin_matches": pin_matches,
        "missing": [
            (m["version"], m["name"], m["classification"])
            for m in report["missing_migrations"]
        ],
    }
    (HERE / "offline-gate-summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(
        "gate (offline):",
        summary["status"],
        summary["stop_reasons"],
        summary["advisories"],
    )
    print(
        "missing:",
        len(summary["missing"]),
        "| content drift:",
        len(report["content_drift"]),
        "| name drift:",
        len(report["name_drift"]),
    )
    return (
        0
        if pin_matches and summary["stop_reasons"] == ["missing_candidate_migrations"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
