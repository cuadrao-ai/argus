"""Reject credential-shaped literals in tracked configuration without echoing them."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

CONFIG_SUFFIXES = frozenset({".yaml", ".yml", ".toml", ".json", ".json5", ".jsonc", ".ini", ".cfg", ".conf", ".config"})
CREDENTIAL = re.compile(
    r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?![A-Za-z0-9_-])"
    r"|(?<![A-Za-z0-9_-])sb_[A-Za-z0-9_-]{12,}(?![A-Za-z0-9_-])"
)


def is_configuration(path: Path) -> bool:
    return path.suffix.lower() in CONFIG_SUFFIXES or path.name.startswith((".env", "Dockerfile"))


def credential_locations(root: Path) -> list[tuple[str, int]]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True,
    ).stdout.decode().split("\0")
    found: list[tuple[str, int]] = []
    for name in tracked:
        path = root / name
        if not name or not is_configuration(path) or not path.is_file() or path.is_symlink():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CREDENTIAL.search(line):
                found.append((name, number))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    locations = credential_locations(args.root)
    for name, number in locations:
        print(f"{name}:{number}: credential-shaped config literal; use environment injection", file=sys.stderr)
    return int(bool(locations))


if __name__ == "__main__":
    raise SystemExit(main())
