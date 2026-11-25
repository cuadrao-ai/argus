from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING, Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from argus.domain.owner_scope import BusinessSpace, OwnerScope
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RecordingInputError,
    RegisteredAccountRequired,
)
from argus.domain.recording.import_claim import ImportClaim, require_import_claim
from argus.domain.recording.money_postgres import owner_lock
from argus.domain.recording.owner_funds import NoAccountRecord

if TYPE_CHECKING:
    from argus.domain.recording.postgres_repository import (
        PostgresFinancialAccountRepository,
    )


def load(
    connection: Connection,
    user_ids: Collection[str],
    scope: OwnerScope,
    *,
    activity_id: str | None = None,
    history: bool = False,
) -> list[NoAccountRecord]:
    if not isinstance(scope, BusinessSpace):
        return []
    selected = " and g.id=%s" if activity_id is not None else ""
    current = "" if history else " and m.activity_revision=g.current_revision"
    rows = connection.execute(
        f"""select g.id,r.id,r.user_id,r.owner_space_id,r.currency,v.amount_minor,
        v.as_of,v.as_of_zone,v.details->>'note',v.details->>'category_id',v.recorded_at,
        r.record_kind,r.funding,m.activity_revision,v.recorded_by::text
        from public.financial_records r
        join public.financial_activity_memberships m on m.record_id=r.id
        and m.record_owner_id=r.user_id and m.user_id=r.user_id
        join public.financial_record_revisions v on v.record_id=r.id and v.user_id=r.user_id
        and v.revision=m.record_revision
        join public.financial_activity_groups g on g.id=m.activity_id and g.user_id=m.user_id
        where r.account_id is null and g.reversed_at is null
        and r.user_id=any(%s::uuid[]) and r.owner_space_id=%s{selected}{current}""",
        (
            list(user_ids),
            scope.space_id,
            *([activity_id] if activity_id is not None else []),
        ),
    ).fetchall()
    return [
        NoAccountRecord(*(str(value) if i < 4 else value for i, value in enumerate(row)))
        for row in rows
    ]


def load_history(
    repository: PostgresFinancialAccountRepository,
    user_id: str,
    scope: OwnerScope,
    activity_id: str,
) -> list[NoAccountRecord]:
    with repository._pool.connection() as connection:
        rows = load(connection, [user_id], scope, activity_id=activity_id, history=True)
    return sorted(rows, key=lambda row: row.revision, reverse=True)


def transact(
    repository: PostgresFinancialAccountRepository,
    row: NoAccountRecord,
    key: str,
    identity: str,
    preview_valid: bool,
    *,
    import_claim: ImportClaim | None = None,
) -> dict[str, Any]:
    with repository._pool.connection() as connection:
        with connection.transaction():
            owner_lock(connection, row.user_id)
            if not connection.execute(
                "select 1 from auth.users where id=%s and coalesce(is_anonymous,false)=false",
                (row.user_id,),
            ).fetchone():
                raise RegisteredAccountRequired()
            if not connection.execute(
                "select 1 from public.spaces where id=%s and created_by=%s and closed_at is null for share",
                (row.owner_space_id, row.user_id),
            ).fetchone():
                raise AccountNotFound()
            receipt = connection.execute(
                "select identity_hash,activity_id,revision from public.financial_activity_receipts where user_id=%s and scope='canonical' and idempotency_key=%s",
                (row.user_id, key),
            ).fetchone()
            if receipt:
                if receipt[0] != identity:
                    raise IdempotencyConflict()
                saved = next(
                    (
                        item
                        for item in load(
                            connection,
                            [row.user_id],
                            BusinessSpace(row.owner_space_id),
                            activity_id=str(receipt[1]),
                            history=True,
                        )
                        if item.revision == receipt[2]
                    ),
                    None,
                )
                if saved is None:
                    raise IdempotencyConflict()
                return {"activity": saved.response(), "accounts": [], "replayed": True}
            require_import_claim(
                connection, row.user_id, BusinessSpace(row.owner_space_id), import_claim
            )
            if not preview_valid:
                raise RecordingInputError(
                    "preview_required", "Review the proposed change before saving it."
                )
            connection.execute(
                "insert into public.financial_activity_groups(id,user_id,kind,current_revision) values(%s,%s,%s,1)",
                (row.activity_id, row.user_id, row.kind),
            )
            connection.execute(
                "insert into public.financial_activity_revisions(activity_id,revision,user_id) values(%s,1,%s)",
                (row.activity_id, row.user_id),
            )
            connection.execute(
                """insert into public.financial_records(id,account_id,user_id,record_kind,current_revision,created_at,owner_space_id,funding,currency)
                values(%s,null,%s,%s,1,%s,%s,%s,%s)""",
                (
                    row.record_id,
                    row.user_id,
                    row.kind,
                    row.recorded_at,
                    row.owner_space_id,
                    row.funding,
                    row.currency,
                ),
            )
            connection.execute(
                """insert into public.financial_record_revisions(record_id,user_id,revision,amount_minor,as_of,as_of_zone,recorded_by,recorded_at,details)
                values(%s,%s,1,%s,%s,%s,%s,%s,%s)""",
                (
                    row.record_id,
                    row.user_id,
                    row.amount_minor,
                    row.occurred_at,
                    row.time_zone,
                    row.user_id,
                    row.recorded_at,
                    Jsonb({"note": row.note, "category_id": row.category_id}),
                ),
            )
            connection.execute(
                """insert into public.financial_activity_memberships(activity_id,user_id,activity_revision,record_id,record_revision,role,record_owner_id)
                values(%s,%s,1,%s,1,'single',%s)""",
                (row.activity_id, row.user_id, row.record_id, row.user_id),
            )
            connection.execute(
                """insert into public.financial_activity_receipts(user_id,scope,idempotency_key,identity_hash,activity_id,revision,affected_accounts)
                values(%s,'canonical',%s,%s,%s,1,'{}')""",
                (row.user_id, key, identity, row.activity_id),
            )
            return {"activity": row.response(), "accounts": [], "replayed": False}
