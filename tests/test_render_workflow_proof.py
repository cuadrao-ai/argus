from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


class FakeProofGateway:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = dict(row)
        self.transitions: list[tuple[str, dict[str, object]]] = []

    def fetch_job(self, job_id: str) -> dict[str, object] | None:
        if self.row["id"] != job_id:
            return None
        return dict(self.row)

    def update_job_status(
        self,
        *,
        job_id: str,
        status: str,
        execution_metadata: dict[str, object],
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> dict[str, object]:
        assert self.row["id"] == job_id
        self.transitions.append(
            (
                status,
                {
                    "execution_metadata": execution_metadata,
                    "started_at": started_at,
                    "finished_at": finished_at,
                },
            )
        )
        self.row["status"] = status
        self.row["execution_metadata"] = execution_metadata
        if started_at is not None:
            self.row["started_at"] = started_at
        if finished_at is not None:
            self.row["finished_at"] = finished_at
        return dict(self.row)


def test_workflow_proof_marks_queued_job_running_then_succeeded() -> None:
    from workflows.proof import run_workflow_proof

    job_id = str(uuid4())
    gateway = FakeProofGateway(
        {
            "id": job_id,
            "status": "queued",
            "attempts": 0,
            "launch_payload": {"kind": "render_workflow_proof"},
            "execution_metadata": {"existing": "kept"},
        }
    )

    result = run_workflow_proof(
        gateway,
        job_id=job_id,
        nonce="proof-nonce",
        workflow_run_id="local-run",
    )

    assert result["job_id"] == job_id
    assert result["status"] == "succeeded"
    assert result["nonce"] == "proof-nonce"
    assert result["workflow_run_id"] == "local-run"
    assert [transition[0] for transition in gateway.transitions] == [
        "running",
        "succeeded",
    ]
    metadata = gateway.row["execution_metadata"]
    assert metadata["existing"] == "kept"
    assert metadata["workflow_proof"]["nonce"] == "proof-nonce"
    assert metadata["workflow_proof"]["workflow_run_id"] == "local-run"


def test_workflow_proof_records_effective_runtime_provider_mode() -> None:
    from workflows.proof import run_workflow_proof

    job_id = str(uuid4())
    gateway = FakeProofGateway(
        {
            "id": job_id,
            "status": "queued",
            "attempts": 0,
            "launch_payload": {"kind": "render_workflow_proof"},
            "execution_metadata": {},
        }
    )

    result = run_workflow_proof(
        gateway,
        job_id=job_id,
        nonce="proof-nonce",
        workflow_run_id="local-run",
        runtime_facts={
            "provider_mode": "live_provider",
            "market_data_cache": "false",
        },
    )

    assert result["runtime_facts"] == {
        "provider_mode": "live_provider",
        "market_data_cache": "false",
    }
    metadata = gateway.row["execution_metadata"]["workflow_proof"]
    assert metadata["runtime_facts"] == {
        "provider_mode": "live_provider",
        "market_data_cache": "false",
    }


def test_workflow_proof_verify_requires_completed_current_nonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflows import proof

    job_id = str(uuid4())
    gateway = FakeProofGateway(
        {
            "id": job_id,
            "status": "succeeded",
            "attempts": 1,
            "finished_at": "2026-06-23T16:00:00+00:00",
            "launch_payload": {"kind": "render_workflow_proof"},
            "execution_metadata": {
                "workflow_proof": {
                    "kind": "render_workflow_proof",
                    "nonce": "proof-nonce",
                    "finished_at": "2026-06-23T16:00:00+00:00",
                    "runtime_facts": {"provider_mode": "live_provider"},
                }
            },
        }
    )
    monkeypatch.setattr(proof.PostgresProofJobGateway, "from_env", lambda: gateway)

    assert (
        proof.main(
            [
                "verify",
                "--job-id",
                job_id,
                "--expect-nonce",
                "proof-nonce",
                "--expect-provider-mode",
                "live_provider",
            ]
        )
        == 0
    )


def test_workflow_proof_verify_rejects_unfinished_or_stale_proof_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflows import proof

    job_id = str(uuid4())
    gateway = FakeProofGateway(
        {
            "id": job_id,
            "status": "running",
            "attempts": 1,
            "launch_payload": {"kind": "render_workflow_proof"},
            "execution_metadata": {
                "workflow_proof": {
                    "kind": "render_workflow_proof",
                    "nonce": "old-nonce",
                    "runtime_facts": {"provider_mode": "live_provider"},
                }
            },
        }
    )
    monkeypatch.setattr(proof.PostgresProofJobGateway, "from_env", lambda: gateway)

    with pytest.raises(proof.WorkflowProofError, match="expected succeeded"):
        proof.main(
            [
                "verify",
                "--job-id",
                job_id,
                "--expect-nonce",
                "proof-nonce",
                "--expect-provider-mode",
                "live_provider",
            ]
        )

    gateway.row["status"] = "succeeded"
    gateway.row["finished_at"] = "2026-06-23T16:00:00+00:00"
    gateway.row["execution_metadata"]["workflow_proof"]["finished_at"] = (
        "2026-06-23T16:00:00+00:00"
    )
    with pytest.raises(proof.WorkflowProofError, match="expected nonce"):
        proof.main(
            [
                "verify",
                "--job-id",
                job_id,
                "--expect-nonce",
                "proof-nonce",
                "--expect-provider-mode",
                "live_provider",
            ]
        )


def test_workflow_proof_rejects_non_proof_jobs() -> None:
    from workflows.proof import WorkflowProofError, run_workflow_proof

    job_id = str(uuid4())
    gateway = FakeProofGateway(
        {
            "id": job_id,
            "status": "queued",
            "attempts": 0,
            "launch_payload": {"kind": "real_backtest"},
            "execution_metadata": {},
        }
    )

    with pytest.raises(WorkflowProofError, match="render_workflow_proof"):
        run_workflow_proof(gateway, job_id=job_id, nonce="proof-nonce")


def test_workflow_proof_requires_secret_database_url() -> None:
    from workflows.proof import require_database_url

    with pytest.raises(RuntimeError, match="ARGUS_WORKFLOW_DATABASE_URL"):
        require_database_url({})

    assert require_database_url(
        {"ARGUS_WORKFLOW_DATABASE_URL": "postgres://workflow:secret@example/db"}
    )
    assert require_database_url({"DATABASE_URL": "postgres://legacy:secret@example/db"})
    assert (
        require_database_url(
            {
                "ARGUS_WORKFLOW_DATABASE_URL": "postgres://workflow:secret@example/db",
                "DATABASE_URL": "postgres://legacy:secret@example/db",
            }
        )
        == "postgres://workflow:secret@example/db"
    )


def test_trigger_proof_serializes_generated_sdk_models() -> None:
    from workflows.trigger_proof import _json_safe

    class GeneratedSdkModel:
        def to_dict(self) -> dict[str, object]:
            return {
                "id": "trn-local",
                "status": "completed",
                "attempts": [
                    {
                        "status": "completed",
                        "result": {"job_id": "job-local"},
                    }
                ],
            }

    assert _json_safe(GeneratedSdkModel()) == {
        "id": "trn-local",
        "status": "completed",
        "attempts": [
            {
                "status": "completed",
                "result": {"job_id": "job-local"},
            }
        ],
    }


def test_trigger_proof_prefers_canonical_task_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflows.trigger_proof import _task_id

    monkeypatch.setenv(
        "ARGUS_BACKTEST_WORKFLOW_TASK",
        "argus-backtests/workflow_proof",
    )
    monkeypatch.setenv(
        "ARGUS_RENDER_WORKFLOW_PROOF_TASK",
        "argus-render-workflow-proof/workflow_proof",
    )

    assert _task_id(None) == "argus-backtests/workflow_proof"


def test_trigger_proof_uses_direct_task_run_api(monkeypatch: pytest.MonkeyPatch) -> None:
    from workflows import trigger_proof as proof_trigger

    calls: list[tuple[str, dict[str, object]]] = []

    class FakeDispatcher:
        def __init__(self, *, task_id: str) -> None:
            calls.append(("dispatcher_init", {"task_id": task_id}))

        def dispatch(self, *, job_id: str, nonce: str) -> dict[str, object]:
            calls.append(("dispatch", {"job_id": job_id, "nonce": nonce}))
            return {"id": "trn-direct", "status": "pending"}

    class FakeTaskRunClient:
        def __init__(self) -> None:
            self.calls = 0

        def get_task_run(self, task_run_id: str) -> dict[str, object]:
            self.calls += 1
            calls.append(
                (
                    "get_task_run",
                    {"task_run_id": task_run_id, "call": self.calls},
                )
            )
            if self.calls == 1:
                return {"id": task_run_id, "status": "pending"}
            return {
                "id": task_run_id,
                "status": "completed",
                "results": [{"job_id": "job-1", "status": "succeeded"}],
            }

    monkeypatch.setattr(
        "argus.api.chat.backtest_jobs.RenderWorkflowDispatcher",
        FakeDispatcher,
    )
    monkeypatch.setattr(
        "argus.api.chat.backtest_jobs.RenderTaskRunClient",
        FakeTaskRunClient,
    )
    monkeypatch.setattr(proof_trigger.time, "sleep", lambda _seconds: None)

    result = proof_trigger.trigger_proof(
        task_id="argus-backtests/workflow_proof",
        job_id="job-1",
        nonce="nonce-1",
        timeout_seconds=5,
        poll_seconds=0.1,
    )

    assert result == {
        "id": "trn-direct",
        "status": "completed",
        "results": [{"job_id": "job-1", "status": "succeeded"}],
    }
    assert calls == [
        (
            "dispatcher_init",
            {"task_id": "argus-backtests/workflow_proof"},
        ),
        ("dispatch", {"job_id": "job-1", "nonce": "nonce-1"}),
        ("get_task_run", {"task_run_id": "trn-direct", "call": 1}),
        ("get_task_run", {"task_run_id": "trn-direct", "call": 2}),
    ]


def test_trigger_proof_fails_on_terminal_task_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflows import trigger_proof as proof_trigger

    class FakeDispatcher:
        def __init__(self, *, task_id: str) -> None:
            self.task_id = task_id

        def dispatch(self, *, job_id: str, nonce: str) -> dict[str, object]:
            return {"id": "trn-failed", "status": "pending"}

    class FakeTaskRunClient:
        def get_task_run(self, task_run_id: str) -> dict[str, object]:
            return {"id": task_run_id, "status": "failed"}

    monkeypatch.setattr(
        "argus.api.chat.backtest_jobs.RenderWorkflowDispatcher",
        FakeDispatcher,
    )
    monkeypatch.setattr(
        "argus.api.chat.backtest_jobs.RenderTaskRunClient",
        FakeTaskRunClient,
    )

    with pytest.raises(RuntimeError, match="finished with status failed"):
        proof_trigger.trigger_proof(
            task_id="argus-backtests/workflow_proof",
            job_id="job-1",
            nonce="nonce-1",
            timeout_seconds=5,
            poll_seconds=0.1,
        )


def test_seed_cli_reuses_stable_proof_principal_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from workflows import proof

    class SeedGateway:
        def __init__(self) -> None:
            self.profile: dict[str, str] | None = None
            self.job_args: dict[str, str | None] | None = None

        def ensure_proof_profile(self, *, user_id: str, email: str) -> None:
            self.profile = {"user_id": user_id, "email": email}

        def create_proof_job(
            self,
            *,
            user_id: str,
            nonce: str,
            idempotency_key: str | None = None,
        ) -> dict[str, object]:
            assert self.profile is not None
            assert self.profile["user_id"] == user_id
            self.job_args = {
                "user_id": user_id,
                "nonce": nonce,
                "idempotency_key": idempotency_key,
            }
            return {
                "id": "00000000-0000-4000-8000-000000000002",
                "user_id": user_id,
                "conversation_id": None,
                "operation_scope": proof.PROOF_OPERATION_SCOPE,
                "status": "queued",
            }

    gateway = SeedGateway()
    monkeypatch.setattr(proof.PostgresProofJobGateway, "from_env", lambda: gateway)

    exit_code = proof.main(["seed", "--nonce", "internet-proof"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["user_id"] == proof.DEFAULT_PROOF_USER_ID
    assert output["email"] == f"render-workflow-proof+{output['user_id']}@example.invalid"
    assert output["job_id"] == "00000000-0000-4000-8000-000000000002"
    assert output["operation_scope"] == "workflows.proof"
    assert "conversation_id" not in output
    assert output["nonce"] == "internet-proof"
    assert output["status"] == "queued"
    assert gateway.profile == {"user_id": output["user_id"], "email": output["email"]}
    assert gateway.job_args == {
        "user_id": output["user_id"],
        "nonce": "internet-proof",
        "idempotency_key": None,
    }


def test_seed_cli_respects_explicit_proof_user(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from workflows import proof

    class SeedGateway:
        def ensure_proof_profile(self, *, user_id: str, email: str) -> None:
            self.profile = {"user_id": user_id, "email": email}

        def create_proof_job(
            self,
            *,
            user_id: str,
            nonce: str,
            idempotency_key: str | None = None,
        ) -> dict[str, object]:
            return {
                "id": "00000000-0000-4000-8000-000000000004",
                "user_id": user_id,
                "conversation_id": None,
                "operation_scope": proof.PROOF_OPERATION_SCOPE,
                "status": "queued",
            }

    gateway = SeedGateway()
    monkeypatch.setattr(proof.PostgresProofJobGateway, "from_env", lambda: gateway)

    exit_code = proof.main(
        [
            "seed",
            "--user-id",
            "00000000-0000-4000-8000-000000000003",
            "--nonce",
            "explicit-proof",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["user_id"] == "00000000-0000-4000-8000-000000000003"
    assert output["operation_scope"] == "workflows.proof"
    assert gateway.profile["user_id"] == "00000000-0000-4000-8000-000000000003"


def test_seed_cli_no_longer_accepts_a_conversation() -> None:
    """A proof job has no conversation to sit in, so the seeder cannot be
    handed one; the argument would be the one way back into the projection."""
    from workflows import proof

    with pytest.raises(SystemExit):
        proof.build_parser().parse_args(
            ["seed", "--conversation-id", "00000000-0000-4000-8000-000000000005"]
        )


def test_backtest_jobs_migration_defines_durable_workflow_boundary() -> None:
    migrations = list((ROOT / "supabase" / "migrations_archive").glob("*backtest_jobs*.sql"))
    assert migrations, "missing backtest_jobs migration"

    sql = "\n".join(path.read_text(encoding="utf-8") for path in migrations)

    assert "create table if not exists public.backtest_jobs" in sql
    for column in (
        "id uuid primary key",
        "user_id uuid not null references public.profiles",
        "conversation_id uuid not null references public.conversations",
        "idempotency_key text",
        "payload_hash text not null",
        "launch_payload jsonb not null",
        "status text not null",
        "execution_metadata jsonb not null default '{}'::jsonb",
        "result_run_id uuid references public.backtest_runs",
    ):
        assert column in sql

    for status in ("queued", "running", "succeeded", "failed", "canceled", "expired"):
        assert f"'{status}'" in sql

    for index_name in (
        "idx_backtest_jobs_user_status_queued",
        "idx_backtest_jobs_conversation_created",
        "idx_backtest_jobs_result_run",
        "idx_backtest_jobs_user_idempotency_key",
        "idx_backtest_jobs_user_payload_hash",
    ):
        assert index_name in sql

    assert "alter table public.backtest_jobs enable row level security" in sql
    assert "create policy backtest_jobs_owner_select" in sql
    assert "to authenticated" in sql
    assert "using (user_id = auth.uid())" in sql
    assert "grant select on table public.backtest_jobs to authenticated" in sql
    assert "grant all privileges on table public.backtest_jobs to service_role" in sql


def test_backtest_finalization_migration_defines_transactional_service_role_rpc() -> None:
    migration = (
        ROOT
        / "supabase"
        / "migrations_archive"
        / "20260713000001_finalize_backtest_completion.sql"
    )

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8").lower()
    assert "function public.finalize_backtest_completion" in sql
    assert "insert into public.backtest_runs" in sql
    assert "insert into public.ideas" in sql
    assert "insert into public.idea_versions" in sql
    assert "insert into public.evidence_artifacts" in sql
    assert "for update" in sql
    assert "revoke all on function public.finalize_backtest_completion" in sql
    assert "grant execute on function public.finalize_backtest_completion" in sql
    assert "to service_role" in sql


def test_api_contract_documents_backtest_job_boundary_fields() -> None:
    contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    section_start = contract.index("\n## Backtest Job\n")
    section_end = contract.index("# 5. Metrics Catalog")
    section = contract[section_start:section_end]

    for field in (
        '"user_id": "uuid"',
        '"idempotency_key": "uuid-or-client-key"',
        '"launch_payload":',
        '"priority": "normal"',
        '"attempts": 1',
        '"max_attempts": 1',
        '"queued_at": "timestamp"',
        '"started_at": "timestamp"',
        '"finished_at": null',
    ):
        assert field in section


def test_workflow_dependencies_install_argus_runtime_and_workflow_group() -> None:
    requirements_path = ROOT / "workflows" / "requirements.txt"
    assert not requirements_path.exists()

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    workflow_group = pyproject["tool"]["poetry"]["group"]["workflows"]
    workflow_deps = workflow_group["dependencies"]
    proof_script = (ROOT / ".github" / "workflow-proof.sh").read_text(encoding="utf-8")

    assert workflow_group["optional"] is True
    assert workflow_deps["render-sdk"] == ">=0.7.0,<0.8.0"
    assert workflow_deps["psycopg"] == {
        "version": ">=3.3.4,<4.0.0",
        "extras": ["binary"],
    }
    assert "poetry install --only main,workflows --no-interaction" in proof_script
    assert "--only workflows" not in proof_script
    assert "--no-root" not in proof_script
    assert "poetry run python" in proof_script
    assert "Root Directory: ." in proof_script
    assert "Start Command: poetry run python workflows/main.py" in proof_script
    assert "run_python workflows/proof.py" in proof_script
    assert "run_python workflows/trigger_proof.py" in proof_script
    assert "\n    python workflows/proof.py" not in proof_script
    assert "\n    python workflows/trigger_proof.py" not in proof_script
