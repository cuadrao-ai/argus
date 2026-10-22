from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_staging_web_has_its_own_manual_integration_and_recovery_config():
    config = yaml.safe_load((ROOT / "render.yaml").read_text())
    stage = next(
        service
        for service in config["services"]
        if service["name"] == "cuadrao-web-staging"
    )
    assert stage["branch"] == "codex/private-alpha-next"
    assert stage["rootDir"] == "web"
    assert stage["autoDeployTrigger"] == "off"
    assert stage["buildCommand"] == "bun install --frozen-lockfile && bun run build"
    assert stage["startCommand"] == "bun run start -- -p $PORT"
    assert "envVarGroups" not in stage
    env = {entry["key"]: entry for entry in stage["envVars"]}
    assert env["ARGUS_APP_ORIGIN"]["value"] == "https://cuadrao-web-staging.onrender.com"
    assert (
        env["NEXT_PUBLIC_SUPABASE_URL"]["value"]
        == "https://skedzwocnmrhfigiwyzi.supabase.co"
    )
    assert env["NEXT_PUBLIC_MOCK_AUTH"]["value"] == "false"
    assert env["NEXT_PUBLIC_BUSINESS_PILOT_ENABLED"]["value"] == "true"
    assert env["NEXT_PUBLIC_SUPABASE_ANON_KEY"] == {
        "key": "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        "sync": False,
    }
    assert "lgdhvepyrzbnscqssgqq" not in str(stage)
    assert all("SERVICE_ROLE" not in entry["key"] for entry in stage["envVars"])
