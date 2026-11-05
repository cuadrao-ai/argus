#!/usr/bin/env python3
"""Split the checkpoint→candidate diff into per-file hunk files and print a summary table.

Usage: hunk_inventory.py <repo> <base> <head> <outdir> <path>...
Writes <outdir>/<slug>.diff per changed file and <outdir>/summary.md.
"""
import re
import subprocess
import sys
from pathlib import Path

repo, base, head, outdir, *paths = sys.argv[1:]
out = Path(outdir)
out.mkdir(parents=True, exist_ok=True)

names = subprocess.run(
    ["git", "-C", repo, "diff", "--name-status", base, head, "--"] + paths,
    check=True, capture_output=True, text=True,
).stdout.splitlines()

rows = []
for line in names:
    status, path = line.split("\t", 1)
    diff = subprocess.run(
        ["git", "-C", repo, "diff", "-U3", base, head, "--", path],
        check=True, capture_output=True, text=True,
    ).stdout
    hunks = re.findall(r"^@@ .* @@", diff, flags=re.M)
    plus = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    minus = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    slug = path.replace("ios/ArgusFoundation/", "").replace("/", "__")
    (out / f"{slug}.diff").write_text(diff)
    base_lines = 0
    if status != "A":
        base_lines = len(subprocess.run(
            ["git", "-C", repo, "show", f"{base}:{path}"], check=True, capture_output=True, text=True
        ).stdout.splitlines())
    rows.append((path, status, len(hunks), plus, minus, base_lines))

with (out / "summary.md").open("w") as f:
    f.write("| file | status | hunks | + | - | base lines |\n|---|---|---|---|---|---|\n")
    for r in rows:
        f.write("| " + " | ".join(str(x) for x in r) + " |\n")
print(open(out / "summary.md").read())
