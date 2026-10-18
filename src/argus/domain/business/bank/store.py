"""In-memory bank matching store. Postgres uses the same method names."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from argus.domain.business.bank.model import (
    BankAccountBinding,
    BankImport,
    BankLine,
    BankMatchingError,
    Suggestion,
    SuggestionStatus,
    TargetKind,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryBankStore:
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or _now
        self._lock = threading.Lock()
        self.accounts: dict[UUID, BankAccountBinding] = {}
        self.imports: dict[UUID, BankImport] = {}
        self.lines: dict[UUID, BankLine] = {}
        self.suggestions: dict[UUID, Suggestion] = {}

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield

    def get_account(self, space_id: UUID) -> BankAccountBinding | None:
        with self._lock:
            return next(
                (row for row in self.accounts.values() if row.space_id == space_id),
                None,
            )

    def put_account(self, row: BankAccountBinding) -> BankAccountBinding:
        with self._lock:
            existing = next(
                (
                    item
                    for item in self.accounts.values()
                    if item.space_id == row.space_id
                ),
                None,
            )
            if existing is not None:
                if existing.account_id != row.account_id:
                    raise BankMatchingError("one_account")
                return existing
            self.accounts[row.id] = row
            return row

    def import_for_key(
        self, space_id: UUID, actor_id: UUID, key: str
    ) -> BankImport | None:
        with self._lock:
            return next(
                (
                    row
                    for row in self.imports.values()
                    if row.space_id == space_id
                    and row.imported_by == actor_id
                    and row.idempotency_key == key
                ),
                None,
            )

    def put_import(self, row: BankImport) -> BankImport:
        with self._lock:
            self.imports[row.id] = row
            return row

    def upsert_line(self, line: BankLine) -> tuple[BankLine, bool]:
        with self._lock:
            for existing in self.lines.values():
                if (
                    existing.bank_account_id == line.bank_account_id
                    and existing.occurred_on == line.occurred_on
                    and existing.amount == line.amount
                    and existing.normalized_description == line.normalized_description
                    and existing.line_hash == line.line_hash
                ):
                    return existing, False
            self.lines[line.id] = line
            return line, True

    def find_line(
        self,
        bank_account_id: UUID,
        occurred_on: date,
        amount: Decimal,
        normalized_description: str,
        line_hash: str,
    ) -> BankLine | None:
        with self._lock:
            return next(
                (
                    row
                    for row in self.lines.values()
                    if row.bank_account_id == bank_account_id
                    and row.occurred_on == occurred_on
                    and row.amount == amount
                    and row.normalized_description == normalized_description
                    and row.line_hash == line_hash
                ),
                None,
            )

    def list_lines(
        self, space_id: UUID, *, period_start: date, period_end: date
    ) -> tuple[BankLine, ...]:
        with self._lock:
            rows = [
                row
                for row in self.lines.values()
                if row.space_id == space_id
                and period_start <= row.occurred_on <= period_end
            ]
        return tuple(sorted(rows, key=lambda row: (row.occurred_on, str(row.id))))

    def lines_for_import(self, space_id: UUID, import_id: UUID) -> tuple[BankLine, ...]:
        with self._lock:
            rows = [
                row
                for row in self.lines.values()
                if row.space_id == space_id and row.first_import_id == import_id
            ]
        return tuple(sorted(rows, key=lambda row: (row.occurred_on, str(row.id))))

    def get_line(self, space_id: UUID, line_id: UUID) -> BankLine:
        with self._lock:
            row = self.lines.get(line_id)
        if row is None or row.space_id != space_id:
            raise BankMatchingError("suggestion_not_found")
        return row

    def get_pair(
        self, line_id: UUID, target_kind: TargetKind, target_id: str
    ) -> Suggestion | None:
        with self._lock:
            return next(
                (
                    row
                    for row in self.suggestions.values()
                    if row.line_id == line_id
                    and row.target_kind == target_kind
                    and row.target_id == target_id
                ),
                None,
            )

    def put_suggestion(self, row: Suggestion) -> Suggestion:
        with self._lock:
            self.suggestions[row.id] = row
            return row

    def get_suggestion(self, space_id: UUID, suggestion_id: UUID) -> Suggestion:
        with self._lock:
            row = self.suggestions.get(suggestion_id)
        if row is None or row.space_id != space_id:
            raise BankMatchingError("suggestion_not_found")
        return row

    def list_suggestions(
        self,
        space_id: UUID,
        *,
        line_id: UUID | None = None,
        status: SuggestionStatus | None = None,
    ) -> tuple[Suggestion, ...]:
        with self._lock:
            rows = [
                row
                for row in self.suggestions.values()
                if row.space_id == space_id
                and (line_id is None or row.line_id == line_id)
                and (status is None or row.status == status)
            ]
        return tuple(sorted(rows, key=lambda row: str(row.id)))

    def confirmed_for_line(self, line_id: UUID) -> Suggestion | None:
        with self._lock:
            return next(
                (
                    row
                    for row in self.suggestions.values()
                    if row.line_id == line_id and row.status == "confirmed"
                ),
                None,
            )

    def decide(
        self,
        space_id: UUID,
        suggestion_id: UUID,
        *,
        status: SuggestionStatus,
        actor_id: UUID,
        decision_key: str,
    ) -> Suggestion:
        with self._lock:
            row = self.suggestions.get(suggestion_id)
            if row is None or row.space_id != space_id:
                raise BankMatchingError("suggestion_not_found")
            if row.status != "pending":
                if row.decision_key == decision_key and row.status == status:
                    return row
                raise BankMatchingError("suggestion_not_pending")
            if status == "confirmed" and any(
                other.line_id == row.line_id and other.status == "confirmed"
                for other in self.suggestions.values()
            ):
                raise BankMatchingError("line_already_confirmed")
            decided = Suggestion(
                id=row.id,
                space_id=row.space_id,
                line_id=row.line_id,
                target_id=row.target_id,
                target_kind=row.target_kind,
                status=status,
                parts=row.parts,
                created_at=row.created_at,
                decided_at=self._clock(),
                decided_by=actor_id,
                decision_key=decision_key,
            )
            self.suggestions[row.id] = decided
            return decided


def new_id() -> UUID:
    return uuid4()
