from uuid import uuid4

import httpx
import pytest
from argus.observability.posthog_deletion import PostHogEventDeletion
from argus.observability.product_events import actor_hash_for_user


def test_submission_is_pending_even_when_provider_says_completed():
    calls = []
    request_id, submission = str(uuid4()), str(uuid4())

    def respond(request):
        calls.append(request)
        return httpx.Response(
            201,
            json={
                "id": request_id,
                "submission_id": submission,
                "status": "completed",
                "count": 2,
            },
        )

    adapter = PostHogEventDeletion(
        "https://us.posthog.com", "1", "synthetic", transport=httpx.MockTransport(respond)
    )
    result = adapter.advance(actor_hash_for_user(str(uuid4())), submission, None)
    assert result.outcome == "pending"
    assert result.request_id == request_id
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,outcome",
    [
        ("draft", "pending"),
        ("pending", "pending"),
        ("approved", "pending"),
        ("in_progress", "pending"),
        ("queued", "pending"),
        ("completed", "deleted"),
        ("failed", "operator_needed"),
        ("unknown", "operator_needed"),
    ],
)
def test_only_independent_completed_poll_closes_step(status, outcome):
    request_id, submission = str(uuid4()), str(uuid4())
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": request_id,
                "submission_id": submission,
                "status": status,
                "count": 0,
            },
        )

    adapter = PostHogEventDeletion(
        "https://us.posthog.com", "1", "synthetic", transport=httpx.MockTransport(respond)
    )
    result = adapter.advance(actor_hash_for_user(str(uuid4())), submission, request_id)
    assert result.outcome == outcome
    assert seen[0].method == "GET"
    assert seen[0].url.path.endswith(f"/{request_id}/")


@pytest.mark.parametrize(
    "code,outcome",
    [
        (401, "operator_needed"),
        (403, "operator_needed"),
        (404, "operator_needed"),
        (409, "pending"),
        (429, "failed"),
        (500, "failed"),
        (302, "failed"),
    ],
)
def test_provider_errors_keep_step_open_and_do_not_store_body(code, outcome):
    request_id, submission = str(uuid4()), str(uuid4())
    adapter = PostHogEventDeletion(
        "https://us.posthog.com",
        "1",
        "synthetic",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                code, json={"detail": "secret user@example.test", "persons_found": 0}
            )
        ),
    )
    result = adapter.advance(actor_hash_for_user(str(uuid4())), submission, request_id)
    assert result.outcome == outcome
    evidence = result.evidence(submission)
    assert evidence["http_status"] == code
    assert "secret" not in str(evidence)
    assert "persons_found" not in str(evidence)


@pytest.mark.parametrize(
    "body",
    [
        {"persons_found": 0},
        [],
        {"status": "completed"},
        {"id": "bad", "status": "completed"},
    ],
)
def test_malformed_or_person_delete_response_never_completes(body):
    adapter = PostHogEventDeletion(
        "https://us.posthog.com",
        "1",
        "synthetic",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    result = adapter.advance(actor_hash_for_user(str(uuid4())), str(uuid4()), None)
    assert result.outcome != "deleted"


def test_lost_submission_response_reuses_identical_submission_and_query():
    import json

    payloads = []
    submission, distinct_id = str(uuid4()), actor_hash_for_user(str(uuid4()))

    def respond(request):
        payloads.append(json.loads(request.content))
        raise httpx.ReadTimeout("synthetic", request=request)

    adapter = PostHogEventDeletion(
        "https://us.posthog.com", "1", "synthetic", transport=httpx.MockTransport(respond)
    )
    for _ in range(2):
        assert adapter.advance(distinct_id, submission, None).outcome == "failed"
    assert payloads[0] == payloads[1]
    assert payloads[0]["submission_id"] == submission
    assert (
        payloads[0]["query"]
        == f"SELECT uuid FROM events WHERE distinct_id = '{distinct_id}'"
    )


def test_invalid_distinct_id_has_no_outbound_side_effect():
    calls = []
    adapter = PostHogEventDeletion(
        "https://us.posthog.com",
        "1",
        "synthetic",
        transport=httpx.MockTransport(lambda request: calls.append(request)),
    )
    assert adapter.advance("' OR true", str(uuid4()), None).outcome == "operator_needed"
    assert calls == []


def test_factory_is_disabled_without_flag_even_with_credentials(monkeypatch):
    from argus.observability.analytics_deletion import (
        RecordingAnalyticsDeletion,
        analytics_deletion_from_env,
    )

    monkeypatch.delenv("ARGUS_ANALYTICS_DELETION_ENABLED", raising=False)
    monkeypatch.setenv("ARGUS_POSTHOG_DELETION_API_KEY", "synthetic")
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    assert isinstance(analytics_deletion_from_env(), RecordingAnalyticsDeletion)


def test_a_server_that_sends_no_posthog_events_has_nothing_to_delete(monkeypatch):
    """Decision 1B: with no POSTHOG_PROJECT_TOKEN the server never sent an
    event under the person's distinct id, so the step is not applicable."""
    from argus.observability.analytics_deletion import analytics_deletion_from_env

    monkeypatch.delenv("ARGUS_ANALYTICS_DELETION_ENABLED", raising=False)
    monkeypatch.delenv("POSTHOG_PROJECT_TOKEN", raising=False)
    assert analytics_deletion_from_env().delete_person("anyone") == "not_applicable"


def test_a_server_that_sends_events_without_an_adapter_records_only(monkeypatch):
    from argus.observability.analytics_deletion import analytics_deletion_from_env

    monkeypatch.delenv("ARGUS_ANALYTICS_DELETION_ENABLED", raising=False)
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    assert analytics_deletion_from_env().delete_person("anyone") == "recorded_by_fake"


def test_the_real_adapter_still_runs_when_no_events_are_sent_now(monkeypatch):
    """Events sent before the token was removed are still owed a deletion."""
    from argus.observability.analytics_deletion import analytics_deletion_from_env

    for name, value in {
        "ARGUS_ANALYTICS_DELETION_ENABLED": "true",
        "ARGUS_POSTHOG_DELETION_HOST": "https://us.posthog.com",
        "ARGUS_POSTHOG_DELETION_PROJECT_ID": "1",
        "ARGUS_POSTHOG_DELETION_API_KEY": "synthetic",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("POSTHOG_PROJECT_TOKEN", raising=False)
    assert isinstance(analytics_deletion_from_env(), PostHogEventDeletion)


def test_enabled_factory_requires_dedicated_configuration(monkeypatch):
    from argus.observability.analytics_deletion import analytics_deletion_from_env

    monkeypatch.setenv("ARGUS_ANALYTICS_DELETION_ENABLED", "true")
    for name in ("HOST", "PROJECT_ID", "API_KEY"):
        monkeypatch.delenv(f"ARGUS_POSTHOG_DELETION_{name}", raising=False)
    with pytest.raises(RuntimeError, match="dedicated"):
        analytics_deletion_from_env()


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", str(uuid4())),
        ("submission_id", str(uuid4())),
        ("count", True),
        ("count", -1),
        ("count", "7"),
    ],
)
def test_poll_rejects_mismatched_identity_and_invalid_counts(field, value):
    request_id, submission = str(uuid4()), str(uuid4())
    body = {
        "id": request_id,
        "submission_id": submission,
        "status": "completed",
        "count": 7,
    }
    body[field] = value
    adapter = PostHogEventDeletion(
        "https://us.posthog.com",
        "1",
        "synthetic",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    assert (
        adapter.advance(actor_hash_for_user(str(uuid4())), submission, request_id).outcome
        == "operator_needed"
    )


def test_explicitly_configured_factory_uses_event_adapter(monkeypatch):
    from argus.observability.analytics_deletion import analytics_deletion_from_env

    for name, value in {
        "ARGUS_ANALYTICS_DELETION_ENABLED": "true",
        "ARGUS_POSTHOG_DELETION_HOST": "https://us.posthog.com",
        "ARGUS_POSTHOG_DELETION_PROJECT_ID": "1",
        "ARGUS_POSTHOG_DELETION_API_KEY": "synthetic",
    }.items():
        monkeypatch.setenv(name, value)
    assert isinstance(analytics_deletion_from_env(), PostHogEventDeletion)
