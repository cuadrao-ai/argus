"""Fixtures that drive the real auth dependency with a scripted gateway.

The in-memory repository backs the service, so these tests need no database.
Identity still flows through ``current_user``: a bearer token resolves to a
registered or an anonymous Supabase user, exactly as the production dependency
decides account kind.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.schemas import OnboardingState, User
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.store import utcnow
from argus.domain.supabase_gateway import SupabaseGateway
from fastapi.testclient import TestClient

ALICE = "registered-alice"
BOB = "registered-bob"
GUEST = "guest-gina"
TOKENS = (ALICE, BOB, GUEST)


def _profile(user_id: str, email: str | None) -> User:
    now = utcnow()
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


@pytest.fixture
def identities() -> dict[str, dict[str, Any]]:
    users = {}
    for token in TOKENS:
        anonymous = token.startswith("guest")
        user_id = str(uuid4())
        users[token] = {
            "id": user_id,
            "email": None if anonymous else f"{token}@example.test",
            "is_anonymous": anonymous,
        }
    return users


@pytest.fixture
def gateway(identities: dict[str, dict[str, Any]]) -> MagicMock:
    by_id = {user["id"]: user for user in identities.values()}

    def auth_user(token: str) -> dict[str, Any]:
        if token not in identities:
            raise RuntimeError("Invalid or missing user in token response.")
        return dict(identities[token])

    def profile(auth_user: dict[str, Any]) -> User:
        return _profile(auth_user["id"], auth_user.get("email"))

    def workspace(*, user_id: str, at):  # noqa: ANN001
        if not by_id[user_id]["is_anonymous"]:
            return None
        return GuestWorkspace(
            user_id=user_id,
            conversation_id=str(uuid4()),
            status="active",
            created_at=at - timedelta(minutes=1),
            expires_at=at + timedelta(days=7),
            claimed_by=None,
            claimed_at=None,
            updated_at=at - timedelta(minutes=1),
        )

    mock = MagicMock(spec=SupabaseGateway)
    mock.get_auth_user_from_token.side_effect = auth_user
    mock.get_or_create_profile_for_auth_user.side_effect = profile
    mock.get_active_guest_workspace.side_effect = workspace
    mock.private_alpha_email_disabled.return_value = False
    mock.private_alpha_email_allowed.return_value = True
    return mock


@pytest.fixture
def surface_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_FINANCIAL_ACCOUNTS_ENABLED", "true")
    monkeypatch.setenv("ARGUS_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")


@pytest.fixture
def client(surface_env: None, gateway: MagicMock) -> Iterator[TestClient]:
    assert api_state.PERSISTENCE_MODE == "memory"
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        yield test_client


class AccountsApi:
    """One caller's view of the routes, so tests read as the person's steps."""

    def __init__(self, client: TestClient, token: str | None) -> None:
        self._client = client
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    def create(self, body: dict[str, Any], *, key: str | None):
        headers = dict(self._headers)
        if key is not None:
            headers["Idempotency-Key"] = key
        return self._client.post("/api/v1/financial-accounts", json=body, headers=headers)

    def list(self):
        return self._client.get("/api/v1/financial-accounts", headers=self._headers)

    def get(self, account_id: str):
        return self._client.get(
            f"/api/v1/financial-accounts/{account_id}", headers=self._headers
        )

    def edit(self, account_id: str, body: dict[str, Any]):
        return self._client.patch(
            f"/api/v1/financial-accounts/{account_id}", json=body, headers=self._headers
        )

    def opening(self, account_id: str, body: dict[str, Any]):
        return self._client.put(
            f"/api/v1/financial-accounts/{account_id}/opening",
            json=body,
            headers=self._headers,
        )


@pytest.fixture
def alice(client: TestClient) -> AccountsApi:
    return AccountsApi(client, ALICE)


@pytest.fixture
def bob(client: TestClient) -> AccountsApi:
    return AccountsApi(client, BOB)


@pytest.fixture
def guest(client: TestClient) -> AccountsApi:
    return AccountsApi(client, GUEST)


@pytest.fixture
def anonymous(client: TestClient) -> AccountsApi:
    return AccountsApi(client, None)


@pytest.fixture
def legacy_blank_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank creates keep an unknown balance, like accounts saved before blank meant 0."""
    from argus.domain.recording import service

    monkeypatch.setattr(service, "blank_opening", lambda scope, account_type: None)
