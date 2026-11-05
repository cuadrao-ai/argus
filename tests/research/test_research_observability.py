"""Research settlement no longer reaches PostHog (SPEC 0, package 0C-1).

The research work kind and outcome stay on the cost ledger and the research
sidecar. PostHog receives only the closed wave 1 analytics registry, which has
no research event.
"""

from __future__ import annotations

from typing import Any, get_args

import httpx
import pytest
from argus.agent_runtime.research_grounded import build_research_sidecar
from argus.api import state as api_state
from argus.api.chat.research_evidence import record_research_turn_evidence
from argus.domain.research.contracts import CapabilityClass
from argus.observability import envelope as envelope_module


@pytest.fixture
def capture_payloads(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "test-project-token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    monkeypatch.setattr(api_state.store, "usage_counters", {})

    def post(url: str, *, json: dict[str, Any], timeout: float) -> httpx.Response:
        payloads.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(envelope_module.httpx, "post", post)
    return payloads


@pytest.mark.parametrize("capability_class", get_args(CapabilityClass))
@pytest.mark.parametrize("degraded_code", [None, "research_unavailable"])
def test_research_settlement_sends_nothing_to_posthog(
    capability_class: CapabilityClass,
    degraded_code: str | None,
    capture_payloads: list[dict[str, Any]],
    faker: Any,
) -> None:
    research = build_research_sidecar(
        capability_class=capability_class,
        shape="balanced",
        sources=[{"title": faker.sentence(), "url": faker.url()}],
        retrieved_at=faker.iso8601(),
        subjects=[{"symbol": "SPY", "name": faker.sentence()}],
        peers=[],
        usage={"cache_status": "miss", "cost_usd": 0.005, "latency_ms": 640},
        period_of_interest=None,
        degraded_code=degraded_code,
    )

    record_research_turn_evidence(
        research=research,
        user_id=faker.uuid4(),
        conversation_id=faker.uuid4(),
        message_id=faker.uuid4(),
        request_id=faker.uuid4(),
    )

    assert capture_payloads == []


def test_non_research_settlement_does_not_emit(capture_payloads, faker) -> None:
    record_research_turn_evidence(
        research=None,
        user_id=faker.uuid4(),
        conversation_id=None,
        message_id=None,
        request_id=None,
    )
    assert capture_payloads == []
