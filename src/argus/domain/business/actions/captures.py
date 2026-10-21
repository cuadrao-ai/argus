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
from argus.domain.business.document_type import typed_facts
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
                    typed = {}
                    if request.draft is None:
                        event = mutations.new_candidate(context.owner_id, now)
                        before = None
                        after = BusinessFacts(
                            currency=Known(value="DOP", origin="default", source_ids=())
                        )
                        # A typed note prints no issuer RNC, so the read's rule
                        # finds no Business number in it: a receipt.
                        document_type = request.document_type or "recibo"
                        if document_type == "venta":
                            after = typed_facts(
                                after, "venta", (source_id,), "owner_stated", None
                            )
                        typed = {
                            "document_type": document_type,
                            "document_type_detected": request.document_type is None,
                        }
                    else:
                        event = mutations.event_at(tx, request.draft)
                        before = after = facts_of(event)
                        event = replace(event, version=event.version + 1, updated_at=now)
                    result = mutations.save_revision(
                        tx,
                        event,
                        before,
                        after,
                        (source_id,),
                        tx.authorization.provenance,
                        None,
                        **typed,
                    )
            except ActionError as error:
                result = error.result
            return plans.finish_receipt(tx, key, result)
    except ActionError as error:
        return error.result


# A saved note: the message source of a capture_note action's own revision.
_NOTES = (
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
)
# The Bandeja's notes: drafts still awaiting review that no receipt carries.
# A note added to a receipt's record is part of that receipt's row.
_AWAITING_WITHOUT_RECEIPT = (
    " and e.state in ('open','accepting') and not exists ("
    "   select 1 from public.business_draft_sources l2"
    "   join public.business_sources s2 on s2.id=l2.source_id and s2.space_id=l2.space_id"
    "   where l2.draft_id=e.id and l2.space_id=e.owner_space_id"
    "   and s2.connection_id is not null)"
)


def entries(
    service: BusinessActions,
    context: ActionContext,
    *,
    query: str = "",
    limit: int = 20,
    view: str = "all",
) -> list[dict]:
    if "\x00" in query or len(query) > 200 or not 1 <= limit <= 50:
        raise ActionError("invalid_input", "business_capture_query_invalid")
    with transaction(service.authority, context) as tx:
        return tx.rows(
            "select e.id as draft_id,e.version,v.version as revision,s.id as source_id,"
            " s.text_content as text,s.received_at,e.state as review_state"
            + _NOTES
            + (_AWAITING_WITHOUT_RECEIPT if view == "inbox" else "")
            + " and strpos(lower(s.text_content),lower(%s))>0"
            " order by s.received_at desc,s.id desc limit %s",
            (context.actor.space_id, context.owner_id, query, limit),
        )


def awaiting_notes(tx) -> int:  # noqa: ANN001
    """How many drafts the Bandeja's notes stand for, uncapped: the same rows
    ``entries(view="inbox")`` lists, one per draft."""

    return tx.rows(
        "select count(distinct e.id) as drafts" + _NOTES + _AWAITING_WITHOUT_RECEIPT,
        (tx.context.actor.space_id, tx.context.owner_id),
    )[0]["drafts"]
