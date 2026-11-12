"""Reject undeclared links between deployables using tracked source paths."""

from __future__ import annotations

import fnmatch
import json
import posixpath
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = "scripts/cross_folder_links.json"
# These inspect repository structure, rather than consume another product's facts.
EXCLUSIONS = {
    "scripts/check_*.py": "Repository guards inspect the tree by design.",
    "scripts/ci/*": "CI selection, inventories and deployment inspect all packages.",
    "scripts/ops/staging_env.py": "Deployment configuration agreement reads all services.",
    "scripts/ops/settings_drift.py": "Deployment settings inventory reads all services.",
    "scripts/qa/setup-local-identities.sh": "Local worktree and identity setup.",
    "scripts/qa/write-local-env.sh": "Local worktree environment setup.",
    "tests/test_deploy_staging.py": "Tests of deployment change selection.",
    "tests/test_local_environment_store.py": "Tests of local worktree environment setup.",
    "tests/test_local_qa_env_writer.py": "Tests of local worktree environment setup.",
    "tests/test_worktree_environment_setup.py": "Tests of local worktree environment setup.",
    "tests/promotion_evidence_repository.py": "Synthetic repository for release tooling tests.",
    "tests/test_ci_*.py": "Tests of repository CI guards.",
    "tests/test_pr_guards.py": "Tests of repository ownership and PR guards.",
    "tests/test_modularity_budget.py": "Tests of repository modularity guard.",
    "tests/test_file_size_check.py": "Tests of repository file size guard.",
    "tests/test_no_evidence_media.py": "Tests of repository evidence guard.",
    "tests/test_cross_folder_links.py": "Tests intentionally create prohibited links.",
    "tests/test_alpha_artifacts.py": "Deployment and worktree configuration agreement.",
    "tests/test_private_alpha_release_profile.py": "Deployment service profile agreement.",
    "tests/test_render_release_profile_contract.py": "Deployment service configuration agreement.",
    "tests/test_local_smoke_contract.py": "Local worktree boot agreement.",
    "tests/test_config_credentials.py": "Credential template guard.",
}
SOURCE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".sh",
    ".json",
    ".toml",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".html",
    ".yaml",
    ".yml",
    "",
}
PATH = re.compile(r"(?<![\w/])(?:\.\./)*(?:src|web|marketing)/[\w./*${}+-]+")
QUOTED_JOIN = re.compile(r"""["']([^"'\n]+)["'](?:\s*/\s*["']([^"'\n]+)["'])+""")
LITERALS = re.compile(r"""["']([^"'\n]+)["']""")
IMPORT = re.compile(r"\b(?:from|import)\s+([a-zA-Z_]\w*(?:\.\w+)*)")


def package_paths(text: str) -> dict[str, str]:
    packages = {}
    for block in re.findall(r"\{[^{}]+\}", text):
        fields = dict(re.findall(r"(include|from)\s*=\s*[\"']([^\"']+)[\"']", block))
        if "include" in fields and "from" in fields:
            packages[fields["include"]] = fields["from"] + "/" + fields["include"]
    return packages


def package(path: str) -> str | None:
    top = path.split("/", 1)[0]
    return {
        "src": "api",
        "tests": "api",
        "web": "app",
        "marketing": "site",
        "pyproject.toml": "api",
    }.get(top)


def references(
    consumer: str, text: str, packages: dict[str, str], tracked: set[str] | None = None
) -> set[str]:
    """Conservatively include quoted paths, path joins, imports and generated credits."""
    joined = QUOTED_JOIN.sub(
        lambda match: '"' + "/".join(LITERALS.findall(match[0])) + '"', text
    )
    # Split literals in pathlib and path.join are still literal cross-package paths.
    joined = re.sub(
        r"\b(?:join|resolve)\([^()\n]+\)",
        lambda match: '"' + "/".join(LITERALS.findall(match[0])) + '"',
        joined,
    )
    roots = set(
        re.findall(r"(?:/\s*|(?:join|resolve)\(.*?)[\"'](web|marketing|src)[\"']", text)
    )
    paths = set(roots)
    for root in roots:
        for literal in LITERALS.findall(text):
            if "/" in literal and not literal.startswith(("/", "../", "http")):
                candidate = root + "/" + literal
                if tracked is not None and candidate in tracked:
                    paths.add(candidate)
    paths.update(
        {posixpath.normpath(match[0].lstrip("./")) for match in PATH.finditer(joined)}
    )
    for value in LITERALS.findall(text):
        if value.startswith("../"):
            resolved = posixpath.normpath(
                posixpath.join(posixpath.dirname(consumer), value)
            )
            if package(resolved):
                paths.add(resolved)
    for name in IMPORT.findall(text):
        first, _, rest = name.partition(".")
        if first in packages:
            paths.add(
                packages[first] + ("/" + rest.replace(".", "/") + ".py" if rest else "")
            )
        elif first in {"web", "marketing", "src"}:
            paths.add(name.replace(".", "/") + ".py")
    for name, folder in packages.items():
        for match in re.finditer(
            r'files\(["\']'
            + re.escape(name)
            + r'["\']\)\.joinpath\(["\']([^"\']+)["\']\)',
            text,
        ):
            paths.add(f"{folder}/{match[1]}")
        for match in re.finditer(re.escape(name) + r"/([\w./-]+)", text):
            paths.add(f"{folder}/{match[1]}")
    return paths


def discover(root: Path) -> set[tuple[str, str]]:
    tracked = set(
        subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    )
    if "pyproject.toml" not in tracked:
        raise ValueError("pyproject.toml must be tracked")
    packages = package_paths((root / "pyproject.toml").read_text())
    links: set[tuple[str, str]] = set()
    for consumer in tracked:
        if (
            not consumer
            or consumer == LIST
            or not (package(consumer) or consumer.startswith("scripts/"))
        ):
            continue
        if any(fnmatch.fnmatchcase(consumer, pattern) for pattern in EXCLUSIONS):
            continue
        path = root / consumer
        if path.suffix not in SOURCE_SUFFIXES or not path.is_file() or path.is_symlink():
            continue
        text = path.read_text(errors="replace")
        targets = references(consumer, text, packages, tracked)
        if consumer == "pyproject.toml":
            targets.update(packages.values())
        owners = {package(target) for target in targets} - {None}
        own = package(consumer)
        # A generator is its deployable's tooling. A multi-deployable script bridges all its endpoints.
        if own is None and len(owners) < 2:
            continue
        for target in targets:
            if package(target) and package(target) != own:
                links.add((consumer, target.rstrip("./")))
    return links


def main() -> int:
    started = time.perf_counter()
    links = discover(ROOT)
    entries = json.loads((ROOT / LIST).read_text())
    allowed = {(entry["consumer"], entry["owner"]) for entry in entries}
    for consumer, owner in sorted(links - allowed):
        print(
            f"new cross-folder link {consumer} -> {owner}: put the fact in shared/ or in its one owner (see AGENTS.md)"
        )
    for consumer, owner in sorted(allowed - links):
        print(
            f"listed link no longer exists: remove it from scripts/cross_folder_links.json ({consumer} -> {owner})"
        )
    print(
        f"Cross-folder links: {len(links)} found, {len(allowed)} listed; {time.perf_counter() - started:.3f}s"
    )
    return int(links != allowed)


if __name__ == "__main__":
    sys.exit(main())
