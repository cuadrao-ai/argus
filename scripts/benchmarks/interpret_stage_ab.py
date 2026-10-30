"""In-process interpret-stage latency for a fixed cohort, one label per run.

The deployed API runs main, so a branch cannot be measured by the #563 HTTP
harness before promotion. This driver runs the same interpret node the API
runs, under the same seven-call turn allowance, on the #563 cohort messages,
and records wall time plus every route receipt. Run it once per code version
with the same manifest and compare the two files with --summarize.

Paid: every turn spends real provider calls. No persistence is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PRODUCT_CALLS = frozenset({"LLMInterpretationResponse"})
PRODUCT_TASKS = frozenset({"chat_composer", "knowledge_route", "asset_mention_preflight"})
GUARDRAIL_SCHEMAS = (
    "FocusedAssetDiscoveryRead",
    "CapabilitySideQuestionAudit",
    "ContextQuestionAudit",
    "FocusedStrategyExtraction",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _receipt_row(receipt) -> dict:
    row = {
        "task": receipt.task,
        "tier": receipt.tier,
        "schema_name": receipt.schema_name,
        "latency_ms": receipt.latency_ms,
        "outcome": receipt.outcome,
        "fallback_used": receipt.fallback_used,
        "failure_mode": receipt.failure_mode,
        "usage_cost_usd": receipt.usage_cost_usd,
    }
    if receipt.repair_effect:
        row["repair_effect"] = {
            key: receipt.repair_effect.get(key)
            for key in ("trigger_reason", "repair_applied", "no_op_reason")
        }
    return row


def run(args: argparse.Namespace) -> None:
    load_dotenv(args.env_file, override=False)
    if not (os.getenv("OPENROUTER_API_KEY") or "").strip():
        raise SystemExit("OPENROUTER_API_KEY is required; this run spends provider calls")
    import argus
    from argus.agent_runtime.capabilities.contract import (
        build_default_capability_contract,
    )
    from argus.agent_runtime.llm_interpreter import OpenRouterStructuredInterpreter
    from argus.agent_runtime.stages.interpret import interpret_stage
    from argus.agent_runtime.state.models import RunState, UserState
    from argus.agent_runtime.turn_execution import (
        active_turn_execution,
        turn_execution_scope,
    )
    from argus.llm.openrouter import (
        begin_openrouter_route_receipt_capture,
        end_openrouter_route_receipt_capture,
    )

    manifest = json.loads(args.manifest.read_text())
    categories = set(args.categories.split(","))
    provenance = {
        "schema_version": "argus_interpret_stage_ab/v1",
        "label": args.label,
        "started_at": _utc_now(),
        # The commit of the tree actually imported, which PYTHONPATH may point
        # away from the invoking worktree.
        "source_sha": subprocess.check_output(
            [
                "git",
                "-C",
                os.fspath(Path(argus.__file__).resolve().parent),
                "rev-parse",
                "HEAD",
            ],
            text=True,
        ).strip(),
        "argus_module": os.fspath(Path(argus.__file__).resolve()),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "categories": sorted(categories),
        "iterations": args.iterations,
        "models": {
            name: os.getenv(name, "")
            for name in (
                "CUADRAO_STRUCTURED_MODEL",
                "CUADRAO_STRUCTURED_FALLBACK_MODEL",
                "CUADRAO_CHAT_MODEL",
            )
        },
        "market_data_provider_mode": os.getenv("ARGUS_MARKET_DATA_PROVIDER_MODE", ""),
        "research_rail_enabled": os.getenv("ARGUS_RESEARCH_RAIL_ENABLED", ""),
        "turn_call_allowance": os.getenv("CUADRAO_TURN_CALL_ALLOWANCE", ""),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; choose a fresh output file")
    contract = build_default_capability_contract()
    with args.output.open("w") as output:
        output.write(json.dumps({"provenance": provenance}) + "\n")
        for iteration in range(args.iterations):
            for group in manifest["categories"]:
                if group["category"] not in categories:
                    continue
                for case in group["cases"]:
                    state = RunState.new(
                        current_user_message=case["message"], recent_thread_history=[]
                    )
                    user = UserState(
                        user_id="argus-interpret-stage-ab",
                        language_preference=case["language"],
                        expertise_level="beginner",
                    )
                    token = begin_openrouter_route_receipt_capture()
                    started = time.perf_counter()
                    outcome = "error"
                    error_kind = None
                    calls_reserved = None
                    blocked_tasks: list[str] = []
                    assistant_characters = 0
                    try:
                        with turn_execution_scope(entry_state={}):
                            result = interpret_stage(
                                state=state,
                                user=user,
                                latest_task_snapshot=None,
                                selected_thread_metadata={
                                    "ui_language": case["language"]
                                },
                                structured_interpreter=OpenRouterStructuredInterpreter(
                                    contract=contract
                                ),
                            )
                            execution = active_turn_execution()
                            if execution is not None:
                                calls_reserved = execution.calls_reserved
                                blocked_tasks = list(execution.blocked_tasks)
                        outcome = result.outcome
                        patch = (
                            getattr(result, "patch", None)
                            or getattr(result, "stage_patch", {})
                            or {}
                        )
                        assistant_characters = len(
                            str(patch.get("assistant_response") or "")
                        )
                    except Exception as exc:  # noqa: BLE001
                        error_kind = type(exc).__name__
                    finally:
                        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
                        receipts = end_openrouter_route_receipt_capture(token)
                    record = {
                        "label": args.label,
                        "iteration": iteration + 1,
                        "category": group["category"],
                        "case_id": case["id"],
                        "language": case["language"],
                        "elapsed_ms": elapsed_ms,
                        "outcome": outcome,
                        "error_kind": error_kind,
                        "assistant_characters": assistant_characters,
                        "calls_reserved": calls_reserved,
                        "blocked_tasks": blocked_tasks,
                        "receipts": [_receipt_row(receipt) for receipt in receipts],
                    }
                    output.write(json.dumps(record, default=str) + "\n")
                    output.flush()
                    print(
                        json.dumps(
                            {
                                "label": args.label,
                                "case": case["id"],
                                "elapsed_ms": elapsed_ms,
                                "outcome": outcome,
                                "calls": [r.schema_name or r.task for r in receipts],
                            }
                        ),
                        flush=True,
                    )
        output.write(json.dumps({"finished_at": _utc_now()}) + "\n")


def load_records(path: Path) -> tuple[dict, list[dict]]:
    provenance: dict = {}
    records: list[dict] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "provenance" in row:
            provenance = row["provenance"]
        elif "case_id" in row:
            records.append(row)
    return provenance, records


def summarize(records: list[dict]) -> dict:
    """Per category: turn wall time, per-schema fires, and the guardrail share."""
    by_category: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_category[record["category"]].append(record)
    summary: dict = {}
    for category, rows in sorted(by_category.items()):
        elapsed = [row["elapsed_ms"] / 1000 for row in rows]
        provider_total = 0.0
        guardrail_total = 0.0
        fires: Counter = Counter()
        latencies: dict[str, list[float]] = defaultdict(list)
        turns_firing: Counter = Counter()
        composer_skipped = 0
        cost = 0.0
        for row in rows:
            seen: set[str] = set()
            for receipt in row["receipts"]:
                ms = float(receipt.get("latency_ms") or 0)
                provider_total += ms
                name = receipt.get("schema_name") or receipt.get("task")
                cost += float(receipt.get("usage_cost_usd") or 0)
                if (
                    receipt.get("task") == "chat_composer"
                    and receipt.get("outcome") == "skipped"
                ):
                    composer_skipped += 1
                if name in GUARDRAIL_SCHEMAS:
                    guardrail_total += ms
                    fires[name] += 1
                    latencies[name].append(ms / 1000)
                    seen.add(name)
            for name in seen:
                turns_firing[name] += 1
        summary[category] = {
            "turns": len(rows),
            "errors": sum(1 for row in rows if row.get("error_kind")),
            "elapsed_p50_s": round(_quantile(elapsed, 0.5) or 0, 2),
            "elapsed_p95_s": round(_quantile(elapsed, 0.95) or 0, 2),
            "provider_mean_s": round(provider_total / max(1, len(rows)) / 1000, 2),
            "guardrail_mean_s": round(guardrail_total / max(1, len(rows)) / 1000, 2),
            # Every call outside the four gated ones; a move here is provider
            # drift between runs, not the lane.
            "other_calls_mean_s": round(
                (provider_total - guardrail_total) / max(1, len(rows)) / 1000, 2
            ),
            "guardrail_share": round(guardrail_total / provider_total, 3)
            if provider_total
            else 0.0,
            "composer_skipped": composer_skipped,
            "cost_usd": round(cost, 4),
            "calls": {
                name: {
                    "fires": fires[name],
                    "turns": turns_firing[name],
                    "p50_s": round(_quantile(latencies[name], 0.5) or 0, 2),
                }
                for name in GUARDRAIL_SCHEMAS
            },
        }
    return summary


def render(label_summaries: list[tuple[str, dict]]) -> str:
    lines = [
        "| Turn type | label | n | interpret p50 | p95 | provider mean | other calls mean | guardrail mean | share | composer skipped | cost |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    categories = sorted(
        {category for _, summary in label_summaries for category in summary}
    )
    for category in categories:
        for label, summary in label_summaries:
            row = summary.get(category)
            if row is None:
                continue
            lines.append(
                f"| {category} | {label} | {row['turns']} | {row['elapsed_p50_s']:.2f}s | "
                f"{row['elapsed_p95_s']:.2f}s | {row['provider_mean_s']:.2f}s | "
                f"{row['other_calls_mean_s']:.2f}s | "
                f"{row['guardrail_mean_s']:.2f}s | {row['guardrail_share']:.0%} | "
                f"{row['composer_skipped']} | ${row['cost_usd']:.3f} |"
            )
    lines.append("")
    lines.append("| Turn type | label | call | fires | turns | p50 |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: |")
    for category in categories:
        for label, summary in label_summaries:
            row = summary.get(category)
            if row is None:
                continue
            for name, call in row["calls"].items():
                lines.append(
                    f"| {category} | {label} | {name} | {call['fires']} | {call['turns']} | {call['p50_s']:.2f}s |"
                )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--execute-live", action="store_true", required=True)
    runner.add_argument("--label", required=True)
    runner.add_argument("--manifest", type=Path, required=True)
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument(
        "--categories", default="ordinary_chat,compute_intent_probe,confirmation"
    )
    runner.add_argument("--iterations", type=int, default=1)
    runner.add_argument("--env-file", type=Path, default=Path(".env"))
    summarizer = sub.add_parser("summarize")
    summarizer.add_argument("files", type=Path, nargs="+")
    summarizer.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    if args.command == "run":
        run(args)
        return
    # Files sharing a label are one sample: interleaved runs of the same code
    # version are pooled so provider drift cannot masquerade as a change.
    pooled: dict[str, list[dict]] = defaultdict(list)
    provenances: dict[str, list[dict]] = defaultdict(list)
    for path in args.files:
        provenance, records = load_records(path)
        label = str(provenance.get("label") or path.stem)
        pooled[label].extend(records)
        provenances[label].append(provenance)
    label_summaries = []
    payload = {}
    for label, records in pooled.items():
        summary = summarize(records)
        label_summaries.append((label, summary))
        payload[label] = {"provenance": provenances[label], "summary": summary}
    if args.json is not None:
        args.json.write_text(json.dumps(payload, indent=2) + "\n")
    sys.stdout.write(render(label_summaries) + "\n")


if __name__ == "__main__":
    main()
