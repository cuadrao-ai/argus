"""Compare two local Supabase databases: schema, grants, triggers, buckets and seed rows.

    python3 docs/reports/evidence/1890-baseline/schema_diff.py <container-a> <container-b> <out-dir>

Each side is a whole-database `pg_dump --schema-only` (every schema except the
migration ledger) plus a data dump of the tables the migrations own and of
storage.buckets, both from the container's own pg_dump. It writes the
normalized dumps and their unified diff to <out-dir> and exits 1 when they
differ.

Normalizing removes only what does not describe the schema: pg_dump's session
token and version lines, the order of its object blocks (ties break on object
ids, which differ between two builds), and clock times in seed rows.
"""

from __future__ import annotations

import difflib
import re
import subprocess
import sys
from pathlib import Path

VOLATILE = (
    re.compile(r"^\\(un)?restrict "),
    re.compile(r"^-- Dumped (from|by) "),
)
CLOCK = re.compile(r"'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(\.\d+)?\+00'")
BLOCK = re.compile(r"\n(?=--\n-- (Name|Data for Name): )")


def dump(container: str, *args: str) -> str:
    # Bytes, decoded strictly: a string literal in the dump can hold a raw carriage
    # return or tab, which universal newlines and str.splitlines() would lose.
    return subprocess.run(
        ["docker", "exec", container, "pg_dump", "-U", "supabase_admin", "-d", "postgres", *args],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")  # fmt: skip


def normalized(container: str) -> list[str]:
    schema = dump(container, "--schema-only", "-N", "supabase_migrations")
    data = dump(container, "--data-only", "--column-inserts", "-n", "public", "-n", "argus_private")
    data += dump(container, "--data-only", "--column-inserts", "-t", "storage.buckets")
    blocks = []
    for block in BLOCK.split(schema + data)[::2]:
        lines = [line for line in block.split("\n") if not any(p.match(line) for p in VOLATILE)]
        blocks.append("\n".join(CLOCK.sub("'<clock>'", line) for line in lines).strip("\n"))
    return "\n\n".join(sorted(b for b in blocks if b)).split("\n")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="")


def main() -> None:
    left, right, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    a, b = normalized(left), normalized(right)
    write(out / "a.sql", "\n".join(a) + "\n")
    write(out / "b.sql", "\n".join(b) + "\n")
    diff = list(difflib.unified_diff(a, b, "a (history + drops)", "b (baseline)", lineterm=""))
    write(out / "schema.diff", "\n".join(diff) + ("\n" if diff else ""))
    print(f"a: {len(a)} lines, b: {len(b)} lines, diff: {len(diff)} lines")
    sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
