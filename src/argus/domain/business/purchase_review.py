from __future__ import annotations

from decimal import Decimal

from argus.domain.business.contracts.dgii import (
    SERVICE_EXPENSE_TYPES,
    PurchaseDeclaration,
    PurchaseReview,
    money_text,
)
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.fiscal_identity import identity_digits, normalized_ncf

# 606 type 09 is goods that form the cost of a sale. A saved declaration replaces it.
_GOODS_COST = "09"
# 606 payment form by what paid: 01 cash, 02 bank, 03 card. Other accounts stay unset.
_PAYMENT_FORM = {
    "owner_funds": "01",
    "cash": "01",
    "checking": "02",
    "savings": "02",
    "credit_card": "03",
}


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


def declaration_from_facts(
    facts: BusinessFacts, paid_from: str
) -> PurchaseDeclaration | None:
    """The 606 declaration of a local expense receipt, from its stored facts.

    None when the 606 does not report it: no RNC, no fiscal number, or a
    consumer (02) one. Goods take the total minus ITBIS, so the line adds back
    to the booked total. ``paid_from`` is ``owner_funds`` or the account type.
    """

    rnc = _fiscal(facts, "rnc")
    number = normalized_ncf(_fiscal(facts, "ecf") or _fiscal(facts, "ncf"))
    if rnc is None or number is None or number[1:3] == "02":
        return None
    review = PurchaseReview(
        category=_GOODS_COST, payment_method=_PAYMENT_FORM.get(paid_from)
    )
    gross = Decimal(facts.amount.value) if isinstance(facts.amount, Known) else None
    itbis = _fiscal(facts, "itbis")
    base = gross - Decimal(itbis) if gross is not None and itbis else gross
    digits = identity_digits(rnc)
    return apply_purchase(
        None, review, money_text(base) if base is not None and base > 0 else None
    ).model_copy(update={"id_type": {9: "1", 11: "2"}.get(len(digits or ""))})


def _fiscal(facts: BusinessFacts, name: str) -> str | None:
    fact = getattr(facts.fiscal, name, None)
    return fact.value if isinstance(fact, Known) and fact.value else None
