"""Every enabled database consumer shares the lifespan's bounded pool."""

from importlib import import_module
from unittest.mock import AsyncMock, Mock

import pytest
from argus.api import app_setup, financial_accounts, personalization_memory
from argus.api import state as api_state
from fastapi import FastAPI


@pytest.mark.asyncio
@pytest.mark.parametrize("accounts_enabled", [True, False])
async def test_lifespan_starts_pool_before_memory_and_shares_with_invites_and_deletion(
    monkeypatch: pytest.MonkeyPatch, accounts_enabled: bool
) -> None:
    from argus.api import account_deletion_runtime, households

    pools = []

    def open_pool(*args, **kwargs):
        pool = Mock(max_size=kwargs["max_size"])
        pools.append(pool)
        return pool

    monkeypatch.setattr("psycopg_pool.ConnectionPool", open_pool)
    monkeypatch.setattr(app_setup, "validate_startup_configuration", lambda: None)
    monkeypatch.setattr(api_state, "PERSISTENCE_MODE", "supabase")
    monkeypatch.setattr(api_state, "CHECKPOINTER_MODE", "memory")
    monkeypatch.setattr(api_state, "DATABASE_URL", "postgresql://localhost/pool-test")
    monkeypatch.setenv("CUADRAO_FINANCIAL_ACCOUNTS_ENABLED", str(accounts_enabled))
    monkeypatch.setenv("ARGUS_ENABLE_PERSONALIZATION_MEMORY", "true")
    monkeypatch.setenv("ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL", "false")
    monkeypatch.setenv("CUADRAO_BETA_INVITES_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_HOUSEHOLDS_ENABLED", "false")
    monkeypatch.setenv("CUADRAO_INVITE_CODE_SECRET", "pool-tests-invite-secret-0123456789")
    for module_name, suffix in (
        ("fiscal_operations", "fiscal"),
        ("profile_images", "profile_images"),
        ("ingestion", "ingestion"),
        ("bank_matching", "bank_matching"),
        ("email_intake", "email_intake"),
        ("whatsapp_worker", "worker"),
        ("apple_sign_in", "apple_sign_in"),
    ):
        module = import_module(f"argus.api.{module_name}")
        monkeypatch.setattr(module, f"start_{suffix}", Mock())
        stop = AsyncMock() if suffix in {"fiscal", "email_intake", "worker"} else Mock()
        monkeypatch.setattr(module, f"stop_{suffix}", stop)
    monkeypatch.setattr("argus.api.whatsapp.drain_whatsapp", AsyncMock())
    start_memory = personalization_memory.start_personalization_memory
    pools_before_memory = []

    def observe_memory_start(app):
        pools_before_memory.extend(pools)
        start_memory(app)

    monkeypatch.setattr(personalization_memory, "start_personalization_memory", observe_memory_start)
    app = FastAPI()
    async with app_setup.lifespan(app):
        pool = app.state.financial_accounts_pool
        assert pools_before_memory == [pool]
        assert personalization_memory.memory_service()._store._pool is pool
        assert households.invites_store()._pool is pool
        assert account_deletion_runtime.deletion_pool(api_state.DATABASE_URL) is pool
        assert len(pools) == 1
        assert pool.max_size == 2
        assert (financial_accounts.financial_accounts_service() is not None) == accounts_enabled
        pool.close.assert_not_called()
    pool.close.assert_called_once()
