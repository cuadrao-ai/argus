"""Reviewed financial commands using one atomic repository boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from argus.domain.recording.loop_schemas import CoverageAnswer, OpeningCoverageAnswer
from argus.domain.recording.loop_storage import OperationResult
from argus.domain.recording.repository import FinancialAccountRepository, StoredAccount

if TYPE_CHECKING:
    from argus.domain.recording.service import FinancialAccountService

from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from argus.domain.backtest_admission import canonical_hash
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.accounts import signed_to_owner
from argus.domain.recording.currency import (
    MAX_MINOR_UNITS,
    currency_exponent,
    format_minor_units,
    parse_minor_units,
)
from argus.domain.recording.errors import (
    AccountNotFound,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.loop import (
    CheckRecord,
    Coverage,
    expected_at,
    observations,
    on_or_before_day,
    position,
    residuals,
    validate_monotonic,
)
from argus.domain.recording.loop_schemas import (
    ActivityRequest,
    CheckRequest,
    LoopOpeningRequest,
)
from argus.domain.recording.loop_storage import Mutation, apply
from argus.domain.recording.records import (
    OpeningRecord,
    OpeningRevision,
    _as_instant,
    _validate_zone,
    plan_opening_write,
)
from argus.domain.recording.schemas import _balance_response


def token(
    kind: str,
    account_id: str,
    record_id: str | None,
    request: ActivityRequest | CheckRequest | LoopOpeningRequest,
) -> str:
    body = request.model_dump(mode="json", exclude={"preview_token"})
    return canonical_hash(
        {"kind": kind, "account_id": account_id, "record_id": record_id, "request": body}
    )


def _answers(
    values: list[CoverageAnswer] | list[OpeningCoverageAnswer], key: str
) -> dict[str, bool]:
    answers = {}
    for value in values:
        identity = getattr(value, key)
        if identity in answers:
            raise RecordingInputError(
                "coverage_duplicate", "Answer each balance question once."
            )
        answers[identity] = value.included
    return answers


def _stamp(stamp: datetime, zone: str, now: datetime) -> datetime:
    stamp = _as_instant(stamp)
    _validate_zone(zone, None)
    if stamp > now:
        raise RecordingInputError(
            "date_in_future", "The recorded date cannot be in the future."
        )
    return stamp


def _view(stored: StoredAccount) -> dict[str, Any]:
    b = position(stored.opening, stored.checks, stored.expenses, stored.coverage)
    if (
        b.amount_minor is not None
        and abs(b.amount_minor) > MAX_MINOR_UNITS
        or abs(b.activity_since_tracking_minor) > MAX_MINOR_UNITS
    ):
        raise RecordingInputError(
            "amount_out_of_range", "The resulting recorded amount is too large."
        )
    if any(
        value is not None and abs(value) > MAX_MINOR_UNITS
        for value in residuals(
            stored.opening, stored.checks, stored.expenses, stored.coverage
        ).values()
    ):
        raise RecordingInputError(
            "amount_out_of_range", "The resulting recorded difference is too large."
        )
    return _balance_response(b, stored.account).model_dump(mode="json")


class FinancialLoopService:
    def __init__(
        self,
        accounts: FinancialAccountService,
        repository: FinancialAccountRepository,
        clock: Callable[[], datetime],
    ) -> None:
        self.accounts = accounts
        self.repository = repository
        self.clock = clock

    def _current(
        self, user_id: str, account_id: str, expected_version: int
    ) -> StoredAccount:
        stored = self.accounts.get(user_id=user_id, account_id=account_id, scope=PERSONAL)
        if stored.account.version != expected_version:
            raise StaleVersion()
        return stored

    def preview_activity(
        self,
        *,
        user_id: str,
        account_id: str,
        request: ActivityRequest,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        from argus.domain.recording.money_legacy import preview

        return preview(
            self,
            user_id=user_id,
            account_id=account_id,
            request=request,
            record_id=record_id,
        )

    def write_activity(
        self,
        *,
        user_id: str,
        account_id: str,
        request: ActivityRequest,
        idempotency_key: str,
        record_id: str | None = None,
    ) -> OperationResult:
        from argus.domain.recording.money_legacy import write

        return write(
            self,
            user_id=user_id,
            account_id=account_id,
            request=request,
            idempotency_key=idempotency_key,
            record_id=record_id,
        )

    def preview_check(
        self, *, user_id: str, account_id: str, request: CheckRequest
    ) -> dict[str, Any]:
        stored = self._current(user_id, account_id, request.expected_version)
        _, preview = self._check(stored, request)
        return preview

    def write_check(
        self,
        *,
        user_id: str,
        account_id: str,
        request: CheckRequest,
        idempotency_key: str,
    ) -> OperationResult:
        account_id = self.accounts.get(
            user_id=user_id, account_id=account_id, scope=PERSONAL
        ).account.id

        def plan(stored: StoredAccount) -> Mutation:
            mutation, preview = self._check(stored, request)
            self._confirmed(request, preview)
            return mutation

        return self.repository.mutate(
            user_id=user_id,
            account_id=account_id,
            idempotency_key=idempotency_key,
            identity_hash=token("check", account_id, None, request),
            expected_version=request.expected_version,
            planner=plan,
            scope=PERSONAL,
        )

    def _check(
        self, stored: StoredAccount, request: CheckRequest
    ) -> tuple[Mutation, dict[str, Any]]:
        now = self.clock()
        stamp = _stamp(request.as_of, request.time_zone, now)
        anchors = observations(stored.opening, stored.checks)
        zone = ZoneInfo(request.time_zone)
        if (
            anchors
            and stamp.astimezone(zone).date() < anchors[-1].as_of.astimezone(zone).date()
        ):
            raise RecordingInputError(
                "check_before_latest_observation",
                "This build records checks on or after the latest balance date.",
            )
        amount = signed_to_owner(
            parse_minor_units(request.amount, stored.account.currency),
            stored.account.type,
        )
        kind = (
            "value_update"
            if stored.account.type in {"investment", "property", "vehicle", "other_asset"}
            else "balance_check"
        )
        check = CheckRecord(
            str(uuid4()),
            stored.account.id,
            amount,
            stamp,
            request.time_zone,
            None,
            None,
            stored.account.version,
            stored.account.user_id,
            now,
            note=(request.note or "").strip() or None,
            kind=kind,
        )
        anchor = observations(None, (check,))[0]
        links = tuple(
            Coverage(check.id, 1, e.id, e.current.revision, True)
            for e in stored.expenses
            if e.current.active and on_or_before_day(e.current, anchor)
        )
        expected = expected_at(
            anchor,
            anchors[-1] if anchors else None,
            stored.expenses,
            (*stored.coverage, *links),
        )
        difference = None if expected is None else amount - expected
        for value in (expected, difference):
            if value is not None and abs(value) > MAX_MINOR_UNITS:
                raise RecordingInputError(
                    "amount_out_of_range", "The resulting recorded amount is too large."
                )
        check = replace(check, expected_minor=expected, difference_minor=difference)
        mutation = Mutation(check, links, "balance_check")
        candidate = apply(stored, mutation, now)
        for expense in candidate.expenses:
            validate_monotonic(
                expense,
                observations(candidate.opening, candidate.checks),
                candidate.coverage,
            )
        _view(candidate)
        preview = {
            "account_version": stored.account.version,
            "currency": stored.account.currency,
            "currency_fraction_digits": currency_exponent(stored.account.currency),
            "expected_amount_minor": expected,
            "observed_amount_minor": amount,
            "difference_minor": difference,
            "as_of": stamp,
            "time_zone": request.time_zone,
            "preview_token": token("check", stored.account.id, None, request),
        }
        return mutation, preview

    def preview_opening(
        self, *, user_id: str, account_id: str, request: LoopOpeningRequest
    ) -> dict[str, Any]:
        stored = self._current(user_id, account_id, request.expected_version)
        _, preview = self._opening(stored, request)
        return preview

    def write_opening(
        self,
        *,
        user_id: str,
        account_id: str,
        request: LoopOpeningRequest,
        idempotency_key: str,
    ) -> OperationResult:
        account_id = self.accounts.get(
            user_id=user_id, account_id=account_id, scope=PERSONAL
        ).account.id

        def plan(stored: StoredAccount) -> Mutation:
            mutation, preview = self._opening(stored, request)
            self._confirmed(request, preview)
            return mutation

        return self.repository.mutate(
            user_id=user_id,
            account_id=account_id,
            idempotency_key=idempotency_key,
            identity_hash=token("opening", account_id, None, request),
            expected_version=request.expected_version,
            planner=plan,
            scope=PERSONAL,
        )

    def _opening(
        self, stored: StoredAccount, request: LoopOpeningRequest
    ) -> tuple[Mutation, dict[str, Any]]:
        now = self.clock()
        current = stored.opening.current if stored.opening else None
        if current is None and request.as_of is None:
            raise RecordingInputError(
                "field_missing", "Review a specific date for this starting balance."
            )
        if request.expected_revision != (current.revision if current else None):
            raise StaleVersion()
        write = plan_opening_write(
            account_type=stored.account.type,
            currency=stored.account.currency,
            amount=request.amount,
            as_of=request.as_of,
            time_zone=request.time_zone,
            reason=request.reason,
            current=current,
            now=now,
        )
        zone = ZoneInfo(write.time_zone)
        if any(
            write.as_of.astimezone(zone).date() > c.as_of.astimezone(zone).date()
            for c in stored.checks
        ):
            raise RecordingInputError(
                "opening_after_check",
                "A starting balance cannot follow a recorded balance check.",
            )
        revision = OpeningRevision(
            (current.revision if current else 0) + 1,
            write.amount_minor,
            write.as_of,
            write.time_zone,
            write.reason,
            stored.account.user_id,
            now,
            current.estimate_basis if current else None,
        )
        opening = OpeningRecord(
            stored.opening.id if stored.opening else str(uuid4()),
            stored.account.id,
            (*stored.opening.revisions, revision) if stored.opening else (revision,),
        )
        anchor = observations(opening, ())[0]
        answers = _answers(request.coverage, "activity_id")
        applicable = {
            e.id
            for e in stored.expenses
            if e.current.active and on_or_before_day(e.current, anchor)
        }
        if set(answers) - applicable:
            raise RecordingInputError(
                "coverage_invalid", "The selected activity falls after the opening date."
            )
        questions, links = [], []
        for e in stored.expenses:
            if e.id not in applicable:
                continue
            choice = answers.get(e.id)
            questions.append(
                {
                    "activity_id": e.id,
                    "amount_minor": e.current.amount_minor,
                    "amount": format_minor_units(
                        e.current.amount_minor, stored.account.currency
                    ),
                    "occurred_at": e.current.occurred_at,
                    "note": e.current.note,
                    "included": choice,
                }
            )
            if choice is not None:
                links.append(
                    Coverage(anchor.id, anchor.revision, e.id, e.current.revision, choice)
                )
        ready = set(answers) == applicable
        mutation = Mutation(opening, tuple(links), "opening_balance")
        after = None
        if ready:
            candidate = apply(stored, mutation, now)
            for e in candidate.expenses:
                validate_monotonic(
                    e, observations(opening, candidate.checks), candidate.coverage
                )
            after = _view(candidate)
        return mutation, {
            "account_version": stored.account.version,
            "ready": ready,
            "activities": questions,
            "before": _view(stored),
            "after": after,
            "preview_token": token("opening", stored.account.id, None, request)
            if ready
            else None,
        }

    @staticmethod
    def _record_id(value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(UUID(value))
        except ValueError:
            raise AccountNotFound() from None

    @staticmethod
    def _confirmed(
        request: ActivityRequest | CheckRequest | LoopOpeningRequest,
        preview: dict[str, Any],
    ) -> None:
        if preview.get("ready") is False:
            raise RecordingInputError(
                "balance_coverage_required",
                "Review whether earlier activity was included in each balance.",
            )
        if request.preview_token != preview["preview_token"]:
            raise RecordingInputError(
                "preview_required", "Review the proposed change before saving it."
            )
