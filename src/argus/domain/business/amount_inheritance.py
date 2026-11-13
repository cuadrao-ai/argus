from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argus.domain.business.transactions import ActionTransaction

from argus.domain.business.contracts.dgii import DgiiDeclaration, PurchaseDeclaration
from argus.domain.business.contracts.facts import BusinessFacts, InheritedValue, Known
from argus.domain.business.purchase_review import AMOUNT_SIDES, derived_amount, net_amount

INHERITANCE = {
    "billed_amount": ("607", "net_amount"),
    "goods_amount": ("606", "net_amount"),
    "itbis": (None, "itbis"),
    "legal_tip": (None, "legal_tip"),
    "paid_on": ("606", "occurred_on"),
    "services_amount": ("606", "net_amount"),
}


def _text(value: object) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def _equal(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, date) or isinstance(right, date):
        return _text(left) == _text(right)
    return Decimal(str(left)) == Decimal(str(right))


def inherits(
    target: str, current: object, expected: object, overrides: tuple[str, ...] | None
) -> bool:
    """Whether a declaration field follows its source. A recorded override
    never does, even when empty: a person cleared it. A draft saved before
    overrides were recorded follows the source while empty or equal to it."""

    if overrides is not None:
        return target not in overrides
    return current is None or _equal(current, expected)


def inheritance_state(
    facts: BusinessFacts,
    declaration: DgiiDeclaration | None,
    overrides: tuple[str, ...] | None = None,
    *,
    paid: bool = False,
) -> dict[str, InheritedValue]:
    if declaration is None:
        return {}
    tax = facts.fiscal.itbis if facts.fiscal is not None else None
    sources = {
        "net_amount": net_amount(facts, declaration).amount,
        "itbis": tax.value if isinstance(tax, Known) else None,
        "legal_tip": facts.legal_tip.value if isinstance(facts.legal_tip, Known) else None,
        "occurred_on": facts.occurred_on.value if paid and isinstance(facts.occurred_on, Known) else None,
    }
    split = derived_amount(declaration, facts) if isinstance(declaration, PurchaseDeclaration) else None
    result = {}
    for target, (form, source) in INHERITANCE.items():
        if form is not None and declaration.form != form:
            continue
        expected = getattr(split, target) if target in AMOUNT_SIDES else sources[source]
        current = getattr(declaration, target)
        result[target] = InheritedValue(
            field=source, value=_text(expected), inherited=inherits(target, current, expected, overrides)
        )
    return result


def inherit_amounts(
    facts: BusinessFacts,
    declaration: DgiiDeclaration | None,
    overrides: tuple[str, ...] | None,
    *,
    paid: bool = False,
) -> DgiiDeclaration | None:
    if declaration is None:
        return None
    changes = {
        name: date.fromisoformat(state.value) if name == "paid_on" and state.value else state.value
        for name, state in inheritance_state(facts, declaration, overrides, paid=paid).items()
        if state.inherited
    }
    from argus.domain.business.contracts.dgii import MONEY_LIMIT, money_text

    for name, value in changes.items():
        if name != "paid_on" and value is not None:
            amount = Decimal(value)
            rounded = money_text(amount)
            changes[name] = rounded if 0 <= amount and Decimal(rounded) < MONEY_LIMIT else None
    return declaration.model_copy(update=changes)


def inheritance_overrides(
    facts: BusinessFacts,
    stored: DgiiDeclaration | None,
    declared: DgiiDeclaration | None,
    previous: tuple[str, ...] | None,
    *,
    written: tuple[str, ...] = (),
    restore: tuple[str, ...] = (),
    amount_derived: bool = False,
) -> tuple[str, ...]:
    if previous is None:
        overrides = {
            name for name, state in inheritance_state(facts, stored).items()
            if not state.inherited
        }
        if amount_derived:
            overrides.difference_update(AMOUNT_SIDES)
        elif isinstance(stored, PurchaseDeclaration) and any(getattr(stored, side) is not None for side in AMOUNT_SIDES):
            overrides.update(AMOUNT_SIDES)
    else:
        overrides = set(previous)
    overrides.update(written)
    if declared is not None:
        for name, (form, _) in INHERITANCE.items():
            if form is not None and declared.form != form:
                continue
            if name in written or (
                (stored is not None or getattr(declared, name) is not None)
                and (stored is None or not _equal(getattr(declared, name), getattr(stored, name)))
            ):
                overrides.add(name)
    if overrides.intersection(AMOUNT_SIDES):
        overrides.update(AMOUNT_SIDES)
    if set(restore).intersection(AMOUNT_SIDES):
        overrides.difference_update(AMOUNT_SIDES)
    overrides.difference_update(restore)
    return tuple(sorted(overrides))


def document_is_paid(status: str | None, bill_mark: str | None = None) -> bool:
    return status in {"pagado", "cobrado"} or bill_mark == "Factura pagada"


def draft_is_paid(
    tx: ActionTransaction, activity_id: str | None, bill_mark: str | None
) -> bool:
    rows = tx.rows(
        "select status from public.business_document_settlements"
        " where space_id=%s and owner_id=%s and activity_id=%s",
        (tx.context.actor.space_id, tx.context.owner_id, activity_id),
    ) if activity_id else []
    return document_is_paid(rows[0]["status"] if rows else None, bill_mark)
