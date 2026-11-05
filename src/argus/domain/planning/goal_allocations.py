"""Persist residuals once and reconstruct the existing Personal goal state."""

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


def load(connection: Connection, user_id: str, goals: dict[str, dict[str, Any]]) -> None:
    for body in goals.values():
        body["allocations"] = []
    for gid, aid, amount in connection.execute(
        "select goal_id,account_id,unlinked_minor from public.financial_goal_allocations "
        "where goal_owner_id=%s and account_owner_id=%s order by goal_id,ordinal",
        (user_id, user_id),
    ).fetchall():
        goals[str(gid)]["allocations"].append(
            {"account_id": str(aid), "unlinked_minor": amount}
        )


def persist(
    connection: Connection, user_id: str, goals: dict[str, dict[str, Any]]
) -> None:
    for gid, body in goals.items():
        connection.execute(
            "insert into public.financial_goals(id,user_id,body) values(%s,%s,%s) "
            "on conflict(id,user_id) do update set body=excluded.body",
            (
                gid,
                user_id,
                Jsonb(
                    {key: value for key, value in body.items() if key != "allocations"}
                ),
            ),
        )
    for gid, body in goals.items():
        retained = [entry["account_id"] for entry in body["allocations"]]
        connection.execute(
            "delete from public.financial_goal_allocations where goal_id=%s "
            "and goal_owner_id=%s and account_owner_id=%s and binding_id is null "
            "and not (account_id=any(%s::uuid[]))",
            (gid, user_id, user_id, retained),
        )
        # A published row is retained for attribution/history; omitted Personal
        # residuals release its money rather than keeping an invisible old amount.
        omitted = connection.execute(
            "select account_id from public.financial_goal_allocations where goal_id=%s "
            "and goal_owner_id=%s and account_owner_id=%s and binding_id is not null "
            "and not (account_id=any(%s::uuid[])) order by ordinal,account_id",
            (gid, user_id, user_id, retained),
        ).fetchall()
        for ordinal, (aid,) in enumerate(omitted, start=len(retained)):
            connection.execute(
                "update public.financial_goal_allocations set unlinked_minor=0,ordinal=%s "
                "where goal_id=%s and account_id=%s",
                (ordinal, gid, aid),
            )
        for ordinal, allocation in enumerate(body["allocations"]):
            connection.execute(
                "insert into public.financial_goal_allocations "
                "(goal_id,goal_owner_id,account_id,account_owner_id,unlinked_minor,ordinal) "
                "values(%s,%s,%s,%s,%s,%s) on conflict(goal_id,account_id) "
                "do update set unlinked_minor=excluded.unlinked_minor,ordinal=excluded.ordinal",
                (
                    gid,
                    user_id,
                    allocation["account_id"],
                    user_id,
                    allocation["unlinked_minor"],
                    ordinal,
                ),
            )
