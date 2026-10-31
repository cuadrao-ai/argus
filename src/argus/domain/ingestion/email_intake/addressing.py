"""Alias changes, retired addresses, and sender standing. Both stores."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from threading import RLock
from uuid import uuid4

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from argus.domain.ingestion.email_intake.alignment import bare_address
from argus.domain.ingestion.email_intake.models import RecipientRoute, route_from_row


class AliasTaken(RuntimeError):
    """The normalized alias is already on a route or retired forever."""


@dataclass(frozen=True)
class SenderRule:
    id: str
    space_id: str
    kind: str
    value: str
    status: str
    first_scan_at: datetime | None = None
    last_auth_result: str | None = None
    last_seen_at: datetime | None = None


@dataclass(frozen=True)
class AddressEvent:
    id: str
    space_id: str
    actor_id: str | None
    event_type: str
    old_address: str | None
    new_address: str | None
    created_at: datetime


@dataclass(frozen=True)
class RetiredAlias:
    route_id: str
    space_id: str
    principal_id: str
    recipient: str
    alias_normalized: str | None


def _event_address(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned or len(cleaned) > 254:
        raise ValueError("email_address_event_invalid")
    return cleaned


def _address_value(address: str | None) -> tuple[str, str] | None:
    if not address or address.count("@") != 1:
        return None
    local, domain = address.strip().lower().split("@", 1)
    if not local or not domain or " " in local or " " in domain:
        return None
    return f"{local}@{domain}", domain


class PostgresAddressing:
    def alias_taken(self, normalized: str, *, except_route_id: str | None = None) -> bool:
        with self.pool.connection() as connection, connection.cursor() as cursor:
            row = cursor.execute(
                "select ("
                "exists(select 1 from public.business_email_routes "
                "where alias_normalized=%s and (%s::uuid is null or id<>%s)) "
                "or exists(select 1 from public.business_email_retired_aliases "
                "where alias_normalized=%s))",
                (normalized, except_route_id, except_route_id, normalized),
            ).fetchone()
            return bool(row[0])

    def matching_retired(self, recipients: tuple[str, ...]) -> list[RetiredAlias]:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            rows = cursor.execute(
                "select r.route_id::text, route.space_id::text, route.principal_id::text, "
                "r.recipient, r.alias_normalized "
                "from public.business_email_retired_aliases r "
                "join public.business_email_routes route on route.id=r.route_id "
                "where r.recipient=any(%s)",
                (list(recipients),),
            ).fetchall()
        return [
            RetiredAlias(
                row["route_id"],
                row["space_id"],
                row["principal_id"],
                row["recipient"],
                row["alias_normalized"],
            )
            for row in rows
        ]

    def change_address(
        self,
        route_id: str,
        *,
        alias: str,
        alias_normalized: str,
        recipient: str,
        review_required: bool,
        actor_id: str | None = None,
    ) -> RecipientRoute:
        with (
            self.pool.connection() as connection,
            connection.transaction(),
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute("select pg_advisory_xact_lock(hashtext(%s))", (alias_normalized,))
            current = cursor.execute(
                "select * from public.business_email_routes where id=%s for update",
                (route_id,),
            ).fetchone()
            if current is None or not current["active"]:
                raise LookupError("email_route_unavailable")
            if (
                current["alias_normalized"] == alias_normalized
                and current["recipient"] == recipient
            ):
                return route_from_row(current)
            try:
                cursor.execute(
                    "insert into public.business_email_retired_aliases"
                    "(route_id, alias_normalized, recipient) values (%s,%s,%s)",
                    (route_id, current["alias_normalized"], current["recipient"]),
                )
                row = cursor.execute(
                    "update public.business_email_routes set alias=%s, alias_normalized=%s, "
                    "recipient=%s, review_required=%s where id=%s returning *",
                    (alias, alias_normalized, recipient, review_required, route_id),
                ).fetchone()
            except UniqueViolation:
                raise AliasTaken() from None
            self._write_event(
                cursor,
                current["space_id"],
                actor_id,
                "address_changed",
                current["recipient"],
                recipient,
            )
            return route_from_row(row)

    def _write_event(self, cursor, space_id, actor_id, event_type, old, new) -> None:  # noqa: ANN001
        cursor.execute(
            "insert into public.business_email_address_events"
            "(space_id, actor_id, event_type, old_address, new_address) "
            "values (%s,%s,%s,%s,%s)",
            (
                space_id,
                actor_id,
                event_type,
                _event_address(old),
                _event_address(new),
            ),
        )

    def address_events(self, space_id: str) -> list[AddressEvent]:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            rows = cursor.execute(
                "select id::text, space_id::text, actor_id::text, event_type, "
                "old_address, new_address, created_at "
                "from public.business_email_address_events where space_id=%s "
                "order by created_at, id",
                (space_id,),
            ).fetchall()
        return [AddressEvent(**row) for row in rows]

    def list_senders(self, space_id: str) -> list[SenderRule]:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            rows = cursor.execute(
                "select id::text, space_id::text, kind, value, status, first_scan_at, "
                "last_auth_result, last_seen_at from public.business_email_senders "
                "where space_id=%s order by created_at, id",
                (space_id,),
            ).fetchall()
        return [SenderRule(**row) for row in rows]

    def upsert_sender(
        self,
        space_id: str,
        kind: str,
        value: str,
        status: str,
        actor_id: str | None = None,
    ) -> SenderRule:
        event = "sender_authorized" if status == "authorized" else "sender_blocked"
        with (
            self.pool.connection() as connection,
            connection.transaction(),
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            row = cursor.execute(
                "insert into public.business_email_senders(space_id, kind, value, status) "
                "values (%s,%s,%s,%s) on conflict(space_id, kind, value) do update "
                "set status=excluded.status returning id::text, space_id::text, kind, value, "
                "status, first_scan_at, last_auth_result, last_seen_at",
                (space_id, kind, value, status),
            ).fetchone()
            self._write_event(
                cursor,
                space_id,
                actor_id,
                event,
                value if status == "blocked" else None,
                value,
            )
            return SenderRule(**row)

    def remove_sender(
        self, space_id: str, sender_id: str, actor_id: str | None = None
    ) -> SenderRule | None:
        with (
            self.pool.connection() as connection,
            connection.transaction(),
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            row = cursor.execute(
                "delete from public.business_email_senders where id=%s and space_id=%s "
                "returning id::text, space_id::text, kind, value, status, first_scan_at, "
                "last_auth_result, last_seen_at",
                (sender_id, space_id),
            ).fetchone()
            if row is None:
                return None
            self._write_event(
                cursor, space_id, actor_id, "sender_removed", row["value"], None
            )
            return SenderRule(**row)

    def has_sender_rules(self, space_id: str) -> bool:
        with self.pool.connection() as connection:
            row = connection.execute(
                "select 1 from public.business_email_senders where space_id=%s limit 1",
                (space_id,),
            ).fetchone()
            return row is not None

    def sender_standing(self, space_id: str, address: str | None) -> str:
        parsed = _address_value(bare_address(address))
        if parsed is None:
            return "new"
        full = parsed[0]
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            row = cursor.execute(
                "select status from public.business_email_senders "
                "where space_id=%s and kind='address' and value=%s",
                (space_id, full),
            ).fetchone()
        return row["status"] if row else "new"

    def claim_first_scan(self, space_id: str, address: str | None) -> bool:
        parsed = _address_value(bare_address(address))
        if parsed is None:
            return False
        full = parsed[0]
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "update public.business_email_senders set first_scan_at=now() "
                "where id = ("
                "select id from public.business_email_senders where space_id=%s "
                "and status='authorized' and first_scan_at is null "
                "and kind='address' and value=%s limit 1"
                ") returning id",
                (space_id, full),
            ).fetchone()
            return row is not None

    def space_name(self, space_id: str) -> str | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                "select name from public.spaces where id=%s", (space_id,)
            ).fetchone()
            return row[0] if row else None

    def mark_cap_exempt(self, delivery, *, exempt: bool = True) -> None:
        with self.pool.connection() as connection:
            changed = connection.execute(
                "update public.business_email_deliveries set cap_exempt=%s "
                "where id=%s and lease_token=%s and lease_until>now() and state='processing'",
                (exempt, delivery.id, delivery.lease_token),
            ).rowcount
            if changed != 1:
                from argus.domain.ingestion.email_intake.store import LeaseLost

                raise LeaseLost()

    def stamp_route(self, delivery, **values: object) -> None:  # noqa: ANN001
        allowed = {"inbox_group", "auth_result", "review_note", "first_scan"}
        if set(values) - allowed:
            raise ValueError("invalid_email_stamp")
        assignments = ",".join(f"{key}=%s" for key in values)
        with self.pool.connection() as connection:
            changed = connection.execute(
                f"update public.business_email_deliveries set {assignments}, updated_at=now() "
                "where id=%s and lease_token=%s and lease_until>now() and state='processing'",
                (*values.values(), delivery.id, delivery.lease_token),
            ).rowcount
            if changed != 1:
                from argus.domain.ingestion.email_intake.store import LeaseLost

                raise LeaseLost()


class MemoryAddressing:
    def _address_lock(self) -> RLock:
        return self._lock

    def alias_taken(self, normalized: str, *, except_route_id: str | None = None) -> bool:
        with self._lock:
            for route in self._routes.values():
                if route.alias_normalized == normalized and route.id != except_route_id:
                    return True
            return normalized in self._retired_aliases

    def matching_retired(self, recipients: tuple[str, ...]) -> list[RetiredAlias]:
        with self._lock:
            return [self._retired[item] for item in recipients if item in self._retired]

    def change_address(
        self,
        route_id: str,
        *,
        alias: str,
        alias_normalized: str,
        recipient: str,
        review_required: bool,
        actor_id: str | None = None,
    ) -> RecipientRoute:
        with self._lock:
            current = self._routes.get(route_id)
            if current is None or not current.active:
                raise LookupError("email_route_unavailable")
            if current.alias_normalized == alias_normalized and current.recipient == recipient:
                return current
            if self.alias_taken(alias_normalized, except_route_id=route_id):
                raise AliasTaken()
            if any(
                route.recipient == recipient and route.id != route_id
                for route in self._routes.values()
            ):
                raise AliasTaken()
            if recipient in self._retired:
                raise AliasTaken()
            self._retired[current.recipient] = RetiredAlias(
                route_id,
                current.space_id,
                current.principal_id,
                current.recipient,
                current.alias_normalized,
            )
            if current.alias_normalized:
                self._retired_aliases.add(current.alias_normalized)
            updated = replace(
                current,
                recipient=recipient,
                alias=alias,
                alias_normalized=alias_normalized,
                review_required=review_required,
            )
            self._routes[route_id] = updated
            self._remember(
                current.space_id,
                actor_id,
                "address_changed",
                current.recipient,
                recipient,
            )
            return updated

    def _remember(self, space_id, actor_id, event_type, old, new) -> None:  # noqa: ANN001
        self._events.append(
            AddressEvent(
                str(uuid4()),
                str(space_id),
                None if actor_id is None else str(actor_id),
                event_type,
                _event_address(old),
                _event_address(new),
                self.clock(),
            )
        )

    def address_events(self, space_id: str) -> list[AddressEvent]:
        with self._lock:
            return [event for event in self._events if event.space_id == space_id]

    def list_senders(self, space_id: str) -> list[SenderRule]:
        with self._lock:
            return [rule for rule in self._senders.values() if rule.space_id == space_id]

    def upsert_sender(
        self,
        space_id: str,
        kind: str,
        value: str,
        status: str,
        actor_id: str | None = None,
    ) -> SenderRule:
        event = "sender_authorized" if status == "authorized" else "sender_blocked"
        with self._lock:
            key = (space_id, kind, value)
            current = self._senders.get(key)
            rule = (
                replace(current, status=status)
                if current
                else SenderRule(str(uuid4()), space_id, kind, value, status)
            )
            self._senders[key] = rule
            self._remember(
                space_id,
                actor_id,
                event,
                value if status == "blocked" else None,
                value,
            )
            return rule

    def remove_sender(
        self, space_id: str, sender_id: str, actor_id: str | None = None
    ) -> SenderRule | None:
        with self._lock:
            found = next(
                (
                    key
                    for key, rule in self._senders.items()
                    if rule.id == sender_id and rule.space_id == space_id
                ),
                None,
            )
            if found is None:
                return None
            rule = self._senders.pop(found)
            self._remember(space_id, actor_id, "sender_removed", rule.value, None)
            return rule

    def has_sender_rules(self, space_id: str) -> bool:
        with self._lock:
            return any(rule.space_id == space_id for rule in self._senders.values())

    def sender_standing(self, space_id: str, address: str | None) -> str:
        parsed = _address_value(bare_address(address))
        if parsed is None:
            return "new"
        full = parsed[0]
        with self._lock:
            rule = self._senders.get((space_id, "address", full))
            return rule.status if rule is not None else "new"

    def claim_first_scan(self, space_id: str, address: str | None) -> bool:
        parsed = _address_value(bare_address(address))
        if parsed is None:
            return False
        full = parsed[0]
        with self._lock:
            rule = self._senders.get((space_id, "address", full))
            if rule is None or rule.status != "authorized" or rule.first_scan_at is not None:
                return False
            self._senders[(space_id, rule.kind, rule.value)] = replace(
                rule, first_scan_at=self.clock()
            )
            return True

    def space_name(self, space_id: str) -> str | None:
        return self._space_names.get(space_id)

    def mark_cap_exempt(self, delivery, *, exempt: bool = True) -> None:
        with self._lock:
            current = self._held(delivery)
            self._deliveries[delivery.id] = replace(current, cap_exempt=exempt)

    def stamp_route(self, delivery, **values: object) -> None:  # noqa: ANN001
        allowed = {"inbox_group", "auth_result", "review_note", "first_scan"}
        if set(values) - allowed:
            raise ValueError("invalid_email_stamp")
        with self._lock:
            current = self._held(delivery)
            self._deliveries[delivery.id] = replace(current, **values)
