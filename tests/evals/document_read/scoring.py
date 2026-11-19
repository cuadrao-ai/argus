"""Runs the receipt reader over the set and scores what it returned, field by field.

The read goes through ``DocumentExtractor.prepare`` and ``.extract``, the same
path an upload takes. Only the provider call can be replaced, by a scripted
read, and then nothing leaves the process.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

from argus.domain.business.fiscal_identity import (
    identity_digits,
    printed_ncf,
    printed_rnc,
)
from argus.domain.ingestion.documents import extractor as reader
from argus.domain.ingestion.documents.config import DocumentExtractionSettings
from argus.domain.ingestion.documents.failures import ReadFailure
from argus.domain.ingestion.documents.models import (
    DocumentExtractionError,
    ExtractionBatch,
    ExtractionResult,
)
from argus.domain.ingestion.documents.preparation import (
    PreparedDocument,
    prepare_document,
)

from tests.evals.document_read.cases import Case, shapes
from tests.evals.document_read.dataset import Sample, set_sha256

SCHEMA_VERSION = "document_read_scorecard_v2"
#: The reader has no field for this yet, so there is nothing to score.
UNSUPPORTED = object()
OUTCOMES = (
    "correct",
    "correct_empty",
    "false_fill",
    "blank",
    "failed",
    "unsupported",
    "judgment",
    "not_scored",
)
#: The outcomes that put a receipt in a field's denominator.
SCORED = ("correct", "correct_empty", "false_fill", "blank", "failed")
#: The fields whose answer can be a judgment, with the key that says so.
BASIS = {"expense_type": "expense_type_basis"}
ScriptedRead = Callable[[Sample], ExtractionResult | Exception]
Prepared = dict[str, PreparedDocument | DocumentExtractionError]
_SETTINGS = DocumentExtractionSettings(enabled=True)


def _purchases(batch: ExtractionBatch) -> list[Any]:
    return [row for row in batch.observations if row.evidence == "transaction"]


def _money(value: str | None) -> str | None:
    if not value or not reader.plain_amount(value):
        return value or None
    return f"{Decimal(value):.2f}" if Decimal(value).as_tuple().exponent >= -2 else value


def _rnc(value: str | None) -> str | None:
    if not value:
        return None
    return identity_digits(printed_rnc(value)) or value


def _ncf(value: str | None) -> str | None:
    return printed_ncf(value).strip().upper() if value else None


def read_fields(batch: ExtractionBatch) -> dict[str, object]:
    """The reader's answer for each scored field. This is the one place that
    names where the reader keeps a value; a field it gains is mapped here."""

    receipt = batch.receipt
    purchases = _purchases(batch)
    purchase = purchases[0] if len(purchases) == 1 else None
    day = (purchase.occurred_on if purchase else None) or (
        receipt.occurred_on if receipt else None
    )
    total = (receipt.total if receipt else None) or (
        purchase.amount if purchase else None
    )
    return {
        "issue_date": day.isoformat() if day else None,
        "supplier_rnc": _rnc(receipt.rnc) if receipt else None,
        "buyer_rnc": UNSUPPORTED,
        "ncf": _ncf((receipt.ecf or receipt.ncf) if receipt else None),
        "total": _money(total),
        "itbis": _money(receipt.itbis if receipt else None),
        "payment_form": UNSUPPORTED,
        "expense_type": UNSUPPORTED,
    }


FIELDS = tuple(read_fields(ExtractionBatch(candidates=())))


def _outcome(expected: str | None, read: object, basis: str, answered: bool) -> str:
    if read is UNSUPPORTED:
        return "unsupported"
    if basis == "judgment":
        return "judgment"
    if not answered:
        return "failed"
    if read is None:
        return "correct_empty" if expected is None else "blank"
    return "correct" if read == expected else "false_fill"


def _swapped(day: date) -> str | None:
    try:
        return date(day.year, day.day, day.month).isoformat()
    except ValueError:
        return None


# A false fill with a known cause: (name, field, the wrong value that names it).
MISTAKES: tuple[tuple[str, str, Callable[[Case], str | None]], ...] = (
    (
        "expiry_as_issue_date",
        "issue_date",
        lambda case: case.expiry.isoformat() if case.expiry else None,
    ),
    (
        "signature_as_issue_date",
        "issue_date",
        lambda case: case.signed_on.isoformat(),
    ),
    ("day_month_swapped", "issue_date", lambda case: _swapped(case.issued)),
    ("buyer_rnc_as_supplier", "supplier_rnc", lambda case: case.buyer_rnc),
)


def _qr_outcome(sample: Sample, qr: Any) -> str:
    if sample.expected.purchases != 1:
        return "not_scored"
    if qr is None:
        return "missed" if sample.expected.dgii_qr_readable else "none_expected"
    if not sample.expected.dgii_qr_readable:
        return "unexpected"
    case = sample.case
    same = (
        qr.rnc_emisor == case.supplier_rnc
        and qr.encf == case.ncf
        and Decimal(qr.monto_total or "0") == case.total
        and qr.fecha_emision in (None, case.issued)
    )
    return "decoded" if same else "decoded_wrong"


def _record(
    sample: Sample, batch: ExtractionBatch | None, qr: Any, route_receipts: object
) -> dict[str, Any]:
    """One receipt's scores. ``batch`` is ``None`` when the model answered and
    the answer could not be used: the receipt stays in every denominator and
    nothing on it is correct."""

    case, answer = sample.case, asdict(sample.expected)
    one_receipt = sample.expected.purchases == 1
    answered = batch is not None
    batch = batch or ExtractionBatch(candidates=())
    fields: dict[str, dict[str, Any]] = {}
    mistakes: list[str] = []
    for name, read in read_fields(batch).items():
        basis = answer[BASIS[name]] if name in BASIS else "clear"
        outcome = (
            _outcome(answer[name], read, basis, answered) if one_receipt else "not_scored"
        )
        fields[name] = {
            "basis": basis,
            "outcome": outcome,
            "expected": answer[name],
            "read": None if read is UNSUPPORTED else read,
        }
        if outcome == "false_fill":
            mistakes.extend(
                mistake
                for mistake, field, wrong in MISTAKES
                if field == name and wrong(case) == read
            )
    issues = sorted({issue.code for issue in batch.issues})
    complete = (
        batch.readable is True
        and batch.complete is True
        and "incomplete_extraction" not in issues
    )
    purchases = len(_purchases(batch))
    return {
        "case_id": case.case_id,
        "status": "read" if answered else "model_failure",
        "shapes": list(shapes(case)),
        "fields": fields,
        "mistakes": mistakes,
        "qr": _qr_outcome(sample, qr),
        "complete": {
            "expected": sample.expected.complete,
            "read": complete if answered else None,
            "outcome": (
                "not_scored"
                if not one_receipt
                else "failed"
                if not answered
                else "correct"
                if complete == sample.expected.complete
                else "wrong"
            ),
        },
        "purchases": {
            "expected": sample.expected.purchases,
            "read": purchases if answered else None,
            "outcome": (
                "failed"
                if not answered
                else "correct"
                if purchases == sample.expected.purchases
                else "wrong"
            ),
        },
        "unsure": not complete or bool(issues),
        "issues": issues,
        "route_receipts": route_receipts,
    }


def score_case(sample: Sample, batch: ExtractionBatch) -> dict[str, Any]:
    return _record(sample, batch, batch.dgii_qr, batch.metadata.get("route_receipts", []))


def model_answered(error: DocumentExtractionError) -> bool:
    """Whether the read failed on the model's own answer. The extractor gives
    a kind (``failures.classify``) only to a provider call that was sent, and
    ``permanent`` is the kind of an answer that came back wrong: not the
    schema, cut short, or refused. A read that was never sent, a timeout, a
    dropped connection, a 5xx, a 429 and a refused key are not answers."""

    failure = getattr(error, "read_failure", None)
    return isinstance(failure, ReadFailure) and failure.kind == "permanent"


def _failed(
    sample: Sample,
    document: PreparedDocument | DocumentExtractionError,
    error: DocumentExtractionError,
) -> dict[str, Any]:
    route_receipts = error.metadata.get("route_receipts", [])
    response = getattr(error, "response", None)
    cause = {
        "error": error.code,
        "http_status": getattr(response, "status_code", None),
    }
    if isinstance(document, PreparedDocument) and model_answered(error):
        return {**_record(sample, None, document.dgii_qr, route_receipts), **cause}
    return {
        "case_id": sample.case.case_id,
        "status": "infrastructure_error",
        "shapes": list(shapes(sample.case)),
        **cause,
        "route_receipts": route_receipts,
    }


def prepare_set(samples: tuple[Sample, ...]) -> Prepared:
    """The local half of every read: the image rebuild and the QR decode. It
    costs nothing, so one prepared set serves any number of reads."""

    def prepare(sample: Sample) -> PreparedDocument | DocumentExtractionError:
        try:
            return prepare_document(sample.image, "image/jpeg", _SETTINGS)
        except DocumentExtractionError as error:
            return error

    with ThreadPoolExecutor(max_workers=8) as pool:
        documents = pool.map(prepare, samples)
        return {
            sample.case.case_id: document
            for sample, document in zip(samples, documents, strict=True)
        }


async def read_set(
    samples: tuple[Sample, ...],
    prepared: Prepared,
    *,
    scripted: ScriptedRead | None = None,
    stop: Callable[[list[dict[str, Any]]], bool] = lambda _: False,
    only: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Read each receipt once and score it. With ``scripted`` the provider call
    is replaced and no key is needed. ``stop`` is asked before every read."""

    extractor = reader.DocumentExtractor(_SETTINGS)
    offline = (
        (
            patch.object(reader, "resolve_openrouter_model", lambda **_: "scripted"),
            patch.object(reader, "resolve_openrouter_api_key", lambda _: "offline"),
        )
        if scripted
        else ()
    )
    for stub in offline:
        stub.start()
    results: list[dict[str, Any]] = []
    try:
        for sample in samples:
            if only and sample.case.case_id not in only:
                continue
            if stop(results):
                break
            document = prepared[sample.case.case_id]
            results.append(await _read(extractor, sample, document, scripted))
    finally:
        for stub in offline:
            stub.stop()
    return results


async def _read(
    extractor: reader.DocumentExtractor,
    sample: Sample,
    document: PreparedDocument | DocumentExtractionError,
    scripted: ScriptedRead | None,
) -> dict[str, Any]:
    async def extract() -> ExtractionBatch:
        return await extractor.extract(
            sample.image,
            f"{sample.case.case_id}.jpg",
            "image/jpeg",
            f"document-read-eval:{sample.case.case_id}",
            datetime.now(timezone.utc),
            prepared=document,
        )

    try:
        if isinstance(document, DocumentExtractionError):
            raise document
        if scripted is None:
            return score_case(sample, await extract())
        answer = scripted(sample)
        call = AsyncMock(
            **{"side_effect" if isinstance(answer, Exception) else "return_value": answer}
        )
        with patch.object(reader, "invoke_openrouter_json_schema", call):
            return score_case(sample, await extract())
    except DocumentExtractionError as error:
        return _failed(sample, document, error)


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _field_totals(scored_reads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    totals = {}
    for name in FIELDS:
        counts = Counter(result["fields"][name]["outcome"] for result in scored_reads)
        scored = sum(counts[outcome] for outcome in SCORED)
        totals[name] = {
            **{outcome: counts[outcome] for outcome in OUTCOMES},
            "scored": scored,
            "accuracy": _rate(counts["correct"] + counts["correct_empty"], scored),
            "false_fill_rate": _rate(counts["false_fill"], scored),
            "blank_rate": _rate(counts["blank"], scored),
            "failed_rate": _rate(counts["failed"], scored),
        }
    return totals


def _usage(results: list[dict[str, Any]]) -> dict[str, Any]:
    receipts = [receipt for result in results for receipt in result["route_receipts"]]
    costs = [receipt.get("usage_cost_usd") for receipt in receipts]
    known = [cost for cost in costs if isinstance(cost, (int, float))]
    return {
        "calls": len(receipts),
        "known_cost_usd": round(sum(known), 6),
        "unpriced_calls": len(costs) - len(known),
        "latency_ms": sum(receipt.get("latency_ms") or 0 for receipt in receipts),
    }


def known_cost_usd(results: list[dict[str, Any]]) -> float:
    return _usage(results)["known_cost_usd"]


def reader_text_sha256() -> dict[str, str]:
    """Digests of the text the model reads, so a scorecard names its prompt."""

    schema = json.dumps(ExtractionResult.model_json_schema(), sort_keys=True)
    return {
        "prompt_sha256": hashlib.sha256(reader._PROMPT.encode()).hexdigest(),
        "schema_sha256": hashlib.sha256(schema.encode()).hexdigest(),
    }


def build_scorecard(
    samples: tuple[Sample, ...],
    results: list[dict[str, Any]],
    *,
    tier: str,
    candidate_sha: str,
    model: str | None,
) -> dict[str, Any]:
    status = Counter(result["status"] for result in results)
    read = [result for result in results if result["status"] == "read"]
    # A model failure is a read that went wrong, so it is scored with the reads.
    scored = [result for result in results if result["status"] != "infrastructure_error"]
    not_run = len(samples) - len(results)
    qr = Counter(result["qr"] for result in scored)
    readable = qr["decoded"] + qr["decoded_wrong"] + qr["missed"]
    complete = Counter(result["complete"]["outcome"] for result in scored)
    purchases = Counter(result["purchases"]["outcome"] for result in scored)
    fields = _field_totals(scored)
    by_shape: dict[str, Counter[str]] = {}
    for result in scored:
        outcomes = Counter(field["outcome"] for field in result["fields"].values())
        for shape in result["shapes"]:
            by_shape.setdefault(shape, Counter()).update(outcomes, receipts=1)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "tier": tier,
            "candidate_sha": candidate_sha,
            "model": model,
            "set_sha256": set_sha256(samples),
            "set_receipts": len(samples),
            **reader_text_sha256(),
        },
        "provider_usage": _usage(results),
        "reliability": {
            "attempted": len(results),
            "read": len(read),
            "model_failure": status["model_failure"],
            "infrastructure_error": status["infrastructure_error"],
            "not_run": not_run,
            "success_rate": _rate(len(read), len(results)),
            # These receipts are in no rate, so the rates cover a subset.
            "incomplete": bool(status["infrastructure_error"] or not_run),
        },
        "fields": fields,
        "expense_type": {
            "clear": {
                name: fields["expense_type"][name]
                for name in (
                    "correct",
                    "false_fill",
                    "blank",
                    "failed",
                    "scored",
                    "accuracy",
                    "false_fill_rate",
                )
            },
            "judgment": [
                {
                    "case_id": result["case_id"],
                    "expected": result["fields"]["expense_type"]["expected"],
                    "read": result["fields"]["expense_type"]["read"],
                }
                for result in scored
                if result["fields"]["expense_type"]["basis"] == "judgment"
                and result["fields"]["expense_type"]["outcome"] != "not_scored"
            ],
        },
        "mistakes": dict(
            sorted(Counter(m for result in read for m in result["mistakes"]).items())
        ),
        "qr": {
            **{
                name: qr[name]
                for name in (
                    "decoded",
                    "decoded_wrong",
                    "missed",
                    "unexpected",
                    "none_expected",
                    "not_scored",
                )
            },
            "decode_rate": _rate(qr["decoded"], readable),
        },
        "complete": {
            "correct": complete["correct"],
            "wrong": complete["wrong"],
            "failed": complete["failed"],
            "not_scored": complete["not_scored"],
            "accuracy": _rate(
                complete["correct"],
                complete["correct"] + complete["wrong"] + complete["failed"],
            ),
        },
        "purchases": {
            "correct": purchases["correct"],
            "wrong": purchases["wrong"],
            "failed": purchases["failed"],
            "accuracy": _rate(purchases["correct"], len(scored)),
        },
        "unsure": {
            "receipts": sum(result["unsure"] for result in read),
            "rate": _rate(sum(result["unsure"] for result in read), len(read)),
            "issues": dict(
                sorted(Counter(i for result in read for i in result["issues"]).items())
            ),
        },
        "by_shape": {
            shape: dict(sorted(counts.items()))
            for shape, counts in sorted(by_shape.items())
        },
        "results": results,
    }


def summary_table(scorecard: dict[str, Any]) -> str:
    """The per-field table of a scorecard, as Markdown."""

    runs = scorecard["reliability"]
    rows = []
    if runs["incomplete"]:
        rows += [
            f"**INCOMPLETE RUN: {runs['infrastructure_error']} receipts got no "
            f"answer and {runs['not_run']} were not read. They are in no rate "
            "below. Do not compare this scorecard with another.**",
            "",
        ]
    rows += [
        f"Reads: {runs['read']} of {runs['attempted']} attempted came back usable. "
        f"{runs['model_failure']} model failures, scored as failed. "
        f"{runs['infrastructure_error']} infrastructure failures, not scored.",
        "",
        "| Field | Correct | Correctly empty | False fill | Blank | Failed "
        "| Unsupported | Judgment |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, counts in scorecard["fields"].items():
        rows.append(
            f"| {name} | {counts['correct']} | {counts['correct_empty']} | "
            f"{counts['false_fill']} | {counts['blank']} | {counts['failed']} | "
            f"{counts['unsupported']} | "
            f"{counts['judgment']} |"
        )
    qr, unsure = scorecard["qr"], scorecard["unsure"]
    complete, purchases = scorecard["complete"], scorecard["purchases"]
    clear, judged = (scorecard["expense_type"][name] for name in ("clear", "judgment"))
    rows.append("")
    rows.append(
        f"QR decoded {qr['decoded']} of {qr['decoded'] + qr['decoded_wrong'] + qr['missed']}"
        f" readable, {qr['unexpected']} unexpected. "
        f"Unsure {unsure['receipts']} of {runs['read']} read. "
        f"Named mistakes: {scorecard['mistakes'] or 'none'}."
    )
    rows.append(
        f"Purchase count right {purchases['correct']} of "
        f"{purchases['correct'] + purchases['wrong'] + purchases['failed']} scored. "
        f"Complete judgment right {complete['correct']} of "
        f"{complete['correct'] + complete['wrong'] + complete['failed']} scored."
    )
    rows.append(
        f"Tipo de gasto, clear answers: {clear['correct']} correct, "
        f"{clear['false_fill']} false fill, {clear['blank']} blank, "
        f"{clear['failed']} failed of "
        f"{clear['scored']} scored. {len(judged)} judgment receipts, not scored."
    )
    if judged:
        rows += ["", "| Judgment receipt | Expected | Read |", "| --- | --- | --- |"]
        rows += [
            f"| {row['case_id']} | {row['expected'] or '-'} | {row['read'] or '-'} |"
            for row in judged
        ]
    return "\n".join(rows)
