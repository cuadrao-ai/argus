from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITE_LOCAL_ENV = ROOT / "scripts" / "qa" / "write-local-env.sh"
ASSERT_NONPROD = ROOT / "scripts" / "qa" / "assert-nonprod-target.sh"


def test_local_qa_env_writer_does_not_overwrite_shared_symlink_targets(
    tmp_path: Path,
) -> None:
    worker = tmp_path / "worker"
    scripts = worker / "scripts" / "qa"
    scripts.mkdir(parents=True)
    (worker / "web").mkdir()
    shutil.copy2(WRITE_LOCAL_ENV, scripts / WRITE_LOCAL_ENV.name)
    shutil.copy2(ASSERT_NONPROD, scripts / ASSERT_NONPROD.name)

    operations = worker / "scripts/ops"
    operations.mkdir()
    for name in ("staging_env.py", "staging_env_manifest.json"):
        shutil.copy2(ROOT / "scripts/ops" / name, operations / name)

    canonical_backend = tmp_path / "canonical.env"
    canonical_frontend = tmp_path / "canonical.web.env"
    canonical_backend.write_text("CANONICAL_BACKEND=unchanged\n", encoding="utf-8")
    canonical_frontend.write_text(
        "CANONICAL_FRONTEND=unchanged\n",
        encoding="utf-8",
    )
    (worker / ".env").symlink_to(canonical_backend)
    (worker / "web" / ".env.local").symlink_to(canonical_frontend)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_supabase = fake_bin / "supabase"
    fake_supabase.write_text(
        """#!/bin/bash
cat <<'EOF'
API_URL="http://127.0.0.1:54321"
ANON_KEY="local-anon"
SERVICE_ROLE_KEY="local-service"
DB_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"
JWT_SECRET="local-jwt"
EOF
""",
        encoding="utf-8",
    )
    fake_supabase.chmod(fake_supabase.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env.pop("CUADRAO_LOCAL_ENV_STORE", None)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        ["bash", str(scripts / WRITE_LOCAL_ENV.name)],
        cwd=worker,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "symlink refused" in result.stdout + result.stderr
    assert canonical_backend.read_text(encoding="utf-8") == (
        "CANONICAL_BACKEND=unchanged\n"
    )
    assert canonical_frontend.read_text(encoding="utf-8") == (
        "CANONICAL_FRONTEND=unchanged\n"
    )
    assert (worker / ".env").is_symlink()
    assert (worker / "web" / ".env.local").is_symlink()
