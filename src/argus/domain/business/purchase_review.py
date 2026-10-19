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
    """A 606 declaration from the stored facts when the person saved none.

    The amount that lands in goods is the total minus ITBIS, so the annex
    still adds back to the booked total. Payment follows who paid.
    """

    review = PurchaseReview(
        category=_GOODS_COST if _reportable_local_purchase(facts) else None,
        payment_method=_payment_method(facts),
    )
    declared = apply_purchase(None, review, _base_amount(facts))
    id_type = _id_type(facts)
    if id_type is None:
        return declared
    return declared.model_copy(update={"id_type": id_type})


def _payment_method(facts: BusinessFacts) -> str | None:
    if not isinstance(facts.funding, Known):
        return None
    funding = facts.funding.value
    if isinstance(funding, OwnerFunding):
        return "01"
    if isinstance(funding, BusinessAccountFunding):
        return "02"
    return None


def _id_type(facts: BusinessFacts) -> str | None:
    fiscal = facts.fiscal
    if fiscal is None or not isinstance(fiscal.rnc, Known) or not fiscal.rnc.value:
        return None
    digits = identity_digits(fiscal.rnc.value)
    if digits is None:
        return None
    if len(digits) == 9:
        return "1"
    if len(digits) == 11:
        return "2"
    return None


def _base_amount(facts: BusinessFacts) -> str | None:
    if not isinstance(facts.amount, Known) or not facts.amount.value:
        return None
    gross = Decimal(facts.amount.value)
    fiscal = facts.fiscal
    itbis = (
        Decimal(fiscal.itbis.value)
        if fiscal is not None
        and isinstance(fiscal.itbis, Known)
        and fiscal.itbis.value
        else None
    )
    if itbis is not None and gross > itbis:
        return money_text(gross - itbis)
    return money_text(gross)


def _reportable_local_purchase(facts: BusinessFacts) -> bool:
    fiscal = facts.fiscal
    if fiscal is None or not isinstance(fiscal.rnc, Known) or not fiscal.rnc.value:
        return False
    number = None
    if isinstance(fiscal.ecf, Known) and fiscal.ecf.value:
        number = normalized_ncf(fiscal.ecf.value)
    elif isinstance(fiscal.ncf, Known) and fiscal.ncf.value:
        number = normalized_ncf(fiscal.ncf.value)
    return number is not None and number[1:3] != "02"
