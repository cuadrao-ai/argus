"""Process wiring for Business bank matching. Default-off, nested in the pilot."""

from __future__ import annotations

from uuid import UUID

from loguru import logger

from argus.api import state as api_state
from argus.domain.business.bank.model import AccountRef
from argus.domain.business.bank.service import (
    BankMatchingService,
    EmptyCatalog,
    configure_bank_matching,
)
from argus.domain.business.bank.store import MemoryBankStore
from argus.domain.business.config import business_bank_matching_enabled
from argus.domain.owner_scope import BusinessSpace
from argus.domain.recording.errors import AccountNotFound


def account_of(space_id: UUID, owner_id: UUID, account_id: UUID) -> AccountRef | None:
    from argus.api.financial_accounts import financial_accounts_service

    service = financial_accounts_service()
    if service is None:
        return None
    try:
        stored = service.get(
            user_id=str(owner_id),
            account_id=str(account_id),
            scope=BusinessSpace(str(space_id)),
        )
    except AccountNotFound:
        return None
    return AccountRef(account_id=account_id, currency=stored.account.currency)


def start_bank_matching(app) -> None:  # noqa: ANN001
    """Build the service at startup. Flag off, or durable mode without a pool, stays off."""

    if not business_bank_matching_enabled():
        configure_bank_matching(None)
        return
    pool = getattr(app.state, "financial_accounts_pool", None)
    try:
        if pool is not None:
            from argus.domain.business.bank.movements_store import DocumentCatalog
            from argus.domain.business.bank.store_postgres import PostgresBankStore

            store, catalog = PostgresBankStore(pool), DocumentCatalog(pool)
        elif api_state.PERSISTENCE_MODE == "supabase":
            logger.warning(
                "Business bank matching needs the financial accounts pool; surface stays off"
            )
            configure_bank_matching(None)
            return
        else:
            store, catalog = MemoryBankStore(), EmptyCatalog()
        configure_bank_matching(BankMatchingService(store, catalog, account_of))
    except Exception as exc:
        logger.warning(
            "Business bank matching construction failed; surface stays off",
            failure_mode=type(exc).__name__,
        )
        configure_bank_matching(None)


def stop_bank_matching(app) -> None:  # noqa: ANN001
    del app
    configure_bank_matching(None)
