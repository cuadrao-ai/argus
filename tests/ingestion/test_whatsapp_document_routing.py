"""A sender can place each file in exactly one of their eligible Businesses."""

import pytest
from argus.domain.business.document_type import buyer_tax_id
from argus.domain.ingestion.whatsapp.routing import route_document
from argus.domain.owner_scope import BusinessSpace

A = "101234567"
B = "00100000001"
C = "201111111"
X = "302222222"
ELIGIBLE = {"a": A, "b": B}


@pytest.mark.parametrize(
    ("issuer", "buyer", "expected"),
    [
        ("1-01-23456-7", None, BusinessSpace("a")),
        (X, "001-0000000-1", BusinessSpace("b")),
        (A, A, BusinessSpace("a")),
        (A, B, "two_matches"),
        (None, None, "no_buyer_rnc"),
        (X, None, "no_buyer_rnc"),
        (None, X, "no_match"),
        (None, C, "no_match"),
    ],
    ids=[
        "issuer",
        "buyer",
        "same",
        "ambiguous",
        "neither",
        "missing-buyer",
        "unknown",
        "ineligible",
    ],
)
def test_route_against_only_the_senders_businesses(issuer, buyer, expected):
    assert route_document(ELIGIBLE, issuer=issuer, buyer=buyer) == expected


def test_held_read_requires_a_match_after_other_grants_are_lost():
    assert route_document({"a": A}, issuer=None, buyer=None) == "no_buyer_rnc"
    assert route_document({}, issuer=None, buyer=None) == "no_eligible_business"


def test_buyer_from_printed_id_when_qr_omits_it():
    from argus.domain.business.contracts.checks import DgiiQr

    url = "https://ecf.dgii.gov.do/consulta"
    qr = DgiiQr(url=url, host="ecf.dgii.gov.do", rnc_emisor=A, encf="E310000000001")
    assert buyer_tax_id(None, B) == B
    assert buyer_tax_id(qr, B) == B
    assert buyer_tax_id(qr.model_copy(update={"rnc_comprador": A}), B) == A
