"""HTTP and database helpers for the flags-off rehearsal. Prints no secrets."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import psycopg

HERE = Path(__file__).parent
API = "http://127.0.0.1:8641/api/v1"
FIXTURES = Path("/Users/garces/Documents/projects/repos/argus-worktrees/business-pilot-spaces/tests/fixtures/whatsapp")
WORLD = HERE / "world.json"


def _env(name: str) -> dict[str, str]:
    return {k: v.strip().strip('"') for k, v in (l.split("=", 1) for l in (HERE / name).read_text().splitlines() if "=" in l)}


STACK, WA = _env("stack.env"), _env("wa.env")
assert STACK["API_URL"] == "http://127.0.0.1:57791" and ":57792/" in STACK["DB_URL"], "argus-biz-flagsoff only"
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(method: str, url: str, *, body=None, raw: bytes | None = None, headers=None, token=None):
    headers = dict(headers or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with NO_PROXY.open(request, timeout=60) as response:
            status, payload, ctype = response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        status, payload, ctype = error.code, error.read(), error.headers.get("Content-Type", "")
    if "json" in ctype:
        try:
            return status, json.loads(payload or b"null")
        except ValueError:
            return status, payload
    return status, payload


def api(method: str, path: str, token=None, **kw):
    return http(method, API + path, token=token, **kw)


def code(result) -> str:
    status, body = result
    return f"{status} {body.get('code', '')}".strip() if isinstance(body, dict) else str(status)


def idem() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


def create_user(label: str) -> dict:
    email = f"flagsoff-{label.lower()}-{secrets.token_hex(3)}@qa.argus.local"
    password = secrets.token_urlsafe(18)
    admin = {"apikey": STACK["SERVICE_ROLE_KEY"], "Authorization": f"Bearer {STACK['SERVICE_ROLE_KEY']}"}
    status, user = http("POST", f"{STACK['API_URL']}/auth/v1/admin/users", headers=admin,
                        body={"email": email, "password": password, "email_confirm": True,
                              "user_metadata": {"display_name": f"Owner {label}", "language": "en"}})
    assert status == 200, (status, user)
    return {"label": label, "id": user["id"], "email": email, "password": password}


def token(person: dict) -> str:
    status, body = http("POST", f"{STACK['API_URL']}/auth/v1/token?grant_type=password",
                        headers={"apikey": STACK["ANON_KEY"]},
                        body={"email": person["email"], "password": person["password"]})
    assert status == 200, status
    return body["access_token"]


def until(fn, seconds: float = 30, every: float = 0.5):
    end = time.time() + seconds
    while True:
        value = fn()
        if value or time.time() > end:
            return value
        time.sleep(every)


def delivery(name: str, phone: str, message: dict) -> bytes:
    body = json.loads((FIXTURES / name).read_text())
    value = body["entry"][0]["changes"][0]["value"]
    value["contacts"][0]["wa_id"] = phone
    value["messages"][0] = {**value["messages"][0], **message, "from": phone, "timestamp": str(int(time.time()))}
    return json.dumps(body).encode()


def webhook(raw: bytes):
    signature = "sha256=" + hmac.new(WA["WA_APP_SECRET"].encode(), raw, hashlib.sha256).hexdigest()
    return http("POST", f"{API}/webhooks/whatsapp", raw=raw,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})


def db():
    return psycopg.connect(STACK["DB_URL"], autocommit=True)


def load_world() -> dict:
    return json.loads(WORLD.read_text()) if WORLD.exists() else {}


def save_world(world: dict) -> None:
    WORLD.write_text(json.dumps(world, indent=1))
