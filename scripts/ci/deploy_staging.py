"""Decide which staging service a commit deploys.

The live web service is cuadrao-app-staging. Its build root is web/, from the
blueprint service whose rootDir is web. The API service builds the repository
root with poetry, including the package under web/argus_display_contract.
supabase/migrations and supabase/config.toml follow the backend paths the CI
classifier treats as heavy. docs/ deploy nothing. The marketing staging
service stays out of this deploy.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SERVICE_ID_RE = re.compile(r"^srv-[A-Za-z0-9]+$")
API_SERVICE = "cuadrao-api-staging"
WEB_SERVICE = "cuadrao-app-staging"
ALLOWED = (API_SERVICE, WEB_SERVICE)
REJECTED = frozenset(
    {
        "cuadrao-api",
        "cuadrao-app",
        "cuadrao-marketing",
        "cuadrao-web",
        "cuadrao-marketing-staging",
    }
)
SKIP_LINE = "Nothing deployable changed since the comparison commit. Skipping deploy."
CI_CHECK = "ci"
PENDING_DEPLOY = frozenset(
    {
        "created",
        "build_in_progress",
        "update_in_progress",
        "pre_deploy_in_progress",
        "queued",
    }
)
FAILED_DEPLOY = frozenset(
    {
        "build_failed",
        "update_failed",
        "deactivated",
        "canceled",
    }
)
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_INTERVAL_SECONDS = 15
DEPLOY_ID_RE = re.compile(r"^dep-[A-Za-z0-9]+$")


class DeployError(Exception):
    pass


@dataclass(frozen=True)
class ServicePaths:
    name: str
    prefixes: tuple[str, ...]
    exact: frozenset[str]


RULES = (
    ServicePaths(
        API_SERVICE,
        ("src/", "web/argus_display_contract/", "supabase/migrations/"),
        frozenset(
            {
                "pyproject.toml",
                "poetry.lock",
                ".python-version",
                "supabase/config.toml",
                "Dockerfile",
                "requirements.txt",
            }
        ),
    ),
    ServicePaths(WEB_SERVICE, ("web/",), frozenset()),
)


def resolve_sha(raw: str, head: str) -> str:
    chosen = (raw.strip() or head.strip()).lower()
    if SHA_RE.fullmatch(chosen) is None:
        raise DeployError("SHA must be 40 hex characters.")
    return chosen


def normalize(path: str) -> str:
    cleaned = path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def matches(path: str, rule: ServicePaths) -> bool:
    normal = normalize(path)
    if not normal:
        return False
    if normal in rule.exact:
        return True
    return any(normal.startswith(prefix) for prefix in rule.prefixes)


def select_services(
    api_paths: list[str],
    web_paths: list[str],
    *,
    force_all: bool,
) -> tuple[str, ...]:
    if force_all:
        return ALLOWED
    by_name = {API_SERVICE: api_paths, WEB_SERVICE: web_paths}
    return tuple(
        rule.name
        for rule in RULES
        if any(matches(path, rule) for path in by_name[rule.name])
    )


def allow_name(name: str) -> str:
    if name in REJECTED or name not in ALLOWED:
        raise DeployError(
            f"Refusing service {name}. Staging deploy allows only "
            f"{API_SERVICE} and {WEB_SERVICE}."
        )
    return name


def flag(value: str) -> bool:
    token = value.strip().lower()
    if token in {"true", "1"}:
        return True
    if token in {"false", "0", ""}:
        return False
    raise DeployError("FORCE_ALL must be true or false.")


def git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "git failed"
        raise DeployError(detail)
    return result.stdout.strip()


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def assert_ancestor(repo: Path, sha: str, tip: str) -> None:
    commit = resolve_sha(sha, sha)
    if not is_ancestor(repo, commit, tip):
        raise DeployError(f"{commit} is not an ancestor of {tip}.")


def older_base(repo: Path, left: str, right: str) -> str:
    first = resolve_sha(left, left)
    second = resolve_sha(right, right)
    if first == second or is_ancestor(repo, first, second):
        return first
    if is_ancestor(repo, second, first):
        return second
    return git(repo, ["merge-base", first, second])


def read_json(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DeployError("Cannot read the JSON payload.") from exc


def flatten_checks(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        runs: list[dict[str, object]] = []
        for item in payload:
            runs.extend(flatten_checks(item))
        return runs
    if isinstance(payload, dict):
        nested = payload.get("check_runs")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if "name" in payload:
            return [payload]
    raise DeployError("Cannot read check runs.")


def load_checks(text: str) -> list[dict[str, object]]:
    stripped = text.strip()
    if not stripped:
        return []
    try:
        return flatten_checks(read_json(stripped))
    except DeployError:
        runs: list[dict[str, object]] = []
        for line in stripped.splitlines():
            if line.strip():
                runs.extend(flatten_checks(read_json(line)))
        return runs


def latest_checks(
    runs: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    latest: dict[str, tuple[str, dict[str, object]]] = {}
    for run in runs:
        name = str(run.get("name") or "")
        stamp = str(run.get("completed_at") or run.get("started_at") or "")
        current = latest.get(name)
        if current is None or stamp >= current[0]:
            latest[name] = (stamp, run)
    return {name: run for name, (_, run) in latest.items()}


def require_green(runs: list[dict[str, object]], status: dict[str, object]) -> None:
    latest = latest_checks(runs)
    ci_run = latest.get(CI_CHECK)
    if ci_run is None or ci_run.get("conclusion") != "success":
        raise DeployError("The ci check has not succeeded at this commit.")
    # A skipped docs-checks run is a passing gate. Any other conclusion is not.
    docs = latest.get("docs-checks")
    if docs is not None and docs.get("conclusion") not in {"success", "skipped"}:
        raise DeployError("docs-checks did not succeed or skip.")
    total = int(status.get("total_count") or 0)
    if total == 0:
        return
    if status.get("state") != "success":
        raise DeployError("Combined commit status is not success.")


def rows(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        raise DeployError("Cannot read the JSON payload.")
    return [row for row in payload if isinstance(row, dict)]


def live_commit(payload: object) -> str | None:
    deploys: list[dict[str, object]] = []
    for row in rows(payload):
        deploy = row.get("deploy", row)
        if isinstance(deploy, dict):
            deploys.append(deploy)
    deploys.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    for deploy in deploys:
        if deploy.get("status") != "live":
            continue
        commit = deploy.get("commit")
        sha = ""
        if isinstance(commit, dict):
            sha = str(commit.get("id") or "")
        elif isinstance(commit, str):
            sha = commit
        sha = sha.lower()
        if SHA_RE.fullmatch(sha):
            return sha
    return None


def comparison_base(live: str, parent: str) -> str:
    token = live.strip().lower()
    if token in {"", "unknown"}:
        return resolve_sha(parent, parent)
    return resolve_sha(token, token)


def resolve_service(payload: object, expect: str) -> str:
    allow_name(expect)
    found: list[str] = []
    for row in rows(payload):
        service = row.get("service", row)
        if not isinstance(service, dict) or service.get("name") != expect:
            continue
        service_id = str(service.get("id") or "")
        if SERVICE_ID_RE.fullmatch(service_id) is None:
            raise DeployError("Service id is not usable.")
        found.append(service_id)
    if len(found) != 1:
        raise DeployError(f"Expected one service named {expect}.")
    return found[0]


def summarize_deploy(payload: object, name: str) -> str:
    allow_name(name)
    if not isinstance(payload, dict) or not str(payload.get("status") or ""):
        raise DeployError("Deploy response had no status.")
    return f"Requested deploy for {name}."


def split_paths(data: bytes) -> list[str]:
    if b"\0" in data:
        if data.endswith(b"\0"):
            data = data[:-1]
        parts = data.split(b"\0")
    else:
        parts = data.splitlines()
    return [part.decode("utf-8", "surrogateescape") for part in parts if part]


def read_paths(path: str | None) -> list[str]:
    if not path:
        return []
    return split_paths(Path(path).read_bytes())


def command_validate(args: argparse.Namespace) -> int:
    raw = args.sha if args.sha is not None else os.environ.get("INPUT_SHA", "")
    head = ""
    if not raw.strip():
        head = git(Path(args.repo), ["rev-parse", "HEAD"])
    print(resolve_sha(raw, head))
    return 0


def command_ancestor(args: argparse.Namespace) -> int:
    assert_ancestor(Path(args.repo), args.sha, args.tip)
    return 0


def command_allow(args: argparse.Namespace) -> int:
    allow_name(args.name)
    return 0


def command_allowlist(_args: argparse.Namespace) -> int:
    for name in ALLOWED:
        print(name)
    return 0


def command_select(args: argparse.Namespace) -> int:
    force_all = flag(os.environ.get("FORCE_ALL", ""))
    if args.api_paths or args.web_paths:
        api_paths = read_paths(args.api_paths)
        web_paths = read_paths(args.web_paths)
    else:
        shared = split_paths(sys.stdin.buffer.read())
        api_paths = shared
        web_paths = shared
    chosen = select_services(api_paths, web_paths, force_all=force_all)
    if not chosen:
        print(SKIP_LINE)
        return 0
    for name in chosen:
        print(name)
    return 0


def command_require(args: argparse.Namespace) -> int:
    runs = load_checks(Path(args.check_runs).read_text(encoding="utf-8"))
    status = read_json(Path(args.status).read_text(encoding="utf-8"))
    if not isinstance(status, dict):
        raise DeployError("Cannot read the JSON payload.")
    require_green(runs, status)
    return 0


def command_live(_args: argparse.Namespace) -> int:
    commit = live_commit(read_json(sys.stdin.read()))
    print(commit or "unknown")
    return 0


def command_resolve(args: argparse.Namespace) -> int:
    print(resolve_service(read_json(sys.stdin.read()), args.expect))
    return 0


def command_base(_args: argparse.Namespace) -> int:
    print(
        comparison_base(
            os.environ.get("LIVE_COMMIT", ""),
            os.environ.get("PARENT_SHA", ""),
        )
    )
    return 0


def command_older(args: argparse.Namespace) -> int:
    print(
        older_base(
            Path(args.repo),
            os.environ.get("API_BASE", ""),
            os.environ.get("WEB_BASE", ""),
        )
    )
    return 0


def command_summarize(args: argparse.Namespace) -> int:
    payload = read_json(Path(args.response).read_text(encoding="utf-8"))
    print(summarize_deploy(payload, args.name))
    return 0


def deploy_commit(payload: dict[str, object]) -> str:
    commit = payload.get("commit")
    if isinstance(commit, dict):
        return str(commit.get("id") or "").lower()
    if isinstance(commit, str):
        return commit.lower()
    return ""


def classify_deploy(payload: dict[str, object], expected_sha: str, name: str) -> str:
    status = str(payload.get("status") or "")
    if status == "live":
        if deploy_commit(payload) != expected_sha:
            raise DeployError(f"{name} is live at a different commit.")
        return "live"
    if status in FAILED_DEPLOY:
        raise DeployError(f"{name} deploy failed: {status}.")
    if status in PENDING_DEPLOY:
        return "pending"
    label = status or "missing"
    raise DeployError(f"{name} deploy failed: unexpected status {label}.")


def poll_deploy(
    fetch,
    *,
    name: str,
    expected_sha: str,
    timeout: float,
    interval: float,
    now,
    sleep,
) -> None:
    start = now()
    while True:
        if now() - start >= timeout:
            raise DeployError(f"{name} deploy timed out.")
        try:
            payload = fetch()
        except StopIteration:
            raise DeployError(f"{name} deploy timed out.") from None
        if not isinstance(payload, dict):
            raise DeployError(f"{name} deploy failed: unexpected status missing.")
        if classify_deploy(payload, expected_sha, name) == "live":
            return
        sleep(interval)


def posted_deploy_id(payload: object) -> str:
    if not isinstance(payload, dict):
        raise DeployError("Deploy response had no status.")
    value = str(payload.get("id") or "")
    if DEPLOY_ID_RE.fullmatch(value) is None:
        raise DeployError("Deploy id is not usable.")
    return value


def fetch_render_deploy(
    service_id: str, deploy_id: str, api_key: str
) -> dict[str, object]:
    if SERVICE_ID_RE.fullmatch(service_id) is None:
        raise DeployError("Service id is not usable.")
    if DEPLOY_ID_RE.fullmatch(deploy_id) is None:
        raise DeployError("Deploy id is not usable.")
    if not api_key:
        raise DeployError(
            "RENDER_API_KEY is missing. Lucas adds it as a repository secret."
        )
    url = f"https://api.render.com/v1/services/{service_id}/deploys/{deploy_id}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise DeployError(f"Deploy status request failed: HTTP {exc.code}.") from None
    except Exception as exc:
        raise DeployError(
            f"Deploy status request failed: {type(exc).__name__}."
        ) from None
    payload = read_json(body)
    if not isinstance(payload, dict):
        raise DeployError("Cannot read the deploy status.")
    return payload


def command_wait(args: argparse.Namespace) -> int:
    allow_name(args.name)
    expected = resolve_sha(args.sha, args.sha)
    timeout = float(args.timeout)
    interval = float(args.interval)
    if args.responses:
        payloads = [
            read_json(line)
            for line in Path(args.responses).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        clock = {"t": 0.0}

        def now() -> float:
            return clock["t"]

        def sleep(seconds: float) -> None:
            clock["t"] += seconds

        def fetch():
            if not payloads:
                raise StopIteration
            return payloads.pop(0)

        poll_deploy(
            fetch,
            name=args.name,
            expected_sha=expected,
            timeout=timeout,
            interval=interval,
            now=now,
            sleep=sleep,
        )
    else:
        payload = read_json(Path(args.response).read_text(encoding="utf-8"))
        deploy_id = posted_deploy_id(payload)
        api_key = os.environ.get("RENDER_API_KEY", "")

        def fetch_live():
            return fetch_render_deploy(args.service_id, deploy_id, api_key)

        poll_deploy(
            fetch_live,
            name=args.name,
            expected_sha=expected,
            timeout=timeout,
            interval=interval,
            now=time.monotonic,
            sleep=time.sleep,
        )
    print(f"{args.name} is live.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decide a staging deploy.")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-sha")
    validate.add_argument("--sha", default=None)
    validate.add_argument("--repo", default=".")
    validate.set_defaults(func=command_validate)

    ancestor = commands.add_parser("assert-ancestor")
    ancestor.add_argument("--sha", required=True)
    ancestor.add_argument("--tip", required=True)
    ancestor.add_argument("--repo", default=".")
    ancestor.set_defaults(func=command_ancestor)

    allow = commands.add_parser("allow-name")
    allow.add_argument("--name", required=True)
    allow.set_defaults(func=command_allow)

    allowlist = commands.add_parser("allowlist")
    allowlist.set_defaults(func=command_allowlist)

    select = commands.add_parser("select-services")
    select.add_argument("--api-paths")
    select.add_argument("--web-paths")
    select.set_defaults(func=command_select)

    require = commands.add_parser("require-green")
    require.add_argument("--check-runs", required=True)
    require.add_argument("--status", required=True)
    require.set_defaults(func=command_require)

    live = commands.add_parser("live-commit")
    live.set_defaults(func=command_live)

    resolve = commands.add_parser("resolve-service")
    resolve.add_argument("--expect", required=True)
    resolve.set_defaults(func=command_resolve)

    base = commands.add_parser("comparison-base")
    base.set_defaults(func=command_base)

    older = commands.add_parser("older-base")
    older.add_argument("--repo", default=".")
    older.set_defaults(func=command_older)

    summary = commands.add_parser("summarize-deploy")
    summary.add_argument("--name", required=True)
    summary.add_argument("--response", required=True)
    summary.set_defaults(func=command_summarize)

    wait = commands.add_parser("wait-deploy")
    wait.add_argument("--name", required=True)
    wait.add_argument("--sha", required=True)
    wait.add_argument("--responses")
    wait.add_argument("--service-id")
    wait.add_argument("--response")
    wait.add_argument("--timeout", default=str(DEFAULT_TIMEOUT_SECONDS))
    wait.add_argument("--interval", default=str(DEFAULT_INTERVAL_SECONDS))
    wait.set_defaults(func=command_wait)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except DeployError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
