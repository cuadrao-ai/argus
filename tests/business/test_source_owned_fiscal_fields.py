"""A declaration field with no row in Datos fiscales always follows its
source. Montos owns Propina legal, so an override kept from before the row
left is never read, never saved again and never taken anew. A record saved
before Montos carried the tip has no source: its declaration keeps the tip."""

from __future__ import annotations

from uuid import UUID

import pytest
from argus.domain.business.amount_inheritance import (
    APPROVED,
    INHERITANCE,
    NO_SOURCES,
    SOURCE_OWNED,
    inherit_amounts,
    inheritance_overrides,
    inheritance_state,
    saved_declaration,
    source_owned,
    written_from,
)
from argus.domain.business.contracts.dgii import (
    PurchaseReview,
    SalePaymentSplit,
)
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    MontosReview,
)
from argus.domain.business.purchase_review import apply_payment_split, apply_purchase

from tests.business.test_document_type_direction import _event, _review

OLD, TIP, CORRECTED = "50.00", "80.00", "100.00"
FORMS = {"recibo": "606", "venta": "607"}


def _known(value: str) -> Known:
    return Known(value=value, origin="extracted", source_ids=(UUID(int=1),))


def _facts(document_type: str, tip: str | None = TIP) -> BusinessFacts:
    return BusinessFacts(
        kind=_known("income" if document_type == "venta" else "expense"),
        currency=_known("DOP"),
        amount=_known("1260.00"),
        legal_tip=_known(tip) if tip else BusinessFacts().legal_tip,
        fiscal=FiscalFacts(itbis=_known("180.00")),
    )


def _declared(document_type: str, **held: str):  # noqa: ANN202
    start = (
        apply_payment_split(None, SalePaymentSplit())
        if document_type == "venta"
        else apply_purchase(None, PurchaseReview(category="09"))
    )
    return start.model_copy(update=held)


def _overridden(document_type: str, tip: str | None = TIP):  # noqa: ANN202
    """A record whose tip was typed in Datos fiscales while the row was there."""

    event = _event(document_type, _facts(document_type, tip))
    event.resolution["business"].update(
        dgii=_declared(document_type, legal_tip=OLD).model_dump(mode="json"),
        fiscal_overrides=["legal_tip"],
    )
    return event


def test_every_source_owned_field_is_a_linked_one():
    assert SOURCE_OWNED <= INHERITANCE.keys()
    assert "legal_tip" in SOURCE_OWNED
    assert source_owned(_facts("recibo")) == SOURCE_OWNED
    assert source_owned(_facts("recibo", None)) == frozenset()


@pytest.mark.parametrize("document_type", FORMS)
def test_a_montos_tip_reaches_the_declaration_over_an_old_override(monkeypatch, document_type):
    saved = _review(
        monkeypatch,
        _overridden(document_type),
        None,
        montos=MontosReview(legal_tip={"state": "known", "value": "100"}),
    )
    assert saved["dgii"]["form"] == FORMS[document_type]
    assert saved["dgii"]["legal_tip"] == CORRECTED
    assert "legal_tip" not in saved["fiscal_overrides"]


@pytest.mark.parametrize("document_type", FORMS)
def test_any_save_drops_the_old_override(monkeypatch, document_type):
    saved = _review(
        monkeypatch,
        _overridden(document_type),
        None,
        {"occurred_on": {"state": "known", "value": "2026-09-05"}},
    )
    assert saved["dgii"]["legal_tip"] == TIP
    assert "legal_tip" not in saved["fiscal_overrides"]


@pytest.mark.parametrize("document_type", FORMS)
def test_an_open_review_shows_the_tip_of_montos_despite_the_old_override(document_type):
    facts = _facts(document_type)
    held = _declared(document_type, legal_tip=OLD)
    shown = written_from(facts, held, ("legal_tip",), None, NO_SOURCES)
    assert shown.legal_tip == TIP
    assert inheritance_state(facts, shown, ("legal_tip",))["legal_tip"].inherited


@pytest.mark.parametrize("document_type", FORMS)
def test_a_new_override_is_dropped(monkeypatch, document_type):
    facts = _facts(document_type)
    shown = inherit_amounts(facts, _declared(document_type), ())
    typed = shown.model_copy(update={"legal_tip": OLD})
    for overrides in (
        inheritance_overrides(facts, shown, typed, ()),
        inheritance_overrides(facts, shown, None, (), written=("legal_tip",)),
        inheritance_overrides(facts, typed, None, None),
    ):
        assert "legal_tip" not in overrides
    event = _event(document_type, facts)
    event.resolution["business"]["dgii"] = shown.model_dump(mode="json")
    saved = _review(
        monkeypatch, event, None, montos=MontosReview(override_inherited=("legal_tip",))
    )
    assert saved["dgii"]["legal_tip"] == TIP
    assert "legal_tip" not in saved["fiscal_overrides"]


@pytest.mark.parametrize("overrides", [("legal_tip",), None], ids=["recorded", "legacy"])
def test_an_approved_record_reports_its_saved_tip_until_it_is_saved_again(overrides):
    facts = _facts("recibo")
    held = _declared("recibo", legal_tip=OLD, itbis="180.00")
    assert saved_declaration(facts, held, overrides, None).legal_tip == OLD
    after = facts.model_copy(update={"legal_tip": _known("100")})
    kept = inheritance_overrides(facts, held, None, overrides, linked=APPROVED)
    assert "legal_tip" not in kept
    assert inherit_amounts(after, held, kept, APPROVED).legal_tip == CORRECTED


@pytest.mark.parametrize("document_type", FORMS)
def test_a_tip_montos_takes_back_leaves_the_declaration(monkeypatch, document_type):
    saved = _review(
        monkeypatch,
        _overridden(document_type),
        None,
        montos=MontosReview(legal_tip={"state": "unknown"}),
    )
    assert saved["dgii"]["legal_tip"] is None
    assert "legal_tip" not in saved["fiscal_overrides"]


@pytest.mark.parametrize("document_type", FORMS)
def test_a_record_saved_before_montos_keeps_the_tip_of_its_declaration(monkeypatch, document_type):
    facts = _facts(document_type, None)
    held = _declared(document_type, legal_tip=OLD)
    assert written_from(facts, held, ("legal_tip",), None, NO_SOURCES).legal_tip == OLD
    saved = _review(
        monkeypatch,
        _overridden(document_type, None),
        None,
        {"occurred_on": {"state": "known", "value": "2026-09-05"}},
    )
    assert saved["dgii"]["legal_tip"] == OLD
    assert "legal_tip" in saved["fiscal_overrides"]
