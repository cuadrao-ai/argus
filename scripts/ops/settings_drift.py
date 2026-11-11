"""Compare one staging service's live settings with the manifest.

The token comes from the environment at run time. Output is names and
non-secret values. A secret is present or missing and is never printed.
The command does not write.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Callable

from loguru import logger
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from scripts.ops.staging_env import (
    SECRETISH_NAME,
    SECRETISH_VALUE,
    ManifestError,
    RenderError,
    load_manifest,
    read_live,
    staging_entries,
    staging_services,
)

TOKEN_ENV = "RENDER_API_KEY"


def compare(service: dict[str, Any], live: dict[str, str]) -> list[str]:
    """Lines of agreement and drift. A drift line starts with ``drift``."""

    lines: list[str] = []
    known: set[str] = set()
    for entry in staging_entries(service):
        name = entry["name"]
        known.add(name)
        secret = entry.get("kind") != "plain" or SECRETISH_NAME.search(name) is not None
        present = name in live
        if secret or "value" not in entry:
            if entry.get("optional") and not present:
                lines.append(f"ok {name} absent")
            elif present:
                lines.append(f"ok {name} present")
            else:
                lines.append(f"drift {name} missing")
            continue
        expected = str(entry["value"])
        if not present:
            lines.append(f"drift {name} expected={expected} actual=missing")
            continue
        actual = live[name]
        if actual == expected:
            lines.append(f"ok {name}={expected}")
        elif SECRETISH_VALUE.search(actual):
            lines.append(f"drift {name} expected={expected} actual=<redacted>")
        else:
            lines.append(f"drift {name} expected={expected} actual={actual}")
    for removal in service.get("remove", []):
        known.add(removal["name"])
        if removal["name"] in live:
            lines.append(f"drift {removal['name']} extra")
    for hold in service.get("hold", []):
        known.add(hold["name"])
    for name in sorted(set(live) - known):
        lines.append(f"drift {name} extra")
    return lines


def drifted(lines: list[str]) -> bool:
    return any(line.startswith("drift ") for line in lines)


def _write_report(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def run(
    argv: list[str],
    client_factory: Callable[[str], Any] | None = None,
    out: Callable[[str], None] = _write_report,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=["api", "web"])
    parser.add_argument("--token-env", default=TOKEN_ENV)
    args = parser.parse_args(argv)

    class TokenSettings(BaseSettings):
        model_config = SettingsConfigDict(case_sensitive=True, env_file=None)
        token: SecretStr = Field(default=SecretStr(""), validation_alias=args.token_env)

    token = TokenSettings().token.get_secret_value()
    if not token:
        logger.error("{} is not set", args.token_env)
        return 2
    try:
        manifest = load_manifest()
        service = staging_services(manifest)[args.service]
        client = (client_factory or _client)(token)
        live = read_live(client, service)
    except (RenderError, ManifestError):
        logger.error(
            "Could not compare staging settings. Check the manifest and read-only access."
        )
        return 2
    lines = compare(service, live)
    for line in lines:
        out(line.replace(token, "<redacted>"))
    return 1 if drifted(lines) else 0


def _client(token: str) -> Any:
    from scripts.ops.staging_env import HttpRenderClient

    return HttpRenderClient(token)


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
