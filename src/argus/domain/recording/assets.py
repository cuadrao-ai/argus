"""Manual estimates and their one optional reference to an existing debt."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from argus.domain.recording.service import FinancialAccountService

from pydantic import BaseModel

from argus.domain.backtest_admission import canonical_hash
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.accounts import OPTIONAL_ASSET_TYPES
from argus.domain.recording.asset_schemas import AssetDetailsRequest, AssetEstimateRequest
from argus.domain.recording.currency import parse_minor_units
from argus.domain.recording.errors import (
    AccountNotFound,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.loop import CheckRecord, observations
from argus.domain.recording.loop_schemas import CheckRequest
from argus.domain.recording.loop_service import _stamp
from argus.domain.recording.loop_storage import Mutation, OperationResult, apply
from argus.domain.recording.records import OpeningRevision, _normalize_reason
from argus.domain.recording.repository import StoredAccount
from argus.domain.recording.schemas import FinancialAccountResponse, account_response


class AssetPreviewResponse(BaseModel):
    account: FinancialAccountResponse
    preview_token: str


class AssetOperationResponse(BaseModel):
    account: FinancialAccountResponse
    record_id: str
    revision: int
    replayed: bool


class AssetDetailsResponse(BaseModel):
    account: FinancialAccountResponse
    change_version: int
    replayed: bool


@dataclass(frozen=True)
class AssetDetailsResult:
    stored: StoredAccount
    change_version: int
    replayed: bool


def require_asset(stored: StoredAccount) -> None:
    if stored.account.type not in OPTIONAL_ASSET_TYPES:
        raise RecordingInputError(
            "asset_required", "Choose a property, vehicle or other asset."
        )


def identity(account_id: str, request: AssetEstimateRequest | AssetDetailsRequest) -> str:
    return canonical_hash(
        {
            "account_id": account_id,
            "kind": type(request).__name__,
            "request": request.model_dump(mode="json", exclude={"preview_token"}),
        }
    )


class AssetService:
    def __init__(self, accounts: FinancialAccountService) -> None:
        self.accounts = accounts

    def preview(
        self, owner: str, account_id: str, request: AssetEstimateRequest
    ) -> AssetPreviewResponse:
        stored = self.accounts.get(user_id=owner, account_id=account_id, scope=PERSONAL)
        if stored.account.version != request.expected_version:
            raise StaleVersion()
        mutation = self._estimate(stored, request)
        return AssetPreviewResponse(
            account=account_response(apply(stored, mutation, self.accounts._clock())),
            preview_token=identity(stored.account.id, request),
        )

    def write(
        self, owner: str, account_id: str, request: AssetEstimateRequest, key: str
    ) -> OperationResult:
        account_id = self.accounts.get(
            user_id=owner, account_id=account_id, scope=PERSONAL
        ).account.id
        token = identity(account_id, request)

        def plan(stored: StoredAccount) -> Mutation:
            if request.preview_token != token:
                raise RecordingInputError(
                    "preview_required", "Review this estimate before saving."
                )
            return self._estimate(stored, request)

        return self.accounts._repository.mutate(
            user_id=owner,
            account_id=account_id,
            idempotency_key=key,
            identity_hash=token,
            expected_version=request.expected_version,
            planner=plan,
            scope=PERSONAL,
        )

    def _estimate(self, stored: StoredAccount, request: AssetEstimateRequest) -> Mutation:
        require_asset(stored)
        basis = (request.estimate_basis or "").strip() or None
        if request.record_id is None:
            mutation, _ = self.accounts.loop._check(
                stored,
                CheckRequest(
                    expected_version=request.expected_version,
                    amount=request.amount,
                    as_of=request.as_of,
                    time_zone=request.time_zone,
                ),
            )
            assert isinstance(mutation.record, CheckRecord)
            return replace(
                mutation, record=replace(mutation.record, estimate_basis=basis)
            )
        try:
            selected_id = str(UUID(request.record_id))
        except ValueError:
            raise AccountNotFound() from None
        now = self.accounts._clock()
        stamp = _stamp(request.as_of, request.time_zone, now)
        reason = _normalize_reason(request.reason, required=True)
        amount = parse_minor_units(request.amount, stored.account.currency)
        anchors = observations(stored.opening, stored.checks)
        selected = next((a for a in anchors if a.id == selected_id), None)
        if selected is None:
            raise AccountNotFound()
        if selected.revision != request.expected_revision:
            raise StaleVersion()
        if stored.opening and stored.opening.id == selected_id:
            revision = OpeningRevision(
                selected.revision + 1,
                amount,
                stamp,
                request.time_zone,
                reason,
                stored.account.user_id,
                now,
                basis,
            )
            record = replace(
                stored.opening, revisions=(*stored.opening.revisions, revision)
            )
            mutation = Mutation(record, (), "opening_balance")
        else:
            old = next(c for c in stored.checks if c.id == selected_id)
            check = replace(
                old,
                revision=old.revision + 1,
                amount_minor=amount,
                as_of=stamp,
                time_zone=request.time_zone,
                estimate_basis=basis,
                reason=reason,
                recorded_by=stored.account.user_id,
                recorded_at=now,
                prior_revisions=(*old.prior_revisions, replace(old, prior_revisions=())),
            )
            mutation = Mutation(check, (), "balance_check")
        candidate = apply(stored, mutation, now)
        dates = [a.as_of for a in observations(candidate.opening, candidate.checks)]
        if dates != sorted(dates):
            raise RecordingInputError(
                "estimate_date_order",
                "Keep the corrected date between the surrounding estimates.",
            )
        return mutation

    def details(
        self, owner: str, account_id: str, request: AssetDetailsRequest, key: str
    ) -> AssetDetailsResult:
        account_id = self.accounts.get(
            user_id=owner, account_id=account_id, scope=PERSONAL
        ).account.id
        return self.accounts._repository.write_asset_details(
            user_id=owner,
            account_id=account_id,
            request=request,
            idempotency_key=key,
            identity_hash=identity(account_id, request),
            scope=PERSONAL,
        )
