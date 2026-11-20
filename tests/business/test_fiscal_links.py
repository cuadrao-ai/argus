"""Every 606 field that follows a source: what it shows on a fresh read, and
that a person's override holds until they restore it."""

from dataclasses import replace
from datetime import date
from uuid import UUID, uuid4

import pytest
from argus.domain.business.amount_inheritance import (
    INHERITANCE,
    NO_SOURCES,
    LinkedSources,
    approved_from,
    inherit_amounts,
    inheritance_overrides,
    inheritance_state,
    original_ncf,
    written_from,
)
from argus.domain.business.contracts.dgii import (
    DeclarationSuggestions,
    PurchaseDeclaration,
    PurchaseReview,
)
from argus.domain.business.contracts.facts import BusinessFacts, FiscalFacts, Known
from argus.domain.business.dgii_line import confirmed_declaration
from argus.domain.business.dgii_validation import FiscalRecord
from argus.domain.business.purchase_review import (
    apply_purchase,
    declaration_from_facts,
)
from faker import Faker

fake = Faker("es_MX")
Faker.seed(2307)
DAY = date(2026, 9, 5)
RNC = fake.numerify("1########")
CEDULA = fake.numerify("0##########")
NCF = "B01" + fake.numerify("########")
ORIGINAL = "E31" + fake.numerify("##########")


def known(value: object) -> Known:
    return Known(value=value, origin="extracted", source_ids=(UUID(int=1),))


def read(*, rnc: str = RNC, ncf: str = NCF, tip: str | None = None) -> BusinessFacts:
    """A receipt as the reader leaves it: 1,000 before ITBIS, 180 of ITBIS."""

    total = 1180 + int(tip or 0)
    return BusinessFacts(
        kind=known("expense"),
        amount=known(f"{total}.00"),
        occurred_on=known(DAY),
        legal_tip=known(tip) if tip else BusinessFacts().legal_tip,
        fiscal=FiscalFacts(rnc=known(rnc), ncf=known(ncf), itbis=known("180.00")),
    )


def suggested(**answers: str) -> LinkedSources:
    return LinkedSources(
        DeclarationSuggestions.model_validate(
            {field: {"value": value, "source": "last_choice"} for field, value in answers.items()}
        )
    )


def fresh(facts: BusinessFacts, linked: LinkedSources = NO_SOURCES) -> PurchaseDeclaration:
    """What a review of a read nobody touched shows."""

    return inherit_amounts(facts, declaration_from_facts(facts, None), None, linked)


@pytest.mark.parametrize(("rnc", "expected"), [(RNC, "1"), (CEDULA, "2")], ids=["rnc", "cedula"])
def test_tipo_id_follows_the_rnc_length(rnc, expected):
    facts = read(rnc=rnc)
    shown = fresh(facts)
    state = inheritance_state(facts, shown)["id_type"]
    assert shown.id_type == expected
    assert (state.field, state.value, state.inherited) == ("rnc", expected, True)


def test_tipo_id_moves_with_a_corrected_rnc():
    shown = fresh(read(rnc=RNC))
    assert inherit_amounts(read(rnc=CEDULA), shown, ()).id_type == "2"


def test_itbis_and_propina_follow_the_receipt():
    shown = fresh(read(tip="100"))
    assert (shown.itbis, shown.legal_tip) == ("180.00", "100.00")


@pytest.mark.parametrize(
    ("category", "side", "other"),
    [("09", "goods_amount", "services_amount"), ("02", "services_amount", "goods_amount")],
)
@pytest.mark.parametrize("confirmed", [True, False])
def test_montos_follow_the_tipo_de_gasto_suggested_or_confirmed(category, side, other, confirmed):
    facts = read()
    start = declaration_from_facts(facts, None)
    if confirmed:
        shown = inherit_amounts(facts, apply_purchase(start, PurchaseReview(category=category)), ())
    else:
        shown = fresh(facts, suggested(category=category))
    assert (getattr(shown, side), getattr(shown, other)) == ("1000.00", None)
    # A suggestion fills the amount, never the answer.
    assert shown.category == (category if confirmed else None)


def test_montos_move_sides_when_the_suggestion_changes():
    facts = read()
    shown = fresh(facts, suggested(category="09"))
    moved = inherit_amounts(facts, shown, (), suggested(category="02"))
    assert (moved.goods_amount, moved.services_amount) == (None, "1000.00")


def test_montos_stay_blank_with_no_tipo_de_gasto():
    shown = fresh(read())
    assert (shown.goods_amount, shown.services_amount) == (None, None)


@pytest.mark.parametrize(
    ("payment_method", "paid_on"),
    [("01", DAY), ("02", DAY), ("03", DAY), ("07", DAY), ("04", None), ("05", None), ("06", None), (None, None)],
)
@pytest.mark.parametrize("saved", [True, False])
def test_fecha_pago_follows_the_forma_de_pago_saved_or_suggested(payment_method, paid_on, saved):
    facts = read()
    start = declaration_from_facts(facts, None)
    if saved or payment_method is None:
        shown = inherit_amounts(
            facts, apply_purchase(start, PurchaseReview(payment_method=payment_method)), ()
        )
    else:
        shown = fresh(facts, suggested(payment_method=payment_method))
    assert shown.paid_on == paid_on


def test_a_saved_forma_de_pago_wins_over_a_suggested_one():
    facts = read()
    credit = apply_purchase(declaration_from_facts(facts, None), PurchaseReview(payment_method="04"))
    assert inherit_amounts(facts, credit, (), suggested(payment_method="01")).paid_on is None


def credit_note(**declared: object) -> tuple[BusinessFacts, PurchaseDeclaration]:
    facts = read(ncf="B04" + fake.numerify("########"))
    return facts, apply_purchase(declaration_from_facts(facts, None), PurchaseReview(**declared))


def test_ncf_modificado_is_the_linked_purchases_number():
    purchase = uuid4()
    facts, declaration = credit_note(actual_refund=True, purchase_activity_id=purchase)
    approved = {str(purchase): read(ncf=ORIGINAL)}
    linked = LinkedSources(original_ncf=original_ncf(facts, declaration, approved.get))
    shown = inherit_amounts(facts, declaration, (), linked)
    state = inheritance_state(facts, shown, (), linked)["modified_ncf"]
    assert shown.modified_ncf == ORIGINAL
    assert (state.field, state.value, state.inherited) == ("original_ncf", ORIGINAL, True)


@pytest.mark.parametrize(
    ("ncf", "tied"),
    [("B04" + fake.numerify("########"), False), ("B03" + fake.numerify("########"), True), (NCF, True)],
    ids=["credit note with no purchase", "debit note", "invoice"],
)
def test_ncf_modificado_is_the_persons_without_a_linked_credit_note(ncf, tied):
    purchase = uuid4()
    facts = read(ncf=ncf)
    declaration = apply_purchase(
        declaration_from_facts(facts, None),
        PurchaseReview(modified_ncf=NCF, purchase_activity_id=purchase if tied else None),
    )
    linked = LinkedSources(
        original_ncf=original_ncf(facts, declaration, {str(purchase): read(ncf=ORIGINAL)}.get)
    )
    assert "modified_ncf" not in inheritance_state(facts, declaration, (), linked)
    assert inherit_amounts(facts, declaration, (), linked).modified_ncf == NCF


def _typed(name: str) -> object:
    return {"id_type": "2", "paid_on": date(2026, 9, 20), "modified_ncf": NCF}.get(name, "5.00")


@pytest.mark.parametrize("name", sorted(name for name, (form, _) in INHERITANCE.items() if form != "607"))
def test_an_override_holds_until_it_is_restored(name):
    purchase = uuid4()
    facts, declaration = credit_note(
        category="09", payment_method="01", actual_refund=True, purchase_activity_id=purchase
    )
    facts = facts.model_copy(update={"legal_tip": known("100"), "amount": known("1280.00")})
    linked = LinkedSources(
        original_ncf=original_ncf(facts, declaration, {str(purchase): read(ncf=ORIGINAL)}.get)
    )
    shown = inherit_amounts(facts, declaration, (), linked)
    followed = getattr(shown, name)
    assert followed is not None or name == "services_amount"

    edited = shown.model_copy(update={name: _typed(name)})
    overrides = inheritance_overrides(facts, shown, edited, (), linked=linked)
    assert name in overrides
    assert not inheritance_state(facts, edited, overrides, linked)[name].inherited
    assert getattr(inherit_amounts(facts, edited, overrides, linked), name) == _typed(name)

    restored = inheritance_overrides(facts, edited, None, overrides, restore=(name,), linked=linked)
    assert getattr(inherit_amounts(facts, edited, restored, linked), name) == followed
    assert inheritance_state(facts, edited, restored, linked)[name].inherited


def test_goods_and_services_say_they_restore_and_override_together():
    facts = read()
    linked = suggested(category="09", payment_method="01")
    state = inheritance_state(facts, fresh(facts, linked), None, linked)
    paired = {name: entry.paired_with for name, entry in state.items()}
    assert paired == {
        "goods_amount": ("services_amount",),
        "id_type": (),
        "itbis": (),
        "legal_tip": (),
        "paid_on": (),
        "services_amount": ("goods_amount",),
    }


def test_a_review_that_changes_nothing_shown_records_no_override():
    facts = read()
    linked = suggested(category="09", payment_method="01")
    shown = fresh(facts, linked)
    overrides = inheritance_overrides(facts, shown, shown, None, amount_derived=True, linked=linked)
    assert overrides == ()


def test_approval_writes_what_the_review_showed():
    facts = read()
    linked = replace(
        suggested(category="09", payment_method="03"), built=declaration_from_facts(facts, None)
    )
    shown = written_from(facts, None, None, None, linked)

    written = approved_from(facts, None, None, None, linked)

    answers = {"category": "09", "payment_method": "03"}
    assert written.model_dump(exclude={"suggestion_sources"}) == {
        **shown.model_dump(exclude={"suggestion_sources"}),
        **answers,
    }
    assert (written.id_type, written.goods_amount, written.paid_on) == ("1", "1000.00", DAY)


def test_export_still_reads_an_unconfirmed_tipo_de_gasto_as_missing():
    facts = read()
    # What is stored follows a person's answers alone: a suggestion fills nothing.
    stored = inherit_amounts(facts, fresh(facts, suggested(category="09")), ())
    assert (stored.category, stored.goods_amount, stored.services_amount) == (None, None, None)

    prefilled = stored.model_copy(update={"category": "09", "category_suggested": True})
    record = FiscalRecord(
        activity_id=str(uuid4()),
        activity_revision=1,
        draft_id=str(uuid4()),
        approved_revision=1,
        occurred_on=DAY,
        amount="1180.00",
        currency="DOP",
        kind="expense",
        document_type="recibo",
        facts=facts,
        declaration=inherit_amounts(facts, prefilled, ()),
        source_ids=(),
    )
    exported = confirmed_declaration(record)
    assert (exported.category, exported.goods_amount, exported.services_amount) == (None, None, None)
