"""The local e-CF checks say what the file itself proves, in words that do
not overreach: a signature that verifies means the content has not changed
since it was signed with the key the file carries; DGII acceptance and the
issuing authority are never claimed. Fixtures are generated here, fake only."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from argus.domain.ingestion.documents.ecf_checks import (
    MAX_CERTIFICATE_CHARS,
    ecf_checks,
    read_ecf,
)
from argus.domain.ingestion.documents.models import ReceiptDetails

from tests.ecf_signing_support import (
    FIXTURE,
    RNC,
    SIGNED_AT,
    fake_certificate,
    fake_key,
    signed_ecf,
)

NOW = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)
READ = ReceiptDetails(
    total="33254.91",
    itbis="4676.47",
    rnc=RNC,
    ecf="E320000001234",
    occurred_on=date(2026, 10, 9),
    currency="DOP",
)


def by_name(verification):  # noqa: ANN001
    return {check.name: check for check in verification.checks}


def test_a_signed_invoice_verifies_integrity_totals_read_and_subject_only():
    verification = ecf_checks(read_ecf(signed_ecf()), READ, NOW)
    checks = by_name(verification)
    assert (verification.encf, verification.tipo_ecf) == ("E320000001234", "32")
    assert [c.name for c in verification.checks] == [
        "signature_integrity",
        "totals_arithmetic",
        "read_matches_xml",
        "certificate_validity",
        "certificate_issuer",
        "subject_rnc",
        "dgii_accepted",
        "security_code",
    ]
    assert checks["signature_integrity"].state == "verified"
    assert checks["totals_arithmetic"].state == "verified"
    assert checks["totals_arithmetic"].detail["sum_of_items"] == "25980.40"
    assert checks["read_matches_xml"].state == "verified"
    # Two facts about the certificate window, and revocation named as unchecked.
    validity = checks["certificate_validity"]
    assert (validity.state, validity.code) == ("verified", "revocation_not_checked")
    assert (validity.detail["at_signature"], validity.detail["today"]) == (
        "valid",
        "valid",
    )
    assert validity.detail["revocation"] == "not_checked"
    # No trust list and no network: these two never claim more than they know.
    assert (checks["certificate_issuer"].state, checks["certificate_issuer"].code) == (
        "not_checked",
        "issuer_not_on_trust_list",
    )
    assert checks["certificate_issuer"].detail["issuer"] == "Autoridad Ficticia de Prueba"
    assert (checks["dgii_accepted"].state, checks["dgii_accepted"].code) == (
        "not_checked",
        "network_not_in_tier_a",
    )
    assert checks["subject_rnc"].state == "verified"
    # The read carries no printed code, so the expected one is kept for a person.
    security = checks["security_code"]
    assert (security.state, security.code) == ("not_checked", "no_printed_code")
    assert len(security.detail["expected"]) == 6


def test_content_changed_after_signing_fails_integrity_only():
    signed = signed_ecf()
    tampered = signed.replace(
        b"<MontoTotal>33254.91</MontoTotal>", b"<MontoTotal>33254.92</MontoTotal>"
    )
    checks = by_name(ecf_checks(read_ecf(tampered), READ, NOW))
    assert (checks["signature_integrity"].state, checks["signature_integrity"].code) == (
        "failed",
        "digest_mismatch",
    )
    # The other checks still read the file as it is now.
    assert checks["totals_arithmetic"].code == "totals_mismatch"
    assert checks["read_matches_xml"].code == "read_differs"
    assert checks["read_matches_xml"].detail == {"total": "read=33254.91 xml=33254.92"}


def test_a_signature_from_another_key_fails():
    key = fake_key()
    checks = by_name(
        ecf_checks(read_ecf(signed_ecf(key=key, sign_with=fake_key())), READ, NOW)
    )
    assert (checks["signature_integrity"].state, checks["signature_integrity"].code) == (
        "failed",
        "signature_invalid",
    )


def test_an_unsigned_invoice_is_not_checked_and_still_adds_up():
    checks = by_name(ecf_checks(read_ecf(FIXTURE.read_bytes()), READ, NOW))
    assert (checks["signature_integrity"].state, checks["signature_integrity"].code) == (
        "not_checked",
        "no_signature",
    )
    assert checks["totals_arithmetic"].state == "verified"
    assert checks["certificate_validity"].code == "no_signature"
    assert checks["security_code"].code == "no_signature"


def test_the_certificate_window_is_judged_at_the_declared_signing_time():
    key = fake_key()
    expired = fake_certificate(
        key,
        not_before=datetime(2024, 1, 1, tzinfo=timezone.utc),
        not_after=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    checks = by_name(
        ecf_checks(read_ecf(signed_ecf(key=key, certificate=expired)), READ, NOW)
    )
    validity = checks["certificate_validity"]
    assert (validity.state, validity.code) == (
        "failed",
        "certificate_not_valid_at_signature",
    )
    assert (validity.detail["at_signature"], validity.detail["today"]) == (
        "expired",
        "expired",
    )
    # Valid when signed, expired today: still what the file proves.
    then_valid = fake_certificate(
        key,
        not_before=datetime(2026, 1, 1, tzinfo=timezone.utc),
        not_after=datetime(2026, 10, 10, tzinfo=timezone.utc),
    )
    checks = by_name(
        ecf_checks(read_ecf(signed_ecf(key=key, certificate=then_valid)), READ, NOW)
    )
    validity = checks["certificate_validity"]
    assert (
        validity.state,
        validity.detail["at_signature"],
        validity.detail["today"],
    ) == (
        "verified",
        "valid",
        "expired",
    )
    # No declared signing time: the window cannot be judged.
    checks = by_name(ecf_checks(read_ecf(signed_ecf(key=key, signed_at=None)), READ, NOW))
    assert checks["certificate_validity"].code == "signature_time_missing"


def test_the_subject_serial_must_be_the_issuer_rnc():
    key = fake_key()
    other = fake_certificate(key, rnc="101000000")
    checks = by_name(
        ecf_checks(read_ecf(signed_ecf(key=key, certificate=other)), READ, NOW)
    )
    assert (checks["subject_rnc"].state, checks["subject_rnc"].code) == (
        "failed",
        "subject_rnc_differs",
    )
    none = fake_certificate(key, rnc=None)
    checks = by_name(
        ecf_checks(read_ecf(signed_ecf(key=key, certificate=none)), READ, NOW)
    )
    assert checks["subject_rnc"].code == "no_subject_serial"


def test_the_read_is_compared_field_by_field_and_only_where_both_exist():
    document = read_ecf(signed_ecf())
    assert by_name(ecf_checks(document, None, NOW))["read_matches_xml"].code == "no_read"
    partial = ReceiptDetails(total="33254.91", rnc="131111223")
    check = by_name(ecf_checks(document, partial, NOW))["read_matches_xml"]
    assert (check.state, check.code, list(check.detail)) == (
        "failed",
        "read_differs",
        ["rnc"],
    )
    assert (
        by_name(ecf_checks(document, ReceiptDetails(merchant="x"), NOW))[
            "read_matches_xml"
        ].code
        == "no_read"
    )


def test_totals_that_do_not_add_up_fail_with_both_sides_named():
    off = FIXTURE.read_bytes().replace(
        b"<MontoPropinaLegal>2598.04</MontoPropinaLegal>",
        b"<MontoPropinaLegal>2598.00</MontoPropinaLegal>",
    )
    check = by_name(ecf_checks(read_ecf(off), None, NOW))["totals_arithmetic"]
    assert (check.state, check.code) == ("failed", "totals_mismatch")
    assert (check.detail["monto_total"], check.detail["sum_of_parts"]) == (
        "33254.91",
        "33254.87",
    )
    items_off = FIXTURE.read_bytes().replace(
        b"<MontoItem>1360.00</MontoItem>", b"<MontoItem>1300.00</MontoItem>"
    )
    assert (
        by_name(ecf_checks(read_ecf(items_off), None, NOW))["totals_arithmetic"].code
        == "items_mismatch"
    )


@pytest.mark.parametrize(
    "mutate,code",
    [
        (
            lambda s: s.replace(
                b"</ds:Signature>",
                b"</ds:Signature>" * 1
                + b'<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#"/>',
                1,
            ),
            "several_signatures",
        ),
        (
            lambda s: s.replace(
                b"<ds:X509Certificate>",
                b"<ds:X509Certificate>" + b"A" * (MAX_CERTIFICATE_CHARS + 8),
                1,
            ),
            "certificate_too_large",
        ),
        (lambda s: s.replace(b'URI=""', b'URI="#x"', 1), "reference_unsupported"),
        (
            lambda s: s.replace(b"xmldsig-more#rsa-sha256", b"xmldsig-more#rsa-md5", 1),
            "unsupported_algorithm",
        ),
    ],
)
def test_caps_and_unsupported_shapes_are_not_checked_rather_than_trusted(mutate, code):
    check = by_name(ecf_checks(read_ecf(mutate(signed_ecf())), READ, NOW))[
        "signature_integrity"
    ]
    assert (check.state, check.code) == ("not_checked", code)


def test_anything_but_an_ecf_reads_as_none():
    assert read_ecf(b"<Other><MontoTotal>1</MontoTotal></Other>") is None
    assert read_ecf(b"<!DOCTYPE x [<!ENTITY e 'x'>]><ECF/>") is None
    assert read_ecf(b"not xml") is None
    assert read_ecf(b"\xff\xfe<ECF/>") is None


def test_a_valid_signature_window_is_read_in_utc_against_the_declared_time():
    key = fake_key()
    edge = fake_certificate(
        key,
        not_before=datetime(2026, 10, 9, 14, 5, tzinfo=timezone.utc),
        not_after=datetime(2026, 10, 9, 14, 5, tzinfo=timezone.utc) + timedelta(days=1),
    )
    checks = by_name(
        ecf_checks(
            read_ecf(signed_ecf(key=key, certificate=edge, signed_at=SIGNED_AT)),
            READ,
            NOW,
        )
    )
    assert checks["certificate_validity"].detail["at_signature"] == "valid"
