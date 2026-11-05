from __future__ import annotations

from typing import get_args

import httpx
import pytest
from argus.observability import (
    build_event_envelope,
    capture_event,
    live_analytics_sink_enabled,
    posthog_event_payload,
    sanitize_observability_attributes,
)
from argus.observability.analytics_events import (
    CardSaved,
    LandingViewed,
    SignedIn,
    build_analytics_envelope,
)
from argus.observability.envelope import EventType, FeatureArea
from argus.observability.product_events import actor_hash_for_user


def _analytics_envelope():
    return build_analytics_envelope(
        CardSaved(calculator="time_value"),
        user_id="account-raw-id",
        internal_account=False,
    )


def test_posthog_event_name_is_the_analytics_event_name() -> None:
    payload = posthog_event_payload(_analytics_envelope(), api_key="ph_project_token")

    assert payload["event"] == "card_saved"
    assert payload["distinct_id"] == actor_hash_for_user("account-raw-id")
    assert payload["properties"]["calculator"] == "time_value"
    assert "product_event" not in payload["properties"]
    assert "event_type" not in payload["properties"]


@pytest.mark.parametrize("event_type", get_args(EventType))
def test_an_envelope_outside_the_analytics_registry_never_reaches_posthog(
    monkeypatch,
    event_type: str,
) -> None:
    posts: list[object] = []
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(
        "argus.observability.envelope.httpx.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )
    envelope = build_event_envelope(
        event_type=event_type,  # type: ignore[arg-type]
        event_action="completed",
        feature_area=get_args(FeatureArea)[0],
        actor_hash="actor_hash_1",
        attributes={"product_event": "decision_capture"},
    )

    result = capture_event(envelope)

    assert result.model_dump(mode="python") == {
        "status": "suppressed",
        "reason": "not_an_analytics_event",
        "event_id": envelope.event_id,
        "destination": None,
    }
    assert posts == []
    with pytest.raises(ValueError):
        posthog_event_payload(envelope, api_key="ph_project_token")


def test_analytics_event_is_non_emitting_by_default(monkeypatch) -> None:
    monkeypatch.delenv("POSTHOG_PROJECT_TOKEN", raising=False)
    monkeypatch.delenv("POSTHOG_REGION", raising=False)
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    envelope = _analytics_envelope()

    assert envelope.schema_version == "argus_analytics_event/v1"
    assert envelope.privacy_mode == "metadata_only"
    assert live_analytics_sink_enabled() is False
    assert capture_event(envelope).model_dump(mode="python") == {
        "status": "suppressed",
        "reason": "posthog_not_configured",
        "event_id": envelope.event_id,
        "destination": None,
    }


def test_posthog_capture_requires_explicit_region_or_host(monkeypatch) -> None:
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.delenv("POSTHOG_REGION", raising=False)
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    envelope = _analytics_envelope()

    assert live_analytics_sink_enabled() is False
    assert capture_event(envelope).model_dump(mode="python") == {
        "status": "suppressed",
        "reason": "posthog_region_not_configured",
        "event_id": envelope.event_id,
        "destination": None,
    }


def test_posthog_capture_is_a_personless_server_event(monkeypatch) -> None:
    sent: list[tuple[str, dict[str, object], float]] = []

    def fake_post(url: str, *, json: dict[str, object], timeout: float) -> httpx.Response:
        sent.append((url, json, timeout))
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "US Cloud")
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    monkeypatch.setenv("APP_ENV", "private-alpha")
    monkeypatch.setattr("argus.observability.envelope.httpx.post", fake_post)
    envelope = build_analytics_envelope(
        LandingViewed(language="es-419", cohort="piloto-7kq2"),
        user_id="guest-raw-id",
        internal_account=False,
    )

    result = capture_event(envelope)

    assert result.model_dump(mode="python") == {
        "status": "captured",
        "reason": None,
        "event_id": envelope.event_id,
        "destination": "posthog",
    }
    url, body, timeout = sent[0]
    assert url == "https://us.i.posthog.com/i/v0/e/"
    assert timeout == 0.75
    assert body["api_key"] == "ph_project_token"
    assert body["event"] == "landing_viewed"
    assert body["distinct_id"] == actor_hash_for_user("guest-raw-id")
    assert body["properties"] == {
        "$process_person_profile": False,
        "schema_version": "argus_analytics_event/v1",
        "event_id": envelope.event_id,
        "environment": "private-alpha",
        "internal_account": False,
        "language": "es-419",
        "cohort": "piloto-7kq2",
    }
    assert "guest-raw-id" not in str(body)


def test_an_analytics_envelope_without_an_internal_flag_is_not_sent() -> None:
    """The registry always states ``internal_account``; an envelope that does not
    was not built by it."""
    envelope = _analytics_envelope().model_copy(update={"internal_account": None})

    assert capture_event(envelope).reason == "not_an_analytics_event"
    with pytest.raises(ValueError):
        posthog_event_payload(envelope, api_key="ph_project_token")


def test_signed_in_payload_carries_the_guest_hash_not_the_guest_id() -> None:
    envelope = build_analytics_envelope(
        SignedIn(signup="new", trigger="save"),
        user_id="account-raw-id",
        guest_user_id="guest-raw-id",
        internal_account=False,
    )

    payload = posthog_event_payload(envelope, api_key="ph_project_token")

    assert payload["properties"]["guest_id_hash"] == actor_hash_for_user(
        "guest-raw-id"
    )
    assert "guest-raw-id" not in str(payload)
    assert "account-raw-id" not in str(payload)


def test_observability_sanitizer_blocks_sensitive_and_raw_payloads() -> None:
    sanitized = sanitize_observability_attributes(
        {
            "decision_state": "watching",
            "raw_prompt": "buy my whole account",
            "context_packets": [{"provider": "internal"}],
            "provider_metadata": {"model": "internal"},
            "account_balance": "$100,000",
            "nested": {
                "transcript": "full audio transcript",
                "safe_count": 2,
            },
            "items": [
                {"api_key": "secret", "safe": "yes"},
                "keep short text",
            ],
        }
    )

    assert sanitized == {
        "decision_state": "watching",
        "nested": {"safe_count": 2},
        "items": [{"safe": "yes"}, "keep short text"],
    }
