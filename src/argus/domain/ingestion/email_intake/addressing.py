"""Alias changes, retired addresses, and sender standing. Both stores."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from threading import RLock
from uuid import uuid4

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

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


@dataclass(frozen=True)
class RetiredAlias:
    route_id: str
    space_id: str
    principal_id: str
    recipient: str
    alias_normalized: str | None


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
            return route_from_row(row)

    def list_senders(self, space_id: str) -> list[SenderRule]:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            rows = cursor.execute(
                "select id::text, space_id::text, kind, value, status, first_scan_at "
                "from public.business_email_senders where space_id=%s order by created_at, id",
                (space_id,),
            ).fetchall()
        return [SenderRule(**row) for row in rows]

    def upsert_sender(self, space_id: str, kind: str, value: str, status: str) -> SenderRule:
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            row = cursor.execute(
                "insert into public.business_email_senders(space_id, kind, value, status) "
                "values (%s,%s,%s,%s) on conflict(space_id, kind, value) do update "
                "set status=excluded.status returning id::text, space_id::text, kind, value, "
                "status, first_scan_at",
                (space_id, kind, value, status),
            ).fetchone()
            return SenderRule(**row)

    def has_sender_rules(self, space_id: str) -> bool:
        with self.pool.connection() as connection:
            row = connection.execute(
                "select 1 from public.business_email_senders where space_id=%s limit 1",
                (space_id,),
            ).fetchone()
            return row is not None

    def sender_standing(self, space_id: str, address: str | None) -> str:
        parsed = _address_value(address)
        if parsed is None:
            return "new"
        full, domain = parsed
        with (
            self.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            rows = cursor.execute(
                "select kind, status from public.business_email_senders "
                "where space_id=%s and ((kind='address' and value=%s) or (kind='domain' and value=%s))",
                (space_id, full, domain),
            ).fetchall()
        by_kind = {row["kind"]: row["status"] for row in rows}
        return by_kind.get("address") or by_kind.get("domain") or "new"

    def claim_first_scan(self, space_id: str, address: str | None) -> bool:
        parsed = _address_value(address)
        if parsed is None:
            return False
        full, domain = parsed
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "update public.business_email_senders set first_scan_at=now() "
                "where id = ("
                "select id from public.business_email_senders where space_id=%s and status='authorized' "
                "and first_scan_at is null and ("
                "(kind='address' and value=%s) or (kind='domain' and value=%s and not exists ("
                "select 1 from public.business_email_senders a where a.space_id=%s "
                "and a.kind='address' and a.value=%s))) "
                "order by case kind when 'address' then 0 else 1 end limit 1"
                ") returning id",
                (space_id, full, domain, space_id, full),
            ).fetchone()
            return row is not None

    def space_name(self, space_id: str) -> str | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                "select name from public.spaces where id=%s", (space_id,)
            ).fetchone()
            return row[0] if row else None

    def mark_cap_exempt(self, delivery) -> None:  # noqa: ANN001
        with self.pool.connection() as connection:
            changed = connection.execute(
                "update public.business_email_deliveries set cap_exempt=true "
                "where id=%s and lease_token=%s and lease_until>now() and state='processing'",
                (delivery.id, delivery.lease_token),
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
            return updated

    def list_senders(self, space_id: str) -> list[SenderRule]:
        with self._lock:
            return [rule for rule in self._senders.values() if rule.space_id == space_id]

    def upsert_sender(self, space_id: str, kind: str, value: str, status: str) -> SenderRule:
        with self._lock:
            key = (space_id, kind, value)
            current = self._senders.get(key)
            rule = SenderRule(
                current.id if current else str(uuid4()),
                space_id,
                kind,
                value,
                status,
                current.first_scan_at if current else None,
            )
            self._senders[key] = rule
            return rule

    def has_sender_rules(self, space_id: str) -> bool:
        with self._lock:
            return any(rule.space_id == space_id for rule in self._senders.values())

    def sender_standing(self, space_id: str, address: str | None) -> str:
        parsed = _address_value(address)
        if parsed is None:
            return "new"
        full, domain = parsed
        with self._lock:
            address_rule = self._senders.get((space_id, "address", full))
            if address_rule is not None:
                return address_rule.status
            domain_rule = self._senders.get((space_id, "domain", domain))
            return domain_rule.status if domain_rule is not None else "new"

    def claim_first_scan(self, space_id: str, address: str | None) -> bool:
        parsed = _address_value(address)
        if parsed is None:
            return False
        full, domain = parsed
        with self._lock:
            rule = self._senders.get((space_id, "address", full)) or self._senders.get(
                (space_id, "domain", domain)
            )
            if rule is None or rule.status != "authorized" or rule.first_scan_at is not None:
                return False
            self._senders[(space_id, rule.kind, rule.value)] = replace(
                rule, first_scan_at=self.clock()
            )
            return True

    def space_name(self, space_id: str) -> str | None:
        return self._space_names.get(space_id)

    def mark_cap_exempt(self, delivery) -> None:  # noqa: ANN001
        with self._lock:
            current = self._held(delivery)
            self._deliveries[delivery.id] = replace(current, cap_exempt=True)

    def stamp_route(self, delivery, **values: object) -> None:  # noqa: ANN001
        allowed = {"inbox_group", "auth_result", "review_note", "first_scan"}
        if set(values) - allowed:
            raise ValueError("invalid_email_stamp")
        with self._lock:
            current = self._held(delivery)
            self._deliveries[delivery.id] = replace(current, **values)
