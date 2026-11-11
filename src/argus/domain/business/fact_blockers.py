"""Fact-level draft blockers without the Business actions or ingestion graph."""

from __future__ import annotations

from decimal import Decimal

from argus.domain.business.contracts.dossier import AccountChoice, Blocker
from argus.domain.business.contracts.facts import (
    BusinessAccountFunding,
    BusinessFacts,
    Known,
)
from argus.domain.business.dgii_validation import credit_note
from argus.domain.recording.money_schemas import ELIGIBILITY


def fiscal_number(facts: BusinessFacts) -> str | None:
    if facts.fiscal is None:
        return None
    for fact in (facts.fiscal.ecf, facts.fiscal.ncf):
        if isinstance(fact, Known):
            return fact.value
    return None


def refund_shaped(facts: BusinessFacts) -> bool:
    """A refund, or a document whose fiscal number is a credit note."""

    kind = facts.kind.value if isinstance(facts.kind, Known) else None
    return kind == "refund" or credit_note(fiscal_number(facts))


def blockers(facts: BusinessFacts, accounts: tuple[AccountChoice, ...]) -> list[Blocker]:
    result = [
        Blocker(code="fact_required", field=name)
        for name in ("kind", "amount", "currency", "occurred_on")
        if not isinstance(getattr(facts, name), Known)
    ]
    if refund_shaped(facts) and not isinstance(facts.funding, Known):
        # A purchase or a sale records with no payment answer. A credit note
        # stays with the account it returns money to.
        result.append(Blocker(code="fact_required", field="funding"))
    if isinstance(facts.kind, Known) and facts.kind.value not in {
        "expense",
        "income",
        "refund",
    }:
        result.append(Blocker(code="activity_kind_unsupported", field="kind"))
    if (
        isinstance(facts.kind, Known)
        and facts.kind.value in {"income", "refund"}
        and isinstance(facts.funding, Known)
        and not isinstance(facts.funding.value, BusinessAccountFunding)
    ):
        result.append(Blocker(code="business_funding_unsupported", field="funding"))
    if (
        isinstance(facts.kind, Known)
        and facts.kind.value in {"income", "refund"}
        and isinstance(facts.funding, Known)
        and isinstance(facts.funding.value, BusinessAccountFunding)
    ):
        account = next(
            (item for item in accounts if item.id == facts.funding.value.account_id),
            None,
        )
        if account is None:
            result.append(Blocker(code="business_record_not_found", field="funding"))
        elif (
            isinstance(facts.currency, Known) and account.currency != facts.currency.value
        ):
            result.append(Blocker(code="import_currency_mismatch", field="funding"))
        elif account.type not in ELIGIBILITY[facts.kind.value]:
            result.append(Blocker(code="account_ineligible", field="funding"))
    if (
        isinstance(facts.kind, Known)
        and facts.kind.value == "income"
        and isinstance(facts.category_id, Known)
        and facts.category_id.value is not None
    ):
        result.append(Blocker(code="business_category_unsupported", field="category_id"))
    if isinstance(facts.amount, Known) and Decimal(facts.amount.value) <= 0:
        result.append(Blocker(code="amount_positive_required", field="amount"))
    if (
        isinstance(facts.business_share, Known)
        and facts.business_share.value.kind == "partial"
    ):
        # A personal receipt (none) is approved and left out of the totals;
        # a partial share has no recording rule yet.
        result.append(
            Blocker(code="business_allocation_unsupported", field="business_share")
        )
    return result
