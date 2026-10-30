from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from fastapi import Request

from argus.api.client_ip import resolve_client_ip
from argus.api.schemas import AccountCapabilities
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.visitor_usage import visitor_key_for

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _enabled(name: str, *, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return raw_value.strip().lower() in _TRUE_VALUES


def guest_access_enabled() -> bool:
    server_enabled = _enabled("CUADRAO_GUEST_ACCESS_ENABLED", default=True)
    presentation = os.getenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED")
    if presentation is None or not presentation.strip():
        return server_enabled
    presentation_value = presentation.strip().lower()
    if presentation_value not in _TRUE_VALUES | _FALSE_VALUES:
        return False
    return server_enabled and presentation_value in _TRUE_VALUES


def public_account_access_enabled() -> bool:
    return _enabled("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED")


class PermanentAccessGateway(Protocol):
    def private_alpha_email_disabled(self, email: str) -> bool: ...

    def private_alpha_email_allowed(self, email: str) -> bool: ...


def permanent_account_access_allowed(
    gateway: PermanentAccessGateway,
    email: str,
) -> bool:
    if public_account_access_enabled():
        return not gateway.private_alpha_email_disabled(email)
    return gateway.private_alpha_email_allowed(email)


@dataclass(frozen=True)
class AccountContext:
    kind: Literal["guest", "registered"]
    user_id: str
    expires_at: datetime | None
    capabilities: AccountCapabilities
    conversation_id: str | None = None
    # Carried so funnel milestones can be claimed against the visitor rather
    # than a guest user id that renewal replaces. None when the context was
    # built without a request.
    visitor_key: str | None = None


_current_account_context: ContextVar[AccountContext | None] = ContextVar(
    "argus_account_context",
    default=None,
)


def client_identity(request: Request) -> str:
    """Best available identifier for the visitor behind a request.

    Delegates to the single trusted-header helper. Guest allowances are
    charged against this instead of a user id, because a guest user id
    renews on a timer.
    """
    return resolve_client_ip(request)


def visitor_key_for_request(request: Request) -> str:
    """The one notion of visitor subject, shared with guest allowances."""
    return visitor_key_for(client_identity(request))


def guest_capabilities() -> AccountCapabilities:
    return AccountCapabilities(
        can_create_additional_conversation=False,
        can_manage_conversation=False,
        can_save_decision=False,
        can_manage_account=False,
        can_use_omnisearch=True,
        can_search_current_workspace=True,
        # Both classes can discover; guests are metered, not blocked. Reporting
        # False here told guests discovery was unavailable while it worked.
        can_use_grounded_discovery=True,
        can_submit_feedback=True,
    )


def registered_capabilities() -> AccountCapabilities:
    return AccountCapabilities(
        can_create_additional_conversation=True,
        can_manage_conversation=True,
        can_save_decision=True,
        can_manage_account=True,
        can_use_omnisearch=True,
        can_search_current_workspace=True,
        can_use_grounded_discovery=True,
        can_submit_feedback=True,
    )


def guest_account_context(
    workspace: GuestWorkspace,
    *,
    visitor_key: str | None = None,
) -> AccountContext:
    return AccountContext(
        kind="guest",
        user_id=workspace.user_id,
        expires_at=workspace.expires_at,
        capabilities=guest_capabilities(),
        conversation_id=workspace.conversation_id,
        visitor_key=visitor_key,
    )


def registered_account_context(
    user_id: str,
    *,
    visitor_key: str | None = None,
) -> AccountContext:
    return AccountContext(
        kind="registered",
        user_id=user_id,
        expires_at=None,
        capabilities=registered_capabilities(),
        conversation_id=None,
        visitor_key=visitor_key,
    )


def store_account_context(request: Request, context: AccountContext) -> None:
    request.state.account_context = context


def account_context(request: Request) -> AccountContext:
    context = getattr(request.state, "account_context", None)
    if not isinstance(context, AccountContext):
        raise RuntimeError("Verified account context was not established.")
    _current_account_context.set(context)
    return context


def current_account_context() -> AccountContext | None:
    return _current_account_context.get()
