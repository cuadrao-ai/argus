"""Mocked tier of the receipt-read eval: no model call, no key, no network."""

from __future__ import annotations

import asyncio
import io
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from argus.domain.business.dgii_codes import EXPENSE_TYPES, PAYMENT_FORMS
from argus.domain.business.fiscal_identity import rnc_check_digit_ok
from argus.domain.ingestion.documents import extractor as reader
from argus.domain.ingestion.documents.dgii_qr import read_dgii_qr
from argus.domain.ingestion.documents.models import (
    DocumentExtractionError,
    ExtractionBatch,
)
from argus.llm import openrouter
from PIL import Image

from tests.evals.document_read import read_live, run_live, scoring, scripted
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
    UNSUPPORTED,
    Prepared,
    ScriptedRead,
    build_scorecard,
    prepare_set,
    read_set,
    score_case,
    summary_table,
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
    documents = prepare_set(samples)
    rejected = {
        case_id: document.code
        for case_id, document in documents.items()
        if isinstance(document, DocumentExtractionError)
    }
    assert not rejected, f"this machine could not prepare {rejected}"
    return documents


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


def test_no_qr_answer_is_a_near_miss(samples: tuple[Sample, ...]) -> None:
    """At half size every photo gives the same QR answer, so a pixel of
    difference between two machines cannot change one."""

    for sample in samples:
        with Image.open(io.BytesIO(sample.image)) as photo:
            half = io.BytesIO()
            photo.resize((photo.width // 2, photo.height // 2)).save(half, "JPEG")
        decoded = read_dgii_qr([half.getvalue()]) is not None
        assert decoded == sample.expected.dgii_qr_readable, sample.case.case_id


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
    assert card["complete"] == {
        "correct": len(one),
        "wrong": 0,
        "failed": 0,
        "not_scored": len(samples) - len(one),
        "accuracy": 1.0,
    }
    assert card["purchases"] == {
        "correct": len(samples),
        "wrong": 0,
        "failed": 0,
        "accuracy": 1.0,
    }
    assert card["reliability"]["incomplete"] is False
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


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.invalid/read")
    return httpx.HTTPStatusError(
        str(status), request=request, response=httpx.Response(status, request=request)
    )


NO_ANSWER = {
    "connection": httpx.ConnectError("scripted"),
    "timeout": httpx.ReadTimeout("scripted"),
    "provider 503": _status_error(503),
    "provider 429": _status_error(429),
    "refused key": _status_error(401),
}


@pytest.mark.parametrize("shape", NO_ANSWER)
def test_a_read_with_no_answer_is_not_a_reader_score_and_flags_the_scorecard(
    shape: str, samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    card = scorecard(lambda sample: NO_ANSWER[shape])
    assert card["reliability"] == {
        "attempted": len(samples),
        "read": 0,
        "model_failure": 0,
        "infrastructure_error": len(samples),
        "not_run": 0,
        "success_rate": 0.0,
        "incomplete": True,
    }
    assert {r["error"] for r in card["results"]} == {"extraction_provider_failed"}
    assert all(counts["scored"] == 0 for counts in card["fields"].values())
    assert card["qr"]["decode_rate"] is None
    assert summary_table(card).startswith("**INCOMPLETE RUN")


def test_one_read_with_no_answer_flags_the_scorecard(
    samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    lost = scored(samples)[0].case.case_id
    card = scorecard(
        lambda sample: (
            scripted.outage(sample)
            if sample.case.case_id == lost
            else scripted.faithful(sample)
        )
    )
    assert card["reliability"]["infrastructure_error"] == 1
    assert card["reliability"]["incomplete"] is True
    assert card["fields"]["total"]["scored"] == len(scored(samples)) - 1


@pytest.mark.parametrize("broken", [scripted.unparseable, scripted.cut_off])
def test_an_answer_the_model_broke_lowers_every_score(
    broken: ScriptedRead,
    samples: tuple[Sample, ...],
    scorecard: Callable[..., dict[str, Any]],
) -> None:
    one = scored(samples)
    hard = {sample.case.case_id for sample in one[::3]} | {
        sample.case.case_id for sample in samples if sample.expected.purchases > 1
    }
    assert 3 <= len(hard) < len(samples)
    card = scorecard(
        lambda sample: (
            broken(sample) if sample.case.case_id in hard else scripted.faithful(sample)
        )
    )
    clean = scorecard(scripted.faithful)
    failed = sum(sample.case.case_id in hard for sample in one)
    for name in READ_TODAY:
        counts = card["fields"][name]
        assert counts["failed"] == failed, name
        assert counts["scored"] == len(one) == clean["fields"][name]["scored"]
        assert counts["accuracy"] == round((len(one) - failed) / len(one), 4)
        assert counts["accuracy"] < clean["fields"][name]["accuracy"]
    for name in UNREAD_TODAY:
        assert card["fields"][name]["unsupported"] == len(one)
    assert card["complete"]["failed"] == failed
    assert card["complete"]["accuracy"] == round((len(one) - failed) / len(one), 4)
    assert card["purchases"]["failed"] == len(hard)
    assert card["purchases"]["accuracy"] == round(1 - len(hard) / len(samples), 4)
    assert card["qr"] == clean["qr"]
    assert all(
        counts["receipts"] == clean["by_shape"][shape]["receipts"]
        for shape, counts in card["by_shape"].items()
    )
    assert card["reliability"] == {
        "attempted": len(samples),
        "read": len(samples) - len(hard),
        "model_failure": len(hard),
        "infrastructure_error": 0,
        "not_run": 0,
        "success_rate": round(1 - len(hard) / len(samples), 4),
        "incomplete": False,
    }
    assert {
        r["case_id"] for r in card["results"] if r["status"] == "model_failure"
    } == hard
    assert "INCOMPLETE" not in summary_table(card)


def _provider_answer(content: str, finish: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://provider.invalid/read"),
        json={"choices": [{"finish_reason": finish, "message": {"content": content}}]},
    )


BROKEN_ANSWERS = {
    "malformed JSON": _provider_answer('{"complete": tr'),
    "not the schema": _provider_answer('{"complete": true, "invented": 1}'),
    "out of output": _provider_answer('{"complete": true', finish="length"),
}


@pytest.mark.parametrize("shape", BROKEN_ANSWERS)
def test_the_provider_call_reports_a_broken_answer_as_a_model_failure(
    shape: str,
    samples: tuple[Sample, ...],
    prepared: Prepared,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def post(**_: object) -> httpx.Response:
        return BROKEN_ANSWERS[shape]

    monkeypatch.setattr(openrouter, "resolve_openrouter_api_key", lambda *_: "offline")
    monkeypatch.setattr(reader, "resolve_openrouter_api_key", lambda _: "offline")
    monkeypatch.setattr(reader, "resolve_openrouter_model", lambda **_: "scripted")
    monkeypatch.setattr(openrouter, "_post_openrouter_json_schema", post)
    one = scored(samples)[0]
    results = asyncio.run(read_set(samples, prepared, only=frozenset({one.case.case_id})))
    assert [result["status"] for result in results] == ["model_failure"]
    assert {results[0]["fields"][name]["outcome"] for name in READ_TODAY} == {"failed"}


def test_a_reader_that_breaks_every_answer_scores_zero(
    scorecard: Callable[..., dict[str, Any]],
) -> None:
    card = scorecard(scripted.unparseable)
    assert [card["fields"][name]["accuracy"] for name in READ_TODAY] == [0.0] * len(
        READ_TODAY
    )
    assert card["complete"]["accuracy"] == 0.0
    assert card["purchases"]["accuracy"] == 0.0
    assert card["reliability"]["success_rate"] == 0.0


def test_a_stopped_run_reports_what_it_did_not_read(
    samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    card = scorecard(scripted.faithful, stop=lambda done: len(done) >= 5)
    assert card["reliability"]["read"] == 5
    assert card["reliability"]["not_run"] == len(samples) - 5
    assert card["reliability"]["incomplete"] is True


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


def test_a_missed_second_receipt_is_scored(
    samples: tuple[Sample, ...], scorecard: Callable[..., dict[str, Any]]
) -> None:
    two = [s.case.case_id for s in samples if s.expected.purchases > 1]
    assert two
    card = scorecard(scripted.first_receipt_only)
    assert card["purchases"] == {
        "correct": len(samples) - len(two),
        "wrong": len(two),
        "failed": 0,
        "accuracy": round((len(samples) - len(two)) / len(samples), 4),
    }
    missed = [r for r in card["results"] if r["purchases"]["outcome"] == "wrong"]
    assert [r["case_id"] for r in missed] == two
    assert [r["purchases"] for r in missed] == [
        {"expected": 2, "read": 1, "outcome": "wrong"}
    ] * len(two)
    assert (
        f"Purchase count right {len(samples) - len(two)} of {len(samples)}"
        in summary_table(card)
    )


CLEAR_EXPENSE_TYPES = {
    "alquiler": "03",
    "seguros": "11",
    "equipos": "10",
    "mobiliario": "10",
    "papeleria": "02",
    "toner": "02",
    "servicios": "02",
}


def test_only_the_named_trades_have_a_clear_expense_type(
    samples: tuple[Sample, ...],
) -> None:
    clear = {
        name: trade.expense_type
        for name, trade in TRADES.items()
        if trade.expense_basis == "clear"
    }
    assert clear == CLEAR_EXPENSE_TYPES
    bases = Counter(sample.expected.expense_type_basis for sample in scored(samples))
    assert min(bases["clear"], bases["judgment"]) >= 5


def expense_card(
    samples: tuple[Sample, ...],
    monkeypatch: pytest.MonkeyPatch,
    read: Callable[[Sample], str | None],
) -> dict[str, Any]:
    """A scorecard for a reader that has a tipo de gasto field and returns ``read``."""

    results = []
    for sample in samples:
        answer = {**dict.fromkeys(FIELDS, UNSUPPORTED), "expense_type": read(sample)}
        monkeypatch.setattr(scoring, "read_fields", lambda _, answer=answer: answer)
        results.append(score_case(sample, ExtractionBatch(candidates=())))
    return build_scorecard(
        samples, results, tier="mocked", candidate_sha="mocked", model="scripted"
    )


def _wrong_on(basis: str) -> Callable[[Sample], str | None]:
    def read(sample: Sample) -> str | None:
        answer = sample.expected
        return "09" if answer.expense_type_basis == basis else answer.expense_type

    return read


def test_a_judgment_mismatch_never_changes_the_expense_type_score(
    samples: tuple[Sample, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    right = expense_card(samples, monkeypatch, lambda s: s.expected.expense_type)
    card = expense_card(samples, monkeypatch, _wrong_on("judgment"))
    judged = [s for s in scored(samples) if s.expected.expense_type_basis == "judgment"]
    clear = len(scored(samples)) - len(judged)
    assert card["expense_type"]["clear"] == right["expense_type"]["clear"]
    assert card["expense_type"]["clear"] == {
        "correct": clear,
        "false_fill": 0,
        "blank": 0,
        "failed": 0,
        "scored": clear,
        "accuracy": 1.0,
        "false_fill_rate": 0.0,
    }
    totals = card["fields"]["expense_type"]
    assert (totals["scored"], totals["judgment"]) == (clear, len(judged))
    assert card["expense_type"]["judgment"] == [
        {
            "case_id": s.case.case_id,
            "expected": s.expected.expense_type,
            "read": "09",
        }
        for s in judged
    ]
    assert f"{len(judged)} judgment receipts, not scored" in summary_table(card)


def test_a_clear_false_fill_and_a_clear_blank_are_scored_apart(
    samples: tuple[Sample, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    clear = sum(s.expected.expense_type_basis == "clear" for s in scored(samples))
    wrong = expense_card(samples, monkeypatch, _wrong_on("clear"))["expense_type"]
    assert wrong["clear"] == {
        "correct": 0,
        "false_fill": clear,
        "blank": 0,
        "failed": 0,
        "scored": clear,
        "accuracy": 0.0,
        "false_fill_rate": 1.0,
    }
    blank = expense_card(
        samples,
        monkeypatch,
        lambda s: (
            None if s.expected.expense_type_basis == "clear" else s.expected.expense_type
        ),
    )["expense_type"]
    assert (blank["clear"]["false_fill"], blank["clear"]["blank"]) == (0, clear)


INHERITED = {
    "CUADRAO_OPENROUTER_API_KEY_DEV": "inherited-dev",
    "CUADRAO_OPENROUTER_API_KEY_STG": "inherited-stg",
    "CUADRAO_PROD_OPENROUTER_API_KEY": "inherited-registered",
    "OPENROUTER_API_KEY": "inherited-local",
    "openrouter_api_key": "inherited-lower-case",
    "APP_ENV": "staging",
    "CUADRAO_VISION_MODEL": "inherited/model",
    "ARGUS_VISION_MODEL": "inherited/old-model",
}
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def env_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A shell full of other credentials, and an env file that selects one."""

    for name, value in INHERITED.items():
        monkeypatch.setenv(name, value)
    path = tmp_path / "env"
    path.write_text("EVAL_KEY=selected-fake\n")
    return path


@pytest.fixture
def child_env(env_file) -> dict[str, str]:
    selected = run_live.load_settings(env_file, "EVAL_KEY", "selected/model")
    return run_live.child_environment(selected)


@pytest.fixture
def in_the_child(child_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """Give this process the environment the reading process starts with."""

    for name in INHERITED:
        monkeypatch.delenv(name, raising=False)
    for name, value in child_env.items():
        monkeypatch.setenv(name, value)


def test_live_runner_never_takes_an_inherited_model(env_file) -> None:
    with pytest.raises(SystemExit, match="pass --model"):
        run_live.load_settings(env_file, "EVAL_KEY", None)


def test_the_reading_process_starts_with_only_the_selected_key_and_model(
    child_env,
) -> None:
    assert child_env[read_live.KEY_SETTING] == "selected-fake"
    assert child_env[read_live.MODEL_SETTING] == "selected/model"
    assert not set(child_env.values()) & set(INHERITED.values())
    assert all(name.isupper() for name in child_env)
    assert {name.upper() for name in INHERITED} <= set(child_env)


def test_an_inherited_key_cannot_reach_a_read(child_env) -> None:
    probe = (
        "from argus.domain.ingestion.documents import extractor as reader\n"
        "from tests.evals.document_read import read_live, scoring\n"
        "read_live.selected_provider()\n"
        "used = reader.DocumentExtractor(scoring._SETTINGS)._provider()\n"
        "assert used == ('selected/model', 'selected-fake')\n"
    )
    child = subprocess.run(
        (sys.executable, "-c", probe),
        cwd=ROOT,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 0, child.stderr


def test_a_live_run_leaves_the_operator_shell_as_it_was(
    env_file, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[dict[str, Any]] = []

    def start(command: tuple[str, ...], **how: Any) -> SimpleNamespace:
        started.append({"command": command, **how})
        return SimpleNamespace(returncode=3, stdout="candidate\n")

    monkeypatch.setattr(run_live.subprocess, "run", start)
    args = SimpleNamespace(
        out=tmp_path / "out",
        env_file=env_file,
        key_name="EVAL_KEY",
        model="selected/model",
        only=["fecha-2-digit-year"],
        cap_usd=0.5,
    )
    assert run_live.run(args) == 3
    (child,) = (start for start in started if "env" in start)
    assert child["command"][-6:-4] == ("--candidate-sha", "candidate")
    assert child["env"][read_live.KEY_SETTING] == "selected-fake"
    assert "selected-fake" not in child["command"]
    assert "tests.evals.document_read.read_live" in child["command"]
    assert reader.resolve_openrouter_api_key("registered") == "inherited-stg"
    assert (
        reader.resolve_openrouter_model(task="document_extraction") == "inherited/model"
    )


@pytest.mark.parametrize(
    ("other", "refusal"),
    [
        ({"resolve_openrouter_api_key": lambda _: "inherited-dev"}, "selected key"),
        ({"resolve_openrouter_model": lambda **_: "inherited/model"}, "selected model"),
    ],
)
def test_live_reads_refuse_when_a_read_would_use_something_else(
    in_the_child, monkeypatch: pytest.MonkeyPatch, other: dict[str, Any], refusal: str
) -> None:
    for name, resolve in other.items():
        monkeypatch.setattr(reader, name, resolve)
    with pytest.raises(SystemExit, match=refusal) as stopped:
        read_live.selected_provider()
    assert "selected-fake" not in str(stopped.value)
    assert "inherited-dev" not in str(stopped.value)


def test_live_reads_refuse_a_hosted_shell(
    env_file, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    monkeypatch.setenv("RENDER", "true")
    request.getfixturevalue("in_the_child")
    with pytest.raises(SystemExit, match="refused"):
        read_live.selected_provider()


def test_live_reads_refuse_to_start_without_a_selected_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(read_live.KEY_SETTING, "")
    monkeypatch.setenv(read_live.MODEL_SETTING, "selected/model")
    with pytest.raises(SystemExit, match="run_live"):
        read_live.selected_provider()
