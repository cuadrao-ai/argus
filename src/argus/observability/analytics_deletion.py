from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from argus.observability.envelope import posthog_project_token_configured
from argus.observability.posthog_deletion import EventDeletionResult, PostHogEventDeletion

AnalyticsDeletionOutcome = Literal[
    "deleted", "recorded_by_fake", "not_applicable", "failed"
]
FLAG = "ARGUS_ANALYTICS_DELETION_ENABLED"
# Kept in the run record beside not_applicable, so an audit shows why.
NOT_APPLICABLE_REASON = "posthog_not_configured"


@runtime_checkable
class EventAnalyticsDeletion(Protocol):
    def advance(
        self, distinct_id: str, submission_id: str, request_id: str | None
    ) -> EventDeletionResult: ...


class AnalyticsDeletion(Protocol):
    def delete_person(self, distinct_id: str) -> AnalyticsDeletionOutcome:
        """Delete the person and their events by distinct id. Never raises."""
        ...


@dataclass
class RecordingAnalyticsDeletion:
    """The default: records the request, contacts nobody."""

    calls: list[dict] = field(default_factory=list)

    def delete_person(self, distinct_id: str) -> AnalyticsDeletionOutcome:
        # PostHog's bulk delete takes a list of distinct ids.
        self.calls.append({"distinct_ids": [distinct_id], "delete_events": True})
        return "recorded_by_fake"


@dataclass
class NoAnalyticsEvents:
    """This server sends no PostHog events (decision 1B, October 15, 2026),
    so no event under the person's distinct id exists to delete."""

    def delete_person(self, distinct_id: str) -> AnalyticsDeletionOutcome:
        return "not_applicable"


def fake_analytics_allowed() -> bool:
    """Only an explicitly local, dev or test environment may count the fake
    as done. Unset counts as not allowed, so a deploy that forgets to name its
    environment fails safe (the PostHog step stays pending)."""
    for name in ("APP_ENV", "ARGUS_ENV", "ARGUS_APP_ENV", "ENVIRONMENT"):
        value = os.getenv(name, "").strip().lower()
        if value:
            return value in {"local", "development", "dev", "test"}
    return False


def analytics_deletion_from_env() -> AnalyticsDeletion | EventAnalyticsDeletion:
    """The configured deletion adapter wins even with no token today: events
    sent before the token was removed are still owed a deletion."""
    if os.getenv(FLAG, "").strip().lower() in {"1", "true", "yes", "on"}:
        names = (
            "ARGUS_POSTHOG_DELETION_HOST",
            "ARGUS_POSTHOG_DELETION_PROJECT_ID",
            "ARGUS_POSTHOG_DELETION_API_KEY",
        )
        values = [os.getenv(name, "").strip() for name in names]
        if not all(values):
            raise RuntimeError(
                f"{FLAG} requires dedicated PostHog deletion configuration"
            )
        return PostHogEventDeletion(*values)
    if not posthog_project_token_configured():
        return NoAnalyticsEvents()
    return RecordingAnalyticsDeletion()
