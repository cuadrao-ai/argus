"""Postgres bank matching store. The memory store exposes the same methods."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.business.bank.model import (
    BankAccountBinding,
    BankImport,
    BankLine,
    BankMatchingError,
    ScoreParts,
    Suggestion,
    SuggestionStatus,
    TargetKind,
)

LINE_COLUMNS = """
    id, space_id, bank_account_id, first_import_id, occurred_on, description,
    normalized_description, amount, currency, raw_line, line_hash, created_at
"""
_SUGGESTION = """
    id, space_id, line_id, target_id, target_kind, status, amount_score,
    date_score, merchant_score, created_at, decided_at, decided_by, decision_key
"""


class PostgresBankStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool
        self._local = threading.local()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._pool.connection() as connection:
            with connection.transaction():
                self._local.connection = connection
                try:
                    yield
                finally:
                    self._local.connection = None

    def get_account(self, space_id: UUID) -> BankAccountBinding | None:
        row = self._one(
            """
            select id, space_id, account_id, currency, created_at
            from public.business_bank_accounts
            where space_id = %s
            """,
            (space_id,),
        )
        return None if row is None else _account(row)

    def put_account(self, row: BankAccountBinding) -> BankAccountBinding:
        self._one(
            """
            insert into public.business_bank_accounts (
                id, space_id, account_id, currency, created_at
            ) values (%s, %s, %s, %s, %s)
            on conflict (space_id) do nothing
            returning id
            """,
            (row.id, row.space_id, row.account_id, row.currency, row.created_at),
        )
        existing = self.get_account(row.space_id)
        if existing is None or existing.account_id != row.account_id:
            raise BankMatchingError("one_account")
        return existing

    def import_for_key(
        self, space_id: UUID, actor_id: UUID, key: str
    ) -> BankImport | None:
        row = self._one(
            f"""
            select {_IMPORT}
            from public.business_bank_imports
            where space_id = %s and imported_by = %s and idempotency_key = %s
            """,
            (space_id, actor_id, key),
        )
        return None if row is None else _import(row)

    def put_import(self, row: BankImport) -> BankImport:
        updated = self._one(
            """
            update public.business_bank_imports
            set inserted_count = %s, unchanged_count = %s
            where id = %s and space_id = %s
            returning id
            """,
            (row.inserted_count, row.unchanged_count, row.id, row.space_id),
        )
        if updated is not None:
            return row
        self._one(
            """
            insert into public.business_bank_imports (
                id, space_id, bank_account_id, reader_id, source_sha256,
                idempotency_key, inserted_count, unchanged_count,
                imported_by, imported_at
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                row.id,
                row.space_id,
                row.bank_account_id,
                row.reader_id,
                row.source_sha256,
                row.idempotency_key,
                row.inserted_count,
                row.unchanged_count,
                row.imported_by,
                row.imported_at,
            ),
        )
        return row

    def upsert_line(self, line: BankLine) -> tuple[BankLine, bool]:
        inserted = self._one(
            f"""
            insert into public.business_bank_lines ({LINE_COLUMNS})
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (
                bank_account_id, occurred_on, amount,
                normalized_description, line_hash
            ) do nothing
            returning id
            """,
            (
                line.id,
                line.space_id,
                line.bank_account_id,
                line.first_import_id,
                line.occurred_on,
                line.description,
                line.normalized_description,
                line.amount,
                line.currency,
                Jsonb(dict(line.raw_line)),
                line.line_hash,
                line.created_at,
            ),
        )
        if inserted is not None:
            return line, True
        found = self.find_line(
            line.bank_account_id,
            line.occurred_on,
            line.amount,
            line.normalized_description,
            line.line_hash,
        )
        if found is None:
            raise BankMatchingError("invalid_statement")
        return found, False

    def find_line(
        self,
        bank_account_id: UUID,
        occurred_on: date,
        amount: Decimal,
        normalized_description: str,
        line_hash: str,
    ) -> BankLine | None:
        row = self._one(
            f"""
            select {LINE_COLUMNS}
            from public.business_bank_lines
            where bank_account_id = %s
                and occurred_on = %s
                and amount = %s
                and normalized_description = %s
                and line_hash = %s
            """,
            (
                bank_account_id,
                occurred_on,
                amount,
                normalized_description,
                line_hash,
            ),
        )
        return None if row is None else line_from_row(row)

    def list_lines(
        self, space_id: UUID, *, period_start: date, period_end: date
    ) -> tuple[BankLine, ...]:
        rows = self._rows(
            f"""
            select {LINE_COLUMNS}
            from public.business_bank_lines
            where space_id = %s and occurred_on between %s and %s
            order by occurred_on, id
            """,
            (space_id, period_start, period_end),
        )
        return tuple(line_from_row(row) for row in rows)

    def lines_for_import(self, space_id: UUID, import_id: UUID) -> tuple[BankLine, ...]:
        rows = self._rows(
            f"""
            select {LINE_COLUMNS}
            from public.business_bank_lines
            where space_id = %s and first_import_id = %s
            order by occurred_on, id
            """,
            (space_id, import_id),
        )
        return tuple(line_from_row(row) for row in rows)

    def get_line(self, space_id: UUID, line_id: UUID) -> BankLine:
        row = self._one(
            f"""
            select {LINE_COLUMNS}
            from public.business_bank_lines
            where id = %s and space_id = %s
            """,
            (line_id, space_id),
        )
        if row is None:
            raise BankMatchingError("suggestion_not_found")
        return line_from_row(row)

    def get_pair(
        self, line_id: UUID, target_kind: TargetKind, target_id: str
    ) -> Suggestion | None:
        row = self._one(
            f"""
            select {_SUGGESTION}
            from public.business_bank_suggestions
            where line_id = %s and target_kind = %s and target_id = %s
            """,
            (line_id, target_kind, target_id),
        )
        return None if row is None else _suggestion(row)

    def put_suggestion(self, row: Suggestion) -> Suggestion:
        self._one(
            """
            insert into public.business_bank_suggestions (
                id, space_id, line_id, target_id, target_kind, status,
                amount_score, date_score, merchant_score, created_at,
                decided_at, decided_by, decision_key
            ) values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            returning id
            """,
            (
                row.id,
                row.space_id,
                row.line_id,
                row.target_id,
                row.target_kind,
                row.status,
                row.parts.amount_score,
                row.parts.date_score,
                row.parts.merchant_score,
                row.created_at,
                row.decided_at,
                row.decided_by,
                row.decision_key,
            ),
        )
        return row

    def get_suggestion(self, space_id: UUID, suggestion_id: UUID) -> Suggestion:
        row = self._one(
            f"""
            select {_SUGGESTION}
            from public.business_bank_suggestions
            where id = %s and space_id = %s
            """,
            (suggestion_id, space_id),
        )
        if row is None:
            raise BankMatchingError("suggestion_not_found")
        return _suggestion(row)

    def list_suggestions(
        self,
        space_id: UUID,
        *,
        line_id: UUID | None = None,
        status: SuggestionStatus | None = None,
    ) -> tuple[Suggestion, ...]:
        rows = self._rows(
            f"""
            select {_SUGGESTION}
            from public.business_bank_suggestions
            where space_id = %s
                and (%s::uuid is null or line_id = %s)
                and (%s::text is null or status = %s)
            order by id
            """,
            (space_id, line_id, line_id, status, status),
        )
        return tuple(_suggestion(row) for row in rows)

    def confirmed_for_line(self, line_id: UUID) -> Suggestion | None:
        row = self._one(
            f"""
            select {_SUGGESTION}
            from public.business_bank_suggestions
            where line_id = %s and status = 'confirmed'
            """,
            (line_id,),
        )
        return None if row is None else _suggestion(row)

    def decide(
        self,
        space_id: UUID,
        suggestion_id: UUID,
        *,
        status: SuggestionStatus,
        actor_id: UUID,
        decision_key: str,
    ) -> Suggestion:
        try:
            row = self._one(
                f"""
                update public.business_bank_suggestions
                set status = %s,
                    decided_at = now(),
                    decided_by = %s,
                    decision_key = %s
                where id = %s and space_id = %s and status = 'pending'
                returning {_SUGGESTION}
                """,
                (status, actor_id, decision_key, suggestion_id, space_id),
            )
        except UniqueViolation as exc:
            raise BankMatchingError("line_already_confirmed") from exc
        if row is not None:
            return _suggestion(row)
        current = self.get_suggestion(space_id, suggestion_id)
        if current.decision_key == decision_key and current.status == status:
            return current
        raise BankMatchingError("suggestion_not_pending")

    def _rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        held = getattr(self._local, "connection", None)
        if held is not None:
            return _fetch(held, sql, params)
        with self._pool.connection() as connection, connection.transaction():
            return _fetch(connection, sql, params)

    def _one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self._rows(sql, params)
        return rows[0] if rows else None


_IMPORT = """
    id, space_id, bank_account_id, reader_id, source_sha256, idempotency_key,
    inserted_count, unchanged_count, imported_by, imported_at
"""


def _fetch(connection, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:  # noqa: ANN001
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _account(row: dict[str, Any]) -> BankAccountBinding:
    return BankAccountBinding(
        id=row["id"],
        space_id=row["space_id"],
        account_id=row["account_id"],
        currency=row["currency"],
        created_at=row["created_at"],
    )


def _import(row: dict[str, Any]) -> BankImport:
    return BankImport(
        id=row["id"],
        space_id=row["space_id"],
        bank_account_id=row["bank_account_id"],
        reader_id=row["reader_id"],
        source_sha256=row["source_sha256"],
        idempotency_key=row["idempotency_key"],
        inserted_count=row["inserted_count"],
        unchanged_count=row["unchanged_count"],
        imported_by=row["imported_by"],
        imported_at=row["imported_at"],
    )


def line_from_row(row: dict[str, Any]) -> BankLine:
    raw = row["raw_line"]
    return BankLine(
        id=row["id"],
        space_id=row["space_id"],
        bank_account_id=row["bank_account_id"],
        first_import_id=row["first_import_id"],
        occurred_on=row["occurred_on"],
        description=row["description"],
        normalized_description=row["normalized_description"],
        amount=Decimal(row["amount"]),
        currency=row["currency"],
        raw_line={str(key): str(value) for key, value in dict(raw).items()},
        line_hash=row["line_hash"],
        created_at=row["created_at"],
    )


def _suggestion(row: dict[str, Any]) -> Suggestion:
    return Suggestion(
        id=row["id"],
        space_id=row["space_id"],
        line_id=row["line_id"],
        target_id=row["target_id"],
        target_kind=row["target_kind"],
        status=row["status"],
        parts=ScoreParts(
            amount_score=Decimal(row["amount_score"]),
            date_score=Decimal(row["date_score"]),
            merchant_score=Decimal(row["merchant_score"]),
        ),
        created_at=row["created_at"],
        decided_at=row["decided_at"],
        decided_by=row["decided_by"],
        decision_key=row["decision_key"],
    )
