"""Lend an active transaction to adapters that normally acquire from a pool."""

from contextlib import AbstractContextManager, nullcontext

from psycopg import Connection


class BorrowedConnection:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def connection(
        self, timeout: float | None = None
    ) -> AbstractContextManager[Connection]:
        return nullcontext(self._connection)
