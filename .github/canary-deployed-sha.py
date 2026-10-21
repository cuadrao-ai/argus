#!/usr/bin/env python3
"""Resolve one coherent deployed SHA from Render status payloads."""

from __future__ import annotations

import argparse
import re
import sys


def _status_values(raw_status: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw_status.splitlines():
        key, separator, value = line.partition("=")
        if separator and key and key not in values:
            values[key] = value
    return values


def _value(values: dict[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    return "" if value == "<missing>" else value


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _workflow_commit_matches(full_sha: str, workflow_sha: str) -> bool:
    return bool(
        re.fullmatch(r"[0-9a-f]{40}", full_sha)
        and re.fullmatch(r"[0-9a-f]{7,40}", workflow_sha)
        and full_sha.startswith(workflow_sha)
    )


def resolve_deployed_sha(
    *, api_status: str, web_status: str, workflow_status: str
) -> str:
    api = _status_values(api_status)
    web = _status_values(web_status)
    workflow = _status_values(workflow_status)

    _require(_value(api, "status") == "live", "api_deploy_not_live")
    _require(_value(web, "status") == "live", "web_deploy_not_live")
    _require(_value(workflow, "status") == "ready", "workflow_version_not_ready")

    workflow_version_id = _value(workflow, "workflow_version_id")
    _require(bool(workflow_version_id), "workflow_version_id_missing")

    api_sha = _value(api, "commit")
    web_sha = _value(web, "commit")
    workflow_sha = _value(workflow, "commit")
    _require(bool(api_sha), "api_deploy_sha_missing")
    _require(bool(web_sha), "web_deploy_sha_missing")
    _require(
        _workflow_commit_matches(api_sha, workflow_sha),
        "workflow_commit_mismatch",
    )
    return api_sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-status", required=True)
    parser.add_argument("--web-status", required=True)
    parser.add_argument("--workflow-status", required=True)
    args = parser.parse_args()
    try:
        print(
            resolve_deployed_sha(
                api_status=args.api_status,
                web_status=args.web_status,
                workflow_status=args.workflow_status,
            )
        )
    except ValueError as error:
        print(f"ERROR: canary failed at services_same_commit: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
