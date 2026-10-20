from __future__ import annotations

from collections.abc import Iterable
from contextlib import nullcontext
from typing import Any
from uuid import UUID, uuid4

from argus.agent_runtime.business.context import AuthorizedBusinessContext
from argus.agent_runtime.business.interpretation import (
    BUSINESS_MODEL_CANDIDATES,
    BusinessInterpretation,
    BusinessReply,
)
from argus.agent_runtime.business.stages import BusinessStages
from argus.agent_runtime.graph.workflow import build_workflow
from argus.agent_runtime.runtime import build_workflow_input
from argus.agent_runtime.state.models import ConversationMessage, UserState
from argus.domain.business.contracts.facts import Contract
from argus.domain.business.contracts.recovery import DurableTurn
from argus.llm.openrouter import (
    openrouter_profile_for_task,
    openrouter_request_guard,
    openrouter_schema_payload,
    openrouter_structured_model_candidates,
)
from argus.llm.openrouter_request_policy import (
    openrouter_payload_route,
    validate_openrouter_route,
)

#: Person-entered facts the reply model is not shown until a scorecard measures them.
_UNMEASURED_DOSSIER_FIELDS = {
    "due_on": True,
    "history": {"__all__": {"before_due_on", "after_due_on"}},
}


class BusinessTurnResult(Contract):
    graph_run_id: UUID
    plan: dict[str, Any]
    tool_records: tuple[dict[str, Any], ...]
    saved_state: dict[str, Any]
    reply_text: str


def business_provider_route(model_name: str | None = None) -> dict[str, Any]:
    model = model_name or BUSINESS_MODEL_CANDIDATES[0]
    if model not in BUSINESS_MODEL_CANDIDATES:
        raise ValueError("Business runtime model is not an authorized candidate")
    return {
        "gateway": "openrouter",
        **{
            role: [
                openrouter_payload_route(
                    openrouter_schema_payload(
                        model=candidate,
                        messages=[],
                        schema_model=schema,
                        schema_name=schema.__name__,
                        profile=openrouter_profile_for_task("interpretation"),
                    )
                )
                for candidate in openrouter_structured_model_candidates(
                    model, task="interpretation"
                )
            ]
            for role, schema in (
                ("interpretation", BusinessInterpretation),
                ("reply", BusinessReply),
            )
        },
    }


class BusinessTurnRunner:
    def __init__(self, *, interpreter: Any = None, model_name: str | None = None) -> None:
        self.interpreter = interpreter
        self.model_name = model_name

    def _interpreter(self) -> Any:
        if self.interpreter is None:
            from argus.agent_runtime.capabilities.contract import (
                build_default_capability_contract,
            )
            from argus.agent_runtime.llm_interpreter import (
                OpenRouterStructuredInterpreter,
            )

            self.interpreter = OpenRouterStructuredInterpreter(
                contract=build_default_capability_contract(), model_name=self.model_name
            )
        return self.interpreter

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
        context.check_access()
        interpreter = self._interpreter()
        guard = nullcontext()
        if context.channel == "whatsapp":
            route = business_provider_route(getattr(interpreter, "model_name", None))

            def check_request(task: str, payload: dict[str, object]) -> dict[str, object]:
                if task != "interpretation":
                    raise PermissionError("business_provider_task_not_disclosed")
                validate_openrouter_route(
                    payload, route["interpretation"] + route["reply"]
                )
                context.check_access()
                return payload

            guard = openrouter_request_guard(check_request, final=True)
        with guard:
            return await self._run(
                context=context,
                turn=turn,
                message=message,
                history=history,
                interpreter=interpreter,
            )

    async def _run(
        self,
        *,
        context: AuthorizedBusinessContext,
        turn: DurableTurn,
        message: str,
        history: Iterable[ConversationMessage | dict[str, Any]],
        interpreter: Any,
    ) -> BusinessTurnResult:
        stages = BusinessStages(context, interpreter, message)
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
        context.check_access()
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
                    mode="json", exclude=_UNMEASURED_DOSSIER_FIELDS
                )
                for draft_id in sorted(touched_ids)
            ]
        context.check_access()
        reply = context.begin_reply()
        if reply is None:
            context.check_access()
            reply = await interpreter.acompose_business(
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
