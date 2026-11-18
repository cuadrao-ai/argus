"""Mocked tier of the receipt-read eval: no model call, no key, no network."""

from __future__ import annotations

import asyncio
import io
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import fields
from typing import Any

import pytest
from argus.domain.business.dgii_codes import EXPENSE_TYPES, PAYMENT_FORMS
from argus.domain.business.fiscal_identity import rnc_check_digit_ok
from PIL import Image

from tests.evals.document_read import run_live, scripted
from tests.evals.document_read.cases import (
    MONTHS_ABBR,
    PAYMENTS,
    TRADES,
    Expected,
    coverage,
    hard_pair_counts,
)
from tests.evals.document_read.dataset import Sample, build_set, write_set
from tests.evals.document_read.render import LONG_SIDE, render
from tests.evals.document_read.scoring import (
    FIELDS,
    SCHEMA_VERSION,
    Prepared,
    ScriptedRead,
    build_scorecard,
    prepare_set,
    read_set,
)

UNREAD_TODAY = ("buyer_rnc", "payment_form", "expense_type")
READ_TODAY = tuple(name for name in FIELDS if name not in UNREAD_TODAY)
REQUIRED_SHAPES = (
    "collage of pieces",
    "several receipts in one photo",
    "totals out of frame",
    "no issue date printed",
    "date label Fecha",
    "date label Emitido",
    "date label Fecha Emisión",
    "expiry line Caduca",
    "expiry line Válido hasta",
    "2-digit year",
    "4-digit year",
    "ambiguous day/month/year order",
    "issue date near the QR",
    "tax line ITBIS",
    "tax line Impuesto",
    "tax line Impuesto 0.00",
    "no tax line",
    "supplier and buyer RNC",
    "buyer RNC only",
    "smudged supplier RNC",
    "e-NCF",
    "paper NCF",
    "DGII QR in frame",
    "DGII QR partly out of frame",
    "second QR, not DGII",
    "finger over the payment line",
    "handwritten note",
    "shadow",
    "angled",
    "forma de pago: none",
    "tipo de gasto: none",
)


@pytest.fixture(scope="module")
def samples() -> tuple[Sample, ...]:
    return build_set()


@pytest.fixture(scope="module")
def prepared(samples: tuple[Sample, ...]) -> Prepared:
    return prepare_set(samples)


@pytest.fixture(scope="module")
def scorecard(
    samples: tuple[Sample, ...], prepared: Prepared
) -> Callable[..., dict[str, Any]]:
    def run(read: ScriptedRead, **limits: Any) -> dict[str, Any]:
        results = asyncio.run(read_set(samples, prepared, scripted=read, **limits))
        return build_scorecard(
            samples, results, tier="mocked", candidate_sha="mocked", model="scripted"
        )

    return run


def scored(samples: tuple[Sample, ...]) -> list[Sample]:
    return [sample for sample in samples if sample.expected.purchases == 1]


def test_set_is_synthetic_small_and_phone_sized(samples: tuple[Sample, ...]) -> None:
    assert 35 <= len(samples) <= 50
    assert len({sample.case.case_id for sample in samples}) == len(samples)
    for sample in samples:
        case = sample.case
        for rnc in (case.supplier_rnc, case.buyer_rnc):
            assert rnc.startswith("9") and rnc_check_digit_ok(rnc)
        with Image.open(io.BytesIO(sample.image)) as photo:
            assert photo.format == "JPEG"
            assert max(photo.size) <= LONG_SIDE
        assert len(sample.image) < 1024 * 1024


def test_a_case_always_renders_the_same_photo(samples: tuple[Sample, ...]) -> None:
    for sample in samples[:3]:
        assert render(sample.case) == sample.image


def test_codes_come_from_the_dgii_tables() -> None:
    assert {code for _, code in PAYMENTS.values() if code} <= set(PAYMENT_FORMS)
    assert {t.expense_type for t in TRADES.values() if t.expense_type} <= set(
        EXPENSE_TYPES
    )


def test_issue_dates_cover_every_month_in_several_years(
    samples: tuple[Sample, ...],
) -> None:
    printed = [s.case for s in samples if s.case.date_label]
    months = Counter(case.issued.month for case in printed)
    assert set(months) == set(range(1, 13))
    assert max(months.values()) <= len(printed) // 5
    assert len({case.issued.year for case in printed}) >= 3
    named = [case for case in printed if case.date_style.month != "number"]
    assert {case.issued.month for case in named} == set(range(1, 13))
    spellings = {case.date_style.render(case.issued) for case in named}
    assert any("SEPT" in text for text in spellings)
    assert {case.date_style.casing for case in named} == {"upper", "lower", "title"}
    assert sum(case.date_style.month == "full" for case in named) >= 3
    assert all(any(name in text.lower() for text in spellings) for name in MONTHS_ABBR)


def test_set_covers_every_required_shape(samples: tuple[Sample, ...]) -> None:
    counts = coverage(tuple(sample.case for sample in samples))
    assert [shape for shape in REQUIRED_SHAPES if not counts.get(shape)] == []


def test_each_hard_pair_has_three_receipts_per_side(
    samples: tuple[Sample, ...],
) -> None:
    pairs = hard_pair_counts(tuple(sample.case for sample in samples))
    assert len(pairs) == 3
    assert all(min(sides) >= 3 for sides in pairs.values()), pairs


@pytest.mark.parametrize(
    ("case_id", "answers"),
    [
        ("no-date-valido-hasta", {"issue_date": None, "dgii_qr_readable": True}),
        ("fecha-2-digit-year", {"issue_date": "2026-11-04", "payment_form": "03"}),
        ("ambiguous-10-11-12", {"issue_date": "2012-11-10", "itbis": None}),
        ("month-SEPT", {"issue_date": "2024-09-09", "expense_type": "03"}),
        ("buyer-rnc-only", {"supplier_rnc": None, "expense_type": "05"}),
        ("smudged-supplier-rnc", {"supplier_rnc": None, "expense_type": None}),
        ("impuesto-zero", {"itbis": "0.00", "payment_form": "01"}),
        ("finger-over-payment", {"payment_form": None, "complete": True}),
        ("credit-terms-30-dias", {"payment_form": "04", "expense_type": "10"}),
        ("no-payment-line", {"payment_form": None, "expense_type": "11"}),
        ("no-date-caduca-qr-cut", {"dgii_qr_readable": False, "complete": True}),
        (
            "totals-out-of-frame",
            {"total": None, "itbis": None, "payment_form": None, "complete": False},
        ),
        ("two-receipts-one-photo", {"purchases": 2}),
    ],
)
def test_expected_answers(
    samples: tuple[Sample, ...], case_id: str, answers: dict[str, object]
) -> None:
    sample = next(s for s in samples if s.case.case_id == case_id)
    assert {name: getattr(sample.expected, name) for name in answers} == answers


def test_every_photo_gets_an_answer_file(samples: tuple[Sample, ...], tmp_path) -> None:
    write_set(samples, tmp_path)
    assert len(list(tmp_path.glob("*.jpg"))) == len(samples)
    for sample in samples:
        answer = json.loads(
            (tmp_path / f"{sample.case.case_id}.expected.json").read_text()
        )
        assert set(answer["expected"]) == {field.name for field in fields(Expected)}


def test_qr_decode_is_measured_on_the_real_decoder(
    samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    qr = scorecard(scripted.empty)["qr"]
    one = scored(samples)
    readable = sum(sample.expected.dgii_qr_readable for sample in one)
    assert qr["decoded"] == readable
    assert qr["none_expected"] == len(one) - readable
    assert qr["not_scored"] == len(samples) - len(one)
    assert (qr["missed"], qr["decoded_wrong"], qr["unexpected"]) == (0, 0, 0)
    assert qr["decode_rate"] == 1.0


def test_a_faithful_read_scores_clean(
    samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    card = scorecard(scripted.faithful)
    one = scored(samples)
    for name in READ_TODAY:
        counts = card["fields"][name]
        assert (counts["false_fill"], counts["blank"]) == (0, 0), name
        assert counts["correct"] + counts["correct_empty"] == len(one)
        assert counts["not_scored"] == len(samples) - len(one)
        assert counts["correct_empty"] == sum(
            getattr(sample.expected, name) is None for sample in one
        )
    assert card["mistakes"] == {}
    assert card["complete"] == {"correct": len(one), "wrong": 0, "accuracy": 1.0}
    unsure = {r["case_id"] for r in card["results"] if r["unsure"]}
    assert unsure == {
        s.case.case_id
        for s in samples
        if not s.expected.complete or s.expected.purchases > 1
    }


def test_fields_the_reader_lacks_are_unsupported_not_blank(
    samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    card = scorecard(scripted.faithful)
    for name in UNREAD_TODAY:
        counts = card["fields"][name]
        assert counts["unsupported"] == len(scored(samples))
        assert (counts["scored"], counts["accuracy"]) == (0, None)


def test_false_fills_are_counted_apart_from_blanks(
    samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    card = scorecard(scripted.careless)
    one = [sample.case for sample in scored(samples)]
    expiry_taken = sum(not case.date_label and bool(case.expiry) for case in one)
    buyer_taken = sum(
        case.supplier_rnc_print != "printed" and bool(case.buyer_rnc_label)
        for case in one
    )
    tax_dropped = sum(
        case.tax in ("impuesto", "impuesto_zero") and case.totals_visible for case in one
    )
    assert min(expiry_taken, buyer_taken, tax_dropped) >= 3
    dates, rncs, tax = (
        card["fields"][name] for name in ("issue_date", "supplier_rnc", "itbis")
    )
    assert (dates["false_fill"], dates["blank"]) == (expiry_taken, 0)
    assert (rncs["false_fill"], rncs["blank"]) == (buyer_taken, 0)
    assert (tax["false_fill"], tax["blank"]) == (0, tax_dropped)
    assert card["mistakes"] == {
        "buyer_rnc_as_supplier": buyer_taken,
        "expiry_as_issue_date": expiry_taken,
    }
    assert card["complete"]["wrong"] == sum(not case.totals_visible for case in one)


def test_an_empty_read_is_blank_never_a_false_fill(
    samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    card = scorecard(scripted.empty)
    for name in READ_TODAY:
        counts = card["fields"][name]
        assert counts["false_fill"] == 0
        assert counts["blank"] == sum(
            getattr(sample.expected, name) is not None for sample in scored(samples)
        )


def test_a_provider_outage_is_not_a_reader_score(
    samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    card = scorecard(scripted.outage)
    assert card["totals"]["infrastructure_error"] == len(samples)
    assert {r["error"] for r in card["results"]} == {"extraction_provider_failed"}
    assert all(counts["scored"] == 0 for counts in card["fields"].values())
    assert card["qr"]["decode_rate"] is None


def test_a_stopped_run_reports_what_it_did_not_read(
    samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    card = scorecard(scripted.faithful, stop=lambda done: len(done) >= 5)
    assert card["totals"]["read"] == 5
    assert card["totals"]["not_run"] == len(samples) - 5


def test_scorecard_is_a_json_document(
    scorecard: Callable[..., dict[str, Any]],
) -> None:
    card = json.loads(json.dumps(scorecard(scripted.careless)))
    assert card["schema_version"] == SCHEMA_VERSION
    assert {"prompt_sha256", "schema_sha256", "set_sha256", "candidate_sha"} <= set(
        card["provenance"]
    )
    assert card["provider_usage"] == {
        "calls": 0,
        "known_cost_usd": 0,
        "unpriced_calls": 0,
        "latency_ms": 0,
    }


def test_live_runner_stops_without_a_key(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    env_file = tmp_path / "env"
    env_file.write_text("OPENROUTER_API_KEY=\n")
    with pytest.raises(SystemExit, match="OPENROUTER_API_KEY is not set"):
        run_live.load_settings(env_file, "OPENROUTER_API_KEY", None)
