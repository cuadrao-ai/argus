"""Seven-day pending expiry and explicit renewal on an isolated Postgres database."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.spaces import PostgresSpaceStore
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared

users = shared.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")
MIGRATION = (
    Path(__file__).parents[1]
    / "supabase/migrations/20261018040438_business_invite_seven_day_expiry.sql"
)


def test_migration_only_shortens_pending_and_preserves_history(users):
    with psycopg.connect(shared.DSN, autocommit=True) as db:
        space = str(uuid4())
        db.execute(
            "insert into public.spaces(id,kind,name,created_by) values(%s,'business','Invite test',%s)",
            (space, users["owner"]),
        )
        for kind in ("pending", "accepted", "revoked"):
            db.execute(
                "insert into public.business_access_invites(space_id,issuer_id,email,created_at,expires_at,accepted_at,revoked_at)"
                " values(%s,%s,%s,now()-interval '8 days',now()+interval '6 days',"
                " case when %s='accepted' then now() end, case when %s='revoked' then now() end)",
                (space, users["owner"], f"{kind}@example.test", kind, kind),
            )
        before = dict(
            db.execute(
                "select email,expires_at from public.business_access_invites where space_id=%s",
                (space,),
            ).fetchall()
        )
        db.execute(MIGRATION.read_text(), prepare=False)
        after = dict(
            db.execute(
                "select email,expires_at from public.business_access_invites where space_id=%s",
                (space,),
            ).fetchall()
        )
        assert before["pending@example.test"] - after[
            "pending@example.test"
        ] == timedelta(days=7)
        assert after["accepted@example.test"] == before["accepted@example.test"]
        assert after["revoked@example.test"] == before["revoked@example.test"]
        assert db.execute(
            "select expires_at < now() from public.business_access_invites where space_id=%s and email='pending@example.test'",
            (space,),
        ).fetchone()[0]


def test_real_pending_renewal_is_owner_only_and_expiry_grants_nothing(users):
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as pool:
        spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
        space, _ = spaces.create(users["owner"], "Invite test")
        with pool.connection() as db:
            email = db.execute(
                "select email from auth.users where id=%s", (users["other"],)
            ).fetchone()[0]
        _, listed = access.give(space.id, users["owner"], email)
        invite = listed.invites[0]
        assert invite.expires_at - invite.created_at == timedelta(days=7)
        with pool.connection() as db:
            db.execute(
                "update auth.users set email_confirmed_at=now() where id=%s",
                (users["other"],),
            )
            db.execute(
                "update public.business_access_invites set created_at=now()-interval '8 days', expires_at=now()-interval '1 second' where id=%s",
                (invite.id,),
            )
        assert access.accept_invites(users["other"]) == 0
        assert access.list(space.id, users["owner"]).invites[0].state == "expired"
        assert access.spaces_for(users["other"]) == ()
        assert access.resend(space.id, users["other"], invite.id) is None
        renewed = access.resend(space.id, users["owner"], invite.id)
        assert renewed is not None
        assert renewed.invites[0].expires_at - renewed.invites[0].created_at == timedelta(
            days=7
        )
        assert access.accept_invites(users["other"]) == 1
        assert access.accept_invites(users["other"]) == 0
        assert access.resend(space.id, users["owner"], invite.id) is None


def test_expiry_is_rechecked_after_waiting_for_access_lock(users, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from argus.domain.business import access as access_module

    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as pool:
        spaces, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
        space, _ = spaces.create(users["owner"], "Invite lock test")
        with pool.connection() as db:
            email = db.execute(
                "select email from auth.users where id=%s", (users["other"],)
            ).fetchone()[0]
        _, listed = access.give(space.id, users["owner"], email)
        with pool.connection() as db:
            db.execute(
                "update auth.users set email_confirmed_at=now() where id=%s",
                (users["other"],),
            )
        waiting, original_lock = Event(), access_module._lock

        def observed_lock(connection, space_id):
            waiting.set()
            original_lock(connection, space_id)

        monkeypatch.setattr(access_module, "_lock", observed_lock)
        with ThreadPoolExecutor(max_workers=1) as executor:
            with pool.connection() as db, db.transaction():
                original_lock(db, space.id)
                future = executor.submit(access.accept_invites, users["other"])
                assert waiting.wait(3)
                db.execute(
                    "update public.business_access_invites set created_at=now()-interval '8 days', expires_at=clock_timestamp()-interval '1 second' where id=%s",
                    (listed.invites[0].id,),
                )
            assert future.result(timeout=3) == 0
        assert access.spaces_for(users["other"]) == ()
