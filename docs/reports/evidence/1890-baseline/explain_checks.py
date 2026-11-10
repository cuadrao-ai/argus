"""Show that each CHECK constraint in schema.diff differs only by how Postgres re-reads it.

    python3 docs/reports/evidence/1890-baseline/explain_checks.py <container-b> <schema.diff>

For every `-    CONSTRAINT <name> CHECK <expr>` line (the history's stored text), it
adds the same CHECK to a temporary copy of the table in database B, reads the
definition back, and compares it with the `+` line (the baseline's text). Equal
text means the baseline holds exactly what Postgres makes of the history's
definition; nothing is written outside a rolled-back transaction.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

LINE = re.compile(r"^([-+])    CONSTRAINT (\S+) (CHECK .*?),?$")


def reread(container: str, name: str, check: str) -> str:
    table = subprocess.run(
        ["docker", "exec", container, "psql", "-U", "postgres", "-d", "postgres", "-XAtc",
         f"select conrelid::regclass from pg_constraint where conname = '{name}'"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8").strip()  # fmt: skip
    sql = (
        f"begin; create temp table t (like {table});"
        f" alter table t add constraint {name} {check};"
        f" select pg_get_constraintdef(oid) from pg_constraint"
        f" where conname = '{name}' and conrelid = 't'::regclass; rollback;"
    )
    out = subprocess.run(
        ["docker", "exec", container, "psql", "-U", "postgres", "-d", "postgres", "-XAtq", "-c", sql],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")  # fmt: skip
    return out.strip("\n").split("\n")[-1]


def main() -> None:
    container, diff = sys.argv[1], sys.argv[2]
    history, baseline = {}, {}
    # Bytes, split on newlines only, so a carriage return inside a CHECK survives.
    for line in Path(diff).read_bytes().decode("utf-8").split("\n"):
        match = LINE.match(line)
        if match:
            (history if match.group(1) == "-" else baseline)[match.group(2)] = match.group(3)
    failures = 0
    for name, check in sorted(history.items()):
        same = reread(container, name, check) == baseline.get(name)
        failures += not same
        print(f"{name}: history text re-read by Postgres {'equals' if same else 'DIFFERS FROM'} the baseline")
    print(f"{len(history) - failures} of {len(history)} explained")
    sys.exit(1 if failures or not history else 0)


if __name__ == "__main__":
    main()
