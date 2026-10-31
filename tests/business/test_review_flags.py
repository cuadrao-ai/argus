from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.business.contracts.facts import BusinessFacts, FiscalFacts, Known
from argus.domain.business.dgii_line import reason
from argus.domain.business.month_close import summarize
from argus.domain.business.review_flags import review_flags, unconfirmed

from tests.business.test_month_close import DAY, document

SOURCE = (uuid4(),)


def known(value):
    return Known(value=value, origin="extracted", source_ids=SOURCE)


def facts(amount="1180", currency="DOP", **fiscal) -> BusinessFacts:
    values = {"rnc": "199990021", "ncf": "B0100000001", "itbis": "180"} | fiscal
    return BusinessFacts(
        amount=known(amount),
        currency=known(currency),
        fiscal=FiscalFacts(
            **{name: known(value) for name, value in values.items() if value is not None}
        ),
    )


def codes(view: BusinessFacts) -> list[str]:
    return [flag.code for flag in review_flags(view)]


class TestRncCheckDigit:
    def test_a_wrong_check_digit_is_flagged_and_needs_confirmation(self):
        flagged = review_flags(facts(rnc="199990022"))
        assert [flag.code for flag in flagged] == ["rnc_check_digit"]
        assert unconfirmed(flagged) == ("rnc_check_digit",)

    def test_a_corrected_rnc_clears_the_flag(self):
        assert codes(facts(rnc="199990021")) == []
        assert codes(facts(rnc="1-99-99002-1")) == []

    def test_a_cedula_is_checked_by_its_own_digit(self):
        assert codes(facts(rnc="00113918205")) == []
        assert codes(facts(rnc="00113918204")) == ["rnc_check_digit"]

    def test_a_length_the_export_already_refuses_is_not_a_check_digit_flag(self):
        assert codes(facts(rnc="12345")) == []


class TestNcfFormat:
    @pytest.mark.parametrize("ncf", ["B01000008", "B010000008", "B0100000001X"])
    def test_a_malformed_ncf_is_flagged_and_kept_as_read(self, ncf):
        view = facts(ncf=ncf)
        assert codes(view) == ["ncf_malformed"]
        assert view.fiscal.ncf.value == ncf

    @pytest.mark.parametrize("ncf", ["B0100000001", "b0100000001", " B0100000001 "])
    def test_a_b_series_ncf_clears_the_flag(self, ncf):
        assert codes(facts(ncf=ncf)) == []

    def test_an_e_cf_needs_twelve_digits(self):
        assert codes(facts(ncf=None, ecf="E310000000001")) == []
        assert codes(facts(ncf=None, ecf="E31000000001")) == ["ncf_malformed"]

    def test_no_ncf_is_not_a_format_flag(self):
        assert codes(facts(ncf=None)) == []


class TestItbisRate:
    def test_exactly_at_the_tolerance_is_not_flagged(self):
        assert codes(facts(amount="1181.00", itbis="181.00")) == []

    def test_one_cent_over_the_tolerance_is_flagged_and_only_warns(self):
        flagged = review_flags(facts(amount="1181.01", itbis="181.01"))
        assert [flag.code for flag in flagged] == ["itbis_high"]
        assert unconfirmed(flagged) == ()

    def test_a_low_itbis_is_not_flagged(self):
        assert codes(facts(amount="1160", itbis="160")) == []
        assert codes(facts(amount="1000", itbis="0")) == []

    def test_a_usd_receipt_uses_one_dollar_of_tolerance(self):
        assert codes(facts(amount="119.00", currency="USD", itbis="19.00")) == []
        assert codes(facts(amount="119.01", currency="USD", itbis="19.01")) == [
            "itbis_high"
        ]

    def test_cents_are_compared_exactly_not_as_floats(self):
        assert codes(facts(amount="0.3", itbis="0.1")) == []
        assert codes(facts(amount="1.1", itbis="1.01")) == []
        assert codes(facts(amount="1.1", itbis="1.02")) == ["itbis_high"]


class TestCopy:
    def test_each_flag_reads_the_approved_spanish(self):
        assert reason("rnc_check_digit") == (
            "El dígito verificador del RNC no coincide. Revisa que esté bien escrito."
        )
        assert reason("ncf_malformed") == (
            "El NCF no tiene el formato correcto. Debe ser B más 10 dígitos, o E"
            " más 12 si es e-CF. Revisa lo que dice el comprobante."
        )
        assert reason("itbis_high") == (
            "El ITBIS parece alto para este total. Revisa los montos."
        )
        assert reason("duplicate_comprobante") == "Ya registraste este comprobante."
        assert reason("duplicate_comprobante_action") == "Ver el registrado"


class TestMonthClose:
    def test_a_malformed_ncf_is_listed_apart_from_a_missing_one(self):
        summary = summarize(
            [
                document(activity_id="malformed", ncf="B01000008"),
                document(activity_id="missing", ncf=None),
            ],
            DAY.replace(day=1),
            DAY,
        )
        assert [line["activity_id"] for line in summary["ncf_malformed"]] == ["malformed"]
        assert [line["activity_id"] for line in summary["missing_ncf"]] == [
            "malformed",
            "missing",
        ]
