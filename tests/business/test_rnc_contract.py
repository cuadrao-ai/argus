"""An RNC with no nonzero digit is no RNC. The facts contract owns the rule:
a read or a QR of one holds an unknown RNC with its sources kept, a saved
read of one loads as unknown, and a person's is refused. A real RNC is kept."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    KnownInput,
    Rnc,
    Unknown,
)
from argus.domain.ingestion.documents.dgii_qr import fill_from_qr
from argus.domain.ingestion.documents.extractor import fiscal_facts_from_receipt
from argus.domain.ingestion.documents.models import ReceiptDetails
from pydantic import TypeAdapter, ValidationError

from tests.dgii_qr_support import URL

ZEROS = ("000000000", "000-00000-0", "00000000000")


@pytest.mark.parametrize("printed", ZEROS)
def test_a_read_rnc_without_a_number_is_unknown_and_keeps_its_source(printed):
    source = uuid4()
    facts = fiscal_facts_from_receipt(
        ReceiptDetails(rnc=printed, ncf="B0100000099"), source_id=source
    )
    assert isinstance(facts.rnc, Unknown)
    assert (facts.rnc.origin, facts.rnc.source_ids) == ("extracted", (source,))
    # The rest of the read is untouched.
    assert (facts.ncf.state, facts.ncf.value) == ("known", "B0100000099")


def test_a_real_rnc_is_kept_as_read():
    facts = fiscal_facts_from_receipt(
        ReceiptDetails(rnc="131-99988-8"), source_id=uuid4()
    )
    assert (facts.rnc.state, facts.rnc.value, facts.rnc.origin) == (
        "known",
        "131-99988-8",
        "extracted",
    )


def test_a_saved_read_of_zeros_loads_as_unknown_instead_of_failing():
    source = str(uuid4())
    saved = {
        "rnc": {
            "state": "known",
            "value": "000000000",
            "origin": "extracted",
            "verified": False,
            "source_ids": [source],
        }
    }
    loaded = FiscalFacts.model_validate(saved)
    assert isinstance(loaded.rnc, Unknown)
    assert [str(item) for item in loaded.rnc.source_ids] == [source]


def test_a_qr_of_zeros_fills_no_rnc():
    from argus.domain.ingestion.documents.dgii_qr import parse_dgii_url

    qr = parse_dgii_url(URL).model_copy(update={"rnc_emisor": "000000000"})
    source = uuid4()
    facts = BusinessFacts(fiscal=FiscalFacts()).model_dump(mode="json")
    filled = BusinessFacts.model_validate(
        fill_from_qr(facts, qr, source, fill_amount=False)
    )
    assert isinstance(filled.fiscal.rnc, Unknown)
    assert filled.fiscal.ecf.state == "known"


@pytest.mark.parametrize("origin", ["owner_stated", "member_set"])
def test_a_person_typing_zeros_is_refused(origin):
    with pytest.raises(ValidationError, match="nonzero digit"):
        FiscalFacts(
            rnc=Known[Rnc](value="000000000", origin=origin, source_ids=(uuid4(),))
        )
    with pytest.raises(ValidationError, match="nonzero digit"):
        TypeAdapter(KnownInput[Rnc]).validate_python(
            {"state": "known", "value": "000-00000-0"}
        )
    kept = FiscalFacts(
        rnc=Known[Rnc](value="131999888", origin=origin, source_ids=(uuid4(),))
    )
    assert kept.rnc.value == "131999888"
