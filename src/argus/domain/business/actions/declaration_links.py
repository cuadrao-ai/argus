"""How a write turns into the declaration a draft saves and the fields it
holds apart from their source. A save and the amounts preview both run it."""

from collections.abc import Callable
from typing import NamedTuple

from argus.domain.business.actions.fiscal import validate_changed_dates
from argus.domain.business.amount_inheritance import (
    LinkedSources,
    inherit_amounts,
    inheritance_overrides,
    written_from,
)
from argus.domain.business.contracts.dgii import DgiiDeclaration, SalePaymentSplit
from argus.domain.business.contracts.facts import BusinessFacts
from argus.domain.business.purchase_review import apply_payment_split, kept_sources


class Written(NamedTuple):
    stored: DgiiDeclaration | None
    declared: DgiiDeclaration | None
    overrides: tuple[str, ...]


def written_declaration(
    facts: BusinessFacts,
    stored: DgiiDeclaration | None,
    declare: Callable[[DgiiDeclaration | None], DgiiDeclaration | None],
    previous: tuple[str, ...] | None,
    bill_mark: str | None,
    linked: LinkedSources,
    *,
    retyped: bool = False,
    written: tuple[str, ...] = (),
    restore: tuple[str, ...] = (),
    amount_derived: bool,
    unsaved: bool,
) -> Written:
    """A person's write over ``stored``: the declaration it starts from,
    ``declare``'s answer to it and the fields it holds apart."""

    stored = written_from(facts, stored, previous, bill_mark, linked)
    declared = declare(stored)
    validate_changed_dates(stored, declared)
    declared = kept_sources(stored, declared)
    return Written(stored, declared, inheritance_overrides(
        facts, stored, declared,
        None if retyped else previous,
        written=written,
        restore=restore,
        amount_derived=amount_derived,
        linked=linked,
        unsaved=unsaved,
    ))


def saved_declaration_links(
    before: BusinessFacts,
    after: BusinessFacts,
    declaration: DgiiDeclaration | None,
    previous: tuple[str, ...] | None,
    bill_mark: str | None,
    overrides: tuple[str, ...] | None,
    sources: Callable[[BusinessFacts, DgiiDeclaration | None], LinkedSources],
    *,
    written: bool,
    venta: bool,
    amount_derived: bool,
) -> tuple[DgiiDeclaration | None, tuple[str, ...]]:
    """The declaration a revision saves and its overrides. One a person did
    not just write (``written``) is the draft's own, as the draft showed it."""

    if declaration is None and venta:
        declaration = apply_payment_split(None, SalePaymentSplit())
    linked = sources(after, declaration)
    if not written:
        declaration = written_from(before, declaration, previous, bill_mark, linked)
    if overrides is None:
        overrides = inheritance_overrides(
            before, declaration, None, previous,
            amount_derived=amount_derived, linked=linked,
        )
    return inherit_amounts(after, declaration, overrides, linked), overrides
