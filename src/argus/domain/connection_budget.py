"""Modeled API/worker pool and checkpointer clients during a deploy.

The hosted pooler is in session mode and allows 15 clients. A deploy keeps the
previous API process and the previous document worker until the new ones are
up. The worker's drain holds its clients for that overlap. The checkpointer
holds one client for the life of an API process when durable mode is on.
Transient direct signup and maintenance connections are outside this pool budget.
"""

from __future__ import annotations

POOLER_SESSION_CLIENTS = 15
DEPLOY_GENERATIONS = 2
CHECKPOINTER_CONNECTIONS = 1
WORKER_CONNECTIONS = 3
API_CONNECTIONS = (POOLER_SESSION_CLIENTS // DEPLOY_GENERATIONS) - WORKER_CONNECTIONS
BUSINESS_POOL_MAX = 2
SESSION_POOL_MAX = API_CONNECTIONS - CHECKPOINTER_CONNECTIONS - BUSINESS_POOL_MAX


def deploy_client_ceiling() -> int:
    """Clients if both generations sit at their cap."""

    return DEPLOY_GENERATIONS * (API_CONNECTIONS + WORKER_CONNECTIONS)


def worker_pool_max(max_reads: int) -> int:
    """One client per in-flight read, and never more than the worker's share."""

    return min(max_reads, WORKER_CONNECTIONS)
