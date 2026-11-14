"""pg_catalog sweep of everything an auth.users delete can reach (Lane 6).

The sweep reads the live catalog of a database with every migration applied,
so it cannot drift from the schema. It is shared by the real-Postgres census
test and by ``python -m tests.account_deletion_census`` which prints the rows in
the census document's table format.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Platform schemas: internal keys are classified separately. Every edge that
# crosses the application boundary remains in the census, in either direction.
PLATFORM_SCHEMAS = (
    "auth",
    "storage",
    "realtime",
    "_realtime",
    "graphql",
    "graphql_public",
    "vault",
    "pgsodium",
    "pgsodium_masks",
    "supabase_functions",
    "supabase_migrations",
    "net",
    "cron",
    "extensions",
    "pgbouncer",
    "_analytics",
    "pg_catalog",
    "information_schema",
    "pg_toast",
)

ACTIONS = {
    "a": "NO ACTION",
    "r": "RESTRICT",
    "c": "CASCADE",
    "n": "SET NULL",
    "d": "SET DEFAULT",
}
BLOCKING = {"NO ACTION", "RESTRICT"}

# A uuid column whose name says it holds a person or a membership.
USER_COLUMN = re.compile(
    r"^(user_id|owner_id|actor_id|recorded_by|created_by|accepted_by|claimed_by)$"
    r"|_(user|owner)_id$|(^|_)membership_id$"
)

# Plan history that is protected after the fact (decision 17's "protected plan
# history"): append-only revisions and the departure archives that pin them.
PROTECTED_HISTORY = frozenset(
    {
        "public.financial_activity_revisions",
        "public.financial_record_revisions",
        "public.financial_plan_definition_revisions",
        "public.financial_goal_allocation_revisions",
        "public.household_plan_archived_claims",
        "public.household_plan_archived_allocations",
        "public.household_plan_archived_activities",
    }
)


@dataclass(frozen=True)
class ForeignKey:
    name: str
    table: str
    columns: tuple[str, ...]
    referenced: str
    referenced_columns: tuple[str, ...]
    on_delete: str
    on_update: str
    match_full: bool
    deferrable: bool
    initially_deferred: bool
    hops: int

    @property
    def blocks(self) -> bool:
        return self.on_delete in BLOCKING

    @property
    def deferral(self) -> str:
        if not self.deferrable:
            return "no"
        return "initially deferred" if self.initially_deferred else "deferrable"

    @property
    def key(self) -> tuple[str, ...]:
        return (
            self.table,
            ",".join(self.columns),
            self.referenced,
            ",".join(self.referenced_columns),
            "FULL" if self.match_full else "SIMPLE",
            self.on_delete,
            self.on_update,
            self.deferral,
        )

    @property
    def owner_columns(self) -> tuple[str, ...]:
        if self.referenced == "auth.users":
            return self.columns
        return tuple(c for c in self.columns if USER_COLUMN.search(c))

    def rekey(self, nullable: set[tuple[str, str]]) -> str:
        """What moving this key's owner side to a placeholder takes."""
        owners = self.owner_columns
        if not owners:
            return "No owner column."
        if self.referenced == "auth.users":
            column = owners[0]
            tail = (
                " The column is nullable, so it can be set to null instead."
                if (self.table, column) in nullable
                else " The column is `not null`."
            )
            return (
                "Points straight at `auth.users`: a placeholder id must be a real "
                "`auth.users` row, or this key must change." + tail
            )
        if all(c.endswith("membership_id") for c in owners):
            return (
                "Keyed by membership id, not user id: re-point it to the "
                "person's placeholder membership in its household, keyed to that "
                "household's placeholder `auth.users` row (never nulled)."
            )
        if len(self.columns) == 1:
            return (
                f"Single-column key to `{self.referenced.removeprefix('public.')}`, "
                "not a composite owner key. The row follows that parent: it goes "
                "with the person's own rows, or is re-pointed to a placeholder's "
                "parent row."
            )
        if self.on_update == "CASCADE":
            return "Follows the parent's owner id through ON UPDATE CASCADE."
        if self.deferrable:
            return (
                f"Composite owner key, ON UPDATE {self.on_update}, deferrable: "
                "move the parent and its children to the new owner in place, in "
                "one transaction, keeping ids and revisions. The new id must "
                "still reach `auth.users` through the parent."
            )
        return (
            f"Composite owner key, ON UPDATE {self.on_update}, not deferrable: "
            "neither side can change its owner id first. Moving it, to a new plan "
            "owner or a household's placeholder, needs this key made DEFERRABLE "
            "INITIALLY IMMEDIATE (not ON UPDATE CASCADE): update the parent and "
            "its children in place, keeping ids and revisions. The new id must "
            "also reach `auth.users` through the parent."
        )


@dataclass(frozen=True)
class UserColumn:
    table: str
    column: str
    nullable: bool
    covered_by: tuple[str, ...]  # "referenced_table ACTION" per covering FK


_EXCLUDED = "array[" + ",".join(f"'{s}'" for s in PLATFORM_SCHEMAS) + "]::text[]"

_SWEEP = f"""
with recursive
fk as (
  select c.oid, c.conname, c.conrelid, c.confrelid, c.conkey, c.confkey,
         c.confdeltype, c.confupdtype, c.confmatchtype, c.condeferrable,
         c.condeferred, n.nspname as source_schema, rn.nspname as target_schema
    from pg_constraint c
    join pg_class r on r.oid = c.conrelid
    join pg_namespace n on n.oid = r.relnamespace
    join pg_class rr on rr.oid = c.confrelid
    join pg_namespace rn on rn.oid = rr.relnamespace
   where c.contype = 'f'
),
reach(rel, hops) as (
  select 'auth.users'::regclass::oid, 0
  union
  select fk.conrelid, reach.hops + 1
    from fk join reach on fk.confrelid = reach.rel
   where reach.hops < 20
),
depth as (select rel, min(hops) as hops from reach group by rel)
select fk.conname,
       fk.conrelid::regclass::text,
       array(select a.attname::text from unnest(fk.conkey) with ordinality k(n, o)
              join pg_attribute a on a.attrelid = fk.conrelid and a.attnum = k.n
             order by k.o),
       fk.confrelid::regclass::text,
       array(select a.attname::text from unnest(fk.confkey) with ordinality k(n, o)
              join pg_attribute a on a.attrelid = fk.confrelid and a.attnum = k.n
             order by k.o),
       fk.confdeltype::text,
       fk.confupdtype::text,
       fk.confmatchtype = 'f',
       fk.condeferrable,
       fk.condeferred,
       coalesce(d.hops + 1, 0)
  from fk left join depth d on d.rel = fk.confrelid
 where d.rel is not null or fk.source_schema = any({_EXCLUDED})
       or fk.target_schema = any({_EXCLUDED})
 order by 2, 3, 4
"""

_COLUMNS = f"""
select n.nspname || '.' || c.relname, a.attname::text, not a.attnotnull
  from pg_attribute a
  join pg_class c on c.oid = a.attrelid and c.relkind in ('r', 'p')
  join pg_namespace n on n.oid = c.relnamespace
 where a.attnum > 0 and not a.attisdropped and a.atttypid = 'uuid'::regtype
   and n.nspname <> all({_EXCLUDED})
 order by 1, 2
"""


def _qualified(name: str) -> str:
    return name if "." in name else "public." + name


def catalog_keys(connection) -> list[ForeignKey]:  # noqa: ANN001
    """Auth-reachable keys plus every system-schema key, even outside that graph."""
    rows = connection.execute(_SWEEP).fetchall()
    return [
        ForeignKey(
            name=name,
            table=_qualified(table),
            columns=tuple(columns),
            referenced=_qualified(referenced),
            referenced_columns=tuple(referenced_columns),
            on_delete=ACTIONS[action],
            on_update=ACTIONS[update],
            match_full=match_full,
            deferrable=deferrable,
            initially_deferred=deferred,
            hops=hops,
        )
        for (
            name,
            table,
            columns,
            referenced,
            referenced_columns,
            action,
            update,
            match_full,
            deferrable,
            deferred,
            hops,
        ) in rows
    ]


def sweep(connection) -> list[ForeignKey]:  # noqa: ANN001
    """Traverse every schema; exclude only edges internal to platform schemas."""
    return [k for k in catalog_keys(connection) if not platform_internal(k)]


def platform_internal(key: ForeignKey) -> bool:
    return all(t.split(".")[0] in PLATFORM_SCHEMAS for t in (key.table, key.referenced))


# These carriers cannot be inferred from a uuid type or a column name. Their
# physical columns and types are still checked against the database catalog.
KNOWN_CARRIERS = (
    ("public.visitor_usage_counters", "visitor_key", "user:<id>"),
    ("public.argus_memory_vectors", "payload", "user_id"),
    ("public.financial_plan_links", "attribution", "destination_owner_id"),
)


def known_carriers(connection) -> list[tuple[str, str, str, str]]:  # noqa: ANN001
    result = []
    for table, column, selector in KNOWN_CARRIERS:
        row = connection.execute(
            "select format_type(atttypid, atttypmod) from pg_attribute "
            "where attrelid=to_regclass(%s) and attname=%s and not attisdropped",
            (table, column),
        ).fetchone()
        if row:
            result.append((table, column, row[0], selector))
    return result


def schema_snapshot(connection) -> tuple:  # noqa: ANN001
    """Definitions and enabled state, including checks, triggers and nullability."""
    constraints = connection.execute(
        "select conrelid::regclass::text, conname, contype, "
        "pg_get_constraintdef(oid, false), convalidated "
        "from pg_constraint order by 1, 2, 3"
    ).fetchall()
    triggers = connection.execute(
        "select tgrelid::regclass::text, tgname, pg_get_triggerdef(oid, false), "
        "tgenabled, pg_get_functiondef(tgfoid) from pg_trigger order by 1, 2"
    ).fetchall()
    columns = connection.execute(
        "select attrelid::regclass::text, attname, attnotnull "
        "from pg_attribute where attnum > 0 and not attisdropped order by 1, 2"
    ).fetchall()
    return tuple(constraints), tuple(triggers), tuple(columns)


def user_columns(connection, keys: list[ForeignKey]) -> list[UserColumn]:  # noqa: ANN001
    """Every uuid column named for a person or membership, or keyed to auth.users."""
    direct = {
        (k.table, c) for k in keys if k.referenced == "auth.users" for c in k.columns
    }
    result = []
    for table, column, nullable in connection.execute(_COLUMNS).fetchall():
        if not USER_COLUMN.search(column) and (table, column) not in direct:
            continue
        covering = tuple(
            f"{k.referenced} {k.on_delete}"
            for k in keys
            if k.table == table and column in k.columns
        )
        result.append(UserColumn(table, column, nullable, covering))
    return result


def markdown_rows(keys: list[ForeignKey], nullable: set[tuple[str, str]]) -> list[str]:
    """Census rows for the document; the probe and Lane 6 cells are left TODO."""
    return [
        f"| `{k.table.removeprefix('public.')}` | `{', '.join(k.columns)}` "
        f"| `{k.referenced.removeprefix('public.')}` | `{', '.join(k.referenced_columns)}` "
        f"| {'FULL' if k.match_full else 'SIMPLE'} | {k.on_delete} | {k.on_update} "
        f"| {k.deferral} | {k.rekey(nullable)} | TODO | TODO |"
        for k in keys
    ]


def nullable_columns(columns: list[UserColumn]) -> set[tuple[str, str]]:
    return {(c.table, c.column) for c in columns if c.nullable}


def markdown_system_rows(keys: list[ForeignKey]) -> list[str]:
    """List each system-schema key, including explicitly excluded internal edges."""
    return [
        f"| `{k.table}` | `{k.name}` | `{k.referenced}` | "
        f"{'out of scope: platform internal' if platform_internal(k) else 'swept'} |"
        for k in keys
        if any(t.split(".")[0] in PLATFORM_SCHEMAS for t in (k.table, k.referenced))
    ]


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    import psycopg

    with psycopg.connect(os.environ["ARGUS_DISPOSABLE_DATABASE_URL"]) as conn:
        found = sweep(conn)
        print("\n".join(markdown_system_rows(catalog_keys(conn))))
        print(
            "\n".join(markdown_rows(found, nullable_columns(user_columns(conn, found))))
        )
