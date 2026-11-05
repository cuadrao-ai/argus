import json
from contextlib import nullcontext
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import yaml
from argus.api import state as api_state
from argus.api.main import app
from argus.api.pagination import encode_cursor
from argus.api.schemas import (
    AccountCapabilities,
    Conversation,
    EvidenceArtifact,
    GuestAccountSummary,
    Idea,
    IdeaVersion,
    Message,
    OnboardingState,
    User,
    UserResponse,
)
from argus.domain.backtest_finalization import MemoryBacktestFinalizationGateway
from argus.domain.chat_turn_lifecycle import TransitionResult
from argus.domain.conversation_activity import Boundary, encode_attention_cursor
from argus.domain.market_data.assets import ResolvedAsset
from argus.domain.owner_scope import PERSONAL
from argus.domain.postgres_history_reader import (
    HistoryCursorError,
    PostgresHistoryReader,
)
from argus.domain.postgres_search_reader import SearchReadResult
from argus.domain.store import AlphaStore, utcnow
from argus.domain.supabase_gateway import (
    ConversationCursorError,
    QuotaExceededError,
    SupabaseGateway,
)
from argus.domain.username_signup import UsernameSignupPrevalidation
from fastapi.testclient import TestClient

client = TestClient(app)


def _stream_events(stream: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for part in stream.split("\n\n"):
        data_line = next(
            (line for line in part.splitlines() if line.startswith("data: ")),
            None,
        )
        if data_line is None:
            continue
        raw = data_line.removeprefix("data: ").strip()
        if raw == "[DONE]":
            events.append({"type": "done"})
            continue
        events.append(json.loads(raw))
    return events


def _final_payload(stream: str) -> dict[str, Any]:
    final_events = [
        event for event in _stream_events(stream) if event.get("type") == "final"
    ]
    assert len(final_events) == 1
    payload = final_events[0]["payload"]
    assert isinstance(payload, dict)
    return payload


def _mock_profile(*, language: str = "en", stage: str = "ready") -> User:
    now = utcnow()
    return User(
        id="00000000-0000-0000-0000-000000000001",
        email="developer@argus.local",
        username="mock-developer",
        display_name="Mock Developer",
        language=language,  # type: ignore[arg-type]
        locale="es-419" if language == "es-419" else "en-US",
        is_admin=True,
        onboarding=OnboardingState(
            completed=stage == "completed",
            stage=stage,  # type: ignore[arg-type]
            language_confirmed=True,
            primary_goal="test_stock_idea" if stage != "language_selection" else None,
        ),
        created_at=now,
        updated_at=now,
    )


def _fake_resolve_asset(symbol: str) -> ResolvedAsset:
    candidate = symbol.strip().upper().replace("-", "/")
    if candidate == "TESLA":
        candidate = "TSLA"
    compact = candidate.replace("/", "")
    if compact.endswith("USD") and len(compact) > 3:
        compact = compact[:-3]

    if compact in {"AAPL", "TSLA", "MSFT", "SPY"}:
        return ResolvedAsset(
            canonical_symbol=compact,
            asset_class="equity",
            name=compact,
            raw_symbol=compact,
        )
    if compact in {"BTC", "ETH", "USDT", "USDC"}:
        return ResolvedAsset(
            canonical_symbol=compact,
            asset_class="crypto",
            name=compact,
            raw_symbol=compact,
        )
    raise ValueError("invalid_symbol")


def _fake_fetch_ohlcv(
    symbol: str,
    asset_class: str,  # noqa: ARG001
    start_date: date,
    end_date: date,
    timeframe: str,
) -> pd.DataFrame:
    freq_map = {"1D": "D", "1h": "h", "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h"}
    index = pd.date_range(
        start=start_date, end=end_date, freq=freq_map[timeframe], tz="UTC"
    )
    if len(index) < 80:
        index = pd.date_range(
            start=start_date, periods=80, freq=freq_map[timeframe], tz="UTC"
        )
    base_map = {"AAPL": 100.0, "TSLA": 200.0, "MSFT": 150.0, "SPY": 400.0, "BTC": 30000.0}
    base = base_map.get(symbol, 100.0)
    close = pd.Series(base + pd.RangeIndex(len(index)).astype(float) * 0.5, index=index)
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": 5000.0,
        },
        index=index,
    )


def _fake_fetch_price_series(
    symbol: str,
    asset_class: str,
    start_date: date,
    end_date: date,
    timeframe: str,
) -> pd.Series:
    return _fake_fetch_ohlcv(
        symbol=symbol,
        asset_class=asset_class,
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe,
    )["close"]


def test_guest_account_response_contract_is_typed_and_exact() -> None:
    now = utcnow()
    response = UserResponse(
        user=_mock_profile(),
        account_kind="guest",
        guest=GuestAccountSummary(
            expires_at=now + timedelta(days=7),
            conversation_id="00000000-0000-0000-0000-000000000002",
            conversation_limit=1,
            simulation_limit=1,
            feedback_limit=5,
        ),
        capabilities=AccountCapabilities(
            can_create_additional_conversation=False,
            can_manage_conversation=False,
            can_save_decision=False,
            can_manage_account=False,
            can_use_omnisearch=True,
            can_search_current_workspace=True,
            can_use_grounded_discovery=False,
            can_submit_feedback=True,
        ),
        public_account_access_enabled=False,
    )

    assert response.guest is not None
    assert response.guest.conversation_limit == 1
    assert response.guest.simulation_limit == 1
    assert response.guest.feedback_limit == 5
    assert response.model_dump()["account_kind"] == "guest"


def test_gateway_auth_flows_use_separate_auth_client():
    service_client = MagicMock()
    auth_client = MagicMock()

    signup_response = MagicMock()
    signup_response.user = object()
    signup_response.model_dump.return_value = {"user": {"id": "auth-user"}}
    auth_client.sign_up.return_value = signup_response

    login_response = MagicMock()
    login_response.session = object()
    login_response.model_dump.return_value = {"session": {"access_token": "token"}}
    auth_client.sign_in_with_password.return_value = login_response

    gateway = SupabaseGateway(
        client=service_client, auth_client_factory=lambda: auth_client
    )

    assert gateway.signup(
        email="alpha@example.com",
        password="password",
        captcha_token="captcha-proof",
    ) == {"user": {"id": "auth-user"}}
    assert gateway.login(
        email="alpha@example.com",
        password="password",
        captcha_token="captcha-proof",
    ) == {"session": {"access_token": "token"}}

    auth_client.sign_up.assert_called_once_with(
        {
            "email": "alpha@example.com",
            "password": "password",
            "options": {
                "data": {
                    "display_name": None,
                    "username": None,
                    "language": "en",
                },
                "captcha_token": "captcha-proof",
            },
        }
    )
    auth_client.sign_in_with_password.assert_called_once_with(
        {
            "email": "alpha@example.com",
            "password": "password",
            "options": {"captcha_token": "captcha-proof"},
        }
    )
    service_client.auth.sign_up.assert_not_called()
    service_client.auth.sign_in_with_password.assert_not_called()


def test_gateway_signup_records_language_for_profile_bootstrap():
    service_client = MagicMock()
    auth_client = MagicMock()
    signup_response = MagicMock()
    signup_response.user = object()
    signup_response.model_dump.return_value = {"user": {"id": "auth-user"}}
    auth_client.sign_up.return_value = signup_response
    gateway = SupabaseGateway(
        client=service_client, auth_client_factory=lambda: auth_client
    )

    gateway.signup(
        email="alpha@example.com",
        password="password",
        captcha_token="captcha-proof",
        language="es-419",
    )

    auth_client.sign_up.assert_called_once_with(
        {
            "email": "alpha@example.com",
            "password": "password",
            "options": {
                "data": {
                    "display_name": None,
                    "username": None,
                    "language": "es-419",
                },
                "captcha_token": "captcha-proof",
            },
        }
    )


def test_gateway_profile_bootstrap_derives_locale_from_signup_language():
    service_client = MagicMock()
    gateway = SupabaseGateway(client=service_client)
    gateway.private_alpha_role_for_email = MagicMock(return_value="user")
    gateway.get_user = MagicMock(return_value=None)
    now = utcnow().isoformat()
    service_client.table.return_value.upsert.return_value.execute.return_value.data = [
        {
            "id": "00000000-0000-0000-0000-000000000009",
            "email": "alpha@example.com",
            "username": None,
            "display_name": "Alpha",
            "language": "es-419",
            "locale": "es-419",
            "is_admin": False,
            "onboarding": OnboardingState().model_dump(),
            "created_at": now,
            "updated_at": now,
        }
    ]

    profile = gateway.get_or_create_profile_for_auth_user(
        {
            "id": "00000000-0000-0000-0000-000000000009",
            "email": "alpha@example.com",
            "user_metadata": {
                "display_name": "Alpha",
                "language": "es-419",
            },
        }
    )

    assert profile.language == "es-419"
    assert profile.locale == "es-419"
    persisted = service_client.table.return_value.upsert.call_args.args[0]
    assert persisted["language"] == "es-419"
    assert persisted["locale"] == "es-419"


def test_gateway_profile_bootstrap_rereads_winner_after_concurrent_create():
    service_client = MagicMock()
    gateway = SupabaseGateway(client=service_client)
    gateway.private_alpha_role_for_email = MagicMock(return_value="user")
    canonical_profile = _mock_profile().model_copy(
        update={
            "id": "00000000-0000-0000-0000-000000000009",
            "email": "alpha@example.com",
            "is_admin": False,
        }
    )
    gateway.get_user = MagicMock(side_effect=[None, canonical_profile])
    service_client.table.return_value.insert.return_value.execute.side_effect = (
        RuntimeError("duplicate key value violates unique constraint profiles_pkey")
    )
    service_client.table.return_value.upsert.return_value.execute.return_value.data = []

    profile = gateway.get_or_create_profile_for_auth_user(
        {
            "id": "00000000-0000-0000-0000-000000000009",
            "email": "alpha@example.com",
            "user_metadata": {
                "display_name": "Racing Alpha",
                "language": "es-419",
            },
        }
    )

    assert profile is canonical_profile
    assert gateway.get_user.call_count == 2
    service_client.table.return_value.upsert.assert_called_once()
    _, upsert_kwargs = service_client.table.return_value.upsert.call_args
    assert upsert_kwargs == {
        "on_conflict": "id",
        "ignore_duplicates": True,
    }
    service_client.table.return_value.insert.assert_not_called()


def test_gateway_private_alpha_role_reads_active_allowlist_row():
    client_mock = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.limit.return_value = query
    query.execute.return_value.data = [
        {"email": "lagarces1@gmail.com", "role": "admin", "disabled_at": None}
    ]
    client_mock.table.return_value = query

    gateway = SupabaseGateway(client=client_mock)

    assert gateway.private_alpha_role_for_email(" LAGARCES1@gmail.com ") == "admin"
    assert gateway.private_alpha_email_allowed("LAGARCES1@gmail.com") is True
    client_mock.table.assert_called_with("private_alpha_allowlist")


def test_gateway_private_alpha_role_ignores_disabled_allowlist_row():
    client_mock = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.limit.return_value = query
    query.execute.return_value.data = [
        {
            "email": "disabled@example.com",
            "role": "user",
            "disabled_at": "2026-05-30T00:00:00Z",
        }
    ]
    client_mock.table.return_value = query

    gateway = SupabaseGateway(client=client_mock)

    assert gateway.private_alpha_role_for_email("disabled@example.com") is None
    assert gateway.private_alpha_email_allowed("disabled@example.com") is False


def _runtime_success_result(
    *,
    symbol: str = "TSLA",
    timeframe: str = "1D",
    language: str = "en",
) -> dict[str, Any]:
    return {
        "stage_outcome": "ready_to_respond",
        "assistant_response": (
            "Probé la idea con TSLA."
            if language.lower().startswith("es")
            else f"I tested that idea with {symbol}."
        ),
        "final_response_payload": {
            "result": {
                "execution_status": "succeeded",
                "resolved_strategy": {
                    "strategy_type": "rsi_mean_reversion",
                    "asset_universe": [symbol],
                },
                "resolved_parameters": {
                    "timeframe": timeframe,
                    "date_range": {
                        "start": "2025-01-01",
                        "end": "2025-12-31",
                    },
                },
                "metrics": {
                    "aggregate": {"performance": {"total_return_pct": 12.5}},
                    "by_symbol": {},
                },
                "benchmark_metrics": {
                    "benchmark_symbol": "BTC" if symbol == "BTC" else "SPY",
                    "benchmark_return_pct": 9.2,
                },
                "assumptions": ["Starting capital: $10,000."],
                "caveats": [],
            },
            "result_card": {
                "title": f"{symbol} RSI Mean Reversion",
                "status_label": "Simulation Complete",
                "rows": [{"label": "Total Return", "value": "+12.5%"}],
                "assumptions": ["Starting capital: $10,000."],
            },
        },
    }


def _runtime_success_for_message(**kwargs: Any) -> dict[str, Any]:
    language = str(getattr(kwargs.get("user"), "language_preference", "en"))
    return _runtime_success_result(language=language)


async def _runtime_success_events(**kwargs: Any):
    result = _runtime_success_for_message(**kwargs)
    assistant_response = str(result.get("assistant_response") or "")
    yield {"type": "stage_start", "stage": "interpret"}
    yield {"type": "stage_outcome", "outcome": str(result["stage_outcome"])}
    if assistant_response:
        yield {"type": "token", "content": assistant_response}
    yield {"type": "final", "payload": result}


@pytest.fixture(autouse=True)
def _patch_engine_io(monkeypatch: pytest.MonkeyPatch) -> None:
    from argus.domain import engine as domain_engine

    monkeypatch.setattr(domain_engine, "resolve_asset", _fake_resolve_asset)
    monkeypatch.setattr(domain_engine, "fetch_ohlcv", _fake_fetch_ohlcv)
    monkeypatch.setattr(domain_engine, "fetch_price_series", _fake_fetch_price_series)


@pytest.fixture
def mock_gateway():
    gateway = MagicMock(spec=SupabaseGateway)
    finalization_store = AlphaStore()
    gateway.get_user.return_value = _mock_profile()
    gateway.get_or_create_mock_user.return_value = _mock_profile()
    gateway.get_auth_user_from_token.return_value = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "developer@argus.local",
    }
    gateway.private_alpha_email_allowed.return_value = True
    gateway.count_completed_runs.return_value = 1
    gateway.list_messages.return_value = []
    gateway.list_message_page_context.return_value = ([], set())
    gateway.reconcile_stale_chat_turns.return_value = []
    gateway.list_projectable_chat_turns.return_value = []
    gateway.reconcile_conversation_activity_turns.return_value = []
    gateway.read_conversation_activity_batch.side_effect = (
        lambda *, user_id, conversation_ids: [
            {
                "conversation_id": conversation_id,
                "sources": [],
                "read_state": None,
            }
            for conversation_id in conversation_ids
        ]
    )
    gateway.get_latest_completed_run_for_conversation.return_value = None
    gateway.accept_chat_turn.side_effect = lambda **kwargs: kwargs["message"]
    gateway.transition_chat_turn.return_value = TransitionResult(outcome="applied")
    gateway.finalize_chat_turn.side_effect = lambda **kwargs: kwargs["message"]
    gateway.finalize_backtest_completion.side_effect = (
        lambda *, finalization: MemoryBacktestFinalizationGateway(
            finalization_store
        ).finalize_backtest_completion(finalization=finalization)
    )
    gateway.finalize_direct_backtest_success.side_effect = (
        lambda *, job_id, finalization: MemoryBacktestFinalizationGateway(
            finalization_store
        ).finalize_backtest_completion(finalization=finalization)
    )
    gateway.get_evidence_capture_by_run.return_value = None
    gateway.create_backtest_evidence_capture.side_effect = (
        lambda *, user_id, captured: captured
    )
    gateway.create_idea.side_effect = lambda *, user_id, idea: idea
    gateway.create_idea_version.side_effect = lambda *, user_id, version: version
    gateway.create_evidence_artifact.side_effect = lambda *, user_id, artifact: artifact
    gateway.get_decision_note_by_artifact.return_value = None
    gateway.upsert_decision_note.side_effect = lambda *, user_id, decision: decision
    gateway.capture_current_decision_note.side_effect = lambda *, user_id, decision: (
        decision,
        api_state.store.evidence_artifacts[decision.evidence_artifact_id].model_copy(
            update={"lifecycle": "decided"}
        ),
        api_state.store.ideas[decision.idea_id].model_copy(
            update={"lifecycle": "decided"}
        ),
        api_state.store.idea_versions[decision.idea_version_id].model_copy(
            update={"lifecycle": "decided"}
        ),
    )
    gateway.create_decision_note.side_effect = lambda *, user_id, decision: decision
    gateway.mark_evidence_artifact_lifecycle.side_effect = (
        lambda *, user_id, artifact_id, lifecycle: api_state.store.evidence_artifacts[
            artifact_id
        ].model_copy(update={"lifecycle": lifecycle})
    )
    gateway.update_backtest_run_result_card.side_effect = (
        lambda *,
        user_id,
        run_id,
        conversation_result_card: api_state.store.backtest_runs[run_id].model_copy(
            update={"conversation_result_card": conversation_result_card}
        )
    )
    gateway.mark_result_card_decision_for_run.return_value = None
    gateway.get_backtest_job_reservation.return_value = None
    gateway.admit_backtest_job.return_value = {
        "decision": "admitted",
        "job": {"id": "job-admitted-1", "status": "running"},
    }
    gateway.finalize_direct_backtest_job.return_value = {
        "id": "job-admitted-1",
        "status": "succeeded",
    }
    gateway.get_backtest_job.return_value = None

    def _rpc(name: str, params: dict[str, Any] | None = None, **_kwargs: Any):
        if name in {
            "claim_registered_compute_usage",
            "claim_guest_compute_usage",
            "claim_research_usage",
        }:
            return SimpleNamespace(
                execute=lambda: SimpleNamespace(
                    data={
                        "available": True,
                        "guest_exhausted": False,
                        "visitor_exhausted": False,
                        "session_exhausted": False,
                    }
                )
            )
        return MagicMock()

    gateway.client = SimpleNamespace(rpc=_rpc)
    with (
        patch("argus.api.state.supabase_gateway", gateway),
        patch("argus.api.routers.profile._apple_identity", return_value=None),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
    ):
        yield gateway


def test_successful_api_response_omits_static_rate_limit_headers(mock_gateway):
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers
    assert "X-RateLimit-Remaining" not in response.headers
    assert "X-RateLimit-Reset" not in response.headers


def test_me_reads_profile_from_supabase_gateway(mock_gateway):
    profile = _mock_profile(language="es-419")
    mock_gateway.get_user.return_value = profile

    response = client.get("/api/v1/me", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert response.json()["user"]["language"] == "es-419"
    assert mock_gateway.get_user.call_count >= 1


def test_me_usage_returns_exact_owner_scoped_allowance_truth(mock_gateway, monkeypatch):
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")

    def _list(*, user_id, resources, period, at):
        assert user_id == "00000000-0000-0000-0000-000000000001"
        assert set(resources) == {"backtest_runs"}
        if period == "hour":
            return [
                {
                    "resource": "backtest_runs",
                    "limit_count": 10,
                    "used_count": 2,
                    "period_end": "2026-07-17T15:00:00+00:00",
                },
            ]
        return [
            {
                "resource": "backtest_runs",
                "limit_count": 50,
                "used_count": 53,
                "period_end": "2026-07-18T00:00:00+00:00",
            },
        ]

    mock_gateway.list_current_usage_counters.side_effect = _list

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    allowances = response.json()["allowances"]
    unbounded = {
        "hour": None,
        "day": None,
        "guest_session": None,
        "available_now": True,
        "limiting_window": None,
    }
    assert allowances["compute"] == unbounded
    assert allowances["grounding"] == unbounded
    assert allowances["execution"]["hour"] == {
        "limit": 10,
        "used": 2,
        "remaining": 8,
        "period_end": "2026-07-17T15:00:00Z",
    }
    assert allowances["execution"]["day"] == {
        "limit": 50,
        "used": 53,
        "remaining": 0,
        "period_end": "2026-07-18T00:00:00Z",
    }
    assert allowances["execution"]["available_now"] is False
    assert allowances["execution"]["limiting_window"] == "day"


def test_me_usage_zero_state_does_not_create_or_increment_counters(
    mock_gateway, monkeypatch
):
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    mock_gateway.list_current_usage_counters.return_value = []

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    allowances = response.json()["allowances"]
    assert allowances["execution"]["hour"]["used"] == 0
    assert allowances["execution"]["hour"]["remaining"] == 10
    assert allowances["execution"]["day"]["remaining"] == 50
    assert allowances["execution"]["available_now"] is True
    assert allowances["compute"]["available_now"] is True
    assert allowances["grounding"]["available_now"] is True
    mock_gateway.check_and_increment_usage_limits.assert_not_called()


def test_me_usage_openapi_contract_publishes_operation_classes():
    generated = app.openapi()["components"]["schemas"]
    checked_openapi = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.yaml").read_text(
            encoding="utf-8"
        )
    )
    checked = checked_openapi["components"]["schemas"]

    for schemas in (generated, checked):
        container = schemas["UsageAllowances"]
        classes = ["compute", "grounding", "execution"]
        # messages and backtests stay for deployed bundles, marked deprecated
        # and derived from the classes; they leave after the next promotion.
        aliases = {"messages": "compute", "backtests": "execution"}
        assert container["required"] == classes + list(aliases)
        assert set(container["properties"]) == set(classes) | set(aliases)
        for alias, source in aliases.items():
            assert container["properties"][alias]["deprecated"] is True
            assert container["properties"][alias]["readOnly"] is True
            assert (
                container["properties"][alias]["$ref"]
                == container["properties"][source]["$ref"]
            )
        # Compute can only ever be unbounded; grounding depends on the
        # account kind; execution always carries windows.
        assert container["properties"]["compute"] == {
            "$ref": "#/components/schemas/UnboundedAllowance"
        }
        assert container["properties"]["grounding"]["anyOf"] == [
            {"$ref": "#/components/schemas/UsageAllowance"},
            {"$ref": "#/components/schemas/UnboundedAllowance"},
        ]
        assert container["properties"]["execution"] == {
            "$ref": "#/components/schemas/UsageAllowance"
        }

        window_keys = {"hour", "day", "guest_session", "available_now", "limiting_window"}
        assert set(schemas["UsageAllowance"]["properties"]) == window_keys
        assert schemas["UsageAllowance"]["properties"]["limiting_window"]["enum"] == [
            "hour",
            "day",
            "guest_session",
        ]
        unbounded = schemas["UnboundedAllowance"]["properties"]
        assert set(unbounded) == window_keys
        for key in ("hour", "day", "guest_session", "limiting_window"):
            assert unbounded[key]["type"] == "null"
        assert unbounded["available_now"]["const"] is True


def test_me_usage_requires_authentication(mock_gateway, monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")

    response = client.get("/api/v1/me/usage")

    assert response.status_code == 401
    mock_gateway.list_current_usage_counters.assert_not_called()


def test_me_usage_returns_problem_details_when_durable_truth_is_unavailable(
    mock_gateway,
    monkeypatch,
):
    mock_gateway.list_current_usage_counters.side_effect = RuntimeError(
        "supabase unavailable"
    )
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")
    failure_client = TestClient(app, raise_server_exceptions=False)

    response = failure_client.get(
        "/api/v1/me/usage",
        headers={
            "Authorization": "Bearer test-token",
            "X-Request-Id": "usage-read-failure",
        },
    )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "type": "https://api.argus.app/problems/usage-read-failed",
        "title": "Usage Read Failed",
        "status": 500,
        "detail": "Current allowance information is unavailable.",
        "code": "usage_read_failed",
        "request_id": "usage-read-failure",
    }
    assert response.headers["X-Request-Id"] == "usage-read-failure"


def test_patch_me_supabase_ignores_retired_profile_fields(mock_gateway, monkeypatch):
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")
    before = _mock_profile(stage="language_selection")
    mock_gateway.get_user.return_value = before

    def _updated_user(_user_id: str, payload: dict) -> User:
        return User.model_validate(before.model_dump() | payload)

    mock_gateway.update_user.side_effect = _updated_user

    response = client.patch(
        "/api/v1/me",
        json={
            "language": "es-419",
            "locale": "es-419",
            "theme": "light",
            "onboarding": {"language_confirmed": False},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    user = response.json()["user"]
    assert user["language"] == "es-419"
    assert "theme" not in user
    assert user["onboarding"] == before.onboarding.model_dump()
    mock_gateway.update_user.assert_called_once()
    assert "theme" not in mock_gateway.update_user.call_args.args[1]


def test_patch_me_persists_a_curated_avatar_theme(mock_gateway, monkeypatch):
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")
    before = _mock_profile()
    mock_gateway.get_user.return_value = before

    def _updated_user(_user_id: str, payload: dict) -> User:
        return User.model_validate(before.model_dump() | payload)

    mock_gateway.update_user.side_effect = _updated_user

    response = client.patch(
        "/api/v1/me",
        json={"avatar_theme": "plum"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["avatar_theme"] == "plum"
    assert mock_gateway.update_user.call_args.args[1]["avatar_theme"] == "plum"


def test_patch_me_rejects_an_unknown_avatar_theme(mock_gateway):
    response = client.patch(
        "/api/v1/me",
        json={"avatar_theme": "arbitrary-hex"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 422


def test_patch_me_rejects_a_null_avatar_theme(mock_gateway):
    response = client.patch(
        "/api/v1/me",
        json={"avatar_theme": None},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 422


def test_registered_profile_exposes_a_default_avatar_theme_but_guest_does_not():
    now = utcnow()
    registered = UserResponse(
        user=_mock_profile(),
        account_kind="registered",
        guest=None,
        capabilities=AccountCapabilities(
            can_create_additional_conversation=True,
            can_manage_conversation=True,
            can_save_decision=True,
            can_manage_account=True,
            can_use_omnisearch=True,
            can_search_current_workspace=False,
            can_use_grounded_discovery=True,
            can_submit_feedback=True,
        ),
        public_account_access_enabled=False,
    )
    guest = UserResponse(
        user=_mock_profile(),
        account_kind="guest",
        guest=GuestAccountSummary(
            expires_at=now + timedelta(days=7),
            conversation_id="00000000-0000-0000-0000-000000000002",
            conversation_limit=1,
            simulation_limit=1,
            feedback_limit=5,
        ),
        capabilities=AccountCapabilities(
            can_create_additional_conversation=False,
            can_manage_conversation=False,
            can_save_decision=False,
            can_manage_account=False,
            can_use_omnisearch=False,
            can_search_current_workspace=True,
            can_use_grounded_discovery=False,
            can_submit_feedback=True,
        ),
        public_account_access_enabled=False,
    )

    assert registered.model_dump(mode="json")["user"]["avatar_theme"] == "ocean"
    assert "avatar_theme" not in guest.model_dump(mode="json")["user"]


def test_feedback_accepts_account_deletion_request_and_enriches_context(mock_gateway):
    response = client.post(
        "/api/v1/feedback",
        json={
            "type": "account_deletion_request",
            "message": "Private alpha account deletion requested.",
            "context": {"source": "profile_modal"},
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"success": True}
    mock_gateway.create_feedback.assert_called_once()
    call = mock_gateway.create_feedback.call_args.kwargs
    assert call["feedback_type"] == "account_deletion_request"
    assert call["user_id"] == "00000000-0000-0000-0000-000000000001"
    assert call["message"] == "Private alpha account deletion requested."
    context = call["context"]
    assert context["source"] == "profile_modal"
    assert context["account_email"] == "developer@argus.local"
    assert context["profile_language"] == "en"
    assert context["request_user_id"] == "00000000-0000-0000-0000-000000000001"
    assert isinstance(context["requested_at"], str)


def test_create_conversation_uses_dev_memory_fallback_when_supabase_fails(
    mock_gateway,
    monkeypatch,
):
    mock_gateway.create_conversation.side_effect = RuntimeError("supabase unavailable")
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "true")

    response = client.post(
        "/api/v1/conversations",
        json={"language": "en"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    conversation = response.json()["conversation"]
    assert conversation["title"] == "New idea"
    assert conversation["title_source"] == "system_default"


def test_deleted_conversation_messages_supabase_return_not_found(mock_gateway):
    now = utcnow()
    mock_gateway.get_conversation.return_value = Conversation(
        id="deleted-conversation",
        title="Deleted idea",
        title_source="system_default",
        language="en",
        pinned=False,
        archived=False,
        last_message_preview="Old turn",
        deleted_at=now,
        created_at=now,
        updated_at=now,
    )

    response = client.get(
        "/api/v1/conversations/deleted-conversation/messages",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    mock_gateway.list_messages.assert_not_called()


def test_delete_all_conversations_supabase_delegates_with_user_ownership(
    mock_gateway,
):
    mock_gateway.soft_delete_all_conversations.return_value = 3

    response = client.delete(
        "/api/v1/conversations",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "deleted_count": 3}
    mock_gateway.soft_delete_all_conversations.assert_called_once_with(
        scope=PERSONAL, user_id="00000000-0000-0000-0000-000000000001"
    )


def test_supabase_activity_get_and_patch_use_verified_source_identity(
    mock_gateway,
) -> None:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    conversation_id = "11111111-1111-4111-8111-111111111111"
    source_id = "22222222-2222-4222-8222-222222222222"
    conversation = Conversation(
        id=conversation_id,
        title="Activity task",
        title_source="system_default",
        language="en",
        pinned=False,
        archived=False,
        last_message_preview="Done",
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )
    source = {
        "conversation_id": conversation_id,
        "source_kind": "chat_turn",
        "source_id": source_id,
        "status": "completed",
        "occurred_at": now.isoformat(),
        "stage_outcome": "ready_to_respond",
        "result_hydrateable": False,
    }
    mock_gateway.get_conversation.return_value = conversation
    mock_gateway.read_conversation_activity_batch.side_effect = None
    mock_gateway.read_conversation_activity_batch.return_value = [
        {
            "conversation_id": conversation_id,
            "sources": [source],
            "read_state": None,
        }
    ]

    current = client.get(
        f"/api/v1/conversations/{conversation_id}/activity",
        headers={"Authorization": "Bearer test-token"},
    )

    assert current.status_code == 200
    assert current.json()["attention"]["status"] == "new_activity"
    cursor = current.json()["attention"]["cursor"]
    assert cursor == encode_attention_cursor(Boundary("chat_turn", source_id, now))

    mock_gateway.mutate_conversation_activity_read_state.return_value = {
        "outcome": "applied",
        "read_state": {},
    }
    mock_gateway.read_conversation_activity_batch.return_value = [
        {
            "conversation_id": conversation_id,
            "sources": [source],
            "read_state": {
                "read_through_occurred_at": now.isoformat(),
                "read_through_source_kind": "chat_turn",
                "read_through_source_id": source_id,
                "manual_unread_at": None,
            },
        }
    ]

    marked = client.patch(
        f"/api/v1/conversations/{conversation_id}/activity",
        json={"action": "mark_read", "through_attention_cursor": cursor},
        headers={"Authorization": "Bearer test-token"},
    )

    assert marked.status_code == 200
    assert marked.json()["attention"] == {"status": "none", "cursor": None}
    mock_gateway.mutate_conversation_activity_read_state.assert_called_once_with(
        user_id="00000000-0000-0000-0000-000000000001",
        conversation_id=conversation_id,
        action="mark_read",
        source_kind="chat_turn",
        source_id=source_id,
    )


def test_supabase_activity_conflict_maps_to_rfc_problem(mock_gateway) -> None:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    conversation_id = "11111111-1111-4111-8111-111111111111"
    source_id = "22222222-2222-4222-8222-222222222222"
    mock_gateway.get_conversation.return_value = Conversation(
        id=conversation_id,
        title="Activity task",
        title_source="system_default",
        language="en",
        pinned=False,
        archived=False,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )
    mock_gateway.mutate_conversation_activity_read_state.return_value = {
        "outcome": "conflict",
        "read_state": None,
    }
    cursor = encode_attention_cursor(Boundary("chat_turn", source_id, now))

    response = client.patch(
        f"/api/v1/conversations/{conversation_id}/activity",
        json={"action": "mark_read", "through_attention_cursor": cursor},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "attention_cursor_conflict"
    assert response.json()["type"].endswith("/attention-cursor-conflict")


def test_unauthorized_missing_token(mock_gateway):
    import os

    os.environ["NEXT_PUBLIC_MOCK_AUTH"] = "false"
    os.environ["CUADRAO_MOCK_AUTH"] = "false"

    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_unauthorized_invalid_token(mock_gateway):
    import os

    os.environ["NEXT_PUBLIC_MOCK_AUTH"] = "false"
    os.environ["CUADRAO_MOCK_AUTH"] = "false"
    mock_gateway.get_auth_user_from_token.side_effect = Exception("Invalid token")

    response = client.get("/api/v1/me", headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401


def test_unauthorized_revoked_supabase_session(mock_gateway, monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.setattr(api_state, "DATABASE_URL", "postgresql://auth-pool/argus")
    mock_gateway.get_auth_user_from_token.return_value = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "developer@argus.local",
    }
    mock_gateway.private_alpha_email_allowed.return_value = True

    with patch(
        "argus.api.dependencies.auth_session_is_active", return_value=False
    ) as is_active:
        response = client.get(
            "/api/v1/me",
            cookies={"sb-auth-token": "revoked-but-unexpired-token"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    is_active.assert_called_once_with(
        database_url="postgresql://auth-pool/argus",
        token="revoked-but-unexpired-token",
        user_id="00000000-0000-0000-0000-000000000001",
    )
    mock_gateway.get_or_create_profile_for_auth_user.assert_not_called()


def test_auth_session_verification_failure_fails_closed(mock_gateway, monkeypatch):
    from argus.api.auth_sessions import AuthSessionVerificationUnavailable

    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.setattr(api_state, "DATABASE_URL", "postgresql://auth-pool/argus")
    mock_gateway.get_auth_user_from_token.return_value = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "developer@argus.local",
    }

    with patch(
        "argus.api.dependencies.auth_session_is_active",
        side_effect=AuthSessionVerificationUnavailable,
    ):
        response = client.get(
            "/api/v1/me",
            headers={"Authorization": "Bearer valid-but-unverifiable-token"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "auth_session_verification_unavailable"
    mock_gateway.get_or_create_profile_for_auth_user.assert_not_called()


def test_profile_creation_on_first_login(mock_gateway):
    import os

    os.environ["NEXT_PUBLIC_MOCK_AUTH"] = "false"
    os.environ["CUADRAO_MOCK_AUTH"] = "false"
    mock_gateway.get_auth_user_from_token.return_value = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "developer@argus.local",
    }
    mock_gateway.private_alpha_email_allowed.return_value = True

    # simulate user not found initially
    mock_gateway.get_user.return_value = None
    mock_gateway.get_or_create_profile_for_auth_user.return_value = _mock_profile(
        stage="language_selection"
    )

    response = client.get("/api/v1/me", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 200
    mock_gateway.private_alpha_email_allowed.assert_called_once_with(
        "developer@argus.local"
    )
    mock_gateway.get_or_create_profile_for_auth_user.assert_called_once()


def test_authenticated_request_blocks_private_alpha_email_without_access(mock_gateway):
    import os

    os.environ["NEXT_PUBLIC_MOCK_AUTH"] = "false"
    os.environ["CUADRAO_MOCK_AUTH"] = "false"
    mock_gateway.get_auth_user_from_token.return_value = {
        "id": "user-1",
        "email": "disabled@example.com",
    }
    mock_gateway.private_alpha_email_allowed.return_value = False

    response = client.get("/api/v1/me", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 403
    assert response.json()["code"] == "private_alpha_access_required"
    mock_gateway.private_alpha_email_allowed.assert_called_once_with(
        "disabled@example.com"
    )
    mock_gateway.get_or_create_profile_for_auth_user.assert_not_called()


def test_login_sets_session_cookie_for_browser_auth(mock_gateway):
    import os

    email = os.environ.get("MOCK_USER_EMAIL", "developer@argus.local")
    password = os.environ.get("MOCK_USER_PASSWORD", "password")
    mock_gateway.private_alpha_email_allowed.return_value = True
    mock_gateway.login.return_value = {
        "session": {
            "access_token": "access-token-123",
            "refresh_token": "refresh-token-123",
            "expires_in": 3600,
        },
        "user": {"id": "user-1", "email": email},
    }

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "captcha_token": "captcha-proof",
        },
    )

    assert response.status_code == 200
    mock_gateway.private_alpha_email_allowed.assert_called_once_with(email)
    assert "mark_private_alpha_login" not in [
        call[0] for call in mock_gateway.method_calls
    ]
    assert response.cookies.get("sb-auth-token") == "access-token-123"
    assert response.cookies.get("sb-refresh-token") == "refresh-token-123"


def test_login_forces_secure_session_cookies_in_production(mock_gateway, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    mock_gateway.private_alpha_email_allowed.return_value = True
    mock_gateway.login.return_value = {
        "session": {
            "access_token": "access-token-123",
            "refresh_token": "refresh-token-123",
            "expires_in": 3600,
        },
        "user": {"id": "user-1", "email": "beta@example.com"},
    }

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "beta@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
    )

    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "sb-auth-token" in set_cookie
    assert "sb-refresh-token" in set_cookie
    assert "secure" in set_cookie


def test_logout_rejects_untrusted_browser_origin() -> None:
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_origin_rejected"


def test_logout_accepts_configured_browser_origin() -> None:
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}


def test_feedback_submission_persists_with_user_ownership(mock_gateway):
    profile = _mock_profile()
    mock_gateway.get_or_create_mock_user.return_value = profile

    response = client.post(
        "/api/v1/feedback",
        json={
            "type": "general",
            "message": "The private alpha flow feels clear.",
            "context": {"surface": "settings", "metadata": {"path": "/chat"}},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    mock_gateway.check_and_increment_usage_limits.assert_called_once_with(
        user_id=profile.id,
        resource="feedback",
        limits=[("day", 50), ("hour", 20)],
    )
    mock_gateway.create_feedback.assert_called_once_with(
        user_id=profile.id,
        feedback_type="general",
        message="The private alpha flow feels clear.",
        context={"surface": "settings", "page_path": "/chat"},
    )


def test_feedback_submission_sanitizes_browser_context(mock_gateway):
    profile = _mock_profile()
    mock_gateway.get_or_create_mock_user.return_value = profile

    response = client.post(
        "/api/v1/feedback",
        json={
            "type": "bug",
            "message": "The result card copy action felt broken.",
            "context": {
                "source": "message_more_menu",
                "surface": "chat",
                "message_id": "msg-1",
                "conversation_id": "conv-1",
                "artifact_type": "result_card",
                "url": (
                    "https://argus.example/chat?conversation=conv-1&auth=secret"
                    "#private"
                ),
                "timestamp": "2026-06-15T08:00:00.000Z",
                "rating": "negative",
                "tags": ["incorrect", "slow"],
                "hasAttachments": False,
                "attachmentCount": 0,
                "metadata": {"path": "/chat?conversation=conv-1", "token": "secret"},
                "raw_prompt": "buy AAPL with my personal note",
                "email": "person@example.com",
            },
        },
    )

    assert response.status_code == 200
    context = mock_gateway.create_feedback.call_args.kwargs["context"]
    assert context == {
        "source": "message_more_menu",
        "surface": "chat",
        "message_id": "msg-1",
        "conversation_id": "conv-1",
        "artifact_type": "result_card",
        "page_path": "/chat",
        "timestamp": "2026-06-15T08:00:00.000Z",
        "rating": "negative",
        "tags": ["incorrect", "slow"],
        "has_attachments": False,
        "attachment_count": 0,
    }


def test_feedback_rejects_oversized_message(mock_gateway):
    response = client.post(
        "/api/v1/feedback",
        json={
            "type": "general",
            "message": "x" * 5001,
            "context": {"surface": "settings"},
        },
    )

    assert response.status_code == 422
    mock_gateway.create_feedback.assert_not_called()


def test_feedback_rejects_oversized_context(mock_gateway):
    response = client.post(
        "/api/v1/feedback",
        json={
            "type": "general",
            "message": "The private alpha flow feels clear.",
            "context": {f"extra_{index}": "x" for index in range(40)},
        },
    )

    assert response.status_code == 422
    mock_gateway.create_feedback.assert_not_called()


def test_feedback_rejects_deep_context(mock_gateway):
    response = client.post(
        "/api/v1/feedback",
        json={
            "type": "general",
            "message": "The private alpha flow feels clear.",
            "context": {"metadata": {"a": {"b": {"c": {"d": "too deep"}}}}},
        },
    )

    assert response.status_code == 422
    mock_gateway.create_feedback.assert_not_called()


def test_feedback_rejects_large_serialized_context(mock_gateway):
    response = client.post(
        "/api/v1/feedback",
        json={
            "type": "general",
            "message": "The private alpha flow feels clear.",
            "context": {
                "surface": "settings",
                "metadata": {"path": "/chat", "blob": "x" * 9000},
            },
        },
    )

    assert response.status_code == 422
    mock_gateway.create_feedback.assert_not_called()


def test_feedback_quota_exceeded_returns_retry_after(mock_gateway):
    mock_gateway.check_and_increment_usage_limits.side_effect = QuotaExceededError(
        "Quota exceeded for feedback (hour)"
    )

    response = client.post(
        "/api/v1/feedback",
        json={
            "type": "general",
            "message": "The private alpha flow feels clear.",
            "context": {"surface": "settings"},
        },
    )

    assert response.status_code == 429
    assert response.json()["code"] == "too_many_requests"
    assert response.headers.get("Retry-After") == "60"
    mock_gateway.create_feedback.assert_not_called()


def test_signup_allows_email_on_private_alpha_allowlist(mock_gateway, monkeypatch):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True
    mock_gateway.signup.return_value = {
        "session": {
            "access_token": "access-token-123",
            "refresh_token": "refresh-token-123",
            "expires_in": 3600,
        },
        "user": {"id": "user-1", "email": "beta@example.com"},
    }

    response = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "beta@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
    )

    assert response.status_code == 200
    mock_gateway.private_alpha_email_allowed.assert_called_once_with("beta@example.com")
    mock_gateway.signup.assert_called_once()
    mock_gateway.get_or_create_profile_for_auth_user.assert_called_once_with(
        mock_gateway.signup.return_value["user"]
    )
    assert "mark_private_alpha_signup_accepted" not in [
        call[0] for call in mock_gateway.method_calls
    ]
    assert response.cookies.get("sb-auth-token") == "access-token-123"


def test_signup_duplicate_obfuscated_user_does_not_emit_product_event(
    mock_gateway,
    monkeypatch,
):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    captured_events: list[tuple[str, dict[str, object]]] = []

    def fake_capture_product_event(kind: str, **payload: object) -> None:
        captured_events.append((kind, dict(payload)))

    monkeypatch.setattr(
        "argus.api.routers.auth.capture_product_event",
        fake_capture_product_event,
    )
    mock_gateway.private_alpha_email_allowed.return_value = True
    mock_gateway.signup.return_value = {
        "session": None,
        "user": {
            "id": "obfuscated-user-id",
            "email": "existing@example.com",
            "identities": [],
        },
    }

    response = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "existing@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
    )

    assert response.status_code == 200
    assert captured_events == []
    mock_gateway.get_or_create_profile_for_auth_user.assert_not_called()


def test_signup_keeps_obfuscated_duplicate_indistinguishable_without_profile(
    mock_gateway,
    monkeypatch,
):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True
    fresh_provider_response = {
        "session": None,
        "user": {
            "id": "fresh-user-id",
            "email": "fresh@example.com",
            "identities": [{"id": "fresh-identity-id"}],
        },
    }
    duplicate_provider_response = {
        "session": None,
        "user": {
            "id": "obfuscated-user-id",
            "email": "existing@example.com",
            "identities": [],
        },
    }
    mock_gateway.signup.side_effect = [
        fresh_provider_response,
        duplicate_provider_response,
    ]
    profile_rows: set[str] = set()
    def create_profile(auth_user):
        profile_rows.add(str(auth_user["id"]))
        return _mock_profile().model_copy(update={"id": str(auth_user["id"])})

    mock_gateway.get_or_create_profile_for_auth_user.side_effect = create_profile
    headers = {"CF-Connecting-IP": "203.0.113.92"}

    fresh = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "fresh@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
        headers=headers,
    )
    duplicate = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "existing@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
        headers=headers,
    )

    assert fresh.status_code == duplicate.status_code == 200
    assert fresh.json() == fresh_provider_response
    assert duplicate.json() == duplicate_provider_response
    assert set(fresh.json()) == set(duplicate.json()) == {"session", "user"}
    assert set(fresh.json()["user"]) == set(duplicate.json()["user"])
    assert profile_rows == {"fresh-user-id"}
    mock_gateway.get_or_create_profile_for_auth_user.assert_called_once_with(
        fresh_provider_response["user"]
    )


def test_signup_retry_does_not_reveal_profile_creation_through_username(
    mock_gateway,
    monkeypatch,
):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True
    mock_gateway.signup.side_effect = [
        {
            "session": None,
            "user": {
                "id": "fresh-user-id",
                "email": "fresh@example.com",
                "identities": [{"id": "fresh-identity-id"}],
            },
        },
        {
            "session": None,
            "user": {
                "id": "obfuscated-user-id",
                "email": "fresh@example.com",
                "identities": [],
            },
        },
    ]
    headers = {"CF-Connecting-IP": "203.0.113.93"}

    with patch(
        "argus.api.routers.auth.serialized_username_signup",
        side_effect=[
            nullcontext(
                UsernameSignupPrevalidation(
                    auth_user_exists=False,
                    username_available=True,
                )
            ),
            nullcontext(
                UsernameSignupPrevalidation(
                    auth_user_exists=True,
                    username_available=False,
                )
            ),
        ],
    ):
        first = client.post(
            "/api/v1/auth/signup",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "email": "fresh@example.com",
                "password": "password123",
                "captcha_token": "captcha-proof",
                "username": "portfolioalpha",
            },
            headers=headers,
        )
        retry = client.post(
            "/api/v1/auth/signup",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "email": "fresh@example.com",
                "password": "password123",
                "captcha_token": "captcha-proof",
                "username": "portfolioalpha",
            },
            headers=headers,
        )

    assert first.status_code == retry.status_code == 200
    assert retry.json()["user"]["identities"] == []
    assert mock_gateway.signup.call_count == 2
    mock_gateway.get_or_create_profile_for_auth_user.assert_called_once()


def test_signup_normalizes_taken_username_before_creating_auth_user_or_profile(
    mock_gateway,
    monkeypatch,
):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True
    with patch(
        "argus.api.routers.auth.serialized_username_signup",
        return_value=nullcontext(
            UsernameSignupPrevalidation(
                auth_user_exists=False,
                username_available=False,
            )
        ),
    ) as serialize_username:
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "email": "fresh@example.com",
                "password": "password123",
                "captcha_token": "captcha-proof",
                "username": "PortfolioAlpha",
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "auth_signup_failed"
    assert response.json()["detail"] == "Signup failed. Please try again."
    serialize_username.assert_called_once_with(
        api_state.DATABASE_URL,
        "fresh@example.com",
        "portfolioalpha",
    )
    mock_gateway.signup.assert_not_called()
    mock_gateway.get_or_create_profile_for_auth_user.assert_not_called()


def test_signup_passes_selected_language_to_gateway(mock_gateway, monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True
    mock_gateway.signup.return_value = {"user": {"id": "user-1"}}

    response = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "alpha@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
            "language": "es-419",
        },
    )

    assert response.status_code == 200
    mock_gateway.signup.assert_called_once_with(
        age_confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        email="alpha@example.com",
        password="password123",
        display_name=None,
        username=None,
        language="es-419",
        captcha_token="captcha-proof",
    )


def test_signup_rejects_unsupported_language_before_provider_signup(
    mock_gateway,
    monkeypatch,
):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")

    response = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "alpha@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
            "language": "fr-CA",
        },
    )

    assert response.status_code == 422
    mock_gateway.signup.assert_not_called()


@pytest.mark.parametrize("path", ["/api/v1/auth/signup", "/api/v1/auth/login"])
def test_password_auth_requires_captcha_before_provider_call(
    path,
    mock_gateway,
    monkeypatch,
):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True

    response = client.post(
        path,
        json={"email": "alpha@example.com", "password": "password123"},
    )

    assert response.status_code == 422
    mock_gateway.signup.assert_not_called()
    mock_gateway.login.assert_not_called()


@pytest.mark.parametrize("path", ["/api/v1/auth/signup", "/api/v1/auth/login"])
def test_password_auth_bounds_captcha_before_provider_call(
    path,
    mock_gateway,
    monkeypatch,
):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True

    response = client.post(
        path,
        json={
            "email": "alpha@example.com",
            "password": "password123",
            "captcha_token": "x" * 4097,
        },
    )

    assert response.status_code == 422
    mock_gateway.signup.assert_not_called()
    mock_gateway.login.assert_not_called()


def test_public_signup_allowlist_denial_matches_provider_failure(
    mock_gateway,
    monkeypatch,
):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = False
    headers = {"X-Request-Id": "signup-enumeration-regression"}

    allowlist_denied = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "stranger@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
        headers=headers,
    )

    mock_gateway.signup.assert_not_called()
    mock_gateway.private_alpha_email_allowed.assert_called_once_with(
        "stranger@example.com"
    )
    mock_gateway.reset_mock()
    mock_gateway.private_alpha_email_allowed.return_value = True
    mock_gateway.signup.side_effect = RuntimeError("provider rejected captcha")

    provider_failed = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "alpha@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
        headers=headers,
    )

    assert allowlist_denied.status_code == provider_failed.status_code == 400
    assert (
        allowlist_denied.headers["X-Request-Id"]
        == provider_failed.headers["X-Request-Id"]
        == headers["X-Request-Id"]
    )
    assert (
        allowlist_denied.json()
        == provider_failed.json()
        == {
            "type": "https://api.argus.app/problems/auth-signup-failed",
            "title": "Signup Failed",
            "status": 400,
            "detail": "Signup failed. Please try again.",
            "code": "auth_signup_failed",
            "request_id": "signup-enumeration-regression",
        }
    )
    assert "provider rejected captcha" not in provider_failed.text


def test_public_signup_allowlist_denial_matches_taken_username_precheck(
    mock_gateway,
    monkeypatch,
):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    headers = {"X-Request-Id": "signup-username-enumeration-regression"}
    mock_gateway.private_alpha_email_allowed.return_value = False

    allowlist_denied = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "stranger@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
            "username": "takenname",
        },
        headers=headers,
    )

    mock_gateway.reset_mock()
    mock_gateway.private_alpha_email_allowed.return_value = True
    with patch(
        "argus.api.routers.auth.serialized_username_signup",
        return_value=nullcontext(
            UsernameSignupPrevalidation(
                auth_user_exists=False,
                username_available=False,
            )
        ),
    ):
        username_taken = client.post(
            "/api/v1/auth/signup",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "email": "alpha@example.com",
                "password": "password123",
                "captcha_token": "captcha-proof",
                "username": "takenname",
            },
            headers=headers,
        )

    assert allowlist_denied.status_code == username_taken.status_code == 400
    assert allowlist_denied.json() == username_taken.json()
    mock_gateway.signup.assert_not_called()


def test_login_normalizes_private_alpha_access_failures(
    mock_gateway,
    monkeypatch,
):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = False

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "disabled@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert response.json()["detail"] == "Invalid email or password."
    mock_gateway.login.assert_not_called()
    mock_gateway.private_alpha_email_allowed.assert_called_once_with(
        "disabled@example.com"
    )
    assert "mark_private_alpha_login" not in [
        call[0] for call in mock_gateway.method_calls
    ]


def test_login_normalizes_provider_auth_failures(mock_gateway, monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True
    mock_gateway.login.side_effect = RuntimeError("invalid provider password")

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "alpha@example.com",
            "password": "wrong-password",
            "captcha_token": "captcha-proof",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert response.json()["detail"] == "Invalid email or password."
    mock_gateway.login.assert_called_once_with(
        email="alpha@example.com",
        password="wrong-password",
        captcha_token="captcha-proof",
    )


def test_login_rate_limit_blocks_extra_attempt_before_provider(
    mock_gateway,
    monkeypatch,
):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = True
    mock_gateway.login.side_effect = RuntimeError("invalid provider password")
    headers = {"CF-Connecting-IP": "203.0.113.10"}

    for _ in range(auth_router.AUTH_LOGIN_ATTEMPT_LIMIT):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "alpha@example.com",
                "password": "wrong-password",
                "captcha_token": "captcha-proof",
            },
            headers=headers,
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={
            "email": "alpha@example.com",
            "password": "wrong-password",
            "captcha_token": "captcha-proof",
        },
        headers=headers,
    )

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_requests"
    assert blocked.headers.get("Retry-After")
    assert mock_gateway.login.call_count == auth_router.AUTH_LOGIN_ATTEMPT_LIMIT


def test_signup_rate_limit_blocks_extra_attempt_before_allowlist_check(
    mock_gateway,
    monkeypatch,
):
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    mock_gateway.private_alpha_email_allowed.return_value = False
    headers = {"CF-Connecting-IP": "203.0.113.11"}

    for _ in range(auth_router.AUTH_SIGNUP_ATTEMPT_LIMIT):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "age_confirmed_at": "2026-01-01T00:00:00Z",
                "email": "stranger@example.com",
                "password": "password123",
                "captcha_token": "captcha-proof",
            },
            headers=headers,
        )
        assert response.status_code == 400
        assert response.json()["code"] == "auth_signup_failed"

    blocked = client.post(
        "/api/v1/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": "stranger@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
        headers=headers,
    )

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_requests"
    assert blocked.headers.get("Retry-After")
    assert mock_gateway.private_alpha_email_allowed.call_count == (
        auth_router.AUTH_SIGNUP_ATTEMPT_LIMIT
    )
    mock_gateway.signup.assert_not_called()


def test_auth_attempt_limiter_compacts_expired_keys(monkeypatch):
    from argus.api import rate_limits
    from argus.api.routers import auth as auth_router

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setattr(auth_router._AUTH_ATTEMPT_LIMITER, "_compact_threshold", 1)
    monkeypatch.setattr(rate_limits, "monotonic", lambda: 0.0)

    assert (
        auth_router._AUTH_ATTEMPT_LIMITER.record_or_retry_after(
            keys=("login:ip:stale",),
            limit=auth_router.AUTH_LOGIN_ATTEMPT_LIMIT,
            window_seconds=auth_router._AUTH_ATTEMPT_WINDOW_SECONDS,
        )
        is None
    )

    monkeypatch.setattr(
        rate_limits,
        "monotonic",
        lambda: float(auth_router._AUTH_ATTEMPT_WINDOW_SECONDS + 1),
    )
    assert (
        auth_router._AUTH_ATTEMPT_LIMITER.record_or_retry_after(
            keys=("login:ip:fresh",),
            limit=auth_router.AUTH_LOGIN_ATTEMPT_LIMIT,
            window_seconds=auth_router._AUTH_ATTEMPT_WINDOW_SECONDS,
        )
        is None
    )

    assert "login:ip:stale" not in auth_router._AUTH_ATTEMPT_LIMITER._attempts
    assert "login:ip:fresh" in auth_router._AUTH_ATTEMPT_LIMITER._attempts


def test_decision_endpoint_returns_success_when_card_enrichment_fails(
    mock_gateway,
    monkeypatch,
):
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")
    now = utcnow()
    user_id = "00000000-0000-0000-0000-000000000001"
    idea = Idea(
        id="idea-card-fail",
        source_conversation_id="conversation-card-fail",
        title="AAPL evidence idea",
        summary="AAPL evidence summary",
        lifecycle="captured",
        active_version_id="version-card-fail",
        created_at=now,
        updated_at=now,
    )
    version = IdeaVersion(
        id="version-card-fail",
        idea_id=idea.id,
        source_conversation_id="conversation-card-fail",
        source_run_id="run-card-fail",
        version_number=1,
        canonical_spec={"symbols": ["AAPL"], "benchmark_symbol": "SPY"},
        strategy_snapshot={"symbols": ["AAPL"]},
        title=idea.title,
        summary=idea.summary,
        lifecycle="captured",
        created_at=now,
    )
    artifact = EvidenceArtifact(
        id="artifact-card-fail",
        idea_id=idea.id,
        idea_version_id=version.id,
        source_conversation_id="conversation-card-fail",
        source_run_id="run-card-fail",
        artifact_type="backtest",
        lifecycle="captured",
        title="AAPL evidence",
        digest="AAPL backtest versus SPY.",
        payload={
            "provenance": {
                "symbols": ["AAPL"],
                "benchmark_symbol": "SPY",
            }
        },
        created_at=now,
        updated_at=now,
    )
    api_state.store.ideas[idea.id] = idea
    api_state.store.idea_owners[idea.id] = user_id
    api_state.store.idea_versions[version.id] = version
    api_state.store.idea_version_owners[version.id] = user_id
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = user_id
    mock_gateway.mark_result_card_decision_for_run.side_effect = RuntimeError(
        "card enrichment failed"
    )

    response = client.post(
        f"/api/v1/evidence-artifacts/{artifact.id}/decision",
        json={"decision_state": "promising", "note": "Keep watching."},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["decision_state"] == "promising"
    assert body["evidence_artifact"]["lifecycle"] == "decided"
    decisions = [
        decision
        for decision in api_state.store.decision_notes.values()
        if decision.evidence_artifact_id == artifact.id
    ]
    assert len(decisions) == 1
    mock_gateway.capture_current_decision_note.assert_called_once()
    mock_gateway.mark_result_card_decision_for_run.assert_called_once()


def test_decision_endpoint_missing_evidence_returns_404_problem_details(
    mock_gateway,
):
    mock_gateway.get_evidence_artifact.return_value = None

    response = client.post(
        "/api/v1/evidence-artifacts/missing-artifact/decision",
        json={"decision_state": "watching"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "https://api.argus.app/problems/not-found"
    assert body["title"] == "Not Found"
    assert body["status"] == 404
    assert body["code"] == "not_found"
    assert body["request_id"]


def test_decision_endpoint_integrity_failure_returns_500_problem_details(
    mock_gateway,
):
    now = utcnow()
    user_id = "00000000-0000-0000-0000-000000000001"
    idea = Idea(
        id="idea-integrity-fail",
        source_conversation_id="conversation-integrity-fail",
        title="AAPL evidence idea",
        summary="AAPL evidence summary",
        lifecycle="captured",
        active_version_id="version-integrity-fail",
        created_at=now,
        updated_at=now,
    )
    version = IdeaVersion(
        id="version-integrity-fail",
        idea_id=idea.id,
        source_conversation_id="conversation-integrity-fail",
        source_run_id="run-integrity-fail",
        version_number=1,
        canonical_spec={"symbols": ["AAPL"], "benchmark_symbol": "SPY"},
        strategy_snapshot={"symbols": ["AAPL"]},
        title=idea.title,
        summary=idea.summary,
        lifecycle="captured",
        created_at=now,
    )
    artifact = EvidenceArtifact(
        id="artifact-integrity-fail",
        idea_id=idea.id,
        idea_version_id=version.id,
        source_conversation_id="conversation-integrity-fail",
        source_run_id="run-integrity-fail",
        artifact_type="backtest",
        lifecycle="captured",
        title="AAPL evidence",
        digest="AAPL backtest versus SPY.",
        payload={
            "provenance": {
                "symbols": ["AAPL"],
                "benchmark_symbol": "SPY",
            }
        },
        created_at=now,
        updated_at=now,
    )
    api_state.store.ideas[idea.id] = idea
    api_state.store.idea_owners[idea.id] = user_id
    api_state.store.idea_versions[version.id] = version
    api_state.store.idea_version_owners[version.id] = user_id
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = user_id
    mock_gateway.capture_current_decision_note.side_effect = ValueError(
        "Decision capture did not return durable artifact state."
    )

    response = client.post(
        f"/api/v1/evidence-artifacts/{artifact.id}/decision",
        json={"decision_state": "promising", "note": "Keep watching."},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["type"] == "https://api.argus.app/problems/decision-capture-failed"
    assert body["title"] == "Decision Capture Failed"
    assert body["status"] == 500
    assert body["code"] == "decision_capture_failed"
    assert body["request_id"]


def test_search_supabase_returns_cursor_page_and_supported_types(mock_gateway):
    now = utcnow()
    mock_gateway.search_rows.return_value = {
        "conversations": [
            {
                "id": "chat-1",
                "title": "Tesla chat",
                "last_message_preview": "Discussing TSLA",
                "updated_at": now.isoformat(),
                "pinned": True,
            }
        ],
        "strategies": [
            {
                "id": "strat-1",
                "name": "Tesla strategy",
                "symbols": ["TSLA"],
                "template": "rsi_mean_reversion",
                "updated_at": now.isoformat(),
                "pinned": False,
            }
        ],
        "collections": [
            {
                "id": "col-1",
                "name": "Tesla collection",
                "updated_at": now.isoformat(),
                "pinned": False,
            }
        ],
        "runs": [
            {
                "id": "run-1",
                "conversation_result_card": {"title": "TSLA backtest"},
                "created_at": now.isoformat(),
            }
        ],
    }

    response = client.get(
        "/api/v1/search?q=tesla&limit=2",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [(item["type"], item["id"]) for item in payload["items"]] == [
        ("conversation", "chat-1")
    ]
    assert payload["next_cursor"] is None


def test_search_supabase_pushes_bounded_cursor_and_filter_to_gateway(
    mock_gateway,
):
    now = utcnow().replace(microsecond=0)
    pivot_id = "00000000-0000-0000-0000-000000000091"
    mock_gateway.search_rows.return_value = SearchReadResult(
        rows={
            "conversations": [],
            "strategies": [],
            "collections": [],
            "runs": [],
            "ideas": [],
            "evidence": [],
            "decisions": [],
        },
        ledger_counts={
            "promising": 0,
            "watching": 0,
            "rejected": 0,
            "revisit_later": 0,
        },
    )
    cursor = encode_cursor(now.isoformat(), pivot_id)

    response = client.get(
        "/api/v1/search",
        params={
            "q": "Needle",
            "limit": 2,
            "cursor": cursor,
            "decision_state": "promising",
            "include_ledger_groups": "true",
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    mock_gateway.search_rows.assert_called_once_with(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        query="needle",
        source_limit=3,
        cursor_updated_at=now,
        cursor_id=pivot_id,
        decision_state="promising",
        include_ledger_groups=True,
        guest_scope=False,
        guest_conversation_id=None,
    )


def test_search_supabase_pushes_visible_conversation_ids_to_bounded_reader(
    mock_gateway,
):
    conversation_ids = [
        "00000000-0000-0000-0000-000000000091",
        "00000000-0000-0000-0000-000000000092",
    ]
    mock_gateway.search_rows.return_value = SearchReadResult(
        rows={
            "conversations": [],
            "strategies": [],
            "collections": [],
            "runs": [],
            "ideas": [],
            "evidence": [],
            "decisions": [],
        },
        ledger_counts={
            "promising": 0,
            "watching": 0,
            "rejected": 0,
            "revisit_later": 0,
        },
    )

    response = client.get(
        "/api/v1/search",
        params={
            "q": "",
            "limit": 2,
            "conversation_id": conversation_ids,
            "include_ledger_groups": "true",
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    mock_gateway.search_rows.assert_called_once_with(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        query="",
        source_limit=2,
        cursor_updated_at=None,
        cursor_id=None,
        decision_state=None,
        include_ledger_groups=True,
        guest_scope=False,
        guest_conversation_id=None,
        conversation_ids=conversation_ids,
    )
    assert response.json()["next_cursor"] is None


def test_search_reader_cursor_failure_maps_to_invalid_cursor_problem(
    mock_gateway,
):
    try:
        from argus.domain.postgres_search_reader import SearchCursorError
    except ModuleNotFoundError:
        pytest.fail("bounded Postgres Search reader is not implemented")
    now = utcnow().replace(microsecond=0)
    mock_gateway.search_rows.side_effect = SearchCursorError("missing pivot")

    response = client.get(
        "/api/v1/search",
        params={
            "q": "needle",
            "cursor": encode_cursor(
                now.isoformat(),
                "00000000-0000-0000-0000-000000000091",
            ),
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert response.json()["detail"] == "Invalid cursor."


def test_search_supabase_rejects_naive_cursor_before_database_read(
    mock_gateway,
):
    response = client.get(
        "/api/v1/search",
        params={
            "q": "needle",
            "cursor": encode_cursor(
                "2026-07-27T12:00:00",
                "00000000-0000-0000-0000-000000000091",
            ),
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid cursor."
    mock_gateway.search_rows.assert_not_called()


def test_search_supabase_returns_typed_p1_artifacts(mock_gateway):
    now = utcnow()
    mock_gateway.search_rows.return_value = {
        "conversations": [],
        "strategies": [],
        "collections": [],
        "runs": [
            {
                "id": "run-1",
                "conversation_id": "conversation-1",
                "conversation_result_card": {
                    "title": "AAPL MSFT evidence run",
                    "symbols": ["AAPL", "MSFT"],
                    "artifact_type": "backtest",
                    "evidence_artifact_id": "artifact-1",
                    "evidence_lifecycle": "captured",
                    "context_packets": [{"raw": "do not expose"}],
                },
                "created_at": now.isoformat(),
                "benchmark_symbol": "SPY",
            }
        ],
        "ideas": [
            {
                "id": "idea-1",
                "title": "AAPL MSFT Buy and Hold",
                "summary": "Test AAPL and MSFT against SPY.",
                "lifecycle": "captured",
                "active_version_id": "version-1",
                "source_conversation_id": "conversation-1",
                "updated_at": now.isoformat(),
            }
        ],
        "evidence": [
            {
                "id": "artifact-1",
                "title": "AAPL MSFT evidence run",
                "digest": "AAPL MSFT beat SPY in the test window.",
                "lifecycle": "captured",
                "artifact_type": "backtest",
                "source_run_id": "run-1",
                "source_conversation_id": "conversation-1",
                "updated_at": now.isoformat(),
                "payload": {
                    "result_card": {
                        "context_packets": [{"raw": "do not expose"}],
                    },
                    "provenance": {
                        "symbols": ["AAPL", "MSFT"],
                        "benchmark_symbol": "SPY",
                    },
                },
            }
        ],
        "decisions": [
            {
                "id": "decision-1",
                "decision_state": "promising",
                "note": "Worth revisiting.",
                "evidence_artifact_id": "artifact-1",
                "artifact_title": "AAPL MSFT evidence run",
                "artifact_digest": "AAPL MSFT beat SPY in the test window.",
                "artifact_payload": {
                    "quick_take": "AAPL and MSFT beat SPY.",
                    "provenance": {
                        "symbols": ["AAPL", "MSFT"],
                        "benchmark_symbol": "SPY",
                    },
                },
                "source_conversation_id": "conversation-1",
                "updated_at": now.isoformat(),
            }
        ],
    }

    response = client.get(
        "/api/v1/search?q=aapl&limit=20",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["type"] == "conversation"
    assert item["id"] == item["conversation_id"] == "conversation-1"
    assert item["dossier"]["decision"] == {
        "state": "promising",
        "note": "Worth revisiting.",
        "run_label": "AAPL MSFT evidence run",
    }
    assert item["dossier"]["tested"]["symbols"] == ["AAPL", "MSFT"]
    assert item["total_runs"] == 1
    assert item["decided_runs"] == 1


def test_search_supabase_projects_localized_actions_without_generation(
    monkeypatch: pytest.MonkeyPatch,
    mock_gateway,
):
    from argus.agent_runtime import runtime as agent_runtime
    from argus.domain import engine as domain_engine

    def unexpected_external_call(*_: object, **__: object) -> None:
        raise AssertionError("Search action projection must not call external systems")

    monkeypatch.setattr(domain_engine, "resolve_asset", unexpected_external_call)
    monkeypatch.setattr(domain_engine, "fetch_ohlcv", unexpected_external_call)
    monkeypatch.setattr(agent_runtime, "run_agent_turn", unexpected_external_call)
    spanish_user = _mock_profile(language="es-419")
    mock_gateway.get_or_create_profile_for_auth_user.return_value = spanish_user
    mock_gateway.get_or_create_mock_user.return_value = spanish_user
    now = utcnow()
    mock_gateway.search_rows.return_value = {
        "conversations": [
            {
                "id": "conversation-action-es",
                "title": "Dossier GLD",
                "updated_at": now.isoformat(),
                "pinned": False,
            }
        ],
        "runs": [
            {
                "id": "run-action-es",
                "conversation_id": "conversation-action-es",
                "status": "completed",
                "asset_class": "equity",
                "symbols": ["GLD"],
                "benchmark_symbol": "SPY",
                "config_snapshot": {
                    "template": "buy_and_hold",
                    "timeframe": "1D",
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "resolved_parameters": {
                        "sizing_mode": "capital_amount",
                        "capital_amount": 10_000,
                    },
                },
                "conversation_result_card": {
                    "title": "GLD anual",
                    "evidence_artifact_id": "evidence-action-es",
                    "idea_id": "idea-action-es",
                    "idea_version_id": "idea-version-action-es",
                },
                "created_at": now.isoformat(),
            }
        ],
        "ideas": [],
        "evidence": [
            {
                "id": "evidence-action-es",
                "source_conversation_id": "conversation-action-es",
                "source_run_id": "run-action-es",
                "title": "GLD anual",
                "digest": "GLD frente a SPY.",
                "payload": {},
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        ],
        "decisions": [
            {
                "id": "decision-action-es",
                "source_conversation_id": "conversation-action-es",
                "evidence_artifact_id": "evidence-action-es",
                "decision_state": "promising",
                "note": "Revisar el próximo año.",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        ],
        "messages": [],
    }

    response = client.get(
        "/api/v1/search?q=GLD&limit=20",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    conversation = response.json()["items"][0]
    retest, decision = conversation["dossier"]["actions"]
    # Localization no longer rides a generated prompt: the action carries
    # identity, policy, and server-owned pre-click eligibility only.
    assert retest == {
        "type": "retest_run",
        "source_run_id": "run-action-es",
        "run_label": retest["run_label"],
        "window_policy": "preserve_start_ending_latest_available",
        "contract_version": "argus_retest_run/v2",
        "state": "new_data_available",
        "reason_code": None,
        "repair": None,
    }
    assert decision == {
        "type": "decision",
        "availability": "available",
        "evidence_artifact_id": "evidence-action-es",
        "decision_state": "promising",
        "note": "Revisar el próximo año.",
        "run_label": "GLD anual",
    }


def test_search_supabase_decision_without_payload_keeps_honest_fallback(
    mock_gateway,
):
    now = utcnow()
    mock_gateway.search_rows.return_value = {
        "conversations": [],
        "strategies": [],
        "collections": [],
        "runs": [],
        "ideas": [],
        "evidence": [],
        "decisions": [
            {
                "id": "decision-2",
                "decision_state": "rejected",
                "note": "Too volatile for me.",
                "evidence_artifact_id": "artifact-2",
                "artifact_title": "NVDA momentum test",
                "artifact_digest": "NVDA lost to SPY in the window.",
                "source_conversation_id": "conversation-2",
                "updated_at": now.isoformat(),
            }
        ],
    }

    response = client.get(
        "/api/v1/search?q=nvda&limit=20",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["type"] == "conversation"
    assert item["dossier"] is None
    assert item["total_runs"] == 0
    assert item["decided_runs"] == 0
    assert item["decision_states"] == ["rejected"]


def test_search_supabase_orders_p1_artifacts_before_source_conversation(
    mock_gateway,
):
    now = utcnow()
    newer = (now + timedelta(minutes=5)).replace(microsecond=0)
    mock_gateway.search_rows.return_value = {
        "conversations": [
            {
                "id": "conversation-1",
                "title": "AAPL MSFT TSLA source wrapper",
                "last_message_preview": "AAPL MSFT TSLA chat wrapper",
                "updated_at": newer.isoformat(),
                "pinned": False,
            }
        ],
        "strategies": [],
        "collections": [],
        "runs": [
            {
                "id": "run-1",
                "conversation_id": "conversation-1",
                "conversation_result_card": {
                    "title": "AAPL, MSFT, TSLA evidence backtest",
                    "symbols": ["AAPL", "MSFT", "TSLA"],
                    "artifact_type": "backtest",
                    "evidence_artifact_id": "artifact-1",
                    "evidence_lifecycle": "captured",
                },
                "created_at": (now.replace(microsecond=0)).isoformat(),
                "benchmark_symbol": "SPY",
            }
        ],
        "ideas": [
            {
                "id": "idea-1",
                "title": "AAPL, MSFT, TSLA evidence idea",
                "summary": "AAPL, MSFT, TSLA evidence summary.",
                "lifecycle": "captured",
                "active_version_id": "version-1",
                "source_conversation_id": "conversation-1",
                "updated_at": now.isoformat(),
            }
        ],
        "evidence": [
            {
                "id": "artifact-1",
                "title": "AAPL, MSFT, TSLA evidence artifact",
                "digest": "AAPL, MSFT, TSLA evidence artifact digest.",
                "lifecycle": "captured",
                "artifact_type": "backtest",
                "source_run_id": "run-1",
                "source_conversation_id": "conversation-1",
                "updated_at": now.isoformat(),
                "payload": {
                    "provenance": {
                        "symbols": ["AAPL", "MSFT", "TSLA"],
                        "benchmark_symbol": "SPY",
                    },
                },
            }
        ],
        "decisions": [
            {
                "id": "decision-1",
                "decision_state": "promising",
                "note": "AAPL, MSFT, TSLA evidence decision note.",
                "evidence_artifact_id": "artifact-1",
                "artifact_title": "AAPL, MSFT, TSLA evidence artifact",
                "artifact_digest": "AAPL, MSFT, TSLA evidence artifact digest.",
                "source_conversation_id": "conversation-1",
                "updated_at": now.isoformat(),
            }
        ],
    }

    response = client.get(
        "/api/v1/search?q=AAPL%20MSFT%20TSLA&limit=10",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert [(item["type"], item["id"]) for item in response.json()["items"]] == [
        ("conversation", "conversation-1")
    ]


def test_search_supabase_preserves_pinned_chat_above_p1_artifacts(mock_gateway):
    now = utcnow().replace(microsecond=0)
    mock_gateway.search_rows.return_value = {
        "conversations": [
            {
                "id": "conversation-1",
                "title": "AAPL pinned conversation",
                "last_message_preview": "AAPL pinned source",
                "updated_at": (now + timedelta(minutes=5)).isoformat(),
                "pinned": True,
            }
        ],
        "strategies": [],
        "collections": [],
        "runs": [],
        "ideas": [],
        "evidence": [
            {
                "id": "artifact-1",
                "title": "AAPL evidence artifact",
                "digest": "AAPL evidence artifact digest.",
                "lifecycle": "captured",
                "artifact_type": "backtest",
                "source_run_id": "run-1",
                "source_conversation_id": "conversation-1",
                "updated_at": now.isoformat(),
                "payload": {
                    "provenance": {
                        "symbols": ["AAPL"],
                        "benchmark_symbol": "SPY",
                    },
                },
            }
        ],
        "decisions": [],
    }

    response = client.get(
        "/api/v1/search?q=aapl&limit=10",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert [(item["type"], item["id"]) for item in response.json()["items"]] == [
        ("conversation", "conversation-1")
    ]


def test_search_supabase_preserves_exact_chat_above_lower_relevance_p1_artifacts(
    mock_gateway,
):
    now = utcnow().replace(microsecond=0)
    mock_gateway.search_rows.return_value = {
        "conversations": [
            {
                "id": "conversation-1",
                "title": "AAPL",
                "last_message_preview": "AAPL exact source",
                "updated_at": (now + timedelta(minutes=5)).isoformat(),
                "pinned": False,
            }
        ],
        "strategies": [],
        "collections": [],
        "runs": [],
        "ideas": [],
        "evidence": [
            {
                "id": "artifact-1",
                "title": "AAPL evidence artifact",
                "digest": "AAPL evidence artifact digest.",
                "lifecycle": "captured",
                "artifact_type": "backtest",
                "source_run_id": "run-1",
                "source_conversation_id": "conversation-1",
                "updated_at": now.isoformat(),
                "payload": {
                    "provenance": {
                        "symbols": ["AAPL"],
                        "benchmark_symbol": "SPY",
                    },
                },
            }
        ],
        "decisions": [],
    }

    response = client.get(
        "/api/v1/search?q=aapl&limit=10",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert [(item["type"], item["id"]) for item in response.json()["items"]] == [
        ("conversation", "conversation-1")
    ]


def test_search_supabase_preserves_symbol_match_above_lower_relevance_p1_artifact(
    mock_gateway,
):
    now = utcnow().replace(microsecond=0)
    mock_gateway.search_rows.return_value = {
        "conversations": [],
        "strategies": [
            {
                "id": "strategy-1",
                "name": "Saved alpha strategy",
                "symbols": ["AAPL"],
                "template": "buy_hold",
                "updated_at": now.isoformat(),
                "pinned": False,
            }
        ],
        "collections": [],
        "runs": [],
        "ideas": [],
        "evidence": [
            {
                "id": "artifact-1",
                "title": "AAPL evidence artifact",
                "digest": "AAPL evidence artifact digest.",
                "lifecycle": "captured",
                "artifact_type": "backtest",
                "source_run_id": "run-1",
                "source_conversation_id": "conversation-1",
                "updated_at": (now + timedelta(minutes=5)).isoformat(),
                "payload": {
                    "provenance": {
                        "symbols": ["MSFT"],
                        "benchmark_symbol": "SPY",
                    },
                },
            }
        ],
        "decisions": [],
    }

    response = client.get(
        "/api/v1/search?q=aapl&limit=10",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert [(item["type"], item["id"]) for item in response.json()["items"]] == [
        ("conversation", "conversation-1")
    ]


def test_history_supabase_requests_non_archived_rows_by_default(mock_gateway):
    mock_gateway.list_history_rows.return_value = {
        "runs": [],
        "conversations": [],
        "strategies": [],
        "collections": [],
    }

    response = client.get(
        "/api/v1/history",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    mock_gateway.list_history_rows.assert_called_once_with(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        limit=21,
        cursor_activity_at=None,
        cursor_id=None,
        cursor_pinned=None,
        cursor_type_rank=None,
        deleted=False,
        archived=False,
    )


def test_history_supabase_chat_items_carry_title_source(mock_gateway):
    mock_gateway.list_history_rows.return_value = {
        "runs": [],
        "conversations": [
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "title": "NVDA Buy and Hold",
                "title_source": "ai_generated",
                "last_message_preview": "Use NVDA from January 3, 2023",
                "pinned": False,
                "updated_at": "2026-07-01T00:00:00+00:00",
            }
        ],
        "strategies": [
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "name": "NVDA momentum",
                "symbols": ["NVDA"],
                "pinned": False,
                "updated_at": "2026-07-01T00:00:00+00:00",
            }
        ],
        "collections": [],
    }

    response = client.get(
        "/api/v1/history",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    chat_items = [item for item in response.json()["items"] if item["type"] == "chat"]
    assert [item["title_source"] for item in chat_items] == ["ai_generated"]
    non_chat_items = [item for item in response.json()["items"] if item["type"] != "chat"]
    assert non_chat_items
    assert all("title_source" not in item for item in non_chat_items)
    assert all("activity" not in item for item in non_chat_items)
    mock_gateway.reconcile_conversation_activity_turns.assert_called_once_with(
        user_id="00000000-0000-0000-0000-000000000001",
        conversation_ids=["22222222-2222-2222-2222-222222222222"],
    )
    mock_gateway.read_conversation_activity_batch.assert_called_once_with(
        user_id="00000000-0000-0000-0000-000000000001",
        conversation_ids=["22222222-2222-2222-2222-222222222222"],
    )


def test_history_supabase_can_request_archived_rows(mock_gateway):
    mock_gateway.list_history_rows.return_value = {
        "runs": [],
        "conversations": [],
        "strategies": [],
        "collections": [],
    }

    response = client.get(
        "/api/v1/history?archived=true",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    mock_gateway.list_history_rows.assert_called_once_with(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        limit=21,
        cursor_activity_at=None,
        cursor_id=None,
        cursor_pinned=None,
        cursor_type_rank=None,
        deleted=False,
        archived=True,
    )


def test_history_supabase_middle_page_uses_cursor_pivot_outside_candidates(
    mock_gateway,
):
    pivot_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    candidate_at = pivot_at - timedelta(minutes=1)
    pivot_id = "22222222-2222-2222-2222-222222222222"
    mock_gateway.list_history_rows.return_value = {
        "runs": [],
        "conversations": [],
        "strategies": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "Next strategy",
                "symbols": ["AAPL"],
                "pinned": False,
                "updated_at": candidate_at.isoformat(),
            }
        ],
        "collections": [],
    }

    response = client.get(
        "/api/v1/history",
        params={
            "limit": 2,
            "cursor": encode_cursor(pivot_at.isoformat(), pivot_id),
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        "11111111-1111-1111-1111-111111111111"
    ]
    mock_gateway.list_history_rows.assert_called_once_with(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        limit=3,
        cursor_activity_at=pivot_at,
        cursor_id=pivot_id,
        cursor_pinned=None,
        cursor_type_rank=None,
        deleted=False,
        archived=False,
    )


def test_history_supabase_cursor_retains_original_pivot_rank(mock_gateway):
    newest_at = datetime(2026, 7, 2, 12, 2, tzinfo=timezone.utc)
    pivot_at = newest_at - timedelta(minutes=1)
    sentinel_at = pivot_at - timedelta(minutes=1)
    pivot_id = "22222222-2222-2222-2222-222222222222"
    mock_gateway.list_history_rows.side_effect = [
        {
            "runs": [],
            "conversations": [],
            "strategies": [
                {
                    "id": "33333333-3333-3333-3333-333333333333",
                    "name": "Newest pinned strategy",
                    "symbols": ["AAPL"],
                    "pinned": True,
                    "updated_at": newest_at.isoformat(),
                },
                {
                    "id": pivot_id,
                    "name": "Pinned page pivot",
                    "symbols": ["MSFT"],
                    "pinned": True,
                    "updated_at": pivot_at.isoformat(),
                },
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "Unpinned sentinel",
                    "symbols": ["NVDA"],
                    "pinned": False,
                    "updated_at": sentinel_at.isoformat(),
                },
            ],
            "collections": [],
        },
        {
            "runs": [],
            "conversations": [],
            "strategies": [],
            "collections": [],
        },
    ]

    first_page = client.get(
        "/api/v1/history?limit=2",
        headers={"Authorization": "Bearer test-token"},
    )
    assert first_page.status_code == 200
    cursor = first_page.json()["next_cursor"]
    assert cursor is not None

    second_page = client.get(
        "/api/v1/history",
        params={"limit": 2, "cursor": cursor},
        headers={"Authorization": "Bearer test-token"},
    )

    assert second_page.status_code == 200
    assert mock_gateway.list_history_rows.call_args_list[1].kwargs == {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "scope": PERSONAL,
        "limit": 3,
        "cursor_activity_at": pivot_at,
        "cursor_id": pivot_id,
        "cursor_pinned": True,
        "cursor_type_rank": 3,
        "deleted": False,
        "archived": False,
    }


def test_history_supabase_missing_or_ambiguous_pivot_uses_invalid_cursor_problem(
    mock_gateway,
):
    pivot_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    mock_gateway.list_history_rows.side_effect = HistoryCursorError

    response = client.get(
        "/api/v1/history",
        params={
            "cursor": encode_cursor(
                pivot_at.isoformat(),
                "22222222-2222-2222-2222-222222222222",
            )
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert response.json()["detail"] == "Invalid cursor."


@pytest.mark.parametrize(
    ("cursor_timestamp", "cursor_id"),
    [
        ("2026-07-27T12:00:00", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        (
            "2026-07-27T12:00:00+00:00",
            "{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}",
        ),
        (
            "2026-07-27T12:00:00+00:00",
            "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        ),
    ],
)
def test_history_supabase_malformed_cursor_uses_invalid_cursor_problem_before_pool(
    mock_gateway,
    cursor_timestamp: str,
    cursor_id: str,
):
    pool = MagicMock()
    connection = pool.connection.return_value.__enter__.return_value
    database_cursor = connection.cursor.return_value.__enter__.return_value
    database_cursor.fetchall.side_effect = [
        [{"source_type": "strategy", "pinned": False, "type_rank": 3}],
        [],
    ]
    mock_gateway.list_history_rows.side_effect = PostgresHistoryReader(pool).list_rows

    response = client.get(
        "/api/v1/history",
        params={
            "cursor": encode_cursor(cursor_timestamp, cursor_id),
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert response.json()["detail"] == "Invalid cursor."
    pool.connection.assert_not_called()


def test_conversation_first_middle_final_and_empty_pages(mock_gateway):
    updated_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    conversations = [
        Conversation(
            id=f"conv-{idx}",
            title=f"Idea {idx}",
            title_source="system_default",
            language="en",
            pinned=idx < 2,
            archived=False,
            last_message_preview=f"Preview {idx}",
            deleted_at=None,
            created_at=updated_at,
            updated_at=updated_at,
        )
        for idx in range(5)
    ]
    mock_gateway.list_conversations.side_effect = [
        conversations[:3],
        conversations[2:5],
        conversations[4:],
        [],
    ]
    latest_messages = {
        conversation.id: {
            "conversation_id": conversation.id,
            "role": "user",
            "content": f"Most recent user message {index}",
            "metadata": {},
        }
        for index, conversation in enumerate(conversations)
    }
    mock_gateway.read_conversation_preview_messages.side_effect = (
        lambda *, user_id, conversation_ids: [
            latest_messages[conversation_id] for conversation_id in conversation_ids
        ]
    )

    first_page = client.get(
        "/api/v1/conversations?limit=2",
        headers={"Authorization": "Bearer test-token"},
    )
    assert first_page.status_code == 200
    payload = first_page.json()
    assert len(payload["items"]) == 2
    assert payload["next_cursor"] is not None

    second_page = client.get(
        f"/api/v1/conversations?limit=2&cursor={payload['next_cursor']}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert [item["id"] for item in second_payload["items"]] == ["conv-2", "conv-3"]
    assert second_payload["next_cursor"] is not None

    final_page = client.get(
        f"/api/v1/conversations?limit=2&cursor={second_payload['next_cursor']}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert final_page.status_code == 200
    expected_final = conversations[4].model_dump(mode="json")
    expected_final["activity"] = {
        "latest_message_id": None,
        "operation": {"status": "idle", "kind": None, "updated_at": None},
        "attention": {"status": "none", "cursor": None},
    }
    expected_final["last_message_preview"] = latest_messages["conv-4"]["content"]
    expected_final["preview"] = {
        "kind": "text",
        "text": latest_messages["conv-4"]["content"],
        "symbols": [],
        "template": None,
    }
    assert final_page.json() == {
        "items": [expected_final],
        "next_cursor": None,
    }

    empty_page = client.get(
        "/api/v1/conversations?limit=2",
        headers={"Authorization": "Bearer test-token"},
    )
    assert empty_page.status_code == 200
    assert empty_page.json() == {"items": [], "next_cursor": None}

    calls = mock_gateway.list_conversations.call_args_list
    assert calls[0].kwargs == {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "scope": PERSONAL,
        "limit": 2,
        "archived": None,
        "deleted": False,
        "cursor_updated_at": None,
        "cursor_id": None,
    }
    assert calls[1].kwargs["cursor_updated_at"] == updated_at
    assert calls[1].kwargs["cursor_id"] == "conv-1"
    assert calls[2].kwargs["cursor_updated_at"] == updated_at
    assert calls[2].kwargs["cursor_id"] == "conv-3"
    assert calls[3].kwargs["cursor_updated_at"] is None
    assert calls[3].kwargs["cursor_id"] is None
    projected_pages = [
        call.kwargs["conversation_ids"]
        for call in mock_gateway.read_conversation_activity_batch.call_args_list
    ]
    assert projected_pages == [
        ["conv-0", "conv-1"],
        ["conv-2", "conv-3"],
        ["conv-4"],
    ]
    assert [
        call.kwargs["conversation_ids"]
        for call in mock_gateway.read_conversation_preview_messages.call_args_list
    ] == [page for page in projected_pages for _ in range(2)]
    assert all(
        call.kwargs["user_id"] == "00000000-0000-0000-0000-000000000001"
        for call in mock_gateway.read_conversation_preview_messages.call_args_list
    )


def test_conversation_missing_pivot_uses_existing_invalid_cursor_problem(mock_gateway):
    cursor = encode_cursor(
        datetime(2026, 7, 1, tzinfo=timezone.utc).isoformat(),
        "missing-conversation",
    )
    mock_gateway.list_conversations.side_effect = ConversationCursorError(
        "invalid conversation cursor pivot"
    )

    response = client.get(
        f"/api/v1/conversations?limit=2&cursor={cursor}",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid cursor."


def test_conversations_cursor_supabase_pages_beyond_one_hundred_items(mock_gateway):
    now = datetime(2026, 7, 1, tzinfo=timezone.utc)
    conversations = [
        Conversation(
            id=f"conv-{idx:03d}",
            title=f"Idea {idx}",
            title_source="system_default",
            language="en",
            pinned=False,
            archived=False,
            last_message_preview=f"Preview {idx}",
            deleted_at=None,
            created_at=now - timedelta(seconds=idx),
            updated_at=now - timedelta(seconds=idx),
        )
        for idx in range(130)
    ]
    mock_gateway.list_conversations.side_effect = [
        conversations[:51],
        conversations[50:101],
        conversations[100:],
    ]

    first_page = client.get(
        "/api/v1/conversations?limit=50",
        headers={"Authorization": "Bearer test-token"},
    )
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert len(first_payload["items"]) == 50
    assert first_payload["next_cursor"] is not None

    second_page = client.get(
        f"/api/v1/conversations?limit=50&cursor={first_payload['next_cursor']}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert len(second_payload["items"]) == 50
    assert second_payload["next_cursor"] is not None

    third_page = client.get(
        f"/api/v1/conversations?limit=50&cursor={second_payload['next_cursor']}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert third_page.status_code == 200
    third_payload = third_page.json()
    assert len(third_payload["items"]) == 30
    assert third_payload["next_cursor"] is None

    all_ids = [
        item["id"]
        for payload in (first_payload, second_payload, third_payload)
        for item in payload["items"]
    ]
    assert len(all_ids) == len(set(all_ids)) == 130


def test_message_first_middle_final_and_empty_pages(mock_gateway):
    created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    conversation = Conversation(
        id="20000000-0000-0000-0000-000000000001",
        title="Paged messages",
        title_source="system_default",
        language="en",
        created_at=created_at,
        updated_at=created_at,
    )
    messages = [
        Message(
            id=f"30000000-0000-0000-0000-{idx:012d}",
            conversation_id=conversation.id,
            role="user",
            content=f"Message {idx}",
            created_at=created_at,
            metadata={},
        )
        for idx in range(5)
    ]
    mock_gateway.get_conversation.return_value = conversation
    mock_gateway.list_messages.side_effect = [
        messages[:3],
        messages[2:5],
        messages[4:],
        [],
    ]

    first_page = client.get(
        f"/api/v1/conversations/{conversation.id}/messages?limit=2",
        headers={"Authorization": "Bearer test-token"},
    )
    assert first_page.status_code == 200
    payload = first_page.json()
    assert [item["id"] for item in payload["items"]] == [
        messages[0].id,
        messages[1].id,
    ]
    assert payload["next_cursor"] is not None

    second_page = client.get(
        (
            f"/api/v1/conversations/{conversation.id}/messages"
            f"?limit=2&cursor={payload['next_cursor']}"
        ),
        headers={"Authorization": "Bearer test-token"},
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert [item["id"] for item in second_payload["items"]] == [
        messages[2].id,
        messages[3].id,
    ]
    assert second_payload["next_cursor"] is not None

    final_page = client.get(
        (
            f"/api/v1/conversations/{conversation.id}/messages"
            f"?limit=2&cursor={second_payload['next_cursor']}"
        ),
        headers={"Authorization": "Bearer test-token"},
    )
    assert final_page.status_code == 200
    assert final_page.json() == {
        "items": [messages[4].model_dump(mode="json")],
        "next_cursor": None,
        "surface": "personal",
    }

    empty_page = client.get(
        f"/api/v1/conversations/{conversation.id}/messages?limit=2",
        headers={"Authorization": "Bearer test-token"},
    )
    assert empty_page.status_code == 200
    assert empty_page.json() == {"items": [], "next_cursor": None, "surface": "personal"}

    calls = mock_gateway.list_messages.call_args_list
    assert calls[0].kwargs == {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "conversation_id": conversation.id,
        "limit": 2,
        "cursor_created_at": None,
        "cursor_id": None,
        "page": True,
    }
    assert calls[1].kwargs["cursor_created_at"] == created_at
    assert calls[1].kwargs["cursor_id"] == messages[1].id
    assert calls[2].kwargs["cursor_created_at"] == created_at
    assert calls[2].kwargs["cursor_id"] == messages[3].id
    assert calls[3].kwargs["cursor_created_at"] is None
    assert calls[3].kwargs["cursor_id"] is None


def test_message_malformed_pivot_uses_existing_invalid_cursor_problem(mock_gateway):
    now = utcnow()
    conversation = Conversation(
        id="20000000-0000-0000-0000-000000000002",
        title="Malformed message cursor",
        title_source="system_default",
        language="en",
        created_at=now,
        updated_at=now,
    )
    cursor = encode_cursor(
        datetime(2026, 7, 1, tzinfo=timezone.utc).isoformat(),
        "missing-message",
    )
    mock_gateway.get_conversation.return_value = conversation

    response = client.get(
        (f"/api/v1/conversations/{conversation.id}/messages" f"?limit=2&cursor={cursor}"),
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid cursor."
    mock_gateway.list_messages.assert_not_called()


class _MessagePageContextGateway:
    def __init__(
        self,
        delegate: Any,
        *,
        page_messages: list[Message],
        later_work: list[Message],
        represented_request_ids: set[str] | None = None,
    ) -> None:
        self._delegate = delegate
        self._page_messages = page_messages
        self._later_work = later_work
        self._represented_request_ids = represented_request_ids or set()
        self.context_calls: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def list_messages(self, **_: Any) -> list[Message]:
        return list(self._page_messages)

    def list_message_page_context(
        self,
        **kwargs: Any,
    ) -> tuple[list[Message], set[str]]:
        self.context_calls.append(kwargs)
        return list(self._later_work), set(self._represented_request_ids)


def test_message_page_later_artifact_preserves_retry_supersession(
    mock_gateway,
) -> None:
    created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    conversation = Conversation(
        id="20000000-0000-0000-0000-000000000003",
        title="Retry reconciliation",
        title_source="system_default",
        language="en",
        created_at=created_at,
        updated_at=created_at,
    )
    user_message = Message(
        id="30000000-0000-0000-0000-000000000010",
        conversation_id=conversation.id,
        role="user",
        content="Test AAPL.",
        created_at=created_at,
        metadata={},
    )
    failed_message = Message(
        id="30000000-0000-0000-0000-000000000011",
        conversation_id=conversation.id,
        role="assistant",
        content="Something went wrong.",
        created_at=created_at + timedelta(microseconds=1),
        metadata={
            "conversation_mode": "recovery",
            "agent_runtime_stage_outcome": "agent_runtime_failure",
            "recovery": {"code": "runtime_failure", "retryable": True},
            "retry_last_turn": {"message": user_message.content},
        },
    )
    lookahead = Message(
        id="30000000-0000-0000-0000-000000000012",
        conversation_id=conversation.id,
        role="assistant",
        content="Still working.",
        created_at=created_at + timedelta(microseconds=2),
        metadata={},
    )
    later_artifact = Message(
        id="30000000-0000-0000-0000-000000000013",
        conversation_id=conversation.id,
        role="assistant",
        content="Ready to run.",
        created_at=created_at + timedelta(microseconds=3),
        metadata={"confirmation_card": {"status": "ready_to_run"}},
    )
    gateway = _MessagePageContextGateway(
        mock_gateway,
        page_messages=[user_message, failed_message, lookahead],
        later_work=[later_artifact],
    )
    mock_gateway.get_conversation.return_value = conversation

    with patch("argus.api.state.supabase_gateway", gateway):
        response = client.get(
            f"/api/v1/conversations/{conversation.id}/messages?limit=2",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    failed = response.json()["items"][1]
    assert failed["id"] == failed_message.id
    assert "retry_last_turn" not in failed["metadata"]
    assert failed["metadata"]["recovery"]["retryable"] is False
    assert len(gateway.context_calls) == 1


def test_message_page_later_user_preserves_abandoned_retry_suppression(
    mock_gateway,
) -> None:
    created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    conversation = Conversation(
        id="20000000-0000-0000-0000-000000000004",
        title="Abandoned reconciliation",
        title_source="system_default",
        language="en",
        created_at=created_at,
        updated_at=created_at,
    )
    abandoned_user = Message(
        id="30000000-0000-0000-0000-000000000020",
        conversation_id=conversation.id,
        role="user",
        content="Test AAPL.",
        created_at=created_at,
        metadata={},
    )
    page_messages = [
        abandoned_user,
        Message(
            id="30000000-0000-0000-0000-000000000021",
            conversation_id=conversation.id,
            role="assistant",
            content="Waiting.",
            created_at=created_at + timedelta(microseconds=1),
            metadata={},
        ),
        Message(
            id="30000000-0000-0000-0000-000000000022",
            conversation_id=conversation.id,
            role="assistant",
            content="Still waiting.",
            created_at=created_at + timedelta(microseconds=2),
            metadata={},
        ),
    ]
    later_user = Message(
        id="30000000-0000-0000-0000-000000000023",
        conversation_id=conversation.id,
        role="user",
        content="Test MSFT instead.",
        created_at=created_at + timedelta(microseconds=3),
        metadata={},
    )
    gateway = _MessagePageContextGateway(
        mock_gateway,
        page_messages=page_messages,
        later_work=[later_user],
    )
    mock_gateway.get_conversation.return_value = conversation
    mock_gateway.list_projectable_chat_turns.return_value = [
        {
            "turn_id": abandoned_user.id,
            "request_id": "abandoned-request",
            "assistant_message_id": None,
            "status": "abandoned",
            "reconciled_outcome": None,
            "failure_code": "turn_abandoned",
            "retryable": True,
        }
    ]

    with patch("argus.api.state.supabase_gateway", gateway):
        response = client.get(
            f"/api/v1/conversations/{conversation.id}/messages?limit=2",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    abandoned = response.json()["items"][0]
    assert abandoned["id"] == abandoned_user.id
    assert abandoned["metadata"]["agent_runtime_turn"]["status"] == "abandoned"
    assert "retry_last_turn" not in abandoned["metadata"]
    assert len(gateway.context_calls) == 1


def test_message_page_transcript_representation_prevents_duplicate_job_projection(
    mock_gateway,
) -> None:
    created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    conversation = Conversation(
        id="20000000-0000-0000-0000-000000000005",
        title="Run action reconciliation",
        title_source="system_default",
        language="en",
        created_at=created_at,
        updated_at=created_at,
    )
    action_message = Message(
        id="30000000-0000-0000-0000-000000000030",
        conversation_id=conversation.id,
        role="user",
        content="Run backtest",
        created_at=created_at,
        metadata={
            "chat_action": {
                "type": "run_backtest",
                "payload": {"confirmation_id": "confirmation-1"},
            }
        },
    )
    page_messages = [
        action_message,
        Message(
            id="30000000-0000-0000-0000-000000000031",
            conversation_id=conversation.id,
            role="assistant",
            content="Waiting.",
            created_at=created_at + timedelta(microseconds=1),
            metadata={},
        ),
        Message(
            id="30000000-0000-0000-0000-000000000032",
            conversation_id=conversation.id,
            role="assistant",
            content="Still waiting.",
            created_at=created_at + timedelta(microseconds=2),
            metadata={},
        ),
    ]
    represented_message = Message(
        id="30000000-0000-0000-0000-000000000033",
        conversation_id=conversation.id,
        role="assistant",
        content="Run queued.",
        created_at=created_at + timedelta(microseconds=3),
        metadata={
            "backtest_job": {
                "id": "job-1",
                "request_message_id": action_message.id,
            }
        },
    )
    gateway = _MessagePageContextGateway(
        mock_gateway,
        page_messages=page_messages,
        later_work=[represented_message],
        represented_request_ids={action_message.id},
    )
    mock_gateway.get_conversation.return_value = conversation
    mock_gateway.list_backtest_job_reservations.return_value = [
        {
            "id": "job-1",
            "idempotency_key": "confirmation-1",
            "conversation_id": conversation.id,
            "request_message_id": action_message.id,
            "status": "queued",
        }
    ]

    with patch("argus.api.state.supabase_gateway", gateway):
        response = client.get(
            f"/api/v1/conversations/{conversation.id}/messages?limit=2",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    action = response.json()["items"][0]
    assert action["id"] == action_message.id
    assert "backtest_job" not in action["metadata"]
    assert len(gateway.context_calls) == 1
