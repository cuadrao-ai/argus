import pytest
from argus.domain.business.fiscal_profile import FiscalProfileChange
from pydantic import ValidationError


def profile(kind: str, value: str, *, previous=None):
    return FiscalProfileChange(
        name="Taller Norte",
        previous_name="Mi negocio",
        tax_id={"type": kind, "value": value},
        previous_tax_id=previous,
    )


@pytest.mark.parametrize(
    ("kind", "raw", "digits"),
    [
        ("rnc", "199990013", "199990013"),
        ("rnc", "199-99001-3", "199990013"),
        ("rnc", "199 990013", "199990013"),
        ("cedula", "00100000001", "00100000001"),
        ("cedula", "001-0000000-1", "00100000001"),
    ],
)
def test_valid_rnc_and_cedula_keep_type_and_normalized_digits(kind, raw, digits):
    change = profile(kind, raw)
    assert change.tax_id is not None
    assert change.tax_id.type == kind
    assert change.tax_id.value == digits


@pytest.mark.parametrize(
    ("kind", "raw", "code"),
    [
        ("rnc", "00100000001", "tax_id_length"),
        ("cedula", "199990013", "tax_id_length"),
        ("rnc", "19999001", "tax_id_length"),
        ("cedula", "001000000012", "tax_id_length"),
        ("rnc", "000000000", "tax_id_all_zero"),
        ("cedula", "00000000000", "tax_id_all_zero"),
        ("rnc", "19999001A", "tax_id_not_digits"),
        ("cedula", "001-0000000-X", "tax_id_not_digits"),
        ("passport", "00100000001", "tax_id_type"),
    ],
)
def test_invalid_rnc_and_cedula_name_the_reason(kind, raw, code):
    with pytest.raises(ValidationError, match=code):
        profile(kind, raw)
