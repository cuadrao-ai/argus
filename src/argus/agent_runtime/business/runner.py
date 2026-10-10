from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID, uuid4

from argus.agent_runtime.business.context import AuthorizedBusinessContext
from argus.agent_runtime.business.stages import BusinessStages
from argus.agent_runtime.graph.workflow import build_workflow
from argus.agent_runtime.runtime import build_workflow_input
from argus.agent_runtime.state.models import ConversationMessage, UserState
from argus.domain.business.contracts.facts import Contract
from argus.domain.business.contracts.recovery import DurableTurn


class BusinessTurnResult(Contract):
    graph_run_id: UUID
    plan: dict[str, Any]
    tool_records: tuple[dict[str, Any], ...]
    saved_state: dict[str, Any]
    reply_text: str


class BusinessTurnRunner:
    def __init__(self, *, interpreter: Any = None, model_name: str | None = None) -> None:
        if interpreter is None:
            from argus.agent_runtime.capabilities.contract import (
                build_default_capability_contract,
            )
            from argus.agent_runtime.llm_interpreter import (
                OpenRouterStructuredInterpreter,
            )

            interpreter = OpenRouterStructuredInterpreter(
                contract=build_default_capability_contract(), model_name=model_name
            )
        self.interpreter = interpreter

    async def run(
        self,
        *,
        context: AuthorizedBusinessContext,
        turn: DurableTurn,
        message: str,
        history: Iterable[ConversationMessage | dict[str, Any]] = (),
    ) -> BusinessTurnResult:
        if (
            turn.turn_key != context.turn_key
            or turn.actor_id != context.authorization.actor.actor_id
            or turn.space_id != context.authorization.actor.space_id
            or turn.sender_hash != context.lease.sender_hash
            or turn.lease_fence != context.lease.fence
        ):
            raise ValueError(
                "Business runtime context must bind the claimed durable turn"
            )
        stages = BusinessStages(context, self.interpreter, message)
        workflow = build_workflow(business_runtime=stages)
        graph_run_id = uuid4()
        state = await workflow.ainvoke(
            build_workflow_input(
                user=UserState(
                    user_id=str(turn.actor_id),
                    language_preference=context.language,
                ),
                message=message,
                recent_thread_history=history,
            ),
            config={"configurable": {"thread_id": turn.turn_key}, "run_id": graph_run_id},
        )
        records = tuple(
            record.model_dump(mode="json")
            for record in state["run_state"].tool_call_records
        )
        saved_state = context.actions.read_context(context.authorization)
        touched_ids = {
            record["tool_outcome"]["result"]["outcome"]["draft_id"]
            for record in records
            if record["tool_outcome"]["status"] == "succeeded"
            and record["tool_outcome"]["result"]["outcome"].get("draft_id")
        }
        if touched_ids:
            saved_state["dossiers"] = [
                context.actions.dossier(context.authorization, UUID(draft_id)).model_dump(
                    mode="json"
                )
                for draft_id in sorted(touched_ids)
            ]
        reply = context.begin_reply()
        if reply is None:
            reply = await self.interpreter.acompose_business(
                {
                    "message": message,
                    "language": context.language,
                    "plan": state["business_plan"],
                    "tool_records": records,
                    "saved_state": saved_state,
                }
            )
        return BusinessTurnResult(
            graph_run_id=graph_run_id,
            plan=state["business_plan"],
            tool_records=records,
            saved_state=saved_state,
            reply_text=reply,
        )
