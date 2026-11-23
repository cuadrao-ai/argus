"""The facts the dossier states so the web keeps no rule of its own (#2317):
the note a record is, whether Montos adds up, and the declaration fields a
person cannot hold apart from their source. Each has one owner on the server."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from argus.domain.business.actions.facts import reviewed_amount_facts
from argus.domain.business.amount_inheritance import (
    NO_SOURCES,
    inheritance_overrides,
    inheritance_state,
    source_owned,
    written_from,
)
from argus.domain.business.contracts.dgii import PurchaseReview, SalePaymentSplit
from argus.domain.business.contracts.dossier import (
    _UNMEASURED_DOSSIER_FIELDS,
    AmountsCheck,
    BusinessDossier,
)
from argus.domain.business.contracts.facts import BusinessFacts, MontosReview, NetAmount
from argus.domain.business.dgii_validation import is_credit, is_debit, record_issues
from argus.domain.business.fact_blockers import record_note
from argus.domain.business.purchase_review import (
    apply_payment_split,
    apply_purchase,
    net_amount,
)
from argus.domain.business.review_flags import amounts_check, review_flags
from faker import Faker
from pydantic import ValidationError

from tests.business import test_fiscal_links as links
from tests.business.test_document_type_direction import _event, _review
from tests.business.test_montos import receipt
from tests.dgii.test_packet import practice_records

fake = Faker()
fake.seed_instance(2317)
NEW_FIELDS = ("amounts_check", "note_kind", "source_owned_fields")
PURCHASE = apply_purchase(None, PurchaseReview(category="09"))
SALE = apply_payment_split(None, SalePaymentSplit())


def _number(series: str, kind: str) -> str:
    return f"{series}{kind}" + fake.numerify("#" * (8 if series == "B" else 10))


def _numbered(number: str, kind: str = "expense") -> BusinessFacts:
    facts = links.read(ncf=number)
    return facts.model_copy(update={"kind": links.known(kind)})


@pytest.mark.parametrize(
    ("series", "kind", "note"),
    [
        ("B", "01", None),
        ("E", "31", None),
        ("B", "02", None),
        ("B", "04", "credit"),
        ("E", "34", "credit"),
        ("B", "03", "debit"),
        ("E", "33", "debit"),
    ],
)
@pytest.mark.parametrize("declaration", [PURCHASE, SALE], ids=["purchase", "sale"])
def test_the_comprobante_number_names_the_note(series, kind, note, declaration):
    number = _number(series, kind)
    facts = _numbered(number, "income" if declaration is SALE else "expense")

    assert record_note(facts, declaration) == note
    assert record_note(facts, None) == note


def test_the_note_is_the_one_the_606_and_607_read():
    for record in practice_records():
        note = record_note(record.facts, None)
        assert (note == "credit") == is_credit(record)
        assert (note == "debit") == is_debit(record)


def test_a_debit_note_still_needs_the_comprobante_it_modifies():
    purchase = practice_records()[0]
    facts = purchase.facts.model_copy(
        update={
            "fiscal": purchase.facts.fiscal.model_copy(
                update={"ncf": links.known(_number("B", "03"))}
            )
        }
    )
    debit = replace(purchase, facts=facts)

    assert is_debit(debit)
    assert {"code": "fiscal_credit_reference_conflict", "activity_id": debit.activity_id, "field": "modified_ncf"} in record_issues(
        debit, {}, filer_identity=None
    )


@pytest.mark.parametrize(
    ("kind", "held", "note"),
    [
        ("expense", {}, None),
        ("refund", {}, "credit"),
        ("expense", {"actual_refund": True}, "credit"),
        ("expense", {"modified_ncf": "B0100000007"}, "credit"),
    ],
    ids=["regular", "refund", "saved refund", "saved reference"],
)
def test_a_record_with_no_note_number_is_a_credit_note_by_what_it_holds(kind, held, note):
    facts = _numbered(_number("B", "01"), kind)

    assert record_note(facts, PURCHASE.model_copy(update=held)) == note


@pytest.mark.parametrize(
    ("total", "tax", "subtotal", "tip", "state", "difference"),
    [
        ("1180.00", "180.00", "1000.00", None, "adds_up", None),
        ("1180.00", "180.00", None, None, "adds_up", None),
        ("1280.00", "180.00", "1000.00", "100.00", "adds_up", None),
        ("1200.00", "180.00", "1000.00", None, "difference", "20.00"),
        ("1100.00", "180.00", "1000.00", None, "difference", "-80.00"),
        ("1180.00", None, "1000.00", None, "unchecked", None),
        ("1180.00", None, None, None, "unchecked", None),
        ("900.00", None, "1000.00", None, "difference", "-100.00"),
    ],
)
def test_the_montos_check_and_the_mismatch_flag_are_one_rule(
    total, tax, subtotal, tip, state, difference
):
    facts = receipt(total, tax, subtotal, tip)

    check = amounts_check(facts)

    assert check == AmountsCheck(state=state, difference=difference)
    flagged = [flag for flag in review_flags(facts) if flag.code == "amounts_mismatch"]
    assert [flag.difference for flag in flagged] == ([difference] if difference else [])


@pytest.mark.parametrize("declaration", [PURCHASE, SALE], ids=["purchase", "sale"])
def test_the_montos_check_reads_a_sale_as_it_reads_a_purchase(declaration):
    assert amounts_check(receipt("1180.00", "180.00", "1000.00"), declaration).state == "adds_up"
    assert amounts_check(receipt("1190.00", "180.00", "1000.00"), declaration) == AmountsCheck(
        state="difference", difference="10.00"
    )


def test_montos_with_no_total_or_no_fiscal_facts_is_unchecked():
    assert amounts_check(BusinessFacts()) == AmountsCheck(state="unchecked")
    bare = receipt("900.00", None, "1000.00").model_copy(update={"fiscal": None})
    assert amounts_check(bare) == AmountsCheck(state="unchecked")
    assert review_flags(bare) == ()


@pytest.mark.parametrize(("state", "difference"), [("adds_up", "1.00"), ("difference", None)])
def test_a_difference_goes_with_its_state_alone(state, difference):
    with pytest.raises(ValidationError):
        AmountsCheck(state=state, difference=difference)


def test_tipo_de_id_is_source_owned_on_a_purchase_alone():
    facts = links.read()

    assert "id_type" in source_owned(facts, "606")
    assert "id_type" not in source_owned(facts, "607")
    assert "id_type" not in source_owned(facts, None)


def test_a_stored_tipo_de_id_override_is_ignored():
    facts = links.read()
    held = links.fresh(facts).model_copy(update={"id_type": "2"})

    shown = written_from(facts, held, ("id_type",), None, NO_SOURCES)

    assert shown.id_type == "1"
    assert inheritance_state(facts, shown, ("id_type",))["id_type"].inherited


def test_a_new_tipo_de_id_override_is_dropped(monkeypatch):
    facts = links.read()
    shown = links.fresh(facts)
    typed = shown.model_copy(update={"id_type": "2"})
    for overrides in (
        inheritance_overrides(facts, shown, typed, ()),
        inheritance_overrides(facts, shown, None, (), written=("id_type",)),
    ):
        assert "id_type" not in overrides
    event = _event("recibo", facts)
    event.resolution["business"].update(
        dgii=typed.model_dump(mode="json"), fiscal_overrides=["id_type"]
    )

    saved = _review(
        monkeypatch, event, None, montos=MontosReview(override_inherited=("id_type",))
    )

    assert saved["dgii"]["id_type"] == "1"
    assert "id_type" not in saved["fiscal_overrides"]


def test_a_typed_tipo_de_id_is_saved_as_the_one_the_rnc_states(monkeypatch):
    facts = links.read()
    event = _event("recibo", facts)
    event.resolution["business"]["dgii"] = links.fresh(facts).model_dump(mode="json")

    saved = _review(monkeypatch, event, None, purchase=PurchaseReview(id_type="2"))

    assert saved["dgii"]["id_type"] == "1"
    assert "id_type" not in saved["fiscal_overrides"]


def test_a_sale_keeps_the_tipo_de_id_a_person_gave():
    facts = links.read()
    held = SALE.model_copy(update={"id_type": "2"})

    assert written_from(facts, held, (), None, NO_SOURCES).id_type == "2"
    assert "id_type" not in inheritance_state(facts, held, ())


def test_the_new_facts_are_on_the_dossier_and_out_of_the_model_view():
    fields = BusinessDossier.model_fields

    assert fields["amounts_check"].default == AmountsCheck(state="unchecked")
    assert fields["note_kind"].default is None
    assert fields["source_owned_fields"].default == ()
    assert all(_UNMEASURED_DOSSIER_FIELDS[name] is True for name in NEW_FIELDS)


def test_a_cent_of_rounding_still_adds_up():
    cent = Decimal("0.01")
    total = Decimal(fake.random_int(1000, 900_000)) / 100
    tax = (total * Decimal("0.18")).quantize(cent)
    facts = receipt(format(total + tax + cent, ".2f"), format(tax, ".2f"), format(total, ".2f"))

    assert amounts_check(facts).state == "adds_up"


def test_a_typed_subtotal_taken_back_is_the_calculated_one_again():
    read = receipt("1180.00", "180.00")
    assert net_amount(read) == NetAmount(amount="1000.00", source="calculated")

    typed = reviewed_amount_facts(
        read, MontosReview(net_amount={"state": "known", "value": "900"}), (uuid4(),),
        origin="member_set",
    )
    assert net_amount(typed).source == "edited"
    assert amounts_check(typed) == AmountsCheck(state="difference", difference="100.00")

    restored = reviewed_amount_facts(
        typed, MontosReview(net_amount={"state": "unknown"}), (uuid4(),), origin="member_set"
    )
    assert net_amount(restored) == NetAmount(amount="1000.00", source="calculated")
    assert amounts_check(restored).state == "adds_up"
