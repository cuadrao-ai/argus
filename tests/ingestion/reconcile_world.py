"""Builds a reconciliation world over either storage backend."""

from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store import InMemoryImportStore
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.repository import InMemoryFinancialAccountRepository
from argus.domain.recording.service import FinancialAccountService

from tests.ingestion.reconcile_cases import NOW


@dataclass
class World:
    recon: ReconciliationService
    accounts: FinancialAccountService
    user: str
    connect: Callable[[str], str]
    disconnect: Callable[[str], None]


def build(repository: Any, store: Any, connections: Any, user: str) -> World:
    accounts = FinancialAccountService(repository, lambda: NOW)
    recon = ReconciliationService(
        store, MoneyService(accounts), lambda: NOW, connections=connections
    )

    def connect(source: str) -> str:
        return connections.create(
            user_id=user,
            source=source,
            external_ref=str(uuid4()),
            label=None,
            now=NOW,
            scope=PERSONAL,
        ).id

    def disconnect(connection_id: str) -> None:
        connections.disconnect(user_id=user, connection_id=connection_id, now=NOW)

    return World(recon, accounts, user, connect, disconnect)


def memory_pair() -> tuple[World, World]:
    repository = InMemoryFinancialAccountRepository(lambda: NOW)
    store, connections = InMemoryImportStore(), InMemoryConnectionRepository()
    return (
        build(repository, store, connections, str(uuid4())),
        build(repository, store, connections, str(uuid4())),
    )
