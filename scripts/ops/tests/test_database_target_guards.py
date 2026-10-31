from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

import pytest

OPS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = OPS_DIR.parents[1]

CONNECTION_ENV = (
    "DATABASE_URL",
    "ARGUS_WORKFLOW_DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_PROJECT_URL",
    "ARGUS_CANARY_SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY",
)


class UnexpectedDatabaseAccess(AssertionError):
    """Raised if an entry point reaches its gateway without an explicit target."""


def _package(name: str) -> ModuleType:
    package = ModuleType(name)
    package.__path__ = []  # type: ignore[attr-defined]
    return package


def _unexpected_gateway() -> object:
    raise UnexpectedDatabaseAccess("database gateway was constructed")


def _unexpected_cleanup(*_args: object, **_kwargs: object) -> object:
    raise UnexpectedDatabaseAccess("guest cleanup was attempted")


def _install_import_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    gateway_factory: Callable[[], object] = _unexpected_gateway,
    guest_cleanup_operation: Callable[..., object] = _unexpected_cleanup,
) -> None:
    for name in ("argus", "argus.domain"):
        monkeypatch.setitem(sys.modules, name, _package(name))

    guest_cleanup = ModuleType("argus.domain.guest_cleanup")

    guest_cleanup.cleanup_expired_guest_workspaces = guest_cleanup_operation
    monkeypatch.setitem(sys.modules, "argus.domain.guest_cleanup", guest_cleanup)

    supabase_gateway = ModuleType("argus.domain.supabase_gateway")

    class StubSupabaseGateway:
        @classmethod
        def from_env(cls) -> object:
            return gateway_factory()

    supabase_gateway.SupabaseGateway = StubSupabaseGateway
    monkeypatch.setitem(
        sys.modules,
        "argus.domain.supabase_gateway",
        supabase_gateway,
    )

    dotenv = ModuleType("dotenv")

    def unexpected_dotenv_load() -> bool:
        raise UnexpectedDatabaseAccess("dotenv discovery was attempted")

    dotenv.load_dotenv = unexpected_dotenv_load
    monkeypatch.setitem(sys.modules, "dotenv", dotenv)


def _load_entry_point(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    *,
    gateway_factory: Callable[[], object] = _unexpected_gateway,
    guest_cleanup_operation: Callable[..., object] = _unexpected_cleanup,
) -> ModuleType:
    _install_import_stubs(
        monkeypatch,
        gateway_factory=gateway_factory,
        guest_cleanup_operation=guest_cleanup_operation,
    )
    monkeypatch.syspath_prepend(str(OPS_DIR))
    module_name = f"issue_413_{Path(filename).stem}"
    spec = importlib.util.spec_from_file_location(module_name, OPS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _clear_connection_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CONNECTION_ENV:
        monkeypatch.delenv(name, raising=False)


def _set_fake_connection_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://operator:do-not-print@db.issue413.test:5432/argus",
    )
    monkeypatch.setenv("SUPABASE_URL", "https://api.issue413.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


def test_guest_cleanup_refuses_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_connection_environment(monkeypatch)
    entry_point = _load_entry_point(
        monkeypatch,
        "cleanup_expired_guest_workspaces.py",
    )
    monkeypatch.setattr(sys, "argv", [str(OPS_DIR / entry_point.__name__)])

    with pytest.raises(SystemExit) as exc_info:
        entry_point.main()

    assert exc_info.value.code == 2
    assert "DATABASE_URL" in capsys.readouterr().err


@dataclass(frozen=True)
class _CleanupResult:
    auth_delete_failed: int = 0
    purge_failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "auth_delete_failed": self.auth_delete_failed,
            "purge_failed": self.purge_failed,
        }


def test_guest_cleanup_keeps_json_stdout_clean_and_announces_before_gateway(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_connection_environment(monkeypatch)
    _set_fake_connection_environment(monkeypatch)
    output_before_gateway: list[tuple[str, str]] = []

    def gateway_factory() -> object:
        captured = capsys.readouterr()
        output_before_gateway.append((captured.out, captured.err))
        return object()

    def guest_cleanup_operation(*_args: object, **_kwargs: object) -> object:
        return _CleanupResult()

    entry_point = _load_entry_point(
        monkeypatch,
        "cleanup_expired_guest_workspaces.py",
        gateway_factory=gateway_factory,
        guest_cleanup_operation=guest_cleanup_operation,
    )
    monkeypatch.setattr(sys, "argv", [str(OPS_DIR / entry_point.__name__)])

    assert entry_point.main() == 0
    assert output_before_gateway == [
        (
            "",
            "destructive database target: "
            "database_host=db.issue413.test supabase_host=api.issue413.test\n",
        )
    ]
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "auth_delete_failed": 0,
        "purge_failed": 0,
    }
    assert captured.err == ""
    assert "do-not-print" not in output_before_gateway[0][1]
