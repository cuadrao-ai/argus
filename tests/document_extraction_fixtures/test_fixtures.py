"""Validate paired documents before extraction benchmark results are trusted."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).parent
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
SAMPLES = MANIFEST["samples"]


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda sample: sample["id"])
def test_document_checksum(sample):
    assert (
        hashlib.sha256((ROOT / sample["file"]).read_bytes()).hexdigest()
        == sample["sha256"]
    )


@pytest.mark.parametrize(
    "sample", [s for s in SAMPLES if not s["synthetic"]], ids=lambda sample: sample["id"]
)
def test_public_document_label_pair(sample):
    label_bytes = (ROOT / sample["original_labels"]).read_bytes()
    assert hashlib.sha256(label_bytes).hexdigest() == sample["labels_sha256"]
    annotation = json.loads(label_bytes)
    image = Image.open(ROOT / sample["file"])
    size = annotation["meta"]["image_size"]
    assert image.size == (size["width"], size["height"])
    assert annotation["meta"]["split"] == "test"
    assert sample["id"] == f"cord-test-{annotation['meta']['image_id']}"
    for line in annotation["valid_line"]:
        for word in line["words"]:
            quad = word["quad"]
            assert all(0 <= quad[f"x{i}"] <= image.width for i in range(1, 5))
            assert all(0 <= quad[f"y{i}"] <= image.height for i in range(1, 5))
    totals = [
        word
        for line in annotation["valid_line"]
        if line["category"] == "total.total_price"
        for word in line["words"]
        if not word["is_key"]
    ]
    assert len(totals) == 1
    assert totals[0]["text"] == annotation["gt_parse"]["total"]["total_price"]
    assert totals[0]["text"] == sample["validation"]["total_label"]
    quad = totals[0]["quad"]
    region = image.crop((quad["x1"], quad["y1"], quad["x3"], quad["y3"])).convert("L")
    low, high = region.getextrema()
    assert high - low > 30
    expected = sample["expected_rows"][0]
    assert Decimal(totals[0]["text"].replace(".", "")) == Decimal(expected["amount"])
    assert expected["date"] is None
    assert expected["currency"] is None


@pytest.mark.parametrize(
    "sample",
    [s for s in SAMPLES if s["file"].endswith(".pdf")],
    ids=lambda sample: sample["id"],
)
def test_pdf_rows_pages_and_balance_arithmetic(sample):
    executable = shutil.which("pdftotext")
    if not executable:
        pytest.skip("Poppler pdftotext is required for document-text pair validation")
    result = subprocess.run(
        [executable, "-layout", str(ROOT / sample["file"]), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    pages = result.stdout.split("\f")[:-1]
    assert len(pages) == sample["pages"]
    balance = sample["excluded_balances"]
    net = Decimal(balance["opening"])
    for row in sample["expected_rows"]:
        lines = [
            line for line in pages[row["page"] - 1].splitlines() if row["date"] in line
        ]
        assert len(lines) == 1
        assert row["description"] in lines[0]
        assert row["amount"] in lines[0].replace(",", "")
        assert row["currency"] in pages[row["page"] - 1]
        net += Decimal(row["amount"]) * (-1 if row["kind"] == "expense" else 1)
    assert net == Decimal(balance["closing"])
    assert len(re.findall(r"^\d{4}-\d{2}-\d{2} ", result.stdout, re.MULTILINE)) == len(
        sample["expected_rows"]
    )


def test_synthetic_regeneration_matches_committed_documents(tmp_path):
    script = ROOT.parents[1] / "scripts/documents/prepare_fixtures.py"
    subprocess.run([sys.executable, str(script), "--output", str(tmp_path)], check=True)
    for sample in SAMPLES:
        if sample["synthetic"]:
            generated, committed = tmp_path / sample["file"], ROOT / sample["file"]
            if generated.suffix == ".png":
                with Image.open(generated) as actual, Image.open(committed) as expected:
                    assert actual.size == expected.size
                    assert actual.mode == expected.mode
                    assert actual.tobytes() == expected.tobytes()
            else:
                assert generated.read_bytes() == committed.read_bytes()


def test_unreadable_document_contains_no_visible_transaction_pixels():
    sample = next(sample for sample in SAMPLES if sample["id"] == "unreadable")
    image = Image.open(ROOT / sample["file"])
    assert image.crop((30, 155, 1061, 641)).getextrema() == ((80, 80),) * 3
    assert sample["expected_rows"] == []
