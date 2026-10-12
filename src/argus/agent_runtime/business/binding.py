from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from argus.agent_runtime.business.interpretation import BusinessInterpretation
from argus.domain.business.actions.dossier import blockers
from argus.domain.business.contracts.actions import (
    Ask,
    AttachSource,
    BoundDraft,
    BusinessAction,
    DraftReference,
    ExplainStatus,
    FindRelated,
    PlannedDraft,
    ProposeActivity,
    ProposeAllocation,
    ReadContext,
    TurnPlan,
)
from argus.domain.business.contracts.dossier import AccountChoice, ReviewQuestion
from argus.domain.business.contracts.facts import BusinessFacts


class BusinessBindingError(ValueError):
    pass


@dataclass(frozen=True)
class BusinessBindingSnapshot:
    draft_versions: tuple[tuple[UUID, int], ...]
    questions: tuple[ReviewQuestion, ...]


def capture_business_snapshot(snapshot: dict[str, Any]) -> BusinessBindingSnapshot:
    versions: dict[UUID, int] = {}
    for row in snapshot["drafts"]:
        draft_id = UUID(str(row["id"]))
        version = row["version"]
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version < 1
            or draft_id in versions
        ):
            raise BusinessBindingError("business_context_draft_invalid")
        versions[draft_id] = version
    return BusinessBindingSnapshot(
        draft_versions=tuple(versions.items()),
        questions=tuple(
            ReviewQuestion.model_validate(row) for row in snapshot["questions"]
        ),
    )


def model_business_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    accounts = tuple(AccountChoice.model_validate(row) for row in snapshot["accounts"])

    def without_sources(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: without_sources(item)
                for key, item in value.items()
                if key != "source_ids"
            }
        if isinstance(value, (list, tuple)):
            return [without_sources(item) for item in value]
        return value

    return {
        **snapshot,
        "required_fact_fields": [
            blocker.field
            for blocker in blockers(BusinessFacts(), accounts)
            if blocker.code == "fact_required"
        ],
        "drafts": [
            {
                "id": row["id"],
                "facts": without_sources(row.get("facts", {})),
                "blockers": [
                    blocker.model_dump(mode="json")
                    for blocker in blockers(
                        BusinessFacts.model_validate(row.get("facts", {})), accounts
                    )
                ],
            }
            for row in snapshot["drafts"]
        ],
        "questions": [
            {
                key: value
                for key, value in row.items()
                if key not in {"id", "answer_source_id"}
            }
            for row in snapshot["questions"]
        ],
    }


def _answer_question(
    snapshot: BusinessBindingSnapshot, draft_id: UUID | None, patch: Any
) -> UUID | None:
    if draft_id is None:
        return None
    matches = []
    for row in snapshot.questions:
        if (
            row.draft_id != draft_id
            or row.asked_of != "owner"
            or row.state not in {"open", "waiting_for_window"}
        ):
            continue
        value = getattr(patch, row.field, None)
        if value is not None and value.state in {"known", "owner_does_not_know"}:
            matches.append(row.id)
    if len(matches) > 1:
        raise BusinessBindingError("business_answer_question_ambiguous")
    return matches[0] if matches else None


def compile_business_plan(
    interpretation: BusinessInterpretation,
    *,
    snapshot: BusinessBindingSnapshot,
    source_id: UUID,
) -> TurnPlan:
    versions = dict(snapshot.draft_versions)
    actions: list[BusinessAction] = [ReadContext()] if interpretation.read_context else []
    selected: set[UUID] = set()
    for record in interpretation.records:
        reference: DraftReference | None
        draft_id = record.target_draft_id
        mutable = bool(
            record.facts is not None
            or record.allocation is not None
            or record.question is not None
            or record.attach_current_source
        )
        if draft_id is not None:
            if draft_id in selected:
                raise BusinessBindingError("business_target_repeated")
            selected.add(draft_id)
            if mutable:
                if draft_id not in versions:
                    raise BusinessBindingError("business_target_not_in_context")
                reference = BoundDraft(draft_id=draft_id, base_version=versions[draft_id])
            else:
                reference = None
        else:
            if record.facts is None or record.find_related or record.explain_status:
                raise BusinessBindingError("business_new_target_requires_facts")
            reference = None
        if record.facts is not None:
            if record.allocation is not None and (
                record.facts.funding is not None
                or record.facts.business_share is not None
            ):
                raise BusinessBindingError("business_allocation_overlaps_facts")
            created_index = len(actions)
            actions.append(
                ProposeActivity(
                    draft=reference,
                    facts=record.facts,
                    source_ids=(source_id,),
                    answers_question_id=_answer_question(
                        snapshot, draft_id, record.facts
                    ),
                )
            )
            if draft_id is None:
                reference = PlannedDraft(from_action=created_index)
        if record.allocation is not None:
            actions.append(
                ProposeAllocation(
                    draft=reference,
                    funding=record.allocation.funding,
                    business_share=record.allocation.business_share,
                    source_ids=(source_id,),
                    answers_question_id=_answer_question(
                        snapshot, draft_id, record.allocation
                    ),
                )
            )
        if record.attach_current_source:
            actions.append(AttachSource(draft=reference, source_id=source_id))
        if record.find_related:
            actions.append(FindRelated(draft_id=draft_id))
        if record.question is not None:
            actions.append(Ask(draft=reference, **record.question.model_dump()))
        if record.explain_status:
            actions.append(ExplainStatus(draft_id=draft_id))
        if not mutable and not record.find_related and not record.explain_status:
            raise BusinessBindingError("business_record_intent_empty")
    return TurnPlan(actions=tuple(actions))
