"""The ledger side of deleting an accepted Business document."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from argus.domain.business.actions.fiscal import comprobante_identity
from argus.domain.business.authority import ActionError
from argus.domain.business.fiscal_identity import credit_note, normalized_ncf
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.reconcile.model import ImportEvent


def original_activity(event: ImportEvent) -> UUID:
    # The approval snapshot survives deletion. The live activity_id column
    # belongs only to accepted events and is cleared while in Eliminados.
    value = (event.resolution.get("accepted") or {}).get("activity_id")
    if not value or (event.activity_id is not None and value != event.activity_id):
        raise ActionError("invalid_input", "business_record_not_found")
    return UUID(value)


def _sale_credit_link(tx: ActionTransaction, event: ImportEvent) -> bool:
    business = event.resolution["business"]
    identity = comprobante_identity(business["facts"])
    if not identity or identity[0] != "sale":
        return False
    number = identity[1]
    if credit_note(number):
        modified = normalized_ncf((business.get("dgii") or {}).get("modified_ncf"))
        return bool(
            modified
            and tx.rows(
                "select 1 from public.financial_import_events where owner_space_id=%s"
                " and state in ('accepting','accepted') and business_kind='income'"
                " and business_fiscal_number=%s and id<>%s limit 1",
                (tx.context.actor.space_id, modified, event.id),
            )
        )
    return any(
        credit_note(row["business_fiscal_number"])
        for row in tx.rows(
            "select business_fiscal_number from public.financial_import_events"
            " where owner_space_id=%s and state in ('open','accepting','accepted')"
            " and business_kind='income' and id<>%s"
            " and upper(btrim(resolution->'business'->'dgii'->>'modified_ncf'))=%s",
            (tx.context.actor.space_id, event.id, number),
        )
    )


def linked(tx: ActionTransaction, event: ImportEvent, activity: UUID) -> bool:
    """An active match, settlement, or a fiscal or ledger link in either direction."""

    space, owner = tx.context.actor.space_id, tx.context.owner_id
    declaration = event.resolution["business"].get("dgii") or {}
    return bool(
        # A legacy import can point at a money row it never recorded itself.
        event.accept_key is None
        or declaration.get("purchase_activity_id")
        or tx.rows(
            "select 1 from public.business_bank_line_outcomes"
            " where space_id=%s and target_id=%s and kind='match' and ended_at is null"
            " union all select 1 from public.business_document_settlements"
            " where space_id=%s and activity_id=%s and status<>'pendiente'"
            " union all select 1 from public.financial_import_events"
            " where owner_space_id=%s and id<>%s and state in ('open','accepting','accepted')"
            " and (activity_id=%s or resolution->'business'->'dgii'->>'purchase_activity_id'=%s)"
            " union all select 1 from public.financial_record_revisions"
            " where purchase_activity_id=%s or reversal_of_activity_id=%s"
            " union all select 1 from public.financial_activity_memberships m"
            " join public.financial_record_revisions r on r.record_id=m.record_id"
            " and r.revision=m.record_revision and r.user_id=m.record_owner_id"
            " where m.activity_id=%s and m.user_id=%s"
            " and (r.purchase_activity_id is not null or r.reversal_of_activity_id is not null"
            " or m.record_owner_id<>m.user_id) limit 1",
            (
                space,
                activity,
                space,
                activity,
                space,
                event.id,
                activity,
                str(activity),
                activity,
                activity,
                activity,
                owner,
            ),
        )
        or _sale_credit_link(tx, event)
    )


def set_reversed(tx: ActionTransaction, activity: UUID, at: datetime | None) -> None:
    if not tx.rows(
        "update public.financial_activity_groups set reversed_at=%s"
        " where id=%s and user_id=%s and (reversed_at is null)=%s returning id",
        (at, activity, tx.context.owner_id, at is not None),
    ):
        raise ActionError("invalid_input", "business_record_not_found")
