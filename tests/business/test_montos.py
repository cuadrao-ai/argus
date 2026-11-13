from decimal import Decimal
from uuid import UUID

import pytest
from argus.domain.business.amount_inheritance import (
    inherit_amounts,
    inheritance_overrides,
    inheritance_state,
)
from argus.domain.business.contracts.dgii import PurchaseReview, SalePaymentSplit
from argus.domain.business.contracts.facts import BusinessFacts, FiscalFacts, Known
from argus.domain.business.purchase_review import (
    apply_payment_split,
    apply_purchase,
    derived_amount,
    net_amount,
)
from argus.domain.business.receipt_amounts import read_amount_facts
from argus.domain.business.review_flags import review_flags
from argus.domain.ingestion.documents.models import ReceiptDetails


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
        ("1180.015", "180", "1000", None, "1000", "read", "0.015"),
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


def test_fuel_receipt_includes_isc_and_other_taxes_in_both_calculation_and_check():
    facts = receipt("1330", "180", "1000")
    declared = apply_purchase(None, PurchaseReview(category="09", selective_tax="100", other_taxes="50"))
    assert not review_flags(facts, declaration=declared)
    calculated = receipt("1330", "180")
    assert net_amount(calculated, declared).amount == "1000.00"
    assert not review_flags(calculated, declaration=declared)


@pytest.mark.parametrize(("service", "tip", "expected"), [("100", "25", "100"), (None, "100", "100"), ("0", "100", "0"), (None, None, None)])
def test_read_service_is_legal_tip_with_tip_only_as_fallback(service, tip, expected):
    parts = read_amount_facts(ReceiptDetails(subtotal="1,289.46", service=service, tip=tip), UUID(int=1))
    assert parts["legal_tip"].value == expected
    assert parts["net_amount"].value is None


def test_manual_split_breaks_both_links_and_restore_replaces_both_values():
    facts = receipt("1180", "180")
    initial = inherit_amounts(facts, apply_purchase(None, PurchaseReview(category="09")), ())
    assert initial.goods_amount == "1000.00"
    edited = apply_purchase(initial, PurchaseReview(goods_amount="600", services_amount="400"))
    overrides = inheritance_overrides(facts, initial, edited, (), written=("goods_amount", "services_amount"))
    assert not inheritance_state(facts, edited, overrides)["goods_amount"].inherited
    assert not inheritance_state(facts, edited, overrides)["services_amount"].inherited
    assert inherit_amounts(facts, edited, overrides).goods_amount == "600"
    restored = inheritance_overrides(facts, edited, None, overrides, restore=("goods_amount",))
    result = inherit_amounts(facts, edited, restored)
    assert result.goods_amount == "1000.00"
    assert result.services_amount is None
    assert inheritance_state(facts, result, restored)["goods_amount"].inherited


def test_explicit_edit_equal_to_inherited_amount_is_still_an_override():
    facts = receipt("1180", "180")
    initial = inherit_amounts(facts, apply_purchase(None, PurchaseReview(category="09")), ())
    overrides = inheritance_overrides(facts, initial, initial, (), written=("goods_amount",))
    assert not inheritance_state(facts, initial, overrides)["goods_amount"].inherited
    standalone = inheritance_overrides(facts, initial, None, (), written=("itbis",))
    assert not inheritance_state(facts, initial, standalone)["itbis"].inherited


@pytest.mark.parametrize(("printed", "expected"), [("00.50", "0.5"), ("000", "0"), ("9" * 41, None), ("bad", None)])
def test_read_subtotal_normalizes_or_retains_unknown(printed, expected):
    assert read_amount_facts(ReceiptDetails(subtotal=printed), UUID(int=1))["net_amount"].value == expected


def test_inheritance_never_rounds_a_value_outside_the_fiscal_contract():
    facts = receipt("999999999.999", "0", "999999999.999")
    declared = inherit_amounts(facts, apply_payment_split(None, SalePaymentSplit()), ())
    assert declared.billed_amount is None


def test_sale_inherits_net_and_fiscal_itbis_override_does_not_edit_main_itbis():
    facts = receipt("1280", "180", tip="100")
    initial = inherit_amounts(facts, apply_payment_split(None, SalePaymentSplit()), ())
    assert (initial.billed_amount, initial.itbis, initial.legal_tip) == ("1000.00", "180.00", "100.00")
    edited = initial.model_copy(update={"itbis": "150"})
    overridden = inherit_amounts(facts, edited, ("itbis",))
    assert overridden.itbis == "150"
    assert facts.fiscal.itbis.value == "180"
    assert inherit_amounts(facts, overridden, ()).itbis == "180.00"


def test_payment_date_inherits_only_when_paid_and_modified_document_never_does():
    from datetime import date

    facts = receipt("1180", "180").model_copy(update={"occurred_on": known(date(2026, 11, 1))})
    declaration = apply_purchase(None, PurchaseReview(category="09", modified_ncf="B0100000001"))
    assert inherit_amounts(facts, declaration, (), paid=False).paid_on is None
    assert inherit_amounts(facts, declaration, (), paid=True).paid_on == date(2026, 11, 1)
    assert "modified_ncf" not in inheritance_state(facts, declaration, (), paid=True)
