"""Changed authored extraction remains visible without duplicating confirmed truth."""

import json
from copy import deepcopy

import pytest

from tests.synthetic_ingestion.harness import Harness


@pytest.fixture
def authored_input(tmp_path, valid_row):
    source = tmp_path / "synthetic-capture.txt"
    source.write_text("SYNTHETIC CAPTURE: first location; second location.")
    stub_path = tmp_path / "capture.stub.json"
    stub = {
        "extraction_mode": "stub",
        "source_file": source.name,
        "proposals": [{**valid_row, "source_ref": {"span": "first location"}}],
    }
    stub_path.write_text(json.dumps(stub))
    return source, stub_path, stub


@pytest.mark.parametrize("change", ["amount", "location", "identity_fields"])
def test_changed_stub_requires_review_and_preserves_corrected_record(
    tmp_path, authored_input, change
):
    source, stub_path, stub = authored_input
    original_bytes = source.read_bytes()
    state = tmp_path / "state.json"
    harness = Harness(state)
    first = harness.ingest(source, stub_path=stub_path)
    record_id = harness.confirm(first["ids"])["confirmed"][0]
    harness.correct(
        record_id, reason="Hand-reviewed synthetic correction", amount="95.25"
    )
    saved_record = deepcopy(harness.records[record_id])
    saved_totals = harness.totals()
    if change == "amount":
        stub["proposals"][0]["amount"] = "200.00"
    elif change == "location":
        stub["proposals"][0]["source_ref"]["span"] = "second location"
    else:
        stub["proposals"][0].update(
            source_id="changed-source-id", account="changed-account", currency="USD"
        )
    stub_path.write_text(json.dumps(stub))
    reloaded = Harness(state)
    changed = reloaded.ingest(source, stub_path=stub_path)
    assert source.read_bytes() == original_bytes
    assert changed["ids"] != first["ids"]
    proposal = reloaded.proposals[changed["ids"][0]]
    assert proposal["fields"] == {
        key: value for key, value in stub["proposals"][0].items() if key != "source_ref"
    }
    assert proposal["source_ref"]["span"] == stub["proposals"][0]["source_ref"]["span"]
    assert proposal["status"] == "proposed"
    assert proposal["issues"]
    outcome = reloaded.confirm(changed["ids"])
    assert outcome["confirmed"] == []
    assert changed["ids"][0] in outcome["skipped"]
    assert reloaded.records == {record_id: saved_record}
    assert reloaded.totals() == saved_totals
    exact_retry = Harness(state)
    assert exact_retry.ingest(source, stub_path=stub_path)["ids"] == changed["ids"]
    assert len(exact_retry.proposals) == 2
    assert exact_retry.records == {record_id: saved_record}


def test_identical_stub_retry_is_idempotent_and_distinct_rows_remain_legitimate(
    tmp_path, authored_input
):
    source, stub_path, stub = authored_input
    stub["proposals"].append(deepcopy(stub["proposals"][0]))
    stub_path.write_text(json.dumps(stub))
    state = tmp_path / "state.json"
    harness = Harness(state)
    first = harness.ingest(source, stub_path=stub_path)
    assert len(set(first["ids"])) == 2
    assert len(harness.confirm(first["ids"])["confirmed"]) == 2
    reloaded = Harness(state)
    retry = reloaded.ingest(source, stub_path=stub_path)
    assert retry["ids"] == first["ids"]
    assert reloaded.confirm(retry["ids"])["confirmed"] == []
    assert len(reloaded.proposals) == len(reloaded.records) == 2
