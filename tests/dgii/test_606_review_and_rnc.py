import io
import json
from dataclasses import replace
from datetime import date, datetime, timezone
from zipfile import ZipFile

import pytest
from argus.domain.business.contracts.dgii import PurchaseReview
from argus.domain.business.contracts.facts import BusinessFactPatch, Unknown
from argus.domain.business.dgii_line import reason
from argus.domain.business.purchase_review import apply_purchase
from argus.domain.business.rnc_registry import (
    DGII_RNC_LOOKUP,
    RncRecord,
    postgres_rnc_fetch,
    registry_from_config,
)
from pydantic import ValidationError

from tests.dgii.test_packet import packet, practice_records

FORM = "dgii/DGII_F_606_199990013_202609.TXT"
VALID = "138888002"
INVALID = "138888003"


class MapRegistry:
    def __init__(self, rows):
        self.rows = rows

    def lookup(self, number):
        return self.rows.get(number)


def listed(number, verification="verificado", status="ACTIVO"):
    return RncRecord(
        number,
        "FARMACIA CAROL",
        "FARMACIA",
        status,
        date(2026, 10, 17),
        verification,
    )


def supplier(record, number, id_type="1"):
    rnc = (
        Unknown()
        if number is None
        else record.facts.fiscal.rnc.model_copy(update={"value": number})
    )
    return replace(
        record,
        facts=record.facts.model_copy(
            update={"fiscal": record.facts.fiscal.model_copy(update={"rnc": rnc})}
        ),
        declaration=record.declaration.model_copy(update={"id_type": id_type}),
    )


def with_ncf(record, number):
    return replace(
        record,
        facts=record.facts.model_copy(
            update={
                "fiscal": record.facts.fiscal.model_copy(
                    update={
                        "ncf": record.facts.fiscal.ncf.model_copy(
                            update={"value": number}
                        )
                    }
                )
            }
        ),
    )


def one(record, registry=None):
    changes = {} if registry is None else {"registry": registry}
    return packet((record,), **changes)


def codes(result):
    return [issue["code"] for issue in result.manifest["issues"]]


def purchase():
    return practice_records()[0]


class TestHardRejects:
    def test_missing_or_wrong_length_id_refuses_the_606_file(self):
        record = supplier(with_ncf(purchase(), "B1100000045"), "1234567", None)
        result = one(record)
        assert "fiscal_identity_length" in codes(result)
        matched = next(
            issue
            for issue in result.manifest["issues"]
            if issue["code"] == "fiscal_identity_length"
        )
        assert matched["reason"] == reason("fiscal_identity_length")
        assert matched["reason_en"] == reason("fiscal_identity_length", "en")
        assert matched["activity_id"] == record.activity_id
        assert FORM not in result.files

    def test_a_bad_rnc_check_digit_blocks_the_606_when_the_registry_misses(self):
        record = supplier(purchase(), INVALID)
        result = one(record, MapRegistry({}))
        disposition = (
            "fiscal_identity_check_digit" in codes(result),
            any(
                item["code"] == "fiscal_identity_check_digit"
                for item in result.manifest["warnings"]
            ),
            FORM in result.files,
        )
        assert disposition == (True, False, False)
        matched = next(
            issue
            for issue in result.manifest["issues"]
            if issue["code"] == "fiscal_identity_check_digit"
        )
        assert matched["reason"] == (
            "El RNC debe tener 9 dígitos (empresa) u 11 (cédula). "
            "Revisa que esté bien escrito."
        )
        assert matched["reason_en"] == "The check digit does not match."
        assert matched["activity_id"] == record.activity_id
        assert matched["field"] == "rnc"
        assert result.manifest["forms"]["606"]["status"] == "needs_review"

    def test_id_type_does_not_match_the_number(self):
        result = one(supplier(purchase(), VALID, "2"))
        assert "fiscal_identity_type_mismatch" in codes(result)
        assert "fiscal_identity_length" not in codes(result)
        assert FORM not in result.files

    def test_malformed_ncf_refuses_the_file(self):
        result = one(with_ncf(purchase(), "NOT-AN-NCF"))
        assert "fiscal_ncf_malformed" in codes(result)
        assert FORM not in result.files

    def test_withholding_without_a_payment_date_refuses_the_file(self):
        record = replace(
            purchase(),
            declaration=purchase().declaration.model_copy(
                update={"itbis_withheld": "18.00", "paid_on": None}
            ),
        )
        result = one(record)
        assert "fiscal_withholding_payment_date_required" in codes(result)
        matched = next(
            issue
            for issue in result.manifest["issues"]
            if issue["code"] == "fiscal_withholding_payment_date_required"
        )
        assert (
            matched["reason"] == "Agrega la fecha de pago para registrar una retención."
        )
        assert FORM not in result.files

    def test_b01_without_an_rnc_refuses_the_file(self):
        result = one(supplier(purchase(), None))
        assert "fiscal_b01_rnc_required" in codes(result)
        assert FORM not in result.files


class TestRncWarnings:
    def test_unverified_is_listed_and_the_file_is_still_prepared(self):
        result = one(supplier(purchase(), VALID))
        warning = next(
            item
            for item in result.manifest["warnings"]
            if item["code"] == "rnc_unverified"
        )
        assert warning["line"] == purchase().activity_id
        assert warning["reason"] == "Todavía no lo hemos verificado con la DGII."
        assert warning["reason_en"] == "We have not verified it with the DGII yet."
        assert result.manifest["rnc_checks"][0]["status"] == "sin_verificar"
        assert result.manifest["issues"] == []
        assert FORM in result.files

    def test_verified_keeps_the_registered_name_and_does_not_block(self):
        registry = MapRegistry({VALID: listed(VALID)})
        result = one(supplier(purchase(), VALID), registry)
        assert result.manifest["rnc_checks"][0]["status"] == "verificado"
        assert result.manifest["rnc_checks"][0]["name"] == "FARMACIA CAROL"
        assert result.manifest["rnc_checks"][0]["estado"] == "ACTIVO"
        assert not any(
            item["code"] in {"rnc_unverified", "rnc_inactive"}
            for item in result.manifest["warnings"]
        )
        assert result.manifest["issues"] == []
        assert FORM in result.files

    def test_inactive_is_warn_only_and_exposes_the_raw_estado(self):
        registry = MapRegistry({VALID: listed(VALID, "no_activo", "SUSPENDIDO")})
        result = one(supplier(purchase(), VALID), registry)
        warning = next(
            item for item in result.manifest["warnings"] if item["code"] == "rnc_inactive"
        )
        assert warning["estado"] == "SUSPENDIDO"
        assert warning["file_date"] == "2026-10-17"
        assert warning["trade_name"] == "FARMACIA"
        assert "SUSPENDIDO" in warning["reason"]
        assert "17/10/2026" in warning["reason"]
        assert "SUSPENDIDO" in warning["reason_en"]
        assert result.manifest["issues"] == []
        assert FORM in result.files

    def test_missing_from_the_dgii_file_stays_unverified(self):
        registry = registry_from_config("dgii", lambda number: None)
        result = one(supplier(purchase(), VALID), registry)
        assert result.manifest["rnc_checks"][0]["status"] == "sin_verificar"
        assert any(
            item["code"] == "rnc_unverified" for item in result.manifest["warnings"]
        )
        assert result.manifest["issues"] == []
        assert FORM in result.files


class TestChecksumByRegistry:
    def test_valid_and_found_prepares_the_file(self):
        result = one(supplier(purchase(), VALID), MapRegistry({VALID: listed(VALID)}))
        assert "fiscal_identity_check_digit" not in codes(result)
        assert FORM in result.files

    def test_valid_and_not_found_prepares_the_file(self):
        result = one(supplier(purchase(), VALID), MapRegistry({}))
        assert "fiscal_identity_check_digit" not in codes(result)
        assert any(
            item["code"] == "rnc_unverified" for item in result.manifest["warnings"]
        )
        assert FORM in result.files

    def test_invalid_and_not_found_blocks_the_file(self):
        result = one(supplier(purchase(), INVALID), MapRegistry({}))
        assert "fiscal_identity_check_digit" in codes(result)
        assert not any(
            item["code"] == "fiscal_identity_check_digit"
            for item in result.manifest["warnings"]
        )
        assert FORM not in result.files

    def test_invalid_and_found_stays_in_the_file(self):
        result = one(
            supplier(purchase(), INVALID),
            MapRegistry({INVALID: listed(INVALID)}),
        )
        assert "fiscal_identity_check_digit" not in codes(result)
        assert not any(
            item["code"] == "fiscal_identity_check_digit"
            for item in result.manifest["warnings"]
        )
        assert result.manifest["issues"] == []
        assert FORM in result.files

    def test_both_lengths_block_a_miss_and_trust_a_listed_bad_digit(self):
        cases = (
            ("138888002", "138888003", "1"),
            ("10000000058", "10000000059", "2"),
        )
        for valid, invalid, id_type in cases:
            prepared = one(
                supplier(purchase(), valid, id_type),
                MapRegistry({}),
            )
            missed = one(
                supplier(purchase(), invalid, id_type),
                MapRegistry({}),
            )
            listed_bad = one(
                supplier(purchase(), invalid, id_type),
                MapRegistry({invalid: listed(invalid)}),
            )
            assert FORM in prepared.files
            assert "fiscal_identity_check_digit" not in codes(prepared)
            assert "fiscal_identity_check_digit" in codes(missed)
            assert not any(
                item["code"] == "fiscal_identity_check_digit"
                for item in missed.manifest["warnings"]
            )
            assert FORM not in missed.files
            assert missed.manifest["forms"]["606"]["status"] == "needs_review"
            assert "fiscal_identity_check_digit" not in codes(listed_bad)
            assert listed_bad.manifest["issues"] == []
            assert FORM in listed_bad.files

    def test_a_missing_rnc_blocks_the_606_without_a_check_digit_warning(self):
        result = one(supplier(purchase(), None))
        assert FORM not in result.files
        assert result.manifest["forms"]["606"]["status"] == "needs_review"
        assert "fiscal_identity_check_digit" not in codes(result)
        assert not any(
            item["code"] == "fiscal_identity_check_digit"
            for item in result.manifest["warnings"]
        )
        assert "fiscal_b01_rnc_required" in codes(result)


class TestReviewChecklist:
    def test_missing_expense_type_uses_the_approved_copy(self):
        record = replace(
            purchase(),
            declaration=purchase().declaration.model_copy(update={"category": None}),
        )
        result = one(record)
        warning = next(
            item
            for item in result.manifest["warnings"]
            if item["code"] == "expense_type_missing"
        )
        assert warning["reason"] == "Falta el tipo de gasto"
        assert warning["reason_en"] == "Expense type is missing"
        assert warning["line"] == record.activity_id
        assert "fiscal_fact_required" in codes(result)
        assert FORM not in result.files

    def test_missing_payment_method_uses_the_approved_copy(self):
        record = replace(
            purchase(),
            declaration=purchase().declaration.model_copy(
                update={"payment_method": None}
            ),
        )
        result = one(record)
        warning = next(
            item
            for item in result.manifest["warnings"]
            if item["code"] == "payment_method_missing"
        )
        assert warning["reason"] == "Falta la forma de pago"
        assert warning["reason_en"] == "Payment method is missing"
        assert FORM not in result.files

    def test_suggested_expense_type_stays_out_of_the_export_column(self):
        record = replace(
            purchase(),
            declaration=purchase().declaration.model_copy(
                update={"category": "09", "category_suggested": True}
            ),
        )
        result = one(record)
        assert any(
            item["reason"] == "Falta el tipo de gasto"
            for item in result.manifest["warnings"]
        )
        assert FORM not in result.files

    def test_confirmed_expense_type_is_written_in_the_606_column(self):
        record = replace(
            purchase(),
            declaration=purchase().declaration.model_copy(
                update={"category": "11", "category_suggested": False}
            ),
        )
        detail = one(record).files[FORM].decode("ascii").split("\r\n")[1].split("|")
        assert detail[2] == "11"

    def test_purchase_review_accepts_the_606_codes_and_stays_off_the_model_schema(self):
        schema = BusinessFactPatch.model_json_schema()
        assert "purchase" not in schema["properties"]
        patch = BusinessFactPatch.model_validate(
            {
                "purchase": {
                    "category": "03",
                    "category_suggested": True,
                    "payment_method": "04",
                }
            }
        )
        assert patch.purchase.category == "03"
        with pytest.raises(ValidationError):
            BusinessFactPatch.model_validate({"purchase": {"category": "99"}})

    def test_a_confirmed_service_type_fills_the_services_amount(self):
        declared = apply_purchase(None, PurchaseReview(category="02"), "1000.00")
        assert declared.services_amount == "1000.00"
        assert declared.goods_amount is None
        assert declared.category_suggested is False

    def test_a_suggested_type_does_not_fill_the_split(self):
        declared = apply_purchase(
            None, PurchaseReview(category="09", category_suggested=True), "1000.00"
        )
        assert declared.category == "09"
        assert declared.category_suggested is True
        assert declared.goods_amount is None
        assert declared.services_amount is None

    def test_a_confirmed_type_fills_the_base_after_taxes_and_keeps_cents(self):
        current = purchase().declaration.model_copy(
            update={
                "category": None,
                "services_amount": None,
                "goods_amount": None,
                "selective_tax": "1.10",
                "other_taxes": "2.20",
                "legal_tip": "0.25",
            }
        )
        declared = apply_purchase(
            current,
            PurchaseReview(
                category="09",
                payment_method="04",
                paid_on=date(2026, 9, 3),
                itbis_withheld="18.40",
                income_withholding_type="02",
                income_withheld="10.15",
            ),
            "1180.55",
            "180.10",
        )
        assert declared.goods_amount == "996.90"
        assert declared.services_amount is None
        assert declared.payment_method == "04"
        assert declared.paid_on == date(2026, 9, 3)
        assert declared.itbis_withheld == "18.40"
        assert declared.income_withholding_type == "02"
        assert declared.income_withheld == "10.15"


def test_the_archive_keeps_the_606_for_a_listed_bad_check_digit():
    from argus.domain.business.export import ExportPeriod, ExportSnapshot, build_archive

    record = supplier(purchase(), INVALID)
    snapshot = ExportSnapshot(
        ExportPeriod(date(2026, 9, 1), date(2026, 9, 30)),
        (),
        (),
        (),
        datetime(2026, 10, 18, tzinfo=timezone.utc),
        (record,),
        "199990013",
        "Taller Ensayo",
    )
    blob = build_archive(
        snapshot, lambda _: None, MapRegistry({INVALID: listed(INVALID)})
    )
    with ZipFile(io.BytesIO(blob)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files["manifest.json"])["dgii"]
    assert not any(
        item["code"] == "fiscal_identity_check_digit" for item in manifest["warnings"]
    )
    assert "fiscal_identity_check_digit" not in {
        item["code"] for item in manifest["issues"]
    }
    assert manifest["forms"]["606"]["status"] == "prepared_candidate"
    assert FORM in files


class TestRncRegistry:
    def test_the_default_config_finds_nothing(self):
        assert registry_from_config("unknown").lookup(VALID) is None

    def test_dgii_config_reads_the_fake_lookup(self):
        def fetch(number):
            return {
                "rnc": number,
                "name": "ACME",
                "trade_name": "ACME SRL",
                "status": "SUSPENDIDO",
                "file_date": "2026-10-17",
                "verification": "no_activo",
            }

        found = registry_from_config("dgii", fetch).lookup(VALID)
        assert found.status == "SUSPENDIDO"
        assert found.trade_name == "ACME SRL"
        assert found.file_date == date(2026, 10, 17)
        assert found.verification == "no_activo"

    def test_the_postgres_fetch_calls_dgii_rnc_lookup(self):
        seen = []

        def execute(sql, params):
            seen.append((sql, params))
            return None

        assert postgres_rnc_fetch(execute)(VALID) is None
        assert seen == [(DGII_RNC_LOOKUP, (VALID,))]
