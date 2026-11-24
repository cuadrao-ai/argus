from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from argus.domain.business.accepted_dates import reader_date_reason
from argus.domain.business.contracts.dgii import (
    DeclarationSuggestions,
    DgiiDeclaration,
    PurchaseDeclaration,
)
from argus.domain.business.contracts.facts import BusinessFacts, InheritedValue, Known
from argus.domain.business.fiscal_identity import credit_note
from argus.domain.business.purchase_review import (
    AMOUNT_SIDES,
    derived_amount,
    id_type_of,
    net_amount,
    stated_tip,
    take_suggestions,
)

INHERITANCE = {
    "billed_amount": ("607", "net_amount"),
    "goods_amount": ("606", "net_amount"),
    "id_type": ("606", "rnc"),
    "itbis": (None, "itbis"),
    "legal_tip": (None, "legal_tip"),
    "modified_ncf": ("606", "original_ncf"),
    "paid_on": ("606", "occurred_on"),
    "services_amount": ("606", "net_amount"),
}
#: The linked fields a person never holds apart: nothing in Datos fiscales
#: could restore one. Montos owns Propina legal, and the supplier's RNC in
#: General owns a purchase's Tipo Id.
SOURCE_OWNED = frozenset({"id_type", "legal_tip"})
_MONEY_SOURCES = frozenset({"net_amount", "itbis", "legal_tip"})
#: Forma de pago codes that pay at the purchase: Fecha pago is the receipt's date.
PAID_AT_PURCHASE = frozenset({"01", "02", "03", "07"})
PAID_BILL_MARK = "Factura pagada"


@dataclass(frozen=True)
class LinkedSources:
    """What a link reads beyond the draft's own facts: the answers the server
    suggests while a person has given none, and the NCF of the purchase a
    credit note is tied to (None for any other record)."""

    suggestions: DeclarationSuggestions = DeclarationSuggestions()
    original_ncf: str | None = None
    #: Only the amounts follow the receipt: a record that is not an open draft.
    amounts_only: bool = False
    corrected_sources: frozenset[str] = frozenset()
    #: The 606 declaration the facts of an expense state on their own, its
    #: Forma de pago the one of the account a person said paid it: for an open
    #: expense, and for an approved one with no saved declaration.
    built: PurchaseDeclaration | None = None


NO_SOURCES = LinkedSources()
#: An approved record. Tipo Id, Fecha pago and NCF modificado follow their
#: source only while an open draft is reviewed; approval saves what was shown.
APPROVED = LinkedSources(amounts_only=True)


def links_of(state: str) -> LinkedSources:
    """The links of a draft in ``state`` before any review source is read.
    An approval writes what its open review showed while the draft is accepting."""

    return NO_SOURCES if state in ("open", "accepting") else APPROVED


def _number(facts: BusinessFacts | None) -> str | None:
    fiscal = facts.fiscal if facts is not None else None
    return (fiscal.ecf.value or fiscal.ncf.value) if fiscal is not None else None


def original_ncf(
    facts: BusinessFacts,
    declaration: DgiiDeclaration | None,
    approved: Callable[[str], BusinessFacts | None],
) -> str | None:
    """The NCF or e-NCF of the purchase a credit note is tied to: its NCF
    modificado. ``approved`` reads that purchase's approved facts. None for
    any other record, a debit note included."""

    if (
        not isinstance(declaration, PurchaseDeclaration)
        or declaration.purchase_activity_id is None
        or not credit_note(_number(facts))
    ):
        return None
    return _number(approved(str(declaration.purchase_activity_id)))


def _text(value: object) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def _equal(target: str, left: object, right: object) -> bool:
    if left is None or right is None:
        return left is right
    if INHERITANCE[target][1] not in _MONEY_SOURCES:
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
    return current is None or _equal(target, current, expected)


def source_owned(facts: BusinessFacts, form: str | None) -> frozenset[str]:
    """The fields of this record, on ``form``, that a person never holds
    apart from their source. Propina legal is one once Montos states it; a
    record saved before Montos carried the tip keeps the one its declaration
    holds. Tipo Id is one on every purchase."""

    owned = {name for name in SOURCE_OWNED if INHERITANCE[name][0] in (None, form)}
    if stated_tip(facts) is None:
        owned.discard("legal_tip")
    return frozenset(owned)


def held_apart(
    facts: BusinessFacts, form: str | None, overrides: tuple[str, ...] | None
) -> tuple[str, ...] | None:
    """``overrides`` without the source-owned fields an older save left in it."""

    if overrides is None:
        return None
    return tuple(sorted(set(overrides) - source_owned(facts, form)))


def inheritance_state(
    facts: BusinessFacts,
    declaration: DgiiDeclaration | None,
    overrides: tuple[str, ...] | None = None,
    linked: LinkedSources = NO_SOURCES,
) -> dict[str, InheritedValue]:
    if declaration is None:
        return {}
    tax = facts.fiscal.itbis if facts.fiscal is not None else None
    purchase = isinstance(declaration, PurchaseDeclaration)
    # A suggested answer counts as given, so the links show what approving saves.
    answered = take_suggestions(declaration, linked.suggestions) if purchase else None
    # A date outside the accepted range is evidence to correct, never a payment date.
    day = (
        facts.occurred_on.value
        if answered is not None
        and answered.payment_method in PAID_AT_PURCHASE
        and isinstance(facts.occurred_on, Known)
        else None
    )
    sources = {
        "net_amount": net_amount(facts, declaration).amount,
        "itbis": tax.value if isinstance(tax, Known) else None,
        "legal_tip": facts.legal_tip.value if isinstance(facts.legal_tip, Known) else None,
        "occurred_on": day if reader_date_reason(day) is None else None,
        "rnc": id_type_of(facts),
        "original_ncf": linked.original_ncf,
    }
    split = derived_amount(answered, facts) if answered is not None else None
    overrides = held_apart(facts, declaration.form, overrides)
    result = {}
    for target, (form, source) in INHERITANCE.items():
        if form is not None and declaration.form != form:
            continue
        if source == "original_ncf" and linked.original_ncf is None:
            continue
        # An approved record with no saved line shows the built one, which
        # follows every source as an open draft's does.
        if (
            linked.amounts_only
            and linked.built is None
            and source not in _MONEY_SOURCES | linked.corrected_sources
        ):
            continue
        expected = getattr(split, target) if target in AMOUNT_SIDES else sources[source]
        current = getattr(declaration, target)
        result[target] = InheritedValue(
            field=source,
            value=_text(expected),
            inherited=inherits(target, current, expected, overrides),
            paired_with=tuple(side for side in AMOUNT_SIDES if side != target) if target in AMOUNT_SIDES else (),
        )
    return result


def inherit_amounts(
    facts: BusinessFacts,
    declaration: DgiiDeclaration | None,
    overrides: tuple[str, ...] | None,
    linked: LinkedSources = NO_SOURCES,
) -> DgiiDeclaration | None:
    if declaration is None:
        return None
    from argus.domain.business.contracts.dgii import MONEY_LIMIT, money_text

    changes: dict[str, object] = {}
    for name, state in inheritance_state(facts, declaration, overrides, linked).items():
        if not state.inherited:
            continue
        value: object = state.value
        if value is not None and state.field in _MONEY_SOURCES:
            amount = Decimal(state.value)
            rounded = money_text(amount)
            value = rounded if 0 <= amount and Decimal(rounded) < MONEY_LIMIT else None
        elif value is not None and state.field == "occurred_on":
            value = date.fromisoformat(state.value)
        changes[name] = value
    return declaration.model_copy(update=changes)


def saved_declaration(
    facts: BusinessFacts,
    declaration: DgiiDeclaration | None,
    overrides: tuple[str, ...] | None,
    bill_mark: str | None,
    built: PurchaseDeclaration | None = None,
) -> DgiiDeclaration | None:
    """The declaration an approved record reports: the saved one, as saved.
    One saved before overrides were recorded keeps the fill its export has
    always had: each blank amount from the approved facts, and the Fecha pago
    of a bill read as paid from its date.

    A purchase saved with no Tipo Id takes the one its RNC states: no person
    can give it. A record approved with none saved reports ``built``, the one
    its facts state, each linked field at the value it follows."""

    if declaration is None:
        return inherit_amounts(facts, built, overrides)
    if isinstance(declaration, PurchaseDeclaration) and declaration.id_type is None:
        kind = id_type_of(facts)
        if kind is not None:
            declaration = declaration.model_copy(update={"id_type": kind})
    if overrides is not None:
        return declaration
    filled = inherit_amounts(facts, declaration, None, APPROVED)
    day = facts.occurred_on.value if isinstance(facts.occurred_on, Known) else None
    if (
        isinstance(filled, PurchaseDeclaration)
        and filled.paid_on is None
        and bill_mark == PAID_BILL_MARK
        and day is not None
        and reader_date_reason(day) is None
    ):
        return filled.model_copy(update={"paid_on": day})
    return filled


def written_from(
    facts: BusinessFacts,
    declaration: DgiiDeclaration | None,
    overrides: tuple[str, ...] | None,
    bill_mark: str | None,
    linked: LinkedSources,
) -> DgiiDeclaration | None:
    """The declaration a record shows now: the one owner of it. The dossier
    shows it, a write starts from it and an approval saves it.

    An approved record shows the one it exports. An open draft shows, in
    this order: what a person answered or overrode, a blank they left
    included; a blank Forma de pago as the suggestion beside it, or with none
    as the account's; then each linked field at the value it follows, Fecha
    pago from that Forma de pago."""

    if linked.amounts_only:
        return saved_declaration(facts, declaration, overrides, bill_mark, linked.built)
    return inherit_amounts(facts, _answered(declaration, linked), overrides, linked)


def _answered(
    declaration: DgiiDeclaration | None, linked: LinkedSources
) -> DgiiDeclaration | None:
    """The answers an open review starts from: the person's, or with none
    saved for this purchase the ones its facts state. A suggested Forma de
    pago stays beside its blank answer, so the account's fills only without one."""

    built = linked.built
    if built is None:
        return declaration
    start = (
        declaration
        if isinstance(declaration, PurchaseDeclaration)
        else built.model_copy(update={"payment_method": None})
    )
    if start.payment_method is None and linked.suggestions.payment_method is None:
        return start.model_copy(update={"payment_method": built.payment_method})
    return start


def approved_from(
    facts: BusinessFacts,
    declaration: DgiiDeclaration | None,
    overrides: tuple[str, ...] | None,
    bill_mark: str | None,
    linked: LinkedSources,
) -> DgiiDeclaration | None:
    """The declaration an approval saves: the one its review shows, each
    suggestion shown beside a blank answer saved as that answer."""

    shown = written_from(facts, declaration, overrides, bill_mark, linked)
    if not isinstance(shown, PurchaseDeclaration):
        return shown
    return take_suggestions(shown, linked.suggestions)


def inheritance_overrides(
    facts: BusinessFacts,
    stored: DgiiDeclaration | None,
    declared: DgiiDeclaration | None,
    previous: tuple[str, ...] | None,
    *,
    written: tuple[str, ...] = (),
    restore: tuple[str, ...] = (),
    amount_derived: bool = False,
    linked: LinkedSources = NO_SOURCES,
    unsaved: bool = False,
) -> tuple[str, ...]:
    """The fields a person holds apart from their source after a write.
    ``unsaved`` is a first write over the declaration the server built: a
    field it leaves blank was not given, so it keeps following its source."""

    if previous is None:
        overrides = {
            name for name, state in inheritance_state(facts, stored, None, linked).items()
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
                not (unsaved and getattr(declared, name) is None)
                and (stored is not None or getattr(declared, name) is not None)
                and (stored is None or not _equal(name, getattr(declared, name), getattr(stored, name)))
            ):
                overrides.add(name)
    if overrides.intersection(AMOUNT_SIDES):
        overrides.update(AMOUNT_SIDES)
    if set(restore).intersection(AMOUNT_SIDES):
        overrides.difference_update(AMOUNT_SIDES)
    overrides.difference_update(restore)
    form = getattr(declared or stored, "form", None)
    return held_apart(facts, form, tuple(overrides))
