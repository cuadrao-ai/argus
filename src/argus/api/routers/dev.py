from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from argus.api import state as api_state
from argus.api.dependencies import dev_memory_fallback_enabled
from argus.api.schemas import SuccessResponse

router = APIRouter(prefix="/api/v1", tags=["dev"])


def dev_endpoints_enabled() -> bool:
    return (
        os.getenv("ARGUS_DEV_ENDPOINTS_ENABLED", "").strip().lower() == "true"
        or os.getenv("CUADRAO_MOCK_AUTH", "").strip().lower() == "true"
        or os.getenv("NEXT_PUBLIC_MOCK_AUTH", "").strip().lower() == "true"
    )


@router.post("/dev/reset", response_model=SuccessResponse)
def dev_reset(request: Request) -> SuccessResponse:
    if not dev_endpoints_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    api_state.store.reset()
    if api_state.supabase_gateway is not None:
        try:
            api_state.supabase_gateway.reset_dev_data()
        except Exception:
            if not dev_memory_fallback_enabled():
                raise
    if api_state.CHECKPOINTER_MODE != "postgres":
        api_state.reset_agent_runtime_workflow(request.app)
    api_state.store.get_or_create_dev_user()
    return SuccessResponse(success=True)
