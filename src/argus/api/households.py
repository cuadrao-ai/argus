"""Exposure gate for household membership and account grants.

Default-off behind ``CUADRAO_HOUSEHOLDS_ENABLED``. While off, or when durable mode
has no database, routes answer 404 so the surface does not exist. Guests are
refused after authentication. Household sharing requires financial accounts in
memory mode so grants can resolve owned accounts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from loguru import logger

from argus.api import state as api_state
from argus.api.dependencies import current_user, problem
from argus.api.guest_access import account_context
from argus.api.schemas import User
from argus.domain.household.errors import HouseholdError
from argus.domain.household.service import HouseholdService

FLAG = "CUADRAO_HOUSEHOLDS_ENABLED"
INVITES_FLAG = "CUADRAO_BETA_INVITES_ENABLED"
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

_service: HouseholdService | None = None
_invites = None


def households_enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in TRUE_VALUES


def households_service() -> HouseholdService | None:
    return _service


def invites_enabled() -> bool:
    return os.getenv(INVITES_FLAG, "").strip().lower() in TRUE_VALUES


def invites_store():  # noqa: ANN201
    return _invites


def configure_invites_store(store) -> None:  # noqa: ANN001
    global _invites
    _invites = store


def start_invites(app) -> None:  # noqa: ANN001
    """Beta invites, the group link and the gate. Postgres only; memory stays off."""
    configure_invites_store(None)
    if not invites_enabled():
        return
    if not _code_secret_ready("Beta invites"):
        return
    if api_state.PERSISTENCE_MODE != "supabase" or not api_state.DATABASE_URL:
        logger.warning(
            "Beta invites need DATABASE_URL in supabase mode; surface stays off"
        )
        return
    try:
        from psycopg_pool import ConnectionPool

        from argus.domain.household.invites import PostgresInviteStore

        pool = ConnectionPool(api_state.DATABASE_URL, min_size=0, max_size=4, open=True)
        app.state.invites_pool = pool
        configure_invites_store(PostgresInviteStore(pool))
    except Exception:
        logger.exception("Beta invite surface failed to start; leaving off")
        configure_invites_store(None)


def _code_secret_ready(surface: str) -> bool:
    """Fail closed: a surface that makes or looks up codes needs the secret."""
    from argus.domain.household.invite_codes import code_secret_problem

    reason = code_secret_problem()
    if reason is None:
        return True
    logger.error(
        "{} stay off: invite code secret unusable ({}). Set CUADRAO_INVITE_CODE_SECRET.",
        surface,
        reason,
    )
    return False


def configure_households_service(service: HouseholdService | None) -> None:
    global _service
    _service = service


def start_households(app) -> None:  # noqa: ANN001
    start_invites(app)
    if not households_enabled():
        configure_households_service(None)
        return
    if not _code_secret_ready("Households"):
        configure_households_service(None)
        return
    from argus.api.financial_accounts import financial_accounts_service
    from argus.domain.household.repository import (
        FinancialAccountLookup,
        InMemoryHouseholdRepository,
    )
    from argus.domain.recording.repository import InMemoryFinancialAccountRepository

    accounts_service = financial_accounts_service()
    try:
        if api_state.PERSISTENCE_MODE == "supabase":
            if not api_state.DATABASE_URL:
                logger.warning(
                    "Households need DATABASE_URL in supabase mode; surface stays off"
                )
                configure_households_service(None)
                return
            if accounts_service is None:
                logger.warning(
                    "Households need financial accounts enabled; surface stays off"
                )
                configure_households_service(None)
                return
            from psycopg_pool import ConnectionPool

            from argus.domain.household.postgres import PostgresHouseholdRepository

            pool = ConnectionPool(
                api_state.DATABASE_URL, min_size=0, max_size=4, open=True
            )
            app.state.households_pool = pool
            lookup = FinancialAccountLookup(accounts_service._repository)  # noqa: SLF001
            configure_households_service(
                HouseholdService(PostgresHouseholdRepository(pool, lookup))
            )
            return

        # Memory mode: share the financial accounts in-memory repository when
        # present; otherwise attach a private twin so grant tests can inject one.
        if accounts_service is not None:
            repository = accounts_service._repository  # noqa: SLF001
        else:
            repository = InMemoryFinancialAccountRepository()
            app.state.households_private_accounts = repository
        lookup = FinancialAccountLookup(repository)
        configure_households_service(
            HouseholdService(InMemoryHouseholdRepository(lookup))
        )
    except Exception:
        logger.exception("Household surface failed to start; leaving off")
        configure_households_service(None)


def stop_households(app) -> None:  # noqa: ANN001
    configure_households_service(None)
    configure_invites_store(None)
    invites_pool = getattr(app.state, "invites_pool", None)
    if invites_pool is not None:
        try:
            invites_pool.close()
        except Exception:
            logger.warning("Invites pool close failed")
        app.state.invites_pool = None
    pool = getattr(app.state, "households_pool", None)
    if pool is not None:
        try:
            pool.close()
        except Exception:
            logger.warning("Households pool close failed")
        app.state.households_pool = None


def unavailable_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=404,
        code="households_unavailable",
        title="Not Found",
        detail="Households are not available.",
    )


def require_households_surface(request: Request) -> HouseholdService:
    service = households_service()
    if not households_enabled() or service is None:
        raise unavailable_problem(request)
    return service


@dataclass(frozen=True)
class HouseholdsContext:
    service: HouseholdService
    user_id: str


def _registered_user_id(request: Request) -> str:
    account = account_context(request)
    if account.kind != "registered":
        raise problem(
            request,
            status_code=403,
            code="account_conversion_required",
            title="Account Required",
            detail="Create an account to use households.",
        )
    return account.user_id


def require_households_context(
    request: Request,
    service: HouseholdService = Depends(require_households_surface),  # noqa: B008
    _user: User = Depends(current_user),  # noqa: B008
) -> HouseholdsContext:
    return HouseholdsContext(service=service, user_id=_registered_user_id(request))


def require_invites_surface(request: Request):  # noqa: ANN201
    store = invites_store()
    if not invites_enabled() or store is None:
        raise problem(
            request,
            status_code=404,
            code="invites_unavailable",
            title="Not Found",
            detail="Invites are not available.",
        )
    return store


@dataclass(frozen=True)
class InvitesContext:
    store: object
    user_id: str


def require_invites_context(
    request: Request,
    store=Depends(require_invites_surface),  # noqa: ANN001, B008
    _user: User = Depends(current_user),  # noqa: B008
) -> InvitesContext:
    return InvitesContext(store=store, user_id=_registered_user_id(request))


_STATUS = {
    "account_not_owned": 403,
    "household_admin_required": 403,
    "not_a_member": 403,
    "founder_required": 403,
    "beta_invite_required": 403,
    "invite_request_invalid": 422,
    "verified_user_required": 401,
    "invite_codes_unavailable": 503,
}
_WAITLIST_CODES = frozenset(
    {
        "beta_invite_required",
        "group_link_full",
        "invitation_expired",
        "invitation_revoked",
        "invitation_consumed",
        "invitation_not_found",
    }
)


def waitlist_context(request: Request, code: str) -> dict | None:
    """Beta redeem failures point at the waitlist, so the screen can say so."""
    if code not in _WAITLIST_CODES or not request.url.path.startswith("/api/v1/invites"):
        return None
    store = invites_store()
    url = store.settings.waitlist_url if store is not None else None
    return {"waitlist_url": url} if url else None


def domain_problem(request: Request, error: Exception) -> HTTPException:
    if isinstance(error, HouseholdError):
        status = 404 if error.code.endswith("not_found") else 409
        status = _STATUS.get(error.code, status)
        return problem(
            request,
            status_code=status,
            code=error.code,
            title=error.code.replace("_", " ").capitalize(),
            detail=error.detail,
            context=waitlist_context(request, error.code),
        )
    from argus.api.financial_accounts import domain_problem as financial_problem

    return financial_problem(request, error)
