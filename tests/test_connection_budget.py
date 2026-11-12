"""The deploy overlap stays inside the session pooler."""

from argus.domain.connection_budget import (
    API_CONNECTIONS,
    BUSINESS_POOL_MAX,
    CHECKPOINTER_CONNECTIONS,
    DEPLOY_GENERATIONS,
    POOLER_SESSION_CLIENTS,
    SESSION_POOL_MAX,
    WORKER_CONNECTIONS,
    deploy_client_ceiling,
    worker_pool_max,
)


def test_two_generations_stay_inside_the_session_pooler() -> None:
    assert SESSION_POOL_MAX == 1
    assert BUSINESS_POOL_MAX == 2
    assert CHECKPOINTER_CONNECTIONS + SESSION_POOL_MAX + BUSINESS_POOL_MAX == API_CONNECTIONS
    assert worker_pool_max(3) == WORKER_CONNECTIONS
    assert worker_pool_max(10) == WORKER_CONNECTIONS
    assert deploy_client_ceiling() == DEPLOY_GENERATIONS * (API_CONNECTIONS + WORKER_CONNECTIONS)
    assert deploy_client_ceiling() <= POOLER_SESSION_CLIENTS
    assert deploy_client_ceiling() == 14
