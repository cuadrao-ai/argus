"""The open drafts the rule types again when the Business RNC changes.

A draft nobody named is the rule's to decide: the receipt it suggested with
no Business RNC, and the type the read detected against the old number. A
type a person or a document named, or a receipt the rule defaulted to with
no issuer, stays. Approved records never change here.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

from loguru import logger

from argus.domain.business.actions.mutations import (
    business_tax_id,
    facts_under_type,
    read_issuer,
    save_revision,
    stored_type,
)
from argus.domain.business.contracts.authority import ActorProvenance
from argus.domain.business.contracts.facts import BusinessResolution, Known
from argus.domain.business.document_type import resolved_document_type
from argus.domain.business.transactions import ActionTransaction


def recheck_open_drafts(
    tx: ActionTransaction, actor: ActorProvenance, source_ids: tuple[UUID, ...]
) -> int:
    """Types every open draft the rule owns again, against the Business RNC
    now stored, and saves a revision for each one whose answer changed. The
    number of drafts retyped."""

    own = business_tax_id(tx)
    now = datetime.now(timezone.utc)
    retyped = 0
    for event in tx.imports.events(("open",)):
        business = event.resolution.get("business")
        if business is None:
            continue
        current = stored_type(business)
        if not current.rule_owned:
            continue
        resolution = BusinessResolution.model_validate(business)
        resolved = resolved_document_type(None, _issuer(resolution), own)
        if resolved == current:
            continue
        before = resolution.facts
        after = facts_under_type(before, resolved, source_ids, own)
        logger.info(
            "business_document_type_rechecked draft={} was={} now={} detected={}"
            " suggested={}",
            event.id,
            current.document_type,
            resolved.document_type,
            resolved.detected,
            resolved.suggested,
        )
        save_revision(
            tx,
            replace(event, version=event.version + 1, updated_at=now),
            before,
            after,
            source_ids,
            actor,
            None,
            resolved=resolved,
        )
        retyped += 1
    return retyped


def _issuer(resolution: BusinessResolution) -> str | None:
    """The RNC that issued the draft's document, as the draft carries it."""

    rnc = resolution.facts.fiscal.rnc if resolution.facts.fiscal is not None else None
    return read_issuer(resolution.dgii_qr, rnc.value if isinstance(rnc, Known) else None)
