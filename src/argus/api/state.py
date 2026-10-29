from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from argus.api.chat.backtest_jobs import (
    ShadowBacktestJobTool,
    backtest_workflow_execution_enabled,
)
from argus.domain.store import AlphaStore
from argus.domain.supabase_gateway import SupabaseGateway
from argus.env import load_project_dotenv

load_project_dotenv()

PERSISTENCE_MODE = os.getenv("CUADRAO_PERSISTENCE_MODE", "memory").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
CHECKPOINTER_MODE = os.getenv("CUADRAO_CHECKPOINTER_MODE", "").strip().lower()
if not CHECKPOINTER_MODE:
    CHECKPOINTER_MODE = (
        "postgres" if PERSISTENCE_MODE == "supabase" and DATABASE_URL else "memory"
    )
store = AlphaStore()
supabase_gateway = SupabaseGateway.from_env() if PERSISTENCE_MODE == "supabase" else None


def _dev_memory_fallback_enabled() -> bool:
    return os.getenv("ARGUS_DEV_MEMORY_FALLBACK", "").strip().lower() == "true"


def build_backtest_tool() -> ShadowBacktestJobTool:
    delegate: Any | None = None
    if not backtest_workflow_execution_enabled():
        from argus.agent_runtime.tools.real_backtest import RealBacktestTool

        delegate = RealBacktestTool()

    return ShadowBacktestJobTool(
        delegate=delegate,
        gateway_getter=lambda: supabase_gateway,
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


def build_agent_runtime_checkpoint_serde() -> JsonPlusSerializer:
    # Runtime checkpoints are process-local and may include Pydantic state
    # objects that LangGraph's default msgpack serializer cannot encode.
    return JsonPlusSerializer(
        pickle_fallback=True,
        allowed_msgpack_modules=[
            ("argus.agent_runtime.state.models", "ArtifactReference"),
            ("argus.agent_runtime.state.models", "ConfirmationPayload"),
            ("argus.agent_runtime.state.models", "ConversationMessage"),
            ("argus.agent_runtime.state.models", "FinalResponsePayload"),
            ("argus.agent_runtime.state.models", "ResolutionProvenance"),
            ("argus.agent_runtime.state.models", "ResponseIntent"),
            ("argus.agent_runtime.state.models", "ResponseProfile"),
            ("argus.agent_runtime.state.models", "ResponseProfileOverrides"),
            ("argus.agent_runtime.graph.workflow", "WorkflowStageOutcome"),
            ("argus.agent_runtime.state.models", "RunState"),
            ("argus.agent_runtime.state.models", "StrategySummary"),
            ("argus.agent_runtime.state.models", "StructuredActionContext"),
            ("argus.agent_runtime.state.models", "TaskSnapshot"),
            ("argus.agent_runtime.state.models", "ToolCallRecord"),
            ("argus.agent_runtime.state.models", "UserState"),
            ("argus.agent_runtime.state.models", "UnsupportedConstraint"),
        ],
    )


def build_agent_runtime_checkpointer() -> MemorySaver:
    return MemorySaver(serde=build_agent_runtime_checkpoint_serde())


def get_agent_runtime_workflow(request: Request | None = None):
    target_app = request.app if request is not None else None
    if target_app is None:
        checkpointer = build_agent_runtime_checkpointer()
        return build_agent_runtime_workflow(checkpointer=checkpointer)

    workflow = getattr(target_app.state, "agent_runtime_workflow", None)
    if workflow is None:
        checkpointer = getattr(target_app.state, "agent_runtime_checkpointer", None)
        if checkpointer is None:
            checkpointer = build_agent_runtime_checkpointer()
            target_app.state.agent_runtime_checkpointer = checkpointer
        workflow = build_agent_runtime_workflow(checkpointer=checkpointer)
        target_app.state.agent_runtime_workflow = workflow
    return workflow


@asynccontextmanager
async def isolated_agent_runtime_workflow() -> AsyncIterator[Any]:
    if CHECKPOINTER_MODE == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(
            DATABASE_URL,
            serde=build_agent_runtime_checkpoint_serde(),
        ) as checkpointer:
            await checkpointer.setup()
            yield build_agent_runtime_workflow(checkpointer=checkpointer)
        return

    checkpointer = build_agent_runtime_checkpointer()
    yield build_agent_runtime_workflow(checkpointer=checkpointer)


def reset_agent_runtime_workflow(app: FastAPI) -> None:
    checkpointer = build_agent_runtime_checkpointer()
    app.state.agent_runtime_checkpointer = checkpointer
    app.state.agent_runtime_workflow = build_agent_runtime_workflow(
        checkpointer=checkpointer
    )
