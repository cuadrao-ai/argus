from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from loguru import logger
from psycopg import connect
from pydantic import ValidationError

from argus.api import state as api_state
from argus.api.chat.research_evidence import grounding_meter
from argus.api.dependencies import (
    current_user,
    dev_memory_fallback_enabled,
    problem,
    require_account_capability,
)
from argus.api.guest_access import (
    AccountContext,
    account_context,
    client_identity,
    public_account_access_enabled,
)
from argus.api.schemas import AppleIdentity, ProfilePatch, User, UserResponse
from argus.api.usage_allowance_schemas import (
    UnboundedAllowance,
    UsageAllowance,
    UsageAllowanceResponse,
    UsageAllowances,
    UsageWindow,
)
from argus.domain.apple_sign_in.identity import LinkedAppleIdentity, linked_apple_identity
from argus.domain.store import utcnow
from argus.domain.usage_counter_reader import align_usage_period
from argus.domain.usage_limits import (
    GUEST_CONVERSATION_ALLOWANCE,
    GUEST_FEEDBACK_ALLOWANCE,
    GUEST_SIMULATION_ALLOWANCE,
    SIMULATION_ALLOWANCE_LIMITS,
    SIMULATION_USAGE_RESOURCE,
    read_memory_usage,
)
from argus.domain.visitor_usage import (
    read_memory_visitor_used,
    read_visitor_used,
    visitor_key_for,
)

router = APIRouter(prefix="/api/v1", tags=["profile"])


def _user_response(
    user: User, context: AccountContext, apple_identity: LinkedAppleIdentity | None = None
) -> UserResponse:
    return UserResponse(
        user=user,
        apple_identity=AppleIdentity(subject=apple_identity.subject)
        if apple_identity
        else None,
        account_kind=context.kind,
        guest=(
            {
                "expires_at": context.expires_at,
                "conversation_id": context.conversation_id,
                "conversation_limit": GUEST_CONVERSATION_ALLOWANCE,
                "simulation_limit": GUEST_SIMULATION_ALLOWANCE,
                "feedback_limit": GUEST_FEEDBACK_ALLOWANCE,
            }
            if context.kind == "guest"
            else None
        ),
        capabilities=context.capabilities,
        public_account_access_enabled=public_account_access_enabled(),
    )


def _apple_identity(request: Request, user_id: str) -> LinkedAppleIdentity | None:
    mock_auth = any(
        os.getenv(name, "").strip().lower() == "true"
        for name in ("NEXT_PUBLIC_MOCK_AUTH", "ARGUS_MOCK_AUTH")
    )
    if mock_auth and api_state.supabase_gateway is None and not api_state.DATABASE_URL:
        return None
    try:
        if not api_state.DATABASE_URL:
            raise RuntimeError("identity_storage_unconfigured")
        with connect(
            api_state.DATABASE_URL,
            connect_timeout=2,
            options="-c statement_timeout=2000 -c default_transaction_read_only=on",
        ) as connection:
            return linked_apple_identity(connection, user_id)
    except Exception:
        raise problem(
            request,
            status_code=503,
            code="apple_identity_unavailable",
            title="Identity unavailable",
            detail="Account identity could not be verified. Try again.",
        ) from None


def _accept_business_invites(user_id: str) -> None:
    """Pending Business invites for this person's confirmed email become grants.

    Runs on every profile read, is idempotent, and never blocks the profile."""

    from argus.api.business_spaces import business_access

    store = business_access()
    if store is None:
        return
    try:
        store.accept_invites(user_id)
    except Exception as error:  # noqa: BLE001 - the profile answers; the class is logged
        logger.warning(
            "business_access_accept_failed", user_id=user_id, error=type(error).__name__
        )


@router.get("/me", response_model=UserResponse)
def get_me(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> UserResponse:
    context = account_context(request)
    identity = _apple_identity(request, user.id) if context.kind == "registered" else None
    if context.kind == "registered":
        _accept_business_invites(user.id)
    if api_state.supabase_gateway is not None:
        try:
            profile = api_state.supabase_gateway.get_user(user_id=user.id)
            if profile:
                return _user_response(profile, context, identity)
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            logger.warning(
                "Supabase profile read failed; using dev memory fallback",
                error=str(exc),
                user_id=user.id,
            )
    return _user_response(user, context, identity)


@router.get("/me/usage", response_model=UsageAllowanceResponse)
def get_me_usage(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> UsageAllowanceResponse:
    """Allowance truth keyed by operation class.

    Compute never has a window. Execution and grounding project the counters
    their admission owners charge, so availability here is availability there.
    """
    now = datetime.now(timezone.utc)
    context = account_context(request)
    is_guest = context.kind == "guest"
    grounding = grounding_meter(is_guest=is_guest)
    visitor_key = visitor_key_for(client_identity(request)) if is_guest else None
    guest_period_start = (
        context.expires_at - timedelta(days=7)
        if is_guest and context.expires_at is not None
        else None
    )
    # Account-keyed counters: the guest workspace window for execution, or the
    # registered calendar windows for execution and, rail off, grounding.
    account_resources: tuple[str, ...] = (SIMULATION_USAGE_RESOURCE,)
    if not is_guest and grounding.limits:
        account_resources += (grounding.resource,)
    periods = (
        (("guest_session", guest_period_start),)
        if is_guest
        else (("hour", None), ("day", None))
    )
    rows_by_period: dict[str, dict[str, dict]] = {period: {} for period, _ in periods}
    if api_state.supabase_gateway is not None:
        try:
            for period, period_start in periods:
                query = {
                    "user_id": user.id,
                    "resources": account_resources,
                    "period": period,
                    "at": now,
                }
                if period_start is not None:
                    query["period_start"] = period_start
                rows = api_state.supabase_gateway.list_current_usage_counters(
                    **query,
                )
                rows_by_period[period] = {str(row.get("resource")): row for row in rows}
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                logger.error(
                    "Supabase usage read failed",
                    error=str(exc),
                    user_id=user.id,
                )
                raise problem(
                    request,
                    status_code=500,
                    code="usage_read_failed",
                    title="Usage Read Failed",
                    detail="Current allowance information is unavailable.",
                ) from exc
            logger.warning(
                "Supabase usage read failed; using dev zero-state fallback",
                error=str(exc),
                user_id=user.id,
            )
    else:
        for resource in account_resources:
            for period, period_start in periods:
                row = read_memory_usage(
                    api_state.store.usage_counters,
                    user_id=user.id,
                    resource=resource,
                    period=period,
                    at=now,
                    period_start=period_start,
                )
                if row is not None:
                    rows_by_period[period][resource] = {
                        "resource": resource,
                        "used_count": row.get("used_count", 0),
                        "limit_count": row.get("limit_count"),
                        "period_end": row.get("period_end"),
                    }

    def window(
        resource: str,
        period: str,
        policy_limit: int,
        *,
        fixed_period_end: datetime | None = None,
    ) -> UsageWindow:
        row = rows_by_period[period].get(resource, {})
        if fixed_period_end is None:
            _, default_period_end = align_usage_period(now, period)
        else:
            default_period_end = fixed_period_end
        limit = max(int(row.get("limit_count") or policy_limit), 0)
        used = max(int(row.get("used_count", 0)), 0)
        return UsageWindow(
            limit=limit,
            used=used,
            remaining=max(limit - used, 0),
            period_end=row.get("period_end") or default_period_end,
        )

    def registered_allowance(
        resource: str,
        limits: list[tuple[str, int]],
    ) -> UsageAllowance:
        policy = dict(limits)
        hour = window(resource, "hour", policy["hour"])
        day = window(resource, "day", policy["day"])
        return UsageAllowance(
            hour=hour,
            day=day,
            guest_session=None,
            available_now=hour.remaining > 0 and day.remaining > 0,
            limiting_window="hour" if hour.remaining < day.remaining else "day",
        )

    def visitor_day_window(resource: str, policy_limit: int) -> UsageWindow:
        """Visitor-keyed day window: a renewed workspace changes nothing."""
        if visitor_key is None:
            raise RuntimeError("Visitor day windows belong to guest accounts only.")
        _, day_end = align_usage_period(now, "day")
        used = 0
        try:
            if api_state.supabase_gateway is not None:
                used = read_visitor_used(
                    api_state.supabase_gateway.client,
                    visitor_key=visitor_key,
                    resource=resource,
                    period="day",
                    now=now,
                )
            else:
                used = read_memory_visitor_used(
                    api_state.store.visitor_usage_counters,
                    visitor_key=visitor_key,
                    resource=resource,
                    period="day",
                    now=now,
                )
        except Exception as exc:
            # Fail closed and loudly: a silent zero would hand out
            # unaccounted allowance.
            logger.error(
                "Visitor allowance read failed; treating window as exhausted",
                error=str(exc),
                resource=resource,
                failure_classification="allowance_read_failed",
            )
            used = policy_limit
        return UsageWindow(
            limit=policy_limit,
            used=min(used, policy_limit),
            remaining=max(policy_limit - used, 0),
            period_end=day_end,
        )

    def guest_execution_allowance() -> UsageAllowance:
        """Both bounds admission enforces: the visitor's day and the
        workspace lifetime (#546)."""
        day = visitor_day_window(SIMULATION_USAGE_RESOURCE, GUEST_SIMULATION_ALLOWANCE)
        guest_session = window(
            SIMULATION_USAGE_RESOURCE,
            "guest_session",
            GUEST_SIMULATION_ALLOWANCE,
            fixed_period_end=context.expires_at,
        )
        if day.remaining != guest_session.remaining:
            limiting_window = (
                "day" if day.remaining < guest_session.remaining else "guest_session"
            )
        else:
            # Equal capacity: name the window that resets later. On the
            # workspace's final calendar day that is the visitor day, and a
            # renewed workspace would not clear it.
            limiting_window = (
                "guest_session" if guest_session.period_end >= day.period_end else "day"
            )
        return UsageAllowance(
            hour=None,
            day=day,
            guest_session=guest_session,
            available_now=day.remaining > 0 and guest_session.remaining > 0,
            limiting_window=limiting_window,
        )

    def guest_grounding_allowance() -> UsageAllowance:
        day = visitor_day_window(grounding.resource, dict(grounding.limits)["day"])
        return UsageAllowance(
            hour=None,
            day=day,
            guest_session=None,
            available_now=day.remaining > 0,
            limiting_window="day",
        )

    if is_guest:
        return UsageAllowanceResponse(
            allowances=UsageAllowances(
                compute=UnboundedAllowance(),
                grounding=guest_grounding_allowance(),
                execution=guest_execution_allowance(),
            )
        )

    return UsageAllowanceResponse(
        allowances=UsageAllowances(
            compute=UnboundedAllowance(),
            grounding=(
                registered_allowance(grounding.resource, grounding.limits)
                if grounding.limits
                else UnboundedAllowance()
            ),
            execution=registered_allowance(
                SIMULATION_USAGE_RESOURCE, SIMULATION_ALLOWANCE_LIMITS
            ),
        )
    )


@router.patch("/me", response_model=UserResponse)
def patch_me(
    patch: ProfilePatch,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> UserResponse:
    context = account_context(request)
    require_account_capability(
        request,
        "can_manage_account",
        detail="Sign in to manage a permanent profile.",
        reason="manage_account",
    )
    current = (
        api_state.supabase_gateway.get_user(user_id=user.id)
        if api_state.supabase_gateway is not None
        else api_state.store.users.get(user.id, user)
    )
    if current is None:
        current = user

    data = current.model_dump()
    updates = patch.model_dump(exclude_unset=True)
    updated_fields = sorted(updates)
    data.update(updates)
    data["updated_at"] = utcnow()
    try:
        updated = User.model_validate(data)
    except ValidationError as exc:
        raise problem(
            request,
            status_code=422,
            code="invalid_profile_patch",
            title="Invalid Profile Patch",
            detail="The profile update could not be applied.",
            context={"errors": exc.errors()},
        ) from exc

    identity = _apple_identity(request, user.id)
    if api_state.supabase_gateway is not None:
        try:
            # A derived field is not a column; the row stores what it derives from.
            updated = api_state.supabase_gateway.update_user(
                user.id,
                {
                    "id": user.id,
                    **updated.model_dump(mode="json", include=set(updates)),
                    "updated_at": updated.updated_at.isoformat(),
                },
            )
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            logger.warning(
                "Supabase profile patch failed; using dev memory fallback",
                error=str(exc),
                user_id=user.id,
            )
    api_state.store.users[user.id] = updated
    logger.info(
        "Profile updated",
        user_id=user.id,
        fields=updated_fields,
    )
    return _user_response(updated, context, identity)
