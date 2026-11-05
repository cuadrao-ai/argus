"""Atomic ownership/link changes and their accepted replay identity."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from argus.domain.owner_scope import OwnerScope
from argus.domain.recording.accounts import LIABILITY_TYPES, OPTIONAL_ASSET_TYPES
from argus.domain.recording.asset_model import AssetChange
from argus.domain.recording.asset_schemas import AssetDetailsRequest
from argus.domain.recording.assets import AssetDetailsResult, require_asset
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.repository import StoredAccount

if TYPE_CHECKING:
    from argus.domain.recording.repository import InMemoryFinancialAccountRepository


def debt_id(request: AssetDetailsRequest) -> str | None:
    if request.related_debt_account_id is None:
        return None
    try:
        return str(UUID(request.related_debt_account_id))
    except ValueError:
        raise AccountNotFound() from None


def validate_debt(debt: StoredAccount | None) -> None:
    if debt is None:
        raise AccountNotFound()
    if debt.account.type not in LIABILITY_TYPES:
        raise RecordingInputError(
            "liability_required", "Choose an existing debt account."
        )


def validate_type_change(
    stored: StoredAccount, changes: dict[str, object], linked: bool
) -> None:
    target = changes.get("type", stored.account.type)
    if target == stored.account.type:
        return
    if linked or (
        stored.account.type in OPTIONAL_ASSET_TYPES
        and (stored.has_records or stored.asset_changes)
    ):
        raise RecordingInputError(
            "type_locked", "Keep the type with its estimates and saved asset details."
        )


def memory_write(
    repository: InMemoryFinancialAccountRepository,
    *,
    user_id: str,
    account_id: str,
    request: AssetDetailsRequest,
    idempotency_key: str,
    identity_hash: str,
    scope: OwnerScope,
) -> AssetDetailsResult:
    with repository._lock:
        stored = repository._owned(user_id, account_id, scope)
        previous = next(
            (c for c in stored.asset_changes if c.idempotency_key == idempotency_key),
            None,
        )
        if previous:
            if previous.identity_hash != identity_hash:
                raise IdempotencyConflict()
            return AssetDetailsResult(stored, previous.version, True)
        if stored.account.version != request.expected_version:
            raise StaleVersion()
        require_asset(stored)
        target = debt_id(request)
        if target is not None:
            validate_debt(repository._owned(user_id, target, scope))
        now = repository._clock()
        change = AssetChange(
            stored.account.version + 1,
            stored.account.ownership_share_bps,
            request.ownership_share_bps,
            stored.related_debt_account_id,
            target,
            user_id,
            now,
            idempotency_key,
            identity_hash,
        )
        updated = replace(
            stored,
            account=replace(
                stored.account,
                ownership_share_bps=request.ownership_share_bps,
                version=change.version,
                updated_at=now,
            ),
            related_debt_account_id=target,
            asset_changes=(*stored.asset_changes, change),
        )
        repository._accounts[account_id] = updated
        return AssetDetailsResult(updated, change.version, False)
