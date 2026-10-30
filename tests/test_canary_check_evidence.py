from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest
from faker import Faker

from tests.test_render_canary_script import (
    IMPORT_MARKER,
    RENDER_RUNNER,
    ROOT,
    _browser_checks,
    _function_heredoc,
    _required_checks,
    _shell_assignment,
    _source,
)


def _heredoc_env(source: str, name: str, **values: str) -> dict[str, str]:
    preamble = source.split(f"{name}() {{", 1)[1].split("python3 - ", 1)[0]
    env = os.environ.copy()
    for variable in re.findall(r"^\s*(CANARY_[A-Z_]+)=", preamble, re.MULTILINE):
        env[variable] = ""
    env.update(values)
    return env


HANDOFF_CONTRACT = ROOT / "web/e2e/support/private-alpha-canary-handoff.json"
CONTRACT = json.loads(HANDOFF_CONTRACT.read_text(encoding="utf-8"))


def _passing_handoff(faker: Faker, user_id: str) -> dict[str, Any]:
    return {
        "schema_version": CONTRACT["schema_version"],
        "source": CONTRACT["source"],
        "user_id": user_id,
        "checks": {
            name: {
                "status": CONTRACT["statuses"]["passed"],
                "conversation_id": faker.uuid4(),
            }
            for name in _browser_checks()
        },
    }


def _run_import(
    tmp_path: Path,
    handoff: object,
    *,
    user_id: str,
    mode: int = 0o600,
    contract: Path = HANDOFF_CONTRACT,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    source = _source(RENDER_RUNNER)
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    handoff_path.chmod(mode)
    evidence_path = tmp_path / "browser-evidence.json"
    raw_ids_path = tmp_path / "raw-ids.txt"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _function_heredoc(source, "import_browser_check_results", IMPORT_MARKER),
            str(handoff_path),
            str(evidence_path),
            str(raw_ids_path),
        ],
        cwd=ROOT,
        env=_heredoc_env(
            source,
            "import_browser_check_results",
            CANARY_SESSION_USER_ID=user_id,
            CANARY_REQUIRED_CHECKS="\n".join(_required_checks()),
            CANARY_SAME_COMMIT_CHECK=_shell_assignment(source, "SAME_COMMIT_CHECK"),
            CANARY_HANDOFF_CONTRACT=str(contract),
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    return result, evidence_path, raw_ids_path


def test_browser_check_import_labels_identities_and_reports_no_failure(
    tmp_path: Path, faker: Faker
) -> None:
    user_id = faker.uuid4()
    names = _browser_checks()
    job_id = faker.uuid4()
    handoff = _passing_handoff(faker, user_id)
    handoff["checks"][names[0]]["sign_in_attempts"] = 2
    handoff["checks"][names[1]]["backtest_job_id"] = job_id

    result, evidence_path, raw_ids_path = _run_import(tmp_path, handoff, user_id=user_id)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "-|-|-|-"
    evidence_text = evidence_path.read_text(encoding="utf-8")
    evidence = json.loads(evidence_text)
    assert list(evidence) == names
    assert evidence[names[0]]["sign_in_attempts"] == 2
    assert evidence[names[1]]["backtest_job_label"] == (
        f"backtest_job_{hashlib.sha256(job_id.encode()).hexdigest()[:12]}"
    )
    assert user_id not in evidence_text
    assert job_id not in evidence_text
    assert job_id in raw_ids_path.read_text(encoding="utf-8").splitlines()
    for name in names:
        assert f"canary_check={name} status=passed" in result.stderr


def test_browser_check_import_names_the_first_check_that_did_not_pass(
    tmp_path: Path, faker: Faker
) -> None:
    user_id = faker.uuid4()
    names = _browser_checks()
    conversation_id = faker.uuid4()
    handoff = _passing_handoff(faker, user_id)
    handoff["checks"][names[0]] = {
        "status": "failed",
        "reason": "assistant_answer_missing",
        "conversation_id": conversation_id,
    }
    handoff["checks"][names[1]] = {"status": "not_run"}

    result, _, _ = _run_import(tmp_path, handoff, user_id=user_id)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        f"{names[0]}|assistant_answer_missing|{conversation_id}|-"
    )
    assert (
        f"canary_check={names[0]} status=failed "
        "reason=assistant_answer_missing" in result.stderr
    )
    assert f"canary_check={names[1]} status=not_run" in result.stderr

    handoff["checks"] = {name: {"status": "not_run"} for name in names}
    unrun, _, _ = _run_import(tmp_path, handoff, user_id=user_id)
    assert unrun.stdout.strip() == f"{names[0]}|check_not_run|-|-"


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda handoff: handoff.update(user_id="another-user"), id="identity"
        ),
        pytest.param(lambda handoff: handoff.update(schema_version=1), id="schema"),
        pytest.param(
            lambda handoff: handoff["checks"].pop(next(iter(handoff["checks"]))),
            id="missing-check",
        ),
        pytest.param(
            lambda handoff: handoff["checks"].update(decision_note={"status": "passed"}),
            id="feature-check",
        ),
        pytest.param(
            lambda handoff: next(iter(handoff["checks"].values())).update(
                status="skipped"
            ),
            id="status",
        ),
        pytest.param(
            lambda handoff: next(iter(handoff["checks"].values())).update(
                status="failed", reason="Profile said: Private Text"
            ),
            id="unsafe-reason",
        ),
        pytest.param(
            lambda handoff: next(iter(handoff["checks"].values())).update(
                status="failed",
                reason="backtest_job_failed_3f2a1b4c_9d8e_4f7a_8b6c_5d4e3f2a1b0c",
            ),
            id="normalized-identifier-reason",
        ),
        pytest.param(
            lambda handoff: next(iter(handoff["checks"].values())).update(
                conversation_id="../../api/v1/admin"
            ),
            id="unsafe-identity",
        ),
    ],
)
def test_browser_check_import_rejects_an_untrustworthy_handoff(
    tmp_path: Path,
    faker: Faker,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    user_id = faker.uuid4()
    handoff = _passing_handoff(faker, user_id)
    mutate(handoff)

    result, _, _ = _run_import(tmp_path, handoff, user_id=user_id)

    assert result.returncode != 0


def test_browser_check_import_rejects_a_readable_handoff(
    tmp_path: Path, faker: Faker
) -> None:
    user_id = faker.uuid4()

    result, _, _ = _run_import(
        tmp_path, _passing_handoff(faker, user_id), user_id=user_id, mode=0o644
    )

    assert result.returncode != 0
    assert "not private" in result.stderr


def test_release_evidence_merges_check_results_and_rejects_unknown_checks(
    tmp_path: Path,
) -> None:
    source = _source(RENDER_RUNNER)
    python_source = _function_heredoc(source, "build_release_evidence_json")
    names = _browser_checks()
    same_commit = _shell_assignment(source, "SAME_COMMIT_CHECK")
    browser_evidence = tmp_path / "browser-evidence.json"
    browser_entry = {
        "status": "failed",
        "reason": "profile_http_401_unauthorized",
        "conversation_label": "conversation_0123456789ab",
    }
    browser_evidence.write_text(json.dumps({names[0]: browser_entry}), encoding="utf-8")
    env = _heredoc_env(
        source,
        "build_release_evidence_json",
        CANARY_STATUS="failed",
        CANARY_SURFACE="authenticated-browser-journey",
        CANARY_FAILED=names[0],
        CANARY_FAILURE_REASON="profile_http_401_unauthorized",
        CANARY_REQUIRED_CHECKS="\n".join(_required_checks()),
        CANARY_SHELL_CHECK_RESULTS=f"{same_commit}=passed\n{names[0]}=failed\n",
        CANARY_BROWSER_CHECK_EVIDENCE=str(browser_evidence),
        CANARY_BROWSER_STATUS="failed",
        CANARY_CAPTURE_WRITE_STATUS="written",
        CANARY_EXPECTED_MODE="real-workflow",
    )

    result = subprocess.run(
        [sys.executable, "-c", python_source],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["failed"] == names[0]
    assert evidence["failure_reason"] == "profile_http_401_unauthorized"
    assert evidence["checks"] == {
        same_commit: {"status": "passed"},
        names[0]: browser_entry,
    }
    assert evidence["privacy"] == "no_raw_ids; labels are sha256 prefixes"

    env["CANARY_SHELL_CHECK_RESULTS"] = "decision_note=passed\n"
    rejected = subprocess.run(
        [sys.executable, "-c", python_source],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert "does not require" in rejected.stderr


def test_evidence_artifact_refuses_a_raw_private_identifier(
    tmp_path: Path, faker: Faker
) -> None:
    source = _source(RENDER_RUNNER)
    python_source = _function_heredoc(source, "write_json_artifact")
    raw_id = faker.uuid4()
    raw_ids = tmp_path / "raw-ids.txt"
    raw_ids.write_text(f"{raw_id}\n", encoding="utf-8")
    destination = tmp_path / "evidence.json"

    def write(evidence: dict[str, Any]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", python_source],
            cwd=ROOT,
            env=_heredoc_env(
                source,
                "write_json_artifact",
                CANARY_DESTINATION=str(destination),
                CANARY_ARTIFACT_KIND="evidence",
                CANARY_EVIDENCE_JSON=json.dumps(evidence),
                CANARY_USER_ID=faker.uuid4(),
                CANARY_RAW_IDS_FILE=str(raw_ids),
            ),
            capture_output=True,
            text=True,
            check=False,
        )

    leaked = write({"checks": {"backtest": {"note": raw_id}}})
    assert leaked.returncode != 0
    assert "raw private identifier" in leaked.stderr
    assert not destination.exists()

    unlisted = write({"checks": {"backtest": {"note": faker.uuid4()}}})
    assert unlisted.returncode != 0
    assert "raw private identifier" in unlisted.stderr
    assert not destination.exists()

    label = f"conversation_{hashlib.sha256(raw_id.encode()).hexdigest()[:12]}"
    written = write({"checks": {"backtest": {"conversation_label": label}}})
    assert written.returncode == 0, written.stderr
    assert json.loads(destination.read_text(encoding="utf-8"))["artifact_kind"] == (
        "evidence"
    )
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_browser_artifact_redaction_masks_every_rendered_identifier(
    tmp_path: Path, faker: Faker
) -> None:
    source = _source(RENDER_RUNNER)
    python_source = _function_heredoc(source, "redact_browser_artifacts")
    results = tmp_path / "playwright-results" / "case"
    results.mkdir(parents=True)
    # This run's ids and older canary conversations listed in Recents alike.
    identifiers = [faker.uuid4() for _ in range(4)]
    context_path = results / "error-context.md"
    context_path.write_text(
        "".join(
            f'- link "Chat":\n  - /url: /chat?conversation={identifier}\n'
            for identifier in identifiers
        )
        + f"profile {identifiers[0].upper()}\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "CANARY_REDACT_DIR": str(tmp_path / "playwright-results"),
            "CANARY_REDACT_SIMULATE_FAILURE": "false",
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", python_source],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    redacted = context_path.read_text(encoding="utf-8")
    for identifier in identifiers:
        assert identifier not in redacted.lower()
    assert redacted.count("<redacted>") == len(identifiers) + 1
    assert (tmp_path / "playwright-results" / ".redacted").is_file()


def test_browser_check_import_reads_the_one_handoff_contract(
    tmp_path: Path, faker: Faker
) -> None:
    user_id = faker.uuid4()
    handoff = _passing_handoff(faker, user_id)
    next(iter(handoff["checks"].values())).update(
        status=CONTRACT["statuses"]["failed"], reason="profile_http_401_unauthorized"
    )
    stricter = tmp_path / "stricter-contract.json"
    stricter.write_text(
        json.dumps({**CONTRACT, "reason": {**CONTRACT["reason"], "pattern": "^[a-z]+$"}}),
        encoding="utf-8",
    )
    renamed = tmp_path / "renamed-contract.json"
    renamed.write_text(json.dumps({**CONTRACT, "source": "another_producer"}), encoding="utf-8")

    accepted, _, _ = _run_import(tmp_path, handoff, user_id=user_id)
    refused, _, _ = _run_import(tmp_path, handoff, user_id=user_id, contract=stricter)
    foreign, _, _ = _run_import(tmp_path, handoff, user_id=user_id, contract=renamed)

    assert accepted.returncode == 0, accepted.stderr
    assert "browser check handoff has an unsafe failure reason" in refused.stderr
    assert "browser check handoff contract is invalid" in foreign.stderr

    # Status meanings come from the contract too: a renamed pass is still a pass.
    relabeled = tmp_path / "relabeled-contract.json"
    relabeled.write_text(
        json.dumps({**CONTRACT, "statuses": {**CONTRACT["statuses"], "passed": "succeeded"}}),
        encoding="utf-8",
    )
    passing = _passing_handoff(faker, user_id)
    for entry in passing["checks"].values():
        entry["status"] = "succeeded"
    relabeled_run, _, _ = _run_import(tmp_path, passing, user_id=user_id, contract=relabeled)
    assert relabeled_run.returncode == 0, relabeled_run.stderr
    assert relabeled_run.stdout.strip() == "-|-|-|-"


def test_session_tool_names_only_the_failures_it_raised() -> None:
    session = _source("web/e2e/support/private-alpha-canary-session.ts")
    assert "new Error(" not in session
    assert 'error instanceof CheckFailure ? error.reason : "unknown_failure"' in session

    result = subprocess.run(
        ["bun", "e2e/support/private-alpha-canary-session.ts", "not_a_mode"],
        cwd=ROOT / "web",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "canary_session_state=failed reason=canary_session_mode_invalid" in result.stderr
