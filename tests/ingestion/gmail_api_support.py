"""Shared fixtures for the Gmail API tests: real startup, scripted Google."""

import base64
import os
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from argus.api.gmail import configure_gmail_connector, gmail_connector
from argus.api.ingestion import ingestion_hub
from argus.domain.ingestion.gmail.connector import GmailConnector
from argus.domain.ingestion.gmail.senders import InMemorySenderRepository
from loguru import logger

from tests.ingestion.conftest import ALICE, bearer
from tests.ingestion.gmail_fakes import (
    CLIENT_ID,
    CLIENT_SECRET,
    REDIRECT,
    FakeGoogle,
    RecordingSink,
)
from tests.ingestion.gmail_mailbox import standard_mailbox

URL = "/api/v1/financial-connections/gmail"


@pytest.fixture(autouse=True)
def gmail_env(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("ARGUS_INGESTION_SECRET_KEY", key)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", REDIRECT)


@pytest.fixture
def google(client):  # noqa: ANN001
    started = gmail_connector()
    hub = ingestion_hub()
    assert started is not None and hub.adapter("gmail") is started.adapter
    fake = FakeGoogle(mails=standard_mailbox())
    connector = GmailConnector(
        hub,
        started.config,
        senders=InMemorySenderRepository(),
        transport=httpx.MockTransport(fake),
        sleep=lambda _seconds: None,
    )
    hub.register(connector.adapter)
    hub.sink = RecordingSink()
    configure_gmail_connector(connector)
    return fake


@pytest.fixture
def logs():
    lines: list[str] = []
    handle = logger.add(lambda message: lines.append(str(message.record)), level="DEBUG")
    yield lines
    logger.remove(handle)


def authorize(client, token=ALICE):  # noqa: ANN001
    response = client.post(f"{URL}/authorize", headers=bearer(token))
    assert response.status_code == 200, response.text
    return response.json()["authorization_url"]


def connect(client, google, token=ALICE, senders=("banco-ejemplo.test",), **issue):  # noqa: ANN001
    code, state = google.issue_code(authorize(client, token), **issue)
    body = {"code": code, "state": state}
    if senders is not None:
        body["senders"] = list(senders)
    return client.post(f"{URL}/callback", json=body, headers=bearer(token))


def state_of(url: str) -> str:
    return parse_qs(urlsplit(url).query)["state"][0]
