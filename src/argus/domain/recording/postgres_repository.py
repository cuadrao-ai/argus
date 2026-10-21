"""Postgres repository for financial accounts, over the ``DATABASE_URL`` pool.

Creation and opening writes go through the two migration-owned functions so
replay, compare-and-set and the account/record/revision write happen in one
transaction. Reads and the account edit are plain statements scoped by
``user_id``; the edit's ``version`` predicate is its compare-and-set.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from argus.domain.recording.assets import AssetDetailsResult

from psycopg import sql
from psycopg_pool import ConnectionPool

from argus.domain.owner_scope import OwnerScope, space_id, sql_predicate
from argus.domain.recording.accounts import AccountFacts
from argus.domain.recording.asset_schemas import AssetDetailsRequest
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RegisteredAccountRequired,
    StaleVersion,
)
from argus.domain.recording.loop_postgres import hydrate, mutate
from argus.domain.recording.loop_storage import OperationResult, Planner
from argus.domain.recording.records import (
    OPENING_KIND,
    OpeningRecord,
    OpeningRevision,
    OpeningWrite,
)
from argus.domain.recording.repository import CreateResult, NewAccount, StoredAccount

_EDITABLE_COLUMNS = frozenset(
    {"nickname", "type", "currency", "archived", "ownership_share_bps"}
)

_ACCOUNT_COLUMNS = (
    "id, user_id, type, currency, nickname, archived, ownership_share_bps, "
    "version, created_at, updated_at"
)


class PostgresFinancialAccountRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        identity_hash: str,
        account: NewAccount,
        opening: OpeningWrite | None,
        scope: OwnerScope,
    ) -> CreateResult:
        with self._pool.connection() as connection:
            row = connection.execute(
                "select public.create_financial_account("
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    user_id,
                    idempotency_key,
                    identity_hash,
                    account.type,
                    account.currency,
                    account.nickname,
                    account.ownership_share_bps,
                    opening.amount_minor if opening else None,
                    opening.as_of if opening else None,
                    opening.time_zone if opening else None,
                    space_id(scope),
                ),
            ).fetchone()
            outcome: dict[str, Any] = row[0]
            decision = outcome["decision"]
            if decision == "conflict":
                raise IdempotencyConflict()
            if decision == "registered_required":
                raise RegisteredAccountRequired()
            if decision == "created" and opening is not None and opening.blank:
                from psycopg.types.json import Jsonb

                marked = connection.execute(
                    "update public.financial_record_revisions v set details=details || %s where v.record_id=(select id from public.financial_records where account_id=%s and user_id=%s and record_kind='opening_balance') and v.revision=1",
                    (Jsonb({"blank": True}), outcome["account_id"], user_id),
                )
                if marked.rowcount != 1:
                    # Raising inside the connection block rolls the new account back too.
                    raise RuntimeError("blank opening was not marked on the new account")
            stored = self._load(
                connection, user_id, str(outcome["account_id"]), scope=scope
            )
            if stored is None:  # pragma: no cover - the function just wrote it
                raise AccountNotFound()
            return CreateResult(stored, created=decision == "created")

    def list_accounts(self, *, user_id: str, scope: OwnerScope) -> list[StoredAccount]:
        in_scope, params = sql_predicate(scope, "owner_space_id")
        with self._pool.connection() as connection:
            connection.execute("set transaction isolation level repeatable read")
            rows = connection.execute(
                f"select {_ACCOUNT_COLUMNS} from public.financial_accounts"
                f" where user_id = %s and {in_scope} order by created_at asc, id asc",
                (user_id, *params),
            ).fetchall()
            openings = self._openings(connection, user_id, [str(row[0]) for row in rows])
            records = [
                hydrate(connection, StoredAccount(_facts(row), openings.get(str(row[0]))))
                for row in rows
            ]
            from .canonical_groups import VisibleAccounts, load

            return VisibleAccounts(
                records, load(self, connection, {user_id}, scope=scope)
            )

    def get_account(
        self, *, user_id: str, account_id: str, scope: OwnerScope
    ) -> StoredAccount | None:
        with self._pool.connection() as connection:
            connection.execute("set transaction isolation level repeatable read")
            return self._load(connection, user_id, account_id, scope=scope)

    def get_any_account(self, *, account_id: str) -> StoredAccount | None:
        """Load by id after household authorization; not a client route."""

        with self._pool.connection() as connection:
            connection.execute("set transaction isolation level repeatable read")
            row = connection.execute(
                f"select {_ACCOUNT_COLUMNS} from public.financial_accounts where id = %s",
                (account_id,),
            ).fetchone()
            if row is None:
                return None
            openings = self._openings(connection, str(row[1]), [str(row[0])])
            return hydrate(
                connection, StoredAccount(_facts(row), openings.get(str(row[0])))
            )

    def update_account(
        self,
        *,
        user_id: str,
        account_id: str,
        expected_version: int,
        changes: dict[str, object],
        scope: OwnerScope,
    ) -> StoredAccount:
        unknown = set(changes) - _EDITABLE_COLUMNS
        if unknown:
            raise ValueError(f"not editable: {sorted(unknown)}")
        assignments = [sql.SQL("version = version + 1")]
        params: list[object] = []
        for column, value in changes.items():
            assignments.append(sql.SQL("{} = %s").format(sql.Identifier(column)))
            params.append(value)
        statement = sql.SQL(
            "update public.financial_accounts set {} "
            "where id = %s and user_id = %s and version = %s returning id"
        ).format(sql.SQL(", ").join(assignments))
        with self._pool.connection() as connection:
            with connection.transaction():
                from argus.domain.recording.asset_postgres import lock_owner
                from argus.domain.recording.asset_storage import validate_type_change

                lock_owner(connection, user_id)
                current = self._load(connection, user_id, account_id, scope=scope)
                if current is None:
                    raise AccountNotFound()
                linked = (
                    connection.execute(
                        "select 1 from public.financial_asset_details where user_id=%s and (account_id=%s and related_debt_account_id is not null or related_debt_account_id=%s)",
                        (user_id, account_id, account_id),
                    ).fetchone()
                    is not None
                )
                validate_type_change(current, changes, linked)
                updated = connection.execute(
                    statement, (*params, account_id, user_id, expected_version)
                ).fetchone()
                if updated is None:
                    exists = connection.execute(
                        "select 1 from public.financial_accounts where id = %s and user_id = %s",
                        (account_id, user_id),
                    ).fetchone()
                    raise StaleVersion() if exists else AccountNotFound()
                stored = self._load(connection, user_id, account_id, scope=scope)
        if stored is None:  # pragma: no cover - the row was just updated
            raise AccountNotFound()
        return stored

    def write_opening(
        self,
        *,
        user_id: str,
        account_id: str,
        expected_revision: int | None,
        expected_version: int,
        write: OpeningWrite,
        scope: OwnerScope,
    ) -> StoredAccount:
        with self._pool.connection() as connection:
            # An account never changes space, so checking it first is enough.
            if self._load(connection, user_id, account_id, scope=scope) is None:
                raise AccountNotFound()
            row = connection.execute(
                "select public.write_financial_opening(%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    user_id,
                    account_id,
                    expected_revision,
                    expected_version,
                    write.amount_minor,
                    write.as_of,
                    write.time_zone,
                    write.reason,
                ),
            ).fetchone()
            decision = row[0]["decision"]
            if decision == "not_found":
                raise AccountNotFound()
            if decision == "stale":
                raise StaleVersion()
            if decision == "registered_required":
                raise RegisteredAccountRequired()
            if write.estimate_basis is not None:
                from psycopg.types.json import Jsonb

                connection.execute(
                    "update public.financial_record_revisions v set details=details || %s where v.record_id=(select id from public.financial_records where account_id=%s and user_id=%s and record_kind='opening_balance') and v.revision=%s",
                    (
                        Jsonb({"estimate_basis": write.estimate_basis}),
                        account_id,
                        user_id,
                        (expected_revision or 0) + 1,
                    ),
                )
            stored = self._load(connection, user_id, account_id, scope=scope)
        if stored is None:  # pragma: no cover - the function just wrote it
            raise AccountNotFound()
        return stored

    def mutate(
        self,
        *,
        user_id: str,
        account_id: str,
        idempotency_key: str,
        identity_hash: str,
        expected_version: int,
        planner: Planner,
        scope: OwnerScope,
    ) -> OperationResult:
        return mutate(
            self,
            user_id=user_id,
            account_id=account_id,
            idempotency_key=idempotency_key,
            identity_hash=identity_hash,
            expected_version=expected_version,
            planner=planner,
            scope=scope,
        )

    def write_asset_details(
        self,
        *,
        user_id: str,
        account_id: str,
        request: AssetDetailsRequest,
        idempotency_key: str,
        identity_hash: str,
        scope: OwnerScope,
    ) -> AssetDetailsResult:
        from argus.domain.recording.asset_postgres import write_details

        return write_details(
            self,
            user_id=user_id,
            account_id=account_id,
            request=request,
            idempotency_key=idempotency_key,
            identity_hash=identity_hash,
            scope=scope,
        )

    def _load(
        self,
        connection,  # noqa: ANN001
        user_id: str,
        account_id: str,
        *,
        scope: OwnerScope,
    ) -> StoredAccount | None:
        in_scope, params = sql_predicate(scope, "owner_space_id")
        row = connection.execute(
            f"select {_ACCOUNT_COLUMNS} from public.financial_accounts"
            f" where id = %s and user_id = %s and {in_scope}",
            (account_id, user_id, *params),
        ).fetchone()
        if row is None:
            return None
        account_id = str(row[0])
        openings = self._openings(connection, user_id, [account_id])
        return hydrate(connection, StoredAccount(_facts(row), openings.get(account_id)))

    def _openings(
        self,
        connection,
        user_id: str,
        account_ids: Iterable[str],  # noqa: ANN001
    ) -> dict[str, OpeningRecord]:
        ids = list(account_ids)
        if not ids:
            return {}
        rows = connection.execute(
            "select r.id, r.account_id, v.revision, v.amount_minor, v.as_of, v.as_of_zone,"
            " v.reason, v.recorded_by, v.recorded_at, v.details"
            " from public.financial_records r"
            " join public.financial_record_revisions v on v.record_id = r.id"
            " where r.user_id = %s and r.record_kind = %s and r.account_id = any(%s)"
            " order by r.account_id, v.revision asc",
            (user_id, OPENING_KIND, ids),
        ).fetchall()
        grouped: dict[str, tuple[str, list[OpeningRevision]]] = {}
        for (
            record_id,
            account_id,
            revision,
            amount,
            as_of,
            zone,
            reason,
            by,
            at,
            details,
        ) in rows:
            entry = grouped.setdefault(str(account_id), (str(record_id), []))
            entry[1].append(
                OpeningRevision(
                    revision=revision,
                    amount_minor=amount,
                    as_of=as_of,
                    time_zone=zone,
                    reason=reason,
                    recorded_by=str(by) if by is not None else None,
                    recorded_at=at,
                    estimate_basis=details.get("estimate_basis"),
                    blank=bool(details.get("blank", False)),
                )
            )
        return {
            account_id: OpeningRecord(record_id, account_id, tuple(revisions))
            for account_id, (record_id, revisions) in grouped.items()
        }


def _facts(row: tuple) -> AccountFacts:
    (
        id_,
        user_id,
        type_,
        currency,
        nickname,
        archived,
        share,
        version,
        created,
        updated,
    ) = row
    return AccountFacts(
        id=str(id_),
        user_id=str(user_id),
        type=type_,
        currency=currency,
        nickname=nickname,
        archived=archived,
        ownership_share_bps=share,
        version=version,
        created_at=created,
        updated_at=updated,
    )
