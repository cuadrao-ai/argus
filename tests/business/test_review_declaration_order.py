"""The 606 line an open expense shows, in the order its answers are taken:
the person's own, a blank they left included, then the suggestion, then the
account that paid, then each linked field. An approval saves that line."""

from dataclasses import dataclass, replace
from itertools import product

import pytest
from argus.domain.business.amount_inheritance import (
    APPROVED,
    PAID_AT_PURCHASE,
    LinkedSources,
    approved_from,
    inheritance_overrides,
    links_of,
    written_from,
)
from argus.domain.business.contracts.dgii import PurchaseDeclaration, PurchaseReview
from argus.domain.business.purchase_review import apply_purchase, declaration_from_facts

from tests.business.test_fiscal_links import DAY, read, suggested

FORMS = ("01", "02", "03", "04", "05", "06", "07")
#: Each suggestion differs from every account's Forma de pago, and pays later.
SUGGESTIONS = ({}, {"category": "09"}, {"payment_method": "04"}, {"category": "09", "payment_method": "04"})
ACCOUNTS = (None, "cash", "checking", "credit_card")
ACCOUNT_FORM = {None: None, "cash": "01", "checking": "02", "credit_card": "03"}
FACTS = read()


@dataclass(frozen=True)
class Shape:
    """An open expense: whether a declaration is ``saved`` with this Forma de
    pago, the ``overrides`` recorded on it (None before any were), the
    ``suggestions`` the server shows and the ``account`` type that paid. A
    field named in ``overrides`` is one the person left blank."""

    saved: bool
    payment: str | None
    overrides: tuple[str, ...] | None
    suggestions: tuple[tuple[str, str], ...]
    account: str | None

    @property
    def id(self) -> str:
        held = (
            f"saved forma {self.payment or 'blank'} overrides {self.overrides}"
            if self.saved
            else "nothing saved"
        )
        return f"{held}, suggested {dict(self.suggestions)}, paid from {self.account}"

    @property
    def stored(self) -> PurchaseDeclaration | None:
        if not self.saved:
            return None
        return apply_purchase(None, PurchaseReview(payment_method=self.payment))

    @property
    def linked(self) -> LinkedSources:
        return replace(
            suggested(**dict(self.suggestions)),
            built=declaration_from_facts(FACTS, self.account),
        )

    @property
    def resolved_form(self) -> str | None:
        """The Forma de pago the line stands on, by the order of its sources."""

        return (
            self.payment
            or dict(self.suggestions).get("payment_method")
            or ACCOUNT_FORM[self.account]
        )


SHAPES = [
    *(
        Shape(False, None, None, tuple(suggestions.items()), account)
        for suggestions, account in product(SUGGESTIONS, ACCOUNTS)
    ),
    *(
        Shape(True, payment, overrides, tuple(suggestions.items()), account)
        for payment, overrides, suggestions, account in product(
            (None, *FORMS), (None, (), ("id_type",), ("paid_on",)), SUGGESTIONS, ACCOUNTS
        )
    ),
]
shapes = pytest.mark.parametrize("shape", SHAPES, ids=[shape.id for shape in SHAPES])


def _shown(shape: Shape) -> PurchaseDeclaration:
    return written_from(FACTS, shape.stored, shape.overrides, None, shape.linked)


def _approved(shape: Shape) -> PurchaseDeclaration:
    return approved_from(FACTS, shape.stored, shape.overrides, None, shape.linked)


@shapes
def test_a_review_shows_each_answer_from_its_first_source(shape):
    shown = _shown(shape)
    offered = dict(shape.suggestions)
    cleared = shape.overrides or ()

    # A suggestion stays beside its blank answer; only the account fills one.
    assert shown.category is None
    assert shown.payment_method == (
        shape.payment or (None if "payment_method" in offered else ACCOUNT_FORM[shape.account])
    )
    # Tipo Id is source-owned: an override an older save kept is not read.
    assert shown.id_type == "1"
    assert shown.paid_on == (
        DAY if "paid_on" not in cleared and shape.resolved_form in PAID_AT_PURCHASE else None
    )
    assert shown.goods_amount == ("1000.00" if "category" in offered else None)
    assert shown.itbis == "180.00"


@shapes
def test_an_approval_saves_the_line_shown_with_each_suggestion_taken(shape):
    shown, approved = _shown(shape), _approved(shape)
    offered = dict(shape.suggestions)

    assert approved.model_dump(exclude={"suggestion_sources"}) == {
        **shown.model_dump(exclude={"suggestion_sources"}),
        "category": offered.get("category"),
        "payment_method": shape.resolved_form,
    }
    taken = {name for name in offered if getattr(shape.stored, name, None) is None}
    assert approved.suggestion_sources == dict.fromkeys(taken, "last_choice")


@shapes
@pytest.mark.parametrize("state", ["accepting", "accepted"])
def test_the_approved_line_is_the_one_read_back(shape, state):
    approved = _approved(shape)
    overrides = inheritance_overrides(FACTS, approved, None, shape.overrides)

    assert written_from(FACTS, approved, overrides, None, links_of(state)) == approved


def test_an_approved_record_takes_nothing_from_an_account_or_a_suggestion():
    stored = apply_purchase(None, PurchaseReview())
    linked = replace(APPROVED, built=declaration_from_facts(FACTS, "checking"))

    assert written_from(FACTS, stored, (), None, linked) is stored
