"""Account deletion against a month-close settlement history.

An owner and a member who have each settled a document can delete their
accounts. The revision stays and the actor clears. A direct change or delete
of that history is still refused.
"""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg.errors import CheckViolation

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def db():
    with psycopg.connect(DSN) as connection, connection.transaction(force_rollback=True):
        yield connection


def _refused(connection, statement: str, params: tuple) -> None:
    with pytest.raises(CheckViolation) as refused:
        with connection.transaction():
            connection.execute(statement, params)
    assert refused.value.diag.message_primary == "business_evidence_immutable"


def test_a_draft_from_another_space_is_not_read(db):
    from argus.domain.business.month_close_store import _DRAFTS

    owner = uuid4()
    here = uuid4()
    there = uuid4()
    activity = uuid4()
    db.execute(
        "insert into auth.users (id, email, is_anonymous) values (%s, %s, false)",
        (owner, f"{owner}@month-close.test"),
    )
    db.execute(
        """insert into public.spaces (id, kind, name, created_by, closed_at)
           values (%s, 'business', 'Here', %s, null),
                  (%s, 'business', 'There', %s, now())""",
        (here, owner, there, owner),
    )
    db.execute(
        """insert into public.financial_import_events (
               id, user_id, owner_space_id, state, evidence, resolution,
               activity_id, created_at, updated_at, version
           ) values (
               %s, %s, %s, 'accepted', 'transaction', %s::jsonb,
               %s, now(), now(), 1
           )""",
        (
            uuid4(),
            owner,
            there,
            '{"business": {"schema_version": "1", "facts": {}}}',
            activity,
        ),
    )

    ours = db.execute(_DRAFTS, (owner, here)).fetchall()
    theirs = db.execute(_DRAFTS, (owner, there)).fetchall()
    assert ours == []
    assert [row[0] for row in theirs] == [str(activity)]


def test_owner_and_member_delete_their_accounts_and_history_stays_sealed(db):
    owner = uuid4()
    member = uuid4()
    space = uuid4()
    activity = uuid4()
    db.execute(
        "insert into auth.users (id, email, is_anonymous) values (%s, %s, false), (%s, %s, false)",
        (owner, f"{owner}@month-close.test", member, f"{member}@month-close.test"),
    )
    db.execute(
        "insert into public.spaces (id, kind, name, created_by) values (%s, 'business', 'Month close', %s)",
        (space, owner),
    )
    db.execute(
        "insert into public.financial_activity_groups (id, user_id, kind, current_revision) values (%s, %s, 'income', 1)",
        (activity, owner),
    )
    db.execute(
        """insert into public.business_document_settlements (
            space_id, owner_id, activity_id, document_kind, status, settled_on, payment_method
        ) values (%s, %s, %s, 'invoice', 'cobrado', '2026-10-09', 'efectivo')""",
        (space, owner, activity),
    )
    db.execute(
        """insert into public.business_document_settlement_revisions (
            space_id, activity_id, actor_id, previous_status
        ) values (%s, %s, %s, 'pendiente'), (%s, %s, %s, 'pendiente')""",
        (space, activity, member, space, activity, owner),
    )

    _refused(
        db,
        "update public.business_document_settlement_revisions set actor_id = null where activity_id = %s",
        (activity,),
    )
    _refused(
        db,
        "update public.business_document_settlement_revisions set previous_status = 'cobrado', previous_settled_on = '2026-10-09', previous_payment_method = 'efectivo' where activity_id = %s",
        (activity,),
    )
    _refused(
        db,
        "delete from public.business_document_settlement_revisions where activity_id = %s",
        (activity,),
    )
    _refused(
        db,
        "delete from public.business_document_settlements where activity_id = %s",
        (activity,),
    )

    db.execute("delete from auth.users where id = %s", (member,))
    kept = db.execute(
        """select count(*) as revisions,
                  count(*) filter (where actor_id is null) as cleared,
                  count(*) filter (where actor_id = %s) as owner_actor
           from public.business_document_settlement_revisions
           where activity_id = %s""",
        (owner, activity),
    ).fetchone()
    assert db.execute("select 1 from auth.users where id = %s", (member,)).fetchone() is None
    assert kept == (2, 1, 1)

    db.execute("delete from auth.users where id = %s", (owner,))
    assert db.execute("select 1 from auth.users where id = %s", (owner,)).fetchone() is None
    assert (
        db.execute(
            "select count(*) from public.business_document_settlement_revisions where activity_id = %s",
            (activity,),
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "select count(*) from public.business_document_settlements where activity_id = %s",
            (activity,),
        ).fetchone()[0]
        == 0
    )
