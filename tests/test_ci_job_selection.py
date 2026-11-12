"""CI selection contracts: package skips, literal sharing, and support scans."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/docs-only-changes.sh"
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
FAKE = Faker()
ALWAYS = {"docs-change-gate", "ownership-gate", "ci"}
MARKETING = ALWAYS | {"marketing-checks"}


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def classify(root: Path, *paths: str, event: str = "pull_request"):
    return subprocess.run(
        ["bash", str(root / ".github/docs-only-changes.sh"), "--files", *paths],
        cwd=root, env={**os.environ, "GITHUB_OUTPUT": "", "GITHUB_EVENT_NAME": event},
        capture_output=True, text=True,
    )


def outputs(result):
    assert result.returncode == 0, result.stderr
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if line.startswith(("run_", "docs_only=")))


def jobs_for(*paths):
    flags = outputs(classify(ROOT, *paths))
    return ALWAYS | {f"{package}-checks" for package in ("marketing", "backend", "frontend", "database") if flags[f"run_{package}"] == "true"}


@pytest.fixture
def checkout(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / ".github").mkdir()
    shutil.copy(SCRIPT, tmp_path / ".github/docs-only-changes.sh")
    (tmp_path / "pyproject.toml").write_text('[tool.poetry]\npackages = [{include = "argus", from = "src"}]\n')
    return tmp_path


@pytest.mark.parametrize("package", ["web", "marketing"])
def test_package_only_diff_skips_backend_and_database(checkout, package):
    path = f"{package}/lib/{FAKE.word()}.ts"
    (checkout / package / "lib").mkdir(parents=True)
    (checkout / path).write_text("export const value = 1;")
    (checkout / package / "reference.ts").write_text(path)
    git(checkout, "add", ".")
    flags = outputs(classify(checkout, path))
    assert flags["run_backend"] == flags["run_database"] == "false"
    assert flags["run_frontend"] == str(package == "web").lower()
    assert flags["run_marketing"] == str(package == "marketing").lower()


@pytest.mark.parametrize("package", ["web", "marketing"])
def test_literal_outside_package_reference_runs_every_job(checkout, package):
    path = f"{package}/lib/{FAKE.word()}.ts"
    other = checkout / "tests/reference.txt"
    other.parent.mkdir()
    other.write_text(path)
    git(checkout, "add", ".")
    flags = outputs(classify(checkout, path))
    assert all(value == "true" for key, value in flags.items() if key.startswith("run_"))


@pytest.mark.parametrize("package", ["web", "marketing"])
def test_unreferenced_live_package_skips_backend(package):
    flags = outputs(classify(ROOT, f"{package}/components/{FAKE.uuid4()}.tsx"))
    assert flags["run_backend"] == flags["run_database"] == "false"


@pytest.mark.parametrize("folder,name", [
    ("marketing/lib/email", "account-layout.ts"),
    ("marketing/lib/email", "existing-account.ts"),
    ("marketing/content", "legal-es.json"),
    ("marketing/content", "legal-en.json"),
    ("web/argus_display_contract", "support_contact.json"),
])
def test_live_shared_paths_run_every_job(folder, name):
    # Build the path so this test cannot itself supply the literal reference.
    flags = outputs(classify(ROOT, f"{folder}/{name}"))
    assert all(value == "true" for key, value in flags.items() if key.startswith("run_"))


@pytest.mark.parametrize("path", ["web/shared/x.json", "web/nested/shared/x.json"])
def test_package_metadata_runs_every_job(checkout, path):
    (checkout / "pyproject.toml").write_text('[tool.poetry]\npackages = [{include = "**/shared", from = "web"}]\n')
    flags = outputs(classify(checkout, path))
    assert all(value == "true" for key, value in flags.items() if key.startswith("run_"))


def test_marketing_only_diff_runs_support_address_scan_without_backend_install():
    assert jobs_for(f"marketing/app/{FAKE.uuid4()}/page.tsx") == MARKETING
    gate = WORKFLOW["jobs"]["ownership-gate"]
    scans = [step for step in gate["steps"]
             if "scripts/ci/check_support_email.py" in step.get("run", "")]
    assert len(scans) == 1
    assert not scans[0].get("if")
    assert "needs.docs-change-gate" not in gate.get("if", "")
    assert "pull_request" in gate["if"]
    assert not any("poetry install" in step.get("run", "") for step in gate["steps"])


@pytest.fixture
def support_scan_checkout(tmp_path):
    from scripts.ci import check_support_email as scan

    git(tmp_path, "init", "-q")
    script = tmp_path / "scripts/ci/check_support_email.py"
    script.parent.mkdir(parents=True)
    script.write_text((ROOT / "scripts/ci/check_support_email.py").read_text())
    address = FAKE.email()
    for name in {scan.OWNER, *scan.GENERATED.values(), *scan.OTHER_FACTS}:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(address)
    (tmp_path / scan.OWNER).write_text(json.dumps({"email": address}))
    reader = tmp_path / scan.WEB_OWNER
    reader.parent.mkdir(parents=True, exist_ok=True)
    reader.write_text(scan.SUPPORT_EMAIL_ENV)
    return tmp_path, script, address, scan.SUPPORT_EMAIL_ENV


def run_support_scan(script, **kwargs):
    # No site packages or backend imports are available to the standalone gate.
    return subprocess.run(
        [sys.executable, "-I", "-S", str(script)],
        capture_output=True, text=True, **kwargs,
    )


@pytest.mark.parametrize("kind", ["address", "setting", "quoted"])
def test_support_scan_preserves_ownership_and_quote_exclusions(support_scan_checkout, kind):
    root, script, address, setting = support_scan_checkout
    baseline = run_support_scan(script)
    assert baseline.returncode == 0, baseline.stderr
    name, text = {
        "address": ("marketing/components/new.ts", address),
        "setting": ("web/lib/new.ts", setting),
        "quoted": ("docs/example.md", address + setting),
    }[kind]
    extra = root / name
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text(text)
    result = run_support_scan(script)
    if kind == "quoted":
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert name in result.stderr


def test_support_scan_fails_closed_when_git_is_unavailable(support_scan_checkout):
    _, script, _, _ = support_scan_checkout
    assert run_support_scan(script, env={**os.environ, "PATH": ""}).returncode != 0


def test_integration_push_runs_every_job():
    result = subprocess.run(
        ["bash", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "GITHUB_OUTPUT": "", "GITHUB_EVENT_NAME": "push"},
    )
    assert all(value == "true" for key, value in outputs(result).items() if key.startswith("run_"))
