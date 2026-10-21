"""A running Build 2 process keeps creating and replaying accounts while B4
is applied underneath it. One pool for the whole run, so psycopg's prepared
statements (prepare_threshold 5) are live when the function is dropped."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
from psycopg_pool import ConnectionPool

from argus.domain.recording.postgres_repository import PostgresFinancialAccountRepository
from argus.domain.recording.schemas import CreateFinancialAccountRequest
from argus.domain.recording.service import FinancialAccountService

DSN = os.environ["ARGUS_DISPOSABLE_DATABASE_URL"]
SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 60


def signature() -> int:
    with psycopg.connect(DSN) as conn:
        return conn.execute(
            "select pronargs from pg_proc where proname='create_financial_account'"
        ).fetchone()[0]


user = str(uuid4())
with psycopg.connect(DSN) as conn:
    conn.execute(
        "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
        (user, f"compat-live-{user}@example.test"),
    )
pool = ConnectionPool(DSN, min_size=1, max_size=1, open=True)
service = FinancialAccountService(
    PostgresFinancialAccountRepository(pool), lambda: datetime.now(timezone.utc)
)
request = CreateFinancialAccountRequest(type="cash", currency="DOP", nickname="Live", amount="10.00")
first = service.create(user_id=user, idempotency_key="live-K1", request=request)
deadline, n, outcomes = time.time() + SECONDS, 0, {}
while time.time() < deadline:
    n += 1
    args = signature()
    for kind, key in (("replay_K1", "live-K1"), ("create_new", f"live-{n}")):
        try:
            result = service.create(user_id=user, idempotency_key=key, request=request)
            ok = (result.stored.account.id == first.stored.account.id) if kind == "replay_K1" else result.created
            label = f"{kind}:args={args}:{'ok' if ok else 'unexpected'}"
        except Exception as error:  # every outcome is the evidence
            label = f"{kind}:args={args}:{type(error).__name__}"
        outcomes[label] = outcomes.get(label, 0) + 1
    time.sleep(0.2)
with pool.connection() as conn:
    prepared = conn.execute(
        "select count(*) from pg_prepared_statements where statement ilike '%create_financial_account%'"
    ).fetchone()[0]
print(json.dumps({"iterations": n, "outcomes": outcomes, "prepared_statements_on_pool_connection": prepared}, indent=1))
pool.close()
