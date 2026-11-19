"""Verify a promotion with trusted checkout code and publish its exact-head status."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

STATUS_CONTEXT = "production-migration-gate"
_EXACT_SHA = re.compile(r"[0-9a-f]{40}")


class WorkflowSettings(BaseSettings):
    """Read only the workflow's explicit environment, without dotenv discovery."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        hide_input_in_errors=True,
    )

    GITHUB_REF: str
    GITHUB_SHA: str
    GITHUB_REPOSITORY: str
    GITHUB_RUN_ID: str
    GITHUB_SERVER_URL: str
    GITHUB_API_URL: str
    GH_TOKEN: SecretStr
    PR_NUMBER: str
    RUNNER_TEMP: Path
    PATH: str
    ARGUS_PRODUCTION_DATABASE_URL: SecretStr = SecretStr("")
    CUADRAO_PRODUCTION_DATABASE_SSL_ROOT_CERT: str = ""


def request_json(
    settings: WorkflowSettings,
    route: str,
    body: dict[str, object] | None = None,
) -> dict[str, Any]:
    """Use the trusted API endpoint without following credential-bearing redirects."""

    url = f"{settings.GITHUB_API_URL}/repos/{settings.GITHUB_REPOSITORY}/{route}"
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.request(
            "POST" if body is not None else "GET",
            url,
            headers={"Authorization": f"Bearer {settings.GH_TOKEN.get_secret_value()}"},
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("invalid metadata response")
    return payload


def _current_head(settings: WorkflowSettings, number: int) -> str:
    pr = request_json(settings, f"pulls/{number}")
    if (
        pr["number"] != number
        or pr["state"] != "open"
        or pr["base"]["ref"] != "main"
        or pr["base"]["repo"]["full_name"] != settings.GITHUB_REPOSITORY
        or not isinstance(pr["head"]["sha"], str)
        or not _EXACT_SHA.fullmatch(pr["head"]["sha"])
    ):
        raise ValueError("invalid promotion")
    return str(pr["head"]["sha"])


def _publish(settings: WorkflowSettings, sha: str, state: str) -> None:
    request_json(
        settings,
        f"statuses/{sha}",
        {
            "state": state,
            "context": STATUS_CONTEXT,
            "description": f"Production migration verification: {state}",
            "target_url": (
                f"{settings.GITHUB_SERVER_URL}/{settings.GITHUB_REPOSITORY}"
                f"/actions/runs/{settings.GITHUB_RUN_ID}"
            ),
        },
    )


def _run(
    command: list[str],
    repo_root: Path,
    environ: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=repo_root,
        env=environ,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _write_evidence(
    output: Path,
    report: dict[str, Any],
    sha: str,
    trusted: str,
    state: str,
) -> None:
    evidence = {
        **report,
        "candidate_sha": sha,
        "trusted_sha": trusted,
        "status": "blocked" if state == "error" else report.get("status"),
        "publication_status": state,
    }
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


def run_promotion(settings: WorkflowSettings, *, repo_root: Path | None = None) -> int:
    """Fail closed on stale metadata, gate errors, or evidence identity mismatch."""

    root = repo_root or Path(__file__).resolve().parents[2]
    output = settings.RUNNER_TEMP / "production-migration-gate.json"
    certificate = settings.RUNNER_TEMP / "production-ledger-ca.crt"
    trusted = settings.GITHUB_SHA
    sha: str | None = None
    report: dict[str, Any] = {}
    try:
        if (
            settings.GITHUB_REF != "refs/heads/main"
            or not _EXACT_SHA.fullmatch(trusted)
            or not re.fullmatch(r"[1-9][0-9]*", settings.PR_NUMBER)
            or int(settings.PR_NUMBER) > 2**53 - 1
        ):
            raise ValueError("invalid dispatch")
        number = int(settings.PR_NUMBER)
        sha = _current_head(settings, number)
        _publish(settings, sha, "pending")
        output.unlink(missing_ok=True)
        database_url = settings.ARGUS_PRODUCTION_DATABASE_URL.get_secret_value()
        if not database_url or not settings.CUADRAO_PRODUCTION_DATABASE_SSL_ROOT_CERT:
            raise ValueError("ledger configuration missing")
        certificate.write_text(
            settings.CUADRAO_PRODUCTION_DATABASE_SSL_ROOT_CERT,
            encoding="utf-8",
        )
        public_env = {"PATH": settings.PATH, "GIT_TERMINAL_PROMPT": "0"}
        fetched = _run(
            ["git", "fetch", "--no-tags", "origin", f"refs/pull/{number}/head"],
            root,
            public_env,
        )
        if fetched.returncode != 0:
            raise ValueError("candidate fetch failed")
        resolved = _run(
            ["git", "rev-parse", "--verify", "FETCH_HEAD^{commit}"],
            root,
            public_env,
        )
        if resolved.returncode != 0 or resolved.stdout.strip() != sha:
            raise ValueError("candidate changed")
        result = _run(
            [
                sys.executable,
                str(root / "scripts/ops/production_migration_gate.py"),
                "--candidate-sha",
                sha,
                "--trusted-sha",
                trusted,
                "--output",
                str(output),
            ],
            root,
            {
                **public_env,
                "ARGUS_PRODUCTION_DATABASE_URL": database_url,
                "ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT": str(certificate),
            },
        )
        loaded = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("invalid report")
        report = loaded
        if report.get("candidate_sha") != sha or report.get("trusted_sha") != trusted:
            raise ValueError("evidence identity mismatch")
        if result.returncode == 0 and report.get("status") == "pass":
            state = "success"
        elif result.returncode == 1 and report.get("status") == "blocked":
            state = "failure"
        else:
            raise ValueError("gate execution failed")
        if _current_head(settings, number) != sha:
            raise ValueError("candidate changed")
        _write_evidence(output, report, sha, trusted, state)
        _publish(settings, sha, state)
        return 0 if state == "success" else 1
    except Exception:
        if sha is not None:
            try:
                _write_evidence(output, report, sha, trusted, "error")
            except Exception:
                pass
            try:
                _publish(settings, sha, "error")
            except Exception:
                pass
        logger.error(
            "Promotion verification failed; no successful result was established."
        )
        return 1
    finally:
        try:
            certificate.unlink(missing_ok=True)
        except OSError:
            logger.warning("Temporary public certificate cleanup failed.")


def main() -> int:
    try:
        settings = WorkflowSettings()
    except Exception:
        logger.error("Promotion workflow configuration is invalid.")
        return 1
    return run_promotion(settings)


if __name__ == "__main__":
    raise SystemExit(main())
