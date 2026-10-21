"""Document compatibility probe through the real API, Auth, Postgres and Storage.

Run from a code-version worktree with PYTHONPATH=src:. so the app under test is
that version's. Subcommands: cycle, seed, read. Handoff state lives in a JSON
file in the scratchpad; it holds only disposable local test identities.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import psycopg

HANDOFF = Path(os.environ["COMPAT_HANDOFF"])
DSN = os.environ["ARGUS_DISPOSABLE_DATABASE_URL"]
ORIGIN = {"origin": "http://localhost:3000"}
DOCS = "/api/v1/financial-documents"
BUCKET = "financial-document-sources"
FLAGS = {
    "ARGUS_FINANCIAL_ACCOUNTS_ENABLED": "true",
    "ARGUS_INGESTION_ENABLED": "true",
    "ARGUS_DOCUMENT_EXTRACTION_ENABLED": "true",
    "ARGUS_GUEST_ACCESS_ENABLED": "true",
    "NEXT_PUBLIC_GUEST_ACCESS_ENABLED": "true",
    "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
    "NEXT_PUBLIC_MOCK_AUTH": "false",
    "ARGUS_MOCK_AUTH": "false",
    "APP_ENV": "local",
    "ARGUS_ACCOUNT_DELETION_ENABLED": "true",
}


def out(label: str, value: object) -> None:
    print(f"{label}: {json.dumps(value, default=str)}", flush=True)


@contextmanager
def client():
    from argus.api import state as api_state
    from argus.api.main import app
    from argus.api.routers import auth as auth_router
    from fastapi.testclient import TestClient

    from tests.local_supabase_support import local_supabase_gateway

    os.environ.update(FLAGS)
    auth_router.reset_auth_attempt_limiter_for_tests()
    gateway = local_supabase_gateway()
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch.object(api_state, "DATABASE_URL", DSN),
        patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
        TestClient(app, base_url="http://localhost:3000") as c,
    ):
        yield c, gateway


def register(gateway, label: str) -> dict[str, str]:
    email = f"compat-{label}-{secrets.token_hex(4)}@example.test"
    password = f"Pw-{secrets.token_urlsafe(18)}"
    user = gateway.client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    return {"email": email, "password": password, "id": str(user.user.id)}


def login(c, who: dict[str, str]) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={
            "email": who["email"],
            "password": who["password"],
            "captcha_token": "local-captcha-proof",
        },
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session']['access_token']}"}


def upload(c, auth, content: bytes, name: str):
    return c.post(
        DOCS,
        content=content,
        headers={
            **auth,
            "Content-Type": "image/png",
            "X-Document-Filename": name,
        },
    )


def row(connection_id: str) -> dict | None:
    with psycopg.connect(DSN) as conn:
        cols = [
            r[0]
            for r in conn.execute(
                "select column_name from information_schema.columns where "
                "table_schema='public' and table_name='financial_document_extractions'"
            )
        ]
        want = [c for c in ("source_path", "preparation_job") if c in cols]
        got = conn.execute(
            "select octet_length(source_bytes)"
            + "".join(f", {c}" for c in want)
            + " from public.financial_document_extractions where connection_id=%s",
            (connection_id,),
        ).fetchone()
    if got is None:
        return None
    return {"source_bytes_len": got[0], **dict(zip(want, got[1:]))}


def objects(prefix: str) -> list[str]:
    with psycopg.connect(DSN) as conn:
        exists = conn.execute(
            "select exists(select 1 from storage.buckets where id=%s)", (BUCKET,)
        ).fetchone()[0]
        if not exists:
            return ["<bucket absent>"]
        return [
            n
            for (n,) in conn.execute(
                "select name from storage.objects where bucket_id=%s and "
                "starts_with(name,%s) order by name",
                (BUCKET, prefix),
            )
        ]


def auth_user_exists(user_id: str) -> bool:
    with psycopg.connect(DSN) as conn:
        return conn.execute(
            "select exists(select 1 from auth.users where id=%s)", (user_id,)
        ).fetchone()[0]


def png(tag: str) -> bytes:
    base = (Path("tests/document_extraction_fixtures/receipt-dop.png")).read_bytes()
    return base + tag.encode()


def brief(r) -> dict:
    try:
        body = r.json()
    except ValueError:
        body = {"bytes": len(r.content)}
    if isinstance(body, dict):
        body = {k: body[k] for k in ("code", "status", "replayed", "connection_id", "items", "bytes", "source_available", "pending") if k in body}
        if "items" in body:
            body["items"] = [
                {k: i.get(k) for k in ("connection_id", "status", "source_available")}
                for i in body["items"]
            ]
    return {"http": r.status_code, **(body if isinstance(body, dict) else {})}


def cycle() -> None:
    with client() as (c, gateway):
        who = register(gateway, "cycle")
        auth = login(c, who)
        content = png("cycle")
        up = upload(c, auth, content, "cycle.png")
        out("upload", brief(up))
        cid = up.json()["connection_id"]
        out("row_after_upload", row(cid))
        out("objects_after_upload", objects(f"{who['id']}/"))
        out("list", brief(c.get(DOCS, headers=auth)))
        out("get", brief(c.get(f"{DOCS}/{cid}", headers=auth)))
        src = c.get(f"{DOCS}/{cid}/source", headers=auth)
        out("source", {**brief(src), "bytes_match": src.content == content})
        replay = upload(c, auth, content, "cycle.png")
        out("replay_upload", brief(replay))
        disc = c.post(f"/api/v1/financial-connections/{cid}/disconnect", headers=auth)
        out("disconnect", {"http": disc.status_code})
        out("row_after_disconnect", row(cid))
        out("objects_after_disconnect", objects(f"{who['id']}/"))
        out("list_after_disconnect", brief(c.get(DOCS, headers=auth)))
        gone = c.post("/api/v1/account/delete", json={"confirm": True}, headers=auth)
        out("account_delete", brief(gone))
        out("auth_user_exists_after_delete", auth_user_exists(who["id"]))
        out("objects_after_account_delete", objects(f"{who['id']}/"))


def seed() -> None:
    with client() as (c, gateway):
        u, v = register(gateway, "keep"), register(gateway, "erase")
        state = {"u": u, "v": v, "docs": {}}
        auth = login(c, u)
        for tag in ("a", "b"):
            content = png(f"seed-{tag}")
            r = upload(c, auth, content, f"seed-{tag}.png")
            out(f"seed_upload_{tag}", brief(r))
            cid = r.json()["connection_id"]
            state["docs"][tag] = cid
            out(f"seed_row_{tag}", row(cid))
        vauth = login(c, v)
        r = upload(c, vauth, png("seed-v"), "seed-v.png")
        out("seed_upload_v", brief(r))
        state["docs"]["v"] = r.json()["connection_id"]
        out("seed_objects_u", objects(f"{u['id']}/"))
        out("seed_objects_v", objects(f"{v['id']}/"))
        HANDOFF.write_text(json.dumps(state))


def read() -> None:
    state = json.loads(HANDOFF.read_text())
    u, v, docs = state["u"], state["v"], state["docs"]
    with client() as (c, _):
        auth = login(c, u)
        out("list", brief(c.get(DOCS, headers=auth)))
        a = docs["a"]
        out("get_a", brief(c.get(f"{DOCS}/{a}", headers=auth)))
        out("source_a", brief(c.get(f"{DOCS}/{a}/source", headers=auth)))
        out("row_a", row(a))
        out("replay_upload_a", brief(upload(c, auth, png("seed-a"), "seed-a.png")))
        out("row_a_after_replay", row(a))
        b = docs["b"]
        disc = c.post(f"/api/v1/financial-connections/{b}/disconnect", headers=auth)
        out("disconnect_b", {"http": disc.status_code})
        out("row_b_after_disconnect", row(b))
        out("objects_u_after_disconnect_b", objects(f"{u['id']}/"))
        vauth = login(c, v)
        gone = c.post("/api/v1/account/delete", json={"confirm": True}, headers=vauth)
        out("account_delete_v", brief(gone))
        out("auth_user_v_exists", auth_user_exists(v["id"]))
        out("objects_v_after_account_delete", objects(f"{v['id']}/"))


if __name__ == "__main__":
    {"cycle": cycle, "seed": seed, "read": read}[sys.argv[1]]()
