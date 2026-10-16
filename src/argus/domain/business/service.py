"""Business pilot operations over the owners that already hold each fact.

Documents own capture, the source and preparation; the import queue owns the
reviewed proposal and its one recorded expense; the money service owns canonical
activity. Every method takes a ``BusinessScope`` from ``resolve_business_scope``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from argus.domain import financial_search
from argus.domain.business import ledger
from argus.domain.business.authority import ActionError
from argus.domain.business.config import business_chat_enabled
from argus.domain.business.receipts import (
    CLOSED,
    Receipt,
    compose,
    updates,
)
from argus.domain.business.scope import BusinessScope
from argus.domain.ingestion.documents.config import (
    SOURCE_MEDIA_TYPES,
    load_document_extraction_settings,
)
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store import CaptureHook
from argus.domain.ingestion.receipt_review import RECEIPT_EVENT_STATES, receipt_ids
from argus.domain.ingestion.reconcile.model import ReconcileError, StaleEvent
from argus.domain.ingestion.reconcile.recording import DEFAULT_ZONE
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.recording.errors import IdempotencyConflict
from argus.domain.recording.money_reads import current_activities
from argus.domain.recording.money_schemas import ELIGIBILITY, MoneyRequest
from argus.domain.recording.schemas import CreateFinancialAccountRequest

EXPENSE_ACCOUNT_TYPES = ELIGIBILITY["expense"]
# A review field and the import resolution it sets. The merchant is the note
# ``accept`` records (``recorded_note``); clearing it falls back to the evidence.
_RESOLUTION = {
    "merchant": "note",
    "occurred_on": "occurred_on",
    "amount": "amount",
    "currency": "currency",
    "category_id": "category_id",
    "account_id": "account_id",
}
# Import queue refusals renamed to the codes the Business client shows.
_CODES = {
    "import_unresolved": "missing_fields",
    "import_currency_mismatch": "currency_mismatch",
}


class BusinessError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class BusinessService:
    def __init__(
        self,
        documents: DocumentsService,
        imports: ReconciliationService,
        captured: Callable[[str], frozenset[str]],
    ) -> None:
        self.documents, self.imports, self.captured = documents, imports, captured
        self.accounts = imports.money.accounts

    # --- Workspace -------------------------------------------------------
    def workspace(self, scope: BusinessScope) -> dict[str, Any]:
        accounts = self.accounts_for_expenses(scope)
        return {
            "accounts": accounts,
            # An expense is saved in its account's currency; nothing converts.
            "currencies": sorted({account["currency"] for account in accounts}),
            "assistant_available": False,
            # Whether /biz offers a composer, New chat and Recents at all.
            "chat_available": business_chat_enabled(),
            "receipt_limits": {
                "max_bytes": load_document_extraction_settings().max_bytes,
                "media_types": list(SOURCE_MEDIA_TYPES),
            },
        }

    def accounts_for_expenses(self, scope: BusinessScope) -> list[dict[str, Any]]:
        return [
            {
                "id": stored.account.id,
                "nickname": stored.account.nickname,
                "type": stored.account.type,
                "currency": stored.account.currency,
            }
            for stored in self.accounts.list_accounts(
                user_id=scope.person_id, scope=scope.owner
            )
            if stored.account.type in EXPENSE_ACCOUNT_TYPES
            and not stored.account.archived
        ]

    def create_account(
        self, scope: BusinessScope, request: CreateFinancialAccountRequest, key: str
    ) -> tuple[dict[str, Any], bool]:
        result = self.accounts.create(
            user_id=scope.person_id,
            idempotency_key=key,
            request=request,
            scope=scope.owner,
        )
        account = result.stored.account
        return (
            {
                "id": account.id,
                "nickname": account.nickname,
                "type": account.type,
                "currency": account.currency,
            },
            result.created,
        )

    # --- Receipts --------------------------------------------------------
    def receipts(self, scope: BusinessScope) -> list[Receipt]:
        person = scope.person_id
        events = self.imports.list(
            user_id=person, states=RECEIPT_EVENT_STATES, scope=scope.owner
        )
        whatsapp = self.captured(person)
        found = []
        for connection in self.documents.hub.connections.list(
            user_id=person, scope=scope.owner
        ):
            if connection.source != "statement" or connection.status == "disconnected":
                continue
            try:
                found.append(self._compose(scope, connection.id, events, whatsapp))
            except DocumentServiceError as error:
                if error.code != "document_source_unavailable":
                    raise
        return sorted(found, key=lambda item: item.draft.created_at, reverse=True)

    def receipt(self, scope: BusinessScope, receipt_id: str) -> Receipt:
        events = self.imports.list(
            user_id=scope.person_id, states=RECEIPT_EVENT_STATES, scope=scope.owner
        )
        return self._compose(scope, receipt_id, events, self.captured(scope.person_id))

    def _compose(
        self,
        scope: BusinessScope,
        receipt_id: str,
        events: list[dict[str, Any]],
        whatsapp: frozenset[str],
    ) -> Receipt:
        person = scope.person_id
        draft = self.documents.get(
            user_id=person, connection_id=receipt_id, scope=scope.owner
        )
        return compose(
            draft,
            self.documents.store.get(user_id=person, connection_id=receipt_id),
            events,
            "whatsapp" if receipt_id in whatsapp else "web",
            read_pending=self.documents.read_pending(person, receipt_id, draft),
        )

    async def upload(
        self,
        scope: BusinessScope,
        *,
        content: bytes,
        filename: str,
        media_type: str,
        consent: bool,
        on_capture: CaptureHook | None = None,
    ) -> Receipt:
        outcome = await self.documents.upload(
            user_id=scope.person_id,
            content=content,
            filename=filename,
            media_type=media_type,
            consent=consent,
            scope=scope.owner,
            on_capture=on_capture,
        )
        # The same bytes saved before come back as that receipt, said so.
        return replace(
            self.receipt(scope, outcome.connection_id), replayed=outcome.replayed
        )

    def queue(self, scope: BusinessScope, receipt_id: str) -> None:
        """The owner chose AI preparation for a saved receipt."""

        self.documents.queue(
            user_id=scope.person_id,
            connection_id=receipt_id,
            consent=True,
            scope=scope.owner,
        )

    def source(self, scope: BusinessScope, receipt_id: str) -> tuple[str, bytes]:
        self.documents.get(
            user_id=scope.person_id, connection_id=receipt_id, scope=scope.owner
        )
        from argus.domain.ingestion.documents.objects import SourceStorageUnavailable

        try:
            rebuilt = self.documents.store.rebuilt(
                user_id=scope.person_id, connection_id=receipt_id
            )
        except SourceStorageUnavailable:
            raise DocumentServiceError(
                "document_storage_unavailable", retryable=True
            ) from None
        if rebuilt is None:
            raise DocumentServiceError("document_source_unavailable")
        return rebuilt

    async def start_entry(
        self,
        scope: BusinessScope,
        receipt_id: str,
        version: int,
        account_id: str | None = None,
    ) -> int:
        """The version a review applies to. For a receipt with no single
        purchase, first record the owner's one purchase, then that version.

        A repeat delivers the same purchase, so a replay, a second tab or a
        restart enters one. ``account_id``, the account the review will set, is
        refused before anything is entered when it is outside the space.
        """

        current = await asyncio.to_thread(self.receipt, scope, receipt_id)
        if current.enterable:
            if version != current.version:
                raise StaleEvent()
            if account_id and account_id not in self._account_ids(scope):
                raise ReconcileError(
                    "financial_account_not_found", "Choose your own account."
                )
            await self.documents.enter(
                user_id=scope.person_id, connection_id=receipt_id, scope=scope.owner
            )
            current = await asyncio.to_thread(self.receipt, scope, receipt_id)
            version = current.version
        await asyncio.to_thread(self._set_aside, scope, current)
        return version

    def _account_ids(self, scope: BusinessScope) -> set[str]:
        return {
            stored.account.id
            for stored in self.accounts.list_accounts(
                user_id=scope.person_id, scope=scope.owner
            )
        }

    def _set_aside(self, scope: BusinessScope, receipt: Receipt) -> None:
        """Beside the owner's entry, dismiss every open purchase a read found,
        kept as history, so only the owner's can become the expense. Runs on
        each review and confirm, so an entry interrupted before this finishes
        on the next one."""

        if not receipt.review.owner_entry:
            return
        person, owner = scope.person_id, scope.owner
        for read in receipt.review.read_purchases:
            state, version = read.state, read.version
            for _ in range(3):
                if state != "open":
                    break
                try:
                    self.imports.dismiss(
                        user_id=person,
                        event_id=read.event_id,
                        version=version,
                        scope=owner,
                    )
                    break
                except StaleEvent:
                    # A replayed delivery or another entry changed it first.
                    seen = self.imports.detail(
                        user_id=person, event_id=read.event_id, scope=owner
                    )
                    state, version = seen["state"], seen["version"]
            else:
                raise StaleEvent()

    def review(
        self,
        scope: BusinessScope,
        receipt_id: str,
        version: int,
        fields: Mapping[str, str | None],
    ) -> Receipt:
        """Corrections become the import's resolution; the evidence is untouched."""

        current = self.receipt(scope, receipt_id)
        if current.review.blocker == "possible_duplicate":
            # A possible repeat is settled by a person, never edited into a second expense.
            raise BusinessError("possible_duplicate")
        event_id = _event_id(current)
        try:
            self.imports.resolve(
                user_id=scope.person_id,
                event_id=event_id,
                version=version,
                changes={_RESOLUTION[name]: value for name, value in fields.items()},
                scope=scope.owner,
            )
        except ReconcileError as error:
            raise _renamed(error) from None
        return self.receipt(scope, receipt_id)

    def confirm(
        self, scope: BusinessScope, receipt_id: str, version: int, key: str
    ) -> Receipt:
        """The import accept path, as one expense for the receipt's total.

        A replay, a second key or a concurrent confirm records one expense.
        """

        current = self.receipt(scope, receipt_id)
        self._set_aside(scope, current)
        if current.status == "confirmed":
            return current
        if current.review.blocker == "possible_duplicate":
            raise BusinessError("possible_duplicate")
        if current.version == version and current.missing_fields:
            raise BusinessError("missing_fields")
        try:
            self.imports.accept_reviewed(
                user_id=scope.person_id,
                event_id=_event_id(current),
                version=version,
                idempotency_key=key,
                kind="expense",
                scope=scope.owner,
            )
        except ReconcileError as error:
            if error.code != "import_already_accepted":
                raise _renamed(error) from None
        return self.receipt(scope, receipt_id)

    # --- Expenses ---------------------------------------------------------
    def expenses(
        self, scope: BusinessScope, start: date, end: date | None = None
    ) -> list[dict[str, Any]]:
        end = end if end is not None else ledger.today()
        return self._expenses(scope, self._activities(scope), start, end)

    def expense_rows(
        self, scope: BusinessScope, start: date, end: date
    ) -> list[dict[str, Any]]:
        """The period's saved expenses with their minor-unit amounts, for totals."""

        return ledger.expenses(self._activities(scope), {}, start, end)

    def expense(self, scope: BusinessScope, expense_id: str) -> dict[str, Any]:
        """One saved expense of this Business, with when it was recorded and its
        revision; any other id, including another Business's, is not found."""

        for activity in ledger.expense_activities(self._activities(scope)):
            if activity["activity_id"] == expense_id:
                [item] = self._expenses(scope, [activity], date.min, date.max)
                return {
                    **item,
                    "recorded_at": activity.get("recorded_at"),
                    "revision": activity.get("revision"),
                }
        raise ActionError("not_found", "expense_not_found")

    def _expenses(
        self,
        scope: BusinessScope,
        activities: list[dict[str, Any]],
        start: date,
        end: date,
    ) -> list[dict[str, Any]]:
        ids = [item["activity_id"] for item in ledger.expense_activities(activities)]
        with self.imports.store.transaction(scope.person_id, scope=scope.owner) as tx:
            receipt_of = receipt_ids(tx, self.documents.store, scope.person_id, ids)
        return [
            _wire(item) for item in ledger.expenses(activities, receipt_of, start, end)
        ]

    def search(
        self,
        scope: BusinessScope,
        q: str,
        limit: int,
        views: Mapping[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Expenses and accounts through the canonical financial search, plus
        receipts matched by the same rule on merchant, filename and amount.

        ``views`` are the receipt summaries as the API shows them (a linked draft
        owns merchant, amount and expense), so the match sees what the person
        sees. A receipt whose expense is already a hit is left out: the expense
        opens it.
        """

        query = financial_search.query_text(q)
        found = financial_search.hits(
            self.accounts, scope.person_id, scope=scope.owner, query=query
        )
        activities = [
            hit.activity.model_dump()
            for hit in found
            if isinstance(hit, financial_search.ActivityHit)
        ]
        expenses = self._expenses(scope, activities, date.min, date.max)[:limit]
        listed = {expense["id"] for expense in expenses}
        shown = views or {}
        receipts = [
            summary
            for receipt in self.receipts(scope)
            for summary in [shown.get(receipt.id) or receipt.summary()]
            if summary["expense_id"] not in listed
            and financial_search.matches(query, _summary_text(summary))
        ]
        accounts = [
            {
                "id": hit.account.id,
                "nickname": hit.account.nickname,
                "type": hit.account.type,
                "currency": hit.account.currency,
            }
            for hit in found
            if isinstance(hit, financial_search.AccountHit)
        ]
        return {
            "expenses": expenses,
            "receipts": receipts[:limit],
            "accounts": accounts[:limit],
        }

    def record_expense(
        self, scope: BusinessScope, entered: Mapping[str, Any], key: str
    ) -> dict[str, Any]:
        """A manual expense through the canonical money service."""

        from argus.domain.recording.repository import InMemoryFinancialAccountRepository

        if not isinstance(self.accounts._repository, InMemoryFinancialAccountRepository):
            raise ReconcileError(
                "human_approval_required", "Review and approve the expense draft first."
            )

        request = MoneyRequest(
            kind="expense",
            account_id=entered["account_id"],
            amount=entered["amount"],
            occurred_at=datetime.combine(
                entered["occurred_on"], time(0, 0), tzinfo=ZoneInfo(DEFAULT_ZONE)
            ),
            time_zone=DEFAULT_ZONE,
            note=entered["merchant"],
            category_id=entered["category_id"],
        )
        activity = self.imports.money.write_entered(
            user_id=scope.person_id,
            request=request,
            idempotency_key=key,
            scope=scope.owner,
        )["activity"]
        recorded = ledger.expenses([activity], {}, date.min, date.max)
        if len(recorded) != 1:
            # This key recorded something that is not an expense.
            raise IdempotencyConflict()
        return _wire(recorded[0])

    def overview(
        self, scope: BusinessScope, start: date, end: date | None = None
    ) -> dict[str, Any]:
        today = ledger.today()
        end = end if end is not None else today
        receipts = self.receipts(scope)
        activities = self._activities(scope)
        recorded = ledger.recorded_at(activities)
        outside = [
            item
            for item in ledger.expenses(activities, {}, date.min, date.max)
            if not start <= item["occurred_on"] <= end
        ]
        return {
            "from": start,
            "to": end,
            "today": today,
            "totals": ledger.totals(ledger.expenses(activities, {}, start, end)),
            "outside_period_count": len(outside),
            "outside_period_latest_on": max(
                (item["occurred_on"] for item in outside), default=None
            ),
            "last_received_at": max((r.draft.created_at for r in receipts), default=None),
            "last_confirmed_at": max(recorded.values(), default=None),
        }

    def updates(
        self, scope: BusinessScope, views: Mapping[str, dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        return updates(
            self.receipts(scope), ledger.recorded_at(self._activities(scope)), views
        )

    def inbox(self, scope: BusinessScope) -> list[Receipt]:
        return [r for r in self.receipts(scope) if r.status not in CLOSED]

    def _activities(self, scope: BusinessScope) -> list[dict[str, Any]]:
        return current_activities(
            self.accounts.list_accounts(user_id=scope.person_id, scope=scope.owner)
        )


def _summary_text(summary: Mapping[str, Any]) -> str:
    return " ".join(
        filter(None, [summary["merchant"], summary["filename"], summary["amount"]])
    )


def _wire(expense: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in expense.items() if key != "amount_minor"}


def _event_id(receipt: Receipt) -> str:
    if receipt.review.event_id is None:
        raise BusinessError("receipt_not_prepared")
    return receipt.review.event_id


def _renamed(error: ReconcileError) -> Exception:
    code = _CODES.get(error.code)
    return BusinessError(code) if code else error
