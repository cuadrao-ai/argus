import pytest
from argus.domain.business.contracts.invoicing import CustomerInput
from argus.domain.business.fiscal_sandbox.contracts import Case, digest
from argus.domain.business.invoicing.validation import customer_errors
from pydantic import ValidationError


@pytest.fixture(params=["ascii", "fullwidth", "mixed", "arabic_indic"])
def digits(request):
    def convert(value):
        if request.param == "ascii":
            return value
        alphabet = "٠١٢٣٤٥٦٧٨٩" if request.param == "arabic_indic" else "０１２３４５６７８９"
        translated = value.translate(str.maketrans("0123456789", alphabet))
        return value[:1] + translated[1:] if request.param == "mixed" else translated

    return convert, request.param == "ascii"


@pytest.mark.parametrize("length", [9, 11])
def test_customer_tax_id_requires_ascii_digits(faker, digits, length):
    convert, accepted = digits
    tax_id = convert(faker.numerify("1" + "#" * (length - 1)))
    customer = CustomerInput(name="Cliente de prueba", tax_id=tax_id)
    assert ("tax_id" not in customer_errors(customer)) is accepted


def test_fiscal_case_issuer_requires_ascii_digits(case_factory, digits):
    convert, accepted = digits
    data = case_factory().model_dump()
    data["issuer"] = convert(data["issuer"])
    data["payload"]["sender"]["rnc"] = data["issuer"]
    data["payload_digest"] = digest(data["payload"])
    if accepted:
        assert Case.model_validate(data).issuer == data["issuer"]
    else:
        with pytest.raises(ValidationError):
            Case.model_validate(data)


def test_fiscal_case_number_requires_ascii_digits(case_factory, digits):
    convert, accepted = digits
    data = case_factory().model_dump()
    data["number"] = data["kind"] + convert(data["number"][3:])
    data["payload"]["idDoc"]["encf"] = data["number"]
    data["payload_digest"] = digest(data["payload"])
    if accepted:
        assert Case.model_validate(data).number == data["number"]
    else:
        with pytest.raises(ValidationError):
            Case.model_validate(data)
