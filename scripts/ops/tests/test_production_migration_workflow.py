from __future__ import annotations

import importlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import httpx
import pytest


@pytest.fixture
def promotion(tmp_path: Path, faker: Any) -> SimpleNamespace:
    sha, trusted = faker.sha1(), faker.sha1()
    repository = "fixture/repository"
    pr = {
        "number": 12,
        "state": "open",
        "draft": True,
        "base": {"ref": "main", "repo": {"full_name": repository}},
        "head": {"sha": sha},
    }
    return SimpleNamespace(
        sha=sha,
        trusted=trusted,
        repo=tmp_path,
        env={
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": trusted,
            "GITHUB_REPOSITORY": repository,
            "GITHUB_RUN_ID": "123",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_API_URL": "https://api.example.invalid",
            "GH_TOKEN": faker.password(),
            "PR_NUMBER": "12",
            "RUNNER_TEMP": str(tmp_path),
            "PATH": "/usr/bin:/bin",
            "ARGUS_PRODUCTION_DATABASE_URL": "postgresql://reader:synthetic@db.invalid/postgres",
            "CUADRAO_PRODUCTION_DATABASE_SSL_ROOT_CERT": "synthetic public CA",
        },
        initial=pr,
        final=deepcopy(pr),
        reads=0,
        posts=[],
        commands=[],
        gate_code=0,
        fetch_code=0,
        fetched_sha=sha,
        api_error=False,
        report={"candidate_sha": sha, "trusted_sha": trusted, "status": "pass"},
    )


def install_boundaries(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
) -> None:
    def request_json(
        _settings: object,
        route: str,
        body: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        if body is not None:
            promotion.posts.append((route, body))
            return {}
        promotion.reads += 1
        if promotion.api_error and promotion.reads > 1:
            raise RuntimeError(promotion.env["GH_TOKEN"])
        assert route == "pulls/12"
        return promotion.initial if promotion.reads == 1 else promotion.final

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        promotion.commands.append((command, kwargs))
        assert promotion.env["ARGUS_PRODUCTION_DATABASE_URL"] not in str(command)
        if command[0] == "git":
            assert "ARGUS_PRODUCTION_DATABASE_URL" not in kwargs["env"]
            assert "GH_TOKEN" not in kwargs["env"]
            assert promotion.env["ARGUS_PRODUCTION_DATABASE_URL"] not in str(kwargs)
            assert promotion.env["GH_TOKEN"] not in str(kwargs)
            if "fetch" in command:
                if getattr(promotion, "fetch_exception", False):
                    raise subprocess.TimeoutExpired(command, 120, output=str(command))
                return subprocess.CompletedProcess(
                    command,
                    promotion.fetch_code,
                    str(command),
                    str(command),
                )
            assert command == ["git", "rev-parse", "--verify", "FETCH_HEAD^{commit}"]
            return subprocess.CompletedProcess(command, 0, promotion.fetched_sha, "")
        assert Path(command[1]).name == "production_migration_gate.py"
        assert command[2:6] == [
            "--candidate-sha",
            promotion.sha,
            "--trusted-sha",
            promotion.trusted,
        ]
        assert (
            kwargs["env"]["ARGUS_PRODUCTION_DATABASE_URL"]
            == promotion.env["ARGUS_PRODUCTION_DATABASE_URL"]
        )
        assert "GH_TOKEN" not in kwargs["env"]
        Path(command[command.index("--output") + 1]).write_text(
            json.dumps(promotion.report)
        )
        return subprocess.CompletedProcess(command, promotion.gate_code, "", "")

    monkeypatch.setattr(module, "request_json", request_json)
    monkeypatch.setattr(module.subprocess, "run", run)


def execute(monkeypatch: pytest.MonkeyPatch, promotion: SimpleNamespace) -> int:
    module = importlib.import_module("scripts.ops.production_migration_workflow")
    install_boundaries(module, monkeypatch, promotion)
    return module.run_promotion(
        module.WorkflowSettings(**promotion.env), repo_root=promotion.repo
    )


@pytest.mark.parametrize(
    "code,status,expected",
    [
        (0, "pass", "success"),
        (1, "blocked", "failure"),
        (2, "blocked", "error"),
        (7, "pass", "error"),
        (-9, "pass", "error"),
        (0, "blocked", "error"),
        (1, "pass", "error"),
    ],
)
def test_gate_exit_controls_status_on_the_exact_head(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
    code: int,
    status: str,
    expected: str,
) -> None:
    promotion.gate_code = code
    promotion.report["status"] = status
    result = execute(monkeypatch, promotion)
    assert result == (0 if expected == "success" else 1)
    assert [body["state"] for _, body in promotion.posts] == ["pending", expected]
    assert all(route == f"statuses/{promotion.sha}" for route, _ in promotion.posts)
    assert all(
        body["context"] == "production-migration-gate" for _, body in promotion.posts
    )
    assert all(
        body["target_url"].endswith("/actions/runs/123") for _, body in promotion.posts
    )
    report = json.loads((promotion.repo / "production-migration-gate.json").read_text())
    assert report["publication_status"] == expected
    assert report["candidate_sha"] == promotion.sha
    assert report["trusted_sha"] == promotion.trusted
    assert not (promotion.repo / "production-ledger-ca.crt").exists()


@pytest.mark.parametrize(
    "change",
    [
        "closed",
        "missing_state",
        "wrong_base",
        "wrong_repo",
        "invalid_sha",
        "wrong_number",
    ],
)
def test_non_open_or_invalid_promotion_never_reads_ledger_or_posts_success(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
    change: str,
) -> None:
    if change == "closed":
        promotion.initial["state"] = "closed"
    elif change == "missing_state":
        promotion.initial.pop("state")
    elif change == "wrong_base":
        promotion.initial["base"]["ref"] = "other"
    elif change == "wrong_repo":
        promotion.initial["base"]["repo"]["full_name"] = "fixture/other"
    elif change == "wrong_number":
        promotion.initial["number"] = 13
    else:
        promotion.initial["head"]["sha"] = "main"
    assert execute(monkeypatch, promotion) == 1
    assert promotion.posts == []
    assert promotion.commands == []


@pytest.mark.parametrize("change", ["head", "closed", "base", "api_error"])
def test_metadata_is_rechecked_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
    change: str,
) -> None:
    if change == "head":
        promotion.final["head"]["sha"] = promotion.trusted
    elif change == "closed":
        promotion.final["state"] = "closed"
    elif change == "base":
        promotion.final["base"]["ref"] = "other"
    else:
        promotion.api_error = True
    assert execute(monkeypatch, promotion) == 1
    assert promotion.reads == 2
    assert [body["state"] for _, body in promotion.posts] == ["pending", "error"]
    report = json.loads((promotion.repo / "production-migration-gate.json").read_text())
    assert report["status"] == "blocked"
    assert report["publication_status"] == "error"


@pytest.mark.parametrize("identity", ["candidate_sha", "trusted_sha"])
def test_report_identity_mismatch_cannot_publish_success(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
    identity: str,
) -> None:
    promotion.report[identity] = "c" * 40
    assert execute(monkeypatch, promotion) == 1
    assert promotion.posts[-1][1]["state"] == "error"


@pytest.mark.parametrize(
    "field,value",
    [
        ("GITHUB_REF", "refs/heads/other"),
        ("GITHUB_REF", "refs/tags/main"),
        ("GITHUB_SHA", "main"),
        ("PR_NUMBER", "0"),
        ("PR_NUMBER", "12;anything"),
    ],
)
def test_dispatch_validation_happens_before_api_or_git(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
    field: str,
    value: str,
) -> None:
    promotion.env[field] = value
    assert execute(monkeypatch, promotion) == 1
    assert promotion.reads == 0
    assert promotion.posts == promotion.commands == []


@pytest.mark.parametrize("failure", ["fetch", "fetched_sha", "missing_url", "missing_ca"])
def test_preflight_failures_cannot_publish_success(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
    failure: str,
) -> None:
    if failure == "fetch":
        promotion.fetch_code = 1
    elif failure == "fetched_sha":
        promotion.fetched_sha = promotion.trusted
    elif failure == "missing_url":
        promotion.env["ARGUS_PRODUCTION_DATABASE_URL"] = ""
    else:
        promotion.env["CUADRAO_PRODUCTION_DATABASE_SSL_ROOT_CERT"] = ""
    assert execute(monkeypatch, promotion) == 1
    assert promotion.posts[-1][1]["state"] == "error"
    assert all(command[0] == "git" for command, _ in promotion.commands)


def test_ledger_secret_is_sent_only_to_gate_not_git_or_logs(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
    capfd: pytest.CaptureFixture[str],
) -> None:
    assert execute(monkeypatch, promotion) == 0
    assert len(promotion.commands) == 3
    for command, kwargs in promotion.commands[:2]:
        assert command[0] == "git"
        assert set(kwargs["env"]) == {"PATH", "GIT_TERMINAL_PROMPT"}
    contents = (promotion.repo / "production-migration-gate.json").read_text()
    captured = capfd.readouterr()
    for name in ("ARGUS_PRODUCTION_DATABASE_URL", "GH_TOKEN"):
        assert promotion.env[name] not in captured.out + captured.err + contents


def test_cli_loads_existing_env_contract_without_dotenv_discovery(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
) -> None:
    module = importlib.import_module("scripts.ops.production_migration_workflow")
    for key, value in promotion.env.items():
        monkeypatch.setenv(key, value)
    install_boundaries(module, monkeypatch, promotion)
    assert module.main() == 0
    assert promotion.posts[-1][1]["state"] == "success"
    assert module.WorkflowSettings.model_config.get("env_file") is None


def test_api_adapter_uses_authenticated_bounded_requests(
    promotion: SimpleNamespace,
    respx_mock: Any,
) -> None:
    module = importlib.import_module("scripts.ops.production_migration_workflow")
    route = respx_mock.get(
        "https://api.example.invalid/repos/fixture/repository/pulls/12"
    ).mock(return_value=httpx.Response(200, json=promotion.initial))
    settings = module.WorkflowSettings(**promotion.env)
    assert module.request_json(settings, "pulls/12") == promotion.initial
    assert (
        route.calls.last.request.headers["Authorization"]
        == "Bearer " + promotion.env["GH_TOKEN"]
    )


_FETCH_TOKEN = "synthetic-workflow-token"
_FETCH_ENCODING = "eC1hY2Nlc3MtdG9rZW46c3ludGhldGljLXdvcmtmbG93LXRva2Vu"


def test_candidate_fetch_authentication_is_one_shot_and_origin_scoped(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
) -> None:
    promotion.env["GH_TOKEN"] = _FETCH_TOKEN
    promotion.initial["head"]["repo"] = {
        "clone_url": "https://untrusted.invalid/other/repository.git",
    }
    assert execute(monkeypatch, promotion) == 0
    fetch, fetch_options = promotion.commands[0]
    assert fetch == [
        "git",
        "-c",
        "http.https://github.com/fixture/repository.git.extraheader="
        "AUTHORIZATION: basic " + _FETCH_ENCODING,
        "-c",
        "http.followRedirects=false",
        "fetch",
        "--no-tags",
        "https://github.com/fixture/repository.git",
        "refs/pull/12/head",
    ]
    assert fetch_options["env"] == {"PATH": "/usr/bin:/bin", "GIT_TERMINAL_PROMPT": "0"}
    assert fetch_options["capture_output"] is True
    assert fetch_options["check"] is False
    assert promotion.commands[1][0] == [
        "git",
        "rev-parse",
        "--verify",
        "FETCH_HEAD^{commit}",
    ]
    gate, gate_options = promotion.commands[2]
    assert Path(gate[1]).name == "production_migration_gate.py"
    assert gate[2:] == [
        "--candidate-sha",
        promotion.sha,
        "--trusted-sha",
        promotion.trusted,
        "--output",
        str(promotion.repo / "production-migration-gate.json"),
    ]
    assert gate_options["env"] == {
        "PATH": "/usr/bin:/bin",
        "GIT_TERMINAL_PROMPT": "0",
        "ARGUS_PRODUCTION_DATABASE_URL": promotion.env["ARGUS_PRODUCTION_DATABASE_URL"],
        "ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT": str(
            promotion.repo / "production-ledger-ca.crt"
        ),
    }
    for command, options in promotion.commands[1:]:
        assert _FETCH_TOKEN not in str((command, options))
        assert _FETCH_ENCODING not in str((command, options))
        assert "extraheader" not in str((command, options))


@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_authenticated_fetch_failures_never_expose_credentials(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
    capfd: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    promotion.env["GH_TOKEN"] = _FETCH_TOKEN
    promotion.fetch_code = 128
    promotion.fetch_exception = failure == "timeout"
    assert execute(monkeypatch, promotion) == 1
    assert len(promotion.commands) == 1
    assert _FETCH_ENCODING in str(promotion.commands[0][0])
    assert promotion.posts[-1][1]["state"] == "error"
    captured = capfd.readouterr()
    evidence = (promotion.repo / "production-migration-gate.json").read_text()
    for value in [
        _FETCH_TOKEN,
        _FETCH_ENCODING,
        promotion.env["ARGUS_PRODUCTION_DATABASE_URL"],
    ]:
        assert value not in captured.out + captured.err + evidence


@pytest.mark.parametrize(
    "key,value",
    [
        ("GITHUB_SERVER_URL", "https://untrusted.invalid"),
        ("GITHUB_SERVER_URL", "https://github.com@untrusted.invalid"),
        ("GITHUB_SERVER_URL", "http://github.com"),
        ("GITHUB_REPOSITORY", "fixture/../other"),
        ("GITHUB_REPOSITORY", "fixture/repository?override"),
        ("GH_TOKEN", ""),
    ],
)
def test_invalid_fetch_origin_or_missing_token_never_starts_git(
    monkeypatch: pytest.MonkeyPatch,
    promotion: SimpleNamespace,
    key: str,
    value: str,
) -> None:
    promotion.env[key] = value
    assert execute(monkeypatch, promotion) == 1
    assert promotion.commands == []
    assert not any(body["state"] == "success" for _, body in promotion.posts)
