"""Money orchestration over the shared atomic repository, within one owner scope."""

from typing import Any
from uuid import UUID

from argus.domain.owner_scope import OwnerScope
from argus.domain.recording.errors import (
    AccountNotFound,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.money_plan import MoneyPlan, plan, request_identity
from argus.domain.recording.money_reads import (
    activity,
    current_activities,
    groups,
)
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.repository import StoredAccount
from argus.domain.recording.schemas import account_response
from argus.domain.recording.service import FinancialAccountService


class MoneyService:
    def __init__(self, accounts: FinancialAccountService) -> None:
        self.accounts = accounts
        self.repository = accounts._repository

    def preview(
        self,
        *,
        user_id: str,
        request: MoneyRequest,
        scope: OwnerScope,
        activity_id: str | None = None,
    ) -> dict[str, Any]:
        activity_id = self._id(activity_id)
        if request.owner_funding is not None:
            from .owner_funds import preview

            return preview(request, scope, self.accounts._clock(), activity_id)
        records = self.accounts.list_accounts(user_id=user_id, scope=scope)
        self.require_personal(records, request, activity_id)
        return plan(
            records,
            request,
            activity_id,
            self.accounts._clock(),
        ).preview

    def write(
        self,
        *,
        user_id: str,
        request: MoneyRequest,
        idempotency_key: str,
        scope: OwnerScope,
        activity_id: str | None = None,
    ) -> dict[str, Any]:
        from argus.domain.recording.money_storage import transact

        if request.owner_funding is not None:
            from .owner_funds import write

            return write(
                self.repository,
                user_id,
                request,
                idempotency_key,
                scope,
                self.accounts._clock(),
                activity_id,
            )
        activity_id = self._id(activity_id)

        def planner(accounts: list[StoredAccount]) -> MoneyPlan:
            self.require_personal(accounts, request, activity_id)
            return self.prepare(accounts, request, activity_id)

        records, aid, revision, affected, replayed = transact(
            self.repository,
            user_id,
            idempotency_key,
            request_identity(request, activity_id),
            planner,
            self.accounts._clock(),
            scope=scope,
        )
        return {
            "activity": activity(records, aid, revision),
            "accounts": [
                account_response(s) for s in records if s.account.id in affected
            ],
            "replayed": replayed,
        }

    def write_entered(
        self,
        *,
        user_id: str,
        request: MoneyRequest,
        idempotency_key: str,
        scope: OwnerScope,
    ) -> dict[str, Any]:
        """Record a new activity exactly as the person entered it.

        For a form with no preview step. It is planned under the account lock
        and refused when a balance question needs an answer. The idempotency
        identity is the entered request, so a retry replays the first write
        even though that write moved the account versions a preview would name.
        """

        if request.owner_funding is not None:
            from .owner_funds import write

            return write(
                self.repository,
                user_id,
                request,
                idempotency_key,
                scope,
                self.accounts._clock(),
                entered=True,
            )

        from argus.domain.recording.money_storage import transact

        def planner(accounts: list[StoredAccount]) -> MoneyPlan:
            self.require_personal(accounts, request, None)
            result = plan(accounts, request, None, self.accounts._clock())
            if not result.preview["ready"]:
                raise RecordingInputError(
                    "balance_coverage_required", "Review each balance question."
                )
            return result

        records, aid, revision, _, replayed = transact(
            self.repository,
            user_id,
            idempotency_key,
            request_identity(request, None),
            planner,
            self.accounts._clock(),
            scope=scope,
        )
        return {"activity": activity(records, aid, revision), "replayed": replayed}

    def prepare(
        self,
        accounts: list[StoredAccount],
        request: MoneyRequest,
        activity_id: str | None = None,
    ) -> MoneyPlan:
        result = plan(
            accounts, request, activity_id, self.accounts._clock(), confirming=True
        )
        if request.expected_versions != result.preview["expected_versions"]:
            raise StaleVersion()
        if not result.preview["ready"]:
            raise RecordingInputError(
                "balance_coverage_required", "Review each balance question."
            )
        if request.preview_token != result.preview["preview_token"]:
            raise RecordingInputError(
                "preview_required", "Review the proposed change before saving it."
            )
        return result

    def detail(
        self, *, user_id: str, activity_id: str, scope: OwnerScope
    ) -> dict[str, Any]:
        aid = self._id(activity_id)
        assert aid is not None
        return activity(self.accounts.list_accounts(user_id=user_id, scope=scope), aid)

    def history(
        self, *, user_id: str, activity_id: str, scope: OwnerScope
    ) -> dict[str, Any]:
        records = self.accounts.list_accounts(user_id=user_id, scope=scope)
        aid = self._id(activity_id)
        assert aid is not None
        for row in getattr(records, "owner_funded", ()):
            if row.activity_id == aid:
                return {"items": [row.response()], "next_cursor": None}
        revisions = groups(records).get(aid)
        if not revisions:
            raise AccountNotFound()
        return {
            "items": [
                activity(records, aid, r)
                for r in sorted(revisions, reverse=True)
                if any(s.account.user_id == user_id for s, _, __ in revisions[r])
            ],
            "next_cursor": None,
        }

    def purchases(
        self, *, user_id: str, scope: OwnerScope, currency: str | None = None
    ) -> dict[str, Any]:
        records = current_activities(
            self.accounts.list_accounts(user_id=user_id, scope=scope)
        )
        refunded: dict[str, int] = {}
        for item in records:
            purchase_id = item["purchase_activity_id"]
            if purchase_id:
                refunded[purchase_id] = (
                    refunded.get(purchase_id, 0) + item["amount_minor"]
                )
        items = []
        for item in records:
            if item["kind"] != "expense" or currency and item["currency"] != currency:
                continue
            total = refunded.get(item["activity_id"], 0)
            items.append(
                {
                    **item,
                    "refunded_minor": total,
                    "refundable_minor": item["amount_minor"] - total,
                }
            )
        return {"items": sorted(items, key=lambda a: a["occurred_at"], reverse=True)}

    @staticmethod
    def require_personal(records, request, activity_id):
        referenced = {
            activity_id,
            request.purchase_activity_id,
            request.reversal_of_activity_id,
        }
        if any(
            row.activity_id in referenced for row in getattr(records, "owner_funded", ())
        ):
            raise RecordingInputError(
                "recorded_correction_unsupported",
                "Recorded owner-funded expenses cannot be changed.",
            )
        canonical = getattr(records, "canonical", None)
        if canonical is not None:
            from argus.domain.household.access import dependencies

            ids = dependencies(canonical.records, request, activity_id)
            if not ids <= {s.account.id for s in records}:
                raise AccountNotFound()

    @staticmethod
    def _id(value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(UUID(value))
        except ValueError:
            raise AccountNotFound() from None
