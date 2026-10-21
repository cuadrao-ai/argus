"""Preserve old expense bodies, review tokens and receipt identity hashes."""

from dataclasses import replace
from typing import Any

from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import AccountNotFound, RecordingInputError
from argus.domain.recording.loop_schemas import ActivityRequest
from argus.domain.recording.loop_service import token
from argus.domain.recording.loop_storage import OperationResult
from argus.domain.recording.money_plan import MoneyPlan, plan
from argus.domain.recording.money_schemas import MoneyCoverage, MoneyRequest
from argus.domain.recording.money_storage import transact
from argus.domain.recording.repository import StoredAccount


def legacy_plan(
    service: Any,
    user_id: str,
    account_id: str,
    request: ActivityRequest,
    record_id: str | None,
    accounts: list[StoredAccount],
) -> MoneyPlan:
    if record_id:
        stored = next((s for s in accounts if s.account.id == account_id), None)
        record = (
            next((e for e in stored.expenses if e.id == record_id), None)
            if stored
            else None
        )
        if record is None:
            raise AccountNotFound()
        if record and (
            not record.current.active
            or record.current.kind != "expense"
            or (record.current.activity_id or record.id) != record_id
        ):
            raise RecordingInputError(
                "canonical_activity_required",
                "Open the complete activity to correct its current account.",
            )
    body = MoneyRequest(
        kind="expense",
        account_id=account_id,
        amount=request.amount,
        occurred_at=request.occurred_at,
        time_zone=request.time_zone,
        note=request.note,
        category_id=request.category_id,
        reason=request.reason,
        expected_revision=request.expected_revision,
        expected_versions={account_id: request.expected_version},
        coverage=[
            MoneyCoverage(
                account_id=account_id,
                observation_id=a.observation_id,
                included=a.included,
            )
            for a in request.coverage
        ],
    )
    result = plan(accounts, body, record_id, service.clock(), legacy=True)
    effect = next(
        a for a in result.preview["affected_accounts"] if a["account_id"] == account_id
    )
    preview = {
        "account_version": request.expected_version,
        "ready": result.preview["ready"],
        "observations": effect["observations"],
        "before": effect["before"],
        "after": effect["after"],
        "preview_token": token("activity", account_id, record_id, request)
        if result.preview["ready"]
        else None,
    }
    return replace(result, preview=preview)


def preview(
    service: Any,
    *,
    user_id: str,
    account_id: str,
    request: ActivityRequest,
    record_id: str | None = None,
) -> dict[str, Any]:
    account_id = service.accounts.get(
        user_id=user_id, account_id=account_id, scope=PERSONAL
    ).account.id
    return legacy_plan(
        service,
        user_id,
        account_id,
        request,
        service._record_id(record_id),
        service.accounts.list_accounts(user_id=user_id, scope=PERSONAL),
    ).preview


def write(
    service: Any,
    *,
    user_id: str,
    account_id: str,
    request: ActivityRequest,
    idempotency_key: str,
    record_id: str | None = None,
) -> OperationResult:
    account_id = service.accounts.get(
        user_id=user_id, account_id=account_id, scope=PERSONAL
    ).account.id
    record_id = service._record_id(record_id)

    def planner(accounts: list[StoredAccount]) -> MoneyPlan:
        result = legacy_plan(service, user_id, account_id, request, record_id, accounts)
        service._confirmed(request, result.preview)
        return result

    records, aid, revision, _, replayed = transact(
        service.repository,
        user_id,
        idempotency_key,
        token("activity", account_id, record_id, request),
        planner,
        service.clock(),
        account_id,
        scope=PERSONAL,
    )
    stored = next(s for s in records if s.account.id == account_id)
    return OperationResult(stored, aid, revision, "expense", replayed)
