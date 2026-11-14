"""Keep the documented active and retired conversation routes aligned with OpenAPI."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _endpoint_table(heading: str) -> list[tuple[str, str]]:
    contract = (ROOT / "docs/API_CONTRACT.md").read_text(encoding="utf-8")
    assert heading in contract, f"Missing endpoint table: {heading}"
    section = contract.split(heading, 1)[1].split("\n## ", 1)[0]
    operations = re.findall(r"^\| `(GET|POST|PATCH|DELETE)` \| `([^`]+)` \|", section, re.M)
    assert operations, f"Empty endpoint table: {heading}"
    return operations


def _canonical_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path.split("?", 1)[0])


def test_active_contract_endpoints_exist_in_openapi() -> None:
    paths = yaml.safe_load((ROOT / "docs/api/openapi.yaml").read_text())["paths"]
    canonical = {_canonical_path(path): operations for path, operations in paths.items()}
    contract = (ROOT / "docs/API_CONTRACT.md").read_text(encoding="utf-8")
    # Cover every endpoint table, including separate Method/Path columns and
    # combined method-and-path cells. Historical rows must say Retired explicitly.
    operations = []
    section = ""
    for line in contract.splitlines():
        if line.startswith("#"):
            section = line
        if not line.startswith("|") or "Retired" in line:
            continue
        for method, path in re.findall(
            r"`(GET|POST|PATCH|DELETE|PUT|HEAD|OPTIONS)(?:`\s*\|\s*`| )([^`]+)`",
            line,
        ):
            if section == "### Routes and commands":
                # This table explicitly declares its household-plan base above it.
                path = "/api/v1/households/{household_id}/plan" + path.rstrip("/")
            elif not path.startswith("/api/"):
                path = "/api/v1" + path
            operations.append((method, path))
    assert operations
    assert set(_endpoint_table("## Active conversation endpoint table")) <= set(operations)
    missing = [
        f"{method} {path}"
        for method, path in operations
        if method.lower() not in canonical.get(_canonical_path(path), {})
    ]
    assert not missing, "Active contract operations absent from OpenAPI: " + ", ".join(missing)


def test_retired_contract_endpoints_are_absent_from_openapi() -> None:
    paths = yaml.safe_load((ROOT / "docs/api/openapi.yaml").read_text())["paths"]
    retired = _endpoint_table("## Retired operations (#1996)")
    assert len(retired) == 26
    assert len(set(retired)) == len(retired)
    still_active = [
        f"{method} {path}"
        for method, path in retired
        if method.lower() in paths.get(path, {})
    ]
    assert not still_active, "Retired operations still in OpenAPI: " + ", ".join(still_active)
