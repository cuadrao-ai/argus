"""Pure reduction of already authorized, normalized, matching recorded activities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from itertools import groupby
from typing import Iterable, Literal, get_args

from argus.domain.recording.money_schemas import ActivityKind


class DuplicateActivity(ValueError):
    """More than one row claims the same canonical activity."""


@dataclass(frozen=True)
class ReportIdentity:
    """Trusted scope and semantic query identity, never an authorization receipt."""

    business_id: str
    actor_id: str
    owner_id: str
    grant_id: str | None
    query_fingerprint: str


@dataclass(frozen=True)
class ReportRow:
    activity_id: str
    revision: int
    occurred_on: date
    kind: str
    currency: str
    amount_minor: int | None
    effect: Literal["known", "unknown", "unsupported"]
    # The loader fingerprints every approved fact and visible source/settlement value.
    dependency_fingerprints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.effect not in ("known", "unknown", "unsupported"):
            raise ValueError("invalid recorded effect")
        if self.effect == "known" and (
            self.amount_minor is None or self.kind not in get_args(ActivityKind)
        ):
            raise ValueError("known effect requires a supported kind and amount")
        if self.amount_minor is not None and (
            not isinstance(self.amount_minor, int)
            or isinstance(self.amount_minor, bool)
            or self.amount_minor < 0
        ):
            raise ValueError("recorded amounts require nonnegative integer minor units")
        object.__setattr__(
            self, "dependency_fingerprints", tuple(sorted(self.dependency_fingerprints))
        )


@dataclass(frozen=True)
class RoleTotal:
    currency: str
    kind: str
    matching_count: int
    known_amount_minor: int
    unknown_count: int
    unsupported_count: int
    basis: Literal["recorded_activity_amount"] = "recorded_activity_amount"

    @property
    def complete(self) -> bool:
        return self.unknown_count == self.unsupported_count == 0

    @property
    def amount_minor(self) -> int | None:
        return self.known_amount_minor if self.complete else None


@dataclass(frozen=True)
class ReportResult:
    identity: ReportIdentity
    rows: tuple[ReportRow, ...]
    totals: tuple[RoleTotal, ...]
    fingerprint: str
    observed_at: datetime
    page_number: int
    page_size: int

    @property
    def matching_count(self) -> int:
        return len(self.rows)

    @property
    def page_count(self) -> int:
        return (self.matching_count + self.page_size - 1) // self.page_size

    @property
    def items(self) -> tuple[ReportRow, ...]:
        offset = (self.page_number - 1) * self.page_size
        return self.rows[offset : offset + self.page_size]


def summarize(
    identity: ReportIdentity,
    matching_rows: Iterable[ReportRow],
    *,
    page_number: int,
    page_size: int,
    observed_at: datetime,
) -> ReportResult:
    """Reduce the full match set before paging, without interpreting fiscal effects."""
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 1
        for value in (page_number, page_size)
    ):
        raise ValueError("report pages require positive integers")
    rows = tuple(
        sorted(
            matching_rows,
            key=lambda row: (-row.occurred_on.toordinal(), row.activity_id),
        )
    )
    if len({row.activity_id for row in rows}) != len(rows):
        raise DuplicateActivity("duplicate canonical report activity")

    totals = []
    grouped = sorted(rows, key=lambda row: (row.currency, row.kind))
    for (currency, kind), group in groupby(
        grouped, key=lambda row: (row.currency, row.kind)
    ):
        members = tuple(group)
        totals.append(
            RoleTotal(
                currency=currency,
                kind=kind,
                matching_count=len(members),
                known_amount_minor=sum(
                    row.amount_minor
                    for row in members
                    if row.effect == "known" and row.amount_minor is not None
                ),
                unknown_count=sum(row.effect == "unknown" for row in members),
                unsupported_count=sum(row.effect == "unsupported" for row in members),
            )
        )
    payload = {
        "contract": "recorded_activity_amount_v1",
        "identity": asdict(identity),
        "rows": [
            asdict(row) | {"occurred_on": row.occurred_on.isoformat()} for row in rows
        ],
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return ReportResult(
        identity=identity,
        rows=rows,
        totals=tuple(totals),
        fingerprint=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        observed_at=observed_at,
        page_number=page_number,
        page_size=page_size,
    )
