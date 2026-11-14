"""The open drafts a Business's first tax id types again.

A draft read while the Business had no number is a receipt the read chose:
nothing told a sale from a purchase. The first number is that missing fact,
so the read's rule runs once more over the drafts still open.
"""

from __future__ import annotations

from loguru import logger

from argus.domain.business.actions import mutations
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import ExistingDraft
from argus.domain.business.contracts.facts import BusinessResolution, Known
from argus.domain.business.document_type import issuer_tax_id, resolved_document_type
from argus.domain.business.transactions import ActionTransaction

# The save's receipt owns why: a revision is the recheck's when the save that
# stored the first tax id wrote it. Both rows carry their transaction's time.
_SAVE_WROTE = (
    " a.space_id=r.space_id and a.created_at=r.created_at"
    " and a.command->>'action'='set_business_rnc'"
)
REVISION_REASON = (
    "case when exists (select 1 from public.business_action_receipts a where"
    + _SAVE_WROTE
    + ") then 'business_rnc_set' end"
)


def retyped_drafts(tx: ActionTransaction, key: str) -> int:
    """How many drafts the save with this key moved to Ventas, the same on a
    replay as on the first answer."""

    return tx.rows(
        "select count(*) as moved from public.business_action_receipts a"
        " join public.business_draft_revisions r on"
        + _SAVE_WROTE
        + " where a.space_id=%s and a.actor_id=%s and a.idempotency_key=%s",
        (tx.context.actor.space_id, tx.context.actor.actor_id, key),
    )[0]["moved"]


def recheck_open_drafts(tx: ActionTransaction) -> None:
    """Makes a Venta of each open receipt the read chose whose issuer is the
    Business's own number, still marked as the read's choice. A type a person
    named and an approved record stay. A draft the change refuses stays a
    receipt the person may switch, so it never blocks saving the number."""

    own = mutations.business_tax_id(tx)
    actor = tx.authorization.provenance.model_copy(update={"actor_kind": "extractor"})
    for event in tx.imports.events(("open",)):
        saved = event.resolution.get("business")
        if saved is None:
            continue
        resolution = BusinessResolution.model_validate(saved)
        if not resolution.document_type_detected or resolution.document_type == "venta":
            continue
        fiscal = resolution.facts.fiscal
        read_rnc = (
            fiscal.rnc.value
            if fiscal is not None and isinstance(fiscal.rnc, Known)
            else None
        )
        document_type, detected = resolved_document_type(
            None, issuer_tax_id(resolution.dgii_qr, read_rnc), own
        )
        if document_type != "venta":
            continue
        source_ids = tuple(
            row["source_id"]
            for row in tx.rows(
                "select source_id from public.business_draft_sources"
                " where space_id=%s and draft_id=%s order by source_id",
                (tx.context.actor.space_id, event.id),
            )
        )
        try:
            with tx.connection.transaction():
                mutations.revise(
                    tx,
                    ExistingDraft(draft_id=event.id, version=event.version),
                    None,
                    source_ids,
                    actor,
                    document_type=document_type,
                    document_type_detected=detected,
                )
        except ActionError as error:
            logger.warning(
                "business_document_type_recheck_refused draft_id={} code={}",
                event.id,
                error.code,
            )
            continue
        logger.info(
            "business_document_type_rechecked draft_id={} type={}",
            event.id,
            document_type,
        )
