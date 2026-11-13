from decimal import Decimal
from uuid import UUID

import pytest
from argus.domain.business.contracts.dgii import PurchaseReview
from argus.domain.business.contracts.facts import BusinessFacts, FiscalFacts, Known
from argus.domain.business.purchase_review import (
    apply_purchase,
    derived_amount,
    net_amount,
)
from argus.domain.business.review_flags import review_flags


def known(value: str, origin: str = "extracted") -> Known:
    return Known(value=value, origin=origin, source_ids=(UUID(int=1),))


def receipt(total: str, tax: str, subtotal: str | None = None, tip: str | None = None) -> BusinessFacts:
    values = {"amount": known(total), "fiscal": FiscalFacts(itbis=known(tax))}
    if subtotal is not None:
        values["net_amount"] = known(subtotal)
    if tip is not None:
        values["legal_tip"] = known(tip)
    return BusinessFacts(**values)


def test_small_purchase_derives_net_once_and_places_it_in_goods():
    facts = receipt("184.90", "14.48")
    net = net_amount(facts)
    assert (net.amount, net.source) == ("170.42", "calculated")
    declared = derived_amount(apply_purchase(None, PurchaseReview(category="09")), facts)
    assert declared.goods_amount == "170.42"
    assert declared.services_amount is None
    assert facts.amount.value == "184.9"


@pytest.mark.parametrize(
    ("total", "tax", "subtotal", "tip", "expected", "source", "difference"),
    [
        ("1442.00", "152.54", "1289.46", None, "1289.46", "read", None),
        ("1280", "180", "1000", "100", "1000", "read", None),
        ("1280", "180", None, "100", "1000.00", "calculated", None),
        ("1200", "180", "1000", None, "1000", "read", "20.00"),
        ("1180.01", "180", "1000", None, "1000", "read", None),
        ("1179.98", "180", "1000", None, "1000", "read", "-0.02"),
    ],
)
def test_receipt_amounts(total, tax, subtotal, tip, expected, source, difference):
    facts = receipt(total, tax, subtotal, tip)
    result = net_amount(facts)
    assert Decimal(result.amount) == Decimal(expected)
    assert result.source == source
    mismatch = next((flag for flag in review_flags(facts) if flag.code == "amounts_mismatch"), None)
    assert (mismatch.difference if mismatch else None) == difference


def test_tax_edit_recalculates_only_a_calculated_net():
    facts = receipt("184.90", "14.48")
    changed = facts.model_copy(update={"fiscal": FiscalFacts(itbis=known("18", "member_set"))})
    assert net_amount(changed).amount == "166.90"
    edited = changed.model_copy(update={"net_amount": known("170.42", "member_set")})
    assert (net_amount(edited).amount, net_amount(edited).source) == ("170.42", "edited")
