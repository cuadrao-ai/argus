"""Shared research-rail fixtures: hermetic provider shapes, no live calls."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import pytest

RECORDED_PROBES = Path(__file__).resolve().parents[2] / "docs/reports/evidence/377/probes"
RETRIEVAL_PROBES = (
    Path(__file__).resolve().parents[2] / "docs/reports/evidence/545/probes"
)
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def recorded_agent_response(
    name: str = "perplexity_fast_quote_2026-09-09",
) -> dict[str, Any]:
    """An actual captured response, including its independent invoice.

    The default is a frozen copy of the 2026-09-09 fast quote, billed at the
    schedule the provider bills today; a copy, so re-recording the probe under
    docs/reports/evidence/545 cannot move the invoice every canned document
    bills at. Probes there and the 2026-08-07 recordings under 377, billed at
    the earlier published schedule, stay reachable by name."""
    for path in (FIXTURES / f"{name}.json", RETRIEVAL_PROBES / f"{name}.json"):
        if path.exists():
            return json.loads(path.read_text())["exchanges"][-1]["response"]
    return json.loads((RECORDED_PROBES / f"{name}.json").read_text())["response"]


@pytest.fixture(autouse=True)
def research_rail_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "synthetic_unit_fixture")
    from argus.domain.research.cache import cache_clear

    cache_clear()
    yield
    cache_clear()


def agent_response(
    *,
    text: str = "Apple closed at $312.41 on 2026-08-06.",
    tickers: list[str] | None = None,
    lookup_rows: list[tuple[str, str, str]] | None = None,
    sources: list[str] | None = None,
    invocations: int = 1,
    web_search_invocations: int = 0,
    fetch_url_invocations: int = 0,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_creation_input_tokens: int | None = None,
    cache_read_input_tokens: int | None = None,
    model: str = "openai/gpt-5.6-sol",
    cost_overrides: dict[str, Any] | None = None,
    response_id: str = "resp_test",
    status: str | None = None,
) -> dict[str, Any]:
    """A Perplexity Agent API response in the documented output shape."""
    results: list[dict[str, Any]] = [
        {
            "category": "quote",
            "content": "## Quote\n| symbol | price |\n| --- | --- |\n| AAPL | 312.41 |",
            "sources": list(sources or []),
            "tickers": list(tickers or ["AAPL"]),
        }
    ]
    if lookup_rows:
        table = "Ticker matches:\n| query | ticker | name |\n| --- | --- | --- |\n"
        table += "\n".join(
            f"| {query} | {ticker} | {name} |" for query, ticker, name in lookup_rows
        )
        results.append({"category": "tickers_lookup", "content": table, "sources": []})
    if invocations == 0 and (tickers or lookup_rows or sources):
        raise ValueError(
            "a response whose finance tool never ran carries no finance rows; "
            "pass invocations>=1 or drop tickers, lookup_rows and sources"
        )
    # Recorded zero-tool responses carry no finance_results item and omit
    # usage.tool_calls_details entirely; only tools that ran are reported.
    tool_calls_details: dict[str, dict[str, int]] = {}
    if invocations:
        tool_calls_details["finance_search"] = {"invocation": invocations}
    if web_search_invocations:
        # The request tool is web_search; Agent API usage currently reports
        # the provider-owned response key as search_web.
        tool_calls_details["search_web"] = {"invocation": web_search_invocations}
    if fetch_url_invocations:
        tool_calls_details["fetch_url"] = {"invocation": fetch_url_invocations}
    recorded_usage = recorded_agent_response()["usage"]
    # Keep captured billing unchanged. Counter overrides are synthetic test
    # perturbations; tests about reconciled pricing must give an explicit bill.
    input_tokens = (
        recorded_usage["input_tokens"] if input_tokens is None else input_tokens
    )
    output_tokens = (
        recorded_usage["output_tokens"] if output_tokens is None else output_tokens
    )
    input_details = recorded_usage["input_tokens_details"]
    if cache_creation_input_tokens is None:
        cache_creation_input_tokens = input_details["cache_creation_input_tokens"]
    if cache_read_input_tokens is None:
        cache_read_input_tokens = input_details["cache_read_input_tokens"]
    cost = deepcopy(recorded_usage["cost"])
    if cost_overrides:
        cost.update(cost_overrides)
    document: dict[str, Any] = {
        "id": response_id,
        "model": model,
        "output": [
            {"type": "skill_loaded", "name": "finance"},
            *(
                [
                    {
                        "type": "finance_results",
                        "categories": [item["category"] for item in results],
                        "tickers": list(tickers or ["AAPL"]),
                        "results": results,
                    }
                ]
                if invocations
                else []
            ),
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
        ],
        "usage": {
            "cost": cost,
            "input_tokens": input_tokens,
            "input_tokens_details": {
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "cached_tokens": cache_read_input_tokens,
            },
            "output_tokens": output_tokens,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": input_tokens + output_tokens,
            **({"tool_calls_details": tool_calls_details} if tool_calls_details else {}),
        },
    }
    if status is not None:
        document["status"] = status
    return document


class RecordingTransport(httpx.BaseTransport):
    """Serves canned agent documents and records every request."""

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = list(documents)
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.documents:
            # An exhausted script is an outage that asks for a wait longer than
            # any call's deadline, so the client fails at once instead of
            # retrying on a real clock.
            return httpx.Response(
                500, headers={"Retry-After": "86400"}, json={"error": "exhausted"}
            )
        document = self.documents.pop(0)
        return httpx.Response(200, json=document)


def request_body(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content.decode())


def set_research_query(monkeypatch, namespace, **fields):
    """Supply the primary interpretation at the router test boundary."""
    from argus.agent_runtime.research_query import ResearchQueryExtraction

    # A test module with its own interpretation builder is patched there; a
    # module that runs turns through run_research_turn is patched here.
    target = namespace if "_interpretation" in namespace else globals()
    original = target["_interpretation"]
    query = ResearchQueryExtraction(**fields)

    def interpreted(*args, **kwargs):
        return original(*args, **kwargs).model_copy(update={"research_query": query})

    monkeypatch.setitem(target, "_interpretation", interpreted)


def typed_answer_text(
    answer: str,
    rows: list[dict[str, Any]],
    calculation: dict[str, Any] | None = None,
    follow_up_questions: list[str] | None = None,
    declined: bool = False,
    source_urls: list[str] | None = None,
) -> str:
    """The provider's message text under the strict typed answer schema: the
    pages it names, and its one calculation, when given, as a list of one."""
    return json.dumps(
        {
            "answer_markdown": answer,
            "rows": rows,
            "source_urls": source_urls or [],
            "calculations": [calculation] if calculation else [],
            "follow_up_questions": follow_up_questions or [],
            "declined": declined,
        }
    )


def retrieved_row(
    *,
    subject: str = "NVIDIA",
    symbol: str | None = "NVDA",
    label: str = "share price change today",
    value: float = -4.3,
    kind: str = "percent",
    unit: str = "%",
    as_of: str | None = "2026-09-04",
    source_url: str | None = "https://www.perplexity.ai/finance/NVDA",
) -> dict[str, Any]:
    """One row in the shape the schema requires: every field present."""
    return {
        "subject": subject,
        "symbol": symbol,
        "label": label,
        "value": value,
        "kind": kind,
        "unit": unit,
        "as_of": as_of,
        "source_url": source_url,
    }


def search_results_item(*results: dict[str, Any]) -> dict[str, Any]:
    """A web search output item carrying the given publisher results."""
    return {"type": "search_results", "results": list(results)}


def fetch_url_results_item(*contents: dict[str, Any]) -> dict[str, Any]:
    """A fetched-pages output item: title, url and an excerpt per page."""
    return {"type": "fetch_url_results", "contents": list(contents)}


# --- grounded-turn builders shared by the retrieval and withheld-answer suites

PUBLISHER = "https://www.barrons.com/articles/nvidia-nvda-stock-price"
PROVIDER_PAGE = "https://www.perplexity.ai/finance/NVDA"
RESEARCH_USER_ID = "retrieval"


def educational_interpretation():
    from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
    from argus.agent_runtime.state.models import StrategySummary

    return StructuredInterpretation(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        user_goal_summary="question",
        semantic_turn_act="educational_question",
        requires_clarification=False,
        candidate_strategy_draft=StrategySummary(),
    )






# The builder run_research_turn reads at call time, so set_research_query can
# supply the primary question payload for modules that share the runner.
_interpretation = educational_interpretation


def typed_document(rows: list[dict[str, Any]], *, answer: str) -> dict[str, Any]:
    """A typed NVDA answer that retrieved one publisher page and the
    provider's finance data."""
    document = agent_response(
        text=typed_answer_text(answer, rows),
        tickers=["NVDA"],
        sources=[PROVIDER_PAGE],
        web_search_invocations=1,
    )
    document["output"].insert(
        1,
        search_results_item(
            {"url": PUBLISHER, "title": "Nvidia stock falls", "date": "2026-09-04"}
        ),
    )
    return document


def rows_with_one_rejected() -> list[dict[str, Any]]:
    """Two rows, one cited to the publisher page and one to a page nothing
    retrieved."""
    return [
        retrieved_row(source_url=PUBLISHER),
        retrieved_row(
            label="analyst target price",
            value=250.0,
            kind="currency",
            unit="USD",
            source_url="https://invented.example/target",
        ),
    ]


@pytest.fixture
def collision_catalog(monkeypatch, tmp_path):
    from argus.domain.market_data import assets

    listings = [
        ("BTC", "Grayscale Bitcoin Mini Trust ETF", "us_equity"),
        ("IBIT", "iShares Bitcoin Trust ETF", "us_equity"),
        ("AAPL", "Apple Inc.", "us_equity"),
        ("MSFT", "Microsoft Corporation", "us_equity"),
        ("BTC/USD", "Bitcoin", "crypto"),
        ("ETH/USD", "Ethereum", "crypto"),
        ("SOL/USD", "Solana", "crypto"),
        ("SPY", "SPDR S&P 500 ETF Trust", "us_equity"),
    ]
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "alpaca_assets": [
                    {
                        "symbol": symbol,
                        "name": name,
                        "asset_class": cls,
                        "status": "active",
                    }
                    for symbol, name, cls in listings
                ],
                "kraken_asset_pairs": {},
            }
        )
    )
    monkeypatch.setenv("ARGUS_ASSET_PROVIDER_MODE", "recorded_provider_fixture")
    monkeypatch.setenv("ARGUS_ASSET_FIXTURE_PATH", str(path))
    assets.clear_asset_cache()
    from argus.domain.market_data import tradability

    monkeypatch.setattr(
        tradability, "_probe", lambda symbol, cls: tradability.TradableHistory("tradable")
    )
    tradability.clear_tradable_history_cache()
    etf = assets.ResolvedAsset("BTC", "equity", listings[0][1], "BTC", "alpaca")
    # The exact provider lookup is the external boundary that favors the ETF.
    monkeypatch.setattr(
        assets,
        "_resolve_live_provider_ticker",
        lambda symbol: etf if symbol == "BTC" else None,
    )
    yield
    assets.clear_asset_cache()
    tradability.clear_tradable_history_cache()
