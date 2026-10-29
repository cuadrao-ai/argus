"""Replay recorded provider responses through the research publish path.

``run`` loads one source tree (``--tree``) hermetically: no provider key,
synthetic asset data, memory persistence. Each recorded response is served to
the rail's own provider client and composed by that tree's inline entry
(``grounded_result``) or its background completion (``thorough_job_result``
then ``compose_completed_research``), with the clock frozen at the instant the
question was recorded, so each tree dates the question the way it would have
on the live turn. ``compare`` turns two runs into the committed comparison.

    poetry run python replay.py run --tree <src-tree> --label before --out before.json
    poetry run python replay.py compare before.json after.json --out comparison.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVIDENCE = Path(__file__).resolve().parents[2]
# 377's recordings kept no capture instant. No date bound applies to the
# questions they are replayed as, so any instant composes them identically.
UNRECORDED_INSTANT = "2026-08-07T18:00:00+00:00"
NAMES = {
    "AAPL": "Apple Inc.",
    "NFLX": "Netflix Inc.",
    "NKE": "NIKE, Inc.",
    "NVDA": "NVIDIA Corporation",
    "SPY": "SPDR S&P 500 ETF Trust",
}


@dataclass(frozen=True)
class Case:
    name: str
    recording: str
    question: str
    question_kind: str
    symbols: tuple[str, ...]
    language: str = "en"
    period_of_interest: str | None = None
    path: str = "inline"
    why: str = ""


CASES = (
    Case(
        "nike-fast-1",
        "open-the-gates/probes/nike-fast-1.json",
        "what's the price of nike today",
        "live_quote",
        ("NKE",),
        why="#578's Nike quote: one finance lookup (regression guard)",
    ),
    Case(
        "nike-fast-2",
        "open-the-gates/probes/nike-fast-2.json",
        "what's the price of nike today",
        "live_quote",
        ("NKE",),
        why="#578 probe, same question",
    ),
    Case(
        "nike-fast-web",
        "open-the-gates/probes/nike-fast-web.json",
        "what's the price of nike today",
        "live_quote",
        ("NKE",),
        why="#578 probe with web search offered",
    ),
    Case(
        "nike-unresolved-fast-2steps",
        "open-the-gates/probes/nike-unresolved-fast-2steps.json",
        "what's the price of nike today",
        "live_quote",
        ("NKE",),
        why="#578 probe: the only call went to the ticker lookup",
    ),
    Case(
        "nike-unresolved-fast-4steps",
        "open-the-gates/probes/nike-unresolved-fast-4steps.json",
        "what's the price of nike today",
        "live_quote",
        ("NKE",),
        why="#578 probe at the four-step budget",
    ),
    Case(
        "apple-es-fast-4steps",
        "open-the-gates/probes/apple-es-fast-4steps.json",
        "¿A cuánto está la acción de Apple hoy y cuánto subió esta semana?",
        "live_quote",
        ("AAPL",),
        language="es-419",
        period_of_interest="esta semana",
        why="#578 Spanish quote probe, asked 20:17 ET",
    ),
    Case(
        "perplexity-spx-week",
        "open-the-gates/perplexity-spx-week.json",
        "how much did the S&P 500 move this week?",
        "market_pulse",
        ("SPY",),
        period_of_interest="this week",
        why="#579: the S&P week question, asked 20:13 ET (plain provider call)",
    ),
    Case(
        "perplexity-nvda-week",
        "open-the-gates/perplexity-nvda-week.json",
        "why is NVIDIA stock moving this week?",
        "current_external",
        ("NVDA",),
        period_of_interest="this week",
        why="#578 claim-shaped question, asked 20:22 ET (plain provider call)",
    ),
    Case(
        "perplexity-nike",
        "open-the-gates/perplexity-nike.json",
        "what's the price of nike today",
        "live_quote",
        ("NKE",),
        why="#578 side-by-side recording (plain provider call)",
    ),
    Case(
        "perplexity-apple-pe",
        "open-the-gates/perplexity-apple-pe.json",
        "what is apple's p/e ratio right now?",
        "live_quote",
        ("AAPL",),
        why="#578 side-by-side recording (plain provider call)",
    ),
    Case(
        "perplexity-apple-es",
        "open-the-gates/perplexity-apple-es.json",
        "¿A cuánto está la acción de Apple hoy y cuánto subió esta semana?",
        "live_quote",
        ("AAPL",),
        language="es-419",
        period_of_interest="esta semana",
        why="#578 side-by-side recording (plain provider call)",
    ),
    Case(
        "377-equity-control-quote",
        "377/probes/equity_control_quote.json",
        "AAPL latest close (request not recorded)",
        "live_quote",
        ("AAPL",),
        why="#580: a recorded response that called no tool",
    ),
    Case(
        "377-equity-control-quote-background",
        "377/probes/equity_control_quote.json",
        "AAPL latest close (request not recorded)",
        "cross_company",
        ("AAPL",),
        path="background",
        why="#580 on the background path",
    ),
    Case(
        "377-equity-peers-netflix",
        "377/probes/equity_peers_netflix.json",
        "Netflix peers (request not recorded)",
        "company_lookup",
        ("NFLX",),
        why="#580: prose from memory on a claim-shaped question",
    ),
    Case(
        "377-equity-peers-netflix-background",
        "377/probes/equity_peers_netflix.json",
        "Netflix peers (request not recorded)",
        "cross_company",
        ("NFLX",),
        path="background",
        why="#580: prose from memory on the background path",
    ),
    Case(
        "545-market-pulse-no-tool",
        "545/probes/market_pulse_retry_finance_only.json",
        "anything interesting moving today",
        "market_pulse",
        (),
        why="survey gate unchanged: a survey that called no tool",
    ),
)


def _hermetic_env() -> None:
    os.environ.update(
        {
            "CUADRAO_PERSISTENCE_MODE": "memory",
            "ARGUS_DEV_MEMORY_FALLBACK": "true",
            "CUADRAO_CHECKPOINTER_MODE": "memory",
            "CUADRAO_MOCK_AUTH": "true",
            "ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture",
            "ARGUS_RESEARCH_RAIL_ENABLED": "true",
            "DATABASE_URL": "",
            "OPENROUTER_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "PERPLEXITY_API_KEY": "",
            "ALPACA_API_KEY": "",
            "ALPACA_SECRET_KEY": "",
        }
    )


def _recorded(case: Case) -> tuple[dict[str, Any], str]:
    document = json.loads((EVIDENCE / case.recording).read_text())
    if "exchanges" in document:
        exchange = document["exchanges"][-1]
        return exchange["response"], document.get("captured_at") or UNRECORDED_INSTANT
    instant = document.get("asked_at") or document.get("captured_at")
    return document["response"], instant or UNRECORDED_INSTANT


def _freeze(modules: list[Any], at: datetime) -> None:
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return at.astimezone(tz) if tz is not None else at.replace(tzinfo=None)

    for module in modules:
        if hasattr(module, "datetime"):
            module.datetime = _Frozen


def _sidecar_summary(answer: str, sidecar: dict[str, Any]) -> dict[str, Any]:
    degraded = sidecar.get("degraded") or {}
    return {
        "published": not degraded,
        "degraded_code": degraded.get("code"),
        "sources": [[s["url"], s.get("source_date")] for s in sidecar["sources"]],
        "rows": len(sidecar["rows"]),
        "answer": answer[:240],
    }


def _run_case(case: Case) -> dict[str, Any]:
    import httpx
    from argus.agent_runtime import research_grounded as grounded
    from argus.agent_runtime.research_query import ResearchQueryExtraction
    from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
    from argus.agent_runtime.state.models import RunState, StrategySummary, UserState
    from argus.domain.research import source_selection
    from argus.domain.research.cache import cache_clear
    from argus.domain.research.perplexity_agent import (
        PerplexityAgentClient,
        _packet_from_response,
    )

    response, instant = _recorded(case)
    asked_at = datetime.fromisoformat(instant).astimezone(timezone.utc)
    _freeze([grounded, source_selection], asked_at)
    cache_clear()

    class _Replay(httpx.BaseTransport):
        requests = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            type(self).requests += 1
            return httpx.Response(200, json=response)

    grounded._client = lambda: PerplexityAgentClient("replay", transport=_Replay())
    query = ResearchQueryExtraction(
        question_kind=case.question_kind,
        symbols=list(case.symbols),
        period_of_interest=case.period_of_interest,
    )
    subjects = [
        {"symbol": symbol, "name": NAMES[symbol], "asset_class": "equity"}
        for symbol in case.symbols
    ]
    interpretation = StructuredInterpretation(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        user_goal_summary="question",
        semantic_turn_act="educational_question",
        requires_clarification=False,
        candidate_strategy_draft=StrategySummary(),
    )
    user = UserState(user_id="replay", language_preference=case.language)
    job = grounded.thorough_job_result(
        query=query,
        subjects=subjects,
        interpretation=interpretation,
        user=user,
        message=case.question,
    )
    request = job.stage_patch["research_job_request"]
    if case.path == "background":
        packet = _packet_from_response(response, latency_ms=1, on_unpriced=lambda _: None)
        composed = grounded.compose_completed_research(job_request=request, packet=packet)
        summary = _sidecar_summary(composed["answer"], composed["research"])
    else:
        result = asyncio.run(
            grounded.grounded_result(
                query=query,
                subjects=subjects,
                shape=grounded.shape_for_query(query),
                interpretation=interpretation,
                state=RunState.new(
                    current_user_message=case.question, recent_thread_history=[]
                ),
                user=user,
            )
        )
        patch = result.stage_patch
        summary = _sidecar_summary(patch["assistant_response"], patch["research"])
    retrieved = _packet_from_response(response, latency_ms=1, on_unpriced=lambda _: None)
    usage = retrieved.usage
    return {
        **asdict(case),
        "asked_at": asked_at.isoformat(),
        "question_date": request["question_as_of_date"],
        "provider_requests": _Replay.requests,
        "retrieval_record": {
            "finance_search_invocations": usage.finance_search_invocations,
            "web_search_invocations": usage.web_search_invocations,
            "fetch_url_invocations": usage.fetch_url_invocations,
            "tool_results": list(retrieved.tool_results),
            "sources_before_selection": [
                [source.url, source.source_date] for source in retrieved.sources
            ],
        },
        **summary,
    }


def run(tree: Path, label: str, head: str, out: Path) -> None:
    _hermetic_env()
    sys.path.insert(0, str(tree / "src"))
    import argus

    document = {
        "label": label,
        "tree_head": head,
        "argus_module": str(Path(argus.__file__).resolve().relative_to(tree.resolve())),
        "cases": [_run_case(case) for case in CASES],
    }
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def _cell(case: dict[str, Any]) -> str:
    verdict = "published" if case["published"] else f"`{case['degraded_code']}`"
    return f"{verdict}, {len(case['sources'])} sources, {case['rows']} rows"


def compare(before_path: Path, after_path: Path, out: Path) -> None:
    before = json.loads(before_path.read_text())
    after = json.loads(after_path.read_text())
    lines = [
        f"# Replay: {before['label']} `{before['tree_head']}` against "
        f"{after['label']} `{after['tree_head']}`",
        "",
        "Generated by `drivers/replay.py compare`. Question date is the date each "
        "tree's background job request carries at the recorded instant.",
        "",
        "| Case | Asked (UTC) | Question date before / after | Before | After | Changed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for old, new in zip(before["cases"], after["cases"], strict=True):
        assert old["name"] == new["name"]
        changed = (
            old["published"] != new["published"]
            or old["degraded_code"] != new["degraded_code"]
            or old["sources"] != new["sources"]
            or old["rows"] != new["rows"]
        )
        lines.append(
            f"| {old['name']} | {old['asked_at'][:16]} | {old['question_date']} / "
            f"{new['question_date']} | {_cell(old)} | {_cell(new)} | "
            f"{'**yes**' if changed else 'no'} |"
        )
    out.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--tree", type=Path, required=True)
    run_parser.add_argument("--label", required=True)
    run_parser.add_argument("--head", required=True)
    run_parser.add_argument("--out", type=Path, required=True)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("before", type=Path)
    compare_parser.add_argument("after", type=Path)
    compare_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        run(args.tree, args.label, args.head, args.out)
    else:
        compare(args.before, args.after, args.out)


if __name__ == "__main__":
    main()
