"""Fixtures for household API acceptance with two registered identities."""

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

from tests.household.financial_fixtures import lane as lane

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


TEST_CODE_SECRET = "household-tests-invite-code-secret-0123456789"


@pytest.fixture(autouse=True)
def invite_code_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Codes fail closed without a secret (#789); every household test has one.

    The invite lookup limiter is process-local, so each test starts empty.
    """
    from argus.api import invite_limits

    monkeypatch.setenv("CUADRAO_INVITE_CODE_SECRET", TEST_CODE_SECRET)
    monkeypatch.delenv("CUADRAO_INVITE_CODE_SECRET_PREVIOUS", raising=False)
    invite_limits.reset()
    yield
    invite_limits.reset()


@pytest.fixture
def identities() -> dict[str, dict[str, Any]]:
    users = {}
    for token in TOKENS:
        anonymous = token.startswith("guest")
        users[token] = {
            "id": str(uuid4()),
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
    monkeypatch.setenv("CUADRAO_HOUSEHOLDS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")


@pytest.fixture
def client(surface_env: None, gateway: MagicMock) -> Iterator[TestClient]:
    assert api_state.PERSISTENCE_MODE == "memory"
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        yield test_client


class HouseholdApi:
    def __init__(self, client: TestClient, token: str, user_id: str) -> None:
        self._client = client
        self.user_id = user_id
        self._headers = {"Authorization": f"Bearer {token}"}

    def write(self, path, body=None, *, method="POST", key=None, version_household=None):
        value = dict(body or {})
        if version_household and "expected_version" not in value:
            result = self.get_household(version_household)
            value["expected_version"] = result.json().get("version", 1)
        return self._client.request(
            method,
            "/api/v1" + path,
            json=value,
            headers=self._headers | {"Idempotency-Key": key or str(uuid4())},
        )

    def create_household(self, body=None, key=None):
        return self.write("/households", body, key=key)

    def list_households(self):
        return self._client.get("/api/v1/households", headers=self._headers)

    def get_household(self, hid):
        return self._client.get("/api/v1/households/" + hid, headers=self._headers)

    def invite(self, hid):
        return self.write(f"/households/{hid}/invitations", version_household=hid)

    def accept(self, token):
        return self.write(
            "/household-invitations/accept", {"token": token, "display_name": "Recipient"}
        )

    def shared_accounts(self, hid):
        return self._client.get(
            f"/api/v1/households/{hid}/accounts", headers=self._headers
        )

    def share(self, hid, aid, mid, permission="view"):
        return self.write(
            f"/households/{hid}/account-grants",
            {"account_id": aid, "recipient_membership_id": mid, "permission": permission},
            version_household=hid,
        )

    def create_account(self, body: dict, *, key: str | None = None):
        headers = dict(self._headers)
        headers["Idempotency-Key"] = key or str(uuid4())
        return self._client.post("/api/v1/financial-accounts", json=body, headers=headers)


@pytest.fixture
def alice(client: TestClient, identities: dict[str, dict[str, Any]]) -> HouseholdApi:
    return HouseholdApi(client, ALICE, identities[ALICE]["id"])


@pytest.fixture
def bob(client: TestClient, identities: dict[str, dict[str, Any]]) -> HouseholdApi:
    return HouseholdApi(client, BOB, identities[BOB]["id"])
