from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / ".github" / "setup-worktree-env.sh"
SETUP = ROOT / ".github" / "setup.sh"
CODEX_ENVIRONMENT = ROOT / ".codex" / "environments" / "environment.toml"
GITIGNORE = ROOT / ".gitignore"
BACKEND_SECRET = "backend-secret-value"
FRONTEND_SECRET = "frontend-secret-value"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _create_worktrees(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "argus-tests@example.com")
    _git(repository, "config", "user.name", "Argus Tests")

    (repository / ".gitignore").write_text(
        ".env\nweb/.env.local\n",
        encoding="utf-8",
    )
    (repository / "tracked.txt").write_text("seed\n", encoding="utf-8")
    _git(repository, "add", ".gitignore", "tracked.txt")
    _git(repository, "commit", "-m", "test: seed repository")
    _git(repository, "branch", "codex/private-alpha-next")

    canonical = tmp_path / "canonical integration"
    worker = tmp_path / "issue 194 worker"
    _git(
        repository,
        "worktree",
        "add",
        str(canonical),
        "codex/private-alpha-next",
    )
    _git(
        repository,
        "worktree",
        "add",
        "-b",
        "codex/issue-194",
        str(worker),
        "main",
    )
    return canonical, worker


def _write_canonical_env(canonical: Path) -> None:
    (canonical / ".env").write_text(
        f"OPENROUTER_API_KEY={BACKEND_SECRET}\n",
        encoding="utf-8",
    )
    (canonical / "web").mkdir(exist_ok=True)
    (canonical / "web" / ".env.local").write_text(
        f"NEXT_PUBLIC_SUPABASE_ANON_KEY={FRONTEND_SECRET}\n",
        encoding="utf-8",
    )


def _run_helper(
    target: Path,
    *,
    canonical_override: Path | None = None,
    check_only: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("ARGUS_CANONICAL_WORKTREE_ROOT", None)
    env.pop("CUADRAO_LOCAL_ENV_STORE", None)
    if canonical_override is not None:
        env["ARGUS_CANONICAL_WORKTREE_ROOT"] = str(canonical_override)

    command = ["bash", str(HELPER)]
    if check_only:
        command.append("--check")
    command.append(str(target))
    return subprocess.run(
        command,
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def test_setup_calls_worktree_env_helper_before_dependency_setup() -> None:
    source = SETUP.read_text(encoding="utf-8")

    assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in source
    assert 'REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"' in source
    invocation = '"$SCRIPT_DIR/setup-worktree-env.sh" "$REPO_ROOT"'
    assert invocation in source
    assert source.index(invocation) < source.index("PINNED_PYTHON=")
    assert "git ls-files -- .env web/.env.local" in source


def test_setup_pins_poetry_and_bun_to_ci_versions() -> None:
    source = SETUP.read_text(encoding="utf-8")

    assert 'PINNED_POETRY_VERSION="2.1.3"' in source
    assert 'POETRY_VERSION="$PINNED_POETRY_VERSION" "$PYTHON_CMD" -' in source
    assert 'PINNED_BUN_VERSION="1.3.14"' in source
    assert 'bash -s "bun-v$PINNED_BUN_VERSION"' in source


def test_setup_binds_poetry_to_exact_repo_python_version() -> None:
    source = SETUP.read_text(encoding="utf-8")

    assert 'uv python install "$PINNED_PYTHON"' in source
    assert 'uv python find "$PINNED_PYTHON"' in source
    assert "== '$PINNED_PYTHON'" in source
    assert 'poetry env use "$PYTHON_CMD"' in source


def test_setup_persists_cloud_toolchain_path_and_disables_next_telemetry() -> None:
    source = SETUP.read_text(encoding="utf-8")

    assert 'SHELL_PROFILE="$HOME/.bashrc"' in source
    assert 'export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"' in source
    assert 'export NEXT_TELEMETRY_DISABLED=1' in source
    assert "next telemetry disable" not in source


def test_next_telemetry_cache_cannot_dirty_cloud_checkouts() -> None:
    source = GITIGNORE.read_text(encoding="utf-8")

    assert "web/cache/config.json" in source.splitlines()


def test_codex_environment_delegates_to_tracked_setup_and_cleanup() -> None:
    source = CODEX_ENVIRONMENT.read_text(encoding="utf-8")

    assert "exec .github/setup.sh" in source
    assert 'exec .github/cleanup-worktree.sh "${1:-$PWD}" "${2:-safe}"' in source
    assert "poetry install" not in source
    assert "bun install" not in source
    assert "ALPACA_API_KEY" not in source


def test_setup_without_store_never_links_integration_files(tmp_path: Path) -> None:
    canonical, worker = _create_worktrees(tmp_path)
    _write_canonical_env(canonical)
    result = _run_helper(worker)
    assert result.returncode == 0, _combined_output(result)
    assert not (worker / ".env").exists()
    assert not (worker / "web" / ".env.local").exists()


def test_setup_rejects_old_links_without_reading_or_changing_them(tmp_path: Path) -> None:
    canonical, worker = _create_worktrees(tmp_path)
    _write_canonical_env(canonical)
    (worker / ".env").symlink_to(canonical / ".env")
    result = _run_helper(worker)
    assert result.returncode != 0
    assert (worker / ".env").is_symlink()
    assert BACKEND_SECRET not in _combined_output(result)
