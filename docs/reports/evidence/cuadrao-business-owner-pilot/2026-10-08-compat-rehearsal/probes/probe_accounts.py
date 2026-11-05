"""Account creation idempotency across the B4 drop-and-recreate of
public.create_financial_account. Run from a version worktree, PYTHONPATH=src:.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg_pool import ConnectionPool

HANDOFF = Path(os.environ["COMPAT_HANDOFF"])
DSN = os.environ["ARGUS_DISPOSABLE_DATABASE_URL"]
AS_OF = datetime(2026, 10, 1, tzinfo=timezone.utc)


def out(label: str, value: object) -> None:
    print(f"{label}: {json.dumps(value, default=str)}", flush=True)


def service():
    from argus.domain.recording.postgres_repository import PostgresFinancialAccountRepository
    from argus.domain.recording.service import FinancialAccountService

    pool = ConnectionPool(DSN, min_size=0, max_size=4, open=True)
    return pool, FinancialAccountService(
        PostgresFinancialAccountRepository(pool), lambda: datetime.now(timezone.utc)
    )


def request(nickname: str = "Nomina"):
    from argus.domain.recording.schemas import CreateFinancialAccountRequest

    return CreateFinancialAccountRequest(
        type="checking", currency="DOP", nickname=nickname, amount="1500.00",
        as_of=AS_OF, time_zone="America/Santo_Domingo",
    )


def call(svc, label: str, user: str, key: str, req, **extra) -> None:
    try:
        result = svc.create(user_id=user, idempotency_key=key, request=req, **extra)
        out(label, {
            "account_id": result.stored.account.id,
            "created": result.created,
        })
    except Exception as error:  # every outcome is the evidence
        out(label, {"error": f"{type(error).__name__}: {error}"[:300]})


def signatures() -> None:
    with psycopg.connect(DSN) as conn:
        out("function_signatures", [r[0] for r in conn.execute(
            "select pg_get_function_identity_arguments(p.oid) from pg_proc p"
            " join pg_namespace n on n.oid=p.pronamespace"
            " where n.nspname='public' and p.proname='create_financial_account'"
        )])


def create() -> None:
    signatures()
    user = str(uuid4())
    with psycopg.connect(DSN) as conn:
        conn.execute(
            "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
            (user, f"compat-acct-{user}@example.test"),
        )
    pool, svc = service()
    call(svc, "build2_create_K1_before_B4", user, "compat-K1", request())
    with psycopg.connect(DSN) as conn:
        stored = conn.execute(
            "select identity_hash, account_id::text from public.financial_account_idempotency"
            " where user_id=%s", (user,)
        ).fetchone()
    out("stored_identity_hash_before_B4", stored)
    HANDOFF.write_text(json.dumps({"user": user, "identity_hash": stored[0], "account_id": stored[1]}))
    pool.close()


def replay() -> None:
    signatures()
    state = json.loads(HANDOFF.read_text())
    user = state["user"]
    pool, svc = service()
    scoped = "scope" in inspect.signature(svc.create).parameters
    out("code_takes_scope", scoped)
    tag = os.environ.get("COMPAT_TAG", "x")
    personal = {}
    if scoped:
        from argus.domain.owner_scope import PERSONAL

        personal = {"scope": PERSONAL}
    call(svc, "replay_K1_same_request", user, "compat-K1", request(), **personal)
    call(svc, "replay_K1_changed_request", user, "compat-K1", request("Otro"), **personal)
    call(svc, f"new_key_{tag}", user, f"compat-{tag}-K2", request(), **personal)
    if scoped:
        from argus.domain.business.scope import resolve_business_scope
        from argus.domain.business.spaces import PostgresSpaceStore

        spaces = PostgresSpaceStore(pool)
        if resolve_business_scope(spaces, user) is None:
            spaces.create(user, "Negocio compat")
        business = resolve_business_scope(spaces, user).owner
        call(svc, "replay_K1_from_business_scope", user, "compat-K1", request(), scope=business)
    with psycopg.connect(DSN) as conn:
        out("stored_identity_hash_K1_now", conn.execute(
            "select identity_hash from public.financial_account_idempotency"
            " where user_id=%s and idempotency_key='compat-K1'", (user,)
        ).fetchone()[0] == state["identity_hash"])
        out("accounts_for_user", conn.execute(
            "select count(*), count(*) filter (where owner_space_id is not null)"
            " from public.financial_accounts where user_id=%s", (user,)
        ).fetchone() if "owner_space_id" in [r[0] for r in conn.execute(
            "select column_name from information_schema.columns where table_name='financial_accounts'")] else
            conn.execute("select count(*) from public.financial_accounts where user_id=%s", (user,)).fetchone())
    pool.close()


if __name__ == "__main__":
    {"create": create, "replay": replay}[sys.argv[1]]()
