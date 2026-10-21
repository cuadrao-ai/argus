from __future__ import annotations

from dataclasses import dataclass
from typing import Any, get_type_hints

from argus.domain.business.contracts.actions import (
    Applied,
    Ask,
    AttachSource,
    ExplainStatus,
    FindRelated,
    ProposeActivity,
    ProposeAllocation,
    ReadContext,
    TurnPlan,
)
from argus.domain.business.contracts.facts import Contract
from argus.domain.tool_contracts import LocalizedText, ToolCardPresentation, ToolOutcome
from argus.domain.tool_declaration import (
    ToolCardBinding,
    ToolDeclaration,
    ToolInvocationError,
    ToolPolicy,
    ToolProgressTemplate,
)


class BusinessToolResult(Contract):
    outcome: dict[str, Any]
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class BusinessToolBinding:
    authorized: Any
    plan: TurnPlan
    action_index: int


def _execute(arguments: Contract, context: Any) -> BusinessToolResult:
    binding = getattr(context, "business", None)
    if not isinstance(binding, BusinessToolBinding):
        raise ToolInvocationError("invalid", code="business_context_required")
    authorized = binding.authorized
    action = binding.plan.actions[binding.action_index]
    if action.model_dump(mode="json") != arguments.model_dump(mode="json"):
        raise ToolInvocationError("invalid", code="business_plan_action_mismatch")
    outcome = authorized.actions.execute(
        authorized.authorization,
        authorized.turn_key,
        binding.action_index,
        lease=authorized.lease,
    )
    if not isinstance(outcome, Applied):
        status = "unavailable" if outcome.outcome == "outcome_unknown" else "invalid"
        raise ToolInvocationError(status, code=outcome.code)
    data = None
    if isinstance(action, ReadContext):
        data = authorized.actions.read_context(authorized.authorization)
    elif isinstance(action, FindRelated):
        data = authorized.actions.find_related(authorized.authorization, action.draft_id)
    elif isinstance(action, ExplainStatus):
        data = authorized.actions.dossier(
            authorized.authorization, action.draft_id
        ).model_facing()
    return BusinessToolResult(outcome=outcome.model_dump(mode="json"), data=data)


def read_context(arguments: ReadContext, *, context: Any) -> BusinessToolResult:
    return _execute(arguments, context)


def propose_activity(arguments: ProposeActivity, *, context: Any) -> BusinessToolResult:
    return _execute(arguments, context)


def attach_source(arguments: AttachSource, *, context: Any) -> BusinessToolResult:
    return _execute(arguments, context)


def propose_allocation(
    arguments: ProposeAllocation, *, context: Any
) -> BusinessToolResult:
    return _execute(arguments, context)


def find_related(arguments: FindRelated, *, context: Any) -> BusinessToolResult:
    return _execute(arguments, context)


def ask(arguments: Ask, *, context: Any) -> BusinessToolResult:
    return _execute(arguments, context)


def explain_status(arguments: ExplainStatus, *, context: Any) -> BusinessToolResult:
    return _execute(arguments, context)


def _present(arguments: Any, outcome: ToolOutcome) -> ToolCardPresentation:
    return ToolCardPresentation(title=LocalizedText(locale_key="business.action"))


def get_business_declarations() -> tuple[ToolDeclaration, ...]:
    return tuple(
        ToolDeclaration(
            name=get_type_hints(handler)["arguments"].model_fields["action"].default,
            description=description,
            handler=handler,
            policy=ToolPolicy(),
            progress=ToolProgressTemplate(locale_key="business.action"),
            card=ToolCardBinding(
                card_type="business_action", version=1, presenter=_present
            ),
            domain=("business",),
            surfaces=frozenset({"business"}),
        )
        for handler, description in (
            (read_context, "Read authorized Business drafts, questions and accounts."),
            (
                propose_activity,
                "Prepare or revise a sourced activity draft without recording money.",
            ),
            (
                attach_source,
                "Attach an existing immutable source to an exact draft revision.",
            ),
            (
                propose_allocation,
                "Propose stated funding and business share for an exact revision.",
            ),
            (find_related, "Find related records inside this authorized Business."),
            (ask, "Ask a factual question about the draft, to owner or accountant."),
            (
                explain_status,
                "Read the canonical draft dossier and explain its saved status.",
            ),
        )
    )
