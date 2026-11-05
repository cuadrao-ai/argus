"""In-memory connection repository held to the shared specification."""

import pytest
from argus.domain.ingestion.connections import InMemoryConnectionRepository

from tests.ingestion.connection_cases import *  # noqa: F403


@pytest.fixture
def repo():
    return InMemoryConnectionRepository()


@pytest.fixture
def users():
    return {"owner": "user-owner", "other": "user-other"}
