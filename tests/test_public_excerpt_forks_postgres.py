"""Independent connections exercise fork admission and canonical guest RPCs."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from argus.domain.postgres_public_excerpt_forks import fork_public_excerpt
from argus.domain.public_excerpt_forks import ForkError
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="isolated PostgreSQL required")


@pytest.fixture
def seeded():
    with ConnectionPool(DSN, min_size=1, max_size=5) as pool:
        owner, receiver, guest = [str(uuid4()) for _ in range(3)]
        source, message, snapshot = [str(uuid4()) for _ in range(3)]
        public_id = uuid4().hex + uuid4().hex[:8]
        with pool.connection() as c:
            for user_id in (owner, receiver, guest):
                email = f"{user_id}@example.test"
                c.execute(
                    "insert into auth.users(id,email,is_anonymous) values (%s,%s,%s)",
                    (user_id, email, user_id == guest),
                )
                c.execute(
                    "insert into public.profiles(id,email,username) values (%s,%s,%s)",
                    (user_id, None if user_id == guest else email, user_id),
                )
            c.execute(
                "insert into public.guest_workspaces(user_id,status,expires_at) values (%s,'active',now()+interval '1 day')",
                (guest,),
            )
            c.execute(
                "insert into public.conversations(id,user_id,title) values (%s,%s,'Owner')",
                (source, owner),
            )
            c.execute(
                "insert into public.messages(id,user_id,conversation_id,role,content) values (%s,%s,%s,'assistant','Snapshot answer')",
                (message, owner, source),
            )
            payload = {
                "schema_version": 2,
                "kind": "turns",
                "turns": [
                    {
                        "kind": "answer",
                        "question": "Original question",
                        "answer": "Snapshot answer",
                        "owner_note": "Do not carry me",
                    }
                ],
            }
            c.execute(
                """insert into public.public_excerpt_snapshots(id,public_id,owner_id,source_conversation_id,source_message_ids,selection_key,kind,title,payload,payload_digest)
                values (%s,%s,%s,%s,%s,%s,'answer','Frozen',%s,%s)""",
                (
                    snapshot,
                    public_id,
                    owner,
                    source,
                    [message],
                    uuid4().hex * 2,
                    Jsonb(payload),
                    "a" * 64,
                ),
            )
        yield (
            pool,
            {
                "owner": owner,
                "receiver": receiver,
                "guest": guest,
                "source": source,
                "snapshot": snapshot,
                "public_id": public_id,
            },
        )
        with pool.connection() as c:
            c.execute(
                "delete from auth.users where id=any(%s::uuid[])",
                ([owner, receiver, guest],),
            )


def fork(pool, data, *, guest=False, request_id=None, replacement=None):
    return fork_public_excerpt(
        pool,
        user_id=data["guest" if guest else "receiver"],
        public_id=data["public_id"],
        request_id=request_id or str(uuid4()),
        language="en",
        guest=guest,
        replace_guest_conversation_id=replacement,
    )


def test_concurrent_retries_create_one_receiver_owned_copy(seeded):
    pool, data = seeded
    request_id = str(uuid4())
    barrier = Barrier(2)

    def attempt():
        barrier.wait()
        return fork(pool, data, request_id=request_id)

    with ThreadPoolExecutor(2) as workers:
        results = list(workers.map(lambda _: attempt(), range(2)))
    assert len({chat.id for chat, _ in results}) == 1
    assert sorted(created for _, created in results) == [False, True]
    with pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from public.messages where user_id=%s",
                (data["receiver"],),
            ).fetchone()[0]
            == 2
        )
        c.execute(
            "update public.public_excerpt_snapshots set revoked_at=now(),revocation_reason='owner_revoked' where id=%s",
            (data["snapshot"],),
        )
    assert fork(pool, data, request_id=request_id)[1] is False
    with pytest.raises(ForkError, match="receipt_unavailable"):
        fork(pool, data)


def test_guest_choice_is_explicit_stale_safe_and_preserves_workspace_expiry(seeded):
    pool, data = seeded
    chat, _ = fork(pool, data, guest=True)
    with pool.connection() as c:
        expiry = c.execute(
            "select expires_at from public.guest_workspaces where user_id=%s",
            (data["guest"],),
        ).fetchone()[0]
    with pytest.raises(ForkError, match="receipt_guest_choice_required"):
        fork(pool, data, guest=True)
    with pytest.raises(ForkError, match="receipt_guest_choice_stale"):
        fork(pool, data, guest=True, replacement=str(uuid4()))
    new, _ = fork(pool, data, guest=True, replacement=chat.id)
    assert new.id != chat.id
    with pool.connection() as c:
        row = c.execute(
            "select conversation_id,expires_at from public.guest_workspaces where user_id=%s",
            (data["guest"],),
        ).fetchone()
        assert str(row[0]) == new.id and row[1] == expiry
        assert (
            c.execute(
                "select count(*) from public.conversations where user_id=%s",
                (data["guest"],),
            ).fetchone()[0]
            == 1
        )


@pytest.mark.parametrize("deletion", ["soft", "hard"])
def test_deleted_source_refuses_new_fork_and_preserves_created_copy(seeded, deletion):
    pool, data = seeded
    chat, _ = fork(pool, data)
    with pool.connection() as c:
        c.execute(
            "update public.conversations set deleted_at=now() where id=%s"
            if deletion == "soft"
            else "delete from public.conversations where id=%s",
            (data["source"],),
        )
    with pytest.raises(ForkError, match="receipt_unavailable"):
        fork(pool, data)
    with pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from public.messages where conversation_id=%s",
                (chat.id,),
            ).fetchone()[0]
            == 2
        )


def test_imports_charge_no_usage_or_runs_and_cannot_be_memory_sources(seeded):
    from uuid import UUID

    from argus.memory.contracts import MemorySourceKind
    from argus.memory.postgres_store import PostgresCanonicalMemoryStore

    pool, data = seeded
    chat, _ = fork(pool, data, guest=True)
    with pool.connection() as c:
        for table in (
            "usage_counters",
            "backtest_runs",
            "backtest_jobs",
            "evidence_artifacts",
            "decision_notes",
        ):
            assert (
                c.execute(
                    f"select count(*) from public.{table} where user_id=%s",
                    (data["guest"],),
                ).fetchone()[0]
                == 0
            )
        message_ids = c.execute(
            "select id from public.messages where conversation_id=%s", (chat.id,)
        ).fetchall()
        for (message_id,) in message_ids:
            assert not PostgresCanonicalMemoryStore._source_is_owned(
                c.cursor(), UUID(data["guest"]), MemorySourceKind.MESSAGE, message_id
            )


def test_signup_handoff_retains_forked_messages_and_read_only_provenance(seeded):
    import hashlib

    from tests.test_guest_handoff_postgres import _claim_by_email, _prepare_signup_handoff

    pool, data = seeded
    request_id = str(uuid4())
    chat, _ = fork(pool, data, guest=True, request_id=request_id)
    secret_hash = hashlib.sha256(uuid4().bytes).hexdigest()
    email = f"{data['receiver']}@example.test"
    with pool.connection() as c:
        before = c.execute(
            "select id,content,metadata from public.messages where conversation_id=%s order by created_at,id",
            (chat.id,),
        ).fetchall()
        c.execute("delete from auth.users where id=%s", (data["receiver"],))
        prepared = _prepare_signup_handoff(
            c,
            {"source": data["guest"], "conversation": chat.id},
            email=email,
            secret_hash=secret_hash,
        )
        c.execute(
            "insert into auth.users(id,email,is_anonymous,raw_user_meta_data) values (%s,%s,false,%s)",
            (
                data["receiver"],
                email,
                Jsonb(
                    {
                        "argus_guest_signup": {
                            "handoff_id": prepared[0],
                            "proof": secret_hash,
                        }
                    }
                ),
            ),
        )
        c.execute(
            "insert into public.profiles(id,email) values (%s,%s)",
            (data["receiver"], email),
        )
        claimed = _claim_by_email(
            c,
            {
                "handoff": prepared[0],
                "secret_hash": secret_hash,
                "destination": data["receiver"],
            },
        )
        assert claimed[2] == chat.id
        after = c.execute(
            "select id,content,metadata from public.messages where conversation_id=%s and user_id=%s order by created_at,id",
            (chat.id, data["receiver"]),
        ).fetchall()
        assert after == before
        assert (
            c.execute(
                "select count(*) from public.messages where user_id=%s", (data["guest"],)
            ).fetchone()[0]
            == 0
        )

    # The existing signup RPC moves ownership without rewriting message IDs.
    # Retrying that same browser request must find the transferred copy.
    replay, created = fork(pool, data, request_id=request_id)
    assert replay.id == chat.id
    assert not created
    with pool.connection() as c:
        assert (
            c.execute(
                "select count(*) from public.conversations where user_id=%s",
                (data["receiver"],),
            ).fetchone()[0]
            == 1
        )
    with pytest.raises(ForkError, match="receipt_request_conflict"):
        fork(pool, {**data, "public_id": uuid4().hex}, request_id=request_id)


def test_same_request_id_is_isolated_between_current_owners(seeded):
    pool, data = seeded
    request_id = str(uuid4())
    guest_chat, _ = fork(pool, data, guest=True, request_id=request_id)
    account_chat, created = fork(pool, data, request_id=request_id)
    assert created
    assert guest_chat.id != account_chat.id
    assert fork(pool, data, guest=True, request_id=request_id)[0].id == guest_chat.id
    assert fork(pool, data, request_id=request_id)[0].id == account_chat.id
