"""Shared fixtures for the Plaid API tests: real startup, scripted provider."""

import base64
import os

import httpx
import pytest
from argus.api.ingestion import ingestion_hub
from argus.api.plaid import configure_plaid_connector, plaid_connector
from argus.domain.ingestion.plaid.connector import PlaidConnector
from loguru import logger

from tests.ingestion.conftest import ALICE, bearer
from tests.ingestion.plaid_fakes import (
    PUBLIC_TOKEN,
    FakePlaid,
    RecordingSink,
    page,
    txn,
)

URL = "/api/v1/financial-connections/plaid"
SECRET = "plaid-secret-value"


@pytest.fixture(autouse=True)
def plaid_env(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("ARGUS_INGESTION_SECRET_KEY", key)
    monkeypatch.setenv("PLAID_CLIENT_ID", "client-id")
    monkeypatch.setenv("PLAID_SECRET", SECRET)
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    monkeypatch.delenv("PLAID_CREDENTIALS_INJECTED", raising=False)


@pytest.fixture
def plaid(client):  # noqa: ANN001
    started = plaid_connector()
    assert started is not None and ingestion_hub().adapter("plaid") is started.adapter
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 4.5)], next_cursor="c1")],
            "c1": [page(next_cursor="c1")],
        }
    )
    hub = ingestion_hub()
    connector = PlaidConnector(hub, started.config, transport=httpx.MockTransport(fake))
    hub.register(connector.adapter)
    hub.sink = RecordingSink()
    configure_plaid_connector(connector)
    return fake


@pytest.fixture
def logs():
    lines: list[str] = []
    handle = logger.add(lambda message: lines.append(str(message.record)), level="DEBUG")
    yield lines
    logger.remove(handle)


def connect(client, token=ALICE):  # noqa: ANN001
    return client.post(
        f"{URL}/exchange", json={"public_token": PUBLIC_TOKEN}, headers=bearer(token)
    )
