"""Import a statement, offer pairs, and read line states.

Decisions on a pair and the settlement they write live in ``outcomes_store``.

``unmatched_charge_count`` counts the charges with no confirmed receipt for
one space and period. Month close reads that function. It does not own these
tables.
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
    new_offers,
    normalize_description,
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
from argus.domain.business.bank.movements import movement_state, taken_documents
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
        rows = self.store.list_suggestions(space_id)
        return tuple(
            row
            for row in rows
            if status is None or self.suggestion_view(row)[0] == status
        )

    def suggestion_view(self, row: Suggestion) -> tuple[str, bool]:
        """The status a person sees and whether they can still confirm it. A
        pair is confirmed while its line holds a live match to its target."""

        outcomes = self.store.live_outcomes(row.space_id)
        live = outcomes.get(str(row.line_id))
        if live is not None and live.kind == "match" and live.target_id == row.target_id:
            return "confirmed", False
        actionable = (
            row.status == "pending"
            and live is None
            and row.target_id not in taken_documents(outcomes)
        )
        return row.status, actionable

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

    def unmatched_charges(
        self, *, space_id: UUID, period_start: date, period_end: date
    ) -> tuple[BankLine, ...]:
        """Charges in the period still waiting for a comprobante. Not a stored flag."""

        lines = self.store.list_lines(
            space_id, period_start=period_start, period_end=period_end
        )
        return tuple(
            line
            for line in lines
            if line.amount < 0
            and self.line_state(line) in ("falta_comprobante", "sugerencia")
        )

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
        outcomes = self.store.live_outcomes(line.space_id)
        live = outcomes.get(str(line.id))
        taken = taken_documents(outcomes)
        pairs = self.store.list_suggestions(line.space_id, line_id=line.id)
        state, _reason = movement_state(
            line.amount,
            matched=live is not None and live.kind == "match",
            disposition=live.reason if live is not None else None,
            has_offer=live is None
            and any(
                pair.status == "pending" and pair.target_id not in taken for pair in pairs
            ),
        )
        return state

    def _offer(self, space_id: UUID, lines: tuple[BankLine, ...]) -> list[Suggestion]:
        if not lines:
            return []
        window = timedelta(days=MATCH_WINDOW_DAYS)
        start = min(line.occurred_on for line in lines) - window
        end = max(line.occurred_on for line in lines) + window
        kinds = {expected_kind(line.amount) for line in lines} - {None}
        targets = [
            target
            for kind in sorted(kinds)
            for target in self.catalog.approved_targets(
                space_id, kind=kind, period_start=start, period_end=end
            )
        ]
        known = frozenset(
            (str(row.line_id), row.target_id)
            for line in lines
            for row in self.store.list_suggestions(space_id, line_id=line.id)
        )
        created: list[Suggestion] = []
        for line, target, parts in new_offers(
            lines, targets, known, taken_documents(self.store.live_outcomes(space_id))
        ):
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
