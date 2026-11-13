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
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    Known,
    NetAmount,
    is_sin_comprobante,
)
from argus.domain.business.dgii_codes import PAYMENT_FORM_BY_ACCOUNT_TYPE
from argus.domain.business.document_type import PURCHASE, SALE, DocumentType, direction
from argus.domain.business.fiscal_identity import identity_digits, normalized_ncf

AMOUNT_SIDES = ("services_amount", "goods_amount")


def takes_purchase_declaration(document_type: DocumentType, facts: BusinessFacts) -> bool:
    """Whether a 606 declaration belongs on this record: a purchase with a
    comprobante. The one rule behind the dossier's declaration_editable and
    the review's 606 write."""

    return direction(document_type) is PURCHASE and not is_sin_comprobante(facts)


def takes_payment_split(document_type: DocumentType) -> bool:
    """Whether a 607 payment split belongs on this record: a sale. The one
    rule behind the dossier's payment_split_editable and the review's write."""

    return direction(document_type) is SALE


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


def exact_amount_text(value: Decimal) -> str:
    return format(value, f".{max(2, -value.as_tuple().exponent)}f")


AMOUNT_PARTS = ("itbis", "legal_tip", "selective_tax", "other_taxes")


def amount_parts(
    facts: BusinessFacts | None = None,
    declaration: DgiiDeclaration | None = None,
    *,
    itbis: str | None = None,
    legal_tip: str | None = None,
) -> tuple[Decimal, ...]:
    if facts is not None:
        _, known_itbis = total_and_itbis(facts)
        itbis = known_itbis if known_itbis is not None else itbis
        if isinstance(facts.legal_tip, Known):
            legal_tip = facts.legal_tip.value
        elif facts.legal_tip.origin is not None:
            legal_tip = "0"
    values = {
        "itbis": itbis,
        "legal_tip": legal_tip if legal_tip is not None else getattr(declaration, "legal_tip", None),
        "selective_tax": getattr(declaration, "selective_tax", None),
        "other_taxes": getattr(declaration, "other_taxes", None),
    }
    return tuple(amount_or_zero(values[name]) for name in AMOUNT_PARTS)


def net_amount(
    facts: BusinessFacts | None = None,
    declaration: DgiiDeclaration | None = None,
    *,
    total: str | None = None,
    itbis: str | None = None,
    legal_tip: str | None = None,
) -> NetAmount:
    """The document's net amount. Raw components support legacy minor-unit callers."""
    if facts is not None:
        stated = facts.net_amount
        if isinstance(stated, Known):
            return NetAmount(
                amount=stated.value,
                source="read" if stated.origin in {"extracted", "qr_decoded"} else "edited",
            )
        known_total, known_itbis = total_and_itbis(facts)
        total = known_total if known_total is not None else total
        itbis = known_itbis if known_itbis is not None else itbis
    if total is None:
        return NetAmount(amount=None, source=None)
    value = Decimal(total) - sum(amount_parts(facts, declaration, itbis=itbis, legal_tip=legal_tip))
    return NetAmount(amount=exact_amount_text(value), source="calculated")


def derived_amount(
    declaration: PurchaseDeclaration,
    amount: BusinessFacts | str | None,
    itbis: str | None = None,
) -> PurchaseDeclaration:
    category = _confirmed_type(declaration)
    result = (
        net_amount(amount, declaration)
        if isinstance(amount, BusinessFacts)
        else net_amount(declaration=declaration, total=amount, itbis=itbis)
    )
    base = Decimal(result.amount) if result.amount is not None else None
    value = money_text(base) if category is not None and base is not None and 0 <= base < MONEY_LIMIT else None
    if value is not None and Decimal(value) >= MONEY_LIMIT:
        value = None
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
