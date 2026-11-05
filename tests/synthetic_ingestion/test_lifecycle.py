"""Behavioral checks independent of the generated expected-answer manifest."""

from decimal import Decimal

import pytest

from tests.synthetic_ingestion.harness import Harness


def test_extract_review_confirm_reload_and_retry_are_separate(
    tmp_path, csv_factory, valid_row
):
    source = csv_factory([valid_row])
    state = tmp_path / "state.json"
    harness = Harness(state)
    loaded = harness.ingest(source)
    assert len(loaded["ids"]) == 1
    assert harness.records == {}
    assert harness.totals() == {}
    proposal = harness.proposals[loaded["ids"][0]]
    assert proposal["source_ref"]
    assert proposal["status"] == "proposed"
    result = harness.confirm(loaded["ids"])
    assert len(result["confirmed"]) == 1
    reloaded = Harness(state)
    retried = reloaded.ingest(source)
    reloaded.confirm(retried["ids"])
    assert len(reloaded.records) == 1
    assert Decimal(reloaded.totals()["DOP"]["personal"]["expense"]) == Decimal("125.50")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", ""),
        ("amount", "NaN"),
        ("amount", "Infinity"),
        ("amount", "-Infinity"),
        ("amount", "0"),
        ("amount", "-1"),
        ("amount", "1.234,56"),
        ("date", ""),
        ("date", "09/10/2026"),
        ("date", "2026-02-30"),
        ("currency", "$"),
        ("currency", ""),
        ("account", ""),
        ("destination", ""),
        ("destination", "shared?"),
    ],
)
def test_unresolved_fields_cannot_enter_confirmed_totals(
    tmp_path, csv_factory, valid_row, field, value
):
    harness = Harness(tmp_path / "state.json")
    loaded = harness.ingest(csv_factory([{**valid_row, field: value}]))
    assert loaded["ids"]
    result = harness.confirm(loaded["ids"])
    assert result["confirmed"] == []
    assert result["skipped"]
    assert harness.records == {}
    assert harness.totals() == {}


def test_batch_keeps_rejected_and_unresolved_exceptions_visible(
    tmp_path, csv_factory, valid_row
):
    harness = Harness(tmp_path / "state.json")
    loaded = harness.ingest(
        csv_factory(
            [valid_row, {**valid_row, "amount": ""}, {**valid_row, "amount": "42.00"}]
        )
    )
    reliable, unresolved, rejected = loaded["ids"]
    harness.reject(rejected)
    result = harness.confirm(loaded["ids"])
    assert len(result["confirmed"]) == 1
    assert unresolved in result["skipped"]
    assert rejected in result["skipped"]
    assert harness.proposals[unresolved]["issues"]
    assert harness.proposals[rejected]["status"] == "rejected"
    assert len(harness.review()) == 3
    harness.resolve(unresolved, amount="15.00")
    assert len(harness.confirm([unresolved])["confirmed"]) == 1
    assert len(harness.records) == 2
    assert Decimal(harness.totals()["DOP"]["personal"]["expense"]) == Decimal("140.50")


def test_similar_legitimate_purchases_survive_and_overlapping_import_requires_review(
    tmp_path, csv_factory, valid_row
):
    harness = Harness(tmp_path / "state.json")
    original = csv_factory([valid_row, valid_row], "original.csv")
    first = harness.ingest(original)
    assert len(harness.confirm(first["ids"])["confirmed"]) == 2
    overlap = harness.ingest(
        csv_factory(
            [
                valid_row,
                {**valid_row, "source_id": "independent-new-source", "amount": "88.00"},
            ],
            "overlap.csv",
        )
    )
    matching, fresh = overlap["ids"]
    assert "possible_overlap" in harness.proposals[matching]["issues"]
    result = harness.confirm(overlap["ids"])
    assert len(result["confirmed"]) == 1
    assert matching in result["skipped"]
    harness.resolve(matching, overlap_reviewed=True)
    assert len(harness.confirm([matching])["confirmed"]) == 1
    assert harness.proposals[fresh]["status"] == "confirmed"
    assert len(harness.records) == 4


def test_correction_is_traceable_changes_totals_and_survives_reload(
    tmp_path, csv_factory, valid_row
):
    state = tmp_path / "state.json"
    harness = Harness(state)
    loaded = harness.ingest(csv_factory([valid_row]))
    record_id = harness.confirm(loaded["ids"])["confirmed"][0]
    original_source = dict(harness.records[record_id]["source_ref"])
    harness.correct(
        record_id, reason="Synthetic hand-reviewed receipt correction", amount="95.25"
    )
    reloaded = Harness(state)
    record = reloaded.records[record_id]
    assert record["source_ref"] == original_source
    assert record["revisions"][0]["before"]["amount"] == "125.50"
    assert record["revisions"][0]["after"]["amount"] == "95.25"
    assert record["revisions"][0]["reason"]
    assert Decimal(reloaded.totals()["DOP"]["personal"]["expense"]) == Decimal("95.25")
    reloaded.ingest(csv_factory([valid_row]))
    assert len(reloaded.records) == 1


def test_currencies_destinations_and_activity_types_remain_separate(
    tmp_path, csv_factory, valid_row
):
    rows = [
        {**valid_row, "amount": "100.00"},
        {**valid_row, "amount": "20.00", "kind": "refund"},
        {**valid_row, "amount": "500.00", "kind": "income"},
        {**valid_row, "amount": "70.00", "kind": "transfer"},
        {**valid_row, "amount": "10.00", "currency": "USD"},
        {**valid_row, "amount": "30.00", "destination": "household"},
    ]
    harness = Harness(tmp_path / "state.json")
    loaded = harness.ingest(csv_factory(rows))
    assert len(harness.confirm(loaded["ids"])["confirmed"]) == len(rows)
    totals = harness.totals()
    assert Decimal(totals["DOP"]["personal"]["expense"]) == Decimal("80.00")
    assert Decimal(totals["DOP"]["personal"]["income"]) == Decimal("500.00")
    assert Decimal(totals["DOP"]["personal"]["transfer"]) == Decimal("70.00")
    assert Decimal(totals["USD"]["personal"]["expense"]) == Decimal("10.00")
    assert Decimal(totals["DOP"]["household"]["expense"]) == Decimal("30.00")


def test_failed_persistence_leaves_no_confirmed_totals_and_retry_saves_once(
    tmp_path, csv_factory, valid_row, monkeypatch
):
    from tests.synthetic_ingestion import harness as harness_module

    state = tmp_path / "state.json"
    harness = Harness(state)
    loaded = harness.ingest(csv_factory([valid_row]))
    with monkeypatch.context() as patch:

        def fail_replace(*args):
            raise OSError("Synthetic disk failure")

        patch.setattr(harness_module.os, "replace", fail_replace)
        with pytest.raises(OSError, match="Synthetic disk failure"):
            harness.confirm(loaded["ids"])
    assert harness.records == {}
    assert harness.totals() == {}
    assert Harness(state).records == {}
    assert len(harness.confirm(loaded["ids"])["confirmed"]) == 1
    assert len(Harness(state).records) == 1


def test_invalid_utf8_input_can_be_retried_with_valid_bytes(
    tmp_path, csv_factory, valid_row
):
    source = tmp_path / "retry.csv"
    source.write_bytes(b"\xff\xfe")
    harness = Harness(tmp_path / "state.json")
    failed = harness.ingest(source)
    assert failed["errors"]
    assert failed["ids"] == []
    assert harness.totals() == {}
    repaired = csv_factory([valid_row], "retry.csv")
    loaded = harness.ingest(repaired)
    assert len(harness.confirm(loaded["ids"])["confirmed"]) == 1
    harness.ingest(repaired)
    assert len(harness.records) == 1


def test_partial_structural_failure_keeps_other_manual_rows(tmp_path, valid_row):
    import json

    source = tmp_path / "partial.json"
    source.write_text(json.dumps({"rows": [valid_row, {"amount": "1.00"}]}))
    harness = Harness(tmp_path / "state.json")
    loaded = harness.ingest(source)
    assert len(loaded["errors"]) == 1
    assert len(loaded["ids"]) == 1
    assert len(harness.confirm(loaded["ids"])["confirmed"]) == 1


def test_failed_directory_creation_rolls_back_confirmation(
    tmp_path, csv_factory, valid_row, monkeypatch
):
    from pathlib import Path

    state = tmp_path / "state.json"
    harness = Harness(state)
    loaded = harness.ingest(csv_factory([valid_row]))
    with monkeypatch.context() as patch:

        def fail_mkdir(*args, **kwargs):
            raise OSError("Synthetic directory failure")

        patch.setattr(Path, "mkdir", fail_mkdir)
        with pytest.raises(OSError, match="Synthetic directory failure"):
            harness.confirm(loaded["ids"])
    assert harness.records == {}
    assert harness.totals() == {}
    assert harness.proposals[loaded["ids"][0]]["status"] == "proposed"
    assert Harness(state).records == {}
    assert len(harness.confirm(loaded["ids"])["confirmed"]) == 1


def test_unknown_batch_id_does_not_partially_confirm_prior_valid_id(
    tmp_path, csv_factory, valid_row
):
    state = tmp_path / "state.json"
    harness = Harness(state)
    loaded = harness.ingest(csv_factory([valid_row]))
    with pytest.raises(KeyError):
        harness.confirm([*loaded["ids"], "nonexistent-proposal"])
    assert harness.records == {}
    assert harness.totals() == {}
    assert harness.proposals[loaded["ids"][0]]["status"] == "proposed"
    assert Harness(state).records == {}
    assert len(harness.confirm(loaded["ids"])["confirmed"]) == 1
