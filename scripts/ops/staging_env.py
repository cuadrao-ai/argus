"""Make the two Render staging services match scripts/ops/staging_env_manifest.json.

Commands: plan, apply [--dry-run], check, clipboard api|web, show-verify-token.
Output carries variable names only, never values. Staging services only: the
manifest names both service ids and apply refuses any service whose Render name
differs from the manifest's.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets as secrets_module
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

MANIFEST_PATH = Path(__file__).with_name("staging_env_manifest.json")
DEFAULT_SECRETS_FILE = Path.home() / ".cuadrao" / "staging-secrets.env"
RENDER_API = "https://api.render.com/v1"
VERIFY_TOKEN_NAME = "CUADRAO_WHATSAPP_VERIFY_TOKEN"
KINDS = ("plain", "secret", "generated")
SECRETISH_NAME = re.compile(
    r"SECRET|TOKEN|PASSWORD|API_KEY|SERVICE_ROLE|DATABASE_URL|PRIVATE|SENDER_KEY", re.I
)
SECRETISH_VALUE = re.compile(r"://[^/\s]*:[^@\s]*@|^sk-|^eyJ|BEGIN [A-Z ]*PRIVATE KEY")


class ManifestError(Exception):
    """The manifest breaks a rule; the message names entries, never values."""


class RenderError(Exception):
    """A Render call failed; the message carries a status only, never a body."""


class RenderClient(Protocol):
    def service_name(self, service_id: str) -> str: ...
    def list_env(self, service_id: str) -> dict[str, str]: ...
    def put_env(self, service_id: str, env: dict[str, str]) -> None: ...


class HttpRenderClient:
    def __init__(self, api_key: str) -> None:
        import httpx

        self._http = httpx.Client(
            base_url=RENDER_API,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=30,
        )

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except Exception as exc:  # transport errors can echo URLs and headers
            raise RenderError(f"{method} {path.split('?')[0]} failed: {type(exc).__name__}") from None
        if response.status_code >= 400:
            raise RenderError(f"{method} {path.split('?')[0]} failed: HTTP {response.status_code}")
        return response.json()

    def service_name(self, service_id: str) -> str:
        return str(self._call("GET", f"/services/{service_id}").get("name", ""))

    def list_env(self, service_id: str) -> dict[str, str]:
        env: dict[str, str] = {}
        cursor = ""
        while True:
            suffix = f"&cursor={cursor}" if cursor else ""
            rows = self._call("GET", f"/services/{service_id}/env-vars?limit=100{suffix}")
            for row in rows:
                env[row["envVar"]["key"]] = row["envVar"].get("value") or ""
            if len(rows) < 100:
                return env
            cursor = rows[-1]["cursor"]

    def put_env(self, service_id: str, env: dict[str, str]) -> None:
        body = [{"key": key, "value": value} for key, value in env.items()]
        self._call("PUT", f"/services/{service_id}/env-vars", json=body)


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(path.read_text())
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    for label, service in manifest["services"].items():
        entries = {e["name"]: e for e in service["entries"]}
        names = [e["name"] for e in service["entries"]]
        names += [r["name"] for r in service["remove"]] + [h["name"] for h in service["hold"]]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ManifestError(f"{label}: duplicate or conflicting names: {duplicates}")
        for entry in service["entries"]:
            name, kind = entry["name"], entry.get("kind")
            if kind not in KINDS:
                raise ManifestError(f"{label}: {name} has unknown kind")
            if kind != "plain" and "value" in entry:
                raise ManifestError(f"{label}: {name} is {kind} and must not carry a value")
            if kind == "plain":
                modes = [k for k in ("value", "keep_current", "copy_from") if k in entry]
                if len(modes) != 1:
                    raise ManifestError(f"{label}: {name} needs exactly one of value, keep_current, copy_from")
                if "value" in entry and (
                    SECRETISH_NAME.search(name) or SECRETISH_VALUE.search(str(entry["value"]))
                ):
                    raise ManifestError(f"{label}: {name} looks like a secret and cannot hold a plain value")
        for removal in service["remove"]:
            required = removal.get("requires")
            if required and required not in entries:
                raise ManifestError(f"{label}: removal of {removal['name']} requires an entry that is missing")
        for pair in service.get("distinct", []):
            if any(name not in entries for name in pair):
                raise ManifestError(f"{label}: distinct pair names an unknown entry")


def read_secrets(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.stat().st_mode & 0o077:
        raise ManifestError(f"secrets file {path} must be mode 600 (chmod 600 it)")
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def append_secret(path: Path, name: str, value: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as handle:
        handle.write(f"{name}={value}\n")


@dataclass
class Plan:
    actions: list[tuple[str, str]] = field(default_factory=list)  # (name, action)
    problems: list[str] = field(default_factory=list)
    final: dict[str, str] = field(default_factory=dict)
    generated: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)  # managed names absent after this plan

    @property
    def changes(self) -> bool:
        return any(a in ("add", "update", "delete") for _, a in self.actions)


def compute_plan(
    service: dict[str, Any],
    live: dict[str, str],
    file_secrets: dict[str, str],
    generator: Callable[[], str] = lambda: secrets_module.token_urlsafe(48),
) -> Plan:
    plan = Plan(final=dict(live))
    for entry in service["entries"]:
        name, kind = entry["name"], entry["kind"]
        desired: str | None = None
        if kind == "plain" and "value" in entry:
            desired = str(entry["value"])
        elif kind == "plain" and "copy_from" in entry:
            desired = live.get(name) if name in live else live.get(entry["copy_from"])
        elif entry.get("keep_current"):
            desired = live.get(name)
        elif name in file_secrets:
            desired = file_secrets[name]
        elif name in live:
            desired = live[name]
        elif kind == "generated":
            desired = plan.generated[name] = generator()
        if desired is None:
            plan.missing.append(name)
            plan.actions.append((name, "missing"))
            continue
        action = "add" if name not in live else "update" if live[name] != desired else "ok"
        plan.final[name] = desired
        plan.actions.append((name, action))
    for removal in service["remove"]:
        name = removal["name"]
        if name not in live:
            plan.actions.append((name, "gone"))
        elif removal.get("requires") and removal["requires"] not in plan.final:
            plan.problems.append(f"{name} stays: {removal['requires']} is not set")
            plan.actions.append((name, "blocked"))
        else:
            plan.final.pop(name)
            plan.actions.append((name, "delete"))
    for hold in service["hold"]:
        plan.actions.append((hold["name"], "hold"))
    known = {n for n, _ in plan.actions}
    plan.actions += [(n, "extra") for n in sorted(live) if n not in known]
    for pair in service.get("distinct", []):
        values = [plan.final.get(n) for n in pair]
        if all(values) and len(set(values)) < len(values):
            plan.problems.append(f"{' and '.join(pair)} must differ")
    return plan


def render_plan(label: str, plan: Plan, service: dict[str, Any]) -> str:
    lines = [f"[{label}] {service['service_name']}"]
    lines += [f"  {action:8} {name}" for name, action in plan.actions]
    lines += [f"  PROBLEM  {p}" for p in plan.problems]
    for name in plan.missing:
        entry = next(e for e in service["entries"] if e["name"] == name)
        hint = "add to the secrets file" if entry["kind"] == "secret" and not entry.get("keep_current") else "not set live"
        lines.append(f"  MISSING  {name} ({hint})")
    return "\n".join(lines)


def env_block(env: dict[str, str]) -> str:
    def quote(value: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9_./:@+=-]*", value):
            return value
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

    return "".join(f"{k}={quote(v)}\n" for k, v in env.items())


def to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode(), check=True)


def _services(manifest: dict[str, Any], which: str) -> list[tuple[str, dict[str, Any]]]:
    items = list(manifest["services"].items())
    return items if which == "all" else [(which, manifest["services"][which])]


def _client(factory: Callable[[str], RenderClient] | None) -> RenderClient:
    key = os.environ.get("RENDER_API_KEY")
    if not key:
        raise RenderError("RENDER_API_KEY is not set in this shell")
    return (factory or HttpRenderClient)(key)


def run(
    argv: list[str],
    client_factory: Callable[[str], RenderClient] | None = None,
    out: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(prog="staging_env")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument(
        "--secrets-file",
        type=Path,
        default=Path(os.environ.get("CUADRAO_STAGING_SECRETS_FILE", DEFAULT_SECRETS_FILE)),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "check"):
        sub.add_parser(name).add_argument("service", nargs="?", default="all", choices=["all", "api", "web"])
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("service", nargs="?", default="all", choices=["all", "api", "web"])
    apply_parser.add_argument("--dry-run", action="store_true")
    sub.add_parser("clipboard").add_argument("service", choices=["api", "web"])
    sub.add_parser("show-verify-token")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    file_secrets = read_secrets(args.secrets_file)

    if args.command == "show-verify-token":
        token = file_secrets.get(VERIFY_TOKEN_NAME)
        if token is None:
            api = manifest["services"]["api"]
            if os.environ.get("RENDER_API_KEY"):
                token = _client(client_factory).list_env(api["service_id"]).get(VERIFY_TOKEN_NAME)
            if token is None:
                token = secrets_module.token_urlsafe(48)
                append_secret(args.secrets_file, VERIFY_TOKEN_NAME, token)
                out(f"created {VERIFY_TOKEN_NAME} in the secrets file; run apply to send it to Render")
        to_clipboard(token)
        out("verify token copied to the clipboard; paste it into Meta")
        return 0

    if args.command == "clipboard":
        service = manifest["services"][args.service]
        live: dict[str, str] = {}
        if os.environ.get("RENDER_API_KEY"):
            live = _client(client_factory).list_env(service["service_id"])
        plan = compute_plan(service, live, file_secrets)
        managed = {e["name"] for e in service["entries"]} - set(plan.missing)
        block = {k: v for k, v in plan.final.items() if k in managed}
        for name, value in plan.generated.items():
            append_secret(args.secrets_file, name, value)
        to_clipboard(env_block(block))
        out(f"copied {len(block)} names for {args.service} to the clipboard")
        if plan.missing:
            out("not included (no value available): " + ", ".join(plan.missing))
        return 0

    client = _client(client_factory)
    failed = False
    for label, service in _services(manifest, args.service):
        live = client.list_env(service["service_id"])
        plan = compute_plan(service, live, file_secrets)
        out(render_plan(label, plan, service))
        if args.command == "plan":
            continue
        if args.command == "check":
            failed |= bool(plan.missing)
            continue
        if plan.missing or plan.problems:
            out(f"  not applying {label}: fix the items above first")
            failed = True
            continue
        if client.service_name(service["service_id"]) != service["service_name"]:
            raise RenderError(f"{label}: service id does not match {service['service_name']}; refusing")
        if not plan.changes:
            out(f"  {label}: already matches the manifest")
            continue
        if args.dry_run:
            out(f"  dry run: nothing written to {label}")
            continue
        for name, value in plan.generated.items():
            append_secret(args.secrets_file, name, value)
        client.put_env(service["service_id"], plan.final)
        out(f"  {label}: applied in one update, Render deploys once")
        if service.get("redeploy_note"):
            out(f"  NOTE: {service['redeploy_note']}")
    return 1 if failed else 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except (RenderError, ManifestError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc if not isinstance(exc, subprocess.CalledProcessError) else 'pbcopy failed'}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
