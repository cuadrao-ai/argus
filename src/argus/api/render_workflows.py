"""Starts a Render Workflow task run for one job."""

from __future__ import annotations

import os
from typing import Any

import httpx

TRUE_VALUES = {"1", "true", "yes", "on"}
RENDER_TASK_RUNS_URL = "https://api.render.com/v1/task-runs"


def render_local_dev_enabled() -> bool:
    return os.getenv("RENDER_USE_LOCAL_DEV", "").strip().lower() in TRUE_VALUES


def _render_task_runs_endpoint(endpoint: str | None = None) -> str:
    if endpoint:
        return endpoint.rstrip("/")
    if render_local_dev_enabled():
        local_base = os.getenv("RENDER_LOCAL_DEV_URL", "http://localhost:8120").strip()
        return f"{local_base.rstrip('/')}/v1/task-runs"
    return RENDER_TASK_RUNS_URL


class RenderWorkflowDispatcher:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        task_id: str,
        endpoint: str | None = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("RENDER_API_KEY") or "").strip()
        self.task_id = task_id.strip()
        self.endpoint = _render_task_runs_endpoint(endpoint)

    def dispatch(self, *, job_id: str, nonce: str) -> dict[str, Any]:
        if not self.api_key and not render_local_dev_enabled():
            raise RuntimeError("RENDER_API_KEY is required to dispatch backtest jobs.")
        if "/" not in self.task_id:
            raise RuntimeError(
                "ARGUS_BACKTEST_WORKFLOW_TASK must use {workflow-slug}/{task-name}."
            )

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            self.endpoint,
            headers=headers,
            json={"task": self.task_id, "input": [job_id, nonce]},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return dict(data) if isinstance(data, dict) else {"response": data}
