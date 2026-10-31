from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import Field
from pydantic_settings import BaseSettings

from argus.api import app_setup, openapi_compat, pagination, search_utils
from argus.api import state as api_state
from argus.api.routers import (
    account,
    auth,
    auth_apple,
    computations,
    conversation_activity,
    conversations,
    decisions,
    dev,
    discovery,
    evidence,
    evidence_receipts,
    feedback,
    financial_accounts,
    history,
    household_financial,
    household_planning,
    households,
    internal_client_ip,
    market,
    ops,
    personalization_memory,
    profile,
    profile_apple_name,
    public_receipts,
    receipt_forks,
    search,
    tool_results,
)

cors_allow_origins = app_setup.cors_allow_origins
app = FastAPI(
    title="Argus Alpha API",
    version="1.0.0-alpha",
    lifespan=app_setup.lifespan,
)
app_setup.add_core_middleware_and_handlers(app)


class DeploymentMetadata(BaseSettings):
    git_sha: str | None = Field(default=None, validation_alias="RENDER_GIT_COMMIT")


@app.get("/health")
def health() -> dict[str, str | None]:
    commit = DeploymentMetadata().git_sha
    return {
        "status": "healthy",
        "version": "1.0.0-alpha",
        "git_sha": commit
        if commit and re.fullmatch(r"[0-9a-fA-F]{40}", commit)
        else None,
    }


for api_router in (
    auth.router,
    auth_apple.router,
    profile.router,
    profile_apple_name.router,
    conversations.router,
    computations.router,
    tool_results.router,
    conversation_activity.router,
    evidence.router,
    decisions.router,
    evidence_receipts.router,
    public_receipts.router,
    receipt_forks.router,
    history.router,
    search.router,
    discovery.router,
    market.router,
    personalization_memory.router,
    financial_accounts.router,
    households.router,
    household_financial.router,
    household_planning.router,
    feedback.router,
    account.router,
    ops.router,
    internal_client_ip.router,
    dev.router,
):
    app.include_router(api_router)


def _custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    document = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    app.openapi_schema = openapi_compat.customize_openapi_document(document)
    return app.openapi_schema


app.openapi = _custom_openapi  # type: ignore[method-assign]


store = api_state.store
supabase_gateway = api_state.supabase_gateway
_encode_cursor = pagination.encode_cursor
_decode_cursor = pagination.decode_cursor
_search_type_rank = search_utils.search_type_rank
_score_search_item = search_utils.score_search_item
