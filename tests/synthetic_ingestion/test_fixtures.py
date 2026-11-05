"""Independent numeric anchors and honest extraction-boundary checks."""

import json
import shutil
from decimal import Decimal

import pytest

from tests.synthetic_ingestion.extract import load_input
from tests.synthetic_ingestion.generate import generate
from tests.synthetic_ingestion.harness import Harness


@pytest.fixture
def samples(tmp_path):
    output = tmp_path / "samples"
    generate(output, seed=71)
    return output


def test_same_seed_reproduces_every_artifact_byte_and_different_seed_changes_labels(
    tmp_path,
):
    first, second, third = (tmp_path / name for name in ("first", "second", "third"))
    for output, seed in ((first, 71), (second, 71), (third, 72)):
        generate(output, seed=seed)
    files = sorted(path.name for path in first.iterdir())
    assert files == sorted(path.name for path in second.iterdir())
    assert {name: (first / name).read_bytes() for name in files} == {
        name: (second / name).read_bytes() for name in files
    }
    assert (first / "transactions.csv").read_bytes() != (
        third / "transactions.csv"
    ).read_bytes()


def test_actual_csv_has_independent_financial_anchors_and_visible_exceptions(
    samples, tmp_path
):
    harness = Harness(tmp_path / "state.json")
    result = harness.ingest(samples / "transactions.csv")
    assert result["mode"] == "actual_csv"
    assert len(result["ids"]) == 11
    assert harness.records == {}
    confirmed = harness.confirm(result["ids"])
    assert len(confirmed["confirmed"]) == 6
    assert len(confirmed["skipped"]) == 5
    totals = harness.totals()
    assert Decimal(totals["DOP"]["personal"]["income"]) == Decimal("1200.00")
    assert Decimal(totals["DOP"]["personal"]["expense"]) == Decimal("225.50")
    assert Decimal(totals["DOP"]["personal"]["transfer"]) == Decimal("200.00")
    assert Decimal(totals["USD"]["personal"]["expense"]) == Decimal("40.00")


def test_manual_json_bytes_are_parsed_without_manifest(samples, tmp_path):
    (samples / "manifest.json").unlink()
    harness = Harness(tmp_path / "state.json")
    loaded = harness.ingest(samples / "manual.json")
    assert loaded["mode"] == "actual_manual_json"
    assert len(harness.confirm(loaded["ids"])["confirmed"]) == 3
    totals = harness.totals()["DOP"]["personal"]
    assert Decimal(totals["expense"]) == Decimal("150.00")
    assert Decimal(totals["income"]) == Decimal("1000.00")
    assert Decimal(totals["transfer"]) == Decimal("300.00")


@pytest.mark.skipif(
    shutil.which("pdftotext") is None, reason="Local PDF text extractor unavailable"
)
def test_actual_pdf_text_reconciles_independent_opening_and_closing_balances(
    samples, tmp_path
):
    (samples / "manifest.json").unlink()
    harness = Harness(tmp_path / "state.json")
    loaded = harness.ingest(samples / "statement.pdf")
    assert loaded["mode"] == "actual_synthetic_pdf_text"
    assert len(harness.confirm(loaded["ids"])["confirmed"]) == 4
    totals = harness.totals()["DOP"]["personal"]
    closing = Decimal("1000.00") + Decimal(totals["income"]) - Decimal(totals["expense"])
    assert closing == Decimal("1974.50")
    assert all(p["source_ref"].get("page") == 1 for p in harness.proposals.values())


@pytest.mark.parametrize(
    "filename", ["receipt.png", "scanned-statement.png", "voice-transcript-es.txt"]
)
def test_unsupported_extraction_is_never_reported_as_actual_and_stub_is_explicit(
    samples, filename
):
    actual = load_input(samples / filename)
    assert actual["mode"] == "unsupported"
    assert actual["proposals"] == []
    stub = load_input(samples / filename, stub_path=samples / f"{filename}.stub.json")
    assert stub["mode"] == "stub"
    assert stub["proposals"]
    assert all("confidence" not in proposal for proposal in stub["proposals"])


def test_partial_scan_stub_allows_reliable_income_and_keeps_unreadable_row(
    samples, tmp_path
):
    harness = Harness(tmp_path / "state.json")
    loaded = harness.ingest(
        samples / "scanned-statement.png",
        stub_path=samples / "scanned-statement.png.stub.json",
    )
    assert loaded["mode"] == "stub"
    result = harness.confirm(loaded["ids"])
    assert len(result["confirmed"]) == len(result["skipped"]) == 1
    assert Decimal(harness.totals()["DOP"]["personal"]["income"]) == Decimal("500.00")


def test_expected_manifest_cannot_masquerade_as_authored_extraction_stub(samples):
    result = load_input(samples / "receipt.png", stub_path=samples / "manifest.json")
    assert result["proposals"] == []
    assert result["errors"]


def test_fixture_manifest_explicitly_disclaims_bank_accuracy_and_audio(samples):
    manifest = json.loads((samples / "manifest.json").read_text())
    assert manifest["synthetic"] is True
    assert "No evidence of Dominican bank extraction accuracy" in manifest["disclaimer"]
    assert any(
        "STT" in value and "untested" in value for value in manifest["limitations"]
    )
    assert not list(samples.glob("*.wav"))


def test_actual_csv_responds_to_changed_input_bytes_not_manifest(samples):
    path = samples / "transactions.csv"
    path.write_text(path.read_text().replace("1200.00", "1300.00"), encoding="utf-8")
    result = load_input(path)
    assert result["mode"] == "actual_csv"
    assert any(
        proposal.get("fields", proposal).get("amount") == "1300.00"
        for proposal in result["proposals"]
    )
    assert not any(
        proposal.get("fields", proposal).get("amount") == "1200.00"
        for proposal in result["proposals"]
    )


def test_harness_imports_no_production_modules():
    import subprocess
    import sys

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import tests.synthetic_ingestion.harness; assert not any(n == 'argus' or n.startswith('argus.') for n in sys.modules)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    "filename", ["conversation-es.txt", "conversation-en.txt", "voice-transcript-es.txt"]
)
def test_authored_text_stubs_preserve_real_source_character_spans(samples, filename):
    text = (samples / filename).read_text()
    loaded = load_input(samples / filename, stub_path=samples / f"{filename}.stub.json")
    for proposal in loaded["proposals"]:
        reference = proposal["source_ref"]
        assert text[reference["char_start"] : reference["char_end"]] == reference["quote"]
        assert reference["quote"]


@pytest.mark.skipif(
    shutil.which("pdftotext") is None, reason="Local PDF text extractor unavailable"
)
def test_overlapping_statement_pdf_keeps_new_activity_and_reviews_prior_rows(
    samples, tmp_path
):
    harness = Harness(tmp_path / "state.json")
    original = harness.ingest(samples / "statement.pdf")
    assert len(harness.confirm(original["ids"])["confirmed"]) == 4
    overlap = harness.ingest(samples / "statement-overlap.pdf")
    result = harness.confirm(overlap["ids"])
    assert len(result["confirmed"]) == 1
    assert len(result["skipped"]) == 4
    assert all("possible_overlap" in issues for issues in result["skipped"].values())
    totals = harness.totals()["DOP"]["personal"]
    assert Decimal("1000.00") + Decimal(totals["income"]) - Decimal(
        totals["expense"]
    ) == Decimal("1914.50")


@pytest.mark.skipif(
    shutil.which("pdftotext") is None, reason="Local PDF text extractor unavailable"
)
def test_actual_pdf_short_table_row_reports_structural_error(tmp_path, monkeypatch):
    from tests.synthetic_ingestion import renderers

    malformed_table = (
        "source_id|date|description|amount|currency|kind|account|destination\n"
        "short-1|2026-09-10|Synthetic purchase|10.00|DOP|expense|cash\n"
    ).encode()
    with monkeypatch.context() as patch:
        patch.setattr(renderers, "csv_bytes", lambda *args: malformed_table)
        source = tmp_path / "malformed.pdf"
        renderers.write_pdf(source, [], {"opening": "100.00", "closing": "90.00"})
    loaded = load_input(source)
    assert loaded["mode"] == "actual_synthetic_pdf_text"
    assert loaded["errors"]
    assert loaded["proposals"] == []
