"""Show the linear `_ends_begin_atomic` splits every migration exactly as the old regex did.

    PYTHONPATH=. .venv/bin/python docs/reports/evidence/1890-baseline/splitter_equivalence.py

The old check regex-searched the whole file prefix at every `c`, so the 760 KB
baseline took about 100 s to split. This compares both on edge cases and on
every file in supabase/migrations_archive/ and supabase/migrations/.
"""

import re
import time
from pathlib import Path

from scripts.ops import production_migration_gate as gate


def old_ends_begin_atomic(source: str, index: int) -> bool:
    if source[index] not in {"c", "C"}:
        return False
    return re.search(r"(?i)(?<![\w$])begin\s+atomic$", source[: index + 1]) is not None


CASES = (
    "begin atomic", "BEGIN\n\t ATOMIC", "xbegin atomic", "$begin atomic", "_begin atomic",
    "beginatomic", "begin  atomiC", " begin atomic", "é begin atomic", "ébegin atomic",
    "begin atomicc", "c", "atomic", "begin\natomic",
)  # fmt: skip
for text in CASES:
    for index in range(len(text)):
        assert gate._ends_begin_atomic(text, index) == old_ends_begin_atomic(text, index), text

paths = sorted(Path("supabase/migrations_archive").glob("*.sql"))
paths += sorted(Path("supabase/migrations").glob("*.sql"))
new_splitter = gate._ends_begin_atomic
for path in paths:
    source = path.read_text()
    new = gate._split_supabase_statements(source)
    gate._ends_begin_atomic = old_ends_begin_atomic
    started = time.time()
    old = gate._split_supabase_statements(source)
    took = time.time() - started
    gate._ends_begin_atomic = new_splitter
    assert new == old, path
    if took > 1:
        print(f"{path.name}: {len(new)} statements, identical; the old splitter took {took:.0f}s")
print(f"{len(paths)} files split identically by the old and new check")
