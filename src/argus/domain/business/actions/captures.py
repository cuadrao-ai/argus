from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from argus.domain.business.actions import mutations, plans, sources
from argus.domain.business.actions.facts import facts_of
from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.contracts.actions import (
    ActionOutcome,
    CaptureCommand,
    CaptureNote,
)
from argus.domain.business.contracts.dossier import MessageSource
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.transactions import transaction

if TYPE_CHECKING:
    from argus.domain.business.actions.service import BusinessActions


def capture(
    service: BusinessActions, context: ActionContext, request: CaptureNote, key: str
) -> ActionOutcome:
    command = CaptureCommand(request=request)
    try:
        with transaction(service.authority, context, "prepare") as tx:
            if context.actor.actor_kind != "member":
                raise ActionError("permission_denied", "business_human_command_required")
            saved = plans.receipt(tx, key, command)
            if saved is not None:
                return plans.replay(saved)
            plans.start_receipt(tx, key, command)
            try:
                with tx.connection.transaction():
                    now = datetime.now(timezone.utc)
                    if request.draft is None:
                        event = mutations.new_candidate(context.owner_id, now)
                        before = None
                        after = BusinessFacts(
                            currency=Known(value="DOP", origin="default", source_ids=())
                        )
                    else:
                        event = mutations.event_at(tx, request.draft)
                        before = after = facts_of(event)
                        event = replace(event, version=event.version + 1, updated_at=now)
                    evidence = MessageSource(
                        id=uuid4(),
                        kind="message",
                        channel="web",
                        received_at=now,
                        text=request.text,
                    )
                    source_id = sources.record_source(
                        tx, f"capture:{context.actor.actor_id}:{key}", evidence
                    )
                    result = mutations.save_revision(
                        tx,
                        event,
                        before,
                        after,
                        (source_id,),
                        tx.authorization.provenance,
                        None,
                    )
            except ActionError as error:
                result = error.result
            return plans.finish_receipt(tx, key, result)
    except ActionError as error:
        return error.result


def entries(
    service: BusinessActions, context: ActionContext, *, query: str = "", limit: int = 20
) -> list[dict]:
    if "\x00" in query or len(query) > 200 or not 1 <= limit <= 50:
        raise ActionError("invalid_input", "business_capture_query_invalid")
    with transaction(service.authority, context) as tx:
        return tx.rows(
            "select e.id as draft_id,e.version,v.version as revision,s.id as source_id,"
            " s.text_content as text,s.received_at,e.state as review_state"
            " from public.business_action_receipts r"
            " join public.financial_import_events e on e.id::text=r.outcome->>'draft_id'"
            " and e.owner_space_id=r.space_id"
            " join public.business_draft_revisions v on v.draft_id=e.id"
            " and v.space_id=e.owner_space_id and v.version::text=r.outcome->>'version'"
            " join public.business_sources s on s.id=v.source_ids[1] and s.space_id=v.space_id"
            " join public.business_draft_sources l on l.draft_id=e.id"
            " and l.source_id=s.id and l.space_id=s.space_id"
            " where r.space_id=%s and e.user_id=%s and r.command->>'action'='capture_note'"
            " and r.outcome->>'outcome' in ('applied','replayed')"
            " and cardinality(v.source_ids)=1 and s.kind='message' and s.channel='web'"
            " and strpos(lower(s.text_content),lower(%s))>0"
            " order by s.received_at desc,s.id desc limit %s",
            (context.actor.space_id, context.owner_id, query, limit),
        )
