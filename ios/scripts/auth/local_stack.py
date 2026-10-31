"""Lane-owned synthetic stack setup. Does not read a hosted .env or print credentials."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import urllib.request

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 backend environments.
    import tomli as tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Allocation:
    """One loopback allocation owns its project, ports and ignored state."""

    accounts: bool = False
    port_base: int = 58400

    def __post_init__(self):
        if not 1024 <= self.port_base <= 65524:
            raise ValueError("Port base must leave twelve unprivileged ports available")

    @property
    def suffix(self) -> str:
        return "" if self.port_base == 58400 else f"-{self.port_base}"

    @property
    def work(self) -> Path:
        return (
            ROOT
            / "ios/.build"
            / (("accounts-local" if self.accounts else "auth-local") + self.suffix)
        )

    @property
    def stack(self) -> Path:
        return self.work / "stack"

    @property
    def project(self) -> str:
        return ("ios-accounts" if self.accounts else "ios-auth-8be2") + self.suffix

    @property
    def ports(self) -> dict[tuple[str, str], int]:
        return {
            key: self.port_base + offset
            for key, offset in {
                ("api", "port"): 1,
                ("db", "port"): 2,
                ("local_smtp", "port"): 3,
                ("local_smtp", "smtp_port"): 4,
                ("db", "shadow_port"): 7,
                ("studio", "port"): 8,
                ("db.pooler", "port"): 9,
                ("analytics", "port"): 10,
                ("edge_runtime", "inspector_port"): 11,
            }.items()
        }

    def url(self, offset: int = 0) -> str:
        return f"http://127.0.0.1:{self.port_base + offset}"

    @property
    def web_port(self) -> int:
        return 3001 if self.port_base == 58400 else self.port_base + 6

    @property
    def web_url(self) -> str:
        return f"http://127.0.0.1:{self.web_port}"

    def verify(self) -> None:
        config = tomllib.loads((self.stack / "supabase/config.toml").read_text())
        if config.get("project_id") != self.project:
            raise SystemExit("Stack ownership mismatch")
        for (section, key), port in self.ports.items():
            entry = config
            for part in section.split("."):
                entry = entry.get(part, {})
            if entry.get(key) != port:
                raise SystemExit("Stack port allocation mismatch")


ALLOCATION = Allocation()
EXCLUDE = "vector,edge-runtime,imgproxy,studio,logflare,realtime,storage-api,postgres-meta,supavisor"


def sb(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    ALLOCATION.verify()
    return subprocess.run(
        ["supabase", *args, "--workdir", str(ALLOCATION.stack)],
        check=True,
        capture_output=capture,
        text=True,
    )


def configure(*, accounts: bool = False) -> None:
    if (ALLOCATION.stack / "supabase/config.toml").exists():
        raise SystemExit("Configuration exists. Reuse it; do not reset an active stack.")
    for port in [
        ALLOCATION.port_base,
        ALLOCATION.port_base + 5,
        *([] if accounts else [ALLOCATION.web_port]),
        *ALLOCATION.ports.values(),
    ]:
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                raise SystemExit(
                    f"Port {port} is occupied. Coordinate a new allocation; stop nothing."
                ) from None
    target = ALLOCATION.stack / "supabase"
    target.mkdir(parents=True, mode=0o700)
    shutil.copytree(ROOT / "supabase/migrations", target / "migrations")
    shutil.copy2(ROOT / "supabase/seed.sql", target / "seed.sql")
    section = ""
    lines = []
    redirects = False
    for line in (ROOT / "supabase/config.toml").read_text().splitlines():
        if redirects:
            if line.strip() == "]":
                redirects = False
            continue
        match = re.match(r"^\[([^\]]+)\]", line)
        if match:
            section = match[1]
        key = re.match(r"^(\w+)\s*=", line)
        if key:
            name = key[1]
            if not section and name == "project_id":
                line = f'project_id = "{ALLOCATION.project}"'
            elif (section, name) in ALLOCATION.ports:
                line = f"{name} = {ALLOCATION.ports[section,name]}"
            elif section == "auth" and name == "site_url":
                line = f'site_url = "{ALLOCATION.web_url}"'
            elif section == "auth" and name == "additional_redirect_urls":
                line = (
                    f'additional_redirect_urls = ["{ALLOCATION.web_url}/auth/recovery"]'
                )
                redirects = True
            elif section == "auth" and name == "jwt_expiry":
                line = "jwt_expiry = 60"
            elif section == "auth.email" and name == "enable_confirmations":
                line = "enable_confirmations = true"
        if section == "local_smtp" and line.strip().startswith("# smtp_port ="):
            line = f"smtp_port = {ALLOCATION.port_base + 4}"
        lines.append(line)
    # Public Cloudflare always-pass test secret; local container only.
    lines += [
        "",
        "[auth.captcha]",
        "enabled = true",
        'provider = "turnstile"',
        'secret = "1x0000000000000000000000000000000AA"',
    ]
    (target / "config.toml").write_text("\n".join(lines) + "\n")
    print(
        f"Configured isolated {ALLOCATION.project} stack, ports {ALLOCATION.port_base + 1}-{ALLOCATION.port_base + 11}."
    )


def status() -> dict:
    result = json.loads(sb("status", "-o", "json").stdout)
    if result["API_URL"] != ALLOCATION.url(1):
        raise SystemExit("Refusing non-lane Supabase endpoint")
    database = urlsplit(result["DB_URL"])
    if database.hostname != "127.0.0.1" or database.port != ALLOCATION.port_base + 2:
        raise SystemExit("Refusing non-lane database endpoint")
    return result


def seed(*, user_count: int = 2) -> None:
    if user_count not in (2, 3):
        raise ValueError(
            "Synthetic fixtures support two members and an optional third identity"
        )
    cfg = status()
    path = ALLOCATION.work / "client.json"
    if path.exists():
        raise SystemExit(
            "Synthetic client fixture already exists; reuse, do not mint accounts repeatedly."
        )
    users = []
    for label in ("a", "b", "c")[:user_count]:
        email = f"ios-{label}-{secrets.token_hex(5)}@example.test"
        password = secrets.token_urlsafe(24)
        data = json.dumps(
            {"email": email, "password": password, "email_confirm": True}
        ).encode()
        req = urllib.request.Request(
            cfg["API_URL"] + "/auth/v1/admin/users",
            data=data,
            headers={
                "apikey": cfg["SERVICE_ROLE_KEY"],
                "Authorization": "Bearer " + cfg["SERVICE_ROLE_KEY"],
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req) as response:
            user = json.load(response)
        users.append({"email": email, "password": password, "id": user["id"]})
    fixture = {
        "apiURL": ALLOCATION.url() + "/api/v1",
        "supabaseURL": cfg["API_URL"],
        "publicAnonKey": cfg["ANON_KEY"],
        "users": users,
    }
    path.write_text(json.dumps(fixture))
    path.chmod(0o600)

    # xcconfig treats // as a comment; use its empty-variable escape.
    def url(value: str) -> str:
        return value.replace("://", ":/$()/")

    config = ROOT / "ios/Config/Local.xcconfig"
    if config.exists():
        raise SystemExit(
            "Local.xcconfig exists; synthetic fixture saved, leaving config untouched."
        )
    config.write_text(
        "\n".join(
            [
                "// Ignored local synthetic stack; public configuration only.",
                "ARGUS_AUTH_ENABLED = true",
                "ARGUS_API_URL = " + url(ALLOCATION.url()),
                "ARGUS_SUPABASE_URL = " + url(cfg["API_URL"]),
                "ARGUS_SUPABASE_ANON_KEY = " + cfg["ANON_KEY"],
                "ARGUS_WEB_URL = " + url(ALLOCATION.web_url),
                "ARGUS_CAPTCHA_URL = " + url(ALLOCATION.url(5) + "/captcha.html"),
            ]
        )
        + "\n"
    )
    print(
        f"Created {user_count} synthetic users and ignored client fixture/config. No secrets printed."
    )


def api(
    python: str,
    *,
    accounts_enabled: bool = False,
    api_port: int | None = None,
    households_enabled: bool = False,
) -> None:
    port = ALLOCATION.port_base if api_port is None else api_port
    if not 58400 <= port <= 59900 or 58700 <= port <= 58749:
        raise SystemExit("Refusing API port outside the owned local test range")
    if port in {
        *ALLOCATION.ports.values(),
        ALLOCATION.port_base + 5,
        ALLOCATION.web_port,
    }:
        raise SystemExit("Refusing an API port reserved by this stack allocation")
    if accounts_enabled and not ALLOCATION.accounts:
        raise SystemExit("Financial accounts require --accounts isolation")
    if households_enabled and not (ALLOCATION.accounts and accounts_enabled):
        raise SystemExit("Households require --accounts and --accounts-enabled on")
    cfg = status()
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(
            x in key
            for x in (
                "TOKEN",
                "SECRET",
                "API_KEY",
                "SUPABASE",
                "DATABASE",
                "ARGUS_",
                "SENTRY",
                "POSTHOG",
            )
        )
    }
    env.update(
        {
            "PYTHONPATH": str(ROOT / "src") + ":" + str(ROOT / "web"),
            "SUPABASE_PROJECT_URL": cfg["API_URL"],
            "SUPABASE_URL": cfg["API_URL"],
            "SUPABASE_ANON_PUBLIC_KEY": cfg["ANON_KEY"],
            "SUPABASE_ANON_KEY": cfg["ANON_KEY"],
            "SUPABASE_SERVICE_ROLE_KEY": cfg["SERVICE_ROLE_KEY"],
            "SUPABASE_JWT_SECRET": cfg["JWT_SECRET"],
            "SUPABASE_POSTGRES_SESSION_POOLER_URL": cfg["DB_URL"],
            "DATABASE_URL": cfg["DB_URL"],
            "CUADRAO_PERSISTENCE_MODE": "supabase",
            "ARGUS_FINANCIAL_ACCOUNTS_ENABLED": str(accounts_enabled).lower(),
            "CUADRAO_HOUSEHOLDS_ENABLED": str(households_enabled).lower(),
            "ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture",
            "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
            "CUADRAO_GUEST_ACCESS_ENABLED": "true",
            "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
            "CUADRAO_MOCK_AUTH": "false",
            "NEXT_PUBLIC_MOCK_AUTH": "false",
            "ARGUS_APP_ORIGIN": ALLOCATION.web_url,
        }
    )
    for key in (
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "RESEND_API_KEY",
        "PERPLEXITY_API_KEY",
        "EXA_API_KEY",
        "POSTHOG_API_KEY",
        "SENTRY_DSN",
    ):
        env[key] = ""
    # No .env in this checkout; explicit env is the only local runtime source.
    if (ROOT / ".env").exists():
        raise SystemExit(
            "Refusing a checkout with a root .env; isolate runtime configuration first."
        )
    os.chdir(ROOT)
    os.execve(
        python,
        [
            python,
            "-m",
            "uvicorn",
            "argus.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        env,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["configure", "start", "seed", "api", "web", "stop"]
    )
    parser.add_argument(
        "--python", help="Absolute path to a dependency-complete Python runtime"
    )
    parser.add_argument(
        "--accounts",
        action="store_true",
        help="Use isolated ios-accounts stack/state; does not reserve web port",
    )
    parser.add_argument(
        "--accounts-enabled",
        choices=["on", "off"],
        default="off",
        help="Explicit local API financial-record exposure (default off)",
    )
    parser.add_argument("--port-base", type=int, default=58400)
    parser.add_argument(
        "--user-count",
        type=int,
        choices=[2, 3],
        default=2,
        help="Number of synthetic identities created by seed (default two)",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        help="Local API listen port; reuse the verified allocation Auth and database",
    )
    parser.add_argument(
        "--households-enabled",
        choices=["on", "off"],
        default="off",
        help="Explicit local API Household exposure (default off; requires accounts)",
    )
    args = parser.parse_args()
    ALLOCATION = Allocation(args.accounts, args.port_base)
    if args.action != "api" and (
        args.api_port is not None or args.households_enabled == "on"
    ):
        raise SystemExit("--api-port and --households-enabled on apply only to api")
    if not args.accounts and args.accounts_enabled == "on":
        raise SystemExit("Financial accounts require --accounts isolation")
    ALLOCATION.work.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.action == "configure":
        configure(accounts=args.accounts)
    elif args.action == "start":
        ALLOCATION.verify()
        with (ALLOCATION.work / "supabase-start.log").open("w") as log:
            subprocess.run(
                ["supabase", "start", "-x", EXCLUDE, "--workdir", str(ALLOCATION.stack)],
                stdout=log,
                stderr=log,
                check=True,
            )
        print("Lane Supabase started. Detailed output is ignored local evidence.")
    elif args.action == "seed":
        seed(user_count=args.user_count)
    elif args.action == "api":
        if not args.python or not Path(args.python).is_absolute():
            raise SystemExit("--python must be an absolute interpreter path")
        api(
            args.python,
            accounts_enabled=args.accounts_enabled == "on",
            api_port=args.api_port,
            households_enabled=args.households_enabled == "on",
        )
    elif args.action == "web":
        if args.accounts:
            raise SystemExit("Web port is not allocated to the accounts lane")
        cfg = status()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", ALLOCATION.web_port))
        env = dict(os.environ)
        env.update(
            {
                "NEXT_PUBLIC_SUPABASE_URL": cfg["API_URL"],
                "NEXT_PUBLIC_SUPABASE_ANON_KEY": cfg["ANON_KEY"],
                "NEXT_PUBLIC_ARGUS_API_URL": ALLOCATION.url() + "/api/v1",
                "ARGUS_APP_ORIGIN": ALLOCATION.web_url,
                "NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY": "1x00000000000000000000AA",
                "NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN": "",
                "NEXT_PUBLIC_MOCK_AUTH": "false",
                "NEXT_PUBLIC_MOCK_API": "false",
                "NEXT_PUBLIC_GUEST_ACCESS_ENABLED": "true",
                "NEXT_DIST_DIR": ".next-ios-auth",
            }
        )
        if (ROOT / "web/.env.local").exists():
            raise SystemExit("Refusing preexisting web .env.local")
        os.chdir(ROOT / "web")
        binary = shutil.which("bun")
        os.execve(
            binary,
            [
                binary,
                "run",
                "dev",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(ALLOCATION.web_port),
            ],
            env,
        )
    elif args.action == "stop":
        sb("stop")
        print(f"Stopped only {ALLOCATION.project}; local data retained.")
