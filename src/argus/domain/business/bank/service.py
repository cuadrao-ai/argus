"""Import a statement, offer pairs, and record the person's decision.

``unmatched_charge_count`` is the sin comprobante count for one space and
period. Month close reads that function. It does not own these tables.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from argus.domain.business.bank.matching import (
    derive_confidence,
    expected_kind,
    normalize_description,
    score_parts,
)
from argus.domain.business.bank.model import (
    MATCH_WINDOW_DAYS,
    BankAccountBinding,
    BankImport,
    BankLine,
    BankMatchingError,
    CsvMapping,
    ImportResult,
    MatchTarget,
    ReaderId,
    Suggestion,
    TargetCatalog,
)
from argus.domain.business.bank.readers import select_reader
from argus.domain.business.bank.store import MemoryBankStore, new_id

_SERVICE: "BankMatchingService | None" = None


def configure_bank_matching(service: BankMatchingService | None) -> None:
    global _SERVICE
    _SERVICE = service


def bank_matching_service() -> BankMatchingService | None:
    return _SERVICE


def unmatched_charge_count(space_id: UUID, period_start: date, period_end: date) -> int:
    """Charges in the inclusive period with no confirmed receipt.

    Uses the process service started with the API. Returns the same count
    as ``BankMatchingService.unmatched_charge_count``.
    """

    service = _SERVICE
    if service is None:
        raise BankMatchingError("business_bank_matching_off")
    return service.unmatched_charge_count(space_id, period_start, period_end)


class EmptyCatalog:
    def approved_targets(
        self,
        space_id: UUID,
        *,
        kind: str,
        period_start: date,
        period_end: date,
    ) -> tuple[MatchTarget, ...]:
        del space_id, kind, period_start, period_end
        return ()

    def get(self, space_id: UUID, *, kind: str, target_id: str) -> MatchTarget | None:
        del space_id, kind, target_id
        return None


class BankMatchingService:
    def __init__(
        self,
        store: MemoryBankStore,
        catalog: TargetCatalog,
        account_of,
        clock=None,
    ) -> None:
        self.store = store
        self.catalog = catalog
        self.account_of = account_of
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def import_statement(
        self,
        *,
        space_id: UUID,
        actor_id: UUID,
        owner_id: UUID,
        capabilities: frozenset[str],
        content: bytes,
        account_id: UUID,
        reader_id: ReaderId | None,
        mapping: CsvMapping | None,
        idempotency_key: str,
    ) -> ImportResult:
        self._require(capabilities, "prepare")
        digest = hashlib.sha256(content).hexdigest()
        prior = self.store.import_for_key(space_id, actor_id, idempotency_key)
        if prior is not None:
            if prior.source_sha256 != digest:
                raise BankMatchingError("idempotency_conflict")
            return self._replay(space_id, prior, content, mapping)
        reader = select_reader(content, mapping, reader_id)
        parsed = reader.read(content, mapping)
        with self.store.transaction():
            binding = self._bind(space_id, owner_id, account_id)
            stamped = _stamp_currency(parsed, binding.currency)
            imported_at = self._clock()
            bank_import = BankImport(
                id=new_id(),
                space_id=space_id,
                bank_account_id=binding.id,
                reader_id=reader.id,
                source_sha256=digest,
                idempotency_key=idempotency_key,
                inserted_count=0,
                unchanged_count=0,
                imported_by=actor_id,
                imported_at=imported_at,
            )
            self.store.put_import(bank_import)
            stored: list[BankLine] = []
            inserted = 0
            for row, line_hash in _with_hashes(stamped):
                line = BankLine(
                    id=new_id(),
                    space_id=space_id,
                    bank_account_id=binding.id,
                    first_import_id=bank_import.id,
                    occurred_on=row.occurred_on,
                    description=row.description,
                    normalized_description=normalize_description(row.description),
                    amount=row.amount,
                    currency=row.currency,
                    raw_line=dict(row.raw_line),
                    line_hash=line_hash,
                    created_at=imported_at,
                )
                saved, created = self.store.upsert_line(line)
                stored.append(saved)
                inserted += int(created)
            bank_import = BankImport(
                id=bank_import.id,
                space_id=bank_import.space_id,
                bank_account_id=bank_import.bank_account_id,
                reader_id=bank_import.reader_id,
                source_sha256=bank_import.source_sha256,
                idempotency_key=bank_import.idempotency_key,
                inserted_count=inserted,
                unchanged_count=len(stored) - inserted,
                imported_by=bank_import.imported_by,
                imported_at=bank_import.imported_at,
            )
            self.store.put_import(bank_import)
            suggestions = self._offer(space_id, tuple(stored))
        return ImportResult(bank_import, True, tuple(stored), tuple(suggestions))

    def _replay(
        self,
        space_id: UUID,
        prior: BankImport,
        content: bytes,
        mapping: CsvMapping | None,
    ) -> ImportResult:
        binding = self.store.get_account(space_id)
        if binding is None or binding.id != prior.bank_account_id:
            raise BankMatchingError("account_not_in_space")
        reader = select_reader(content, mapping, prior.reader_id)
        stamped = _stamp_currency(reader.read(content, mapping), binding.currency)
        lines: list[BankLine] = []
        for row, line_hash in _with_hashes(stamped):
            found = self.store.find_line(
                binding.id,
                row.occurred_on,
                row.amount,
                normalize_description(row.description),
                line_hash,
            )
            if found is None:
                raise BankMatchingError("invalid_statement")
            lines.append(found)
        suggestions: list[Suggestion] = []
        for line in lines:
            suggestions.extend(self.store.list_suggestions(space_id, line_id=line.id))
        return ImportResult(prior, False, tuple(lines), tuple(suggestions))

    def list_suggestions(
        self, *, space_id: UUID, capabilities: frozenset[str], status: str | None = None
    ) -> tuple[Suggestion, ...]:
        self._require(capabilities, "read")
        return self.store.list_suggestions(space_id, status=status)  # type: ignore[arg-type]

    def list_lines(
        self,
        *,
        space_id: UUID,
        capabilities: frozenset[str],
        period_start: date,
        period_end: date,
    ) -> tuple[BankLine, ...]:
        self._require(capabilities, "read")
        return self.store.list_lines(
            space_id, period_start=period_start, period_end=period_end
        )

    def confirm_suggestion(
        self,
        *,
        space_id: UUID,
        actor_id: UUID,
        capabilities: frozenset[str],
        suggestion_id: UUID,
        idempotency_key: str,
    ) -> Suggestion:
        self._require(capabilities, "prepare")
        current = self.store.get_suggestion(space_id, suggestion_id)
        if current.status == "declined":
            raise BankMatchingError("pair_declined")
        if current.status == "confirmed" and current.decision_key == idempotency_key:
            return current
        if self.store.confirmed_for_line(current.line_id) not in (None, current):
            if current.status != "confirmed":
                raise BankMatchingError("line_already_confirmed")
        self._recheck(space_id, current)
        return self.store.decide(
            space_id,
            suggestion_id,
            status="confirmed",
            actor_id=actor_id,
            decision_key=idempotency_key,
        )

    def decline_suggestion(
        self,
        *,
        space_id: UUID,
        actor_id: UUID,
        capabilities: frozenset[str],
        suggestion_id: UUID,
        idempotency_key: str,
    ) -> Suggestion:
        self._require(capabilities, "prepare")
        current = self.store.get_suggestion(space_id, suggestion_id)
        if current.status == "declined" and current.decision_key == idempotency_key:
            return current
        return self.store.decide(
            space_id,
            suggestion_id,
            status="declined",
            actor_id=actor_id,
            decision_key=idempotency_key,
        )

    def unmatched_charges(
        self, *, space_id: UUID, period_start: date, period_end: date
    ) -> tuple[BankLine, ...]:
        """Charges in the period with no confirmed receipt. Not a stored flag."""

        lines = self.store.list_lines(
            space_id, period_start=period_start, period_end=period_end
        )
        unmatched: list[BankLine] = []
        for line in lines:
            if line.amount >= 0:
                continue
            confirmed = self.store.confirmed_for_line(line.id)
            if confirmed is None or confirmed.target_kind != "receipt":
                unmatched.append(line)
        return tuple(unmatched)

    def unmatched_charge_count(
        self, space_id: UUID, period_start: date, period_end: date
    ) -> int:
        return len(
            self.unmatched_charges(
                space_id=space_id,
                period_start=period_start,
                period_end=period_end,
            )
        )

    def line_state(self, line: BankLine) -> str:
        confirmed = self.store.confirmed_for_line(line.id)
        if confirmed is not None:
            return "matched"
        if line.amount < 0:
            return "sin_comprobante"
        return "unmatched"

    def _offer(self, space_id: UUID, lines: tuple[BankLine, ...]) -> list[Suggestion]:
        if not lines:
            return []
        window = timedelta(days=MATCH_WINDOW_DAYS)
        start = min(line.occurred_on for line in lines) - window
        end = max(line.occurred_on for line in lines) + window
        created: list[Suggestion] = []
        for line in lines:
            kind = expected_kind(line.amount)
            if kind is None:
                continue
            targets = self.catalog.approved_targets(
                space_id, kind=kind, period_start=start, period_end=end
            )
            for target in targets:
                if self.store.get_pair(line.id, target.kind, target.id) is not None:
                    continue
                parts = score_parts(line, target)
                if parts is None:
                    continue
                suggestion = Suggestion(
                    id=new_id(),
                    space_id=space_id,
                    line_id=line.id,
                    target_id=target.id,
                    target_kind=target.kind,
                    status="pending",
                    parts=parts,
                    created_at=self._clock(),
                    decided_at=None,
                    decided_by=None,
                    decision_key=None,
                )
                self.store.put_suggestion(suggestion)
                created.append(suggestion)
        return created

    def _recheck(self, space_id: UUID, suggestion: Suggestion) -> None:
        target = self.catalog.get(
            space_id, kind=suggestion.target_kind, target_id=suggestion.target_id
        )
        if target is None or not target.approved:
            raise BankMatchingError("target_not_approved")
        line = self.store.get_line(space_id, suggestion.line_id)
        if score_parts(line, target) is None:
            raise BankMatchingError("target_not_approved")

    def _bind(
        self, space_id: UUID, owner_id: UUID, account_id: UUID
    ) -> BankAccountBinding:
        found = self.account_of(space_id, owner_id, account_id)
        if found is None:
            raise BankMatchingError("account_not_in_space")
        existing = self.store.get_account(space_id)
        if existing is not None and existing.account_id != account_id:
            raise BankMatchingError("one_account")
        if existing is not None:
            return existing
        return self.store.put_account(
            BankAccountBinding(
                id=new_id(),
                space_id=space_id,
                account_id=account_id,
                currency=found.currency,
                created_at=self._clock(),
            )
        )

    @staticmethod
    def _require(capabilities: frozenset[str], needed: str) -> None:
        if needed not in capabilities:
            raise BankMatchingError("business_permission_denied")


def _stamp_currency(rows: tuple, currency: str) -> tuple:
    stamped = []
    for row in rows:
        row_currency = row.currency or currency
        if row_currency != currency:
            raise BankMatchingError("invalid_statement")
        if row.currency:
            stamped.append(row)
            continue
        stamped.append(
            type(row)(
                occurred_on=row.occurred_on,
                description=row.description,
                amount=row.amount,
                currency=currency,
                raw_line=row.raw_line,
            )
        )
    return tuple(stamped)


def _with_hashes(rows: tuple) -> list[tuple]:
    counts: dict[str, int] = {}
    keyed: list[tuple[str, object]] = []
    for row in rows:
        raw = json.dumps(dict(row.raw_line), sort_keys=True, ensure_ascii=False)
        seen = counts.get(raw, 0)
        counts[raw] = seen + 1
        digest = hashlib.sha256(f"{raw}\n{seen}".encode()).hexdigest()
        keyed.append((digest, row))
    return [(row, digest) for digest, row in keyed]


def confidence_of(suggestion: Suggestion) -> Decimal:
    return derive_confidence(suggestion.parts)
