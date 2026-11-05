"""Shared fixtures for the personalization-memory API tests.

Imports of the API application stay inside the fixture so the deterministic
domain tests keep their hermetic import surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from api_matrix import (
    GUEST_TOKEN,
    GUEST_USER_ID,
    REGISTERED_EMAIL,
    REGISTERED_TOKEN,
    REGISTERED_USER_ID,
)

_AUTH_ENV_VARS = (
    "NEXT_PUBLIC_MOCK_AUTH",
    "CUADRAO_MOCK_AUTH",
    "CUADRAO_GUEST_ACCESS_ENABLED",
    "NEXT_PUBLIC_GUEST_ACCESS_ENABLED",
    "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED",
    "ARGUS_ENABLE_PERSONALIZATION_MEMORY",
    # Hermeticity: the default classifier must see no key so it skips, never
    # calls the network, and the assessor fails closed unless a test injects
    # a fake.
    "OPENROUTER_API_KEY",
)


@dataclass(frozen=True)
class MemoryApiHarness:
    client: Any
    gateway: Any
    guest_headers: dict[str, str]
    registered_headers: dict[str, str]


@pytest.fixture
def memory_api(monkeypatch: pytest.MonkeyPatch):
    from unittest.mock import MagicMock

    from argus.api import state as api_state
    from argus.api.main import app
    from argus.api.personalization_memory import configure_memory_service
    from argus.api.personalization_memory_assessor import (
        configure_sensitivity_classifier,
    )
    from argus.api.schemas import OnboardingState, User
    from argus.domain.guest_workspaces import GuestWorkspace
    from argus.domain.store import utcnow
    from argus.domain.supabase_gateway import SupabaseGateway
    from fastapi.testclient import TestClient

    for name in _AUTH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    now = utcnow()

    def _profile(user_id: str, email: str | None) -> User:
        return User(
            id=user_id,
            email=email,
            username=None,
            display_name=None,
            language="en",
            locale="en-US",
            is_admin=False,
            onboarding=OnboardingState(),
            created_at=now,
            updated_at=now,
        )

    workspace = GuestWorkspace(
        user_id=GUEST_USER_ID,
        conversation_id=None,
        status="active",
        created_at=now,
        expires_at=now + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=now,
    )

    def _auth_user(token: str) -> dict[str, Any]:
        if token == GUEST_TOKEN:
            return {"id": GUEST_USER_ID, "email": None, "is_anonymous": True}
        if token == REGISTERED_TOKEN:
            return {
                "id": REGISTERED_USER_ID,
                "email": REGISTERED_EMAIL,
                "is_anonymous": False,
            }
        raise ValueError("unknown test token")

    gateway = MagicMock(spec=SupabaseGateway)
    gateway.get_auth_user_from_token.side_effect = _auth_user
    gateway.get_active_guest_workspace.return_value = workspace
    gateway.get_or_create_profile_for_auth_user.side_effect = lambda auth_user: _profile(
        str(auth_user["id"]),
        auth_user.get("email"),
    )
    gateway.private_alpha_email_allowed.return_value = True
    gateway.private_alpha_email_disabled.return_value = False
    # Exposure default for the harness: a developer-role allowlist row. Role
    # gate tests override this per case.
    gateway.private_alpha_role_for_email.return_value = "developer"

    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setattr(
        "argus.api.dependencies.auth_session_is_active",
        lambda **kwargs: True,
    )

    configure_memory_service(None)
    configure_sensitivity_classifier(None)
    try:
        yield MemoryApiHarness(
            client=TestClient(app),
            gateway=gateway,
            guest_headers={"Authorization": f"Bearer {GUEST_TOKEN}"},
            registered_headers={"Authorization": f"Bearer {REGISTERED_TOKEN}"},
        )
    finally:
        configure_memory_service(None)
        configure_sensitivity_classifier(None)
