from __future__ import annotations

from decimal import Decimal

from argus.domain.business.contracts.dgii import (
    SERVICE_EXPENSE_TYPES,
    DgiiDeclaration,
    PurchaseDeclaration,
    PurchaseReview,
    SalesDeclaration,
    amount_or_zero,
    money_text,
)
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.dgii_codes import PAYMENT_FORM_BY_ACCOUNT_TYPE
from argus.domain.business.fiscal_identity import identity_digits, normalized_ncf


def takes_purchase_declaration(
    facts: BusinessFacts, declaration: DgiiDeclaration | None
) -> bool:
    """Whether a 606 declaration belongs on this record. A sale's 607 and an
    income with no declaration take none. The one rule behind the dossier's
    declaration_editable and the review's 606 write."""

    if isinstance(declaration, SalesDeclaration):
        return False
    kind = facts.kind.value if isinstance(facts.kind, Known) else None
    return declaration is not None or kind != "income"


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
    data.update({name: getattr(review, name) for name in written})
    if "category" in written and "category_suggested" not in written:
        data["category_suggested"] = False
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


def changes_recorded_refund(
    current: PurchaseDeclaration | None, declared: PurchaseDeclaration
) -> bool:
    """Whether a 606 write moves what an approval recorded in the money: the
    actual refund and the purchase it is linked to. Neither is a 606 column."""

    before = current or PurchaseReview()
    return (before.actual_refund, before.purchase_activity_id) != (
        declared.actual_refund,
        declared.purchase_activity_id,
    )


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
    review = PurchaseReview(payment_method=PAYMENT_FORM_BY_ACCOUNT_TYPE.get(paid_from))
    digits = identity_digits(rnc)
    return apply_purchase(None, review, None).model_copy(
        update={"id_type": {9: "1", 11: "2"}.get(len(digits or ""))}
    )


def _fiscal(facts: BusinessFacts, name: str) -> str | None:
    fact = getattr(facts.fiscal, name, None)
    return fact.value if isinstance(fact, Known) and fact.value else None
