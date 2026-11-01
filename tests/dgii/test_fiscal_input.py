"""The fiscal form sends identifiers as a person keys them or a read kept them.
The server normalizes once, at the contract boundary: spaces and dashes go,
letters become upper case, and only then does the identifier shape apply."""

import pytest
from argus.domain.business.contracts.dgii import FiscalInput, PurchaseDeclaration
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("printed", "stored"),
    [
        ("1-23-45678-9", "123456789"),
        ("123 45678 9", "123456789"),
        ("001-1234567-8", "00112345678"),
        (" 131000002 ", "131000002"),
        ("131000002", "131000002"),
    ],
)
def test_rnc_keeps_its_digits_without_dashes_or_spaces(printed, stored):
    assert FiscalInput(rnc=printed, ncf=None, itbis=None).rnc == stored


@pytest.mark.parametrize(
    ("printed", "stored"),
    [("b0100000001", "B0100000001"), (" e310000000001 ", "E310000000001")],
)
def test_ncf_is_trimmed_and_upper_cased(printed, stored):
    assert FiscalInput(rnc=None, ncf=printed, itbis=None).ncf == stored
    declared = PurchaseDeclaration.model_validate(
        {
            **{name: None for name in PurchaseDeclaration.model_fields},
            "form": "606",
            "actual_refund": False,
            "category_suggested": False,
            "modified_ncf": printed,
        }
    )
    assert declared.modified_ncf == stored


@pytest.mark.parametrize("value", ["1.23.456", "RNC: 123456789", "", "-"])
def test_anything_else_is_still_refused(value):
    with pytest.raises(ValidationError):
        FiscalInput(rnc=value, ncf=None, itbis=None)
