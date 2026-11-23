"""The claim a new ledger write from import reconciliation must still hold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from argus.domain.owner_scope import OwnerScope, sql_predicate

if TYPE_CHECKING:
    from psycopg import Connection


class ImportClaimLost(Exception):
    """The draft is no longer waiting for this write."""


@dataclass(frozen=True)
class ImportClaim:
    event_id: str
    key: str


def require_import_claim(
    connection: Connection, user_id: str, scope: OwnerScope, claim: ImportClaim | None
) -> None:
    if claim is None:
        return
    in_scope, params = sql_predicate(scope, "owner_space_id")
    # A matching row must remain claimed until the money transaction commits.
    if connection.execute(
        "select 1 from public.financial_import_events where id=%s and user_id=%s"
        f" and {in_scope} and state='accepting' and accept_key=%s for share",
        (claim.event_id, user_id, *params, claim.key),
    ).fetchone() is None:
        raise ImportClaimLost()
