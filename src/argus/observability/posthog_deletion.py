from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

import httpx

Outcome = Literal["pending", "deleted", "failed", "operator_needed"]
PENDING_STATUSES = {"draft", "pending", "approved", "in_progress", "queued"}


@dataclass(frozen=True)
class EventDeletionResult:
    outcome: Outcome
    request_id: str | None = None
    provider_status: str | None = None
    count: int | None = None
    http_status: int | None = None

    def evidence(self, submission_id: str) -> dict[str, str | int | None]:
        return {
            "submission_id": submission_id,
            "request_id": self.request_id,
            "provider_status": self.provider_status,
            "selected_event_count": self.count,
            "http_status": self.http_status,
            "outcome": self.outcome,
        }


class PostHogEventDeletion:
    def __init__(
        self,
        host: str,
        project_id: str,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = urlparse(host)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
            or not project_id.isdecimal()
            or not api_key.strip()
        ):
            raise ValueError("Invalid PostHog deletion configuration")
        self._url = (
            f"{host.rstrip('/')}/api/projects/{project_id}/data_deletion_requests/"
        )
        self._key = api_key
        self._transport = transport

    def advance(
        self, distinct_id: str, submission_id: str, request_id: str | None
    ) -> EventDeletionResult:
        """Submit once by durable identity, then independently poll completion."""
        try:
            submission_id = str(UUID(submission_id))
            if not re.fullmatch(r"argus_actor_[a-f0-9]{32}", distinct_id):
                return EventDeletionResult("operator_needed")
            if request_id is not None:
                request_id = str(UUID(request_id))
            with httpx.Client(
                transport=self._transport,
                timeout=10,
                follow_redirects=False,
                headers={"Authorization": f"Bearer {self._key}"},
            ) as client:
                if request_id is not None:
                    response = client.get(f"{self._url}{request_id}/")
                else:
                    response = client.post(
                        self._url,
                        json={
                            "submission_id": submission_id,
                            "query": (
                                "SELECT uuid FROM events WHERE distinct_id = "
                                f"'{distinct_id}'"
                            ),
                            "variables": {},
                        },
                    )
            if response.status_code == 409:
                return EventDeletionResult(
                    "pending", request_id, http_status=response.status_code
                )
            if response.status_code in {401, 403, 404}:
                return EventDeletionResult(
                    "operator_needed", request_id, http_status=response.status_code
                )
            if response.status_code not in {200, 201}:
                return EventDeletionResult(
                    "failed", request_id, http_status=response.status_code
                )
            body = response.json()
            returned_id = str(UUID(body["id"]))
            if body["submission_id"] != submission_id or (
                request_id is not None and returned_id != request_id
            ):
                return EventDeletionResult("operator_needed", request_id)
            status = body["status"]
            count = body.get("count")
            if count is not None and (
                not isinstance(count, int) or isinstance(count, bool) or count < 0
            ):
                return EventDeletionResult("operator_needed", returned_id)
            if status == "completed":
                outcome: Outcome = "deleted" if request_id is not None else "pending"
            elif status == "failed":
                outcome = "operator_needed"
            elif status in PENDING_STATUSES:
                outcome = "pending"
            else:
                return EventDeletionResult("operator_needed", returned_id)
            return EventDeletionResult(
                outcome, returned_id, status, count, response.status_code
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            return EventDeletionResult("failed", request_id)
