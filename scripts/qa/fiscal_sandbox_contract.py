"""Offline manifest verification. Reads protected fixtures; never contacts or allocates."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

from argus.domain.business.fiscal_sandbox.contracts import Case

_DYNAMIC = (
    ("idDoc", "encf"),
    ("sender", "rnc"),
    ("sender", "companyName"),
    ("sender", "address"),
    ("sender", "stampDate"),
)


def _masked(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    result = deepcopy(payload)
    keys = _DYNAMIC + (
        (("idDoc", "sequenceDueDate"), ("buyer", "rnc"), ("buyer", "companyName"))
        if kind == "E31"
        else ()
    )
    for parent, leaf in keys:
        if parent not in result or leaf not in result[parent]:
            raise ValueError("fixture_dynamic_field_missing")
        result[parent][leaf] = "<operator-selected>"
    return result


def verify(
    manifest: Path, expected_sha256: str, business_id: UUID, templates: dict[str, Path]
) -> int:
    raw = manifest.read_bytes()
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("manifest_digest_mismatch")
    cases = [Case.model_validate(value) for value in json.loads(raw)]
    if not 1 <= len(cases) <= 2 or len({c.case_id for c in cases}) != len(cases):
        raise ValueError("manifest_case_count")
    if len({(c.account_key, c.company_id, c.issuer) for c in cases}) != 1:
        raise ValueError("manifest_company_alias")
    for case in cases:
        if case.business_id != business_id or case.kind not in templates:
            raise ValueError("manifest_scope")
        source = templates[case.kind].read_bytes()
        if (
            len(source) > 65536
            or hashlib.sha256(source).hexdigest() != case.fixture_digest
        ):
            raise ValueError("fixture_digest_mismatch")
        if _masked(json.loads(source), case.kind) != _masked(case.payload, case.kind):
            raise ValueError("fixture_fixed_fields_changed")
    return len(cases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--business-id", type=UUID, required=True)
    parser.add_argument("--e31-template", type=Path)
    parser.add_argument("--e32-template", type=Path)
    args = parser.parse_args()
    templates = {
        kind: path
        for kind, path in (("E31", args.e31_template), ("E32", args.e32_template))
        if path
    }
    try:
        count = verify(args.manifest, args.manifest_sha256, args.business_id, templates)
    except Exception:
        # File contents, paths and validation errors can contain private identity.
        parser.exit(1, "Fiscal manifest verification failed. No contact performed.\n")
    parser.exit(
        0, f"Validated {count} synthetic case(s) offline. Activation remains held.\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
