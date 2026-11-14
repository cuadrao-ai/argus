"""Deletion and startup borrow one pool across stop and restart."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from argus.api import account_deletion_runtime, business_database, financial_accounts
from argus.api import state as api_state


@pytest.fixture
def pools(monkeypatch):
    opened = []

    def open_pool(*_args, **kwargs):
        pool = Mock(max_size=kwargs["max_size"])
        opened.append(pool)
        return pool

    monkeypatch.setattr("psycopg_pool.ConnectionPool", open_pool)
    monkeypatch.setattr(business_database, "_pool", None)
    monkeypatch.setattr(business_database, "_database_url", None)
    monkeypatch.setattr(account_deletion_runtime, "_apple", {})
    yield opened
    business_database.close_business_pool()


def test_deletion_pool_is_reused_at_startup_and_replaced_after_shutdown(
    monkeypatch, pools
):
    url = "postgresql://localhost/deletion-pool-test"
    monkeypatch.setattr(api_state, "PERSISTENCE_MODE", "supabase")
    monkeypatch.setattr(api_state, "DATABASE_URL", url)
    monkeypatch.setenv("CUADRAO_FINANCIAL_ACCOUNTS_ENABLED", "false")
    app = SimpleNamespace(state=SimpleNamespace())
    first = account_deletion_runtime.deletion_pool(url)
    financial_accounts.start_financial_accounts(app)
    assert app.state.financial_accounts_pool is first
    assert len(pools) == 1
    financial_accounts.stop_financial_accounts(app)
    first.close.assert_called_once()
    second = account_deletion_runtime.deletion_pool(url)
    assert second is not first
    financial_accounts.start_financial_accounts(app)
    assert app.state.financial_accounts_pool is second
    assert len(pools) == 2
    financial_accounts.stop_financial_accounts(app)
    financial_accounts.stop_financial_accounts(app)
    second.close.assert_called_once()


def test_standalone_apple_drops_the_service_bound_to_the_previous_pool(
    monkeypatch, pools
):
    monkeypatch.setattr(
        "argus.domain.apple_sign_in.config.AppleSignInConfig.from_env", Mock()
    )
    monkeypatch.setattr("argus.domain.ingestion.secrets.SecretBox.from_env", Mock())
    monkeypatch.setattr("argus.domain.apple_sign_in.client.AppleAuthClient", Mock())
    url = "postgresql://localhost/deletion-pool-test"
    first_pool = account_deletion_runtime.deletion_pool(url)
    first = account_deletion_runtime.standalone_apple(first_pool)
    close = Mock(wraps=first.close)
    monkeypatch.setattr(first, "close", close)
    assert account_deletion_runtime.standalone_apple(first_pool) is first
    business_database.close_business_pool()
    second_pool = account_deletion_runtime.deletion_pool(url)
    second = account_deletion_runtime.standalone_apple(second_pool)
    assert second is not first
    assert second.repository._pool is second_pool
    close.assert_called_once()


def test_pool_rejects_a_different_database_without_disclosing_urls(pools):
    business_database.business_pool("postgresql://localhost/one")
    with pytest.raises(ValueError, match="different database") as error:
        business_database.business_pool("postgresql://localhost/two")
    assert "postgresql" not in str(error.value)
    assert len(pools) == 1
