from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from argus.domain.business.authority import ActionError
from argus.domain.business.bandeja_group import year_to_check
from argus.domain.business.contracts.facts import (
    BusinessAccountFunding,
    BusinessFactPatch,
    BusinessFacts,
    BusinessResolution,
    Known,
    MontosReview,
    is_personal,
    read_fills,
)
from argus.domain.business.purchase_review import stated_tip
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
    upload_year: int | None = None,
) -> BusinessFacts:
    held = before or BusinessFacts(currency=Known(value="DOP", origin="default", source_ids=()))
    facts = held.model_dump(mode="json")
    for name, value in patch.model_dump(mode="json").items():
        if name == "purchase":
            continue
        stated = _stated(value, origin, source_ids)
        if origin == "member_set" and _repeats(held, name, stated, upload_year):
            continue
        facts[name] = stated
    return BusinessFacts.model_validate(facts)


def _stated(value: dict, origin: str, source_ids: tuple[UUID, ...]) -> dict:
    return {**value, "origin": origin, "verified": False, "source_ids": [str(source_id) for source_id in source_ids]}


def _repeats(held: BusinessFacts, name: str, stated: dict, upload_year: int | None) -> bool:
    """Whether a person's statement only repeats the held fact: its value, and
    the same answer from each rule that decides by who gave it: Personal, the
    year check, the stated tip and what a later read may fill."""

    fact = getattr(held, name).model_dump(mode="json")
    if (fact["state"], fact["value"]) != (stated["state"], stated["value"]):
        return False
    after = BusinessFacts.model_validate(held.model_dump(mode="json") | {name: stated})
    return (
        read_fills(fact) == read_fills(stated)
        and is_personal(after) == is_personal(held)
        and year_to_check(after, upload_year) == year_to_check(held, upload_year)
        and stated_tip(after) == stated_tip(held)
    )


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


def reviewed_amount_facts(before: BusinessFacts, review: MontosReview, source_ids: tuple[UUID, ...], *, origin: str) -> BusinessFacts:
    changes = {}
    for name in ("net_amount", "legal_tip"):
        value = getattr(review, name)
        if value is None:
            continue
        stated = _stated(value.model_dump(mode="json"), origin, source_ids)
        if not _repeats(before, name, stated, None):
            changes[name] = stated
    return BusinessFacts.model_validate(before.model_dump(mode="json") | changes)
