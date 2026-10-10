from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from argus.agent_runtime.business.context import AuthorizedBusinessContext
from argus.agent_runtime.business.interpretation import BusinessInterpretation
from argus.agent_runtime.stages.tool_execution import execute_tool_calls_async
from argus.agent_runtime.state.models import RunState
from argus.domain.business.contracts.dossier import MessageSource
from argus.domain.business.tools.declarations import BusinessToolBinding
from argus.domain.capability_registry import get_tool_catalog
from argus.domain.tool_contracts import ToolCall


class BusinessStages:
    def __init__(
        self,
        context: AuthorizedBusinessContext,
        interpreter: Any,
        message: str,
    ) -> None:
        self.context = context
        self.message = message
        self.interpreter = interpreter
        self.plan = None
        self.interpretation = None

    async def interpret(self, state: dict[str, Any]) -> dict[str, Any]:
        context = self.context
        self.plan = context.actions.plan_for_turn(
            context.authorization, context.turn_key, lease=context.lease
        )
        source_id = context.actions.record_source(
            context.authorization,
            f"message:{context.channel}:{context.message_id}",
            MessageSource(
                id=context.message_id,
                kind="message",
                channel=context.channel,
                received_at=context.received_at,
                text=self.message,
            ),
        )
        if self.plan is None:
            message = self.message
            payload = {
                "message": message,
                "source_id": str(source_id),
                "language": context.language,
                "received_at": context.received_at.isoformat(),
                "business": context.actions.read_context(context.authorization),
                "history": [
                    item.model_dump(mode="json")
                    for item in state["run_state"].recent_thread_history
                ],
            }
            self.interpretation = BusinessInterpretation.model_validate(
                await self.interpreter.ainterpret_business(payload)
            )
            self.plan = context.actions.persist_plan(
                context.authorization,
                context.turn_key,
                self.interpretation.plan,
                lease=context.lease,
            )
        calls = [
            ToolCall(
                tool_name=action.action,
                call_id=str(uuid5(NAMESPACE_URL, f"{context.turn_key}:{index}")),
                arguments=action.model_dump(mode="json"),
            )
            for index, action in enumerate(self.plan.actions)
        ]
        return {
            **state,
            "run_state": state["run_state"].model_copy(update={"tool_calls": calls}),
            "stage_outcome": "approved_for_execution",
        }

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        assert self.plan is not None
        result = await execute_tool_calls_async(
            state=state["run_state"],
            tool=None,
            catalog=get_tool_catalog(surface="business"),
            language=self.context.language,
            user=state["user"],
            business_bindings=tuple(
                BusinessToolBinding(self.context, self.plan, index)
                for index in range(len(self.plan.actions))
            ),
        )
        return {
            **state,
            **result.patch,
            "run_state": RunState.model_validate(
                {
                    **state["run_state"].model_dump(mode="python"),
                    "tool_calls": [],
                    "tool_call_records": result.patch["tool_call_records"],
                }
            ),
            "business_plan": self.plan.model_dump(mode="json"),
            "stage_outcome": "end_run",
        }
