from dataclasses import replace
from uuid import UUID

import pytest
from argus.domain.business.amount_inheritance import INHERITANCE, inherit_amounts
from argus.domain.business.contracts.facts import Known
from argus.domain.business.dgii_columns import COLUMNS
from argus.domain.business.dgii_export import line_values
from argus.domain.business.dgii_validation import FiscalRecord, record_issues
from argus.domain.business.purchase_review import AMOUNT_SIDES

from tests.dgii.test_packet import practice_records

FILER = "199990013"
# What the 606 or 607 line carries while the field inherits, and what holds the
# export once a person clears it. None: the field is optional and the cell is empty.
CASES = [
    ("606", "goods_amount", "1000.00", ("fiscal_billed_amount_must_be_positive", "billed_amount")),
    ("606", "services_amount", "", ("fiscal_billed_amount_must_be_positive", "billed_amount")),
    ("606", "itbis", "180.00", ("fiscal_fact_required", "itbis")),
    ("606", "legal_tip", "100.00", ("fiscal_invoice_total_conflict", "amount")),
    ("606", "paid_on", "20260903", None),
    ("607", "billed_amount", "2000.00", ("fiscal_fact_required", "billed_amount")),
    ("607", "itbis", "360.00", ("fiscal_fact_required", "itbis")),
    ("607", "legal_tip", "100.00", ("fiscal_invoice_total_conflict", "amount")),
]


def snapshot(form: str, cleared: str | None = None) -> FiscalRecord:
    """A paid practice record with a legal tip, resolved the way the fiscal snapshot resolves it."""

    base = next(item for item in practice_records() if item.declaration.form == form)
    tip = Known(value="100", origin="member_set", source_ids=(UUID(int=1),))
    total = str(int(float(base.amount)) + 100)
    facts = base.facts.model_copy(
        update={"legal_tip": tip, "amount": base.facts.amount.model_copy(update={"value": total})}
    )
    names = () if cleared is None else AMOUNT_SIDES if cleared in AMOUNT_SIDES else (cleared,)
    declaration = base.declaration.model_copy(
        update={**({"bank": f"{total}.00"} if form == "607" else {}), **dict.fromkeys(names)}
    )
    return replace(
        base,
        amount=total,
        facts=facts,
        declaration=inherit_amounts(facts, declaration, tuple(names), paid=True),
        fiscal_overrides=tuple(names),
        paid=True,
    )


def cell(record: FiscalRecord, name: str) -> str:
    columns = [column for column, _ in COLUMNS[record.declaration.form]]
    return line_values(record)[columns.index(name)]


def test_every_inherited_field_is_covered():
    covered = {(form, name) for form, name, _, _ in CASES}
    assert covered == {
        (form, name)
        for name, (only, _) in INHERITANCE.items()
        for form in ("606", "607")
        if only in (None, form)
    }


@pytest.mark.parametrize(("form", "name", "inherited", "held"), CASES)
def test_an_inherited_fiscal_amount_reaches_the_line(form, name, inherited, held):
    record = snapshot(form)
    assert record_issues(record, {}, filer_identity=FILER) == []
    assert cell(record, name) == inherited


@pytest.mark.parametrize(("form", "name", "inherited", "held"), CASES)
def test_a_cleared_fiscal_amount_stays_cleared(form, name, inherited, held):
    record = snapshot(form, cleared=name)
    assert getattr(record.declaration, name) is None
    issues = {(item["code"], item["field"]) for item in record_issues(record, {}, filer_identity=FILER)}
    if held is None:
        assert issues == set()
        assert cell(record, name) == ""
    else:
        assert held in issues
