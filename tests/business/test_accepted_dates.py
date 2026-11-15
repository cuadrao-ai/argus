"""Fresh Business inputs share one date boundary; saved evidence stays readable."""

from datetime import date, datetime, timezone

import pytest
from argus.api.business_month_close_schemas import SettlementUpdate
from argus.domain.business.contracts.actions import ReviewDraft, TypedPurchase
from argus.domain.business.contracts.dgii import PurchaseReview
from argus.domain.business.contracts.facts import BusinessFactPatch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def dominican_today(freeze_new_york_clock):
    # The UTC day has already changed, but it is still November 15 in the DR.
    freeze_new_york_clock(datetime(2026, 11, 16, 2, tzinfo=timezone.utc))


def past_inputs(day):
    return [
        (BusinessFactPatch, {"occurred_on": {"state": "known", "value": day}}),
        (TypedPurchase, {"amount": "10", "occurred_on": day}),
        (PurchaseReview, {"paid_on": day}),
        (SettlementUpdate, {"status": "pagado", "settled_on": day, "payment_method": "efectivo"}),
    ]


@pytest.mark.parametrize("day,code", [
    ("2016-11-14", "business_date_before_minimum"),
    ("2026-11-16", "business_date_after_today"),
    ("0026-10-05", "business_date_before_minimum"),
])
def test_past_input_refusals(day, code):
    for model, payload in past_inputs(day):
        with pytest.raises(ValidationError) as raised:
            model.model_validate(payload)
        error = raised.value.errors()[0]
        assert error["type"] == code
        assert error["ctx"]["min_date"] == "2016-11-15"
        assert error["ctx"]["today"] == "2026-11-15"


@pytest.mark.parametrize("day", ["2016-11-15", "2026-11-15"])
def test_past_input_inclusive_edges(day):
    for model, payload in past_inputs(day):
        assert model.model_validate(payload)


@pytest.mark.parametrize("day,accepted", [
    ("2016-11-14", False), ("2016-11-15", True),
    ("2026-11-15", True), ("2026-11-16", True), ("9999-12-31", True),
])
def test_due_input_floor_without_ceiling(day, accepted):
    payload = {"version": 1, "due_on": {"state": "known", "value": day}}
    if accepted:
        assert ReviewDraft.model_validate(payload).due_on.value == date.fromisoformat(day)
    else:
        with pytest.raises(ValidationError) as raised:
            ReviewDraft.model_validate(payload)
        assert raised.value.errors()[0]["type"] == "business_date_before_minimum"


@pytest.mark.parametrize("field", ["occurred_on", "due_on"])
@pytest.mark.parametrize("day", ["2016-11-14", "2016-11-15", "2026-11-15", "2026-11-16"])
def test_review_request_boundary(field, day):
    app = FastAPI()

    @app.post("/review")
    def review(body: ReviewDraft):
        return body

    fact = {"state": "known", "value": day}
    payload = {"version": 1, **({"facts": {field: fact}} if field == "occurred_on" else {field: fact})}
    response = TestClient(app).post("/review", json=payload)
    refused = day < "2016-11-15" or (field == "occurred_on" and day > "2026-11-15")
    assert response.status_code == (422 if refused else 200)
    if refused:
        error = response.json()["detail"][0]
        assert error["type"] == ("business_date_before_minimum" if day < "2016-11-15" else "business_date_after_today")
        assert error["ctx"]["min_date"] == "2016-11-15"


def test_reader_date_is_evidence_and_a_correction_reason():
    from uuid import uuid4

    from argus.domain.business.contracts.facts import BusinessFacts, Known
    from argus.domain.business.fact_blockers import blockers

    facts = BusinessFacts(occurred_on=Known(value=date(26, 10, 5), origin="extracted", source_ids=(uuid4(),)))
    reason = next((item for item in blockers(facts, ()) if item.code == "business_date_before_minimum"), None)
    assert reason is not None
    assert reason.field == "occurred_on"
    assert reason.min_date == "2016-11-15"
    assert facts.occurred_on.value == date(26, 10, 5)


def test_bank_import_refuses_an_old_date_with_the_server_minimum():
    from argus.domain.business.bank.model import BankMatchingError
    from argus.domain.business.bank.readers import SandboxCsvReader

    with pytest.raises(BankMatchingError) as raised:
        SandboxCsvReader().read(b"date,name,amount,iso_currency_code,pending\n0026-10-05,test,-10,DOP,false\n", None)
    assert raised.value.code == "business_date_before_minimum"
    assert raised.value.context["min_date"] == "2016-11-15"


@pytest.mark.parametrize("day,code", [("2016-11-14", "business_date_before_minimum"), ("2026-11-16", "business_date_after_today")])
@pytest.mark.parametrize("form,field", [("606", "paid_on"), ("607", "withheld_on")])
def test_fiscal_review_boundary_and_saved_declarations(day, code, form, field):
    from argus.domain.business.contracts.dgii import (
        FiscalReview,
        PurchaseDeclaration,
        SalesDeclaration,
    )

    model = PurchaseDeclaration if form == "606" else SalesDeclaration
    declaration = {name: None for name, info in model.model_fields.items() if info.is_required()}
    declaration.update(form=form, **{field: day})
    assert model.model_validate(declaration)  # Old evidence is still readable.
    with pytest.raises(ValidationError) as raised:
        FiscalReview.model_validate({"fiscal": {"rnc": None, "ncf": None, "itbis": None}, "declaration": declaration})
    assert raised.value.errors()[0]["type"] == code
    assert field in raised.value.errors()[0]["loc"]


def test_leap_day_floor_clamps_to_february_28(freeze_new_york_clock):
    from argus.domain.business.accepted_dates import PastBusinessDate
    from pydantic import TypeAdapter

    freeze_new_york_clock(datetime(2024, 2, 29, 12, tzinfo=timezone.utc))
    adapter = TypeAdapter(PastBusinessDate)
    assert adapter.validate_python("2014-02-28") == date(2014, 2, 28)
    with pytest.raises(ValidationError) as raised:
        adapter.validate_python("2014-02-27")
    assert raised.value.errors()[0]["ctx"]["min_date"] == "2014-02-28"


def test_invoice_write_dates_are_checked_without_rejecting_stored_evidence():
    from argus.domain.business.contracts.invoicing import InvoiceDraft, InvoiceWrite

    saved = InvoiceDraft(issued_on="0026-10-05", due_on="0026-10-10")
    with pytest.raises(ValidationError) as raised:
        InvoiceWrite(data=saved)
    assert raised.value.errors()[0]["type"] == "business_date_before_minimum"


def test_bank_api_refusal_keeps_context():
    from argus.api.routers.business_bank import bank_problem
    from argus.domain.business.bank.model import BankMatchingError
    from starlette.requests import Request

    request = Request({"type": "http", "method": "POST", "path": "/api/v1/business/bank/imports", "headers": [], "state": {"request_id": "date-test"}})
    response = bank_problem(request, BankMatchingError("business_date_before_minimum", {"field": "occurred_on", "min_date": "2016-11-15"}))
    assert response.status_code == 422
    assert response.detail["code"] == "business_date_before_minimum"
    assert response.detail["context"]["min_date"] == "2016-11-15"


def test_fiscal_review_revalidates_a_stored_model_instance():
    from argus.domain.business.contracts.dgii import FiscalInput, FiscalReview
    from argus.domain.business.purchase_review import apply_purchase

    declaration = apply_purchase(None, PurchaseReview(paid_on="2026-11-15"))
    assert FiscalReview(fiscal=FiscalInput(rnc=None, ncf=None, itbis=None), declaration=declaration).declaration.paid_on == date(2026, 11, 15)


@pytest.mark.parametrize("field", ["paid_on", "withheld_on", "settled_on", "issued_on", "due_on"])
@pytest.mark.parametrize("day", ["2016-11-14", "2016-11-15", "2026-11-15", "2026-11-16"])
def test_date_inputs_keep_the_problem_envelope_at_every_http_edge(field, day):
    from argus.api.app_setup import validation_exception_handler
    from argus.domain.business.contracts.dgii import FiscalReview, SalesDeclaration
    from argus.domain.business.contracts.invoicing import InvoiceWrite
    from fastapi.exceptions import RequestValidationError

    if field == "paid_on":
        model, payload = PurchaseReview, {field: day}
    elif field == "withheld_on":
        declaration = {name: None for name, info in SalesDeclaration.model_fields.items() if info.is_required()}
        declaration.update(form="607", withheld_on=day)
        model, payload = FiscalReview, {"fiscal": {"rnc": None, "ncf": None, "itbis": None}, "declaration": declaration}
    elif field == "settled_on":
        model, payload = SettlementUpdate, {"status": "pagado", "payment_method": "efectivo", field: day}
    else:
        model, payload = InvoiceWrite, {"data": {field: day}}
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    def accept(body):
        return body

    accept.__annotations__["body"] = model
    app.post("/date")(accept)
    response = TestClient(app).post("/date", json=payload)
    refused = day < "2016-11-15" or (field != "due_on" and day > "2026-11-15")
    assert response.status_code == (422 if refused else 200)
    if refused:
        problem = response.json()
        assert problem["code"] == "validation_error"
        error = problem["context"]["errors"][0]
        assert error["type"] == ("business_date_before_minimum" if day < "2016-11-15" else "business_date_after_today")
        assert field in error["loc"]
        assert error["ctx"]["min_date"] == "2016-11-15"
