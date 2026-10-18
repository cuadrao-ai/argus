from __future__ import annotations

from decimal import Decimal

from argus.domain.business.contracts.dgii import (
    SERVICE_EXPENSE_TYPES,
    PurchaseDeclaration,
    PurchaseReview,
    amount_or_zero,
    money_text,
)


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
