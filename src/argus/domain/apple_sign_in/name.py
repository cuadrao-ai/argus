from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from argus.domain.apple_sign_in.credentials import AppleIdentityMissing
from argus.domain.apple_sign_in.identity import linked_apple_identity


class AppleNameAccountUnavailable(RuntimeError):
    """The account is missing, closed or already admitted to deletion."""


def initialize_apple_display_name(
    pool: ConnectionPool, *, user_id: str, display_name: str
) -> dict[str, Any]:
    with pool.connection() as connection, connection.transaction():
        connection.execute("set transaction isolation level read committed")
        parent = connection.execute(
            "select banned_until, deleted_at from auth.users where id=%s::uuid for share",
            (user_id,),
        ).fetchone()
        if parent is None or parent[1] is not None:
            raise AppleNameAccountUnavailable
        denied = connection.execute(
            "select (%s::timestamptz > now()) or exists "
            "(select 1 from argus_private.account_placeholders where id=%s::uuid) "
            "or exists (select 1 from argus_private.account_deletion_runs "
            "where user_id=%s::uuid)",
            (parent[0], user_id, user_id),
        ).fetchone()
        if denied and denied[0]:
            raise AppleNameAccountUnavailable
        if linked_apple_identity(connection, user_id, lock=True) is None:
            raise AppleIdentityMissing
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "select * from public.profiles where id=%s::uuid for update",
                (user_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise AppleNameAccountUnavailable
            if not row["name_initialization_closed"]:
                cursor.execute(
                    "update public.profiles set display_name=%s, "
                    "name_initialization_closed=true, updated_at=now() "
                    "where id=%s::uuid returning *",
                    (display_name, user_id),
                )
                row = cursor.fetchone()
            assert row is not None
            return row
