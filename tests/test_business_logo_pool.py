"""A slow logo body must leave the shared Business pool available to reads."""

import asyncio
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager, nullcontext
from threading import BoundedSemaphore
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.api.business import (
    BusinessContext,
    BusinessPerson,
    require_business_document_write,
    require_business_person,
)
from argus.api.routers import business, business_logo
from argus.domain.business.scope import BusinessScope
from argus.domain.connection_budget import BUSINESS_POOL_MAX
from argus.domain.owner_scope import BusinessSpace
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from psycopg_pool import PoolTimeout

from tests.profile_images.pictures import png


@pytest.mark.asyncio
async def test_stalled_logo_uploads_leave_the_same_pool_available_to_business_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = BoundedSemaphore(BUSINESS_POOL_MAX)
    release = asyncio.Event()
    stalled = [asyncio.Event() for _ in range(BUSINESS_POOL_MAX)]
    finished: set[int] = set()
    management_acquires: list[int] = []
    connection = Mock()
    connection.transaction.side_effect = nullcontext

    @contextmanager
    def pooled_connection() -> Iterator[Mock]:
        if not slots.acquire(timeout=0.25):
            raise PoolTimeout("Business pool exhausted")
        try:
            yield connection
        finally:
            slots.release()

    pool = Mock(connection=pooled_connection)
    scope = BusinessScope(
        person_id=str(uuid4()),
        owner=BusinessSpace(str(uuid4())),
        actor_id=str(uuid4()),
        grant_id=str(uuid4()),
    )
    context = BusinessContext(scope, Mock())

    def authorize(*args: object) -> Mock:
        management_acquires.append(len(finished))
        return Mock()

    monkeypatch.setattr("argus.domain.business.authority.authorize", authorize)
    monkeypatch.setattr(
        business_logo.PostgresAccessStore,
        "granted",
        lambda *args: Mock(permissions={"manage"}),
    )
    images = Mock()
    monkeypatch.setattr(business_logo, "require_profile_images", lambda *a, **k: images)
    payload = {
        "id": scope.owner.space_id,
        "name": None,
        "logo_url": None,
        "country": scope.country,
        "currency": scope.currency,
    }
    monkeypatch.setattr(business_logo, "_payload", lambda *a, **k: payload)

    # Run the real Business read handler, with its space store using the same pool.
    def read_space(*args: object) -> Mock:
        with pool.connection():
            return Mock(id=scope.owner.space_id)

    spaces = Mock(get=read_space)
    monkeypatch.setattr(business, "working_scope", lambda *a: scope)
    monkeypatch.setattr(business, "space_payload", lambda *a: payload)
    app = FastAPI()
    app.state.financial_accounts_pool = pool
    app.dependency_overrides[require_business_document_write] = lambda: context
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        scope.person_id, spaces
    )
    app.include_router(business_logo.router, prefix="/business")
    app.add_api_route("/business/space", business.get_space, methods=["GET"])

    @app.exception_handler(PoolTimeout)
    async def exhausted(request: Request, error: PoolTimeout) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=503)

    content = png()

    async def body(index: int):
        yield content[:8]
        stalled[index].set()
        await release.wait()
        finished.add(index)
        yield content[8:]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://local.test"
    ) as client:
        uploads = [
            asyncio.create_task(
                client.put(
                    "/business/logo",
                    content=body(index),
                    headers={"content-type": "image/png"},
                )
            )
            for index in range(BUSINESS_POOL_MAX)
        ]
        try:
            await asyncio.wait_for(
                asyncio.gather(*(event.wait() for event in stalled)), timeout=3
            )
            read = await asyncio.wait_for(client.get("/business/space"), timeout=3)
            assert read.status_code == 200, read.text
            assert read.json() == payload
            assert not finished
            assert not management_acquires
            images.replace.assert_not_called()
        finally:
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*uploads), timeout=3)

    assert all(result.status_code == 200 for result in results)
    assert len(management_acquires) == BUSINESS_POOL_MAX
    assert all(management_acquires)
    assert images.replace.call_count == BUSINESS_POOL_MAX
    for call in images.replace.call_args_list:
        assert call.args[1:] == (content, "image/png")
    # Every slot must be returned, including the management transaction lifetimes.
    with ExitStack() as stack:
        for _ in range(BUSINESS_POOL_MAX):
            stack.enter_context(pool.connection())
