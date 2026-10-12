"""Exposure gate and process wiring for the financial accounts surface.

Default-off behind ``CUADRAO_FINANCIAL_ACCOUNTS_ENABLED`` (or the older ``ARGUS_`` name). While off, or when
durable mode has no database, the routes answer 404 so the surface does not
exist. Guests are refused after authentication with the same problem the
memory surface uses, because the product boundary is registration.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from loguru import logger

from argus.api import state as api_state
from argus.api.dependencies import current_user, problem
from argus.api.guest_access import account_context
from argus.api.schemas import User
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RecordingInputError,
    RegisteredAccountRequired,
    StaleVersion,
)
from argus.domain.recording.repository import InMemoryFinancialAccountRepository
from argus.domain.recording.service import FinancialAccountService
from argus.settings_names import setting_value

FLAG = "CUADRAO_FINANCIAL_ACCOUNTS_ENABLED"
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

_service: FinancialAccountService | None = None


def financial_accounts_enabled() -> bool:
    return (
        setting_value("FINANCIAL_ACCOUNTS_ENABLED") or ""
    ).strip().lower() in TRUE_VALUES


def financial_accounts_service() -> FinancialAccountService | None:
    return _service


def configure_financial_accounts_service(service: FinancialAccountService | None) -> None:
    global _service
    _service = service


def start_financial_accounts(app) -> None:  # noqa: ANN001
    """Build the service at startup; flag off builds nothing.

    Durable mode never falls back to volatile storage: without a database the
    surface stays off rather than minting accounts that vanish on restart.
    """

    if not financial_accounts_enabled():
        configure_financial_accounts_service(None)
        return
    try:
        if api_state.PERSISTENCE_MODE == "supabase":
            if not api_state.DATABASE_URL:
                logger.warning(
                    "Financial accounts need DATABASE_URL in supabase mode; surface stays off"
                )
                configure_financial_accounts_service(None)
                return
            from psycopg_pool import ConnectionPool

            from argus.domain.recording.postgres_repository import (
                PostgresFinancialAccountRepository,
            )

            pool = ConnectionPool(
                api_state.DATABASE_URL, min_size=0, max_size=4, open=True
            )
            app.state.financial_accounts_pool = pool
            configure_financial_accounts_service(
                FinancialAccountService(PostgresFinancialAccountRepository(pool))
            )
            return
        configure_financial_accounts_service(
            FinancialAccountService(InMemoryFinancialAccountRepository())
        )
    except Exception as exc:
        logger.warning(
            "Financial accounts service construction failed; surface stays off",
            failure_mode=type(exc).__name__,
        )
        configure_financial_accounts_service(None)


def stop_financial_accounts(app) -> None:  # noqa: ANN001
    configure_financial_accounts_service(None)
    pool = getattr(app.state, "financial_accounts_pool", None)
    if pool is not None:
        try:
            pool.close()
        except Exception:
            logger.warning("Financial accounts pool close failed")
        app.state.financial_accounts_pool = None


def unavailable_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=404,
        code="financial_accounts_unavailable",
        title="Not Found",
        detail="Financial accounts are not available.",
    )


def require_financial_accounts_surface(request: Request) -> FinancialAccountService:
    """Flag first, before authentication, so an off surface looks absent to everyone."""

    service = financial_accounts_service()
    if not financial_accounts_enabled() or service is None:
        raise unavailable_problem(request)
    return service


@dataclass(frozen=True)
class FinancialAccountsContext:
    service: FinancialAccountService
    user_id: str


def require_financial_accounts_context(
    request: Request,
    service: FinancialAccountService = Depends(require_financial_accounts_surface),  # noqa: B008
    _user: User = Depends(current_user),  # noqa: B008
) -> FinancialAccountsContext:
    account = account_context(request)
    if account.kind != "registered":
        raise problem(
            request,
            status_code=403,
            code="account_conversion_required",
            title="Account Required",
            detail="Create an account to record financial accounts.",
        )
    return FinancialAccountsContext(service=service, user_id=account.user_id)


def domain_problem(request: Request, error: Exception) -> HTTPException:
    """Map a domain failure to its RFC 9457 problem."""

    if isinstance(error, RecordingInputError):
        return problem(
            request,
            status_code=409 if error.code == "budget_scope_conflict" else 422,
            code=error.code,
            title=error.code.replace("_", " ").capitalize(),
            detail=error.detail,
        )
    if isinstance(error, StaleVersion):
        return problem(
            request,
            status_code=409,
            code="stale_version",
            title="Stale Version",
            detail="The account changed since you last read it. Reload and try again.",
        )
    if isinstance(error, IdempotencyConflict):
        return problem(
            request,
            status_code=409,
            code="idempotency_conflict",
            title="Idempotency Conflict",
            detail="This Idempotency-Key was already used for a different request.",
        )
    if isinstance(error, AccountNotFound):
        return problem(
            request,
            status_code=404,
            code="financial_account_not_found",
            title="Not Found",
            detail="No such financial account.",
        )
    if isinstance(error, RegisteredAccountRequired):
        return problem(
            request,
            status_code=403,
            code="account_conversion_required",
            title="Account Required",
            detail="Create an account to record financial accounts.",
        )
    raise error
