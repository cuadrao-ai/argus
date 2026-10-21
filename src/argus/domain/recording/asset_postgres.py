"""Persistence for non-money asset details and append-only accepted changes."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from psycopg import Connection

from argus.domain.owner_scope import OwnerScope, sql_predicate
from argus.domain.recording.asset_model import AssetChange
from argus.domain.recording.asset_schemas import AssetDetailsRequest
from argus.domain.recording.asset_storage import debt_id, validate_debt
from argus.domain.recording.assets import AssetDetailsResult, require_asset
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RegisteredAccountRequired,
    StaleVersion,
)
from argus.domain.recording.repository import StoredAccount

if TYPE_CHECKING:
    from argus.domain.recording.postgres_repository import (
        PostgresFinancialAccountRepository,
    )


def hydrate_asset(connection: Connection, stored: StoredAccount) -> StoredAccount:
    owner, account_id = stored.account.user_id, stored.account.id
    detail = connection.execute(
        "select related_debt_account_id from public.financial_asset_details where user_id=%s and account_id=%s",
        (owner, account_id),
    ).fetchone()
    changes = connection.execute(
        "select account_version,previous_share_bps,ownership_share_bps,previous_debt_account_id,related_debt_account_id,recorded_by,recorded_at,idempotency_key,identity_hash from public.financial_asset_changes where user_id=%s and account_id=%s order by account_version",
        (owner, account_id),
    ).fetchall()
    return replace(
        stored,
        related_debt_account_id=str(detail[0]) if detail and detail[0] else None,
        asset_changes=tuple(
            AssetChange(
                v,
                old,
                new,
                str(before) if before else None,
                str(after) if after else None,
                str(by),
                at,
                key,
                identity,
            )
            for v, old, new, before, after, by, at, key, identity in changes
        ),
    )


def lock_owner(connection: Connection, owner: str) -> None:
    connection.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s,0))",
        ("financial_asset_metadata:" + owner,),
    )


def write_details(
    repository: PostgresFinancialAccountRepository,
    *,
    user_id: str,
    account_id: str,
    request: AssetDetailsRequest,
    idempotency_key: str,
    identity_hash: str,
    scope: OwnerScope,
) -> AssetDetailsResult:
    in_scope, in_params = sql_predicate(scope, "owner_space_id")
    with repository._pool.connection() as connection, connection.transaction():
        if not connection.execute(
            "select 1 from auth.users where id=%s and coalesce(is_anonymous,false)=false",
            (user_id,),
        ).fetchone():
            raise RegisteredAccountRequired()
        lock_owner(connection, user_id)
        locked = connection.execute(
            "select version from public.financial_accounts where id=%s and user_id=%s"
            f" and {in_scope} for update",
            (account_id, user_id, *in_params),
        ).fetchone()
        if not locked:
            raise AccountNotFound()
        stored = repository._load(connection, user_id, account_id, scope=scope)
        assert stored is not None
        previous = next(
            (c for c in stored.asset_changes if c.idempotency_key == idempotency_key),
            None,
        )
        if previous:
            if previous.identity_hash != identity_hash:
                raise IdempotencyConflict()
            return AssetDetailsResult(stored, previous.version, True)
        if locked[0] != request.expected_version:
            raise StaleVersion()
        require_asset(stored)
        target = debt_id(request)
        if target is not None:
            validate_debt(repository._load(connection, user_id, target, scope=scope))
        version = stored.account.version + 1
        connection.execute(
            "update public.financial_accounts set ownership_share_bps=%s,version=%s where id=%s and user_id=%s",
            (request.ownership_share_bps, version, account_id, user_id),
        )
        connection.execute(
            "insert into public.financial_asset_details(account_id,user_id,related_debt_account_id) values(%s,%s,%s) on conflict(account_id) do update set related_debt_account_id=excluded.related_debt_account_id",
            (account_id, user_id, target),
        )
        connection.execute(
            "insert into public.financial_asset_changes(account_id,user_id,account_version,previous_share_bps,ownership_share_bps,previous_debt_account_id,related_debt_account_id,recorded_by,idempotency_key,identity_hash) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                account_id,
                user_id,
                version,
                stored.account.ownership_share_bps,
                request.ownership_share_bps,
                stored.related_debt_account_id,
                target,
                user_id,
                idempotency_key,
                identity_hash,
            ),
        )
        updated = repository._load(connection, user_id, account_id, scope=scope)
        assert updated is not None
        return AssetDetailsResult(updated, version, False)
