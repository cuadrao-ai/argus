from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request

from argus.api import state as api_state
from argus.api.chat.backtest_jobs import (
    ShadowBacktestJobTool,
    backtest_workflow_execution_enabled,
)


def _dev_memory_fallback_enabled() -> bool:
    return os.getenv("ARGUS_DEV_MEMORY_FALLBACK", "").strip().lower() == "true"


def build_backtest_tool() -> ShadowBacktestJobTool:
    delegate: Any | None = None
    if not backtest_workflow_execution_enabled():
        from argus.agent_runtime.tools.real_backtest import RealBacktestTool

        delegate = RealBacktestTool()

    return ShadowBacktestJobTool(
        delegate=delegate,
        gateway_getter=lambda: api_state.supabase_gateway,
        dev_memory_fallback_getter=_dev_memory_fallback_enabled,
    )


def build_agent_runtime_workflow(*, checkpointer: Any):
    from argus.agent_runtime.capabilities.contract import (
        build_default_capability_contract,
    )
    from argus.agent_runtime.graph.workflow import build_workflow
    from argus.agent_runtime.llm_clarifier import OpenRouterClarificationGenerator
    from argus.agent_runtime.llm_interpreter import OpenRouterStructuredInterpreter

    agent_runtime_capability_contract = build_default_capability_contract()
    return build_workflow(
        contract=agent_runtime_capability_contract,
        tool=build_backtest_tool(),
        structured_interpreter=OpenRouterStructuredInterpreter(
            contract=agent_runtime_capability_contract,
        ),
        clarification_generator=OpenRouterClarificationGenerator(),
        checkpointer=checkpointer,
    )


def get_agent_runtime_workflow(request: Request | None = None):
    target_app = request.app if request is not None else None
    if target_app is None:
        checkpointer = api_state.build_agent_runtime_checkpointer()
        return build_agent_runtime_workflow(checkpointer=checkpointer)

    workflow = getattr(target_app.state, "agent_runtime_workflow", None)
    if workflow is None:
        checkpointer = getattr(target_app.state, "agent_runtime_checkpointer", None)
        if checkpointer is None:
            checkpointer = api_state.build_agent_runtime_checkpointer()
            target_app.state.agent_runtime_checkpointer = checkpointer
        workflow = build_agent_runtime_workflow(checkpointer=checkpointer)
        target_app.state.agent_runtime_workflow = workflow
    return workflow


@asynccontextmanager
async def isolated_agent_runtime_workflow() -> AsyncIterator[Any]:
    if api_state.CHECKPOINTER_MODE == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(
            api_state.DATABASE_URL,
            serde=api_state.build_agent_runtime_checkpoint_serde(),
        ) as checkpointer:
            await checkpointer.setup()
            yield build_agent_runtime_workflow(checkpointer=checkpointer)
        return

    checkpointer = api_state.build_agent_runtime_checkpointer()
    yield build_agent_runtime_workflow(checkpointer=checkpointer)


def reset_agent_runtime_workflow(app: FastAPI) -> None:
    checkpointer = api_state.build_agent_runtime_checkpointer()
    app.state.agent_runtime_checkpointer = checkpointer
    app.state.agent_runtime_workflow = build_agent_runtime_workflow(
        checkpointer=checkpointer
    )
