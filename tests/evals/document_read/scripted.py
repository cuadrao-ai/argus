"""Scripted reads for the mocked tier. They stand in for the provider call so
the harness can be proven without a model. They say nothing about a real read."""

from __future__ import annotations

import httpx
from argus.domain.ingestion.documents.models import ExtractionResult
from pydantic import ValidationError

from tests.evals.document_read.cases import Case
from tests.evals.document_read.dataset import Sample


def _result(
    sample: Sample,
    *,
    issue_date: str | None,
    rnc: str | None,
    itbis: str | None,
    complete: bool,
    companion: bool = True,
) -> ExtractionResult:
    case, answer = sample.case, sample.expected
    receipts: list[tuple[Case, str | None]] = [(case, issue_date)]
    if case.companion and companion:
        receipts.append((case.companion, case.companion.issued.isoformat()))
    electronic = case.ncf_series.startswith("E")
    return ExtractionResult.model_validate(
        {
            "complete": complete,
            "readable": True,
            "pages_read": [1],
            "observations": [
                {
                    "page": 1,
                    "row": row,
                    "evidence": "transaction",
                    "amount": f"{receipt.total:.2f}" if answer.total else None,
                    "currency": "DOP",
                    "direction": "outflow",
                    "occurred_on": day,
                }
                for row, (receipt, day) in enumerate(receipts, 1)
            ],
            "receipt": {
                "occurred_on": issue_date,
                "currency": "DOP",
                "total": answer.total,
                "rnc": rnc,
                "ecf": answer.ncf if electronic else None,
                "ncf": None if electronic else answer.ncf,
                "itbis": itbis,
            },
        }
    )


def faithful(sample: Sample) -> ExtractionResult:
    """Every field the reader has, exactly as the photo shows it."""

    answer = sample.expected
    return _result(
        sample,
        issue_date=answer.issue_date,
        rnc=answer.supplier_rnc,
        itbis=answer.itbis,
        complete=answer.complete,
    )


def first_receipt_only(sample: Sample) -> ExtractionResult:
    """A faithful read that stops after the first receipt in the photo."""

    answer = sample.expected
    return _result(
        sample,
        issue_date=answer.issue_date,
        rnc=answer.supplier_rnc,
        itbis=answer.itbis,
        complete=answer.complete,
        companion=False,
    )


def careless(sample: Sample) -> ExtractionResult:
    """The mistakes the set is built to catch: the expiry taken as the issue
    date, the buyer RNC taken as the supplier, a tax line named "Impuesto"
    left empty, and a cut-off receipt called complete."""

    case, answer = sample.case, sample.expected
    expiry = case.expiry.isoformat() if case.expiry else None
    buyer = case.buyer_rnc if case.buyer_rnc_label else None
    return _result(
        sample,
        issue_date=answer.issue_date or expiry,
        rnc=answer.supplier_rnc or buyer,
        itbis=answer.itbis if case.tax == "itbis" else None,
        complete=True,
    )


def empty(sample: Sample) -> ExtractionResult:
    """A readable receipt with nothing filled in."""

    return ExtractionResult(
        complete=True, readable=True, pages_read=(1,), observations=()
    )


def outage(sample: Sample) -> Exception:
    """The provider never answered: the connection failed."""

    return httpx.ConnectError("scripted provider outage")


def unparseable(sample: Sample) -> Exception:
    """The model answered with text that is not the schema, as the provider
    call raises it."""

    try:
        ExtractionResult.model_validate_json('{"complete": tr')
    except ValidationError as error:
        return error
    raise AssertionError("the cut answer parsed")


def cut_off(sample: Sample) -> Exception:
    """The model ran out of output before it finished, as the provider call
    raises it."""

    return ValueError("Incomplete document response")
