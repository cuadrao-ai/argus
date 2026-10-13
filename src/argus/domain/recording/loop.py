"""Expense revisions, observation coverage and the canonical position projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from argus.domain.recording.errors import RecordingInputError
from argus.domain.recording.records import Balance, OpeningRecord


@dataclass(frozen=True)
class ExpenseRevision:
    revision: int
    amount_minor: int
    occurred_at: datetime
    time_zone: str
    note: str | None
    category_id: str | None
    reason: str | None
    recorded_by: str | None
    recorded_at: datetime
    kind: str = "expense"
    role: str = "single"
    active: bool = True
    activity_id: str | None = None
    activity_revision: int | None = None
    source_id: str | None = None
    purchase_activity_id: str | None = None
    purchase_revision: int | None = None
    interest_minor: int | None = None
    reversal_of_activity_id: str | None = None
    reversal_of_revision: int | None = None
    entered_on: date | None = None
    coverage_skips: tuple[tuple[str, str], ...] = ()

    @property
    def movement_minor(self) -> int:
        if not self.active:
            return 0
        if self.kind == "payment_reversal":
            return self.amount_minor if self.role == "source" else -self.amount_minor
        return (
            -self.amount_minor
            if self.kind == "expense" or self.role == "source"
            else self.amount_minor
        )


@dataclass(frozen=True)
class ExpenseRecord:
    id: str
    account_id: str
    revisions: tuple[ExpenseRevision, ...]

    @property
    def current(self) -> ExpenseRevision:
        return self.revisions[-1]


@dataclass(frozen=True)
class CheckRecord:
    id: str
    account_id: str
    amount_minor: int
    as_of: datetime
    time_zone: str
    expected_minor: int | None
    difference_minor: int | None
    reviewed_version: int
    recorded_by: str | None
    recorded_at: datetime
    source: str = "manual"
    kind: Literal["balance_check", "value_update"] = "balance_check"
    revision: int = 1
    note: str | None = None
    estimate_basis: str | None = None
    reason: str | None = None
    prior_revisions: tuple[CheckRecord, ...] = ()


@dataclass(frozen=True)
class Coverage:
    observation_id: str
    observation_revision: int
    activity_id: str
    activity_revision: int
    included: bool


@dataclass(frozen=True)
class Observation:
    id: str
    revision: int
    kind: str
    amount_minor: int
    as_of: datetime
    time_zone: str
    recorded_at: datetime


def observations(
    opening: OpeningRecord | None, checks: tuple[CheckRecord, ...]
) -> tuple[Observation, ...]:
    result = []
    if opening:
        r = opening.current
        result.append(
            Observation(
                opening.id,
                r.revision,
                "opening",
                r.amount_minor,
                r.as_of,
                r.time_zone,
                r.recorded_at,
            )
        )
    result.extend(
        Observation(
            c.id, c.revision, c.kind, c.amount_minor, c.as_of, c.time_zone, c.recorded_at
        )
        for c in sorted(checks, key=lambda c: c.reviewed_version)
    )
    return tuple(result)


CoverageSkip = Literal["after_observation_day", "entered_after_observation"]


def coverage_skip(
    expense: ExpenseRevision, observation: Observation
) -> CoverageSkip | None:
    """Why no inclusion question applies; None means the person must answer.

    Only a movement dated the day it was entered has a real time on that day."""
    zone = ZoneInfo(observation.time_zone)
    occurred = expense.occurred_at.astimezone(zone).date()
    observed = observation.as_of.astimezone(zone).date()
    if occurred != observed:
        return None if occurred < observed else "after_observation_day"
    own = ZoneInfo(expense.time_zone)
    entered_on = expense.entered_on or expense.recorded_at.astimezone(own).date()
    if (
        expense.occurred_at.astimezone(own).date() == entered_on
        and expense.occurred_at > observation.as_of
    ):
        return "entered_after_observation"
    return None


def eligible(expense: ExpenseRevision, observation: Observation) -> bool:
    return coverage_skip(expense, observation) is None


def on_or_before_day(expense: ExpenseRevision, observation: Observation) -> bool:
    """The balance-check and opening rule: any activity on or before the observation's day."""
    zone = ZoneInfo(observation.time_zone)
    return (
        expense.occurred_at.astimezone(zone).date()
        <= observation.as_of.astimezone(zone).date()
    )


def _link(
    expense: ExpenseRecord, observation: Observation, coverage: tuple[Coverage, ...]
) -> Coverage | None:
    key = (observation.id, observation.revision, expense.id, expense.current.revision)
    return next(
        (
            link
            for link in coverage
            if (
                link.observation_id,
                link.observation_revision,
                link.activity_id,
                link.activity_revision,
            )
            == key
        ),
        None,
    )


def answerable(
    expense: ExpenseRecord, observation: Observation, coverage: tuple[Coverage, ...]
) -> bool:
    """Eligible now, or answered under an earlier eligibility rule; answers stand."""
    return eligible(expense.current, observation) or (
        _link(expense, observation, coverage) is not None
    )


def included(
    expense: ExpenseRecord, observation: Observation, coverage: tuple[Coverage, ...]
) -> bool:
    if not expense.current.active:
        return False
    link = _link(expense, observation, coverage)
    if link is not None:
        return link.included
    if not eligible(expense.current, observation):
        return False
    raise ValueError("financial observation is missing explicit activity coverage")


def position(
    opening: OpeningRecord | None,
    checks: tuple[CheckRecord, ...],
    expenses: tuple[ExpenseRecord, ...],
    coverage: tuple[Coverage, ...],
) -> Balance:
    activity = sum(e.current.movement_minor for e in expenses)
    anchors = observations(opening, checks)
    if not anchors:
        return Balance(state="unknown", activity_since_tracking_minor=activity)
    latest = anchors[-1]
    movement = sum(
        e.current.movement_minor
        for e in expenses
        if e.current.active and not included(e, latest, coverage)
    )
    as_of, source_zone = max(
        [
            (latest.as_of, latest.time_zone),
            *(
                (e.current.occurred_at, e.current.time_zone)
                for e in expenses
                if e.current.active
            ),
        ],
        key=lambda source: source[0],
    )
    return Balance(
        state="known",
        amount_minor=latest.amount_minor + movement,
        as_of=as_of.astimezone(ZoneInfo(source_zone)),
        basis="opening" if latest.kind == "opening" else "balance_check",
        activity_since_tracking_minor=activity,
    )


def expected_at(
    observation: Observation,
    preceding: Observation | None,
    expenses: tuple[ExpenseRecord, ...],
    coverage: tuple[Coverage, ...],
) -> int | None:
    if preceding is None:
        return None
    newly_covered = sum(
        e.current.movement_minor
        for e in expenses
        if e.current.active
        and included(e, observation, coverage)
        and not included(e, preceding, coverage)
    )
    return preceding.amount_minor + newly_covered


def residuals(
    opening: OpeningRecord | None,
    checks: tuple[CheckRecord, ...],
    expenses: tuple[ExpenseRecord, ...],
    coverage: tuple[Coverage, ...],
) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    previous = None
    for observation in observations(opening, checks):
        if observation.kind != "opening":
            expected = expected_at(observation, previous, expenses, coverage)
            result[observation.id] = (
                None if expected is None else observation.amount_minor - expected
            )
        previous = observation
    return result


def validate_monotonic(
    expense: ExpenseRecord,
    anchors: tuple[Observation, ...],
    coverage: tuple[Coverage, ...],
) -> None:
    seen = False
    for observation in anchors:
        if not expense.current.active or not answerable(expense, observation, coverage):
            if seen:
                raise RecordingInputError(
                    "coverage_date_conflict",
                    "The selected date and time zone exclude activity already included in an earlier balance.",
                )
            continue
        value = included(expense, observation, coverage)
        if seen and not value:
            raise RecordingInputError(
                "coverage_conflict",
                "An expense included in an earlier balance remains included in later balances.",
            )
        seen = seen or value
