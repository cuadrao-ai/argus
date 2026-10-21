from __future__ import annotations

from pydantic import TypeAdapter

from argus.domain.business.contracts.dgii import DgiiDeclaration
from argus.domain.business.contracts.facts import BusinessFacts
from argus.domain.business.dgii_validation import FiscalRecord
from argus.domain.business.ledger import occurred_on
from argus.domain.recording.owner_funds import owner_funded


def fiscal_snapshot(cursor, context, activities):
    cursor.execute(
        "select name,business_rnc from public.spaces where id=%s",
        (context.actor.space_id,),
    )
    profile = cursor.fetchone()
    # Facts and evidence come from the approved revision. The declaration may
    # be the approval's own revision, written at the version after it.
    cursor.execute(
        "select e.id,e.activity_id,v.version,v.after_facts,d.after_dgii,v.source_ids"
        " from public.financial_import_events e"
        " join public.business_action_receipts a on a.space_id=e.owner_space_id"
        " and a.actor_id::text=e.resolution->'approval_receipt'->>'actor_id'"
        " and a.idempotency_key=e.resolution->'approval_receipt'->>'key'"
        " and a.command->>'action' in ('approve_expense','approve_income','approve_refund')"
        " join lateral (select version,after_facts,source_ids"
        " from public.business_draft_revisions where draft_id=e.id and space_id=e.owner_space_id"
        " and version<=(a.command->'request'->>'version')::integer order by version desc limit 1) v on true"
        " join lateral (select after_dgii from public.business_draft_revisions"
        " where draft_id=e.id and space_id=e.owner_space_id"
        " and version<=(a.command->'request'->>'version')::integer+1 order by version desc limit 1) d on true"
        " where e.user_id=%s and e.owner_space_id=%s and e.state='accepted'"
        " and e.activity_id is not null and e.accept_key is not null",
        (context.owner_id, context.actor.space_id),
    )
    approved = {}
    for row in cursor.fetchall():
        identifier = str(row["activity_id"])
        if identifier in approved:
            raise ValueError("duplicate_canonical_fiscal_approval")
        approved[identifier] = row
    records = []
    for activity in activities:
        identifier = activity["activity_id"]
        row = approved.get(identifier)
        records.append(
            FiscalRecord(
                activity_id=identifier,
                activity_revision=activity["revision"],
                draft_id=str(row["id"]) if row else "",
                approved_revision=row["version"] if row else 0,
                occurred_on=occurred_on(activity),
                amount=str(activity["amount"]),
                currency=activity["currency"],
                kind=activity["kind"],
                facts=BusinessFacts.model_validate(row["after_facts"])
                if row
                else BusinessFacts(),
                declaration=TypeAdapter(DgiiDeclaration).validate_python(
                    row["after_dgii"]
                )
                if row and row["after_dgii"]
                else None,
                source_ids=tuple(str(value) for value in row["source_ids"])
                if row
                else (),
                owner_funded=owner_funded(activity),
            )
        )
    return tuple(records), profile["business_rnc"], profile["name"]
