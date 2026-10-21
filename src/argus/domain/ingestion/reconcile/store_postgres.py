"""Postgres backend for reconciliation, one transaction per person.

``transaction`` takes a transaction-scoped advisory lock on the person, so
concurrent webhook syncs, Shortcuts deliveries and review actions for one
person apply in order and matching never reads a half-written event.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.ingestion.reconcile.model import (
    AccountLink,
    EventNotFound,
    ImportEvent,
    Observation,
)
from argus.domain.ingestion.reconcile.store import ImportTx
from argus.domain.owner_scope import OwnerScope, space_id, sql_predicate

_EVENT = (
    "id::text, user_id::text, state, evidence, anchor_on, attention, attention_detail, "
    "possible_duplicates::text[] as possible_duplicates, resolution, "
    "activity_id::text, accept_key, created_at, updated_at, version"
)
_OBS = (
    "id::text, user_id::text, event_id::text, connection_id::text, source, external_id, "
    "fingerprint, candidate, live, revisions, first_seen_at, updated_at"
)


class _PostgresTx:
    def __init__(self, connection: Connection, user_id: str, scope: OwnerScope) -> None:
        self._c = connection
        self._user = user_id
        self._space = space_id(scope)
        # Events are the scoped root here; observations and links follow
        # their event or connection.
        self._in_scope, self._scope_params = sql_predicate(scope, "owner_space_id")

    def _rows(self, statement: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._c.cursor(row_factory=dict_row) as cursor:
            cursor.execute(statement, params)
            return list(cursor.fetchall()) if cursor.description else []

    def observation(self, connection_id: str, external_id: str) -> Observation | None:
        rows = self._rows(
            f"""select {_OBS} from public.financial_import_observations
            where user_id = %s and connection_id = %s::uuid and external_id = %s""",
            (self._user, connection_id, external_id),
        )
        return _observation(rows[0]) if rows else None

    def observations(self, event_id: str) -> list[Observation]:
        return [
            _observation(r)
            for r in self._rows(
                f"""select {_OBS} from public.financial_import_observations
                where user_id = %s and event_id = %s::uuid order by first_seen_at, id""",
                (self._user, event_id),
            )
        ]

    def connection_observations(self, connection_id: str) -> list[Observation]:
        return [
            _observation(r)
            for r in self._rows(
                f"""select {_OBS} from public.financial_import_observations
                where user_id = %s and connection_id = %s::uuid""",
                (self._user, connection_id),
            )
        ]

    def event(self, event_id: str) -> ImportEvent:
        try:
            event_id = str(uuid.UUID(event_id))
        except (ValueError, TypeError):
            raise EventNotFound() from None
        rows = self._rows(
            f"""select {_EVENT} from public.financial_import_events
            where user_id = %s and id = %s::uuid and {self._in_scope}""",
            (self._user, event_id, *self._scope_params),
        )
        if not rows:
            raise EventNotFound()
        return _event(rows[0])

    def nearby(self, start: date, end: date) -> list[ImportEvent]:
        return [
            _event(r)
            for r in self._rows(
                f"""select {_EVENT} from public.financial_import_events
                where user_id = %s and anchor_on between %s and %s
                and {self._in_scope}""",
                (self._user, start, end, *self._scope_params),
            )
        ]

    def events(self, states: tuple[str, ...]) -> list[ImportEvent]:
        return [
            _event(r)
            for r in self._rows(
                f"""select {_EVENT} from public.financial_import_events
                where user_id = %s and state = any(%s) and {self._in_scope}
                order by created_at, id""",
                (self._user, list(states), *self._scope_params),
            )
        ]

    def activity_links(self) -> dict[str, str]:
        rows = self._rows(
            f"""select activity_id::text as activity_id, id::text as event_id
            from public.financial_import_events
            where user_id = %s and activity_id is not null and {self._in_scope}""",
            (self._user, *self._scope_params),
        )
        return {r["activity_id"]: r["event_id"] for r in rows}

    def links(self) -> dict[tuple[str, str], str]:
        rows = self._rows(
            """select connection_id::text as connection_id, account_key,
                account_id::text as account_id
            from public.financial_import_account_links where user_id = %s""",
            (self._user,),
        )
        return {(r["connection_id"], r["account_key"]): r["account_id"] for r in rows}

    def put_event(self, e: ImportEvent) -> None:
        self._rows(
            """insert into public.financial_import_events
                (id, user_id, state, evidence, anchor_on, attention, attention_detail,
                 possible_duplicates, resolution, activity_id, accept_key,
                 created_at, updated_at, version, owner_space_id)
            values (%s, %s, %s, %s, %s, %s, %s, %s::uuid[], %s, %s, %s, %s, %s, %s, %s)
            on conflict (id) do update set
                state = excluded.state, evidence = excluded.evidence,
                anchor_on = excluded.anchor_on, attention = excluded.attention,
                attention_detail = excluded.attention_detail,
                possible_duplicates = excluded.possible_duplicates,
                resolution = excluded.resolution, activity_id = excluded.activity_id,
                accept_key = excluded.accept_key, updated_at = excluded.updated_at,
                version = excluded.version
            where financial_import_events.user_id = excluded.user_id
            and financial_import_events.owner_space_id
                is not distinct from excluded.owner_space_id""",
            (
                e.id,
                self._user,
                e.state,
                e.evidence,
                e.anchor_on,
                e.attention,
                Jsonb(e.attention_detail) if e.attention_detail is not None else None,
                list(e.possible_duplicates),
                Jsonb(e.resolution),
                e.activity_id,
                e.accept_key,
                e.created_at,
                e.updated_at,
                e.version,
                self._space,
            ),
        )

    def delete_event(self, event_id: str) -> None:
        self._rows(
            "delete from public.financial_import_events"
            f" where user_id = %s and id = %s::uuid and {self._in_scope}",
            (self._user, event_id, *self._scope_params),
        )

    def put_observation(self, o: Observation) -> None:
        self._rows(
            """insert into public.financial_import_observations
                (id, user_id, event_id, connection_id, source, external_id, fingerprint,
                 candidate, live, revisions, first_seen_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (id) do update set
                event_id = excluded.event_id, fingerprint = excluded.fingerprint,
                candidate = excluded.candidate, live = excluded.live,
                revisions = excluded.revisions, updated_at = excluded.updated_at
            where financial_import_observations.user_id = excluded.user_id""",
            (
                o.id,
                self._user,
                o.event_id,
                o.connection_id,
                o.source,
                o.external_id,
                o.fingerprint,
                Jsonb(o.candidate),
                o.live,
                o.revisions,
                o.first_seen_at,
                o.updated_at,
            ),
        )

    def delete_observation(self, observation_id: str) -> None:
        self._rows(
            """delete from public.financial_import_observations
            where user_id = %s and id = %s::uuid""",
            (self._user, observation_id),
        )

    def put_link(self, link: AccountLink) -> None:
        self._rows(
            """insert into public.financial_import_account_links
                (user_id, connection_id, account_key, account_id, created_at)
            values (%s, %s, %s, %s, %s)
            on conflict (user_id, connection_id, account_key)
            do update set account_id = excluded.account_id""",
            (
                self._user,
                link.connection_id,
                link.account_key,
                link.account_id,
                link.created_at,
            ),
        )

    def delete_links(self, connection_id: str) -> None:
        self._rows(
            """delete from public.financial_import_account_links
            where user_id = %s and connection_id = %s::uuid""",
            (self._user, connection_id),
        )

    def account_shared(self, account_id: str) -> bool:
        rows = self._rows(
            """select exists (
                select 1 from public.household_account_grants
                where account_id = %s::uuid and owner_user_id = %s and revoked_at is null
            ) as shared""",
            (account_id, self._user),
        )
        return bool(rows and rows[0]["shared"])


class PostgresImportStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @contextmanager
    def transaction(self, user_id: str, *, scope: OwnerScope) -> Iterator[ImportTx]:
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"financial_import:{user_id}",),
            )
            yield _PostgresTx(connection, user_id, scope)


def _event(r: dict[str, Any]) -> ImportEvent:
    return ImportEvent(
        id=r["id"],
        user_id=r["user_id"],
        state=r["state"],
        evidence=r["evidence"],
        anchor_on=r["anchor_on"],
        attention=r["attention"],
        attention_detail=r["attention_detail"],
        possible_duplicates=tuple(r["possible_duplicates"] or ()),
        resolution=r["resolution"] or {},
        activity_id=r["activity_id"],
        accept_key=r["accept_key"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        version=r["version"],
    )


def _observation(r: dict[str, Any]) -> Observation:
    return Observation(
        id=r["id"],
        user_id=r["user_id"],
        event_id=r["event_id"],
        connection_id=r["connection_id"],
        source=r["source"],
        external_id=r["external_id"],
        fingerprint=r["fingerprint"],
        candidate=r["candidate"],
        live=r["live"],
        revisions=r["revisions"],
        first_seen_at=r["first_seen_at"],
        updated_at=r["updated_at"],
    )
