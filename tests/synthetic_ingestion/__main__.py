"""Run explicit simulated review actions against the synthetic local corpus."""

import argparse
import json
from decimal import Decimal
from pathlib import Path

from .extract import load_input
from .harness import Harness


def run(samples: Path, state: Path, report: Path) -> dict:
    harness = Harness(state)
    extraction = []
    actions = []
    for name in (
        "manual.json",
        "transactions.csv",
        "statement.pdf",
        "overlapping.csv",
        "statement-overlap.pdf",
        "conversation-es.txt",
        "conversation-en.txt",
        "voice-transcript-es.txt",
        "receipt.png",
        "scanned-statement.png",
    ):
        path = samples / name
        stub = samples / f"{name}.stub.json"
        if stub.exists():
            actual = load_input(path)
            extraction.append(
                {"file": name, "mode": actual["mode"], "errors": actual["errors"]}
            )
        result = harness.ingest(path, stub if stub.exists() else None)
        extraction.append({"file": name, **result})
        actions.append(
            {
                "action": "explicit_simulated_batch_confirmation",
                "file": name,
                "result": harness.confirm(result["ids"]),
            }
        )
    overlaps = [p["id"] for p in harness.review() if "possible_overlap" in p["issues"]]
    actions.append(
        {
            "action": "explicit_simulated_overlap_review",
            "flagged_ids": overlaps,
            "decision": "Reject repeated CSV income; keep other potential overlaps visible",
        }
    )
    repeated = next(
        (
            p
            for p in harness.proposals.values()
            if p["source_ref"]["file"] == "overlapping.csv"
            and p["fields"]["source_id"] == "tx-dop-01"
        ),
        None,
    )
    if repeated and repeated["status"] == "proposed":
        harness.reject(repeated["id"])
        actions.append(
            {"action": "explicit_simulated_duplicate_rejection", "id": repeated["id"]}
        )
    ambiguous = next(
        (
            p
            for p in harness.proposals.values()
            if p["fields"]["source_id"] == "tx-currency"
        ),
        None,
    )
    if ambiguous and ambiguous["status"] == "proposed":
        harness.resolve(ambiguous["id"], currency="DOP")
        actions.append(
            {
                "action": "explicit_simulated_user_resolution",
                "id": ambiguous["id"],
                "currency": "DOP",
                "result": harness.confirm([ambiguous["id"]]),
            }
        )
    before_retry = len(harness.records)
    retry = harness.ingest(samples / "transactions.csv")
    harness.confirm(retry["ids"])
    actions.append(
        {
            "action": "retry_identical_source",
            "duplicate_count": len(harness.records) - before_retry,
        }
    )
    unresolved = [p for p in harness.review() if p["status"] == "proposed"]
    if unresolved and not any(
        p["status"] == "rejected" for p in harness.proposals.values()
    ):
        # Explicit demonstration choice: reject one unresolved proposal, preserving the rest.
        rejected = unresolved[-1]["id"]
        harness.reject(rejected)
        actions.append({"action": "explicit_simulated_rejection", "id": rejected})
    correction = next(
        (
            r
            for r in harness.records.values()
            if r["fields"]["source_id"] == "manual-expense"
        ),
        None,
    )
    before_correction = harness.totals()
    if correction and not correction["revisions"]:
        harness.correct(
            correction["id"],
            reason="Simulated user correction: cash lunch was DOP 175.00",
            amount="175.00",
        )
        actions.append(
            {
                "action": "explicit_simulated_correction",
                "id": correction["id"],
                "amount": "175.00",
            }
        )
    reloaded = Harness(state)
    parsed = load_input(samples / "statement.pdf")
    reconciliation = {"status": "untested"}
    if parsed.get("balances") and not parsed["errors"]:
        balance = parsed["balances"]
        activity = sum(
            (
                Decimal(row["fields"]["amount"])
                * (-1 if row["fields"]["kind"] == "expense" else 1)
                for row in parsed["proposals"]
            ),
            Decimal("0"),
        )
        derived = Decimal(balance["opening"]) + activity
        reconciliation = {
            "status": "checked",
            "source": "actual PDF bytes",
            **balance,
            "activity": str(activity),
            "derived_closing": str(derived),
            "matches": derived == Decimal(balance["closing"]),
        }
    output = {
        "synthetic_only": True,
        "purpose": "Local scripted lifecycle simulation, not real-bank accuracy evidence",
        "extraction_checks": extraction,
        "lifecycle_actions": actions,
        "before_correction": before_correction,
        "after_correction_and_reload": reloaded.totals(),
        "reload_matches": reloaded.totals() == harness.totals(),
        "confirmed_records": len(reloaded.records),
        "review_exceptions": [p for p in reloaded.review() if p["status"] != "confirmed"],
        "statement_reconciliation": reconciliation,
        "untested": [
            "OCR",
            "audio/STT",
            "real bank layouts",
            "household permissions",
            "production storage",
        ],
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("run")
    command.add_argument(
        "--samples", type=Path, default=Path(__file__).parent / "samples"
    )
    command.add_argument("--state", type=Path, required=True)
    command.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.samples, args.state, args.report)
    print(
        json.dumps(
            {
                "report": str(args.report),
                "confirmed_records": result["confirmed_records"],
                "reload_matches": result["reload_matches"],
                "synthetic_only": True,
            }
        )
    )


if __name__ == "__main__":
    main()
