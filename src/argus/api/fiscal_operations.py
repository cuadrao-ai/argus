"""Fiscal recovery uses the existing API lifespan and durable pool."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException, Request
from loguru import logger

from argus.domain.business.fiscal_sandbox.config import Settings
from argus.domain.business.fiscal_sandbox.provider import Provider
from argus.domain.business.fiscal_sandbox.service import Service
from argus.domain.business.fiscal_sandbox.store import Store


def fiscal_service(request: Request) -> Service | None:
    """The one read of whether fiscal issuance is wired in this process."""
    return getattr(request.app.state, "fiscal_sandbox", None)


def require_fiscal(request: Request) -> Service:
    service = fiscal_service(request)
    if service is None:
        raise HTTPException(
            404,
            detail="fiscal_sandbox_unavailable",
            headers={"Cache-Control": "no-store"},
        )
    return service


async def _recover(service: Service) -> None:
    while True:
        try:
            await service.reconcile()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never log raw provider exceptions, signed URLs, or SQL parameters.
            logger.warning("Fiscal sandbox recovery unavailable")
        await asyncio.sleep(service.settings.poll_seconds)


def start_fiscal(app: FastAPI) -> None:
    settings = Settings()
    if not settings.enabled:
        return
    pool = getattr(app.state, "financial_accounts_pool", None)
    if pool is None:
        raise RuntimeError("fiscal_durable_store_required")
    cases = settings.cases()
    service = Service(Store(pool), Provider(settings), settings, cases)
    app.state.fiscal_sandbox = service
    app.state.fiscal_sandbox_task = asyncio.create_task(_recover(service))


async def stop_fiscal(app: FastAPI) -> None:
    task = getattr(app.state, "fiscal_sandbox_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    app.state.fiscal_sandbox = None
