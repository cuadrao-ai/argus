"""One process-owned pool for business data, independent of feature flags."""

from __future__ import annotations

import atexit
from threading import Lock
from typing import TYPE_CHECKING

from argus.domain.connection_budget import BUSINESS_POOL_MAX

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool

_lock = Lock()
_pool: ConnectionPool | None = None
_database_url: str | None = None


def business_pool(database_url: str) -> ConnectionPool:
    global _pool, _database_url
    with _lock:
        if _pool is not None:
            if database_url != _database_url:
                raise ValueError("The business pool already uses a different database")
            return _pool
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(
            database_url, min_size=0, max_size=BUSINESS_POOL_MAX, open=True
        )
        _database_url = database_url
        return _pool


def close_business_pool() -> None:
    global _pool, _database_url
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None
            _database_url = None


atexit.register(close_business_pool)
