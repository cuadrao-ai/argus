"""Use cases for the first slice: create, reopen, edit, record or correct the opening.

Each use case validates through the domain modules, then asks the repository
for one atomic storage step. The identity a create request hashes is the
validated, normalized body, so two spellings of one request replay and a
changed body conflicts.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from argus.domain.backtest_admission import canonical_hash
from argus.domain.owner_scope import OwnerScope, Personal
from argus.domain.recording.accounts import (
    OPTIONAL_ASSET_TYPES,
    UNSET,
    AccountEdit,
    normalize_nickname,
    plan_account_edit,
    validate_share,
    validate_type,
)
from argus.domain.recording.currency import normalize_currency
from argus.domain.recording.errors import (
    AccountNotFound,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.records import plan_opening_write
from argus.domain.recording.repository import (
    CreateResult,
    FinancialAccountRepository,
    NewAccount,
    StoredAccount,
)
from argus.domain.recording.schemas import (
    CreateFinancialAccountRequest,
    EditFinancialAccountRequest,
    WriteOpeningRequest,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def blank_opening(scope: OwnerScope, account_type: str) -> str | None:
    """A Personal money account saved without a starting amount starts at a recorded 0."""
    if isinstance(scope, Personal) and account_type not in OPTIONAL_ASSET_TYPES:
        return "0"
    return None


class FinancialAccountService:
    def __init__(
        self,
        repository: FinancialAccountRepository,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._repository = repository
        self._clock = clock
        from argus.domain.recording.loop_service import FinancialLoopService

        self.loop = FinancialLoopService(self, repository, clock)

    def create(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        request: CreateFinancialAccountRequest,
        scope: OwnerScope,
    ) -> CreateResult:
        account = NewAccount(
            type=validate_type(request.type),
            currency=normalize_currency(request.currency),
            nickname=normalize_nickname(request.nickname),
            ownership_share_bps=validate_share(request.ownership_share_bps),
        )
        amount = (request.amount or "").strip() or blank_opening(scope, account.type)
        opening = None
        if amount is not None:
            opening = plan_opening_write(
                account_type=account.type,
                currency=account.currency,
                amount=amount,
                as_of=request.as_of,
                time_zone=request.time_zone,
                reason=None,
                current=None,
                now=self._clock(),
            )
        identity = canonical_hash(
            {
                "type": account.type,
                "currency": account.currency,
                "nickname": account.nickname,
                "ownership_share_bps": account.ownership_share_bps,
                "opening": None
                if opening is None
                else {
                    "amount_minor": opening.amount_minor,
                    # The default balance date is the creation instant, which a
                    # retry cannot reproduce; only an explicit date joins the identity.
                    "as_of": request.as_of.astimezone(timezone.utc).isoformat()
                    if request.as_of is not None
                    else None,
                    "time_zone": opening.time_zone,
                },
            }
        )
        return self._repository.create(
            user_id=user_id,
            idempotency_key=idempotency_key,
            identity_hash=identity,
            account=account,
            opening=opening,
            scope=scope,
        )

    def list_accounts(self, *, user_id: str, scope: OwnerScope) -> list[StoredAccount]:
        return self._repository.list_accounts(user_id=user_id, scope=scope)

    def get(self, *, user_id: str, account_id: str, scope: OwnerScope) -> StoredAccount:
        try:
            # A malformed id names nothing the caller can own; same answer as
            # another user's account, so probes learn nothing from the shape.
            account_id = str(UUID(account_id))
        except ValueError:
            raise AccountNotFound() from None
        stored = self._repository.get_account(
            user_id=user_id, account_id=account_id, scope=scope
        )
        if stored is None:
            raise AccountNotFound()
        return stored

    def edit(
        self,
        *,
        user_id: str,
        account_id: str,
        request: EditFinancialAccountRequest,
        scope: OwnerScope,
    ) -> StoredAccount:
        stored = self.get(user_id=user_id, account_id=account_id, scope=scope)
        if request.expected_version != stored.account.version:
            raise StaleVersion()
        edit = AccountEdit(
            nickname=request.nickname
            if "nickname" in request.model_fields_set
            else UNSET,
            type=request.type,
            currency=request.currency,
            archived=request.archived,
            ownership_share_bps=request.ownership_share_bps,
        )
        changes = plan_account_edit(
            stored.account,
            edit,
            has_records=stored.has_records,
            has_activity=stored.has_activity,
        )
        return self._repository.update_account(
            user_id=user_id,
            account_id=stored.account.id,
            expected_version=request.expected_version,
            changes=changes,
            scope=scope,
        )

    def write_opening(
        self,
        *,
        user_id: str,
        account_id: str,
        request: WriteOpeningRequest,
        scope: OwnerScope,
    ) -> StoredAccount:
        stored = self.get(user_id=user_id, account_id=account_id, scope=scope)
        if stored.expenses or stored.checks:
            raise RecordingInputError(
                "preview_required",
                "Review this starting balance against the recorded activity before saving.",
            )
        current = stored.opening.current if stored.opening is not None else None
        if (
            request.expected_version != stored.account.version
            or request.expected_revision != (current.revision if current else None)
        ):
            # The body is validated against the view the caller holds; when that
            # view is already stale, say so first. Storage re-checks under lock.
            raise StaleVersion()
        write = plan_opening_write(
            account_type=stored.account.type,
            currency=stored.account.currency,
            amount=request.amount,
            as_of=request.as_of,
            time_zone=request.time_zone,
            reason=request.reason,
            current=current,
            now=self._clock(),
        )
        return self._repository.write_opening(
            user_id=user_id,
            account_id=stored.account.id,
            expected_revision=request.expected_revision,
            # Caller-visible version: amount was signed and scaled under the
            # metadata that version names; storage refuses if the account moved.
            expected_version=request.expected_version,
            write=write,
            scope=scope,
        )
