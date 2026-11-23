"""Apply a correction to an accepted document's existing money activity."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from argus.domain.business.actions import document_ledger
from argus.domain.business.actions.fiscal import (
    comprobante_identity,
    require_distinct_fiscal_document,
)
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.dgii import DgiiDeclaration, PurchaseDeclaration
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    Known,
)
from argus.domain.business.document_type import DocumentType
from argus.domain.business.fiscal_identity import normalized_ncf
from argus.domain.business.purchase_review import changes_recorded_refund
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.reconcile.model import ImportEvent
from argus.domain.ingestion.reconcile.recording import recorded_activity_facts
from argus.domain.recording.canonical_groups import owner_closure
from argus.domain.recording.currency import (
    format_minor_units,
    normalize_currency,
    parse_minor_units,
)
from argus.domain.recording.errors import AccountNotFound, RecordingInputError
from argus.domain.recording.loop import observations
from argus.domain.recording.money_plan import plan
from argus.domain.recording.money_postgres import owner_lock, persist
from argus.domain.recording.money_schemas import MoneyCoverage, MoneyRequest
from argus.domain.recording.records import DEFAULT_TIME_ZONE
from argus.domain.recording.service import FinancialAccountService

_MONEY_FACTS = (
    "amount",
    "currency",
    "occurred_on",
    "counterparty",
    "kind",
)


@dataclass(frozen=True)
class Posting:
    record_id: UUID
    record_revision: int
    activity_revision: int
    account_id: UUID | None
    funding: str | None
    currency: str
    kind: str
    amount_minor: int
    as_of: datetime
    as_of_zone: str
    details: dict[str, Any]

    def activity(self, activity_id: UUID) -> dict[str, Any]:
        return {
            "activity_id": str(activity_id),
            "kind": self.kind,
            "amount": format_minor_units(self.amount_minor, self.currency),
            "currency": self.currency,
            "occurred_at": self.as_of,
            "time_zone": self.as_of_zone,
            "legs": [{"account_id": str(self.account_id)}] if self.account_id else [],
        }

    def posted_values(self) -> tuple:
        return (
            self.kind,
            self.amount_minor,
            self.currency,
            self.as_of,
            self.as_of_zone,
            self.details.get("note"),
        )


def revise_activity(
    tx: ActionTransaction,
    event: ImportEvent,
    before: BusinessFacts,
    after: BusinessFacts,
    document_type: DocumentType,
    declaration: DgiiDeclaration | None,
    accounts: FinancialAccountService,
) -> tuple[dict[str, Any] | None, UUID | None]:
    for field in ("amount", "currency", "occurred_on", "kind"):
        if not isinstance(getattr(after, field), Known):
            raise ActionError("invalid_input", "fact_required", context={"field": field})
    if Decimal(after.amount.value) <= 0:
        raise ActionError("invalid_input", "amount_positive_required")
    if (
        after.business_share.value is not None
        and after.business_share.value.kind == "partial"
    ):
        raise ActionError("invalid_input", "business_allocation_unsupported")

    business = event.resolution["business"]
    before_identity = comprobante_identity(business["facts"])
    after_identity = comprobante_identity(after.model_dump(mode="json"))
    previous = business.get("dgii") or {}
    _keep_refund(previous, declaration, after.kind.value)
    modified_ncf = declaration.modified_ncf if declaration else None
    fiscal_link_changed = before_identity != after_identity or (
        normalized_ncf(previous.get("modified_ncf")) != normalized_ncf(modified_ncf)
    )
    if fiscal_link_changed and document_ledger.sale_credit_link(tx, event):
        raise ActionError("invalid_input", "business_document_linked")
    if before_identity != after_identity:
        require_distinct_fiscal_document(tx, event, after)

    metadata = event.resolution.get("accepted")
    type_changed = document_type != business.get("document_type", "recibo")
    if not type_changed and all(
        getattr(before, field).value == getattr(after, field).value
        for field in _MONEY_FACTS
    ):
        return metadata, UUID(event.activity_id) if event.activity_id else None

    if (
        event.accept_key is None
        or (metadata or {}).get("activity_id") != event.activity_id
    ):
        raise ActionError("invalid_input", "business_document_linked")
    activity_id = document_ledger.original_activity(event)
    # The import lock already serializes bank matches, settlements and exports.
    for owner in owner_closure(tx.connection, {tx.context.owner_id}):
        owner_lock(tx.connection, owner)
    linked = document_ledger.linked(tx, event, activity_id)
    old = _current(tx, activity_id, linked=linked)

    try:
        if old.account_id is not None:
            _lock_account(tx, old.account_id)
            old = _current(tx, activity_id, linked=linked)
        new = _corrected(old, before, after)
        if not type_changed and new.posted_values() == old.posted_values():
            return metadata, activity_id
        if linked:
            raise ActionError("invalid_input", "business_document_linked")
        if new.kind not in ("expense", "income"):
            raise ActionError("invalid_input", "activity_kind_unsupported")
        if new.account_id is None:
            _write_no_account(tx, activity_id, old, new, event.updated_at)
        else:
            if new.currency != old.currency:
                raise ActionError("invalid_input", "import_currency_mismatch")
            _write_account(tx, activity_id, old, new, event.updated_at, accounts)
    except RecordingInputError as error:
        raise ActionError("invalid_input", error.code) from None
    except AccountNotFound:
        raise ActionError("not_found", "business_record_not_found") from None

    return (metadata or {}) | recorded_activity_facts(
        new.activity(activity_id)
    ), activity_id


def _keep_refund(
    previous: dict[str, Any], declaration: DgiiDeclaration | None, kind: str
) -> None:
    if not isinstance(declaration, PurchaseDeclaration):
        return
    if declaration.actual_refund or kind == "refund":
        original = (
            PurchaseDeclaration.model_validate(previous)
            if previous.get("form") == "606"
            else None
        )
        if not changes_recorded_refund(original, declaration):
            return
        raise ActionError("invalid_input", "recorded_correction_unsupported")


def _current(tx: ActionTransaction, activity_id: UUID, *, linked: bool) -> Posting:
    rows = tx.rows(
        "select r.id as record_id, r.current_revision as record_revision,"
        " g.current_revision as activity_revision, r.account_id, r.funding,"
        " coalesce(r.currency,a.currency) as currency, g.kind, abs(v.amount_minor) as amount_minor,"
        " v.as_of, v.as_of_zone, v.details"
        " from public.financial_activity_groups g"
        " join public.financial_activity_memberships m on m.activity_id=g.id"
        " and m.user_id=g.user_id and m.activity_revision=g.current_revision"
        " join public.financial_records r on r.id=m.record_id and r.user_id=m.record_owner_id"
        " and r.current_revision=m.record_revision"
        " join public.financial_record_revisions v on v.record_id=r.id and v.user_id=r.user_id"
        " and v.revision=r.current_revision"
        " left join public.financial_accounts a on a.id=r.account_id and a.user_id=r.user_id"
        " where g.id=%s and g.user_id=%s and g.reversed_at is null and m.role='single'"
        " and r.user_id=g.user_id and coalesce(r.owner_space_id,a.owner_space_id)=%s",
        (activity_id, tx.context.owner_id, tx.context.actor.space_id),
    )
    if len(rows) != 1:
        code = "business_document_linked" if linked else "business_record_not_found"
        raise ActionError("invalid_input", code)
    return Posting(**rows[0])


def _lock_account(tx: ActionTransaction, account_id: UUID) -> None:
    if not tx.rows(
        "select id from public.financial_accounts where user_id=%s and owner_space_id=%s"
        " and id=%s for update",
        (tx.context.owner_id, tx.context.actor.space_id, account_id),
    ):
        raise AccountNotFound()


def _corrected(old: Posting, before: BusinessFacts, after: BusinessFacts) -> Posting:
    kind = after.kind.value if before.kind.value != after.kind.value else old.kind
    if kind != "expense" and old.funding is not None:
        raise ActionError("invalid_input", "business_funding_unsupported")
    category = (
        None if kind != old.kind and kind == "income" else old.details.get("category_id")
    )

    note = old.details.get("note")
    if before.counterparty.value != after.counterparty.value:
        note = ((after.counterparty.value or "")[:200]).strip() or None
    currency = old.currency
    if before.currency.value != after.currency.value:
        currency = normalize_currency(after.currency.value)
    amount = old.amount_minor
    if before.amount.value != after.amount.value or currency != old.currency:
        amount = parse_minor_units(after.amount.value, currency)
    stamp, zone = old.as_of, old.as_of_zone
    if before.occurred_on.value != after.occurred_on.value:
        zone = DEFAULT_TIME_ZONE
        stamp = datetime.combine(after.occurred_on.value, time(0), tzinfo=ZoneInfo(zone))

    return replace(
        old,
        activity_revision=old.activity_revision + 1,
        currency=currency,
        kind=kind,
        amount_minor=amount,
        as_of=stamp,
        as_of_zone=zone,
        details={**old.details, "note": note, "category_id": category},
    )


def _write_account(
    tx: ActionTransaction,
    activity_id: UUID,
    old: Posting,
    new: Posting,
    now: datetime,
    accounts: FinancialAccountService,
) -> None:
    existing = accounts.list_accounts(
        user_id=tx.context.owner_id, scope=tx.context.scope, connection=tx.connection
    )
    target = next(
        account for account in existing if account.account.id == str(new.account_id)
    )
    requested_id = str(activity_id)
    request = MoneyRequest(
        kind=new.kind,
        account_id=str(new.account_id),
        amount=format_minor_units(new.amount_minor, new.currency),
        expected_revision=old.activity_revision,
        reason="document_review",
        occurred_at=new.as_of,
        time_zone=new.as_of_zone,
        note=new.details.get("note"),
        category_id=new.details.get("category_id"),
        source_id=new.details.get("source_id") if new.kind == "income" else None,
    )
    options = {"actor_id": str(tx.context.actor.actor_id), "document_correction": True}
    result = plan(existing, request, requested_id, now, **options)
    exact = {
        (link.observation_id, link.observation_revision): link.included
        for link in target.coverage
        if link.activity_id == str(old.record_id)
        and link.activity_revision == old.record_revision
    }
    held = {
        anchor.id: exact[(anchor.id, anchor.revision)]
        for anchor in observations(target.opening, target.checks)
        if (anchor.id, anchor.revision) in exact
    }
    questions = {
        item["observation_id"]
        for effect in result.preview["affected_accounts"]
        if effect["account_id"] == target.account.id
        for item in effect["observations"]
    }
    # When the corrected date is past an observation, its old answer no longer applies.
    if not questions <= held.keys():
        raise ActionError("invalid_input", "balance_coverage_required")
    if questions:
        answers = [
            MoneyCoverage(
                account_id=target.account.id, observation_id=key, included=held[key]
            )
            for key in sorted(questions)
        ]
        result = plan(
            existing,
            request.model_copy(update={"coverage": answers}),
            requested_id,
            now,
            **options,
        )

    persist(tx.connection, tx.context.owner_id, result)


def _write_no_account(
    tx: ActionTransaction,
    activity_id: UUID,
    old: Posting,
    new: Posting,
    now: datetime,
) -> None:
    owner, space = tx.context.owner_id, tx.context.actor.space_id
    if (old.kind, old.currency) != (new.kind, new.currency):
        new = replace(new, record_id=uuid4(), record_revision=1)
        tx.rows(
            "insert into public.financial_records"
            " (id,user_id,record_kind,created_at,owner_space_id,funding,currency)"
            " values (%s,%s,%s,%s,%s,%s,%s)",
            (new.record_id, owner, new.kind, now, space, new.funding, new.currency),
        )
    else:
        new = replace(new, record_revision=old.record_revision + 1)
    _write_record(tx, now, new)
    tx.rows(
        "insert into public.financial_activity_revisions (activity_id,revision,user_id) values (%s,%s,%s)",
        (activity_id, new.activity_revision, owner),
    )
    tx.rows(
        "insert into public.financial_activity_memberships"
        " (activity_id,user_id,activity_revision,record_id,record_revision,role,record_owner_id)"
        " values (%s,%s,%s,%s,%s,'single',%s)",
        (
            activity_id,
            owner,
            new.activity_revision,
            new.record_id,
            new.record_revision,
            owner,
        ),
    )
    tx.rows(
        "update public.financial_activity_groups set current_revision=%s,kind=%s where id=%s and user_id=%s",
        (new.activity_revision, new.kind, activity_id, owner),
    )


def _write_record(tx: ActionTransaction, now: datetime, posting: Posting) -> None:
    owner = tx.context.owner_id
    tx.rows(
        "insert into public.financial_record_revisions"
        " (record_id,user_id,revision,amount_minor,as_of,as_of_zone,recorded_by,recorded_at,details)"
        " values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            posting.record_id,
            owner,
            posting.record_revision,
            posting.amount_minor,
            posting.as_of,
            posting.as_of_zone,
            tx.context.actor.actor_id,
            now,
            Jsonb(posting.details),
        ),
    )
    tx.rows(
        "update public.financial_records set current_revision=%s where id=%s and user_id=%s",
        (posting.record_revision, posting.record_id, owner),
    )
