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
    from workflows.proof import PostgresProofJobGateway, run_workflow_proof
except ModuleNotFoundError:  # pragma: no cover - supports `python workflows/main.py`
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


if __name__ == "__main__":
    app.start()
