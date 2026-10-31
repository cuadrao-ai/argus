"""Isolation guards for independently runnable native demonstrations."""

import io
import json
import stat
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import local_stack
import pytest
from local_stack import Allocation


@pytest.mark.parametrize(
    "accounts,project,state",
    [(False, "ios-auth-8be2", "auth-local"), (True, "ios-accounts", "accounts-local")],
)
def test_defaults_preserve_existing_stack(accounts, project, state):
    allocation = Allocation(accounts)
    assert allocation.project == project
    assert allocation.work.name == state
    assert allocation.url() == "http://127.0.0.1:58400"
    assert allocation.web_port == 3001


@pytest.mark.parametrize("base", [0, 1023, 65525, 70000])
def test_reject_invalid_port_ranges(base):
    with pytest.raises(ValueError):
        Allocation(True, base)


@pytest.fixture
def allocation(tmp_path, monkeypatch):
    monkeypatch.setattr(local_stack.socket, "socket", MagicMock())
    monkeypatch.setattr(local_stack, "ROOT", tmp_path)
    allocation = Allocation(True, 58500)
    monkeypatch.setattr(local_stack, "ALLOCATION", allocation)
    source = tmp_path / "supabase"
    source.mkdir()
    (source / "migrations").mkdir()
    (source / "seed.sql").write_text("")
    template = ['project_id = "original"']
    sections = {}
    for (section, key), port in allocation.ports.items():
        sections.setdefault(section, []).append(f"{key} = {port}")
    for section, values in sections.items():
        template += [f"[{section}]", *values]
    template += [
        "[auth]",
        'site_url = "http://localhost:3001"',
        "additional_redirect_urls = [",
        "]",
    ]
    (source / "config.toml").write_text("\n".join(template))
    local_stack.configure(accounts=True)
    return allocation


def test_configuration_keeps_project_state_and_ports_together(allocation):
    allocation.verify()
    assert allocation.project == "ios-accounts-58500"
    assert allocation.work.name == "accounts-local-58500"
    assert allocation.web_url == "http://127.0.0.1:58506"
    with pytest.raises(SystemExit, match="Configuration exists"):
        local_stack.configure(accounts=True)


@pytest.mark.parametrize(
    "old,new", [("ios-accounts-58500", "ios-accounts"), ("port = 58502", "port = 58402")]
)
def test_wrong_stack_is_rejected_before_cli_invocation(allocation, monkeypatch, old, new):
    config = allocation.stack / "supabase/config.toml"
    config.write_text(config.read_text().replace(old, new))
    monkeypatch.setattr(
        local_stack.subprocess, "run", lambda *a, **k: pytest.fail("CLI must not run")
    )
    with pytest.raises(SystemExit, match="mismatch"):
        local_stack.sb("stop")


@pytest.mark.parametrize(
    "api,database,accepted",
    [
        (
            "http://127.0.0.1:58501",
            "postgresql://user:secret@127.0.0.1:58502/postgres",
            True,
        ),
        (
            "https://example.invalid",
            "postgresql://user:secret@127.0.0.1:58502/postgres",
            False,
        ),
        (
            "http://127.0.0.1:58501",
            "postgresql://user:secret@127.0.0.1:58402/postgres",
            False,
        ),
        (
            "http://127.0.0.1:58501",
            "postgresql://user:secret@example.invalid:58502/postgres",
            False,
        ),
    ],
)
def test_status_accepts_only_owned_loopback_endpoints(
    allocation, monkeypatch, api, database, accepted
):
    result = {"API_URL": api, "DB_URL": database}
    monkeypatch.setattr(
        local_stack, "sb", lambda *a: SimpleNamespace(stdout=json.dumps(result))
    )
    if accepted:
        assert local_stack.status() == result
    else:
        with pytest.raises(SystemExit, match="non-lane"):
            local_stack.status()


def test_occupied_ports_do_not_create_configuration(tmp_path, monkeypatch):
    allocation = Allocation(True, 58500)
    monkeypatch.setattr(local_stack, "ROOT", tmp_path)
    monkeypatch.setattr(local_stack, "ALLOCATION", allocation)
    socket = MagicMock()
    socket.return_value.__enter__.return_value.bind.side_effect = OSError("occupied")
    monkeypatch.setattr(local_stack.socket, "socket", socket)
    with pytest.raises(SystemExit, match="occupied"):
        local_stack.configure(accounts=True)
    assert not allocation.stack.exists()


@pytest.fixture
def api_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(local_stack, "ROOT", tmp_path)
    allocation = Allocation(True, 59500)
    monkeypatch.setattr(local_stack, "ALLOCATION", allocation)
    cfg = {
        "API_URL": allocation.url(1),
        "DB_URL": "postgresql://synthetic:synthetic@127.0.0.1:59502/postgres",
        "ANON_KEY": "synthetic-anon",
        "SERVICE_ROLE_KEY": "synthetic-service",
        "JWT_SECRET": "synthetic-jwt",
    }
    status = MagicMock(return_value=cfg)
    monkeypatch.setattr(local_stack, "status", status)
    monkeypatch.setattr(local_stack.os, "chdir", lambda _: None)
    launched = []
    monkeypatch.setattr(local_stack.os, "execve", lambda *args: launched.append(args))
    return status, launched


@pytest.mark.parametrize("port,households", [(None, False), (59520, True)])
def test_api_override_keeps_auth_database_and_sanitized_provider_environment(
    api_launch, monkeypatch, port, households
):
    status, launched = api_launch
    monkeypatch.setenv("CUADRAO_HOUSEHOLDS_ENABLED", "true")
    monkeypatch.setenv("ARGUS_UNKNOWN_PROVIDER_TOKEN", "must-not-inherit")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    monkeypatch.setenv("DATABASE_URL", "postgresql://hosted.invalid/database")
    local_stack.api(
        "/synthetic/python",
        accounts_enabled=True,
        api_port=port,
        households_enabled=households,
    )
    status.assert_called_once_with()
    assert len(launched) == 1
    binary, command, environment = launched[0]
    assert binary == "/synthetic/python"
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == str(port or 59500)
    assert environment["SUPABASE_URL"] == "http://127.0.0.1:59501"
    assert (
        environment["DATABASE_URL"]
        == "postgresql://synthetic:synthetic@127.0.0.1:59502/postgres"
    )
    assert environment["CUADRAO_HOUSEHOLDS_ENABLED"] == str(households).lower()
    assert environment["ARGUS_FINANCIAL_ACCOUNTS_ENABLED"] == "true"
    assert environment["ARGUS_MARKET_DATA_PROVIDER_MODE"] == "synthetic_unit_fixture"
    assert environment["OPENAI_API_KEY"] == ""
    assert environment["RESEND_API_KEY"] == ""
    assert "ARGUS_UNKNOWN_PROVIDER_TOKEN" not in environment


@pytest.mark.parametrize(
    "port", [0, 58399, 59901, 58700, 58749, 59501, 59502, 59505, 59506]
)
def test_api_rejects_unowned_phone_and_stack_reserved_ports_before_status(
    api_launch, port
):
    status, launched = api_launch
    with pytest.raises(SystemExit, match="Refusing"):
        local_stack.api("/synthetic/python", api_port=port)
    status.assert_not_called()
    assert not launched


@pytest.mark.parametrize(
    "isolated,accounts", [(False, False), (False, True), (True, False)]
)
def test_household_exposure_requires_accounts_isolation(
    api_launch, monkeypatch, isolated, accounts
):
    status, launched = api_launch
    monkeypatch.setattr(local_stack, "ALLOCATION", Allocation(isolated, 59500))
    with pytest.raises(SystemExit, match="require"):
        local_stack.api(
            "/synthetic/python",
            api_port=59520,
            accounts_enabled=accounts,
            households_enabled=True,
        )
    status.assert_not_called()
    assert not launched


def test_api_root_dotenv_refusal_remains_in_force(api_launch, tmp_path):
    _, launched = api_launch
    (tmp_path / ".env").write_text("DO_NOT_READ=synthetic")
    with pytest.raises(SystemExit, match="root .env"):
        local_stack.api(
            "/synthetic/python",
            api_port=59520,
            accounts_enabled=True,
            households_enabled=True,
        )
    assert not launched


@pytest.mark.parametrize("user_count", [2, 3])
def test_seed_preserves_explicit_identities_and_refuses_replacement(
    allocation, monkeypatch, user_count
):
    monkeypatch.setattr(
        local_stack,
        "status",
        lambda: {
            "API_URL": allocation.url(1),
            "ANON_KEY": "synthetic-anon",
            "SERVICE_ROLE_KEY": "synthetic-service",
        },
    )
    (local_stack.ROOT / "ios/Config").mkdir(parents=True)
    requested = []
    identities = [str(uuid4()) for _ in range(user_count)]

    def create(request):
        assert request.full_url == allocation.url(1) + "/auth/v1/admin/users"
        body = json.loads(request.data)
        assert body["email_confirm"] is True
        assert body["email"].endswith("@example.test")
        requested.append(body)
        return io.BytesIO(json.dumps({"id": identities[len(requested) - 1]}).encode())

    monkeypatch.setattr(local_stack.urllib.request, "urlopen", create)
    local_stack.seed(user_count=user_count)
    path = allocation.work / "client.json"
    fixture = json.loads(path.read_text())
    assert [user["id"] for user in fixture["users"]] == identities
    assert [user["email"] for user in fixture["users"]] == [
        request["email"] for request in requested
    ]
    assert len({user["password"] for user in fixture["users"]}) == user_count
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(SystemExit, match="already exists"):
        local_stack.seed(user_count=user_count)
    assert len(requested) == user_count


def test_seed_rejects_unsupported_count_before_contacting_auth(monkeypatch):
    monkeypatch.setattr(
        local_stack, "status", lambda: pytest.fail("Must not contact Auth")
    )
    with pytest.raises(ValueError):
        local_stack.seed(user_count=4)
