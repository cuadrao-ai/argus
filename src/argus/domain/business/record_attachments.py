"""Which linked files still have bytes in this Business."""

from collections.abc import Collection, Sequence
from uuid import UUID

from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.documents.objects import IMAGE_MEDIA_TYPES, SOURCE_BUCKET


def stored_paths(tx: ActionTransaction, paths: Collection[str]) -> set[str]:
    return {
        row["name"]
        for row in tx.rows(
            "select name from storage.objects where bucket_id=%s and name=any(%s)",
            (SOURCE_BUCKET, list(paths)),
        )
    }


def retained_source_ids(
    tx: ActionTransaction, draft_ids: Sequence[str | UUID]
) -> set[str]:
    if not draft_ids:
        return set()
    rows = tx.rows(
        "select s.id::text, case when d.draft->>'media_type'=any(%s)"
        " then d.rebuilt_path end as rebuilt,"
        " d.source_path as original,d.source_bytes is not null as inline"
        " from public.business_draft_sources l join public.business_sources s"
        " on s.space_id=l.space_id and s.id=l.source_id and s.kind='attachment'"
        " join public.financial_source_connections c on c.id=s.connection_id"
        " and c.owner_space_id=l.space_id and c.user_id=%s and c.source='statement'"
        " join public.financial_document_extractions d"
        " on d.connection_id=c.id and d.user_id=c.user_id and d.draft is not null"
        " where l.space_id=%s and l.draft_id=any(%s::uuid[])",
        (
            list(IMAGE_MEDIA_TYPES),
            tx.context.owner_id,
            tx.context.actor.space_id,
            list(draft_ids),
        ),
    )
    paths = {path for row in rows for path in (row["rebuilt"], row["original"]) if path}
    present = stored_paths(tx, paths) if paths else set()
    return {
        row["id"]
        for row in rows
        if row["inline"] or row["rebuilt"] in present or row["original"] in present
    }
