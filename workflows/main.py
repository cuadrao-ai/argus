from __future__ import annotations

import os

from argus.llm.openrouter_key_policy import validate_hosted_openrouter_configuration
from argus.log_sink import configure_logging

configure_logging()

try:
    from render_sdk import Retry, Workflows
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in workflow env
    raise RuntimeError(
        "render_sdk is required to run the Render Workflow service. Install "
        "the Argus runtime and workflows group with: "
        "poetry install --only main,workflows --no-interaction."
    ) from exc

try:
    from workflows.backtest_job import (
        PostgresBacktestJobGateway,
        capacity_probe_should_raise,
    )
    from workflows.backtest_job import (
        run_backtest_job as run_backtest_job_workflow,
    )
    from workflows.proof import PostgresProofJobGateway, run_workflow_proof
except ModuleNotFoundError:  # pragma: no cover - supports `python workflows/main.py`
    from backtest_job import (
        PostgresBacktestJobGateway,
        capacity_probe_should_raise,
    )
    from backtest_job import (
        run_backtest_job as run_backtest_job_workflow,
    )
    from proof import PostgresProofJobGateway, run_workflow_proof


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


validate_hosted_openrouter_configuration()

app = Workflows(
    default_retry=Retry(max_retries=0, wait_duration_ms=1000),
    default_timeout=_positive_int_env("ARGUS_BACKTEST_WORKFLOW_TIMEOUT_SECONDS", 300),
    default_plan=os.getenv("ARGUS_WORKFLOW_PROOF_PLAN", "starter"),
)


@app.task(name="workflow_proof", timeout_seconds=60)
def workflow_proof(job_id: str, nonce: str) -> dict[str, object]:
    return run_workflow_proof(
        PostgresProofJobGateway.from_env(),
        job_id=job_id,
        nonce=nonce,
        workflow_run_id=os.getenv("RENDER_TASK_RUN_ID"),
    )


@app.task(
    name="run_backtest_job",
    timeout_seconds=_positive_int_env("ARGUS_BACKTEST_WORKFLOW_TIMEOUT_SECONDS", 300),
    plan="standard",
    retry=Retry(max_retries=1, wait_duration_ms=1000),
)
def run_backtest_job(job_id: str, nonce: str | None = None) -> dict[str, object]:
    del nonce
    with PostgresBacktestJobGateway.from_env() as gateway:
        result = run_backtest_job_workflow(
            gateway,
            job_id=job_id,
            workflow_run_id=os.getenv("RENDER_TASK_RUN_ID"),
        )
        if capacity_probe_should_raise(result):
            raise RuntimeError("Controlled public-alpha capacity probe failed.")
        return result


if __name__ == "__main__":
    app.start()
