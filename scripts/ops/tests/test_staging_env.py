from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import scripts.ops.staging_env as se

AUDIT_API = """APP_ENV ARGUS_BUSINESS_PILOT_ENABLED ARGUS_CHECKPOINTER_MODE ARGUS_DEV_MEMORY_FALLBACK
ARGUS_DOCUMENT_EXTRACTION_ENABLED ARGUS_FINANCIAL_ACCOUNTS_ENABLED ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY
ARGUS_INGESTION_ENABLED ARGUS_MOCK_AUTH ARGUS_PERSISTENCE_MODE ARGUS_PROD_OPENROUTER_API_KEY ARGUS_VISION_MODEL
CUADRAO_APP_ORIGIN CUADRAO_BUSINESS_EMAIL_CAPTURE_ENABLED CUADRAO_BUSINESS_EMAIL_DOMAIN
CUADRAO_BUSINESS_EMAIL_INTAKE_ENABLED CUADRAO_BUSINESS_PILOT_ENABLED CUADRAO_DOCUMENT_EXTRACTION_ENABLED
CUADRAO_INGESTION_ENABLED CUADRAO_VISION_MODEL CUADRAO_WHATSAPP_DISPLAY_PHONE_NUMBER
CUADRAO_WHATSAPP_INTAKE_ENABLED CUADRAO_WHATSAPP_NUMBER_ID CUADRAO_WHATSAPP_OUTBOUND_ENABLED
CUADRAO-DEV-KEY-PILOT DATABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY SUPABASE_URL""".split()
AUDIT_WEB = """CUADRAO_RESEND_WEBHOOK_SECRET NEXT_PUBLIC_ARGUS_API_URL NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY
NEXT_PUBLIC_BUSINESS_PILOT_ENABLED NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY NEXT_PUBLIC_ENABLE_SPANISH
NEXT_PUBLIC_SUPABASE_ANON_KEY NEXT_PUBLIC_SUPABASE_URL""".split()

SECRET_VALUES = [
    "sk-live-AAAA1111",
    "wa-app-secret-BBBB2222",
    "supa-service-CCCC3333",
    "resend-DDDD4444",
]


class FakeClient:
    def __init__(
        self, live: dict[str, dict[str, str]], names: dict[str, str] | None = None
    ):
        self.live = live
        self.names = names or {}
        self.puts: list[tuple[str, dict[str, str]]] = []

    def service_name(self, service_id):
        return self.names.get(
            service_id,
            "cuadrao-api-staging" if "mrr" in service_id else "cuadrao-web-staging",
        )

    def list_env(self, service_id):
        return dict(self.live[service_id])

    def put_env(self, service_id, env):
        self.puts.append((service_id, dict(env)))


@pytest.fixture
def manifest():
    return se.load_manifest()


def live_for(manifest, label, audit):
    live = {n: f"live-{i}" for i, n in enumerate(audit)}
    if label == "web":
        live["NEXT_PUBLIC_ARGUS_API_URL"] = (
            "https://cuadrao-api-staging.onrender.com/api/v1"
        )
    if label == "api":
        live["ARGUS_PROD_OPENROUTER_API_KEY"] = SECRET_VALUES[0]
        live["ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY"] = "guest-different-EEEE5555"
        live["SUPABASE_SERVICE_ROLE_KEY"] = SECRET_VALUES[2]
    return live


def test_every_audited_name_is_classified(manifest):
    for label, audit in (("api", AUDIT_API), ("web", AUDIT_WEB)):
        svc = manifest["services"][label]
        classified = (
            {e["name"] for e in svc["entries"]}
            | {r["name"] for r in svc["remove"]}
            | {h["name"] for h in svc["hold"]}
        )
        assert set(audit) <= classified


def test_manifest_holds_no_secret_value(manifest):
    text = json.dumps(manifest)
    assert not re.search(r"://[^/\s\"]*:[^@\s\"]*@|sk-|eyJ", text)
    for svc in manifest["services"].values():
        for e in svc["entries"]:
            if e["kind"] != "plain":
                assert "value" not in e


def test_validation_rejects_secret_with_plain_value(manifest):
    manifest["services"]["api"]["entries"].append(
        {"name": "SOME_API_KEY", "kind": "plain", "value": "abc"}
    )
    with pytest.raises(se.ManifestError):
        se.validate_manifest(manifest)


def test_validation_rejects_value_on_secret_kind(manifest):
    manifest["services"]["api"]["entries"].append(
        {"name": "X_SECRET", "kind": "secret", "value": "abc"}
    )
    with pytest.raises(se.ManifestError):
        se.validate_manifest(manifest)


def test_plan_api_adds_deletes_and_holds(manifest):
    live = live_for(manifest, "api", AUDIT_API)
    plan = se.compute_plan(
        manifest["services"]["api"],
        live,
        {"CUADRAO_WHATSAPP_APP_SECRET": "x"},
        generator=lambda: "gen",
    )
    actions = dict(plan.actions)
    assert actions["CUADRAO_FINANCIAL_ACCOUNTS_ENABLED"] == "add"
    assert plan.final["CUADRAO_FINANCIAL_ACCOUNTS_ENABLED"] == "true"
    assert plan.final["ARGUS_HOUSEHOLDS_ENABLED"] == "true"
    assert dict(plan.actions)["ARGUS_INVITE_FOUNDER_USER_ID"] == "skip"
    assert len(plan.final["CUADRAO_INGESTION_SECRET_KEY"]) == 44
    assert actions["ARGUS_FINANCIAL_ACCOUNTS_ENABLED"] == "delete"
    assert actions["ARGUS_VISION_MODEL"] == "delete"
    assert actions["CUADRAO-DEV-KEY-PILOT"] == "hold"
    assert "CUADRAO-DEV-KEY-PILOT" in plan.final
    assert actions["CUADRAO_WHATSAPP_VERIFY_TOKEN"] == "add"
    assert {
        "CUADRAO_WHATSAPP_VERIFY_TOKEN",
        "CUADRAO_WHATSAPP_SENDER_KEY",
        "ARGUS_INVITE_CODE_SECRET",
    } <= plan.generated.keys()
    assert set(plan.missing) == {
        "CUADRAO_WHATSAPP_ACCESS_TOKEN",
        "CUADRAO_RESEND_WEBHOOK_SECRET",
        "RESEND_BUSINESS_API_KEY",
    }


def test_removal_blocked_when_twin_unset(manifest):
    live = live_for(manifest, "web", AUDIT_WEB)
    del live["NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY"]
    plan = se.compute_plan(manifest["services"]["web"], live, {})
    assert dict(plan.actions)["NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY"] == "blocked"
    assert "NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY" in plan.final
    assert plan.problems


def test_web_copies_api_url_then_deletes_old_name(manifest):
    live = live_for(manifest, "web", AUDIT_WEB)
    plan = se.compute_plan(manifest["services"]["web"], live, {})
    assert plan.final["NEXT_PUBLIC_CUADRAO_API_URL"] == live["NEXT_PUBLIC_ARGUS_API_URL"]
    assert "NEXT_PUBLIC_ARGUS_API_URL" not in plan.final
    assert "CUADRAO_RESEND_WEBHOOK_SECRET" not in plan.final


def test_distinct_openrouter_keys(manifest):
    live = live_for(manifest, "api", AUDIT_API)
    live["ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY"] = live["ARGUS_PROD_OPENROUTER_API_KEY"]
    plan = se.compute_plan(manifest["services"]["api"], live, {})
    assert any("must differ" in p for p in plan.problems)


def full_secrets():
    return {
        "CUADRAO_WHATSAPP_APP_SECRET": SECRET_VALUES[1],
        "CUADRAO_WHATSAPP_ACCESS_TOKEN": "wa-access-FFFF6666",
        "CUADRAO_RESEND_WEBHOOK_SECRET": "whsec-GGGG7777",
        "RESEND_BUSINESS_API_KEY": SECRET_VALUES[3],
        "CUADRAO_WHATSAPP_VERIFY_TOKEN": "verify-HHHH8888",
        "CUADRAO_WHATSAPP_SENDER_KEY": "sender-IIII9999",
    }


def write_secrets(path: Path, values: dict[str, str], mode=0o600):
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    path.chmod(mode)


def make_env(tmp_path, manifest):
    live = {
        "srv-db4mrrvlk1mc73d733j0": live_for(manifest, "api", AUDIT_API),
        "srv-db5ihr7lot8c73f3b3h0": live_for(manifest, "web", AUDIT_WEB),
    }
    return FakeClient(live), tmp_path / "secrets.env"


def test_apply_single_put_per_service_and_never_prints_values(
    manifest, tmp_path, capsys, monkeypatch
):
    monkeypatch.setenv("RENDER_API_KEY", "rnd_APIKEYVALUE")
    client, secrets_path = make_env(tmp_path, manifest)
    write_secrets(secrets_path, full_secrets())
    lines: list[str] = []
    code = se.run(
        ["--secrets-file", str(secrets_path), "apply", "--confirm"],
        client_factory=lambda k: client,
        out=lines.append,
    )
    assert code == 0
    assert [sid for sid, _ in client.puts] == [
        "srv-db4mrrvlk1mc73d733j0",
        "srv-db5ihr7lot8c73f3b3h0",
    ]
    api_env = client.puts[0][1]
    assert api_env["CUADRAO_RESEND_WEBHOOK_SECRET"] == "whsec-GGGG7777"
    assert "ARGUS_VISION_MODEL" not in api_env
    everything = "\n".join(lines) + capsys.readouterr().out + capsys.readouterr().err
    values = list(full_secrets().values()) + SECRET_VALUES + ["rnd_APIKEYVALUE"]
    values += [v for env in client.live.values() for v in env.values()]
    assert not [v for v in values if v in everything]
    assert "redeploy" in everything


def test_apply_second_run_is_noop(manifest, tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_API_KEY", "k")
    client, secrets_path = make_env(tmp_path, manifest)
    write_secrets(secrets_path, full_secrets())
    se.run(
        ["--secrets-file", str(secrets_path), "apply", "--confirm"],
        client_factory=lambda k: client,
        out=lambda s: None,
    )
    for sid, env in client.puts:
        client.live[sid] = env
    client.puts.clear()
    se.run(
        ["--secrets-file", str(secrets_path), "apply", "--confirm"],
        client_factory=lambda k: client,
        out=lambda s: None,
    )
    assert client.puts == []


def test_apply_refuses_when_secrets_missing(manifest, tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_API_KEY", "k")
    client, secrets_path = make_env(tmp_path, manifest)
    write_secrets(secrets_path, {})
    code = se.run(
        ["--secrets-file", str(secrets_path), "apply", "--confirm", "api"],
        client_factory=lambda k: client,
        out=lambda s: None,
    )
    assert code == 1 and client.puts == []


def test_dry_run_writes_nothing_and_does_not_create_secrets(
    manifest, tmp_path, monkeypatch
):
    monkeypatch.setenv("RENDER_API_KEY", "k")
    client, secrets_path = make_env(tmp_path, manifest)
    code = se.run(
        ["--secrets-file", str(secrets_path), "apply"],
        client_factory=lambda k: client,
        out=lambda s: None,
    )
    assert client.puts == [] and not secrets_path.exists()
    assert code == 1  # secrets still missing


def test_apply_without_confirm_never_writes(manifest, tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_API_KEY", "k")
    client, secrets_path = make_env(tmp_path, manifest)
    write_secrets(secrets_path, full_secrets())
    lines: list[str] = []
    code = se.run(
        ["--secrets-file", str(secrets_path), "apply"],
        client_factory=lambda k: client,
        out=lines.append,
    )
    assert code == 0 and client.puts == [] and any("--confirm" in line for line in lines)
    se.run(
        ["--secrets-file", str(secrets_path), "apply", "--confirm"],
        client_factory=lambda k: client,
        out=lambda s: None,
    )
    assert len(client.puts) == 2


def test_generated_values_are_created_once_and_kept(manifest, tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_API_KEY", "k")
    client, secrets_path = make_env(tmp_path, manifest)
    secrets = {
        k: v for k, v in full_secrets().items() if "VERIFY" not in k and "SENDER" not in k
    }
    write_secrets(secrets_path, secrets)
    se.run(
        ["--secrets-file", str(secrets_path), "apply", "--confirm", "api"],
        client_factory=lambda k: client,
        out=lambda s: None,
    )
    stored = se.read_secrets(secrets_path)
    assert (
        len(stored["CUADRAO_WHATSAPP_VERIFY_TOKEN"]) >= 43
        and len(stored["CUADRAO_WHATSAPP_SENDER_KEY"]) >= 43
    )
    sid, env = client.puts[0]
    assert env["CUADRAO_WHATSAPP_VERIFY_TOKEN"] == stored["CUADRAO_WHATSAPP_VERIFY_TOKEN"]
    before = dict(stored)
    client.live[sid] = env
    se.run(
        ["--secrets-file", str(secrets_path), "apply", "--confirm", "api"],
        client_factory=lambda k: client,
        out=lambda s: None,
    )
    assert se.read_secrets(secrets_path) == before


def test_apply_refuses_wrong_service_name(manifest, tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_API_KEY", "k")
    client, secrets_path = make_env(tmp_path, manifest)
    client.names["srv-db4mrrvlk1mc73d733j0"] = "argus-api-production"
    write_secrets(secrets_path, full_secrets())
    with pytest.raises(se.RenderError):
        se.run(
            ["--secrets-file", str(secrets_path), "apply", "--confirm", "api"],
            client_factory=lambda k: client,
            out=lambda s: None,
        )
    assert client.puts == []


def test_secrets_file_must_be_private(tmp_path):
    path = tmp_path / "s.env"
    write_secrets(path, {"A": "b"}, mode=0o644)
    with pytest.raises(se.ManifestError):
        se.read_secrets(path)


def test_check_exit_codes(manifest, tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_API_KEY", "k")
    client, secrets_path = make_env(tmp_path, manifest)
    live = client.live["srv-db4mrrvlk1mc73d733j0"]
    live.update({n: "v" for n in ("CUADRAO_FINANCIAL_ACCOUNTS_ENABLED", *full_secrets())})
    assert (
        se.run(
            ["--secrets-file", str(secrets_path), "check", "api"],
            client_factory=lambda k: client,
            out=lambda s: None,
        )
        == 0
    )
    client.live["srv-db4mrrvlk1mc73d733j0"].pop("APP_ENV")
    lines: list[str] = []
    code = se.run(
        ["--secrets-file", str(secrets_path), "check", "api"],
        client_factory=lambda k: client,
        out=lines.append,
    )
    assert code == 1 and any("MISSING  APP_ENV" in line for line in lines)


def test_http_error_masks_body(monkeypatch):
    class Resp:
        status_code = 400
        text = "echoed secret-value-ZZZ"

        def json(self):
            return {}

    client = se.HttpRenderClient.__new__(se.HttpRenderClient)
    client._http = type("H", (), {"request": lambda self, m, p, **k: Resp()})()
    with pytest.raises(se.RenderError) as err:
        client.put_env("srv-1", {"A": "secret-value-ZZZ"})
    assert "secret-value-ZZZ" not in str(err.value) and "400" in str(err.value)


def test_clipboard_goes_to_pbcopy_not_stdout(manifest, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RENDER_API_KEY", raising=False)
    write_path = tmp_path / "s.env"
    write_secrets(write_path, full_secrets())
    sent: list[bytes] = []
    monkeypatch.setattr(
        se.subprocess, "run", lambda cmd, input, check: sent.append(input) or None
    )
    assert se.run(["--secrets-file", str(write_path), "clipboard", "api"]) == 0
    block = sent[0].decode()
    assert "CUADRAO_WHATSAPP_APP_SECRET=" + SECRET_VALUES[1] in block
    assert "ARGUS_VISION_MODEL" not in block
    shown = capsys.readouterr().out
    assert not [v for v in full_secrets().values() if v in shown]


def test_show_verify_token_clipboard_only(manifest, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RENDER_API_KEY", raising=False)
    path = tmp_path / "s.env"
    sent: list[bytes] = []
    monkeypatch.setattr(
        se.subprocess, "run", lambda cmd, input, check: sent.append(input) or None
    )
    assert se.run(["--secrets-file", str(path), "show-verify-token"]) == 0
    token = se.read_secrets(path)["CUADRAO_WHATSAPP_VERIFY_TOKEN"]
    assert sent == [token.encode()]
    assert token not in capsys.readouterr().out
    assert path.stat().st_mode & 0o777 == 0o600


def manifest_file(tmp_path, mutate):
    data = json.loads(se.MANIFEST_PATH.read_text())
    mutate(data)
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data))
    return path


def test_unpinned_service_id_refused(tmp_path):
    path = manifest_file(
        tmp_path, lambda d: d["services"]["api"].update(service_id="srv-production-1")
    )
    with pytest.raises(se.ManifestError):
        se.load_manifest(path)


def test_no_manifest_flag_exists(tmp_path):
    with pytest.raises(SystemExit):
        se.run(["--manifest", str(tmp_path / "m.json"), "plan"])


def test_name_mismatch_refuses_before_any_read(manifest, tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_API_KEY", "k")
    client, secrets_path = make_env(tmp_path, manifest)
    client.names["srv-db4mrrvlk1mc73d733j0"] = "argus-api-production"
    reads: list[str] = []
    original = client.list_env
    client.list_env = lambda sid: reads.append(sid) or original(sid)
    for command in (["plan", "api"], ["check", "api"], ["apply", "--confirm", "api"]):
        with pytest.raises(se.RenderError):
            se.run(
                ["--secrets-file", str(secrets_path), *command],
                client_factory=lambda k: client,
                out=lambda s: None,
            )
    assert reads == [] and client.puts == []


def test_null_env_value_raises_instead_of_blanking():
    class Http:
        def request(self, method, path, **kwargs):
            class R:
                status_code = 200

                def json(self):
                    return [
                        {"envVar": {"key": "DATABASE_URL", "value": None}, "cursor": "c"}
                    ]

            return R()

    client = se.HttpRenderClient.__new__(se.HttpRenderClient)
    client._http = Http()
    with pytest.raises(se.RenderError) as err:
        client.list_env("srv-1")
    assert "DATABASE_URL" in str(err.value)


def test_secrets_file_inside_repo_refused():
    with pytest.raises(se.ManifestError):
        se.read_secrets(se.REPO_ROOT / "temp" / "secrets.env")


def test_cors_origin_in_manifest(manifest):
    entry = next(
        e
        for e in manifest["services"]["api"]["entries"]
        if e["name"] == "ARGUS_CORS_ALLOW_ORIGINS"
    )
    assert entry["value"] == "https://cuadrao-web-staging.onrender.com"


def test_households_wait_for_invite_secret(manifest):
    service = manifest["services"]["api"]
    for entry in service["entries"]:
        if entry["name"] == "ARGUS_INVITE_CODE_SECRET":
            entry["kind"] = "secret"
    live = live_for(manifest, "api", AUDIT_API)
    plan = se.compute_plan(service, live, {})
    actions = dict(plan.actions)
    assert (
        actions["ARGUS_HOUSEHOLDS_ENABLED"] == "blocked"
        and actions["ARGUS_BETA_INVITES_ENABLED"] == "blocked"
    )
    assert "ARGUS_HOUSEHOLDS_ENABLED" not in plan.final


def test_plan_and_dry_run_output_never_leak_values(
    manifest, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("RENDER_API_KEY", "rnd_APIKEYVALUE")
    client, secrets_path = make_env(tmp_path, manifest)
    write_secrets(secrets_path, full_secrets())
    secrets = (
        list(full_secrets().values())
        + SECRET_VALUES
        + ["rnd_APIKEYVALUE", "guest-different-EEEE5555"]
    )
    secrets += [v for env in client.live.values() for v in env.values()]
    for command in (["plan"], ["apply"], ["check"]):
        capsys.readouterr()
        se.run(
            ["--secrets-file", str(secrets_path), *command],
            client_factory=lambda k: client,
        )
        captured = capsys.readouterr()
        assert not [v for v in secrets if v in captured.out + captured.err]


@pytest.mark.parametrize(
    "bad",
    [
        "https://api.example.com./api/v1",
        "https://api.example.com",
        "https://api.example.com/api/v1/",
        "http://x.com/api/v1",
    ],
)
def test_malformed_api_base_url_is_rejected(manifest, bad):
    live = live_for(manifest, "web", AUDIT_WEB)
    live["NEXT_PUBLIC_ARGUS_API_URL"] = bad
    plan = se.compute_plan(manifest["services"]["web"], live, {})
    assert any("NEXT_PUBLIC_CUADRAO_API_URL must be" in p for p in plan.problems)
    manifest["services"]["web"]["entries"].append(
        {"name": "NEXT_PUBLIC_ARGUS_API_URL", "kind": "plain", "value": bad}
    )
    with pytest.raises(se.ManifestError):
        se.validate_manifest(manifest)


def test_good_api_base_url_passes(manifest):
    live = live_for(manifest, "web", AUDIT_WEB)
    live["NEXT_PUBLIC_ARGUS_API_URL"] = "https://cuadrao-api-staging.onrender.com/api/v1"
    plan = se.compute_plan(manifest["services"]["web"], live, {})
    assert plan.problems == []
