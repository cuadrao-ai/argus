"""The reader's Forma de pago and Tipo de gasto are the 606's own codes, and
a value that is not one of them is a blank, never a failed read."""

import pytest
from argus.domain.business.dgii_codes import EXPENSE_TYPES, PAYMENT_FORMS
from argus.domain.ingestion.documents.models import ReceiptDetails
from loguru import logger

CODES = {"payment_form": PAYMENT_FORMS, "expense_type": EXPENSE_TYPES}


@pytest.mark.parametrize("field", list(CODES))
def test_a_receipt_read_holds_each_code_the_606_owns(field):
    assert ReceiptDetails().model_dump()[field] is None
    for code in CODES[field]:
        assert getattr(ReceiptDetails(**{field: code}), field) == code


@pytest.mark.parametrize("field", list(CODES))
def test_the_model_is_told_each_code_with_its_label(field):
    described = ReceiptDetails.model_fields[field].description

    for code, label in CODES[field].items():
        assert f"{code} {label}" in described


@pytest.mark.parametrize("field", list(CODES))
@pytest.mark.parametrize("value", ["12", "3", "tarjeta", ""])
def test_a_value_that_is_no_code_is_a_logged_blank(field, value):
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(message.record["message"]))
    try:
        read = ReceiptDetails(**{field: value})
    finally:
        logger.remove(sink)

    assert getattr(read, field) is None
    assert lines == [f"document_read_code_unknown field={field}"]
