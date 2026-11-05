"""Atomic mutation values shared by the memory and Postgres repositories."""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable

from argus.domain.recording.loop import CheckRecord, Coverage, ExpenseRecord
from argus.domain.recording.records import OpeningRecord
from argus.domain.recording.repository import StoredAccount


@dataclass(frozen=True)
class Mutation:
    record: ExpenseRecord | CheckRecord | OpeningRecord
    coverage: tuple[Coverage, ...]
    kind: str


@dataclass(frozen=True)
class OperationResult:
    stored: StoredAccount
    record_id: str
    revision: int
    kind: str
    replayed: bool


Planner = Callable[[StoredAccount], Mutation]


def apply(stored: StoredAccount, mutation: Mutation, now: datetime) -> StoredAccount:
    record = mutation.record
    changes = {
        "account": replace(
            stored.account, version=stored.account.version + 1, updated_at=now
        ),
        "coverage": (*stored.coverage, *mutation.coverage),
    }
    if isinstance(record, ExpenseRecord):
        changes["expenses"] = tuple(e for e in stored.expenses if e.id != record.id) + (
            record,
        )
    elif isinstance(record, CheckRecord):
        changes["checks"] = tuple(c for c in stored.checks if c.id != record.id) + (
            record,
        )
    else:
        changes["opening"] = record
    return replace(stored, **changes)
