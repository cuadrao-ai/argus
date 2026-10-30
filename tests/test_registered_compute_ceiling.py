"""Signed-in daily compute and research caps.

Conversation stays unbounded in ``GET /me/usage``. Ordinary signed-in turns
still claim a daily unit at entry. Research claims the same visitor-table
row shape guests use, keyed on ``user:<account id>``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from types import SimpleNamespace
from typing import Any

import pytest
from argus.api import state as api_state
from argus.api.chat.research_evidence import (
    claim_research_provider_attempt,
)
from argus.domain.usage_limits import (
    COMPUTE_TURN_CEILING_DETAIL,
    POSTGRES_INTEGER_MAX,
    REGISTERED_COMPUTE_CEILING_RESOURCE,
    registered_daily_research_ceiling,
    registered_daily_turn_ceiling,
    reset_positive_int_env_warnings_for_tests,
)
from argus.domain.visitor_usage import (
    read_memory_visitor_used,
    registered_account_usage_key,
)

from tests.test_allowance_accounting import client, mock_gateway
from tests.test_guest_compute_ceiling import (
    GUEST_HEADERS,
    TURN,
    _guest,
)

__all__ = ["mock_gateway"]

REGISTERED_HEADERS = {"Authorization": "Bearer test-token"}
ACCOUNT_ID = "00000000-0000-0000-0000-000000000001"
ACCOUNT_KEY = registered_account_usage_key(ACCOUNT_ID)


class _FakeRegisteredComputeClaimClient:
    """Thread-safe stub for claim_registered_compute_usage."""

    def __init__(self, *, used: int = 0) -> None:
        self.used = used
        self.claims = 0
        self._lock = Lock()

    def rpc(self, name: str, params: dict[str, Any]) -> SimpleNamespace:
        assert name == "claim_registered_compute_usage"
        with self._lock:
            limit = int(params["p_limit"])
            if self.used >= limit:
                data = {"available": False}
            else:
                self.used += 1
                self.claims += 1
                data = {"available": True}
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))


def _registered(mock_gateway, monkeypatch: pytest.MonkeyPatch, *, turns_today: int):
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    fake = _FakeRegisteredComputeClaimClient(used=turns_today)
    mock_gateway.client = fake
    return fake


def test_registered_compute_claim_sql_is_service_role_only() -> None:
    from pathlib import Path

    sql = Path(
        "supabase/migrations/20260925140000_claim_registered_compute_usage.sql"
    ).read_text(encoding="utf-8")
    lowered = " ".join(sql.lower().split())
    assert "for update" in lowered
    assert (
        "revoke all on function public.claim_registered_compute_usage("
        in lowered
    )
    assert "from public, anon, authenticated" in lowered
    assert (
        "grant execute on function public.claim_registered_compute_usage("
        in lowered
    )
    assert "to service_role" in lowered


def test_guest_and_signed_in_claim_outages_share_one_retry_interval() -> None:
    from argus.api.chat import guest_compute_ceiling, registered_compute_ceiling
    from argus.domain.usage_limits import (
        COMPUTE_CLAIM_UNAVAILABLE_RETRY_AFTER_SECONDS,
    )

    assert (
        guest_compute_ceiling.COMPUTE_CLAIM_UNAVAILABLE_RETRY_AFTER_SECONDS
        is registered_compute_ceiling.COMPUTE_CLAIM_UNAVAILABLE_RETRY_AFTER_SECONDS
        is COMPUTE_CLAIM_UNAVAILABLE_RETRY_AFTER_SECONDS
    )
    assert COMPUTE_CLAIM_UNAVAILABLE_RETRY_AFTER_SECONDS == 15


def test_registered_caps_read_env_or_the_code_owned_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", raising=False)
    monkeypatch.delenv("ARGUS_REGISTERED_DAILY_RESEARCH_CEILING", raising=False)
    assert registered_daily_turn_ceiling() == 200
    assert registered_daily_research_ceiling() == 15
    monkeypatch.setenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", "7")
    monkeypatch.setenv("ARGUS_REGISTERED_DAILY_RESEARCH_CEILING", "4")
    assert registered_daily_turn_ceiling() == 7
    assert registered_daily_research_ceiling() == 4
    monkeypatch.setenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", "0")
    monkeypatch.setenv("ARGUS_REGISTERED_DAILY_RESEARCH_CEILING", "nope")
    assert registered_daily_turn_ceiling() == 200
    assert registered_daily_research_ceiling() == 15


def test_registered_caps_accept_postgres_integer_max_and_fall_back_past_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from argus.domain.usage_limits import guest_session_daily_turn_ceiling

    reset_positive_int_env_warnings_for_tests()
    monkeypatch.setenv(
        "CUADRAO_REGISTERED_DAILY_TURN_CEILING", str(POSTGRES_INTEGER_MAX)
    )
    monkeypatch.setenv(
        "ARGUS_REGISTERED_DAILY_RESEARCH_CEILING", str(POSTGRES_INTEGER_MAX)
    )
    assert registered_daily_turn_ceiling() == POSTGRES_INTEGER_MAX
    assert registered_daily_research_ceiling() == POSTGRES_INTEGER_MAX

    monkeypatch.setenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", "3000000000")
    monkeypatch.setenv("ARGUS_REGISTERED_DAILY_RESEARCH_CEILING", "2147483648")
    monkeypatch.setenv("CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING", "3000000000")
    with patch("argus.domain.usage_limits.logger.warning") as warning:
        assert registered_daily_turn_ceiling() == 200
        assert registered_daily_research_ceiling() == 15
        assert guest_session_daily_turn_ceiling() == 100
        registered_daily_turn_ceiling()
        registered_daily_research_ceiling()
        guest_session_daily_turn_ceiling()
    assert warning.call_count == 3
    names = {call.kwargs["name"] for call in warning.call_args_list}
    assert names == {
        "CUADRAO_REGISTERED_DAILY_TURN_CEILING",
        "ARGUS_REGISTERED_DAILY_RESEARCH_CEILING",
        "CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING",
    }
    assert all(call.kwargs["default"] in {200, 15, 100} for call in warning.call_args_list)


def test_registered_caps_treat_garbage_env_as_the_code_owned_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    reset_positive_int_env_warnings_for_tests()
    monkeypatch.setenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", "3.5")
    monkeypatch.setenv("ARGUS_REGISTERED_DAILY_RESEARCH_CEILING", "-1")
    with patch("argus.domain.usage_limits.logger.warning") as warning:
        assert registered_daily_turn_ceiling() == 200
        assert registered_daily_research_ceiling() == 15
        registered_daily_turn_ceiling()
        registered_daily_research_ceiling()
    assert warning.call_count == 2
    assert {call.kwargs["value"] for call in warning.call_args_list} == {
        "3.5",
        "-1",
    }


def test_the_201st_signed_in_turn_is_refused_with_the_limit_response(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", raising=False)
    fake = _registered(mock_gateway, monkeypatch, turns_today=200)

    response = client.post(
        "/api/v1/chat/stream", json=TURN, headers=REGISTERED_HEADERS
    )

    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "too_many_requests"
    assert body["detail"] == COMPUTE_TURN_CEILING_DETAIL
    assert body["title"] == "Too Many Requests"
    assert int(response.headers["Retry-After"]) >= 1
    assert fake.claims == 0
    mock_gateway.create_message.assert_not_called()


def test_env_override_changes_the_signed_in_chat_cap(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", "2")
    fake = _registered(mock_gateway, monkeypatch, turns_today=2)

    response = client.post(
        "/api/v1/chat/stream", json=TURN, headers=REGISTERED_HEADERS
    )

    assert response.status_code == 429
    assert response.json()["detail"] == COMPUTE_TURN_CEILING_DETAIL
    assert fake.claims == 0


def test_signed_in_and_guest_limit_responses_use_the_same_copy(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    from argus.domain.usage_limits import GUEST_COMPUTE_DAILY_CEILING

    monkeypatch.delenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", raising=False)
    registered = _registered(mock_gateway, monkeypatch, turns_today=200)
    signed_in = client.post(
        "/api/v1/chat/stream", json=TURN, headers=REGISTERED_HEADERS
    )
    _guest(mock_gateway, monkeypatch, turns_today=GUEST_COMPUTE_DAILY_CEILING)
    guest = client.post("/api/v1/chat/stream", json=TURN, headers=GUEST_HEADERS)

    assert signed_in.status_code == guest.status_code == 429
    assert signed_in.json()["code"] == guest.json()["code"] == "too_many_requests"
    assert signed_in.json()["title"] == guest.json()["title"]
    assert signed_in.json()["detail"] == guest.json()["detail"] == COMPUTE_TURN_CEILING_DETAIL
    assert "\u2014" not in signed_in.json()["detail"]
    assert registered.claims == 0


def test_signed_in_counter_resets_the_next_day(monkeypatch: pytest.MonkeyPatch) -> None:
    from argus.api.chat.registered_compute_ceiling import (
        claim_registered_compute_turn,
    )
    from argus.domain.usage_limits import align_usage_period

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.visitor_usage_counters.clear()
    monkeypatch.setenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", "1")
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    start, end = align_usage_period(yesterday, "day")
    api_state.store.visitor_usage_counters[
        (ACCOUNT_KEY, REGISTERED_COMPUTE_CEILING_RESOURCE, "day")
    ] = {
        "period_start": start,
        "period_end": end,
        "used_count": 1,
        "limit_count": 1,
    }

    first_today = claim_registered_compute_turn(account_key=ACCOUNT_KEY)
    second_today = claim_registered_compute_turn(account_key=ACCOUNT_KEY)

    assert first_today.available is True
    assert second_today.available is False
    assert (
        read_memory_visitor_used(
            api_state.store.visitor_usage_counters,
            visitor_key=ACCOUNT_KEY,
            resource=REGISTERED_COMPUTE_CEILING_RESOURCE,
            period="day",
        )
        == 1
    )
    api_state.store.visitor_usage_counters.clear()


def test_the_16th_signed_in_research_run_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.usage_counters.clear()
    api_state.store.visitor_usage_counters.clear()
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    monkeypatch.delenv("ARGUS_REGISTERED_DAILY_RESEARCH_CEILING", raising=False)

    for _ in range(15):
        assert claim_research_provider_attempt(guest_visitor_key=ACCOUNT_KEY).available
    sixteenth = claim_research_provider_attempt(guest_visitor_key=ACCOUNT_KEY)
    assert sixteenth.available is False
    assert sixteenth.registered_exhausted is True
    assert sixteenth.guest_exhausted is False
    api_state.store.usage_counters.clear()
    api_state.store.visitor_usage_counters.clear()


def test_env_override_changes_the_signed_in_research_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.usage_counters.clear()
    api_state.store.visitor_usage_counters.clear()
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    monkeypatch.setenv("ARGUS_REGISTERED_DAILY_RESEARCH_CEILING", "2")

    assert claim_research_provider_attempt(guest_visitor_key=ACCOUNT_KEY).available
    assert claim_research_provider_attempt(guest_visitor_key=ACCOUNT_KEY).available
    third = claim_research_provider_attempt(guest_visitor_key=ACCOUNT_KEY)
    assert third.available is False
    assert third.registered_exhausted is True
    api_state.store.usage_counters.clear()
    api_state.store.visitor_usage_counters.clear()


def test_signed_in_research_exhausted_copy_is_localized_without_em_dash() -> None:
    from argus.agent_runtime.research_grounded import research_capacity_exhausted_note

    english = research_capacity_exhausted_note("en", registered_allowance=True)
    spanish = research_capacity_exhausted_note("es-419", registered_allowance=True)
    assert "Create an account" not in english
    assert "Crea una cuenta" not in spanish
    assert "today's research questions" in english
    assert "consultas de investigación de hoy" in spanish
    assert "\u2014" not in english
    assert "\u2014" not in spanish


def test_replayed_idempotency_key_does_not_consume_a_unit(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_guest_compute_ceiling import (
        REPLAY_HEADERS,
        SPENT_CONFIRMATION_REPLAY,
    )

    fake = _registered(mock_gateway, monkeypatch, turns_today=5)

    first = client.post(
        "/api/v1/chat/stream",
        json=SPENT_CONFIRMATION_REPLAY,
        headers={**REGISTERED_HEADERS, **REPLAY_HEADERS},
    )
    replay = client.post(
        "/api/v1/chat/stream",
        json=SPENT_CONFIRMATION_REPLAY,
        headers={**REGISTERED_HEADERS, **REPLAY_HEADERS},
    )

    assert first.status_code == replay.status_code == 409, replay.text
    assert fake.claims == 0
    assert fake.used == 5
    mock_gateway.create_message.assert_not_called()


def test_unknown_conversation_404_does_not_consume_a_unit(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _registered(mock_gateway, monkeypatch, turns_today=5)
    mock_gateway.get_conversation.return_value = None

    response = client.post(
        "/api/v1/chat/stream",
        json={**TURN, "conversation_id": "conv-unknown"},
        headers=REGISTERED_HEADERS,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert fake.claims == 0
    assert fake.used == 5


def test_signed_in_turn_still_claims_one_unit_after_lookup(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _registered(mock_gateway, monkeypatch, turns_today=5)

    response = client.post(
        "/api/v1/chat/stream", json=TURN, headers=REGISTERED_HEADERS
    )

    assert response.status_code == 200, response.text
    assert fake.claims == 1
    assert fake.used == 6


def test_over_cap_retest_is_refused_before_market_data_coverage(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    from argus.api.chat import retest
    from argus.domain.retest_setup import RetestDossierAvailability

    fake = _registered(mock_gateway, monkeypatch, turns_today=200)
    monkeypatch.delenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", raising=False)
    setup = SimpleNamespace(source_run_id="run-1")
    monkeypatch.setattr(retest, "_owned_retest_setup", lambda **_: setup)
    monkeypatch.setattr(
        retest,
        "retest_dossier_availability",
        lambda _setup: RetestDossierAvailability(state="new_data_available"),
    )
    monkeypatch.setattr(retest, "repaired_retest_setup", lambda s, _a: s)
    coverage_calls: list[Any] = []
    monkeypatch.setattr(
        retest,
        "prepare_retest_confirmation_payload",
        lambda *args, **kwargs: coverage_calls.append(args),
    )

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": "conv-1",
            "action": {
                "type": "retest_run",
                "payload": {
                    "source_run_id": "00000000-0000-4000-8000-0000000000aa",
                    "window_policy": "preserve_start_ending_latest_available",
                    "contract_version": "argus_retest_run/v2",
                },
            },
        },
        headers=REGISTERED_HEADERS,
    )

    assert response.status_code == 429, response.text
    assert coverage_calls == []
    assert fake.claims == 0
