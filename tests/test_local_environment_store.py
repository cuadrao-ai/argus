from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import scripts.ops.staging_env as se

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = """SUPABASE_PROJECT_URL SUPABASE_ANON_PUBLIC_KEY SUPABASE_SERVICE_ROLE_KEY
SUPABASE_JWT_SECRET SUPABASE_POSTGRES_SESSION_POOLER_URL ALPACA_API_KEY ALPACA_SECRET_KEY
OPENROUTER_API_KEY CUADRAO_UTILITY_MODEL CUADRAO_UTILITY_FALLBACK_MODEL CUADRAO_CHAT_MODEL
CUADRAO_CHAT_FALLBACK_MODEL CUADRAO_STRUCTURED_MODEL CUADRAO_STRUCTURED_FALLBACK_MODEL
CUADRAO_CONTEXT_MODEL CUADRAO_CONTEXT_FALLBACK_MODEL CUADRAO_READOUT_MODEL
CUADRAO_READOUT_FALLBACK_MODEL""".split()


def synthetic_jwt(role: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').decode().rstrip("=")
    payload = (
        base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    )
    return f"{header}.{payload}.synthetic-signature"


PUBLIC_ANON = synthetic_jwt("anon")


@pytest.fixture
def values() -> dict[str, str]:
    return dict.fromkeys(REQUIRED, "synthetic-value") | {
        "SUPABASE_PROJECT_URL": "http://127.0.0.1:54321",
        "SUPABASE_POSTGRES_SESSION_POOLER_URL": "postgresql://test:test@localhost:54322/test",
        "SUPABASE_ANON_PUBLIC_KEY": PUBLIC_ANON,
        "SUPABASE_SERVICE_ROLE_KEY": "server-service-secret",
    }


@pytest.fixture
def store(tmp_path: Path, values: dict[str, str]) -> Path:
    path = tmp_path / "selected.env"
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    path.chmod(0o600)
    return path


def worker(tmp_path: Path, name: str = "worker") -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "web").mkdir()
    (root / "web/node_modules").symlink_to(
        ROOT / "web/node_modules", target_is_directory=True
    )
    (root / ".gitignore").write_text(".env\nweb/.env.local\ntemp/*\n!temp/.gitkeep\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def setup(root: Path, store: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("CUADRAO_LOCAL_ENV_STORE", None)
    if store is not None:
        env["CUADRAO_LOCAL_ENV_STORE"] = str(store)
    return subprocess.run(
        ["bash", str(ROOT / ".github/setup-worktree-env.sh"), *args, str(root)],
        env=env,
        capture_output=True,
        text=True,
    )


def test_selected_store_generates_private_isolated_deterministic_files(tmp_path, store):
    roots = [worker(tmp_path, name) for name in ("one", "two")]
    with ThreadPoolExecutor() as pool:
        results = list(pool.map(lambda root: setup(root, store), roots))
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    for relative in (".env", "web/.env.local"):
        first, second = [root / relative for root in roots]
        assert first.is_file() and not first.is_symlink()
        assert first.stat().st_mode & 0o777 == 0o600
        assert first.read_bytes() == second.read_bytes()
        assert first.stat().st_ino != second.stat().st_ino
    before = (roots[0] / ".env").read_bytes()
    assert setup(roots[0], store).returncode == 0
    assert (roots[0] / ".env").read_bytes() == before
    browser = (roots[0] / "web/.env.local").read_text()
    assert f"NEXT_PUBLIC_SUPABASE_ANON_KEY={PUBLIC_ANON}" in browser
    assert "server-service-secret" not in browser
    assert "NEXT_PUBLIC_MOCK_AUTH=false" in browser


@pytest.mark.parametrize(
    "bad", ["$NAME", "${NAME}", "`command`", "a b", "a#b", 'a"b', "a'b", r"a\b", "a\nb"]
)
def test_unsupported_values_fail_without_values_or_partial_writes(tmp_path, store, bad):
    root = worker(tmp_path)
    store.write_text(store.read_text().replace("server-service-secret", bad))
    result = setup(root, store)
    assert result.returncode != 0
    assert bad not in result.stdout + result.stderr
    assert not (root / ".env").exists()
    assert not (root / "web/.env.local").exists()


@pytest.mark.parametrize(
    "problem",
    ["missing", "public", "duplicate", "unknown", "malformed", "permission", "symlink"],
)
def test_invalid_store_fails_closed_even_with_existing_files(tmp_path, store, problem):
    root = worker(tmp_path)
    (root / ".env").write_text("KEEP=unchanged\n")
    if problem == "missing":
        store.write_text(
            store.read_text().replace("OPENROUTER_API_KEY=synthetic-value\n", "")
        )
    elif problem == "public":
        store.write_text(store.read_text().replace(PUBLIC_ANON, "server-service-secret"))
    elif problem == "duplicate":
        store.write_text(store.read_text() + "OPENROUTER_API_KEY=do-not-echo-this\n")
    elif problem == "unknown":
        store.write_text(store.read_text() + "UNKNOWN=do-not-echo-this\n")
    elif problem == "malformed":
        store.write_text(store.read_text() + "do-not-echo-this\n")
    elif problem == "permission":
        store.chmod(0o644)
    else:
        link = store.with_name("link.env")
        link.symlink_to(store)
        store = link
    result = setup(root, store)
    assert result.returncode != 0
    assert "do-not-echo-this" not in result.stdout + result.stderr
    assert "server-service-secret" not in result.stdout + result.stderr
    assert (root / ".env").read_text() == "KEEP=unchanged\n"
    assert not (root / "web/.env.local").exists()


def test_destinations_are_prevalidated_and_user_files_require_replace(tmp_path, store):
    root = worker(tmp_path)
    (root / ".env").write_text("KEEP=unchanged\n")
    result = setup(root, store)
    assert result.returncode != 0
    assert (root / ".env").read_text() == "KEEP=unchanged\n"
    assert setup(root, store, "--replace").returncode == 0
    external = tmp_path / "external"
    external.write_text("untouched")
    (root / "web/.env.local").unlink()
    (root / "web/.env.local").symlink_to(external)
    before = (root / ".env").read_bytes()
    assert setup(root, store).returncode != 0
    assert (root / ".env").read_bytes() == before
    assert external.read_text() == "untouched"


def test_local_command_never_reads_hosted_secrets_or_calls_client(
    monkeypatch, tmp_path, store
):
    root = worker(tmp_path)
    monkeypatch.setenv("CUADRAO_LOCAL_ENV_STORE", str(store))

    def forbidden(*args):
        raise AssertionError("hosted path reached")

    monkeypatch.setattr(se, "read_secrets", forbidden)
    monkeypatch.setattr(se, "_client", forbidden)
    assert se.run(["local", str(root)]) == 0


@pytest.mark.parametrize(
    "target",
    [
        "https://localhost.evil.test",
        "https://evil.test/localhost",
        "https://evil.test/approved",
        "https://approved.supabase.co.evil.test",
        "postgresql://postgres.wrong:key@aws-0.pooler.supabase.com:5432/postgres",
    ],
)
def test_target_guard_rejects_substring_and_wrong_pooler_tenant(
    tmp_path, target, monkeypatch
):
    root = worker(tmp_path)
    (root / ".env").write_text(f"SUPABASE_PROJECT_URL={target}\n")
    (root / "web/.env.local").write_text("NEXT_PUBLIC_MOCK_AUTH=false\n")
    monkeypatch.setenv("ARGUS_QA_APPROVED_SUPABASE_REF", "approved")
    with pytest.raises(se.ManifestError, match="unapproved target"):
        se.guard_local(root, se.load_manifest())


@pytest.mark.parametrize(
    "target",
    [
        "http://localhost:54321",
        "https://approved.supabase.co",
        "postgresql://postgres.approved:key@aws-0.pooler.supabase.com:5432/postgres",
    ],
)
def test_target_guard_accepts_exact_local_or_approved_hosts(
    tmp_path, target, monkeypatch
):
    root = worker(tmp_path)
    (root / ".env").write_text(f'SUPABASE_PROJECT_URL="{target}"\n')
    (root / "web/.env.local").write_text("NEXT_PUBLIC_MOCK_AUTH=false\n")
    monkeypatch.setenv("ARGUS_QA_APPROVED_SUPABASE_REF", "approved")
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    se.guard_local(root, se.load_manifest())


def test_target_guard_checks_inherited_database_target(tmp_path, monkeypatch):
    root = worker(tmp_path)
    (root / ".env").write_text("SUPABASE_URL=http://localhost:54321\n")
    (root / "web/.env.local").write_text("NEXT_PUBLIC_MOCK_AUTH=false\n")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@evil.test/db")
    with pytest.raises(se.ManifestError, match="DATABASE_URL"):
        se.guard_local(root, se.load_manifest())


@pytest.mark.parametrize("name", ["CUADRAO_APP_ORIGIN", "ARGUS_APP_ORIGIN"])
def test_local_manifest_accepts_server_app_origin(name):
    manifest = json.loads((ROOT / "scripts/ops/staging_env_manifest.json").read_text())
    entry = next(
        entry
        for entry in manifest["services"]["web"]["entries"]
        if entry["name"] == "CUADRAO_APP_ORIGIN"
    )
    entry["name"] = name
    se.validate_manifest(manifest)


@pytest.mark.parametrize("name", ["CUADRAO_APP_ORIGIN", "ARGUS_APP_ORIGIN"])
@pytest.mark.parametrize("source", ["inherited", ".env", "web/.env.local"])
@pytest.mark.parametrize("local", [True, False])
def test_target_guard_checks_both_app_origin_names(
    tmp_path, monkeypatch, name, source, local
):
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    root = worker(tmp_path)
    (root / ".env").write_text("SUPABASE_URL=http://localhost:54321\n")
    (root / "web/.env.local").write_text("NEXT_PUBLIC_MOCK_AUTH=false\n")
    target = "http://localhost:3000" if local else "https://outside.example.test"
    if source == "inherited":
        monkeypatch.setenv(name, target)
    else:
        path = root / source
        path.write_text(path.read_text() + f"{name}={target}\n")
    manifest = json.loads((ROOT / "scripts/ops/staging_env_manifest.json").read_text())
    if local:
        se.guard_local(root, manifest)
    else:
        with pytest.raises(se.ManifestError, match=f"{name}: unapproved target"):
            se.guard_local(root, manifest)


def test_local_manifest_rejects_server_source_for_browser(values):
    manifest = se.load_manifest()
    entry = next(
        e
        for e in manifest["services"]["web"]["entries"]
        if e["name"] == "NEXT_PUBLIC_SUPABASE_ANON_KEY"
    )
    entry["local"]["copy_from"] = "SUPABASE_SERVICE_ROLE_KEY"
    with pytest.raises(se.ManifestError, match="unsafe or missing local source"):
        se.validate_manifest(manifest)


def test_partial_install_failure_restores_previous_pair_privately(tmp_path, monkeypatch):
    root = worker(tmp_path)
    for relative in (".env", "web/.env.local"):
        (root / relative).write_text("PREVIOUS=unchanged\n")
    original_replace = se.os.replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("do-not-echo-this")
        original_replace(source, destination)

    monkeypatch.setattr(se.os, "replace", fail_second)
    with pytest.raises(se.ManifestError, match="prior files restored"):
        se.write_local(root, se.LocalEnvironment({"NEW": "api"}, {"NEW": "web"}), True)
    for relative in (".env", "web/.env.local"):
        assert (root / relative).read_text() == "PREVIOUS=unchanged\n"
    assert not list((root / "temp").iterdir())


def test_symlink_parent_is_rejected_before_any_write(tmp_path, store):
    root = worker(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    (root / "web/node_modules").unlink()
    (root / "web").rmdir()
    (root / "web").symlink_to(external, target_is_directory=True)
    result = setup(root, store)
    assert result.returncode != 0
    assert not (root / ".env").exists()
    assert not list(external.iterdir())


@pytest.mark.parametrize("script", ["dev.sh", "qa.sh", "local-smoke.sh"])
def test_entrypoints_honor_invalid_store_before_running_process(tmp_path, script):
    import shutil

    root = worker(tmp_path)
    for name in (
        f".github/{script}",
        ".github/argus-env.sh",
        "scripts/ops/staging_env.py",
        "scripts/ops/staging_env_manifest.json",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    (root / ".env").write_text("KEEP=unchanged\n")
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "CUADRAO_LOCAL_ENV_STORE": str(tmp_path / "missing.env"),
    }
    command = ["bash", str(root / ".github" / script)]
    if script == "local-smoke.sh":
        command.append("--contract-only")
    result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "CUADRAO_LOCAL_ENV_STORE" in result.stderr
    assert (root / ".env").read_text() == "KEEP=unchanged\n"


@pytest.mark.parametrize("selected", [False, True])
def test_dev_entrypoint_runs_without_integration_and_mode_flags_win(
    tmp_path, store, selected
):
    import shutil

    root = worker(tmp_path)
    for name in (
        ".github/dev.sh",
        ".github/argus-env.sh",
        "scripts/ops/staging_env.py",
        "scripts/ops/staging_env_manifest.json",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    binary = root / "bin"
    binary.mkdir()
    poetry = binary / "poetry"
    poetry.write_text(
        '#!/bin/bash\nprintf "%s %s %s %s\\n" "$CUADRAO_PERSISTENCE_MODE" "$CUADRAO_MOCK_AUTH" "${DATABASE_URL:-unset}" "${APP_ENV:-missing}" > "$CAPTURE"\n'
    )
    poetry.chmod(0o755)
    capture = root / "capture"
    env = {
        "PATH": f"{binary}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "DATABASE_URL": "inherited",
        "CUADRAO_MOCK_AUTH": "false",
        "CAPTURE": str(capture),
    }
    if selected:
        env["CUADRAO_LOCAL_ENV_STORE"] = str(store)
    result = subprocess.run(
        ["bash", str(root / ".github/dev.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert capture.read_text().strip() == "memory true unset local"


def test_regular_root_env_still_overrides_process_then_mode_wins(tmp_path):
    root = worker(tmp_path)
    (root / ".env").write_text("OPENROUTER_API_KEY=file-value\nCUADRAO_MOCK_AUTH=false\n")
    env = {"PATH": os.environ["PATH"], "OPENROUTER_API_KEY": "inherited"}
    command = f'source "{ROOT}/.github/argus-env.sh"; argus_load_root_env; argus_export_dev_mode; printf "%s %s" "$OPENROUTER_API_KEY" "$CUADRAO_MOCK_AUTH"'
    result = subprocess.run(
        ["bash", "-c", command], cwd=root, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout == "file-value true"


@pytest.mark.parametrize("source", ["inside", "traversal", "other-worktree"])
def test_store_cannot_be_any_checkout_env_before_it_is_read(tmp_path, values, source):
    root = worker(tmp_path)
    other = worker(tmp_path, "other") if source == "other-worktree" else root
    path = other / ".env"
    path.write_text("SHOULD_NOT_BE_READ=sentinel\n")
    path.chmod(0o600)
    if source == "traversal":
        external = tmp_path / "external"
        external.mkdir()
        path = external / ".." / root.name / ".env"
    result = setup(root, path)
    assert result.returncode != 0
    assert "outside all git worktrees" in result.stderr
    assert "SHOULD_NOT_BE_READ" not in result.stderr
    assert "sentinel" not in result.stderr


def test_qa_entrypoint_uses_selected_store_with_stub_processes(tmp_path, store):
    import shutil

    root = worker(tmp_path)
    for name in (
        ".github/qa.sh",
        ".github/argus-env.sh",
        "scripts/qa/assert-nonprod-target.sh",
        "scripts/ops/staging_env.py",
        "scripts/ops/staging_env_manifest.json",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    binary = root / "bin"
    binary.mkdir()
    poetry = binary / "poetry"
    poetry.write_text(
        '#!/bin/bash\nprintf "%s %s %s\\n" "$CUADRAO_PERSISTENCE_MODE" "$CUADRAO_CHECKPOINTER_MODE" "$CUADRAO_MOCK_AUTH" >> "$CAPTURE"\n'
    )
    poetry.chmod(0o755)
    capture = root / "capture"
    env = {
        "PATH": f"{binary}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "CUADRAO_LOCAL_ENV_STORE": str(store),
        "CAPTURE": str(capture),
    }
    result = subprocess.run(
        ["bash", str(root / ".github/qa.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert capture.read_text().splitlines()
    assert set(capture.read_text().splitlines()) == {"supabase postgres false"}


def test_stack_discovery_uses_resolver_and_explicit_manifest_defaults(
    tmp_path, monkeypatch
):
    import io

    root = worker(tmp_path)
    monkeypatch.delenv("CUADRAO_LOCAL_ENV_STORE", raising=False)
    monkeypatch.setattr(
        se.sys,
        "stdin",
        io.StringIO(
            'API_URL="http://localhost:54321"\nANON_KEY="public-anon"\nSERVICE_ROLE_KEY="server-secret"\nJWT_SECRET="jwt-secret"\nDB_URL="postgresql://test:test@localhost:54322/test"\n'
        ),
    )
    assert se.run(["local", str(root), "--stack"]) == 0
    backend = (root / ".env").read_text()
    browser = (root / "web/.env.local").read_text()
    assert "OPENROUTER_API_KEY=local-qa-disabled" in backend
    assert "NEXT_PUBLIC_MOCK_AUTH=false" in browser
    assert "server-secret" not in browser


def test_target_guard_preserves_root_override_of_inherited_backend_url(
    tmp_path, monkeypatch
):
    root = worker(tmp_path)
    (root / ".env").write_text("SUPABASE_URL=http://localhost:54321\n")
    (root / "web/.env.local").write_text("NEXT_PUBLIC_MOCK_AUTH=false\n")
    monkeypatch.setenv("SUPABASE_URL", "https://unapproved.supabase.co")
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    se.guard_local(root, se.load_manifest())


@pytest.mark.parametrize(
    "key",
    [
        synthetic_jwt("service_role"),
        synthetic_jwt("authenticated"),
        "eyJ.invalid.token",
        "sb_secret_synthetic_privileged",
    ],
)
def test_browser_rejects_non_anonymous_jwt_before_write(tmp_path, store, key):
    root = worker(tmp_path)
    store.write_text(store.read_text().replace(PUBLIC_ANON, key))
    result = setup(root, store)
    assert result.returncode != 0
    assert "NEXT_PUBLIC_SUPABASE_ANON_KEY" in result.stderr
    assert key not in result.stdout + result.stderr
    assert not (root / ".env").exists()


def test_stack_writer_guard_does_not_regenerate_selected_store(tmp_path, store):
    import shutil

    root = worker(tmp_path)
    for name in (
        "scripts/qa/write-local-env.sh",
        "scripts/qa/assert-nonprod-target.sh",
        "scripts/ops/staging_env.py",
        "scripts/ops/staging_env_manifest.json",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    binary = root / "bin"
    binary.mkdir()
    discovery = binary / "supabase"
    discovery.write_text(
        "#!/bin/sh\ncat <<'EOF'\nAPI_URL=\"http://localhost:54331\"\n"
        'ANON_KEY="stack-anon"\nSERVICE_ROLE_KEY="stack-service"\n'
        'JWT_SECRET="stack-jwt"\nDB_URL="postgresql://test:test@localhost:54332/test"\nEOF\n'
    )
    discovery.chmod(0o755)
    result = subprocess.run(
        ["bash", str(root / "scripts/qa/write-local-env.sh")],
        cwd=root,
        env={
            "PATH": f"{binary}:{os.environ['PATH']}",
            "CUADRAO_LOCAL_ENV_STORE": str(store),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "SUPABASE_PROJECT_URL=http://localhost:54331" in (root / ".env").read_text()
    assert (
        "NEXT_PUBLIC_SUPABASE_ANON_KEY=stack-anon"
        in (root / "web/.env.local").read_text()
    )


@pytest.mark.parametrize(
    "secret", ["server-service-secret", synthetic_jwt("service_role")]
)
def test_guard_rejects_inherited_browser_secret(tmp_path, store, monkeypatch, secret):
    root = worker(tmp_path)
    assert setup(root, store).returncode == 0
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", secret)
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    with pytest.raises(se.ManifestError, match="NEXT_PUBLIC_SUPABASE_ANON_KEY"):
        se.guard_local(root, se.load_manifest())


def test_setup_rejects_inherited_browser_secret_before_writes(
    tmp_path, store, monkeypatch
):
    root = worker(tmp_path)
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "server-service-secret")
    result = setup(root, store)
    assert result.returncode != 0
    assert "NEXT_PUBLIC_SUPABASE_ANON_KEY" in result.stderr
    assert "server-service-secret" not in result.stderr
    assert not (root / ".env").exists()


def test_target_guard_preserves_existing_file_aliases_and_comments(tmp_path, monkeypatch):
    root = worker(tmp_path)
    (root / ".env").write_text(
        'export SUPABASE_PROJECT_URL="http://localhost:54321" # local stack\n'
        "SUPABASE_URL=${SUPABASE_PROJECT_URL}\n"
        'SUPABASE_SERVICE_ROLE_KEY="synthetic # server value"\n'
    )
    (root / "web/.env.local").write_text(
        "NEXT_PUBLIC_SUPABASE_URL=${SUPABASE_URL} # from root environment\n"
        'NEXT_PUBLIC_MOCK_AUTH="false" # real auth\n'
    )
    monkeypatch.setenv("SUPABASE_PROJECT_URL", "https://unapproved.supabase.co")
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    se.guard_local(root, se.load_manifest())


def test_target_guard_checks_inherited_secret_with_quoted_file_value(
    tmp_path, monkeypatch
):
    root = worker(tmp_path)
    (root / ".env").write_text('SUPABASE_SERVICE_ROLE_KEY="synthetic # server value"\n')
    (root / "web/.env.local").write_text("NEXT_PUBLIC_MOCK_AUTH=false\n")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "synthetic # server value")
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    with pytest.raises(se.ManifestError, match="NEXT_PUBLIC_SUPABASE_ANON_KEY"):
        se.guard_local(root, se.load_manifest())


@pytest.mark.parametrize(
    ("assignment", "secret"),
    [
        ("opaque-value#comment", "opaque-value"),
        ("opaque-value # inline comment", "opaque-value"),
        ('"opaque#value" # comment', "opaque#value"),
        ("'opaque#value'", "opaque#value"),
        ('"opaque value"', "opaque value"),
        ("${SUPABASE_SERVICE_ROLE_KEY}", "opaque-value"),
    ],
)
@pytest.mark.parametrize("prefix", ["", "export "])
def test_browser_guard_uses_next_env_syntax(
    tmp_path, monkeypatch, assignment, secret, prefix
):
    root = worker(tmp_path)
    (root / ".env").write_text(f"SUPABASE_SERVICE_ROLE_KEY='{secret}'\n")
    (root / "web/.env.local").write_text(
        f"{prefix}NEXT_PUBLIC_SUPABASE_ANON_KEY={assignment}\n"
        "NEXT_PUBLIC_MOCK_AUTH=false\n"
    )
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    with pytest.raises(se.ManifestError, match="NEXT_PUBLIC_SUPABASE_ANON_KEY"):
        se.guard_local(root, se.load_manifest())


def test_browser_guard_checks_next_environment_file_precedence(tmp_path, monkeypatch):
    root = worker(tmp_path)
    (root / ".env").write_text("SUPABASE_SERVICE_ROLE_KEY=opaque-value\n")
    (root / "web/.env.local").write_text(
        "NEXT_PUBLIC_SUPABASE_ANON_KEY=public-value\nNEXT_PUBLIC_MOCK_AUTH=false\n"
    )
    (root / "web/.env.production.local").write_text(
        "NEXT_PUBLIC_SUPABASE_ANON_KEY=opaque-value#comment\n"
    )
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", raising=False)
    with pytest.raises(se.ManifestError, match="NEXT_PUBLIC_SUPABASE_ANON_KEY"):
        se.guard_local(root, se.load_manifest())


@pytest.fixture
def discovered_stack(tmp_path, store):
    root = worker(tmp_path)
    for name in (
        ".github/argus-env.sh",
        ".github/qa.sh",
        ".github/dev.sh",
        ".github/local-smoke.sh",
        ".github/warmup-render.sh",
        ".github/render-env-sync.sh",
        ".github/setup-worktree-env.sh",
        "scripts/qa/run-local-auth-qa.sh",
        "scripts/qa/run-guest-experience-qa.sh",
        "scripts/qa/write-local-env.sh",
        "scripts/qa/assert-nonprod-target.sh",
        "scripts/ops/staging_env.py",
        "scripts/ops/staging_env_manifest.json",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    binary = root / "bin"
    binary.mkdir()
    discovery = binary / "supabase"
    discovery.write_text(
        "#!/bin/sh\ncat <<'EOF'\nAPI_URL=\"http://localhost:54331\"\n"
        'ANON_KEY="stack-anon"\nSERVICE_ROLE_KEY="stack-service"\n'
        'JWT_SECRET="stack-jwt"\nDB_URL="postgresql://test:test@localhost:54332/test"\nEOF\n'
    )
    discovery.chmod(0o755)
    for name in ("poetry", "curl", "bun", "bunx", "sleep"):
        stub = binary / name
        stub.write_text('#!/bin/sh\nprintf "called\\n" >> "$CAPTURE"\nexit 79\n')
        stub.chmod(0o755)
    env = {
        "PATH": f"{binary}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "CUADRAO_LOCAL_ENV_STORE": str(store),
        "ARGUS_QA_APPROVED_SUPABASE_REF": "syntheticproject",
        "CAPTURE": str(root / "launched"),
    }
    result = subprocess.run(
        ["bash", "scripts/qa/write-local-env.sh"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return root, env


@pytest.mark.parametrize("store_target", ["other-local", "hosted"])
@pytest.mark.parametrize(
    "caller",
    [
        "loader",
        "guest",
        "qa",
        "auth",
        "dev",
        "smoke",
        "warmup",
        "sync",
        "setup",
        "replace",
        "check",
        "cli",
    ],
)
def test_regeneration_refuses_to_switch_discovered_stack(
    discovered_stack, store, caller, store_target
):
    root, env = discovered_stack
    if store_target == "hosted":
        store.write_text(
            store.read_text()
            .replace("http://127.0.0.1:54321", "https://syntheticproject.supabase.co")
            .replace(
                "postgresql://test:test@localhost:54322/test",
                "postgresql://test:test@db.syntheticproject.supabase.co:5432/test",
            )
        )
    if caller == "guest":
        with (root / ".gitignore").open("a") as handle:
            handle.write("bin/\nweb/node_modules\n")
        (root / "supabase").mkdir()
        (root / "supabase/config.toml").write_text('project_id = "argus-qa"\n')
        docker = root / "bin/docker"
        docker.write_text("#!/bin/sh\nprintf 'argus-qa|true\\n'\n")
        docker.chmod(0o755)
        subprocess.run(
            ["git", "add", ".gitignore", ".github", "scripts", "supabase"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Synthetic Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
            cwd=root,
            check=True,
        )
    commands = {
        "guest": ["bash", "scripts/qa/run-guest-experience-qa.sh", "preflight"],
        "loader": ["bash", "-c", "source .github/argus-env.sh; argus_load_root_env"],
        "qa": ["bash", ".github/qa.sh"],
        "auth": ["bash", "scripts/qa/run-local-auth-qa.sh"],
        "dev": ["bash", ".github/dev.sh"],
        "smoke": ["bash", ".github/local-smoke.sh", "--contract-only"],
        "warmup": ["bash", ".github/warmup-render.sh", "--help"],
        "sync": ["bash", ".github/render-env-sync.sh", "--help"],
        "setup": ["bash", ".github/setup-worktree-env.sh", str(root)],
        "replace": ["bash", ".github/setup-worktree-env.sh", "--replace", str(root)],
        "check": ["bash", ".github/setup-worktree-env.sh", "--check", str(root)],
        "cli": ["python3", "scripts/ops/staging_env.py", "local", str(root)],
    }
    paths = [root / ".env", root / "web/.env.local"]
    before = [path.read_bytes() for path in paths]
    result = subprocess.run(
        commands[caller], cwd=root, env=env, capture_output=True, text=True, timeout=15
    )
    assert [path.read_bytes() for path in paths] == before
    assert result.returncode != 0
    assert "target" in result.stderr and "conflict" in result.stderr
    assert not (root / "launched").exists()
    for value in ("stack-service", "stack-jwt", "server-service-secret"):
        assert value not in result.stdout + result.stderr


@pytest.fixture
def matching_stack_store(discovered_stack, store):
    root, env = discovered_stack
    current = dict(line.split("=", 1) for line in store.read_text().splitlines())
    current.update(
        {
            "SUPABASE_PROJECT_URL": "http://localhost:54331",
            "SUPABASE_POSTGRES_SESSION_POOLER_URL": "postgresql://test:test@localhost:54332/test",
            "SUPABASE_ANON_PUBLIC_KEY": "stack-anon",
            "SUPABASE_SERVICE_ROLE_KEY": "stack-service",
            "SUPABASE_JWT_SECRET": "stack-jwt",
        }
    )
    store.write_text("".join(f"{name}={value}\n" for name, value in current.items()))
    return root, env


@pytest.mark.parametrize(
    ("name", "replacement"),
    [
        ("SUPABASE_PROJECT_URL", "http://localhost:54321"),
        (
            "SUPABASE_POSTGRES_SESSION_POOLER_URL",
            "postgresql://test:test@localhost:54322/test",
        ),
        ("SUPABASE_ANON_PUBLIC_KEY", "other-stack-credential"),
        ("SUPABASE_SERVICE_ROLE_KEY", "other-stack-credential"),
        ("SUPABASE_JWT_SECRET", "other-stack-credential"),
    ],
)
def test_regeneration_refuses_any_other_stack_field(
    matching_stack_store, store, name, replacement
):
    root, env = matching_stack_store
    values = dict(line.split("=", 1) for line in store.read_text().splitlines())
    values[name] = replacement
    store.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    paths = [root / ".env", root / "web/.env.local"]
    before = [path.read_bytes() for path in paths]
    result = setup(root, store)
    assert result.returncode != 0
    assert name in result.stderr
    assert "other-stack-credential" not in result.stdout + result.stderr
    assert [path.read_bytes() for path in paths] == before


def test_same_stack_allows_provider_refresh_and_idempotent_reload(
    matching_stack_store, store
):
    root, env = matching_stack_store
    browser = (root / "web/.env.local").read_bytes()
    store.write_text(
        store.read_text().replace(
            "OPENROUTER_API_KEY=synthetic-value",
            "OPENROUTER_API_KEY=refreshed-provider-key",
        )
    )
    assert setup(root, store, "--check").returncode == 0
    assert "refreshed-provider-key" not in (root / ".env").read_text()
    assert setup(root, store).returncode == 0
    backend = (root / ".env").read_bytes()
    assert b"OPENROUTER_API_KEY=refreshed-provider-key" in backend
    assert b"SUPABASE_PROJECT_URL=http://localhost:54331" in backend
    result = subprocess.run(
        ["bash", "-c", "source .github/argus-env.sh; argus_load_root_env"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (root / ".env").read_bytes() == backend
    assert (root / "web/.env.local").read_bytes() == browser


def test_explicit_rediscovery_replaces_whole_stack_group(discovered_stack):
    root, env = discovered_stack
    discovery = root / "bin/supabase"
    discovery.write_text(
        discovery.read_text()
        .replace("54331", "54341")
        .replace("54332", "54342")
        .replace("stack-anon", "new-stack-anon")
        .replace("stack-service", "new-stack-service")
        .replace("stack-jwt", "new-stack-jwt")
    )
    result = subprocess.run(
        ["bash", "scripts/qa/write-local-env.sh"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    backend = (root / ".env").read_text()
    browser = (root / "web/.env.local").read_text()
    assert "SUPABASE_PROJECT_URL=http://localhost:54341" in backend
    assert (
        "SUPABASE_POSTGRES_SESSION_POOLER_URL=postgresql://test:test@localhost:54342/test"
        in backend
    )
    assert "SUPABASE_ANON_PUBLIC_KEY=new-stack-anon" in backend
    assert "SUPABASE_SERVICE_ROLE_KEY=new-stack-service" in backend
    assert "SUPABASE_JWT_SECRET=new-stack-jwt" in backend
    assert "NEXT_PUBLIC_SUPABASE_URL=http://localhost:54341" in browser
    assert "NEXT_PUBLIC_SUPABASE_ANON_KEY=new-stack-anon" in browser


def test_orphan_browser_cannot_be_retargeted_from_store(discovered_stack, store):
    root, _ = discovered_stack
    browser = (root / "web/.env.local").read_bytes()
    (root / ".env").unlink()
    result = setup(root, store)
    assert result.returncode != 0
    assert "target" in result.stderr and "conflict" in result.stderr
    assert not (root / ".env").exists()
    assert (root / "web/.env.local").read_bytes() == browser


@pytest.mark.parametrize(
    ("relative", "alias"),
    [(".env", "SUPABASE_URL"), ("web/.env.local", "NEXT_PUBLIC_SUPABASE_URL")],
)
def test_regeneration_refuses_conflicting_target_alias(
    matching_stack_store, store, relative, alias
):
    root, _ = matching_stack_store
    path = root / relative
    path.write_text(
        path.read_text().replace(
            f"{alias}=http://localhost:54331", f"{alias}=http://localhost:54341"
        )
    )
    before = [(root / name).read_bytes() for name in (".env", "web/.env.local")]
    result = setup(root, store)
    assert result.returncode != 0
    assert alias in result.stderr
    assert [(root / name).read_bytes() for name in (".env", "web/.env.local")] == before
