import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "marketing/lib/email/account-layout.ts"
_DEFINITION = re.compile(
    r"^(?:export\s+)?function\s+([A-Za-z0-9_]+)|^(?:export\s+)?const\s+([A-Za-z0-9_]+)\s*=",
    re.MULTILINE,
)


def _matching_brace(source: str, brace: int) -> int:
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(source)


def _body_brace(source: str, start: int, limit: int) -> int:
    paren = source.find("(", start, limit)
    first_brace = source.find("{", start, limit)
    if paren < 0 or (first_brace >= 0 and first_brace < paren):
        return first_brace
    depth = 0
    close = limit
    for index in range(paren, limit):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                close = index
                break
    index = close + 1
    while index < limit:
        while index < limit and source[index].isspace():
            index += 1
        if index < limit and source[index] == ":":
            index += 1
            continue
        if index < limit and source[index] == "{":
            end = _matching_brace(source, index)
            if source[end:limit].lstrip().startswith("{"):
                index = end
                continue
            return index
        index += 1
    return -1


def _block(source: str, start: int, limit: int) -> str:
    brace = _body_brace(source, start, limit)
    if brace < 0:
        return source[start:limit]
    return source[brace : _matching_brace(source, brace)]


def env_keys_read_by_render_account_email(source: str) -> set[str]:
    definitions = list(_DEFINITION.finditer(source))
    bodies: dict[str, str] = {}
    for index, match in enumerate(definitions):
        name = match.group(1) or match.group(2)
        limit = definitions[index + 1].start() if index + 1 < len(definitions) else len(source)
        bodies[name] = _block(source, match.end(), limit)
    pending = ["renderAccountEmail"]
    seen: set[str] = set()
    keys: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen or name not in bodies:
            continue
        seen.add(name)
        body = bodies[name]
        keys.update(re.findall(r"process\.env\.([A-Z][A-Z0-9_]*)", body))
        for callee in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", body):
            if callee in bodies and callee not in seen:
                pending.append(callee)
    return keys


def _example_keys(path: Path) -> set[str]:
    keys = set()
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_account_email_env_keys_are_declared_for_the_web_service() -> None:
    keys = env_keys_read_by_render_account_email(LAYOUT.read_text())
    assert keys, "renderAccountEmail and its helpers read no env keys"
    manifest = json.loads((ROOT / "scripts/ops/staging_env_manifest.json").read_text())
    web = manifest["services"]["web"]
    manifest_names = {entry["name"] for entry in web["entries"]} | {
        entry["name"] for entry in web["hold"]
    }
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text())
    service = next(
        item for item in blueprint["services"] if item["name"] == web["service_name"]
    )
    declared = {
        "render.yaml": {item["key"] for item in service["envVars"]},
        "web/.env.local.example": _example_keys(ROOT / "web/.env.local.example"),
        "scripts/ops/staging_env_manifest.json": manifest_names,
    }
    missing = {
        store: sorted(keys - names) for store, names in declared.items() if keys - names
    }
    assert not missing, missing
