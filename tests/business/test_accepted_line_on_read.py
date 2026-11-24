"""An approved purchase with no saved 606 line reports the one its facts
state: the line an open review builds, following its sources. A saved line
stays as saved, but for a Tipo Id nobody could ever fill by hand."""

from dataclasses import replace

import pytest
from argus.domain.business.amount_inheritance import (
    APPROVED,
    inheritance_overrides,
    inheritance_state,
    saved_declaration,
    written_from,
)
from argus.domain.business.contracts.dgii import PurchaseReview
from argus.domain.business.purchase_review import apply_purchase, declaration_from_facts

from tests.business.test_fiscal_links import CEDULA, DAY, RNC, read

FACTS = read()


def unsaved(account: str | None = None, facts=FACTS):  # noqa: ANN001, ANN201
    """What the dossier and the export read beyond an approved record with no
    saved line: the declaration its facts state."""

    return replace(APPROVED, built=declaration_from_facts(facts, account))


@pytest.mark.parametrize(("rnc", "id_type"), [(RNC, "1"), (CEDULA, "2")], ids=["rnc", "cedula"])
def test_an_approved_purchase_with_no_saved_line_reports_the_built_one(rnc, id_type):
    facts = read(rnc=rnc)
    linked = unsaved(facts=facts)

    line = saved_declaration(facts, None, None, None, linked.built)

    assert (line.form, line.id_type, line.itbis) == ("606", id_type, "180.00")
    # Answers nobody gave stay empty, and with them the split that needs one.
    assert (line.category, line.payment_method, line.paid_on) == (None, None, None)
    assert (line.goods_amount, line.services_amount) == (None, None)
    assert written_from(facts, None, None, None, linked) == line
    links = inheritance_state(facts, line, None, linked)
    assert {"id_type", "itbis", "goods_amount", "services_amount", "paid_on"} <= set(links)
    assert all(link.inherited for link in links.values())
    assert (links["id_type"].field, links["id_type"].value) == ("rnc", id_type)


@pytest.mark.parametrize(
    ("account", "form", "paid_on"),
    [("cash", "01", DAY), ("credit_card", "03", DAY), (None, None, None)],
    ids=["cash", "card", "no account"],
)
def test_the_built_line_takes_forma_de_pago_from_the_account_that_paid(account, form, paid_on):
    line = saved_declaration(FACTS, None, None, None, unsaved(account).built)

    assert (line.payment_method, line.paid_on) == (form, paid_on)


def test_an_approved_record_the_606_does_not_take_reports_no_line():
    consumer = read(ncf="B0200000001")
    linked = unsaved(facts=consumer)

    assert linked.built is None
    assert saved_declaration(consumer, None, None, None, linked.built) is None
    assert written_from(consumer, None, None, None, linked) is None
    assert written_from(FACTS, None, None, None, APPROVED) is None


def test_a_first_fiscal_edit_starts_from_the_built_line():
    linked = unsaved("cash")
    shown = written_from(FACTS, None, None, None, linked)

    declared = apply_purchase(shown, PurchaseReview(category="02"))
    overrides = inheritance_overrides(
        FACTS, shown, declared, None, written=("category",), amount_derived=True,
        linked=linked, unsaved=True,
    )

    assert declared.model_dump(exclude={"category"}) == shown.model_dump(exclude={"category"})
    assert (declared.id_type, declared.payment_method, declared.paid_on) == ("1", "01", DAY)
    assert set(overrides).isdisjoint({"id_type", "itbis", "paid_on", "goods_amount", "services_amount"})


@pytest.mark.parametrize("overrides", [None, ()], ids=["before overrides", "overrides recorded"])
def test_a_saved_line_with_no_tipo_id_takes_the_one_its_rnc_states(overrides):
    saved = apply_purchase(None, PurchaseReview(category="09", payment_method="04"))
    assert saved.id_type is None

    line = saved_declaration(FACTS, saved, overrides, None)

    assert line.id_type == "1"
    assert (line.category, line.payment_method) == ("09", "04")
    assert written_from(FACTS, saved, overrides, None, APPROVED) == line


def test_a_saved_tipo_id_is_never_replaced():
    saved = apply_purchase(None, PurchaseReview(category="09")).model_copy(update={"id_type": "2"})

    assert saved_declaration(FACTS, saved, (), None) is saved
