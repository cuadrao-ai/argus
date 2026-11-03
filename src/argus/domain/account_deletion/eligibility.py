"""What stands in the way of deleting an account, and what the person should know.

One rule for the delete command (``AccountDeletionService._claim``) and for the
read-only check the Ajustes alert makes before it opens.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from argus.domain.business.lifecycle import LifecycleResult

# The person is a current owner, or holds a live owner grant. Same predicate
# for an open Business (a blocker) and a closed one (a notice).
_OWNED_BUSINESSES = (
    "select s.id::text, s.name, s.closed_at from public.spaces s"
    " where s.kind='business' and (s.closed_at is null) = %s"
    " and (s.current_owner_id=%s or exists(select 1 from public.business_client_grants g"
    " where g.space_id=s.id and g.grantee_id=%s and g.business_role='owner'"
    " and g.revoked_at is null))"
    " order by s.name, s.id"
)


@dataclass(frozen=True)
class DeletionBlocker:
    kind: Literal["business_owner", "not_allowed"]
    business_id: str | None = None
    business_name: str | None = None


@dataclass(frozen=True)
class DeletionNotice:
    """A closed Business the person owned that is still inside its reopen
    window. Deleting the account does not wait for it."""

    business_id: str
    business_name: str
    purge_at: datetime
    kind: Literal["closed_business"] = "closed_business"


@dataclass(frozen=True)
class DeletionEligibility:
    blockers: list[DeletionBlocker] = field(default_factory=list)
    notices: list[DeletionNotice] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return not self.blockers


def blockers_on(
    connection: Any, user_id: str, user: tuple[Any, ...] | None
) -> list[DeletionBlocker]:
    """``user`` is the person's ``auth.users`` row (``raw_app_meta_data`` first),
    or None when there is none; an unknown person is not a placeholder."""

    owned = connection.execute(_OWNED_BUSINESSES, (True, user_id, user_id)).fetchall()
    if owned:
        return [DeletionBlocker("business_owner", row[0], row[1]) for row in owned]
    if (
        user is not None
        and connection.execute(
            "select argus_private.is_account_placeholder(%s, %s::jsonb)",
            (user_id, json.dumps(user[0] or {})),
        ).fetchone()[0]
    ):
        return [DeletionBlocker("not_allowed")]
    return []


def notices_on(connection: Any, user_id: str) -> list[DeletionNotice]:
    now = connection.execute("select clock_timestamp()").fetchone()[0]
    notices = []
    for space_id, name, closed_at in connection.execute(
        _OWNED_BUSINESSES, (False, user_id, user_id)
    ).fetchall():
        purge_at = LifecycleResult(space_id, name, closed_at).reopen_until
        if purge_at is not None and now < purge_at:
            notices.append(DeletionNotice(space_id, name, purge_at))
    return notices
