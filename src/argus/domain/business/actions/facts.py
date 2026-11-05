from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.facts import (
    BusinessAccountFunding,
    BusinessFactPatch,
    BusinessFacts,
    BusinessResolution,
    Known,
)
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.reconcile.model import ImportEvent


def facts_of(event: ImportEvent) -> BusinessFacts:
    value = event.resolution.get("business")
    if value is None:
        raise ActionError("invalid_input", "draft_not_prepared")
    return BusinessResolution.model_validate(value).facts


def patched_facts(
    before: BusinessFacts | None,
    patch: BusinessFactPatch,
    source_ids: tuple[UUID, ...],
    *,
    origin: str,
) -> BusinessFacts:
    facts = (
        before
        or BusinessFacts(currency=Known(value="DOP", origin="default", source_ids=()))
    ).model_dump(mode="json")
    for name, value in patch.model_dump(mode="json").items():
        if name == "purchase":
            continue
        facts[name] = {
            **value,
            "origin": origin,
            "verified": False,
            "source_ids": [str(source_id) for source_id in source_ids],
        }
    return BusinessFacts.model_validate(facts)


def validate_facts(tx: ActionTransaction, facts: BusinessFacts) -> None:
    if isinstance(facts.amount, Known) and Decimal(facts.amount.value) <= 0:
        raise ActionError("invalid_input", "amount_positive_required")
    funding = facts.funding
    if isinstance(funding, Known) and isinstance(funding.value, BusinessAccountFunding):
        account = tx.rows(
            "select currency from public.financial_accounts"
            " where id=%s and user_id=%s and owner_space_id=%s and not archived for share",
            (funding.value.account_id, tx.context.owner_id, tx.context.actor.space_id),
        )
        if not account:
            raise ActionError("not_found", "business_record_not_found")
        if (
            isinstance(facts.currency, Known)
            and account[0]["currency"] != facts.currency.value
        ):
            raise ActionError("invalid_input", "import_currency_mismatch")
