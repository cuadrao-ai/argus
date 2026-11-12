from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langgraph.graph import END, StateGraph

from argus.agent_runtime.state.models import ConversationMessage, RunState, UserState

_MAX_RECENT_THREAD_HISTORY = 6


def business_workflow_input(
    *,
    user: UserState,
    message: str,
    recent_thread_history: Iterable[ConversationMessage | dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_message = " ".join(message.strip().split())
    history = list(recent_thread_history or [])[:_MAX_RECENT_THREAD_HISTORY]
    run_state = RunState.new(
        current_user_message=normalized_message,
        recent_thread_history=history,
    )
    return {"run_state": run_state, "user": user}


def build_business_workflow(stages: Any) -> Any:
    async def interpret_node(state: dict[str, Any]) -> dict[str, Any]:
        return await stages.interpret(state)

    async def execute_node(state: dict[str, Any]) -> dict[str, Any]:
        return await stages.execute(state)

    def route(state: dict[str, Any]) -> str:
        if state.get("stage_outcome") == "approved_for_execution":
            return "execute"
        return END

    graph: StateGraph = StateGraph(dict)
    graph.add_node("interpret", interpret_node)
    graph.add_node("execute", execute_node)
    graph.set_entry_point("interpret")
    graph.add_conditional_edges("interpret", route, {"execute": "execute", END: END})
    graph.add_edge("execute", END)
    return graph.compile()
