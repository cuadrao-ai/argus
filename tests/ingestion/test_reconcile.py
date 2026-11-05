"""Reconciliation over the in-memory store, held to the shared cases."""

import pytest

from tests.ingestion.reconcile_cases import *  # noqa: F403
from tests.ingestion.reconcile_review_cases import *  # noqa: F403
from tests.ingestion.reconcile_world import memory_pair


@pytest.fixture
def pair():
    return memory_pair()


@pytest.fixture
def world(pair):
    return pair[0]


@pytest.fixture
def other_world(pair):
    return pair[1]
