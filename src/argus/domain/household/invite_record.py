"""The who-invited-whom record and beta admission, inside the caller's transaction.

Live sender and acceptor ids sit beside the anonymous row and are cleared on
account deletion. The sender reference is random and its mapping row goes with
the account, so counts and the invite chain survive and identify nobody.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4


def sender_ref(c, user_id: str) -> str:  # noqa: ANN001
    c.execute(
        "insert into public.invite_sender_refs(user_id) values(%s)"
        " on conflict (user_id) do nothing",
        (user_id,),
    )
    return str(
        c.execute(
            "select ref from public.invite_sender_refs where user_id=%s", (user_id,)
        ).fetchone()[0]
    )


def origin_of(c, user_id: str) -> str | None:  # noqa: ANN001
    row = c.execute(
        "select referral_id from public.beta_admissions where user_id=%s", (user_id,)
    ).fetchone()
    return str(row[0]) if row and row[0] is not None else None


def admission(c, user_id: str) -> str | None:  # noqa: ANN001
    row = c.execute(
        "select via from public.beta_admissions where user_id=%s", (user_id,)
    ).fetchone()
    return row[0] if row else None


def admit(c, user_id: str, via: str, referral_id: str | None, at: datetime) -> None:  # noqa: ANN001
    c.execute(
        "insert into public.beta_admissions(user_id,via,referral_id,admitted_at)"
        " values(%s,%s,%s,%s) on conflict (user_id) do nothing",
        (user_id, via, referral_id, at),
    )


def record_sent(
    c,  # noqa: ANN001
    *,
    kind: str,
    sender: str,
    at: datetime,
    beta_invitation_id: str | None = None,
    household_invitation_id: str | None = None,
) -> str:
    rid = str(uuid4())
    c.execute(
        "insert into public.invite_referrals(id,kind,beta_invitation_id,"
        "household_invitation_id,inviter_origin_id,sender_ref,sender_user_id,sent_at)"
        " values(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            rid,
            kind,
            beta_invitation_id,
            household_invitation_id,
            origin_of(c, sender),
            sender_ref(c, sender),
            sender,
            at,
        ),
    )
    return rid


def record_household_accepted(
    c,  # noqa: ANN001
    *,
    invitation_id: str,
    acceptor: str,
    at: datetime,
) -> None:
    """Mark the household invite accepted and let the person into the beta."""
    row = c.execute(
        "update public.invite_referrals set acceptor_user_id=%s, accepted_at=%s"
        " where household_invitation_id=%s and accepted_at is null returning id",
        (acceptor, at, invitation_id),
    ).fetchone()
    if row is None:
        existing = c.execute(
            "select id from public.invite_referrals where household_invitation_id=%s",
            (invitation_id,),
        ).fetchone()
        if existing is not None:
            rid = str(existing[0])
        else:
            rid = str(uuid4())
            c.execute(
                "insert into public.invite_referrals(id,kind,household_invitation_id,"
                "acceptor_user_id,sent_at,accepted_at) values(%s,'household',%s,%s,%s,%s)",
                (rid, invitation_id, acceptor, at, at),
            )
    else:
        rid = str(row[0])
    admit(c, acceptor, "household_invitation", rid, at)
