from dataclasses import replace
from uuid import UUID

import pytest
from argus.domain.business.fiscal_identity import (
    cedula_check_digit_ok,
    identity_digits,
    normalized_filer_tax_id,
    normalized_ncf,
    normalized_taxpayer_id,
    rnc_check_digit_ok,
)
from argus.domain.ingestion.documents.extractor import fiscal_facts_from_receipt
from argus.domain.ingestion.documents.models import ReceiptDetails
from faker import Faker

from tests.dgii.test_packet import packet, practice_records


@pytest.fixture(params=["ascii", "fullwidth", "mixed", "arabic_indic"])
def digit_style(request):
    return request.param


def styled(value: str, style: str) -> str:
    if style == "ascii":
        return value
    digits = "٠١٢٣٤٥٦٧٨٩" if style == "arabic_indic" else "０１２３４５６７８９"
    translated = value.translate(str.maketrans("0123456789", digits))
    return value[:-1] + translated[-1] if style == "mixed" else translated


@pytest.fixture
def fake():
    result = Faker()
    result.seed_instance(1612)
    return result


@pytest.fixture(params=[("B01", 8), ("E31", 10)], ids=["ncf", "ecf"])
def fiscal_number(request, fake):
    prefix, length = request.param
    return prefix + fake.numerify("#" * length)


def test_read_preserves_identifier_and_validation_accepts_only_ascii(
    fake, fiscal_number, digit_style
):
    read = styled(fiscal_number, digit_style)
    receipt = ReceiptDetails(ncf=read)
    fiscal = fiscal_facts_from_receipt(receipt, source_id=UUID(fake.uuid4()))

    assert receipt.ncf == read
    assert fiscal.ncf.value == read
    assert normalized_ncf(fiscal.ncf.value) == (
        fiscal_number if digit_style == "ascii" else None
    )


def test_606_requires_ascii_receipt_identifier(fake, fiscal_number, digit_style):
    read = styled(fiscal_number, digit_style)
    record = practice_records()[0]
    projected = fiscal_facts_from_receipt(
        ReceiptDetails(ncf=read), source_id=UUID(fake.uuid4())
    )
    record = replace(
        record,
        facts=record.facts.model_copy(
            update={
                "fiscal": record.facts.fiscal.model_copy(update={"ncf": projected.ncf})
            }
        ),
    )

    result = packet((record,))
    form = "dgii/DGII_F_606_199990013_202609.TXT"
    if digit_style == "ascii":
        assert result.manifest["issues"] == []
        assert fiscal_number in result.files[form].decode("ascii")
    else:
        assert "fiscal_ncf_malformed" in {
            issue["code"] for issue in result.manifest["issues"]
        }
        assert form not in result.files


@pytest.fixture(
    params=[("rnc", 9, rnc_check_digit_ok), ("cedula", 11, cedula_check_digit_ok)]
)
def taxpayer(request, fake):
    kind, length, valid = request.param
    prefix = fake.numerify("1" + "#" * (length - 2))
    number = next(
        prefix + str(digit) for digit in range(10) if valid(prefix + str(digit))
    )
    return kind, number, valid


def test_taxpayer_check_digits_require_ascii(taxpayer, digit_style):
    _, number, valid = taxpayer
    assert valid(styled(number, digit_style)) is (digit_style == "ascii")


def test_taxpayer_normalization_requires_ascii(taxpayer, digit_style):
    kind, number, _ = taxpayer
    value = styled(number, digit_style)
    expected = number if digit_style == "ascii" else None
    assert identity_digits(value) == expected
    assert normalized_taxpayer_id(value) == expected
    if digit_style == "ascii":
        assert normalized_filer_tax_id(kind, value) == number
    else:
        with pytest.raises(ValueError, match="tax_id_not_digits"):
            normalized_filer_tax_id(kind, value)
