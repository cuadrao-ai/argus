"""A retrieved answer publishes: one owner at the composition seam.

PR #562 withheld a whole answer whenever one typed row cited a page the
response had not retrieved, or a typed answer wrote no row. Perplexity's
finance tool answers a price with its own page as the source, the model often
cites a different plausible page instead, and every such quote was paid for
and thrown away. These locks pin the reverse: a row keeps the citation the
model wrote, a figure written with no citation is named under the answer, the
answer itself is never withheld for a row, and the only withholding left is a
turn that retrieved nothing (#580) or a survey that names nothing the resolver
verifies.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from argus.agent_runtime import research_grounded as grounded

from tests.research.conftest import (
    PROVIDER_PAGE,
    PUBLISHER,
    agent_response,
    fetch_url_results_item,
    retrieved_row,
    rows_with_one_rejected,
    run_research_turn,
    search_results_item,
    set_research_query,
    typed_answer_text,
    typed_document,
    wire_grounded_client,
)

_wire = wire_grounded_client
_run = run_research_turn
_typed_document = typed_document
INVENTED = "https://invented.example/target"


def _unsourced_price_rows() -> list[dict]:
    """One row cited to the provider's finance data, one the model wrote
    with no citation at all."""
    return [
        retrieved_row(
            subject="Apple",
            symbol="AAPL",
            label="share price",
            value=200.0,
            kind="currency",
            unit="USD",
            source_url=PROVIDER_PAGE,
        ),
        retrieved_row(
            subject="Apple",
            symbol="AAPL",
            label="analyst target price",
            value=250.0,
            kind="currency",
            unit="USD",
            source_url=None,
        ),
    ]


def test_a_row_citing_a_page_outside_the_retrieval_record_publishes(monkeypatch) -> None:
    """The defect this lane exists for: the model cited a plausible page the
    response had not retrieved, the row was rejected for it, and the whole
    answer was withheld. The citation is the model's own and the answer
    publishes with it."""
    set_research_query(
        monkeypatch, globals(), question_kind="current_external", symbols=["NVDA"]
    )
    prose = "NVIDIA fell **4.3%** and analysts now target **$250**."
    transport = _wire(
        monkeypatch, [_typed_document(rows_with_one_rejected(), answer=prose)] * 2
    )

    result = _run("Why is NVDA moving this week?")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert "degraded" not in sidecar
    assert result.stage_patch["assistant_response"] == prose
    assert [row["source_url"] for row in sidecar["rows"]] == [PUBLISHER, INVENTED]
    assert [source["url"] for source in sidecar["sources"]] == [PUBLISHER]
    assert sidecar["anchor_symbols"] == ["NVDA"]
    assert result.stage_patch["next_experiments"]["rows"]

    served = _run("Why is NVDA moving this week?")
    assert served is not None
    assert len(transport.requests) == 2, "freeform answers are regenerated per request"
    assert served.stage_patch["research"]["usage"]["cache_status"] == "miss"
    assert served.stage_patch["research"]["rows"] == sidecar["rows"]


@pytest.mark.parametrize(
    ("language", "note"),
    [
        ("en", "I couldn't tie Apple analyst target price to a source."),
        ("es-419", "No pude vincular Apple analyst target price a una fuente."),
    ],
)
def test_a_figure_written_without_a_citation_is_named_under_the_answer(
    monkeypatch, language: str, note: str
) -> None:
    """The row the model left uncited stays in the answer and in the rows;
    the turn says, beneath the answer, that it could not tie that figure to
    a source, named from the row's own typed subject and label."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    prose = "AAPL is **$200** today and analysts target **$250**."
    _wire(
        monkeypatch,
        [
            agent_response(
                text=typed_answer_text(prose, _unsourced_price_rows()),
                sources=[PROVIDER_PAGE],
            )
        ],
    )

    result = _run("What is Apple at?", language=language)

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert "degraded" not in sidecar
    assert result.stage_patch["assistant_response"].startswith(prose)
    assert result.stage_patch["assistant_response"].endswith(note)
    assert [(row["label"], row["source_url"]) for row in sidecar["rows"]] == [
        ("share price", None),
        ("analyst target price", None),
    ]
    assert sidecar["anchor_symbols"] == ["AAPL"]


def test_the_thorough_path_composes_the_same_published_answer() -> None:
    """Job composition publishes the same answer without sharing private context."""
    from argus.domain.research.cache import cache_get, cache_stats
    from argus.domain.research.perplexity_agent import _packet_from_response

    prose = "Netflix grew **16%** and analysts target **$250**."
    document = agent_response(
        text=typed_answer_text(
            prose,
            [
                retrieved_row(
                    subject="Netflix",
                    symbol="NFLX",
                    label="revenue growth",
                    value=16.0,
                    source_url=INVENTED,
                ),
                retrieved_row(
                    subject="Netflix",
                    symbol="NFLX",
                    label="analyst target price",
                    value=250.0,
                    kind="currency",
                    unit="USD",
                    source_url=None,
                ),
            ],
        ),
        tickers=["NFLX"],
        sources=[PROVIDER_PAGE],
    )
    # Composition still recognizes quarterly finance data.
    for item in document["output"]:
        if item.get("type") == "finance_results":
            item["categories"] = ["financials"]
            for result in item["results"]:
                result["category"] = "financials"
    packet = _packet_from_response(document, latency_ms=1, on_unpriced=lambda _: None)
    key = "research-packet/v1:legacy-job-key"
    job_request = {
        "capability_class": "thorough_research",
        "language": "es-419",
        "question_kind": "company_lookup",
        "subjects": [{"symbol": "NFLX", "name": "Netflix", "asset_class": "equity"}],
        "cache_key": key,
    }

    composed = grounded.compose_completed_research(job_request=job_request, packet=packet)
    grounded.store_research_packet_for_job(job_request, packet, composed)

    assert "degraded" not in composed["research"]
    assert composed["answer"].startswith(prose)
    assert (
        "No pude vincular Netflix analyst target price a una fuente."
        in composed["answer"]
    )
    assert [row["source_url"] for row in composed["research"]["rows"]] == [INVENTED, None]
    assert cache_get(key) is None
    assert cache_stats()["entries"] == 0


@pytest.mark.parametrize(
    ("question_kind", "document", "figure"),
    [
        (
            "current_external",
            lambda: _typed_document(rows_with_one_rejected(), answer="Fell **4.3%**."),
            "4.3",
        ),
        (
            "live_quote",
            lambda: agent_response(text=typed_answer_text("AAPL is **$200** today.", [])),
            "200",
        ),
    ],
)
def test_no_answer_is_withheld_for_its_rows(
    monkeypatch, question_kind: str, document, figure: str
) -> None:
    """Every retrieved shape #562 withheld for a row or a missing row now
    publishes what the provider wrote. The strict schema is what keeps a
    figure from memory unrepresentable; composition does not second-guess
    it."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind=question_kind,
        symbols={"current_external": ["NVDA"], "live_quote": ["AAPL"]}[question_kind],
    )
    _wire(monkeypatch, [document()])

    result = _run("what about it")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert "degraded" not in sidecar
    assert figure in result.stage_patch["assistant_response"]
    assert result.stage_patch["next_experiments"]["rows"]


APPLE_PAGE = "https://www.cnbc.com/quotes/AAPL"


@pytest.mark.parametrize(
    ("counts", "retrieved"),
    [
        ({"invocations": 1}, None),
        (
            {"invocations": 0, "web_search_invocations": 1},
            search_results_item({"url": APPLE_PAGE, "title": "Apple stock"}),
        ),
        (
            {"invocations": 0, "fetch_url_invocations": 1},
            fetch_url_results_item(
                {"url": APPLE_PAGE, "title": "Apple stock", "snippet": "AAPL $200"}
            ),
        ),
    ],
    ids=["finance_search", "web_search", "fetch_url"],
)
def test_an_answer_that_retrieved_through_any_tool_publishes(
    monkeypatch, counts: dict, retrieved: dict | None
) -> None:
    """The gate asks whether the response retrieved, not through which tool:
    one retrieval of any kind and the answer publishes as written."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    prose = "AAPL is **$200** today."
    document = agent_response(
        text=typed_answer_text(
            prose,
            [
                retrieved_row(
                    subject="Apple",
                    symbol="AAPL",
                    label="price",
                    value=200.0,
                    kind="currency",
                    unit="USD",
                    source_url=APPLE_PAGE,
                )
            ],
        ),
        **counts,
    )
    if retrieved is not None:
        document["output"].insert(1, retrieved)
    _wire(monkeypatch, [document])

    result = _run("What is Apple at?")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert "degraded" not in sidecar
    assert result.stage_patch["assistant_response"] == prose
    assert [row["source_url"] for row in sidecar["rows"]] == [APPLE_PAGE]


NOT_GROUNDED_NOTES = {
    "en": "I couldn't retrieve the data to answer this question.",
    "es-419": "No pude recuperar los datos para responder esta pregunta.",
}


@pytest.mark.parametrize("language", ["en", "es-419"])
@pytest.mark.parametrize(
    "text",
    [
        typed_answer_text(
            "AAPL is **$200** today.",
            [
                retrieved_row(
                    subject="Apple",
                    symbol="AAPL",
                    label="price",
                    value=200.0,
                    kind="currency",
                    unit="USD",
                    source_url=None,
                )
            ],
        ),
        typed_answer_text("AAPL is **$200** today.", []),
        "AAPL is **$200** today.",
    ],
    ids=["typed-with-a-row", "typed-without-rows", "prose"],
)
def test_an_answer_that_retrieved_nothing_is_not_grounded(
    monkeypatch, language: str, text: str
) -> None:
    """#580: a response that used no retrieval tool has no source for anything
    it says, whatever form its text takes. It is withheld the way a survey
    that never looked is: the note says so, the subject stays testable, and
    nothing is stored for the next user who asks."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    document = agent_response(text=text, invocations=0)
    transport = _wire(monkeypatch, [document, document])

    result = _run("What is Apple at?", language=language)

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "research_not_grounded"}
    assert result.stage_patch["assistant_response"] == NOT_GROUNDED_NOTES[language]
    assert sidecar["rows"] == [] and sidecar["sources"] == []
    assert sidecar["anchor_symbols"] == ["AAPL"]
    assert result.stage_patch["next_experiments"]["rows"]

    _run("What is Apple at?", language=language)
    assert len(transport.requests) == 2, "a turn that retrieved nothing is never stored"


@pytest.mark.parametrize(
    ("question_kind", "requires_publisher_sources"),
    [("current_external", False), ("company_lookup", False), ("live_quote", True)],
    ids=["current_external", "company_lookup", "quote-with-a-claim"],
)
def test_a_claim_that_retrieved_nothing_is_not_grounded_before_it_lacks_a_publisher(
    monkeypatch, question_kind: str, requires_publisher_sources: bool
) -> None:
    """A claim-shaped answer that retrieved nothing never had a page to find a
    publisher on, so it is the retrieval failure rather than a missing public
    source, after the one publisher retry that still runs."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind=question_kind,
        symbols=["NVDA"],
        requires_publisher_sources=requires_publisher_sources,
    )
    document = agent_response(
        text=typed_answer_text("NVIDIA fell **4.3%** this week.", []), invocations=0
    )
    transport = _wire(monkeypatch, [document, document])

    result = _run("Why is NVDA moving this week?")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "research_not_grounded"}
    assert result.stage_patch["assistant_response"] == NOT_GROUNDED_NOTES["en"]
    assert len(transport.requests) == 2, "the one publisher retry still runs"


@pytest.mark.parametrize("requires_publisher_sources", [False, True])
def test_the_thorough_path_withholds_an_answer_that_retrieved_nothing(
    requires_publisher_sources: bool,
) -> None:
    """The background run composes through the same gate: a thorough answer
    whose response used no retrieval tool is not published and not stored,
    whether or not its claim needed a publisher."""
    from argus.domain.research.cache import cache_get, cache_stats
    from argus.domain.research.perplexity_agent import _packet_from_response

    packet = _packet_from_response(
        agent_response(
            text=typed_answer_text("Netflix grew **16%** last year.", []),
            invocations=0,
        ),
        latency_ms=1,
        on_unpriced=lambda _: None,
    )
    key = "research-packet/v1:legacy-job-key"
    job_request = {
        "capability_class": "thorough_research",
        "language": "es-419",
        "question_kind": "cross_company",
        "requires_publisher_sources": requires_publisher_sources,
        "subjects": [{"symbol": "NFLX", "name": "Netflix", "asset_class": "equity"}],
        "cache_key": key,
    }

    composed = grounded.compose_completed_research(job_request=job_request, packet=packet)
    grounded.store_research_packet_for_job(job_request, packet, composed)

    assert composed["research"]["degraded"] == {"code": "research_not_grounded"}
    assert composed["answer"].startswith(NOT_GROUNDED_NOTES["es-419"])
    assert "16" not in composed["answer"]
    assert composed["research"]["rows"] == []
    assert cache_get(key) is None
    assert cache_stats()["entries"] == 0


def test_a_survey_that_never_retrieved_is_still_not_grounded(monkeypatch) -> None:
    """The one withholding that survives is the survey's own, from before
    #562: a model that did not look is evidence about the model, not the
    world, so nothing is stored and the next identical question is asked
    afresh."""
    set_research_query(monkeypatch, globals(), question_kind="market_pulse", symbols=[])
    document = agent_response(
        text=typed_answer_text(
            "NVDA (NVDA) rose **4.3%**.", [retrieved_row(label="change", value=4.3)]
        ),
        invocations=0,
    )
    transport = _wire(monkeypatch, [document] * 4)

    result = _run("anything interesting moving today")

    assert result is not None
    assert len(transport.requests) == 2, "the concrete retry still fires once"
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "survey_not_grounded"}
    assert result.stage_patch["assistant_response"] == (
        "I couldn't retrieve today's market movers."
    )
    assert sidecar["rows"] == [] and sidecar["sources"] == []

    _run("anything interesting moving today")
    assert len(transport.requests) == 4, "a survey that never retrieved is not stored"


def test_a_survey_naming_nothing_the_resolver_verifies_is_withheld_without_sharing(
    monkeypatch,
) -> None:
    """A survey with cited rows whose prose names no tradable ticker is
    withheld by composition; subsequent requests still run independently."""
    set_research_query(monkeypatch, globals(), question_kind="market_pulse", symbols=[])
    document = agent_response(
        text=typed_answer_text(
            "ZZZZFAKE led the gainers, up 9.1%.",
            [
                retrieved_row(
                    subject="ZZZZFAKE", symbol="ZZZZFAKE", label="change today", value=9.1
                )
            ],
        ),
        tickers=["ZZZZFAKE"],
        sources=[PROVIDER_PAGE],
    )
    for item in document["output"]:
        if item.get("type") == "finance_results":
            item["categories"] = ["financials"]
            for result in item["results"]:
                result["category"] = "financials"
    transport = _wire(monkeypatch, [document, document])

    result = _run("what is moving today")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "survey_synthesis_incomplete"}
    assert sidecar["rows"] == [] and sidecar["peers"] == []
    assert "next_experiments" not in result.stage_patch
    assert len(transport.requests) == 1

    served = _run("what is moving today")
    assert served is not None
    assert len(transport.requests) == 2, "withheld answers are not shared"
    assert served.stage_patch["research"]["usage"]["cache_status"] == "miss"


def test_a_survey_that_names_a_verified_ticker_publishes_whatever_its_rows(
    monkeypatch,
) -> None:
    """#562 degraded a survey that retrieved and named a ticker but wrote no
    row. Stating no figure is the model's honesty, not a defect: after the
    one concrete retry the prose publishes with the name the resolver
    verified from the packet's own typed tickers."""
    set_research_query(monkeypatch, globals(), question_kind="market_pulse", symbols=[])
    today = datetime.now(timezone.utc).date().isoformat()
    figureless = agent_response(
        text=typed_answer_text(
            "NVIDIA (NVDA) led today's session, but I could not retrieve its figures.",
            [],
            source_urls=[PUBLISHER],
        ),
        tickers=["NVDA"],
        sources=[PROVIDER_PAGE],
        web_search_invocations=1,
    )
    figureless["output"].insert(
        1, search_results_item({"url": PUBLISHER, "title": "Movers", "date": today})
    )
    transport = _wire(monkeypatch, [figureless, figureless])

    result = _run("anything interesting moving today")

    assert result is not None
    assert len(transport.requests) == 2, "one concrete retry, never a loop"
    sidecar = result.stage_patch["research"]
    assert "degraded" not in sidecar
    assert sidecar["anchor_symbols"] == ["NVDA"]
    assert sidecar["rows"] == []
    assert [source["url"] for source in sidecar["sources"]] == [PUBLISHER]
    assert result.stage_patch["assistant_response"].startswith("NVIDIA (NVDA) led")
    assert result.stage_patch["next_experiments"]["rows"]


def test_a_survey_naming_a_ticker_the_packet_never_typed_stays_degraded(
    monkeypatch,
) -> None:
    """The survey rule that predates #562 and stays: a name only the prose
    carries is not one the resolver verified."""
    set_research_query(monkeypatch, globals(), question_kind="market_pulse", symbols=[])
    figureless = agent_response(
        text=typed_answer_text(
            "I could not retrieve current figures for NVIDIA (NVDA).",
            [],
            source_urls=[PUBLISHER],
        ),
        invocations=0,
        web_search_invocations=1,
    )
    today = datetime.now(timezone.utc).date().isoformat()
    figureless["output"].insert(
        1, search_results_item({"url": PUBLISHER, "title": "Movers", "date": today})
    )
    _wire(monkeypatch, [figureless, figureless])

    result = _run("anything interesting moving today")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "survey_synthesis_incomplete"}
    assert sidecar["anchor_symbols"] == [] and sidecar["rows"] == []
    assert [source["url"] for source in sidecar["sources"]] == [PUBLISHER]


def test_the_sidecar_builder_owns_the_degraded_shape() -> None:
    sidecar = grounded.build_research_sidecar(
        capability_class="balanced_lookup",
        shape="balanced",
        sources=[],
        retrieved_at="2026-09-08T00:00:00+00:00",
        subjects=[],
        peers=[],
        usage={},
        period_of_interest=None,
        degraded_code="anything",
        retrieved_rows=[retrieved_row()],
    )
    assert sidecar["rows"] == []


def test_a_broken_typed_answer_never_reaches_the_reader(monkeypatch) -> None:
    """JSON-shaped text that is not the schema is a broken contract, not
    prose: the strict schema is the honesty line and stays. The turn says
    the lookup did not complete and asks the provider again next time."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    truncated = '{"answer_markdown": "AAPL is $200 today", "rows": [{"label": "AAPL", "va'
    transport = _wire(
        monkeypatch,
        [agent_response(text=truncated), agent_response(text=truncated)],
    )

    result = _run("What is Apple at?")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "research_unavailable_malformed_response"}
    answer = result.stage_patch["assistant_response"]
    assert result.stage_patch["recovery"] == {
        "code": "research_lookup_unavailable",
        "retryable": False,
    }
    assert "200" not in answer and "answer_markdown" not in answer
    assert sidecar["rows"] == [] and sidecar["sources"] == []

    _run("What is Apple at?")
    assert len(transport.requests) == 2, "a broken answer is never served from cache"


RECORDED_LOCAL_PROBE = (
    Path(__file__).resolve().parents[2]
    / "docs/reports/evidence/545/probes/domain_filtered_local_source_568.json"
)


def _naming_the_pages_it_read(response: dict) -> dict:
    """The recorded response with its typed answer naming the bank pages it read,
    as the typed answer now does; it was recorded before the schema had the field."""
    named = copy.deepcopy(response)
    read = [
        result["url"]
        for item in named["output"]
        if item.get("type") == "search_results"
        for result in item.get("results") or []
        if "popularenlinea.com" in str(result.get("url"))
    ]
    for item in named["output"]:
        for chunk in item.get("content") or [] if item.get("type") == "message" else []:
            typed = json.loads(chunk["text"])
            typed["source_urls"] = read
            chunk["text"] = json.dumps(typed)
    return named


def test_the_recorded_local_probe_publishes_what_it_found(monkeypatch) -> None:
    """The live recording #568 replayed: eleven pages on the bank's own site
    and no rate on any of them. The provider's answer says so in its own
    words, states no figure, and is what the reader gets, with the site it
    read as its sources; each identical question still runs independently."""
    set_research_query(
        monkeypatch, globals(), question_kind="current_external", symbols=[]
    )
    recorded = _naming_the_pages_it_read(
        json.loads(RECORDED_LOCAL_PROBE.read_text())["exchanges"][-1]["response"]
    )
    transport = _wire(monkeypatch, [recorded, recorded])
    question = (
        "¿Qué tasa de interés paga hoy el Banco Popular Dominicano por un "
        "certificado financiero a un año en pesos?"
    )

    result = _run(question, language="es-419")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert "degraded" not in sidecar
    assert sidecar["rows"] == []
    assert "%" not in result.stage_patch["assistant_response"]
    assert [source["domain"] for source in sidecar["sources"]] == ["popularenlinea.com"]

    served = _run(question, language="es-419")
    assert served is not None
    assert len(transport.requests) == 2
    assert served.stage_patch["research"]["usage"]["cache_status"] == "miss"


RECORDED_NIKE_QUOTE = (
    Path(__file__).resolve().parents[2]
    / "docs/reports/evidence/open-the-gates/probes/nike-fast-1.json"
)


def test_the_recorded_nike_quote_still_publishes(monkeypatch) -> None:
    """The quote #578 reopened: one finance lookup and the provider's own page
    as its evidence. It retrieved, so the gate on a turn that retrieved
    nothing leaves it as it was."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["NKE"]
    )
    recorded = json.loads(RECORDED_NIKE_QUOTE.read_text())["response"]
    assert recorded["usage"]["tool_calls_details"]["finance_search"]["invocation"] == 1
    _wire(monkeypatch, [recorded])

    result = _run("what's the price of nike today")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert "degraded" not in sidecar
    assert "$37.35" in result.stage_patch["assistant_response"]
    assert [row["value"] for row in sidecar["rows"]] == [37.35]
