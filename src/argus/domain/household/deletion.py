"""Account deletion inside the Household owner (Lane 6, steps 1 and 4).

Runs inside the deletion's one database transaction, on the caller's
connection. For each household the person is still in: the admin role passes
to the longest-standing remaining member, or the household closes (1.1); each
shared plan they own passes to its longest-standing participant, and plans
nobody else is in are deleted (1.2, 5.2); then the ordinary leave runs (1.3).
Invite ids are cleared through the one Household-owned invite function (4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class HouseholdDeletionResult:
    households_left: int = 0
    households_closed: int = 0
    admin_handoffs: int = 0
    plans_handed_over: int = 0
    archives_passed_on: int = 0
    events: list[tuple[str, str, str | None, str]] = field(default_factory=list)


def _successor(
    connection: Any, household_id: str, user_id: str
) -> tuple[str, str] | None:
    row = connection.execute(
        "select user_id, id from public.household_members"
        " where household_id = %s and left_at is null and user_id <> %s"
        " order by joined_at, id limit 1",
        (household_id, user_id),
    ).fetchone()
    return (str(row[0]), str(row[1])) if row else None


def _active_members(connection: Any, household_id: str, user_id: str) -> list[str]:
    return [
        str(mid)
        for (mid,) in connection.execute(
            "select id from public.household_members"
            " where household_id = %s and left_at is null and user_id <> %s order by id",
            (household_id, user_id),
        ).fetchall()
    ]


def leave_every_household(
    connection: Any, repository: Any, *, user_id: str, now: datetime
) -> HouseholdDeletionResult:
    """Steps 1.1 to 1.3 for every household the person is still in."""

    result = HouseholdDeletionResult()
    households = [
        str(hid)
        for (hid,) in connection.execute(
            "select h.id from public.households h"
            " join public.household_members m on m.household_id = h.id"
            " where m.user_id = %s and m.left_at is null and h.status = 'active'"
            " order by h.id for update of h",
            (user_id,),
        ).fetchall()
    ]
    for household_id in households:
        others = _active_members(connection, household_id, user_id)
        admin = connection.execute(
            "select admin_user_id from public.households where id = %s", (household_id,)
        ).fetchone()[0]
        # 1.2 first for plans: hand over, or delete plans nobody else is in.
        for binding_id, new_owner_mid in connection.execute(
            "select binding_id, new_owner_membership_id"
            " from argus_private.deletion_hand_over_plans(%s, %s)",
            (user_id, household_id),
        ).fetchall():
            result.plans_handed_over += 1
            result.events.append(
                (household_id, str(new_owner_mid), str(binding_id), "plan_handed_over")
            )
        if not others:
            # 1.1: nobody is left, so the household closes (decision 15).
            repository._close_locked(connection, household_id=household_id)
            result.households_closed += 1
            continue
        if admin is not None and str(admin) == user_id:
            successor = _successor(connection, household_id, user_id)
            connection.execute(
                "update public.households set admin_user_id = %s where id = %s",
                (successor[0], household_id),
            )
            result.admin_handoffs += 1
        # 1.3: the ordinary leave rules (retain_membership, archive_owner, grants).
        repository._end_membership(connection, household_id=household_id, user_id=user_id)
        result.households_left += 1
        for mid in others:
            result.events.append((household_id, mid, None, "member_deleted"))
    for binding_id, new_owner_mid in connection.execute(
        "select binding_id, new_owner_membership_id"
        " from argus_private.deletion_pass_on_archives(%s)",
        (user_id,),
    ).fetchall():
        result.archives_passed_on += 1
        household_id = connection.execute(
            "select household_id from public.household_plan_bindings where id = %s",
            (binding_id,),
        ).fetchone()[0]
        result.events.append(
            (str(household_id), str(new_owner_mid), str(binding_id), "plan_handed_over")
        )
    return result


def return_future_responsibilities(
    connection: Any, *, user_id: str, today: Any
) -> list[tuple[str, str, str | None, str]]:
    """5.1: future responsibilities in plans other people own go back to the
    owner. Past legs stay. Returns one reassign event per plan for its owner."""

    events = []
    rows = connection.execute(
        """select b.id, b.household_id, b.owner_membership_id, b.kind, b.definition_id,
                  b.owner_user_id, max(r.revision)
             from public.household_plan_bindings b
             join public.financial_plan_responsibilities r
               on r.kind = b.kind and r.definition_id = b.definition_id
              and r.owner_id = b.owner_user_id
             join public.household_members m on m.id = r.membership_id
            where m.user_id = %s and b.owner_user_id <> %s
              and b.revoked_at is null and b.departed_at is null
            group by b.id order by b.id""",
        (user_id, user_id),
    ).fetchall()
    for bid, hid, owner_mid, kind, did, owner, _ in rows:
        current = connection.execute(
            "select max(revision) from public.financial_plan_responsibilities"
            " where kind = %s and definition_id = %s and owner_id = %s",
            (kind, did, owner),
        ).fetchone()[0]
        moved = connection.execute(
            """with future as (
                 delete from public.financial_plan_responsibilities r
                  using public.household_members m
                  where m.id = r.membership_id and m.user_id = %(user)s
                    and r.kind = %(kind)s and r.definition_id = %(did)s
                    and r.owner_id = %(owner)s and r.revision = %(rev)s
                    and coalesce(r.agreed_date >= %(today)s, true)
                    and coalesce(r.period >= to_char(%(today)s::date, 'YYYY-MM'), true)
                 returning r.*
               )
               insert into public.financial_plan_responsibilities
                 (kind, definition_id, owner_id, revision, membership_id, amount_minor,
                  period, occurrence_id, schedule_id, agreed_date)
               select kind, definition_id, owner_id, revision, %(owner_mid)s, sum(amount_minor),
                      period, occurrence_id, schedule_id, agreed_date
                 from future
                group by kind, definition_id, owner_id, revision, period, occurrence_id,
                         schedule_id, agreed_date
               on conflict (kind, definition_id, owner_id, revision, membership_id, period,
                            occurrence_id, schedule_id, agreed_date)
               do update set amount_minor = public.financial_plan_responsibilities.amount_minor
                                            + excluded.amount_minor
               returning 1""",
            dict(
                user=user_id,
                kind=kind,
                did=did,
                owner=owner,
                rev=current,
                today=today,
                owner_mid=owner_mid,
            ),
        ).fetchall()
        if moved:
            events.append(
                (str(hid), str(owner_mid), str(bid), "responsibilities_returned")
            )
    return events


def forget_invite_party(connection: Any, *, user_id: str) -> None:
    """Step 4: the one Household-owned writer for the invite tables."""

    connection.execute("select argus_private.forget_invite_party(%s)", (user_id,))


def write_events(connection: Any, events: list[tuple[str, str, str | None, str]]) -> None:
    for household_id, recipient, binding_id, kind in events:
        connection.execute(
            "insert into public.household_deletion_events"
            " (household_id, recipient_membership_id, binding_id, kind)"
            " values (%s, %s, %s, %s)",
            (household_id, recipient, binding_id, kind),
        )
