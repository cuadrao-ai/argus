"""The Business guides refer to shipped words, files and table columns."""

import json
import re
import subprocess
from pathlib import Path

import pytest
from argus.domain.business.reporting_columns import TABLE_COLUMNS

from scripts.check_docs_links import check_document

ROOT = Path(__file__).resolve().parents[1]
DICTIONARY = "docs/specs/field-dictionary.md"
DOCS = (
    "docs/ARCHITECTURE.md",
    "docs/DOCUMENTATION_AUTHORITY.md",
    DICTIONARY,
    ".agent/designs/cuadrao-business-app/DESIGN.md",
)
# Include module-relative paths, filenames and glob patterns, but skip API routes.
REPO_PATH = re.compile(
    r"(?:[.\w-]+/[\w./*<>-]*|[\w.-]+\.(?:py|tsx?|css|md|json|sql|ya?ml|svg|png))"
)


@pytest.fixture(scope="module")
def files_by_name() -> dict[str, list[Path]]:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode()
    by_name: dict[str, list[Path]] = {}
    for name in tracked.split("\0"):
        if name:
            path = Path(name)
            by_name.setdefault(path.name, []).append(path)
    return by_name


def path_exists(ref: str, files_by_name: dict[str, list[Path]]) -> bool:
    if "*" in ref or "<language>" in ref:
        return any(ROOT.glob(ref.replace("<language>", "*")))
    if (ROOT / ref).exists():
        return True
    # A rooted reference must exist as written. Short references may omit a parent.
    if (ROOT / ref.split("/")[0]).is_dir():
        return False
    return any(
        path.match(ref) and (ROOT / path).is_file()
        for path in files_by_name.get(Path(ref).name, [])
    )


@pytest.mark.parametrize("document", DOCS)
def test_documented_business_references_exist(
    document: str, files_by_name: dict[str, list[Path]]
) -> None:
    locales = {
        lang: json.loads((ROOT / f"web/public/locales/{lang}/common.json").read_text())
        for lang in ("es-419", "en")
    }
    missing = []
    assert not (broken_links := check_document(ROOT, ROOT / document)), broken_links
    for line_no, line in enumerate((ROOT / document).read_text().splitlines(), 1):
        for key in re.findall(r"Registros column(?: key)? `([\w-]+)`", line, re.I):
            if key not in TABLE_COLUMNS:
                missing.append((line_no, "Registros column", key))
        for token in re.findall(r"(?<!`)`([^`]+)`(?!`)", line):
            if re.fullmatch(r"business(?:\.[\w-]+)+", token):
                for lang, words in locales.items():
                    value = words
                    for part in token.split("."):
                        value = value.get(part) if isinstance(value, dict) else None
                    if not isinstance(value, str):
                        missing.append((line_no, lang, token))
            else:
                ref = re.split(r"[:#]", token, maxsplit=1)[0]
                # A Python call can qualify its module as folder/module.function().
                call = re.fullmatch(r"([\w./-]+/[\w-]+)\.\w+\(\)", ref)
                if call:
                    ref = call.group(1) + ".py"
                if REPO_PATH.fullmatch(ref) and not path_exists(ref, files_by_name):
                    missing.append((line_no, "path", ref))
    assert not missing, missing


def test_documented_registros_columns_exist() -> None:
    text = (ROOT / DICTIONARY).read_text().split("## Registros columns\n", 1)[1]
    section = text.split("\n## ", 1)[0]
    columns = re.findall(r"^\| `(\w+)` \|", section, re.MULTILINE)
    assert columns
    assert set(columns) <= set(TABLE_COLUMNS)
