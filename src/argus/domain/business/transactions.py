from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from argus.domain.business.authority import (
    ActionContext,
    ActionError,
    Authorization,
    BusinessAuthority,
    authorize,
)
from argus.domain.business.contracts.authority import Capability
from argus.domain.business.contracts.recovery import SenderLease
from argus.domain.business.transactions_legacy import LegacyImportTransaction
from argus.domain.ingestion.reconcile.store_postgres import _PostgresTx
from argus.domain.owner_scope import OwnerScope


@dataclass
class ActionTransaction:
    connection: Connection
    authorization: Authorization
    imports: _PostgresTx

    @property
    def context(self) -> ActionContext:
        return self.authorization.context

    def rows(self, statement: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(statement, params)
            return list(cursor.fetchall()) if cursor.description else []


def check_lease(
    connection: Connection, context: ActionContext, lease: SenderLease
) -> None:
    if lease.space_id != context.actor.space_id:
        raise ActionError("not_found", "business_record_not_found")
    found = connection.execute(
        "select 1 from public.business_sender_leases"
        " where space_id=%s and sender_hash=%s and holder=%s and fence=%s"
        " and lease_until > clock_timestamp() for share",
        (lease.space_id, lease.sender_hash, lease.holder, lease.fence),
    ).fetchone()
    if not found:
        raise ActionError("permission_denied", "business_sender_lease_lost")


@contextmanager
def transaction(
    authority: BusinessAuthority,
    context: ActionContext,
    capability: Capability = "read",
    lease: SenderLease | None = None,
) -> Iterator[ActionTransaction]:
    with authority.pool.connection() as connection, connection.transaction():
        connection.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"financial_import:{context.owner_id}",),
        )
        live = authorize(connection, context.actor, context.grant_id)
        if live.context.owner_id != context.owner_id:
            raise ActionError("not_found", "business_record_not_found")
        live.require(capability)
        if lease is not None:
            check_lease(connection, context, lease)
        yield ActionTransaction(
            connection, live, _PostgresTx(connection, context.owner_id, context.scope)
        )
        if lease is not None:
            check_lease(connection, context, lease)
        authorize(connection, context.actor, context.grant_id).require(capability)


class GrantImportStore:
    def __init__(
        self, authority: BusinessAuthority, context: ActionContext, capability: Capability
    ) -> None:
        self.authority = authority
        self.context = context
        self.capability = capability

    @contextmanager
    def transaction(self, user_id: str, *, scope: OwnerScope) -> Iterator[_PostgresTx]:
        if user_id != self.context.owner_id or scope != self.context.scope:
            raise ActionError("not_found", "business_record_not_found")
        with transaction(self.authority, self.context, self.capability) as tx:
            legacy = LegacyImportTransaction(tx.connection, tx.context)
            yield legacy
            legacy.verify_links()
