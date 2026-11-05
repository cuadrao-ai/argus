"""Ingestion API fixtures: the real auth dependency with a scripted gateway."""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from argus.api import state as api_state
from argus.api.main import app
from fastapi.testclient import TestClient

from tests.financial_accounts.conftest import (  # noqa: F401
    ALICE,
    BOB,
    GUEST,
    gateway,
    identities,
    surface_env,
)


@pytest.fixture
def ingestion_env(surface_env: None, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.setenv("ARGUS_INGESTION_ENABLED", "true")


@pytest.fixture
def client(ingestion_env: None, gateway: MagicMock) -> Iterator[TestClient]:  # noqa: F811
    assert api_state.PERSISTENCE_MODE == "memory"
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        yield test_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
