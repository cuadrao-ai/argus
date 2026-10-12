"""Durable receiving queue: one row per provider message, claimed under a lease.

A delivery is bound to its route when it is enqueued and never moves. Parts are
upserted per attachment so a retry resumes only what is still pending."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator, Protocol, TypedDict
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.ingestion.email_intake.models import (
    EmailDelivery,
    EmailDeliveryPart,
    RecipientRoute,
)

MAX_ATTEMPTS = 8
LEASE = timedelta(seconds=120)
FINAL_STATES = ("partial", "captured", "rejected")


class EmailRelation(TypedDict):
    original: bool
    delivery_ids: set[str]


class LeaseLost(RuntimeError):
    pass


class EmailStore(Protocol):
    def create_route(
        self,
        *,
        recipient: str,
        space_id: str,
        principal_id: str,
        granted_by: str,
        grant_id: str,
    ) -> RecipientRoute: ...

    def deactivate_routes(self, space_id: str) -> int: ...

    def routes(self, recipients: tuple[str, ...]) -> list[RecipientRoute]: ...

    def route_for_space(self, space_id: str) -> RecipientRoute | None: ...

    def locked_route(self, route_id: str) -> Iterator[RecipientRoute | None]: ...

    def enqueue(
        self,
        provider: str,
        external_id: str,
        recipients: tuple[str, ...],
        *,
        route_id: str | None = None,
        space_id: str | None = None,
        principal_id: str | None = None,
    ) -> EmailDelivery: ...

    def reject_unclaimed(self, delivery_id: str, code: str) -> EmailDelivery: ...

    def claim(self, *, delivery_id: str | None = None) -> EmailDelivery | None: ...

    def update(self, delivery: EmailDelivery, **values: object) -> None: ...

    def renew(self, delivery: EmailDelivery) -> None: ...

    def finish(
        self, delivery: EmailDelivery, state: str, error_code: str | None = None
    ) -> None: ...

    def put_part(self, delivery: EmailDelivery, part: EmailDeliveryPart) -> None: ...

    def parts(self, delivery_id: str) -> list[EmailDeliveryPart]: ...

    def list(self, space_id: str, *, limit: int = 50) -> list[EmailDelivery]: ...

    def get(self, delivery_id: str, space_id: str) -> EmailDelivery | None: ...

    def retry(self, delivery_id: str, space_id: str) -> bool: ...

    def membership(self, space_id: str) -> dict[str, EmailRelation]: ...


_UPDATABLE = {"original_document_id", "subject", "sender", "sent_at", "text_body"}


def _delivery(row: dict) -> EmailDelivery:
    values = {field.name: row[field.name] for field in fields(EmailDelivery)}
    for key in (
        "id",
        "route_id",
        "space_id",
        "principal_id",
        "original_document_id",
        "lease_token",
    ):
        if values[key] is not None:
            values[key] = str(values[key])
    values["recipients"] = tuple(values["recipients"])
    return EmailDelivery(**values)


def _route(row: dict) -> RecipientRoute:
    return RecipientRoute(
        **{
            key: value if key == "active" else str(value)
            for key, value in row.items()
            if key in {field.name for field in fields(RecipientRoute)}
        }
    )


class PostgresEmailStore:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def create_route(self, *, recipient, space_id, principal_id, granted_by, grant_id):
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            row = cursor.execute(
                "insert into public.business_email_routes(recipient,space_id,principal_id,granted_by,grant_id) "
                "values(%s,%s,%s,%s,%s) returning *",
                (recipient, space_id, principal_id, granted_by, grant_id),
            ).fetchone()
            return _route(row)

    def deactivate_routes(self, space_id: str) -> int:
        with self.pool.connection() as connection:
            return connection.execute(
                "update public.business_email_routes set active=false where space_id=%s and active",
                (space_id,),
            ).rowcount

    def routes(self, recipients: tuple[str, ...]) -> list[RecipientRoute]:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            return [
                _route(row)
                for row in cursor.execute(
                    "select * from public.business_email_routes where recipient=any(%s) and active",
                    (list(recipients),),
                ).fetchall()
            ]

    def route_for_space(self, space_id: str) -> RecipientRoute | None:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            row = cursor.execute(
                "select * from public.business_email_routes where space_id=%s and active order by created_at limit 1",
                (space_id,),
            ).fetchone()
            return _route(row) if row else None

    @contextmanager
    def locked_route(self, route_id: str) -> Iterator[RecipientRoute | None]:
        with (
            self.pool.connection() as connection,
            connection.transaction(),
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            row = cursor.execute(
                "select * from public.business_email_routes where id=%s for share",
                (route_id,),
            ).fetchone()
            yield _route(row) if row else None

    def enqueue(
        self,
        provider,
        external_id,
        recipients,
        *,
        route_id=None,
        space_id=None,
        principal_id=None,
    ):
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            row = cursor.execute(
                "insert into public.business_email_deliveries(provider,external_id,recipients,route_id,space_id,principal_id) "
                "values(%s,%s,%s,%s,%s,%s) on conflict(provider,external_id) do update "
                "set external_id=excluded.external_id returning *",
                (
                    provider,
                    external_id,
                    Jsonb(list(recipients)),
                    route_id,
                    space_id,
                    principal_id,
                ),
            ).fetchone()
            return _delivery(row)

    def reject_unclaimed(self, delivery_id: str, code: str) -> EmailDelivery:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                "update public.business_email_deliveries set state='rejected',error_code=%s,updated_at=now() "
                "where id=%s and state='received' and lease_token is null and route_id is null",
                (code, delivery_id),
            )
            row = cursor.execute(
                "select * from public.business_email_deliveries where id=%s",
                (delivery_id,),
            ).fetchone()
            return _delivery(row)

    def claim(self, *, delivery_id: str | None = None) -> EmailDelivery | None:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            # A worker that died on its last allowed attempt leaves a retryable row, not a stuck one.
            cursor.execute(
                "update public.business_email_deliveries set state='partial',lease_token=null,lease_until=null,"
                "error_code='email_worker_interrupted',updated_at=now() "
                "where state='processing' and attempts>=%s and lease_until<now()",
                (MAX_ATTEMPTS,),
            )
            row = cursor.execute(
                "with next as (select id from public.business_email_deliveries where state in ('received','processing','partial') "
                "and route_id is not null and attempts<%s and available_at<=now() and (lease_until is null or lease_until<now()) "
                "and (%s::uuid is null or id=%s) order by received_at for update skip locked limit 1) "
                "update public.business_email_deliveries d set state='processing',lease_token=%s,lease_until=now()+interval '120 seconds',"
                "attempts=attempts+1,updated_at=now() from next where d.id=next.id returning d.*",
                (MAX_ATTEMPTS, delivery_id, delivery_id, str(uuid4())),
            ).fetchone()
            return _delivery(row) if row else None

    def update(self, delivery: EmailDelivery, **values: object) -> None:
        if not values or set(values) - _UPDATABLE:
            raise ValueError("invalid_email_update")
        assignments = ",".join(f"{key}=%s" for key in values)
        with self.pool.connection() as connection:
            changed = connection.execute(
                f"update public.business_email_deliveries set {assignments},updated_at=now(),lease_until=now()+interval '120 seconds' "
                "where id=%s and lease_token=%s and lease_until>now() and state='processing'",
                (*values.values(), delivery.id, delivery.lease_token),
            ).rowcount
            if changed != 1:
                raise LeaseLost()

    def renew(self, delivery: EmailDelivery) -> None:
        with self.pool.connection() as connection:
            changed = connection.execute(
                "update public.business_email_deliveries set lease_until=now()+interval '120 seconds' "
                "where id=%s and lease_token=%s and lease_until>now() and state='processing'",
                (delivery.id, delivery.lease_token),
            ).rowcount
            if changed != 1:
                raise LeaseLost()

    def finish(
        self, delivery: EmailDelivery, state: str, error_code: str | None = None
    ) -> None:
        if state not in FINAL_STATES:
            raise ValueError("invalid_email_state")
        with self.pool.connection() as connection:
            changed = connection.execute(
                "update public.business_email_deliveries set state=%s,error_code=%s,lease_token=null,lease_until=null,updated_at=now(),"
                "available_at=now()+least(attempts*10,300)*interval '1 second' where id=%s and lease_token=%s and lease_until>now()",
                (state, error_code, delivery.id, delivery.lease_token),
            ).rowcount
            if changed != 1:
                raise LeaseLost()

    def put_part(self, delivery: EmailDelivery, part: EmailDeliveryPart) -> None:
        with self.pool.connection() as connection, connection.transaction():
            held = connection.execute(
                "select id from public.business_email_deliveries where id=%s and lease_token=%s and lease_until>now() and state='processing' for update",
                (delivery.id, delivery.lease_token),
            ).fetchone()
            if not held:
                raise LeaseLost()
            connection.execute(
                "insert into public.business_email_parts(delivery_id,id,filename,media_type,state,document_id,error_code) "
                "values(%s,%s,%s,%s,%s,%s,%s) on conflict(delivery_id,id) do update "
                "set state=excluded.state,document_id=excluded.document_id,error_code=excluded.error_code",
                (
                    delivery.id,
                    part.id,
                    part.filename,
                    part.media_type,
                    part.state,
                    part.document_id,
                    part.error_code,
                ),
            )

    def parts(self, delivery_id: str) -> list[EmailDeliveryPart]:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            rows = cursor.execute(
                "select id,filename,media_type,state,document_id::text,error_code from public.business_email_parts where delivery_id=%s order by id",
                (delivery_id,),
            ).fetchall()
            return [EmailDeliveryPart(**row) for row in rows]

    def list(self, space_id: str, *, limit: int = 50) -> list[EmailDelivery]:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            rows = cursor.execute(
                "select * from public.business_email_deliveries where space_id=%s order by received_at desc,id limit %s",
                (space_id, limit),
            ).fetchall()
            return [_delivery(row) for row in rows]

    def get(self, delivery_id: str, space_id: str) -> EmailDelivery | None:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            row = cursor.execute(
                "select * from public.business_email_deliveries where id=%s and space_id=%s",
                (delivery_id, space_id),
            ).fetchone()
            return _delivery(row) if row else None

    def retry(self, delivery_id: str, space_id: str) -> bool:
        with self.pool.connection() as connection:
            return (
                connection.execute(
                    "update public.business_email_deliveries set attempts=0,available_at=now(),updated_at=now() "
                    "where id=%s and space_id=%s and state='partial' and lease_token is null",
                    (delivery_id, space_id),
                ).rowcount
                == 1
            )

    def membership(self, space_id: str) -> dict[str, EmailRelation]:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            rows = cursor.execute(
                "select d.id::text, d.original_document_id::text, p.document_id::text "
                "from public.business_email_deliveries d left join public.business_email_parts p "
                "on p.delivery_id=d.id where d.space_id=%s",
                (space_id,),
            ).fetchall()
        return _relations(rows)


def _relations(rows: list[dict]) -> dict[str, EmailRelation]:
    found: dict[str, EmailRelation] = {}
    for row in rows:
        for key, original in (("original_document_id", True), ("document_id", False)):
            document = row[key]
            if document:
                entry = found.setdefault(
                    document, {"original": False, "delivery_ids": set()}
                )
                entry["original"] |= original
                entry["delivery_ids"].add(row["id"])
    return found


class InMemoryEmailStore:
    """The same queue rules in memory, for the offline suite and the local app."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._routes: dict[str, RecipientRoute] = {}
        self._deliveries: dict[str, EmailDelivery] = {}
        self._available: dict[str, datetime] = {}
        self._lease_until: dict[str, datetime] = {}
        self._parts: dict[str, dict[str, EmailDeliveryPart]] = {}

    def create_route(self, *, recipient, space_id, principal_id, granted_by, grant_id):
        if any(route.recipient == recipient for route in self._routes.values()):
            raise ValueError("email_route_exists")
        route = RecipientRoute(
            str(uuid4()), recipient, space_id, principal_id, granted_by, grant_id, True
        )
        self._routes[route.id] = route
        return route

    def deactivate_routes(self, space_id: str) -> int:
        changed = 0
        for key, route in self._routes.items():
            if route.space_id == space_id and route.active:
                self._routes[key] = replace(route, active=False)
                changed += 1
        return changed

    def routes(self, recipients):
        return [
            r for r in self._routes.values() if r.active and r.recipient in recipients
        ]

    def route_for_space(self, space_id):
        return next(
            (r for r in self._routes.values() if r.active and r.space_id == space_id),
            None,
        )

    @contextmanager
    def locked_route(self, route_id):
        yield self._routes.get(route_id)

    def enqueue(
        self,
        provider,
        external_id,
        recipients,
        *,
        route_id=None,
        space_id=None,
        principal_id=None,
    ):
        for existing in self._deliveries.values():
            if (existing.provider, existing.external_id) == (provider, external_id):
                return existing
        now = self.clock()
        delivery = EmailDelivery(
            str(uuid4()),
            provider,
            external_id,
            tuple(recipients),
            route_id,
            space_id,
            principal_id,
            "received",
            None,
            now,
            now,
            None,
            0,
            None,
            None,
            None,
            None,
            None,
        )
        self._deliveries[delivery.id] = delivery
        self._available[delivery.id] = now
        return delivery

    def reject_unclaimed(self, delivery_id, code):
        delivery = self._deliveries[delivery_id]
        if (
            delivery.state == "received"
            and delivery.lease_token is None
            and delivery.route_id is None
        ):
            self._deliveries[delivery_id] = replace(
                delivery, state="rejected", error_code=code, updated_at=self.clock()
            )
        return self._deliveries[delivery_id]

    def _lease_live(self, delivery_id: str) -> bool:
        until = self._lease_until.get(delivery_id)
        return until is not None and until > self.clock()

    def claim(self, *, delivery_id=None):
        now = self.clock()
        for key, delivery in list(self._deliveries.items()):
            if (
                delivery.state == "processing"
                and delivery.attempts >= MAX_ATTEMPTS
                and not self._lease_live(key)
            ):
                self._deliveries[key] = replace(
                    delivery,
                    state="partial",
                    lease_token=None,
                    error_code="email_worker_interrupted",
                    updated_at=now,
                )
                self._lease_until.pop(key, None)
        candidates = sorted(
            (
                d
                for d in self._deliveries.values()
                if d.state in ("received", "processing", "partial")
                and d.route_id is not None
                and d.attempts < MAX_ATTEMPTS
                and self._available[d.id] <= now
                and not self._lease_live(d.id)
                and (delivery_id is None or d.id == delivery_id)
            ),
            key=lambda d: d.received_at,
        )
        if not candidates:
            return None
        delivery = replace(
            candidates[0],
            state="processing",
            lease_token=str(uuid4()),
            attempts=candidates[0].attempts + 1,
            updated_at=now,
        )
        self._deliveries[delivery.id] = delivery
        self._lease_until[delivery.id] = now + LEASE
        return delivery

    def _held(self, delivery: EmailDelivery) -> EmailDelivery:
        current = self._deliveries.get(delivery.id)
        if (
            current is None
            or current.state != "processing"
            or current.lease_token != delivery.lease_token
            or not self._lease_live(delivery.id)
        ):
            raise LeaseLost()
        return current

    def update(self, delivery, **values):
        if not values or set(values) - _UPDATABLE:
            raise ValueError("invalid_email_update")
        current = self._held(delivery)
        self._deliveries[delivery.id] = replace(
            current, updated_at=self.clock(), **values
        )
        self._lease_until[delivery.id] = self.clock() + LEASE

    def renew(self, delivery):
        self._held(delivery)
        self._lease_until[delivery.id] = self.clock() + LEASE

    def finish(self, delivery, state, error_code=None):
        if state not in FINAL_STATES:
            raise ValueError("invalid_email_state")
        current = self._held(delivery)
        now = self.clock()
        self._deliveries[delivery.id] = replace(
            current, state=state, error_code=error_code, lease_token=None, updated_at=now
        )
        self._lease_until.pop(delivery.id, None)
        self._available[delivery.id] = now + timedelta(
            seconds=min(current.attempts * 10, 300)
        )

    def put_part(self, delivery, part):
        self._held(delivery)
        self._parts.setdefault(delivery.id, {})[part.id] = part

    def parts(self, delivery_id):
        return [
            self._parts.get(delivery_id, {})[key]
            for key in sorted(self._parts.get(delivery_id, {}))
        ]

    def list(self, space_id, *, limit=50):
        rows = [d for d in self._deliveries.values() if d.space_id == space_id]
        return sorted(rows, key=lambda d: (d.received_at, d.id), reverse=True)[:limit]

    def get(self, delivery_id, space_id):
        delivery = self._deliveries.get(delivery_id)
        return (
            delivery if delivery is not None and delivery.space_id == space_id else None
        )

    def retry(self, delivery_id, space_id):
        delivery = self.get(delivery_id, space_id)
        if (
            delivery is None
            or delivery.state != "partial"
            or delivery.lease_token is not None
        ):
            return False
        self._deliveries[delivery_id] = replace(
            delivery, attempts=0, updated_at=self.clock()
        )
        self._available[delivery_id] = self.clock()
        return True

    def membership(self, space_id):
        rows = []
        for delivery in self._deliveries.values():
            if delivery.space_id != space_id:
                continue
            parts = self.parts(delivery.id) or [None]
            for part in parts:
                rows.append(
                    {
                        "id": delivery.id,
                        "original_document_id": delivery.original_document_id,
                        "document_id": part.document_id if part else None,
                    }
                )
        return _relations(rows)
