"""Compare repository migration identities with the read-only staging snapshot."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
MIGRATIONS = ROOT / "supabase" / "migrations"
APPLIED_BODIES = {
    "20261016065035_whatsapp_reply_grouping.sql": "420fbe0db147f6f7b773d65f1fb95b37",
    "20261016090033_document_source_prefixes.sql": "9ba6f3044b9d4cc62703d8e02053f0fd",
    "20261016142927_business_name_prompt.sql": "426edecbf1aceb65e5a2b3607006ae46",
}


def main() -> None:
    paths = list(MIGRATIONS.glob("*.sql"))
    recorded = json.loads((EVIDENCE / "staging-migrations.json").read_text())
    expected = {f"{row['version']}_{row['name']}.sql" for row in recorded}
    actual = {path.name for path in paths}
    assert len(recorded) == len(expected), "Duplicate staging identity"
    assert len({path.name.split("_", 1)[0] for path in paths}) == len(paths)
    assert actual == expected, {"repo_only": actual - expected, "staging_only": expected - actual}
    for name, digest in APPLIED_BODIES.items():
        assert hashlib.md5((MIGRATIONS / name).read_bytes()).hexdigest() == digest, name
    assert not [path for path in paths if "20261016010000" < path.name[:14] < "20261016065035"]
    print(f"PASS: {len(paths)} repository and {len(recorded)} staging migrations; zero extras; three exact bodies.")


if __name__ == "__main__":
    main()
