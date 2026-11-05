import pytest
from argus.domain.business.fiscal_identity import (
    cedula_check_digit_ok,
    rnc_check_digit_ok,
)


@pytest.mark.parametrize(
    ("digits", "accepted"),
    [
        pytest.param("100000022", True, id="remainder-0"),
        pytest.param("100000081", True, id="remainder-1"),
        pytest.param("100000039", True, id="remainder-2"),
        pytest.param("100000004", True, id="later-weight"),
        pytest.param("138888002", True, id="valid-9"),
        pytest.param("138888003", False, id="invalid-9"),
        pytest.param("100000020", False, id="remainder-0-bad-digit"),
        pytest.param("100000080", False, id="remainder-1-bad-digit"),
        pytest.param("1000000220", False, id="length-10"),
        pytest.param("10000002", False, id="length-8"),
        pytest.param("10000002-2", False, id="punctuation"),
        pytest.param("", False, id="missing"),
    ],
)
def test_rnc_check_digit(digits, accepted):
    assert rnc_check_digit_ok(digits) is accepted


@pytest.mark.parametrize(
    ("digits", "accepted"),
    [
        pytest.param("10000000058", True, id="valid-11"),
        pytest.param("10000000009", True, id="no-doubled-digit"),
        pytest.param("10000000017", True, id="doubled-digit"),
        pytest.param("10000000059", False, id="invalid-11"),
        pytest.param("0000000000", False, id="length-10"),
        pytest.param("000000000000", False, id="length-12"),
        pytest.param("1000000005-8", False, id="punctuation"),
        pytest.param("", False, id="missing"),
    ],
)
def test_cedula_check_digit(digits, accepted):
    assert cedula_check_digit_ok(digits) is accepted
