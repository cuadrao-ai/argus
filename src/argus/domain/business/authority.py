from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from psycopg import Connection, sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from argus.domain.business.contracts.actions import Refused
from argus.domain.business.contracts.authority import (
    ActorProvenance,
    Capability,
    TrustedActor,
)
from argus.domain.owner_scope import BusinessSpace


class ActionError(Exception):
    def __init__(self, outcome: str, code: str) -> None:
        self.result = Refused(outcome=outcome, code=code)
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ActionContext:
    actor: TrustedActor
    grant_id: UUID
    owner_id: str
    space_name: str

    @property
    def scope(self) -> BusinessSpace:
        return BusinessSpace(str(self.actor.space_id))


@dataclass(frozen=True)
class Authorization:
    context: ActionContext
    provenance: ActorProvenance
    capabilities: frozenset[Capability]

    def require(self, capability: Capability) -> None:
        if capability not in self.capabilities:
            raise ActionError("permission_denied", "business_permission_denied")


def authorize(
    connection: Connection,
    actor: TrustedActor,
    grant_id: UUID | None = None,
) -> Authorization:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """select g.id, g.issuer_id, g.capabilities,
                s.created_by::text as owner_id, s.name,
                coalesce(nullif(btrim(p.display_name), ''),
                    nullif(btrim(p.username), ''), 'Member') as actor_name,
                coalesce(nullif(btrim(i.display_name), ''),
                    nullif(btrim(i.username), ''), 'Member') as issuer_name
            from public.business_client_grants g
            join public.spaces s on s.id=g.space_id
            join auth.users u on u.id=g.grantee_id
            left join public.profiles p on p.id=g.grantee_id
            left join public.profiles i on i.id=g.issuer_id
            where g.space_id=%s and g.grantee_id=%s
                and (%s::uuid is null or g.id=%s)
                and g.revoked_at is null
                and (g.expires_at is null or g.expires_at > clock_timestamp())
                and 'read'=any(g.capabilities)
                and s.kind='business' and s.closed_at is null
                and coalesce(u.is_anonymous,false)=false
            order by cardinality(g.capabilities) desc, g.created_at, g.id
            limit 1 for share of g, s""",
            (actor.space_id, actor.actor_id, grant_id, grant_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise ActionError("not_found", "business_record_not_found")
    capabilities = frozenset(row["capabilities"])
    if actor.actor_kind != "member":
        capabilities &= {"read", "prepare"}
    return Authorization(
        context=ActionContext(actor, row["id"], row["owner_id"], row["name"]),
        provenance=ActorProvenance(
            actor_id=actor.actor_id,
            actor_kind=actor.actor_kind,
            display_name=row["actor_name"],
            grant_id=row["id"],
            issuer_id=row["issuer_id"],
            issuer_display_name=row["issuer_name"],
        ),
        capabilities=capabilities,
    )


class BusinessAuthority:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def resolve_actor(
        self, actor: TrustedActor, *, grant_id: UUID | None = None
    ) -> ActionContext:
        with self.pool.connection() as connection, connection.transaction():
            return authorize(connection, actor, grant_id).context

    def for_record(
        self, actor_id: UUID, record_id: UUID, *, receipt: bool
    ) -> ActionContext:
        table = "financial_source_connections" if receipt else "financial_import_events"
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                sql.SQL("select owner_space_id from public.{} where id=%s").format(
                    sql.Identifier(table)
                ),
                (record_id,),
            ).fetchone()
            if row is None or row[0] is None:
                raise ActionError("not_found", "business_record_not_found")
            return authorize(
                connection,
                TrustedActor(actor_id=actor_id, actor_kind="member", space_id=row[0]),
            ).context
