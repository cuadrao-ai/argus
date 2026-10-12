"""Operator entry for the Business live measurement. Not collected by pytest.

    python -m tests.evals.run_business_live calibrate|variety|acceptance \
        --dsn <loopback dsn> --out <dir under docs/reports/evidence> \
        --env-file <untracked env> --key-name <variable holding the key>

The key is read from the named variable of the env file into this process only
and is never printed. Every call is a real provider call: the runner stops once
the known cost reaches ``--cap-usd`` and reports the exact total.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from argus.agent_runtime.business.interpreter import BusinessInterpreterMethods
from argus.llm.openrouter import (
    begin_openrouter_route_receipt_capture,
    end_openrouter_route_receipt_capture,
    openrouter_request_guard,
)

from tests.evals import business_acceptance, business_runtime_capture
from tests.evals.business_acceptance import _settings, run_business_acceptance
from tests.evals.business_eval import (
    RUBRIC_VERSION,
    check_calibration,
    judge_reply,
    load_calibration,
)
from tests.evals.business_variety import check_variety, load_variety_cases


class BudgetReached(RuntimeError):
    pass


class Ledger:
    def __init__(self, cap_usd: float) -> None:
        self.cap, self.cost, self.calls, self.unpriced = cap_usd, 0.0, 0, 0

    def add(self, receipts: list[Any]) -> None:
        for receipt in receipts:
            self.calls += 1
            value = receipt.as_dict().get("usage_cost_usd")
            if isinstance(value, (int, float)):
                self.cost += value
            else:
                self.unpriced += 1
        if self.cost >= self.cap:
            raise BudgetReached(f"known cost {self.cost:.4f} reached cap {self.cap}")

    def summary(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "known_cost_usd": round(self.cost, 6),
            "unpriced_calls": self.unpriced,
        }


def metered(ledger: Ledger):  # noqa: ANN201
    def end(token: Any) -> list[Any]:
        receipts = end_openrouter_route_receipt_capture(token)
        ledger.add(receipts)
        return receipts

    return end


class LiveInterpreter(BusinessInterpreterMethods):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name


def load_key(env_file: Path, key_name: str) -> None:
    from dotenv import dotenv_values

    value = (dotenv_values(env_file).get(key_name) or "").strip()
    if not value:
        raise SystemExit(f"{key_name} is not set in the env file")
    os.environ["OPENROUTER_API_KEY"] = value
    os.environ.pop("APP_ENV", None)


def git_head(root: Path) -> str:
    return (
        subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=root).decode().strip()
    )


def write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


async def calibrate(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    import hashlib

    examples = load_calibration()
    verdicts: dict[str, Any] = {}
    receipts: list[dict[str, Any]] = []
    settings: list[dict[str, Any]] = []

    def capture(task: str, payload: dict[str, object]) -> dict[str, object]:
        settings.append(_settings(task, payload))
        return payload

    with openrouter_request_guard(capture):
        for example in examples:
            token = begin_openrouter_route_receipt_capture()
            verdict = None
            try:
                verdict = await judge_reply(
                    case_id=example["id"],
                    owner_message=example["owner_message"],
                    reply=example["assistant_reply"],
                    saved_state=example["saved_state"],
                    judge_model=args.judge_model,
                )
            except Exception as error:  # noqa: BLE001
                print(f"calibration {example['id']}: {type(error).__name__}")
            finally:
                step = metered(ledger)(token)
                receipts.extend(r.as_dict() for r in step)
            if verdict is not None:
                verdicts[example["id"]] = verdict
    failures = (
        check_calibration(examples, verdicts)
        if len(verdicts) == len(examples)
        else ["missing_verdicts"]
    )
    sha = hashlib.sha256(
        (
            Path(business_acceptance.__file__).with_name("business_cases")
            / "rubric_calibration.yaml"
        ).read_bytes()
    ).hexdigest()
    costs = [r.get("usage_cost_usd") for r in receipts]
    return {
        "schema_version": "business_e1_judge_calibration_v1",
        "status": "passed"
        if not failures and len(receipts) == len(examples)
        else "failed",
        "judge_model": args.judge_model,
        "rubric_version": RUBRIC_VERSION,
        "fixture_sha256": sha,
        "candidate_sha": git_head(args.root),
        "failures": failures,
        "verdicts": {name: v.model_dump() for name, v in verdicts.items()},
        "call_receipts": receipts,
        "request_settings": settings,
        "total_cost_usd": sum(c for c in costs if isinstance(c, (int, float))),
        "total_latency_ms": sum(r.get("latency_ms") or 0 for r in receipts),
    }


async def variety(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    results = []
    for case in load_variety_cases():
        if args.only and case["id"] not in args.only:
            continue
        entry: dict[str, Any] = {
            "case_id": case["id"],
            "messages": [s["message"] for s in case["steps"]],
        }
        try:
            capture = await business_runtime_capture.capture_case(
                case,
                dsn=args.dsn,
                interpreter_factory=lambda *_: LiveInterpreter(args.runtime_model),
                runtime_model=args.runtime_model,
            )
            entry["failures"] = check_variety(case, capture.observed_steps)
            entry["replies"] = capture.replies
            entry["facts"] = [
                (s.get("draft_facts") or {}).get(case["draft_alias"])
                for s in capture.observed_steps
            ]
        except BudgetReached:
            raise
        except Exception as error:  # noqa: BLE001
            entry["failures"] = [f"capture_error:{type(error).__name__}"]
            entry["error"] = str(error)[:1500]
        entry["status"] = "passed" if not entry["failures"] else "failed"
        results.append(entry)
        print(f"variety {case['id']}: {entry['status']} {entry['failures']}")
    passed = sum(e["status"] == "passed" for e in results)
    return {
        "schema_version": "business_variety_report_v1",
        "candidate_sha": git_head(args.root),
        "runtime_model": args.runtime_model,
        "totals": {"passed": passed, "failed": len(results) - passed},
        "cases": results,
    }


async def acceptance(
    args: argparse.Namespace, ledger: Ledger
) -> tuple[dict[str, Any], dict[str, Any]]:
    return await run_business_acceptance(
        repository_root=args.root,
        candidate_sha=git_head(args.root),
        dsn=args.dsn,
        runtime_model=args.runtime_model,
        judge_model=args.judge_model,
        calibration_report=args.calibration,
        interpreter_factory=lambda *_: LiveInterpreter(args.runtime_model),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("calibrate", "variety", "acceptance"))
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--key-name", default="OPENROUTER_API_KEY")
    parser.add_argument("--runtime-model", default="anthropic/claude-haiku-5.5")
    parser.add_argument("--judge-model", default="anthropic/claude-haiku-5.5")
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--cap-usd", type=float, default=3.0)
    args = parser.parse_args()
    args.root = Path(__file__).resolve().parents[2]
    load_key(args.env_file, args.key_name)
    ledger = Ledger(args.cap_usd)
    end = metered(ledger)
    business_acceptance.end_openrouter_route_receipt_capture = end
    business_runtime_capture.end_openrouter_route_receipt_capture = end
    try:
        if args.command == "calibrate":
            report = asyncio.run(calibrate(args, ledger))
            write(
                args.out / f"judge-calibration-{args.judge_model.split('/')[-1]}.json",
                report,
            )
            print("calibration", report["status"], report["failures"])
        elif args.command == "variety":
            report = asyncio.run(variety(args, ledger))
            write(args.out / "variety-report.json", report)
            print("variety", report["totals"])
        else:
            report, sidecar = asyncio.run(acceptance(args, ledger))
            write(args.out / "business-acceptance.json", report)
            write(args.out / "business-acceptance-request-settings.json", sidecar)
            print("acceptance", report["status"], report["totals"])
    except BudgetReached as stop:
        print("STOPPED:", stop)
        sys.exit(3)
    finally:
        print("ledger", json.dumps(ledger.summary()))


if __name__ == "__main__":
    main()
