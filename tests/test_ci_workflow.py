from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import yaml
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
SMOKE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "private-alpha-smoke.yml"
AGENT_RUNTIME_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "agent-runtime-regression.yml"
)
DOCS_ONLY_SCRIPT = ROOT / ".github" / "docs-only-changes.sh"
DOCS_READING_TESTS_SCRIPT = ROOT / ".github" / "docs-reading-tests.sh"
RUNBOOK_PATH = ROOT / "docs" / "PRIVATE_LAUNCH_RUNBOOK.md"
FAKE = Faker()

_HEAVY_CI_JOBS = ("backend-shards", "frontend-checks")
MARKETING_RUNBOOK_PATH = ROOT / "docs" / "runbooks" / "cuadrao-marketing-launch.md"
# A push or a ready pull request runs the full CI; the scheduled and manual
# probe runs only the latest-CLI real-Postgres leg.
_DRAFT_OR_PUSH = (
    "github.event_name == 'push' || (github.event_name == 'pull_request' && "
    "github.event.pull_request.draft == false)"
)
_LATEST_CLI_PROBE = (
    "github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'"
)
# A manual run with full_run checked runs every job, as an integration push does.
_FULL_RUN = "(github.event_name == 'workflow_dispatch' && inputs.full_run)"
_DRAFT_OR_NON_PR = (
    "github.event.pull_request.draft == false || " "github.event_name != 'pull_request'"
)


def _job_needs(job: dict) -> list[str]:
    needs = job.get("needs")
    if needs is None:
        return []
    if isinstance(needs, str):
        return [needs]
    return list(needs)


def _classify_changed_files(*files: str) -> dict[str, str]:
    result = subprocess.run(
        ["bash", str(DOCS_ONLY_SCRIPT), "--files", *files],
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        key: value
        for line in result.stdout.splitlines()
        if "=" in line
        for key, value in (line.split("=", 1),)
        if key in {"docs_only", "run_heavy", "run_marketing"}
    }


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _smoke_workflow() -> dict:
    return yaml.safe_load(SMOKE_WORKFLOW_PATH.read_text(encoding="utf-8"))


def _agent_runtime_workflow() -> dict:
    return yaml.safe_load(AGENT_RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_ci_runs_on_main_codex_and_jules_without_deploying() -> None:
    workflow = _workflow()

    assert not (ROOT / ".github" / "workflows" / "deploy.yml").exists()
    assert workflow["name"] == "CI"
    assert workflow["on"]["push"]["branches"] == [
        "main",
        "codex/private-alpha-next",
        "codex/private-alpha-next-jules-intake",
    ]
    assert workflow["on"]["pull_request"]["branches"] == [
        "main",
        "codex/private-alpha-next",
        "codex/private-alpha-next-jules-intake",
    ]
    assert "deploy" not in workflow["jobs"]


def test_ci_queues_integration_branch_runs_without_canceling_evidence() -> None:
    concurrency = _workflow()["concurrency"]

    # The event name keeps a scheduled probe on main from canceling a push run.
    assert concurrency["group"] == (
        "${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}"
    )
    assert concurrency["cancel-in-progress"] == (
        "${{ github.ref != 'refs/heads/codex/private-alpha-next' && "
        "github.ref != 'refs/heads/codex/private-alpha-next-jules-intake' }}"
    )


def test_ci_has_active_backend_and_frontend_quality_jobs() -> None:
    jobs = _workflow()["jobs"]

    assert {
        "docs-change-gate",
        "ownership-gate",
        "docs-checks",
        "backend-checks",
        "frontend-checks",
        "ci",
    } <= set(jobs)
    assert "mock-demo phase" not in WORKFLOW_PATH.read_text(encoding="utf-8")

    backend_steps = "\n".join(
        str(step.get("run", "")) for step in jobs["backend-shards"]["steps"]
    )
    assert "poetry run ruff check src tests workflows scripts" in backend_steps
    assert "poetry run pytest tests -q --no-cov" in backend_steps


def test_backend_checks_gates_the_suite_by_directory() -> None:
    """New test files must be gated without editing this workflow.

    A curated file list drops new tests silently, so the backend suite step
    runs `tests` as a directory and must never enumerate individual files.
    """
    workflow = _workflow()
    jobs = workflow["jobs"]
    backend_steps = "\n".join(
        str(step.get("run", "")) for step in jobs["backend-shards"]["steps"]
    )

    assert re.search(r"pytest\s+tests\s", backend_steps)
    assert "tests/test_" not in backend_steps
    assert "tests/agent_runtime/" not in backend_steps
    assert "tests/section3/" not in backend_steps

    frontend_steps = "\n".join(
        str(step.get("run", "")) for step in jobs["frontend-checks"]["steps"]
    )
    setup_bun_step = next(
        step
        for step in jobs["frontend-checks"]["steps"]
        if step.get("uses")
        == "oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6"
    )
    assert workflow["env"]["ARGUS_CI_BUN_VERSION"] == "1.3.14"
    assert setup_bun_step["with"]["bun-version"] == "${{ env.ARGUS_CI_BUN_VERSION }}"
    assert "bun test" in frontend_steps
    assert "bun run build" in frontend_steps


def test_ci_runs_guest_release_gates_with_disposable_local_supabase() -> None:
    jobs = _workflow()["jobs"]
    guest_job = jobs["database-shards"]
    joined_steps = "\n".join(str(step.get("run", "")) for step in guest_job["steps"])
    uses_steps = {
        str(step.get("uses", "")): step for step in guest_job["steps"] if step.get("uses")
    }

    assert "supabase/setup-cli@1dedf2c611547ede7232d26866dd3c56ab903bbb" in uses_steps
    assert _workflow()["env"]["ARGUS_CI_SUPABASE_CLI_VERSION"] == "2.109.0"
    assert uses_steps["supabase/setup-cli@1dedf2c611547ede7232d26866dd3c56ab903bbb"][
        "with"
    ]["version"] == (
        "${{ matrix.supabase-cli == 'latest' && 'latest' || "
        "env.ARGUS_CI_SUPABASE_CLI_VERSION }}"
    )
    assert "supabase --version" in joined_steps
    assert "--format '{{.Names}} {{.Image}}'" in joined_steps
    # `supabase start` applies every migration and the seed; a reset after it
    # replays them for no new coverage.
    assert (
        "supabase start -x studio,postgres-meta,realtime,imgproxy,edge-runtime,mailpit"
        in joined_steps
    )
    assert "supabase db reset" not in joined_steps
    assert "ARGUS_DISPOSABLE_DATABASE_URL" in joined_steps
    assert "ARGUS_LOCAL_SUPABASE_URL" in joined_steps
    assert "ARGUS_LOCAL_SUPABASE_ANON_KEY" in joined_steps
    assert "ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY" in joined_steps
    # The provider-free guest tests run in backend-checks' directory-level
    # `pytest tests`; repeating them here bought no extra coverage.
    assert "tests/evals/test_chat_runtime_trajectory_harness.py" not in joined_steps
    # Glob, not a hand-list: a new _postgres proof must be gated without
    # editing the workflow. The hand-list was how uncovered tables shipped.
    assert "tests/test_*_postgres.py" in joined_steps
    assert "tests/test_guest_auth_local_supabase.py" in joined_steps
    assert "scripts/qa/assert_pytest_gate.py" in joined_steps
    assert guest_job["env"]["OPENROUTER_API_KEY"] == ""
    assert guest_job["env"]["ALPACA_API_KEY"] == ""
    assert guest_job["env"]["ALPACA_SECRET_KEY"] == ""
    assert guest_job["env"]["ARGUS_MARKET_DATA_PROVIDER_MODE"] == "synthetic_unit_fixture"
    assert "live_provider" not in joined_steps


_PILOT_POSTGRES_GLOBS = (
    "tests/test_business*_postgres.py",
    "tests/test_whatsapp*_postgres.py",
    "tests/test_ingestion*_postgres.py",
    "tests/test_fiscal*_postgres.py",
    "tests/test_registros*_postgres.py",
    "tests/test_document*_postgres.py",
    "tests/test_rls*_postgres.py",
    "tests/test_access*_postgres.py",
    "tests/test_client_grants_postgres.py",
    "tests/test_account_deletion_fk_census_postgres.py",
    "tests/test_email_daily_budget_postgres.py",
    "tests/test_dgii_rnc_postgres.py",
    "tests/test_supplier_fast_path_postgres.py",
    "tests/test_flags_off_removal_postgres.py",
    "tests/test_login_failure_parity_postgres.py",
)


def _test_files(args: list[str]) -> list[str]:
    return [arg for arg in args if arg.startswith("tests/")]


def _run_postgres_matrix_step(
    tmp_path: Path, cwd: Path, event: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the matrix step's Bash with a poetry that records its arguments."""
    step = next(
        step
        for step in _workflow()["jobs"]["database-shards"]["steps"]
        if step.get("name") == "Run required real-PostgreSQL matrix"
    )
    scratch = Path(tempfile.mkdtemp(dir=tmp_path))
    log = scratch / "poetry-args.log"
    poetry = scratch / "poetry"
    poetry.write_text(
        f'#!/bin/bash\nprintf \'%s\\n\' "$@" >> "{log}"\n', encoding="utf-8"
    )
    poetry.chmod(0o755)
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", step["run"]],
        cwd=cwd,
        env={
            **os.environ,
            "PATH": f"{scratch}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_EVENT_NAME": event,
            "CI_SHARD_INDEX": "0",
            "CI_SHARD_COUNT": _workflow()["jobs"]["database-shards"]["env"][
                "CI_SHARD_COUNT"
            ],
        },
        capture_output=True,
        text=True,
    )
    args = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, args


def test_pull_requests_run_the_pilot_postgres_set_and_other_events_run_every_proof(
    tmp_path: Path,
) -> None:
    pilot = sorted(
        {
            str(path.relative_to(ROOT))
            for glob in _PILOT_POSTGRES_GLOBS
            for path in ROOT.glob(glob)
        }
    )
    everything = sorted(
        str(path.relative_to(ROOT)) for path in ROOT.glob("tests/test_*_postgres.py")
    )
    assert "tests/test_business_postgres.py" in pilot
    assert "tests/test_client_grants_postgres.py" in pilot
    assert "tests/test_account_deletion_fk_census_postgres.py" in pilot
    assert "tests/test_login_failure_parity_postgres.py" in pilot
    assert set(pilot) < set(everything)

    result, files = _run_postgres_matrix_step(tmp_path, ROOT, "pull_request")
    assert result.returncode == 0, result.stderr
    assert sorted(_test_files(files)) == pilot
    assert files[-2:] == [
        "scripts/qa/assert_pytest_gate.py",
        "temp/guest-postgres-junit.xml",
    ]

    for event in ("push", "schedule", "workflow_dispatch"):
        result, files = _run_postgres_matrix_step(tmp_path, ROOT, event)
        assert result.returncode == 0, result.stderr
        assert sorted(_test_files(files)) == everything, event


def test_database_inventory_artifact_retains_only_json_inventories() -> None:
    steps = _workflow()["jobs"]["database-shards"]["steps"]
    retain = next(
        step
        for step in steps
        if step.get("name") == "Retain database test inventory and timings"
    )
    assert retain["uses"].startswith("actions/upload-artifact@")
    assert retain["with"]["path"] == "temp/ci-inventory/*.json"


def _minimal_shard_inventory(full_nodeids: list[str], shard_index: int = 0) -> dict:
    nodeid = full_nodeids[shard_index]
    return {
        "schema_version": 2,
        "shard_index": shard_index,
        "shard_count": len(full_nodeids),
        "full_nodeids": full_nodeids,
        "nodeids": [nodeid],
        "exitstatus": 0,
        "collection_errors": 0,
        "deselected": [],
        "reports": [
            {
                "nodeid": nodeid,
                "phase": phase,
                "outcome": "passed",
                "duration_seconds": 0.01,
            }
            for phase in ("setup", "call", "teardown")
        ],
    }


def _materialize_database_inventory_artifact(repo: Path, *, download_dir: str) -> None:
    nodeids = [f"tests/shard{i}_postgres.py::test_ok" for i in range(3)]
    members = {
        **{f"postgres-{i}.json": _minimal_shard_inventory(nodeids, i) for i in range(3)},
        "auth.json": _minimal_shard_inventory(
            ["tests/test_guest_auth_local_supabase.py::test_ok"]
        ),
    }
    for rel, payload in members.items():
        target = repo / download_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload), encoding="utf-8")


def test_database_inventory_download_layout_restores_union_glob_inputs(
    tmp_path: Path,
) -> None:
    steps = {
        step["name"]: step
        for step in _workflow()["jobs"]["database-checks"]["steps"]
        if step.get("name")
    }
    download_path = steps["Download database inventories"]["with"]["path"]
    assert download_path == "temp/ci-inventory"
    for layout, succeeds in (("temp", False), (download_path, True)):
        repo = tmp_path / str(succeeds)
        _materialize_database_inventory_artifact(repo, download_dir=layout)
        (repo / "scripts").symlink_to(ROOT / "scripts", target_is_directory=True)
        for name in ("Prove database test union", "Prove anonymous Auth test union"):
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", steps[name]["run"]],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            assert (result.returncode == 0) == succeeds, result.stderr
            if not succeeds:
                assert "No such file or directory" in result.stderr
        if succeeds:
            for kind in ("postgres", "auth"):
                assert (repo / f"temp/ci-proof/{kind}.json").is_file()


def test_a_pilot_postgres_glob_that_matches_no_file_fails_the_step(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    for glob in _PILOT_POSTGRES_GLOBS:
        if "whatsapp" not in glob:
            (repo / glob.replace("*", "")).touch()

    missing, _ = _run_postgres_matrix_step(tmp_path, repo, "pull_request")
    assert missing.returncode != 0
    assert "tests/test_whatsapp*_postgres.py" in missing.stderr

    # A file named without a trailing word still matches its prefix glob.
    (repo / "tests/test_whatsapp_postgres.py").touch()
    found, files = _run_postgres_matrix_step(tmp_path, repo, "pull_request")
    assert found.returncode == 0, found.stderr
    assert "tests/test_whatsapp_postgres.py" in _test_files(files)

    # A literal pilot file that has gone missing fails too.
    (repo / "tests/test_client_grants_postgres.py").unlink()
    gone, _ = _run_postgres_matrix_step(tmp_path, repo, "pull_request")
    assert gone.returncode != 0
    assert "tests/test_client_grants_postgres.py" in gone.stderr


def test_marketing_checks_prove_the_runtime_and_tooling_render_will_use() -> None:
    """CI and the Render service must agree on Node and Bun.

    The runbook owns the Render settings; CI derives its pins from the same
    values instead of keeping a second copy that can drift.
    """
    workflow = _workflow()
    job = workflow["jobs"]["marketing-checks"]
    steps = job["steps"]
    runs = "\n".join(str(step.get("run", "")) for step in steps)
    runbook = MARKETING_RUNBOOK_PATH.read_text(encoding="utf-8")

    node_pin = re.search(r"\| `NODE_VERSION` \| `([0-9.]+)` \|", runbook)
    assert node_pin, "the runbook must state the Render NODE_VERSION"
    setup_node = next(
        step
        for step in steps
        if step.get("uses")
        == "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020"
    )
    assert setup_node["with"]["node-version"] == node_pin.group(1)

    bun_pin = re.search(r"npm install -g bun@([0-9.]+)", runbook)
    assert bun_pin, "the runbook build command must pin Bun"
    assert bun_pin.group(1) == workflow["env"]["ARGUS_CI_BUN_VERSION"]
    setup_bun = next(
        step
        for step in steps
        if step.get("uses")
        == "oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6"
    )
    assert setup_bun["with"]["bun-version"] == "${{ env.ARGUS_CI_BUN_VERSION }}"

    # Each gate runs inside the independent package, in the order a deploy needs.
    ordered = [
        "cd marketing && bun install --frozen-lockfile",
        "cd marketing && bun run lint",
        "cd marketing && bun run typecheck",
        "cd marketing && bun test",
        "cd marketing && bun run build",
        "cd marketing && bun run test:e2e",
    ]
    positions = [runs.index(command) for command in ordered]
    assert positions == sorted(positions)
    assert "cd web" not in runs

    # The Render start command must be a script the package really defines.
    scripts = json.loads((ROOT / "marketing" / "package.json").read_text())["scripts"]
    start = re.search(r"\| Start command \| `npm run (\w+)", runbook)
    assert start and start.group(1) in scripts


def test_ci_aggregator_requires_all_active_quality_jobs() -> None:
    jobs = _workflow()["jobs"]

    assert jobs["ci"]["needs"] == [
        "docs-change-gate",
        "ownership-gate",
        "docs-checks",
        "backend-checks",
        "frontend-checks",
        "marketing-checks",
        "database-checks",
    ]
    assert jobs["ci"]["if"] == f"always() && ({_DRAFT_OR_PUSH} || {_FULL_RUN})"
    aggregator_env = jobs["ci"]["steps"][0]["env"]
    assert aggregator_env["DOCS_CHANGE_GATE"] == ("${{ needs.docs-change-gate.result }}")
    assert aggregator_env["OWNERSHIP_GATE"] == "${{ needs.ownership-gate.result }}"
    assert aggregator_env["DOCS_ONLY"] == (
        "${{ needs.docs-change-gate.outputs.docs_only }}"
    )
    assert aggregator_env["RUN_HEAVY"] == (
        "${{ needs.docs-change-gate.outputs.run_heavy }}"
    )
    assert aggregator_env["RUN_MARKETING"] == (
        "${{ needs.docs-change-gate.outputs.run_marketing }}"
    )
    assert aggregator_env["DOCS_CHECKS"] == "${{ needs.docs-checks.result }}"
    assert aggregator_env["BACKEND_CHECKS"] == "${{ needs.backend-checks.result }}"
    assert aggregator_env["FRONTEND_CHECKS"] == "${{ needs.frontend-checks.result }}"
    assert aggregator_env["MARKETING_CHECKS"] == ("${{ needs.marketing-checks.result }}")
    assert aggregator_env["DATABASE_CHECKS"] == ("${{ needs.database-checks.result }}")
    aggregator_run = jobs["ci"]["steps"][0]["run"]
    assert "CI checks passed." in aggregator_run
    assert "require_success docs-change-gate" in aggregator_run
    assert "require_success ownership-gate" in aggregator_run
    # A selected job must succeed; skipping is allowed only when unselected.
    assert "require_success_or_skipped" not in aggregator_run
    assert 'require_selected docs-checks "$DOCS_ONLY"' in aggregator_run
    assert 'require_success backend-checks "$BACKEND_CHECKS"' in aggregator_run
    assert 'require_success frontend-checks "$FRONTEND_CHECKS"' in aggregator_run
    assert 'require_success marketing-checks "$MARKETING_CHECKS"' in aggregator_run
    assert 'require_success database-checks "$DATABASE_CHECKS"' in aggregator_run


def test_private_alpha_smoke_workflow_runs_local_predeploy_gate() -> None:
    workflow = _smoke_workflow()

    assert workflow["name"] == "Local boot smoke"
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["on"]["push"]["branches"] == ["codex/private-alpha-next"]
    assert workflow["on"]["pull_request"]["branches"] == [
        "codex/private-alpha-next",
        "codex/private-alpha-next-jules-intake",
    ]
    assert "deploy" not in workflow["jobs"]

    job = workflow["jobs"]["local-smoke"]
    assert job["timeout-minutes"] == 10
    assert _job_needs(job) == ["docs-change-gate"]
    assert job["if"] == _DRAFT_OR_NON_PR
    assert "needs.docs-change-gate.outputs.run_heavy == 'true'" in "\n".join(
        step.get("if") or "" for step in job["steps"]
    )
    joined_steps = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "poetry install --with dev,workflows --no-interaction" in joined_steps
    assert "cd web && bun install --frozen-lockfile" in joined_steps
    assert '.github/local-smoke.sh --expected-sha "$GITHUB_SHA"' in joined_steps
    assert "RENDER_API_KEY" not in SMOKE_WORKFLOW_PATH.read_text(encoding="utf-8")


def test_agent_runtime_regression_workflow_runs_full_runtime_sweep() -> None:
    workflow = _agent_runtime_workflow()

    assert workflow["name"] == "Agent Runtime Regression"
    assert set(workflow["on"]) == {
        "workflow_dispatch",
        "schedule",
        "push",
        "pull_request",
    }
    assert workflow["on"]["schedule"] == [{"cron": "15 9 * * *"}]
    assert workflow["on"]["push"]["branches"] == ["codex/private-alpha-next"]
    assert workflow["on"]["pull_request"]["branches"] == ["codex/private-alpha-next"]
    assert "src/argus/agent_runtime/**" in workflow["on"]["pull_request"]["paths"]
    assert "tests/agent_runtime/**" in workflow["on"]["pull_request"]["paths"]
    assert "tests/test_spine_guardrails.py" in workflow["on"]["pull_request"]["paths"]
    assert workflow["permissions"] == {"contents": "read"}
    assert "deploy" not in workflow["jobs"]

    job = workflow["jobs"]["agent-runtime"]
    assert job["timeout-minutes"] == 25
    assert job["if"] == (
        "github.event.pull_request.draft == false || "
        "github.event_name != 'pull_request'"
    )
    setup_python_step = next(
        step
        for step in job["steps"]
        if step.get("uses")
        == "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
    )
    assert setup_python_step["with"]["python-version"] == "3.10"
    checkout_steps = [
        step
        for step in job["steps"]
        if step.get("uses") == "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
    ]
    assert checkout_steps == [
        {
            "name": "Checkout workflow ref",
            "if": "github.event_name != 'schedule'",
            "uses": "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        },
        {
            "name": "Checkout private-alpha-next for nightly schedule",
            "if": "github.event_name == 'schedule'",
            "uses": "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "with": {"ref": "codex/private-alpha-next"},
        },
    ]

    joined_steps = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "poetry install --with dev --no-interaction" in joined_steps
    assert (
        "poetry run pytest tests/agent_runtime tests/test_spine_guardrails.py -q --no-cov"
        in joined_steps
    )
    sweep_step = next(
        step
        for step in job["steps"]
        if step.get("name") == "Run agent_runtime regression sweep"
    )
    assert sweep_step["env"] == {
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture"
    }

    runtime_target = ROOT / "tests" / "agent_runtime"
    hidden_regression_file = (
        ROOT / "tests" / "agent_runtime" / "test_conversational_contract_hardening.py"
    )
    assert hidden_regression_file.exists()
    assert hidden_regression_file.is_relative_to(runtime_target)
    assert str(hidden_regression_file.relative_to(ROOT)) not in joined_steps
    assert "docs-change-gate" not in workflow["jobs"]
    assert "paths-ignore" not in AGENT_RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8")


def test_docs_only_changes_script_classifies_docs_and_code_lists() -> None:
    docs_path = f"docs/{FAKE.word()}/{FAKE.file_name(extension='md')}"
    nested_docs = f"docs/specs/{FAKE.file_name(extension='md')}"
    code_path = f"src/argus/{FAKE.file_name(extension='py')}"
    root_markdown = FAKE.file_name(extension="md")

    assert _classify_changed_files(docs_path, nested_docs) == {
        "docs_only": "true",
        "run_heavy": "false",
        "run_marketing": "false",
    }
    assert _classify_changed_files(code_path) == {
        "docs_only": "false",
        "run_heavy": "true",
        "run_marketing": "false",
    }
    assert _classify_changed_files(docs_path, code_path) == {
        "docs_only": "false",
        "run_heavy": "true",
        "run_marketing": "false",
    }
    assert _classify_changed_files("AGENTS.md") == {
        "docs_only": "false",
        "run_heavy": "true",
        "run_marketing": "false",
    }
    assert _classify_changed_files(root_markdown) == {
        "docs_only": "false",
        "run_heavy": "true",
        "run_marketing": "false",
    }
    assert _classify_changed_files() == {
        "docs_only": "false",
        "run_heavy": "true",
        "run_marketing": "true",
    }


def test_openapi_runs_every_job_and_other_docs_api_files_stay_docs_only() -> None:
    api_path = f"docs/api/{FAKE.file_name(extension='yaml')}"

    assert _classify_changed_files("docs/api/openapi.yaml") == {
        "docs_only": "false",
        "run_heavy": "true",
        "run_marketing": "true",
    }
    assert _classify_changed_files(api_path) == {
        "docs_only": "true",
        "run_heavy": "false",
        "run_marketing": "false",
    }
    assert _classify_changed_files("docs/PRODUCT.md", "docs/api/openapi.yaml") == {
        "docs_only": "false",
        "run_heavy": "true",
        "run_marketing": "true",
    }


def test_docs_only_changes_script_counts_rename_from_code_into_docs(
    tmp_path: Path,
) -> None:
    assert "--no-renames" in DOCS_ONLY_SCRIPT.read_text(encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "ci@example.test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CI"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    source_name = FAKE.file_name(extension="py")
    dest_name = FAKE.file_name(extension="md")
    (repo / "src").mkdir()
    (repo / "src" / source_name).write_text("print(1)\n", encoding="utf-8")
    subprocess.run(["git", "add", f"src/{source_name}"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add code"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "docs").mkdir()
    subprocess.run(
        ["git", "mv", f"src/{source_name}", f"docs/{dest_name}"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "rename into docs"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    result = subprocess.run(
        ["bash", str(DOCS_ONLY_SCRIPT), "--from-git", "HEAD~1"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = {
        key: value
        for line in result.stdout.splitlines()
        if "=" in line
        for key, value in (line.split("=", 1),)
        if key in {"docs_only", "run_heavy"}
    }
    assert f"src/{source_name}" in result.stdout
    assert parsed == {"docs_only": "false", "run_heavy": "true"}

    docs_source = FAKE.file_name(extension="md")
    docs_dest = FAKE.file_name(extension="md")
    (repo / "docs" / docs_source).write_text("note\n", encoding="utf-8")
    subprocess.run(["git", "add", f"docs/{docs_source}"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add docs"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "mv", f"docs/{docs_source}", f"docs/{docs_dest}"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "rename inside docs"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs_rename = subprocess.run(
        ["bash", str(DOCS_ONLY_SCRIPT), "--from-git", "HEAD~1"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    docs_parsed = {
        key: value
        for line in docs_rename.stdout.splitlines()
        if "=" in line
        for key, value in (line.split("=", 1),)
        if key in {"docs_only", "run_heavy"}
    }
    assert f"docs/{docs_source}" in docs_rename.stdout
    assert f"docs/{docs_dest}" in docs_rename.stdout
    assert docs_parsed == {"docs_only": "true", "run_heavy": "false"}


def test_docs_only_changes_script_runs_heavy_jobs_off_pull_request() -> None:
    result = subprocess.run(
        ["bash", str(DOCS_ONLY_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "GITHUB_EVENT_NAME": "push"},
    )
    parsed = {
        key: value
        for line in result.stdout.splitlines()
        if "=" in line
        for key, value in (line.split("=", 1),)
        if key in {"docs_only", "run_heavy"}
    }
    assert parsed == {"docs_only": "false", "run_heavy": "true"}


def test_pull_request_heavy_jobs_use_the_shared_docs_change_gate() -> None:
    jobs = _workflow()["jobs"]
    gate = jobs["docs-change-gate"]
    classify = next(step for step in gate["steps"] if step.get("id") == "classify")

    assert gate["if"] == f"{_DRAFT_OR_PUSH} || {_LATEST_CLI_PROBE}"
    assert gate["outputs"]["run_heavy"] == "${{ steps.classify.outputs.run_heavy }}"
    assert gate["outputs"]["run_marketing"] == (
        "${{ steps.classify.outputs.run_marketing }}"
    )
    assert gate["outputs"]["run_backend"] == "${{ steps.classify.outputs.run_backend }}"
    assert gate["outputs"]["run_frontend"] == "${{ steps.classify.outputs.run_frontend }}"
    assert gate["outputs"]["run_database"] == "${{ steps.classify.outputs.run_database }}"
    assert classify["run"] == ".github/docs-only-changes.sh"
    assert classify["env"]["PR_BASE_SHA"] == ("${{ github.event.pull_request.base.sha }}")
    assert _job_needs(jobs["ownership-gate"]) == []
    assert jobs["ownership-gate"]["if"] == f"{_DRAFT_OR_PUSH} || {_FULL_RUN}"
    ownership_steps = jobs["ownership-gate"]["steps"]
    checkout = next(step for step in ownership_steps if step.get("name") == "Checkout")
    assert checkout["with"]["fetch-depth"] == 0
    fetch_base = next(
        step
        for step in ownership_steps
        if step.get("name") == "Fetch the pull request base"
    )
    assert fetch_base["if"] == "github.event_name == 'pull_request'"
    assert 'git fetch --no-tags origin "${{ github.base_ref }}"' in fetch_base["run"]
    assert 'git cat-file -e "${PR_BASE_SHA}^{commit}"' in fetch_base["run"]
    evidence_step = next(
        step
        for step in ownership_steps
        if step.get("name") == "Reject new evidence media"
    )
    assert evidence_step["run"] == "python scripts/ci/check_no_evidence_media.py"
    assert evidence_step["env"]["PR_BASE_SHA"] == (
        "${{ github.event.pull_request.base.sha }}"
    )
    assert "if" not in evidence_step
    size_step = next(
        step
        for step in ownership_steps
        if step.get("name") == "Reject new or changed files over 2 MB"
    )
    assert size_step["run"] == "python scripts/ci/check_file_size.py"
    assert size_step["env"]["PR_BASE_SHA"] == (
        "${{ github.event.pull_request.base.sha }}"
    )

    event_if = f"({_DRAFT_OR_PUSH} || {_FULL_RUN})"
    assert jobs["backend-shards"]["if"] == (
        f"{event_if} && needs.docs-change-gate.outputs.run_backend == 'true'"
    )
    assert jobs["frontend-checks"]["if"] == event_if
    assert "needs.docs-change-gate.outputs.run_frontend == 'true'" in "\n".join(
        step.get("if") or "" for step in jobs["frontend-checks"]["steps"]
    )
    marketing = jobs["marketing-checks"]
    assert _job_needs(marketing) == ["docs-change-gate"]
    assert marketing["if"] == event_if
    assert "needs.docs-change-gate.outputs.run_marketing == 'true'" in "\n".join(
        step.get("if") or "" for step in marketing["steps"]
    )
    guest_job = jobs["database-shards"]
    assert _job_needs(guest_job) == ["docs-change-gate"]
    assert guest_job["if"] == (
        f"({_DRAFT_OR_PUSH} || {_LATEST_CLI_PROBE}) && "
        "needs.docs-change-gate.outputs.run_database == 'true'"
    )

    smoke = _smoke_workflow()
    smoke_gate = smoke["jobs"]["docs-change-gate"]
    smoke_classify = next(
        step for step in smoke_gate["steps"] if step.get("id") == "classify"
    )
    assert smoke_gate["if"] == _DRAFT_OR_NON_PR
    assert smoke_classify["run"] == ".github/docs-only-changes.sh"
    assert "paths-ignore" not in WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "paths-ignore" not in SMOKE_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "paths:" not in WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "paths:" not in SMOKE_WORKFLOW_PATH.read_text(encoding="utf-8")


def test_docs_checks_job_runs_only_when_the_gate_reports_docs_only() -> None:
    jobs = _workflow()["jobs"]
    job = jobs["docs-checks"]
    joined_steps = "\n".join(str(step.get("run", "")) for step in job["steps"])

    assert _job_needs(job) == ["docs-change-gate"]
    assert job["if"] == (
        f"({_DRAFT_OR_PUSH}) && " "needs.docs-change-gate.outputs.docs_only == 'true'"
    )
    assert "git diff --check" in joined_steps
    assert "poetry install --with dev --no-interaction" in joined_steps
    assert ".github/docs-reading-tests.sh" in joined_steps
    assert "tests/test_openapi_compatibility.py" not in joined_steps
    assert "bun install --frozen-lockfile" in joined_steps
    assert "bun test" not in joined_steps
    assert "bun run build" not in joined_steps
    setup_bun = next(
        step
        for step in job["steps"]
        if step.get("uses")
        == "oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6"
    )
    assert setup_bun["with"]["bun-version"] == "${{ env.ARGUS_CI_BUN_VERSION }}"
    assert "supabase" not in joined_steps.lower()
    assert "local-smoke" not in joined_steps
    assert "docs-checks" in jobs["ci"]["needs"]


def test_docs_reading_tests_selector_includes_guest_observability() -> None:
    result = subprocess.run(
        ["bash", str(DOCS_READING_TESTS_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    selected = result.stdout.splitlines()
    for expected in ("tests/test_guest_observability.py", "tests/test_home_country.py"):
        assert any(
            expected == path or expected.startswith(path + "/") for path in selected
        )
    assert all(
        (ROOT / path).is_dir() or name.startswith("test_") or name.endswith("_test.py")
        for path in selected
        for name in (Path(path).name,)
    )


def test_ci_aggregator_requires_docs_checks_success_when_docs_only() -> None:
    run = _workflow()["jobs"]["ci"]["steps"][0]["run"]
    env = _workflow()["jobs"]["ci"]["steps"][0]["env"]

    assert env["DOCS_ONLY"] == "${{ needs.docs-change-gate.outputs.docs_only }}"
    # docs_only selects docs-checks; tests/test_docs_ci_gate.py executes both
    # branches, so a docs-only run needs docs-checks success.
    assert 'require_selected docs-checks "$DOCS_ONLY" "$DOCS_CHECKS"' in run
    selected_branch = run.split("require_selected() {", 1)[1].split("elif", 1)[0]
    assert 'if [ "$2" = true ]; then' in selected_branch
    assert 'require_success "$1" "$3"' in selected_branch


def test_ci_aggregator_allows_skipped_docs_checks_when_not_docs_only() -> None:
    run = _workflow()["jobs"]["ci"]["steps"][0]["run"]
    selected_branch = run.split("require_selected() {", 1)[1].split("}", 1)[0]
    unselected_branch = selected_branch.split("elif", 1)[1]
    assert '[ "$3" != skipped ]' in unselected_branch
    assert '[ "$3" != success ]' in unselected_branch


def test_real_postgres_matrix_runs_on_pinned_and_latest_supabase_cli() -> None:
    workflow = _workflow()
    guest_job = workflow["jobs"]["database-shards"]

    assert workflow["on"]["schedule"] == [{"cron": "17 9 * * 1"}]
    assert "workflow_dispatch" in workflow["on"]
    assert guest_job["strategy"]["fail-fast"] is False
    assert guest_job["strategy"]["matrix"]["supabase-cli"] == (
        "${{ fromJSON(github.event_name == 'pull_request' && '[\"pinned\"]' || "
        "((github.event_name == 'schedule' || "
        "(github.event_name == 'workflow_dispatch' && !inputs.full_run)) && "
        '\'["latest"]\' || \'["pinned", "latest"]\')) }}'
    )
    by_name = {step.get("name"): step for step in guest_job["steps"]}
    always = (
        "Start disposable local Supabase",
        "Print Supabase CLI and image versions",
        "Run required real-PostgreSQL matrix",
    )
    for name in always:
        assert "if" not in by_name[name], name
    pinned_only = [
        name
        for name, step in by_name.items()
        if step.get("if") == "matrix.supabase-cli == 'pinned' && matrix.shard == 0"
    ]
    assert pinned_only == [
        "Run required local anonymous Auth matrix",
    ]


def test_scheduled_probe_runs_no_other_job() -> None:
    jobs = _workflow()["jobs"]
    probe_jobs = {"docs-change-gate", "database-checks", "database-shards"}

    for name, job in jobs.items():
        if name in probe_jobs:
            assert _LATEST_CLI_PROBE in job["if"], name
        else:
            assert _LATEST_CLI_PROBE not in job["if"], name
            assert _DRAFT_OR_PUSH in job["if"], name
