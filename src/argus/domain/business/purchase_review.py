from __future__ import annotations

from decimal import Decimal

from argus.domain.business.contracts.dgii import (
    SERVICE_EXPENSE_TYPES,
    PurchaseDeclaration,
    PurchaseReview,
    money_text,
)
from argus.domain.business.contracts.facts import (
    BusinessAccountFunding,
    BusinessFacts,
    Known,
    OwnerFunding,
)
from argus.domain.business.fiscal_identity import identity_digits, normalized_ncf

# 606 type 09 is goods that form the cost of a sale. A saved declaration replaces it.
_GOODS_COST = "09"
# 606 payment form by who paid: 01 cash for the owner, 02 bank for a Business account.
_PAYMENT_FORM = {OwnerFunding: "01", BusinessAccountFunding: "02"}


def apply_purchase(
    current: PurchaseDeclaration | None,
    review: PurchaseReview,
    amount: str | None,
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
        data[side] = money_text(Decimal(amount))
    return PurchaseDeclaration.model_validate(data)


def declaration_from_facts(facts: BusinessFacts) -> PurchaseDeclaration:
    """The 606 declaration of an approved expense whose draft holds none.

    Goods take the total minus ITBIS, so the line adds back to the booked
    total. Payment follows who paid.
    """

    rnc = _fiscal(facts, "rnc")
    number = normalized_ncf(_fiscal(facts, "ecf") or _fiscal(facts, "ncf"))
    funding = facts.funding.value if isinstance(facts.funding, Known) else None
    review = PurchaseReview(
        category=_GOODS_COST
        if rnc is not None and number is not None and number[1:3] != "02"
        else None,
        payment_method=_PAYMENT_FORM.get(type(funding)),
    )
    gross = Decimal(facts.amount.value) if isinstance(facts.amount, Known) else None
    itbis = _fiscal(facts, "itbis")
    base = (
        gross - Decimal(itbis)
        if gross is not None and itbis is not None and gross > Decimal(itbis)
        else gross
    )
    digits = identity_digits(rnc)
    return apply_purchase(
        None, review, money_text(base) if base is not None else None
    ).model_copy(update={"id_type": {9: "1", 11: "2"}.get(len(digits or ""))})


def _fiscal(facts: BusinessFacts, name: str) -> str | None:
    fact = getattr(facts.fiscal, name, None)
    return fact.value if isinstance(fact, Known) and fact.value else None
