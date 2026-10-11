from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from argus.domain.owner_scope import BusinessSpace, OwnerScope
from argus.domain.recording.currency import (
    currency_exponent,
    format_minor_units,
    normalize_currency,
    parse_minor_units,
)
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RecordingInputError,
)
from argus.domain.recording.loop_schemas import CATEGORY_IDS
from argus.domain.recording.loop_service import _stamp
from argus.domain.recording.money_plan import request_identity
from argus.domain.recording.money_schemas import MoneyRequest

if TYPE_CHECKING:
    from argus.domain.recording.repository import (
        FinancialAccountRepository,
        StoredAccount,
    )


@dataclass(frozen=True)
class OwnerFundedExpense:
    activity_id: str
    record_id: str
    user_id: str
    owner_space_id: str
    currency: str
    amount_minor: int
    occurred_at: datetime
    time_zone: str
    note: str | None
    category_id: str | None
    recorded_at: datetime

    def response(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "revision": 1,
            "kind": "expense",
            "amount_minor": self.amount_minor,
            "amount": format_minor_units(self.amount_minor, self.currency),
            "currency": self.currency,
            "currency_fraction_digits": currency_exponent(self.currency),
            "occurred_at": self.occurred_at,
            "time_zone": self.time_zone,
            "note": self.note,
            "category_id": self.category_id,
            "source_id": None,
            "purchase_activity_id": None,
            "purchase_revision": None,
            "reversal_of_activity_id": None,
            "reversal_of_revision": None,
            "reason": None,
            "recorded_at": self.recorded_at,
            "recorded_by": self.user_id,
            "funding": "owner_funds",
            "legs": [],
        }


class FundedAccounts(list["StoredAccount"]):
    def __init__(
        self, accounts: list[StoredAccount], owner_funded: list[OwnerFundedExpense]
    ) -> None:
        super().__init__(accounts)
        self.owner_funded = owner_funded


def validate(
    request: MoneyRequest,
    scope: OwnerScope,
    now: datetime,
    activity_id: str | None = None,
) -> tuple[str, int, datetime]:
    request = MoneyRequest.model_validate(request.model_dump())
    funding = request.owner_funding
    if (
        not isinstance(scope, BusinessSpace)
        or funding is None
        or str(funding.owner_space_id) != scope.space_id
    ):
        raise AccountNotFound()
    if activity_id is not None:
        raise RecordingInputError(
            "recorded_correction_unsupported", "Recorded corrections are not supported."
        )
    currency = normalize_currency(funding.currency)
    amount = parse_minor_units(request.amount, currency)
    if amount <= 0:
        raise RecordingInputError("amount_positive_required", "Enter a positive amount.")
    if request.category_id is not None and request.category_id not in CATEGORY_IDS:
        raise RecordingInputError("category_unknown", "Choose an available category.")
    return currency, amount, _stamp(request.occurred_at, request.time_zone, now)


def preview(
    request: MoneyRequest,
    scope: OwnerScope,
    now: datetime,
    activity_id: str | None = None,
) -> dict[str, Any]:
    validate(request, scope, now, activity_id)
    return {
        "ready": True,
        "expected_versions": {},
        "affected_accounts": [],
        "reviewed_request": request.model_dump(mode="json", exclude={"preview_token"}),
        "preview_token": request_identity(request, None),
    }


def write(
    repository: FinancialAccountRepository,
    user_id: str,
    request: MoneyRequest,
    key: str,
    scope: OwnerScope,
    now: datetime,
    activity_id: str | None = None,
    entered: bool = False,
) -> dict[str, Any]:
    from argus.domain.recording.repository import InMemoryFinancialAccountRepository

    currency, amount, stamp = validate(request, scope, now, activity_id)
    identity = request_identity(request, None)
    preview_valid = entered or request.preview_token == identity
    row = OwnerFundedExpense(
        str(uuid4()),
        str(uuid4()),
        user_id,
        scope.space_id,
        currency,
        amount,
        stamp,
        request.time_zone,
        request.note,
        request.category_id,
        now,
    )
    if not isinstance(repository, InMemoryFinancialAccountRepository):
        from argus.domain.recording.owner_funds_postgres import transact

        return transact(repository, row, key, identity, preview_valid)
    with repository._lock:
        receipt = repository._money_receipts.get((user_id, None, key))
        if receipt:
            old_hash, aid, revision, affected = receipt
            if old_hash != identity:
                raise IdempotencyConflict()
            existing = repository._owner_funded.get(aid)
            if existing is None or existing.owner_space_id != scope.space_id:
                raise IdempotencyConflict()
            return {"activity": existing.response(), "accounts": [], "replayed": True}
        if not preview_valid:
            raise RecordingInputError(
                "preview_required", "Review the proposed change before saving it."
            )
        repository._owner_funded[row.activity_id] = row
        repository._money_receipts[(user_id, None, key)] = (
            identity,
            row.activity_id,
            1,
            (),
        )
        return {"activity": row.response(), "accounts": [], "replayed": False}
