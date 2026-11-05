"""Household-owned: argus_private.forget_invite_party (account deletion step 4).

At the top level so the real-PostgreSQL CI matrix (tests/test_*_postgres.py)
gates it.

The function ships in Lane 6's migration, but its rules belong to Household
(Yelena, HoE, signed off Oct 3). It clears the person's ids from every invite
table, keeps every anonymous row, rotates sender_ref to a distinct fresh value
per row with the inviter_origin_id chain unchanged, revokes the person's
unused beta invites, leaves everyone else's rows alone, and is idempotent.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")

LATER = datetime.now(timezone.utc) + timedelta(days=7)


def _user(c: psycopg.Connection) -> str:
    uid = str(uuid.uuid4())
    c.execute(
        "insert into auth.users(id,email) values (%s,%s)",
        (uid, f"invite-{uid}@example.test"),
    )
    return uid


def _beta(c: psycopg.Connection, by: str, *, used: bool = False) -> str:
    return str(
        c.execute(
            "insert into public.beta_invitations"
            " (kind,token_hash,created_by,max_uses,use_count,expires_at,idempotency_key,request_hash)"
            " values ('beta',%s,%s,1,%s,%s,%s,'h') returning id",
            (uuid.uuid4().hex, by, 1 if used else 0, LATER, uuid.uuid4().hex),
        ).fetchone()[0]
    )


def test_forget_invite_party_clears_the_person_and_keeps_everyone_else() -> None:
    with psycopg.connect(DSN, autocommit=True) as c:
        x, y, z = _user(c), _user(c), _user(c)
        hid = str(
            c.execute(
                "insert into public.households(name,admin_user_id) values ('Inv',%s) returning id",
                (z,),
            ).fetchone()[0]
        )
        ref = str(
            c.execute(
                "insert into public.invite_sender_refs(user_id) values (%s) returning ref",
                (x,),
            ).fetchone()[0]
        )
        unused, used, others = _beta(c, x), _beta(c, x, used=True), _beta(c, z)
        c.execute(
            "insert into public.beta_invite_quota_grants(user_id,granted_by,extra,idempotency_key,request_hash)"
            " values (%s,%s,1,%s,'h')",
            (y, x, uuid.uuid4().hex),
        )
        hinv = str(
            c.execute(
                "insert into public.household_invitations(household_id,token_hash,created_by,expires_at,accepted_by,accepted_at)"
                " values (%s,%s,%s,%s,%s,now()) returning id",
                (hid, uuid.uuid4().hex, x, LATER, y),
            ).fetchone()[0]
        )
        first = str(
            c.execute(
                "insert into public.invite_referrals(kind,beta_invitation_id,sender_ref,sender_user_id,acceptor_user_id,accepted_at)"
                " values ('beta',%s,%s,%s,%s,now()) returning id",
                (used, ref, x, y),
            ).fetchone()[0]
        )
        second = str(
            c.execute(
                "insert into public.invite_referrals(kind,household_invitation_id,inviter_origin_id,sender_ref,sender_user_id)"
                " values ('household',%s,%s,%s,%s) returning id",
                (hinv, first, ref, x),
            ).fetchone()[0]
        )
        accepted_from_z = str(
            c.execute(
                "insert into public.invite_referrals(kind,beta_invitation_id,sender_user_id,acceptor_user_id,accepted_at)"
                " values ('beta',%s,%s,%s,now()) returning id",
                (others, z, x),
            ).fetchone()[0]
        )
        try:
            for _ in range(2):  # idempotent
                c.execute("select argus_private.forget_invite_party(%s)", (x,))
            rows = {
                str(r[0]): r[1:]
                for r in c.execute(
                    "select id, sender_ref, sender_user_id, acceptor_user_id, inviter_origin_id"
                    " from public.invite_referrals where id = any(%s::uuid[])",
                    ([first, second, accepted_from_z],),
                ).fetchall()
            }
            refs = [rows[first][0], rows[second][0]]
            assert None not in refs and len(set(refs)) == 2
            assert str(ref) not in {str(r) for r in refs}
            assert rows[first][1] is None and rows[second][1] is None
            # The acceptor of x's invite is someone else and stays.
            assert str(rows[first][2]) == y
            assert str(rows[second][3]) == first
            # x accepted z's invite: x's id goes, z's stays.
            assert rows[accepted_from_z][2] is None
            assert str(rows[accepted_from_z][1]) == z
            assert not c.execute(
                "select 1 from public.invite_sender_refs where user_id=%s", (x,)
            ).fetchone()
            beta = {
                str(r[0]): (r[1] and str(r[1]), r[2])
                for r in c.execute(
                    "select id, created_by, revoked_at is not null"
                    " from public.beta_invitations where id = any(%s::uuid[])",
                    ([unused, used, others],),
                ).fetchall()
            }
            # x's unused invite is revoked, the used one kept; z's untouched.
            assert beta == {unused: (None, True), used: (None, False), others: (z, False)}
            assert c.execute(
                "select granted_by from public.beta_invite_quota_grants where user_id=%s",
                (y,),
            ).fetchone() == (None,)
            assert c.execute(
                "select created_by, accepted_by from public.household_invitations where id=%s",
                (hinv,),
            ).fetchone() == (None, uuid.UUID(y))
        finally:
            c.execute(
                "delete from public.invite_referrals where id = any(%s::uuid[])",
                ([accepted_from_z, second, first],),
            )
            c.execute("delete from public.household_invitations where id=%s", (hinv,))
            c.execute("delete from public.households where id=%s", (hid,))
            c.execute(
                "delete from public.beta_invitations where id = any(%s::uuid[])",
                ([unused, used, others],),
            )
            c.execute("delete from auth.users where id = any(%s::uuid[])", ([x, y, z],))
