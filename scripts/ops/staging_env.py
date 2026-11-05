"""Render settings for staging and production, from scripts/ops/staging_env_manifest.json.

Staging commands (the two staging services only): plan, apply [--confirm],
check, clipboard api|web, show-verify-token. Their output carries variable
names only, never values, and apply refuses any service whose Render name
differs from the manifest's.

Offline commands, for either environment and any service: print (a paste-ready
KEY=VALUE file, --to-fill for the names you supply, --live-names FILE for the
names to delete) and names (required or allowed names). They never read the
secrets file and never call Render.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets as secrets_module
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

MANIFEST_PATH = Path(__file__).with_name("staging_env_manifest.json")
STAGING_IDS = {"api": "srv-db4mrrvlk1mc73d733j0", "web": "srv-db5ihr7lot8c73f3b3h0"}
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SECRETS_FILE = Path.home() / ".cuadrao" / "staging-secrets.env"
RENDER_API = "https://api.render.com/v1"
VERIFY_TOKEN_NAME = "CUADRAO_WHATSAPP_VERIFY_TOKEN"
KINDS = ("plain", "secret", "generated")
ENVIRONMENTS = ("staging", "production")
PRODUCTION_MODES = ("value", "copy_from", "enter", "not_set")
STAGING_FIELDS = {"value", "keep_current", "copy_from", "optional", "requires", "b64_bytes"}
API_URL_NAMES = ("NEXT_PUBLIC_CUADRAO_API_URL", "NEXT_PUBLIC_ARGUS_API_URL")
API_URL_SHAPE = re.compile(r"https://[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*(:\d+)?/api/v1")
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
            raise RenderError(
                f"{method} {path.split('?')[0]} failed: {type(exc).__name__}"
            ) from None
        if response.status_code >= 400:
            raise RenderError(
                f"{method} {path.split('?')[0]} failed: HTTP {response.status_code}"
            )
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
                key, value = row["envVar"]["key"], row["envVar"].get("value")
                if value is None:
                    raise RenderError(
                        f"{key} has no readable value; refusing to overwrite it"
                    )
                env[key] = value
            if len(rows) < 100:
                return env
            cursor = rows[-1]["cursor"]

    def put_env(self, service_id: str, env: dict[str, str]) -> None:
        body = [{"key": key, "value": value} for key, value in env.items()]
        self._call("PUT", f"/services/{service_id}/env-vars", json=body)


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot load the settings manifest: {type(exc).__name__}") from None
    validate_manifest(manifest)
    return manifest


def staging_services(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        label: service
        for label, service in manifest["services"].items()
        if "service_id" in service
    }


def staging_entries(service: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in service["entries"] if not e.get("production_only")]


def entries_for(service: dict[str, Any], environment: str) -> list[dict[str, Any]]:
    return service["entries"] if environment == "production" else staging_entries(service)


def validate_manifest(manifest: dict[str, Any]) -> None:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("services"), dict):
        raise ManifestError("manifest has no services")
    if set(staging_services(manifest)) != set(STAGING_IDS):
        raise ManifestError(
            "manifest must describe exactly the api and web staging services"
        )
    for label, service in manifest["services"].items():
        _validate_production(label, service)
    for label, service in staging_services(manifest).items():
        if service["service_id"] != STAGING_IDS[label]:
            raise ManifestError(f"{label}: service id is not the pinned staging service")
        entries = {e["name"]: e for e in staging_entries(service)}
        for entry in staging_entries(service):
            if any(r not in entries for r in entry.get("requires", [])):
                raise ManifestError(
                    f"{label}: {entry['name']} requires an entry that is missing"
                )
        names = [e["name"] for e in staging_entries(service)]
        names += [r["name"] for r in service["remove"]] + [
            h["name"] for h in service["hold"]
        ]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ManifestError(f"{label}: duplicate or conflicting names: {duplicates}")
        for entry in staging_entries(service):
            name, kind = entry["name"], entry.get("kind")
            if kind not in KINDS:
                raise ManifestError(f"{label}: {name} has unknown kind")
            if kind != "plain" and "value" in entry:
                raise ManifestError(
                    f"{label}: {name} is {kind} and must not carry a value"
                )
            if kind == "plain":
                modes = [k for k in ("value", "keep_current", "copy_from") if k in entry]
                if len(modes) != 1:
                    raise ManifestError(
                        f"{label}: {name} needs exactly one of value, keep_current, copy_from"
                    )
                if (
                    "value" in entry
                    and name in API_URL_NAMES
                    and not API_URL_SHAPE.fullmatch(str(entry["value"]))
                ):
                    raise ManifestError(
                        f"{label}: {name} must be https://host/api/v1 with no trailing dot"
                    )
                if "value" in entry and (
                    SECRETISH_NAME.search(name)
                    or SECRETISH_VALUE.search(str(entry["value"]))
                ):
                    raise ManifestError(
                        f"{label}: {name} looks like a secret and cannot hold a plain value"
                    )
        for removal in service["remove"]:
            required = removal.get("requires")
            if required and required not in entries:
                raise ManifestError(
                    f"{label}: removal of {removal['name']} requires an entry that is missing"
                )
        for pair in service.get("distinct", []):
            if any(name not in entries for name in pair):
                raise ManifestError(f"{label}: distinct pair names an unknown entry")


def _validate_production(label: str, service: dict[str, Any]) -> None:
    if not service.get("production", {}).get("service_name"):
        raise ManifestError(f"{label}: production service_name is missing")
    names = [e["name"] for e in service["entries"]]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ManifestError(f"{label}: duplicate names: {duplicates}")
    for entry in service["entries"]:
        name, rule = entry["name"], entry.get("production")
        if entry.get("kind") not in KINDS:
            raise ManifestError(f"{label}: {name} has unknown kind")
        if not isinstance(rule, dict):
            raise ManifestError(f"{label}: {name} has no production rule")
        modes = [m for m in PRODUCTION_MODES if m in rule]
        if len(modes) != 1 or set(rule) - {*modes, "optional", "service"}:
            raise ManifestError(
                f"{label}: {name} production rule needs exactly one of "
                + ", ".join(PRODUCTION_MODES)
            )
        mode = modes[0]
        if mode == "not_set" and rule["not_set"] is not True:
            raise ManifestError(f"{label}: {name} not_set must be true")
        if mode != "enter" and "optional" in rule:
            raise ManifestError(f"{label}: {name} only an entered value can be optional")
        if mode != "copy_from" and "service" in rule:
            raise ManifestError(f"{label}: {name} service only qualifies copy_from")
        if mode in ("enter", "copy_from") and not str(rule[mode]).strip():
            raise ManifestError(f"{label}: {name} production {mode} is empty")
        if mode == "value":
            _require_plain_value(label, name, entry["kind"], str(rule["value"]))
        staging_fields = STAGING_FIELDS & set(entry)
        if entry.get("production_only") and staging_fields:
            raise ManifestError(
                f"{label}: {name} is production_only and cannot carry {sorted(staging_fields)}"
            )


def _require_plain_value(label: str, name: str, kind: str, value: str) -> None:
    if (
        kind != "plain"
        or SECRETISH_NAME.search(name)
        or SECRETISH_VALUE.search(value)
    ):
        raise ManifestError(
            f"{label}: {name} looks like a secret and cannot hold a plain value"
        )
    if not value or "\n" in value:
        raise ManifestError(f"{label}: {name} value must be one non-empty line")


Mode = Literal["value", "copy_from", "enter", "not_set"]


@dataclass(frozen=True)
class Rule:
    """What one environment wants for one name, in a single vocabulary."""

    mode: Mode
    text: str = ""  # the value, the copied name, or where an entered value comes from
    optional: bool = False
    source: str | None = None  # the service a copied name lives on, when not this one


def rule_for(
    entry: dict[str, Any], environment: str, service: dict[str, Any]
) -> Rule:
    if environment == "production":
        rule = entry["production"]
        mode: Mode = next(m for m in PRODUCTION_MODES if m in rule)  # type: ignore[assignment]
        if mode == "copy_from":
            return Rule(mode, str(rule["copy_from"]), source=rule.get("service"))
        if mode == "not_set":
            return Rule(mode)
        return Rule(mode, str(rule[mode]), bool(rule.get("optional")))
    name = service["service_name"]
    optional = bool(entry.get("optional"))
    if "value" in entry:
        return Rule("value", str(entry["value"]))
    if "copy_from" in entry:
        return Rule("copy_from", str(entry["copy_from"]))
    if entry.get("keep_current"):
        return Rule("enter", f"keep the live value on {name}", optional)
    if entry["kind"] == "generated":
        return Rule("enter", "generated once into the secrets file by apply", optional)
    return Rule("enter", "the local secrets file", optional)


def _offline_service(
    manifest: dict[str, Any], environment: str, label: str
) -> dict[str, Any]:
    service = manifest["services"].get(label)
    if service is None or (
        environment == "staging" and label not in staging_services(manifest)
    ):
        raise ManifestError(f"{label} has no {environment} service in the manifest")
    return service


def paste_ready(manifest: dict[str, Any], environment: str, label: str) -> str:
    service = _offline_service(manifest, environment, label)
    lines = []
    for entry in entries_for(service, environment):
        rule = rule_for(entry, environment, service)
        if rule.mode != "value":
            continue
        _require_plain_value(label, entry["name"], entry["kind"], rule.text)
        lines.append(f"{entry['name']}={rule.text}")
    return "".join(f"{line}\n" for line in sorted(lines))


def to_fill(manifest: dict[str, Any], environment: str, label: str) -> str:
    service = _offline_service(manifest, environment, label)
    blocks = []
    for entry in sorted(entries_for(service, environment), key=lambda e: e["name"]):
        rule = rule_for(entry, environment, service)
        if rule.mode == "copy_from":
            source = manifest["services"][rule.source or label]
            target = (
                source["production"]["service_name"]
                if environment == "production"
                else source["service_name"]
            )
            where = f"copy the live value of {rule.text} on {target}"
        elif rule.mode == "enter":
            where = rule.text + (" (optional: leave it out when unused)" if rule.optional else "")
        else:
            continue
        blocks.append(f"# {where}\n{entry['name']}=\n")
    return "".join(blocks)


def names(
    manifest: dict[str, Any], environment: str, label: str, which: str
) -> list[str]:
    service = _offline_service(manifest, environment, label)
    rules = [(e["name"], rule_for(e, environment, service)) for e in entries_for(service, environment)]
    if which == "required":
        return sorted(
            n for n, r in rules if r.mode in ("copy_from", "enter") and not r.optional
        )
    return sorted(n for n, r in rules if r.mode != "not_set")


def names_to_delete(
    manifest: dict[str, Any], environment: str, label: str, live: set[str]
) -> tuple[list[str], list[str]]:
    """Live names the manifest does not keep: (delete now, delete after the launch deploy).

    DATABASE_URL and SUPABASE_* names are never listed. A legacy name that a
    kept name copies from waits for the launch deploy, because the copy reads
    it until then.
    """

    service = _offline_service(manifest, environment, label)
    kept = set(names(manifest, environment, label, "allowed"))
    if environment == "staging":
        kept |= {hold["name"] for hold in service["hold"]}
    copied = {
        rule.text
        for entry in entries_for(service, environment)
        if (rule := rule_for(entry, environment, service)).mode == "copy_from"
        and rule.source is None
    }
    extra = sorted(
        n
        for n in live - kept
        if n != "DATABASE_URL" and not n.startswith("SUPABASE_")
    )
    return [n for n in extra if n not in copied], [n for n in extra if n in copied]


def read_live_names(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def read_secrets(path: Path) -> dict[str, str]:
    if REPO_ROOT in path.resolve().parents:
        raise ManifestError("secrets file must live outside the repository")
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
    missing: list[str] = field(
        default_factory=list
    )  # managed names absent after this plan

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
    ordered = sorted(staging_entries(service), key=lambda e: bool(e.get("requires")))
    for entry in ordered:
        name, kind = entry["name"], entry["kind"]
        unmet = [r for r in entry.get("requires", []) if r not in plan.final]
        if unmet:
            plan.problems.append(f"{name} waits for {', '.join(unmet)}")
            plan.actions.append((name, "blocked"))
            continue
        desired: str | None = None
        if kind == "plain" and "value" in entry:
            desired = str(entry["value"])
        elif kind == "plain" and "copy_from" in entry:
            desired = live.get(name) if name in live else live.get(entry["copy_from"])
        elif entry.get("keep_current"):
            desired = live.get(name)
        elif kind == "generated" and name in live:
            desired = live[name]
        elif name in file_secrets:
            desired = file_secrets[name]
        elif name in live:
            desired = live[name]
        elif kind == "generated":
            n = entry.get("b64_bytes")
            desired = plan.generated[name] = (
                base64.urlsafe_b64encode(secrets_module.token_bytes(n)).decode()
                if n
                else generator()
            )
        if desired is None and entry.get("optional"):
            plan.actions.append((name, "skip"))
            continue
        if desired is None:
            plan.missing.append(name)
            plan.actions.append((name, "missing"))
            continue
        action = (
            "add" if name not in live else "update" if live[name] != desired else "ok"
        )
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
    for name in API_URL_NAMES:
        if name in plan.final and not API_URL_SHAPE.fullmatch(plan.final[name]):
            plan.problems.append(
                f"{name} must be https://host/api/v1 with no trailing dot"
            )
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
        hint = (
            "add to the secrets file"
            if entry["kind"] == "secret" and not entry.get("keep_current")
            else "not set live"
        )
        lines.append(f"  MISSING  {name} ({hint})")
    return "\n".join(lines)


def env_block(env: dict[str, str]) -> str:
    def quote(value: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9_./:@+=-]*", value):
            return value
        return (
            '"'
            + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            + '"'
        )

    return "".join(f"{k}={quote(v)}\n" for k, v in env.items())


def to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode(), check=True)


def read_live(client: RenderClient, service: dict[str, Any]) -> dict[str, str]:
    if client.service_name(service["service_id"]) != service["service_name"]:
        raise RenderError(
            f"service id does not match {service['service_name']}; refusing"
        )
    return client.list_env(service["service_id"])


def _services(manifest: dict[str, Any], which: str) -> list[tuple[str, dict[str, Any]]]:
    items = list(staging_services(manifest).items())
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
    parser.add_argument(
        "--secrets-file",
        type=Path,
        default=Path(
            os.environ.get("CUADRAO_STAGING_SECRETS_FILE", DEFAULT_SECRETS_FILE)
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "check"):
        sub.add_parser(name).add_argument(
            "service", nargs="?", default="all", choices=["all", "api", "web"]
        )
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument(
        "service", nargs="?", default="all", choices=["all", "api", "web"]
    )
    apply_parser.add_argument(
        "--confirm",
        action="store_true",
        help="write to Render; without it apply is a dry run",
    )
    sub.add_parser("clipboard").add_argument("service", choices=["api", "web"])
    sub.add_parser("show-verify-token")
    print_parser = sub.add_parser(
        "print", help="paste-ready KEY=VALUE lines; never reads secrets"
    )
    print_parser.add_argument("environment", choices=ENVIRONMENTS)
    print_parser.add_argument("service")
    print_mode = print_parser.add_mutually_exclusive_group()
    print_mode.add_argument(
        "--to-fill",
        action="store_true",
        help="the names you supply, blank, each with where its value comes from",
    )
    print_mode.add_argument(
        "--live-names",
        type=Path,
        help="a file of live names, one per line; prints the names to delete",
    )
    names_parser = sub.add_parser("names", help="required or allowed names")
    names_parser.add_argument("environment", choices=ENVIRONMENTS)
    names_parser.add_argument("service")
    names_parser.add_argument("which", choices=["required", "allowed"])
    args = parser.parse_args(argv)

    manifest = load_manifest()

    if args.command in ("names", "print"):
        if args.command == "names":
            text = "\n".join(names(manifest, args.environment, args.service, args.which))
        elif args.live_names:
            now, later = names_to_delete(
                manifest,
                args.environment,
                args.service,
                read_live_names(args.live_names),
            )
            text = "\n".join(
                ["delete now:", *now, "delete after the launch deploy:", *later]
            )
        elif args.to_fill:
            text = to_fill(manifest, args.environment, args.service).rstrip("\n")
        else:
            text = paste_ready(manifest, args.environment, args.service).rstrip("\n")
        if text:
            out(text)
        return 0

    file_secrets = read_secrets(args.secrets_file)

    if args.command == "show-verify-token":
        token = None
        if os.environ.get("RENDER_API_KEY"):
            api = manifest["services"]["api"]
            token = read_live(_client(client_factory), api).get(VERIFY_TOKEN_NAME)
        token = token or file_secrets.get(VERIFY_TOKEN_NAME)
        if token is None:
            token = secrets_module.token_urlsafe(48)
            append_secret(args.secrets_file, VERIFY_TOKEN_NAME, token)
            out(
                f"created {VERIFY_TOKEN_NAME} in the secrets file; run apply to send it to Render"
            )
        to_clipboard(token)
        out("verify token copied to the clipboard; paste it into Meta")
        return 0

    if args.command == "clipboard":
        service = manifest["services"][args.service]
        live: dict[str, str] = {}
        if os.environ.get("RENDER_API_KEY"):
            live = read_live(_client(client_factory), service)
        plan = compute_plan(service, live, file_secrets)
        managed = {e["name"] for e in staging_entries(service)} - set(plan.missing)
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
        live = read_live(client, service)
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
        if not plan.changes:
            out(f"  {label}: already matches the manifest")
            continue
        if not args.confirm:
            out(f"  dry run: nothing written to {label}; add --confirm to apply")
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
        print(
            f"error: {exc if not isinstance(exc, subprocess.CalledProcessError) else 'pbcopy failed'}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
