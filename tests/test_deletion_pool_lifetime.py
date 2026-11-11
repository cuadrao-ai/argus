"""Unlink still reaches Postgres after the business pool has stopped."""

from argus.api import account_deletion_runtime, financial_accounts


def test_deletion_pool_does_not_reuse_a_stopped_business_pool(monkeypatch) -> None:
    url = "postgresql://deletion-pool/argus"
    opened: list[object] = []

    class _Pool:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            opened.append(self)

        def close(self) -> None:
            return None

    monkeypatch.setattr("psycopg_pool.ConnectionPool", _Pool)
    previous = financial_accounts._pool
    account_deletion_runtime._pools.pop(url, None)
    try:
        financial_accounts._pool = object()
        shared = account_deletion_runtime.deletion_pool(url)
        assert shared is financial_accounts._pool
        assert url not in account_deletion_runtime._pools

        financial_accounts._pool = None
        private = account_deletion_runtime.deletion_pool(url)
        assert private is not shared
        assert private is opened[0]
        assert account_deletion_runtime.deletion_pool(url) is private
    finally:
        financial_accounts._pool = previous
        account_deletion_runtime._pools.pop(url, None)
