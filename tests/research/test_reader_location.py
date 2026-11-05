"""Research sends the asking user's country as the location, on both paths.

A country is a declared profile setting. A research request built for a user
with one carries it as the web search's ``user_location``; a request built for
a user with none carries no location. Every request here is recorded by a
transport that answers from canned documents, so no provider is called.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from argus.agent_runtime import research_grounded as grounded
from argus.api import state as api_state
from argus.api.chat import research_jobs
from argus.domain.research.perplexity_agent import PerplexityAgentClient

from tests.research.conftest import (
    PUBLISHER,
    RecordingTransport,
    request_body,
    retrieved_row,
    run_research_turn,
    set_research_query,
    typed_document,
    wire_grounded_client,
)

COUNTRIES = [("MX", {"country": "MX"}), (None, None)]
# The prompt names the reader's country so the answer never assumes another.
READER_LINE = "The reader lives in Mexico (MX)"


def _answer() -> dict[str, Any]:
    return typed_document(
        [retrieved_row(source_url=PUBLISHER)],
        answer="NVIDIA fell **4.3%** today after a report on a partnership program.",
    )


def _user_location(request: httpx.Request) -> dict[str, str] | None:
    body = request_body(request)
    web_search = next(tool for tool in body["tools"] if tool["type"] == "web_search")
    return web_search.get("user_location")


@pytest.mark.parametrize(("country", "location"), COUNTRIES)
def test_an_inline_answer_sends_the_asking_users_country(
    monkeypatch: pytest.MonkeyPatch, country: str | None, location: dict | None
) -> None:
    set_research_query(
        monkeypatch, globals(), question_kind="current_external", symbols=["NVDA"]
    )
    transport = wire_grounded_client(monkeypatch, [_answer()])

    result = run_research_turn(
        f"Why is NVDA moving this week? ({country or 'no country'})", country=country
    )

    assert result is not None
    assert result.stage_patch["research"]["shape"] == "balanced"
    assert len(transport.requests) == 1
    assert _user_location(transport.requests[0]) == location
    assert (READER_LINE in request_body(transport.requests[0])["input"]) is bool(country)


@pytest.mark.parametrize(("country", "location"), COUNTRIES)
def test_a_thorough_job_sends_the_country_of_the_user_who_asked(
    monkeypatch: pytest.MonkeyPatch, country: str | None, location: dict | None
) -> None:
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="cross_company",
        symbols=["NVDA", "AAPL"],
    )
    staged = run_research_turn(
        f"Compare NVIDIA and Apple over three years ({country or 'no country'})",
        country=country,
    )
    assert staged is not None
    job = staged.stage_patch["research_job_request"]
    assert job["country"] == country

    # Memory mode runs the job's rebuilt request synchronously.
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    synchronous = RecordingTransport([_answer()])
    monkeypatch.setattr(
        research_jobs,
        "_client",
        lambda: PerplexityAgentClient("k", transport=synchronous),
    )
    job_row, packet = research_jobs.start_research_job(
        job_request=job,
        user_id="u1",
        conversation_id="c1",
        request_message_id="m1",
        request_id="r1",
    )
    assert job_row is None and packet is not None
    assert _user_location(synchronous.requests[0]) == location
    assert (READER_LINE in request_body(synchronous.requests[0])["input"]) is bool(
        country
    )

    # The background path submits the same request, rebuilt the same way.
    background = RecordingTransport([{"id": "resp_bg1", "status": "queued"}])
    PerplexityAgentClient("k", transport=background).submit_background(
        grounded.research_prompt_for_job(job), grounded.retrieval_spec_for_job(job)
    )
    assert request_body(background.requests[0])["background"] is True
    assert _user_location(background.requests[0]) == location
    assert (READER_LINE in request_body(background.requests[0])["input"]) is bool(country)


def test_a_job_queued_before_countries_existed_sends_no_location() -> None:
    spec = grounded.retrieval_spec_for_job(
        {"question_kind": "cross_company", "language": "en"}
    )
    assert spec.location is None


def test_a_search_made_for_one_country_never_answers_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_research_query(
        monkeypatch, globals(), question_kind="current_external", symbols=["NVDA"]
    )
    transport = wire_grounded_client(monkeypatch, [_answer() for _ in range(3)])
    message = "Why is NVDA moving this week? (reader location preserved)"

    for country in ("MX", "MX", "DO"):
        assert run_research_turn(message, country=country) is not None

    assert [_user_location(request) for request in transport.requests] == [
        {"country": "MX"},
        {"country": "MX"},
        {"country": "DO"},
    ]
