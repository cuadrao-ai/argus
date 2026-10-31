from decimal import Decimal

import pytest
from argus.domain.business.contracts.invoicing import (
    CustomerInput,
    InvoiceDraft,
    InvoiceItem,
)
from argus.domain.business.invoicing.preparation import number, payload
from argus.domain.business.invoicing.store import InvoiceError
from argus.domain.business.invoicing.validation import amounts, draft_errors

from tests.fiscal import conftest as fiscal_fixtures

case_factory = fiscal_fixtures.case_factory


@pytest.fixture
def draft():
    return InvoiceDraft(
        customer_input=CustomerInput(name="Cliente de prueba", tax_id="131111222"),
        issued_on="2026-10-26",
        due_on="2026-11-25",
        payment_type="credit",
        income_type=1,
        tax_inclusion="excluded",
        terms="30 días",
        items=(
            InvoiceItem(
                id="stable-line",
                description="Servicio de prueba",
                quantity="3",
                price="10.01",
                tax="18",
                discount="0.03",
                classification="services",
                tax_treatment="taxable",
            ),
        ),
    )


def issuer(case):
    return {
        "name": case.payload["sender"]["companyName"],
        "country": "DO",
        "business_rnc": case.issuer,
        "business_provided_details": {"address": case.payload["sender"]["address"]},
    }


def test_partial_input_is_preserved_and_exact_discount_precedes_tax(draft):
    assert amounts(draft).model_dump() == {
        "subtotal": "30.03",
        "discount": "0.03",
        "tax": "5.40",
        "total": "35.40",
    }
    partial = InvoiceDraft(items=(InvoiceItem(id="line", price="unfinished"),))
    assert partial.items[0].price == "unfinished"
    assert amounts(partial) is None
    assert draft_errors(partial)["items.line.price"] == "decimal"


@pytest.mark.parametrize("kind", ["E31", "E32"])
def test_saved_lines_map_exactly_without_fixture_amounts_or_recipient_email(
    draft, case_factory, kind
):
    case = case_factory(kind=kind)
    data = draft.model_copy(update={"document_type": kind})
    result = payload(data, case, issuer(case))
    assert result["totals"]["totalAmount"] == 35.4
    assert result["itemDetails"][0]["itemAmount"] == 30
    assert result["itemDetails"][0]["subDiscounts"] == [
        {"subDiscountRate": "$", "subDiscountAmount": 0.03}
    ]
    assert "otherCurrency" not in result
    assert "mail" not in result["buyer"]
    assert result["idDoc"]["paymentDeadline"] == draft.due_on


@pytest.mark.parametrize(
    "change,field",
    [
        ({"currency": "USD"}, "currency"),
        ({"currency": "EUR"}, "currency"),
        ({"tax_inclusion": "included"}, "tax_inclusion"),
        ({"terms": "x" * 16}, "terms"),
        ({"instructions": "a" * 251}, "instructions"),
        ({"notes": "a" * 251}, "notes"),
    ],
)
def test_unsupported_input_remains_saved_but_preparation_refuses(
    draft, case_factory, change, field
):
    case = case_factory()
    changed = draft.model_copy(update=change)
    with pytest.raises(InvoiceError) as caught:
        payload(changed, case, issuer(case))
    assert field in caught.value.field_errors
    assert getattr(changed, field) == change[field]


def test_description_limit_does_not_truncate_and_jurisdiction_is_explicit(
    draft, case_factory
):
    case = case_factory()
    changed = draft.model_copy(
        update={"items": (draft.items[0].model_copy(update={"description": "x" * 81}),)}
    )
    with pytest.raises(InvoiceError) as caught:
        payload(changed, case, {**issuer(case), "country": "US"})
    assert caught.value.field_errors["items.stable-line.description"] == "provider_max_80"
    assert caught.value.field_errors["issuer.country"] == "jurisdiction"
    assert len(changed.items[0].description) == 81


def test_wire_numbers_preserve_decimal_value():
    for value in ("0.01", "9999999.99", "9999999990.01", "35.40"):
        assert Decimal(str(number(value))) == Decimal(value)


def test_notes_and_instructions_are_preserved_in_the_official_pdf_field(
    draft, case_factory
):
    case = case_factory()
    data = draft.model_copy(
        update={"notes": "Nota del cliente", "instructions": "Pagar por transferencia"}
    )
    result = payload(data, case, issuer(case))
    assert (
        result["config"]["pdf"]["note"] == "Nota del cliente\n\nPagar por transferencia"
    )
    assert "paymentAccountNumber" not in result["idDoc"]
    assert data.notes == "Nota del cliente"
    assert data.instructions == "Pagar por transferencia"


def test_unknown_and_included_tax_basis_do_not_invent_excluded_totals(draft):
    assert amounts(draft.model_copy(update={"tax_inclusion": None})) is None
    assert amounts(draft.model_copy(update={"tax_inclusion": "included"})) is None


def test_canonical_artifact_checks_reject_wrong_total_currency_and_customer(
    draft, case_factory
):
    from argus.domain.business.invoicing.artifacts import verify_pdf_text, verify_xml
    from lxml import etree

    allocation = case_factory()
    case = allocation.model_copy(
        update={"payload": payload(draft, allocation, issuer(allocation))}
    )
    text = f"{case.number}\n{case.issuer}\nDOP 35.40"
    verify_pdf_text(text, case)
    for wrong in (
        text.replace("35.40", "35.41"),
        text.replace("DOP", "USD"),
        text.replace(case.number, "E320000000001"),
    ):
        with pytest.raises(ValueError):
            verify_pdf_text(wrong, case)
    xml = b"<ECF><Encabezado><Comprador><RNCComprador>131111222</RNCComprador></Comprador><Totales><MontoTotal>35.40</MontoTotal></Totales></Encabezado></ECF>"
    verify_xml(etree.fromstring(xml), case)
    for wrong in (
        xml.replace(b"35.40", b"35.41"),
        xml.replace(b"131111222", b"131111223"),
        xml.replace(b"</Encabezado>", b"<OtraMoneda/></Encabezado>"),
    ):
        with pytest.raises(ValueError):
            verify_xml(etree.fromstring(wrong), case)


def test_editor_flag_is_default_off_and_only_declared_for_staging(monkeypatch):
    import json
    from pathlib import Path

    import yaml
    from argus.domain.business.invoicing.config import Settings

    name = "CUADRAO_BUSINESS_INVOICING_ENABLED"
    monkeypatch.delenv(name, raising=False)
    assert not Settings().enabled
    root = Path(__file__).resolve().parents[1]
    profile = json.loads(
        (root / ".github/private-alpha-release-profile.json").read_text()
    )
    assert name in profile["staging_only"]["api"]["settings"]
    services = {
        s["name"]: s
        for s in yaml.safe_load((root / "render.yaml").read_text())["services"]
    }
    assert name not in {e["key"] for e in services["cuadrao-api"]["envVars"]}
    assert {e["key"]: e.get("value") for e in services["cuadrao-api-staging"]["envVars"]}[
        name
    ] == "false"
    manifest = json.loads((root / "scripts/ops/staging_env_manifest.json").read_text())
    assert {e["name"]: e.get("value") for e in manifest["services"]["api"]["entries"]}[
        name
    ] == "false"


@pytest.mark.parametrize("currency", ["USD", "EUR"])
def test_non_dop_invoice_issue_is_refused_until_exchange_rate_exists(
    draft, case_factory, currency
):
    case = case_factory()
    with pytest.raises(InvoiceError) as caught:
        payload(draft.model_copy(update={"currency": currency}), case, issuer(case))
    assert caught.value.field_errors["currency"] == "foreign_currency_pending_rate"
