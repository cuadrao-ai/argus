from __future__ import annotations

from decimal import Decimal

from argus.domain.business.contracts.dgii import (
    MONEY_LIMIT,
    SERVICE_EXPENSE_TYPES,
    DgiiDeclaration,
    PurchaseDeclaration,
    PurchaseReview,
    SalePaymentSplit,
    SalesDeclaration,
    amount_or_zero,
    money_text,
)
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.dgii_codes import PAYMENT_FORM_BY_ACCOUNT_TYPE
from argus.domain.business.fiscal_identity import identity_digits, normalized_ncf

AMOUNT_SIDES = ("services_amount", "goods_amount")


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


def takes_payment_split(
    facts: BusinessFacts, declaration: DgiiDeclaration | None
) -> bool:
    """Whether a 607 payment split belongs on this record: a sale with no 606
    declaration. The one rule behind the dossier's payment_split_editable and
    the review's write."""

    kind = facts.kind.value if isinstance(facts.kind, Known) else None
    return kind == "income" and not isinstance(declaration, PurchaseDeclaration)


def apply_payment_split(
    current: SalesDeclaration | None, split: SalePaymentSplit
) -> SalesDeclaration:
    data = (
        current.model_dump()
        if current is not None
        else {**dict.fromkeys(SalesDeclaration.model_fields), "form": "607"}
    )
    data.update({name: getattr(split, name) for name in split.model_fields_set})
    return SalesDeclaration.model_validate(data)


def apply_purchase(
    current: PurchaseDeclaration | None, review: PurchaseReview
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
    return PurchaseDeclaration.model_validate(data)


def amount_is_derived(
    declared: DgiiDeclaration | None,
    stored: DgiiDeclaration | None,
    derived: bool,
    review: PurchaseReview | None,
) -> bool:
    """Whether the services or goods amount is the server's after a write:
    ``declared`` is what the write sets, ``stored`` what the draft held, and
    ``derived`` whether the server worked that out. A confirmed Tipo de gasto
    with neither amount starts it. An amount a person types ends it, on
    ``review`` or as a change to the declaration, and a typed amount that
    equals the rule's stays typed."""

    current = declared or stored
    if not isinstance(current, PurchaseDeclaration):
        return False
    if review is not None:
        if any(getattr(review, side) is not None for side in AMOUNT_SIDES):
            return False
        if _confirmed_type(current) and _amounts(current) == (None, None):
            return True
    return (
        derived
        and isinstance(stored, PurchaseDeclaration)
        and _amounts(current) == _amounts(stored)
    )


def derived_amount(
    declaration: PurchaseDeclaration, amount: str | None, itbis: str | None
) -> PurchaseDeclaration:
    """The declaration with its services or goods amount worked out from the
    total: less ITBIS, selective tax, other taxes and tip, on the side the
    confirmed Tipo de gasto names. The one owner of that rule. Empty while the
    total or the type is unknown, or the taxes leave no amount a 606 can hold,
    so one edit of several in a row never refuses the write."""

    category = _confirmed_type(declaration)
    base = (
        None
        if amount is None or category is None
        else Decimal(amount)
        - amount_or_zero(itbis)
        - amount_or_zero(declaration.selective_tax)
        - amount_or_zero(declaration.other_taxes)
        - amount_or_zero(declaration.legal_tip)
    )
    value = money_text(base) if base is not None and 0 <= base < MONEY_LIMIT else None
    services = category in SERVICE_EXPENSE_TYPES
    return declaration.model_copy(
        update={
            "services_amount": value if services else None,
            "goods_amount": None if services else value,
        }
    )


def total_and_itbis(facts: BusinessFacts) -> tuple[str | None, str | None]:
    fiscal = facts.fiscal
    return (
        facts.amount.value if isinstance(facts.amount, Known) else None,
        fiscal.itbis.value
        if fiscal is not None and isinstance(fiscal.itbis, Known)
        else None,
    )


def _confirmed_type(declaration: PurchaseDeclaration) -> str | None:
    return None if declaration.category_suggested else declaration.category


def _amounts(declaration: PurchaseDeclaration) -> tuple[Decimal | None, ...]:
    return tuple(
        None if value is None else Decimal(value)
        for value in (getattr(declaration, side) for side in AMOUNT_SIDES)
    )


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
    facts: BusinessFacts, account_type: str | None
) -> PurchaseDeclaration | None:
    """The 606 declaration of a local expense receipt, from its stored facts.

    None when the 606 does not report it: no RNC, no fiscal number, or a
    consumer one (B02, E32). The expense type stays unknown for a person, so
    neither amount side is filled. ``account_type`` is the account a person
    stated paid it; with none, Forma de Pago stays blank for a person to set.
    """

    rnc = _fiscal(facts, "rnc")
    number = normalized_ncf(_fiscal(facts, "ecf") or _fiscal(facts, "ncf"))
    if rnc is None or number is None or number[1:3] in {"02", "32"}:
        return None
    review = PurchaseReview(payment_method=PAYMENT_FORM_BY_ACCOUNT_TYPE.get(account_type))
    digits = identity_digits(rnc)
    return apply_purchase(None, review).model_copy(
        update={"id_type": {9: "1", 11: "2"}.get(len(digits or ""))}
    )


def _fiscal(facts: BusinessFacts, name: str) -> str | None:
    fact = getattr(facts.fiscal, name, None)
    return fact.value if isinstance(fact, Known) and fact.value else None
