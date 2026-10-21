"""Any grounded math, steps 11 and 13: computed answers outside a turn.

Listing, comparing and continuing are free and owner-scoped; refreshing the
cited inputs is paid, claimed under the research allowance, and never rewrites
the stored answer. No computed-answer action proposes personalization memory
(decision 8).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from argus.api.main import app
from argus.api.message_store import create_message
from argus.domain.computation_marker import computation_from_tool_card
from faker import Faker
from fastapi.testclient import TestClient

from tests.domain.calculations.support import run_calculation

fake = Faker()


def _multiple(price: float) -> dict[str, Any]:
    return {
        "currency": "USD",
        "symbol": "AAPL",
        "price": price,
        "per_share": 6,
        "multiple": None,
    }


CITED_VALUATION = {
    "currency": "USD",
    "symbol": "NVDA",
    "price": 200,
    "per_share": 4,
    "growth_base_pct": 20,
    "horizon_years": 10,
    "amount": 10000,
    "sources": {
        "price": {"kind": "page", "title": "NVIDIA price", "date": "2026-09-01"},
        "per_share": {
            "kind": "page",
            "title": "NVIDIA per_share",
            "url": "https://example.com/eps",
            "date": "2026-09-01",
        },
        "growth_base_pct": {
            "kind": "page",
            "title": "NVIDIA growth_base_pct",
            "url": "https://example.com/growth",
            "date": "2026-09-01",
        },
    },
}


@pytest.fixture
def client() -> TestClient:
    test_client = TestClient(app)
    test_client.post("/api/v1/dev/reset")
    return test_client


def _conversation(client: TestClient, title: str = "Apple valuation") -> str:
    return client.post("/api/v1/conversations", json={"title": title}).json()[
        "conversation"
    ]["id"]


def _answer(
    client: TestClient,
    conversation_id: str,
    kind: str,
    arguments: dict[str, Any],
    question: str,
) -> str:
    owner = client.get("/api/v1/me").json()["user"]["id"]
    create_message(
        user_id=owner, conversation_id=conversation_id, role="user", content=question
    )
    card = run_calculation(kind, arguments).model_copy(
        update={"artifact_id": fake.uuid4()}
    )
    message = create_message(
        user_id=owner,
        conversation_id=conversation_id,
        role="assistant",
        content="Here it is.",
        metadata={
            "tool_result_cards": [card.model_dump(mode="json")],
            "computation": computation_from_tool_card(card).model_dump(mode="json"),
        },
    )
    return message.id


def _ref(conversation_id: str, message_id: str) -> dict[str, str]:
    return {"conversation_id": conversation_id, "message_id": message_id}


def test_two_answers_of_one_kind_compare_with_differences_from_python(client) -> None:
    first, second = _conversation(client, "At 150"), _conversation(client, "At 180")
    left = _answer(client, first, "price_multiple", _multiple(150), "Apple at 150?")
    right = _answer(client, second, "price_multiple", _multiple(180), "Apple at 180?")

    response = client.post(
        "/api/v1/computations/compare",
        json={"left": _ref(first, left), "right": _ref(second, right)},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "price_multiple"
    assert body["left"]["asked"] == "Apple at 150?"
    assert body["right"]["card"]["arguments"]["price"] == 180
    answer = next(item for item in body["differences"] if item["section"] == "answer")
    assert (answer["left"], answer["right"], answer["difference"]) == (25.0, 30.0, 5.0)
    price = next(item for item in body["differences"] if item["name"] == "price")
    assert price["difference"] == 30.0
    assert price["unit"]["interpolation_args"] == {"code": "USD"}


def test_comparing_across_kinds_the_same_answer_or_a_stranger_is_refused(client) -> None:
    conversation = _conversation(client)
    multiple = _answer(client, conversation, "price_multiple", _multiple(150), "P/E?")
    ratio = _answer(
        client,
        conversation,
        "debt_to_income",
        {
            "currency": "USD",
            "monthly_debt_payments": 1500,
            "monthly_income": 5000,
            "ratio_pct": None,
        },
        "Debt ratio?",
    )
    mixed = client.post(
        "/api/v1/computations/compare",
        json={"left": _ref(conversation, multiple), "right": _ref(conversation, ratio)},
    )
    assert mixed.status_code == 422 and "invalid_selection" in mixed.text
    same = client.post(
        "/api/v1/computations/compare",
        json={
            "left": _ref(conversation, multiple),
            "right": _ref(conversation, multiple),
        },
    )
    assert same.status_code == 422
    stranger = client.post(
        "/api/v1/computations/compare",
        json={
            "left": _ref(conversation, multiple),
            "right": _ref(conversation, fake.uuid4()),
        },
    )
    assert stranger.status_code == 404


def test_the_picker_lists_owned_answers_of_the_kind_without_the_open_one(client) -> None:
    first, second = _conversation(client, "First"), _conversation(client, "Second")
    open_one = _answer(client, first, "price_multiple", _multiple(150), "Apple at 150?")
    other = _answer(client, second, "price_multiple", _multiple(180), "Apple at 180?")
    _answer(
        client,
        second,
        "debt_to_income",
        {
            "currency": "USD",
            "monthly_debt_payments": 1500,
            "monthly_income": 5000,
            "ratio_pct": None,
        },
        "Debt ratio?",
    )

    response = client.get(
        "/api/v1/computations/answers",
        params={"kind": "price_multiple", "exclude_message_id": open_one},
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["message_id"] for item in items] == [other]
    assert items[0]["asked"] == "Apple at 180?"
    assert items[0]["symbols"] == ["AAPL"]


def test_continue_carries_only_the_result_into_a_new_linked_chat(client) -> None:
    source = _conversation(client)
    message_id = _answer(
        client, source, "price_multiple", _multiple(150), "Apple at 150?"
    )
    before = client.get(f"/api/v1/conversations/{source}/messages").json()["items"]

    response = client.post(
        f"/api/v1/conversations/{source}/messages/{message_id}/continue"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    new_id = body["conversation"]["id"]
    assert new_id != source
    messages = client.get(f"/api/v1/conversations/{new_id}/messages").json()["items"]
    assert [message["role"] for message in messages] == ["assistant"]
    assert messages[0]["id"] == body["message_id"]
    metadata = messages[0]["metadata"]
    assert metadata["continued_from"] == {
        "conversation_id": source,
        "message_id": message_id,
    }
    source_metadata = before[-1]["metadata"]
    card = metadata["tool_result_cards"][0]
    assert card["artifact_id"] != source_metadata["tool_result_cards"][0]["artifact_id"]
    assert card["arguments"] == source_metadata["tool_result_cards"][0]["arguments"]
    assert metadata["computation"] == source_metadata["computation"]
    after = client.get(f"/api/v1/conversations/{source}/messages").json()["items"]
    assert [item["id"] for item in after] == [item["id"] for item in before]
    assert after[-1]["metadata"] == before[-1]["metadata"]

    recomputed = client.post(
        f"/api/v1/conversations/{new_id}/tool-results/{card['artifact_id']}/recompute",
        json={
            "message_id": messages[0]["id"],
            "input_revision": 0,
            "arguments": {"price": 180},
        },
    )
    assert recomputed.status_code == 200, recomputed.text
    unchanged = client.get(f"/api/v1/conversations/{source}/messages").json()["items"]
    assert unchanged[-1]["metadata"] == before[-1]["metadata"]


def test_a_guest_cannot_continue_a_result_in_a_new_chat(client, monkeypatch) -> None:
    source = _conversation(client)
    message_id = _answer(
        client, source, "price_multiple", _multiple(150), "Apple at 150?"
    )
    from argus.api import dependencies

    def refuse(request, capability, *, detail, reason):
        assert capability == "can_create_additional_conversation"
        raise dependencies.problem(
            request,
            status_code=403,
            code="account_conversion_required",
            title="Account Required",
            detail=detail,
            context={"reason": reason},
        )

    from argus.api.routers import computations

    monkeypatch.setattr(computations, "require_account_capability", refuse)
    response = client.post(
        f"/api/v1/conversations/{source}/messages/{message_id}/continue"
    )
    assert response.status_code == 403
    assert "account_conversion_required" in response.text


def _wire_refresh(monkeypatch, calculation: Any):
    from argus.agent_runtime import research_grounded as grounded
    from argus.domain.research.perplexity_agent import PerplexityAgentClient

    from tests.research.conftest import (
        RecordingTransport,
        agent_response,
        typed_answer_text,
    )

    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    transport = RecordingTransport(
        [
            agent_response(
                text=typed_answer_text(
                    "NVIDIA inputs as of today.",
                    [],
                    calculation if isinstance(calculation, dict) else None,
                ),
                sources=["https://example.com/eps"],
                tickers=["NVDA"],
            )
        ]
    )
    monkeypatch.setattr(
        grounded, "_client", lambda: PerplexityAgentClient("k", transport=transport)
    )
    return transport


def test_refresh_looks_up_the_cited_inputs_and_never_rewrites_the_answer(
    client, monkeypatch
) -> None:
    from argus.domain.research.config import SCENARIO_RETRIEVAL_INSTRUCTIONS

    page = "https://example.com/eps"
    transport = _wire_refresh(
        monkeypatch,
        {
            "kind": "valuation_scenarios",
            "inputs": [
                {
                    "name": "price",
                    "value": 218.36,
                    "source": "page",
                    "source_url": page,
                    "as_of": "2026-09-11",
                },
                {
                    "name": "per_share",
                    "value": 4.5,
                    "source": "page",
                    "source_url": page,
                    "as_of": "2026-09-10",
                },
                {"name": "amount", "value": 99999, "source": "user"},
            ],
        },
    )
    conversation = _conversation(client, "NVIDIA in ten years")
    message_id = _answer(
        client,
        conversation,
        "valuation_scenarios",
        CITED_VALUATION,
        "What will NVDA be worth?",
    )

    response = client.post(
        f"/api/v1/conversations/{conversation}/messages/{message_id}/computation/refresh"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "refreshed"
    card = body["reruns"][0]["result"]
    assert card["outcome"]["status"] == "succeeded"
    assert card["arguments"]["price"] == 218.36
    assert card["arguments"]["per_share"] == 4.5
    assert card["arguments"]["sources"]["per_share"]["date"] == "2026-09-10"
    # No page states the growth forecast today: it keeps its stored value and date.
    assert card["arguments"]["growth_base_pct"] == 20
    assert card["arguments"]["sources"]["growth_base_pct"]["date"] == "2026-09-01"
    # Only cited inputs are looked up again; the user's amount never moves.
    assert card["arguments"]["amount"] == 10000
    assert body["sources"]
    assert len(transport.requests) == 1
    sent = json.loads(transport.requests[0].content.decode())
    assert sent["instructions"] == SCENARIO_RETRIEVAL_INSTRUCTIONS
    assert (
        "Look up the current published value of each of these calculation inputs"
        in sent["input"]
    )
    assert "price, per_share, growth_base_pct" in sent["input"]
    stored = client.get(f"/api/v1/conversations/{conversation}/messages").json()["items"][
        -1
    ]
    assert stored["metadata"]["tool_result_cards"][0]["arguments"]["price"] == 200


def test_refresh_names_the_readers_country_and_currency_in_the_lookup(
    client, monkeypatch
) -> None:
    transport = _wire_refresh(
        monkeypatch,
        {
            "kind": "valuation_scenarios",
            "inputs": [
                {
                    "name": "price",
                    "value": 218.36,
                    "source": "page",
                    "source_url": "https://example.com/eps",
                    "as_of": "2026-09-11",
                }
            ],
        },
    )
    profile = client.patch("/api/v1/me", json={"country": "DO"})
    assert profile.status_code == 200, profile.text
    conversation = _conversation(client, "NVIDIA in ten years")
    message_id = _answer(
        client,
        conversation,
        "valuation_scenarios",
        CITED_VALUATION,
        "What will NVDA be worth?",
    )

    response = client.post(
        f"/api/v1/conversations/{conversation}/messages/{message_id}/computation/refresh"
    )

    assert response.status_code == 200, response.text
    sent = json.loads(transport.requests[0].content.decode())
    assert (
        "The reader lives in Dominican Republic (DO) and counts money in DOP."
        in sent["input"]
    )


def test_a_failed_refresh_returns_the_signed_in_research_claim(
    client, monkeypatch
) -> None:
    from argus.agent_runtime import research_grounded as grounded
    from argus.api import state as api_state
    from argus.api.chat.research_evidence import RESEARCH_USAGE_RESOURCE
    from argus.domain.research.contracts import ResearchUnavailableError
    from argus.domain.visitor_usage import (
        read_memory_visitor_used,
        registered_account_usage_key,
    )

    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    monkeypatch.setattr(api_state, "supabase_gateway", None)

    class _FailingClient:
        def run_research(self, *_args: Any, **_kwargs: Any):
            raise ResearchUnavailableError("timeout")

    monkeypatch.setattr(grounded, "_client", lambda: _FailingClient())
    owner = client.get("/api/v1/me").json()["user"]["id"]
    key = registered_account_usage_key(owner)
    conversation = _conversation(client)
    message_id = _answer(
        client,
        conversation,
        "valuation_scenarios",
        CITED_VALUATION,
        "What will NVDA be worth?",
    )

    response = client.post(
        f"/api/v1/conversations/{conversation}/messages/{message_id}/computation/refresh"
    )

    assert response.status_code == 503
    assert "research_unavailable" in response.text
    assert (
        read_memory_visitor_used(
            api_state.store.visitor_usage_counters,
            visitor_key=key,
            resource=RESEARCH_USAGE_RESOURCE,
            period="day",
        )
        == 0
    )


def test_refresh_is_refused_before_any_provider_work_when_the_allowance_is_spent(
    client, monkeypatch
) -> None:
    from argus.api.chat import research_evidence
    from argus.domain.research.admission import ResearchAttemptAdmission

    transport = _wire_refresh(monkeypatch, [])
    monkeypatch.setattr(
        research_evidence,
        "claim_research_provider_attempt",
        lambda **_: ResearchAttemptAdmission(available=False),
    )
    conversation = _conversation(client)
    message_id = _answer(
        client,
        conversation,
        "valuation_scenarios",
        CITED_VALUATION,
        "What will NVDA be worth?",
    )
    response = client.post(
        f"/api/v1/conversations/{conversation}/messages/{message_id}/computation/refresh"
    )
    assert response.status_code == 429
    assert "research_capacity_exhausted" in response.text
    assert transport.requests == []


def test_an_answer_that_cites_no_page_has_nothing_to_refresh(client, monkeypatch) -> None:
    transport = _wire_refresh(monkeypatch, [])
    conversation = _conversation(client)
    message_id = _answer(client, conversation, "price_multiple", _multiple(150), "P/E?")
    response = client.post(
        f"/api/v1/conversations/{conversation}/messages/{message_id}/computation/refresh"
    )
    assert response.status_code == 409
    assert "nothing_to_refresh" in response.text
    assert transport.requests == []


def test_no_computed_answer_action_writes_personalization_memory(client) -> None:
    from argus.api.personalization_memory import configure_memory_service
    from argus.memory.service import MemoryService
    from argus.memory.store import InMemoryCanonicalMemoryStore
    from argus.memory.subject import RegisteredMemoryOwner

    store = InMemoryCanonicalMemoryStore()
    configure_memory_service(MemoryService(store=store))
    try:
        first, second = _conversation(client, "One"), _conversation(client, "Two")
        left = _answer(
            client, first, "price_multiple", _multiple(150), "My salary is 90000, P/E?"
        )
        right = _answer(client, second, "price_multiple", _multiple(180), "P/E at 180?")
        decided = client.post(
            f"/api/v1/conversations/{first}/messages/{left}/decision",
            json={"decision_state": "watching", "note": "My own figures"},
        )
        assert decided.status_code == 200, decided.text
        rerun = client.post(
            f"/api/v1/conversations/{first}/messages/{left}/computation/rerun",
            json={"inputs": {"price": 160}},
        )
        assert rerun.status_code == 200, rerun.text
        compared = client.post(
            "/api/v1/computations/compare",
            json={"left": _ref(first, left), "right": _ref(second, right)},
        )
        assert compared.status_code == 200
        continued = client.post(f"/api/v1/conversations/{first}/messages/{left}/continue")
        assert continued.status_code == 200
        owner = client.get("/api/v1/me").json()["user"]["id"]
        assert store.list_records(RegisteredMemoryOwner(owner_id=owner)) == ()
    finally:
        configure_memory_service(None)


def test_a_continued_business_answer_stays_in_business(client, monkeypatch) -> None:
    from argus.api.business_spaces import business_spaces, configure_business_spaces
    from argus.domain.business.spaces import InMemorySpaceStore

    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BUSINESS_CHAT_ENABLED", "true")
    previous = business_spaces()
    spaces = InMemorySpaceStore()
    configure_business_spaces(spaces)
    try:
        person = client.get("/api/v1/me").json()["user"]["id"]
        spaces.create(person, "Mi negocio")
        source = client.post(
            "/api/v1/conversations", json={"title": "Shop", "surface": "business"}
        ).json()["conversation"]["id"]
        message_id = _answer(
            client, source, "price_multiple", _multiple(150), "Apple at 150?"
        )

        response = client.post(
            f"/api/v1/conversations/{source}/messages/{message_id}/continue"
        )

        assert response.status_code == 200, response.text
        continued = response.json()["conversation"]["id"]

        def listed(surface: str) -> list[str]:
            return [
                item["id"]
                for item in client.get(
                    "/api/v1/conversations", params={"surface": surface}
                ).json()["items"]
            ]

        assert sorted(listed("business")) == sorted([source, continued])
        assert continued not in listed("personal")
    finally:
        configure_business_spaces(previous)


def test_the_picker_lists_only_the_answers_on_its_own_side(client, monkeypatch) -> None:
    from argus.api import state as api_state
    from argus.api.business_spaces import business_spaces, configure_business_spaces
    from argus.domain.business.spaces import InMemorySpaceStore

    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BUSINESS_CHAT_ENABLED", "true")
    previous = business_spaces()
    spaces = InMemorySpaceStore()
    configure_business_spaces(spaces)
    try:
        spaces.create(client.get("/api/v1/me").json()["user"]["id"], "Mi negocio")
        personal = _conversation(client, "Home")
        business = client.post(
            "/api/v1/conversations", json={"title": "Shop", "surface": "business"}
        ).json()["conversation"]["id"]
        stranger = _conversation(client, "Someone else")
        personal_answer = _answer(
            client, personal, "price_multiple", _multiple(150), "Apple at 150?"
        )
        business_answer = _answer(
            client, business, "price_multiple", _multiple(180), "Apple at 180?"
        )
        _answer(client, stranger, "price_multiple", _multiple(200), "Apple at 200?")
        api_state.store.conversation_owners[stranger] = fake.uuid4()

        def listed(**params: str) -> list[str]:
            response = client.get(
                "/api/v1/computations/answers",
                params={"kind": "price_multiple", **params},
            )
            assert response.status_code == 200, response.text
            return [item["message_id"] for item in response.json()["items"]]

        assert listed() == [personal_answer]
        assert listed(surface="personal") == [personal_answer]
        assert listed(surface="business") == [business_answer]
        monkeypatch.delenv("ARGUS_BUSINESS_PILOT_ENABLED")
        refused = client.get(
            "/api/v1/computations/answers",
            params={"kind": "price_multiple", "surface": "business"},
        )
        assert (refused.status_code, refused.json()["code"]) == (
            404,
            "business_unavailable",
        )
    finally:
        configure_business_spaces(previous)
