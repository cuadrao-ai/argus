from __future__ import annotations

from decimal import Decimal

from argus.domain.business.contracts.dgii import (
    SERVICE_EXPENSE_TYPES,
    PurchaseDeclaration,
    PurchaseReview,
    amount_or_zero,
    money_text,
)
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.fiscal_identity import identity_digits, normalized_ncf

# 606 payment form by the business account that paid: 01 cash, 02 bank, 03 card.
# Owner funds and other accounts leave it unknown for a person.
_PAYMENT_FORM = {
    "cash": "01",
    "checking": "02",
    "savings": "02",
    "credit_card": "03",
}


def apply_purchase(
    current: PurchaseDeclaration | None,
    review: PurchaseReview,
    amount: str | None,
    itbis: str | None = None,
) -> PurchaseDeclaration:
    if current is None:
        data = {name: None for name in PurchaseDeclaration.model_fields}
        data.update(form="606", actual_refund=False, category_suggested=False)
    else:
        data = current.model_dump()
    written = review.model_fields_set
    for name in (
        "category",
        "payment_method",
        "paid_on",
        "services_amount",
        "goods_amount",
        "itbis_withheld",
        "income_withholding_type",
        "income_withheld",
    ):
        if name in written:
            data[name] = getattr(review, name)
    if "category" in written and "category_suggested" not in written:
        data["category_suggested"] = False
    if "category_suggested" in written:
        data["category_suggested"] = review.category_suggested
    category = data.get("category")
    if (
        category
        and not data.get("category_suggested")
        and data.get("services_amount") is None
        and data.get("goods_amount") is None
        and amount is not None
    ):
        side = "services_amount" if category in SERVICE_EXPENSE_TYPES else "goods_amount"
        data[side] = money_text(
            Decimal(amount)
            - amount_or_zero(itbis)
            - amount_or_zero(data.get("selective_tax"))
            - amount_or_zero(data.get("other_taxes"))
            - amount_or_zero(data.get("legal_tip"))
        )
    return PurchaseDeclaration.model_validate(data)


def declaration_from_facts(
    facts: BusinessFacts, paid_from: str
) -> PurchaseDeclaration | None:
    """The 606 declaration of a local expense receipt, from its stored facts.

    None when the 606 does not report it: no RNC, no fiscal number, or a
    consumer one (B02, E32). The expense type stays unknown for a person, so
    neither amount side is filled. ``paid_from`` is ``owner_funds`` or the
    account type.
    """

    rnc = _fiscal(facts, "rnc")
    number = normalized_ncf(_fiscal(facts, "ecf") or _fiscal(facts, "ncf"))
    if rnc is None or number is None or number[1:3] in {"02", "32"}:
        return None
    review = PurchaseReview(payment_method=_PAYMENT_FORM.get(paid_from))
    digits = identity_digits(rnc)
    return apply_purchase(None, review, None).model_copy(
        update={"id_type": {9: "1", 11: "2"}.get(len(digits or ""))}
    )


def _fiscal(facts: BusinessFacts, name: str) -> str | None:
    fact = getattr(facts.fiscal, name, None)
    return fact.value if isinstance(fact, Known) and fact.value else None
