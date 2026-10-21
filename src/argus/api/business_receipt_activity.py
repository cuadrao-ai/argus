"""Canonical receipt activity and person-scoped seen mutations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from argus.domain.business.receipt_activity import (
    ReceiptActivity,
    aggregate_activity,
    inbox_counts,
    project_activity,
)
from argus.domain.business.transactions import GrantImportStore, transaction


def _stamp(draft: dict, view: dict) -> str | None:
    if draft.get("status") not in ("review_ready", "needs_attention") or view.get(
        "preparable"
    ):
        return None
    return str(draft["version"])


def project(
    context,
    views: list[dict],
    *,
    acknowledge_id: str | None = None,
    cursor: str | None = None,
) -> list[dict]:
    documents = context.service.documents
    store = context.service.imports.store
    person = str(context.scope.actor_id or context.scope.person_id)
    business = str(context.scope.owner.space_id)
    if isinstance(store, GrantImportStore):
        with transaction(store.authority, store.context) as tx:
            ids = [UUID(view["id"]) for view in views]
            rows = tx.rows(
                "select d.connection_id,d.draft,r.completion_cursor from public.financial_document_extractions d"
                " join public.financial_source_connections c on c.id=d.connection_id and c.user_id=d.user_id"
                " left join public.business_receipt_read_states r on r.connection_id=d.connection_id and r.space_id=c.owner_space_id and r.person_id=%s"
                " where c.owner_space_id=%s and c.user_id=%s and c.id=any(%s)"
                + (" for update of c,d" if acknowledge_id else ""),
                (person, business, context.scope.person_id, ids),
            )
            from argus.api.business_drafts import draft_overlay, linked_drafts

            drafts = linked_drafts(tx, [view["id"] for view in views])
            views = [draft_overlay(view, drafts.get(view["id"], [])) for view in views]
            states = {str(row["connection_id"]): row for row in rows}
            baseline = tx.rows(
                "select established_at from public.business_receipt_activity_baseline where singleton=true"
            )[0]["established_at"]
            result = _project(views, states, baseline, drafts)
            if acknowledge_id:
                chosen = next(view for view in result if view["id"] == acknowledge_id)
                activity = chosen["activity"]
                if (
                    activity["state"] == "ready"
                    and cursor == activity["completion_cursor"]
                ):
                    tx.rows(
                        "insert into public.business_receipt_read_states(space_id,person_id,connection_id,completion_cursor) values (%s,%s,%s,%s) on conflict (space_id,person_id,connection_id) do update set completion_cursor=excluded.completion_cursor,seen_at=clock_timestamp()",
                        (business, person, acknowledge_id, cursor),
                    )
                    activity["unread"] = False
            return result
    if not hasattr(documents, "receipt_seen"):
        documents.receipt_seen = {}
        documents.receipt_baseline = datetime.now(timezone.utc)
    states = {}
    for view in views:
        draft = documents.store.draft(
            user_id=context.scope.person_id, connection_id=view["id"]
        )
        if draft:
            states[view["id"]] = {
                "draft": draft.model_dump(mode="json"),
                "completion_cursor": documents.receipt_seen.get(
                    (business, person, view["id"])
                ),
            }
    result = _project(views, states, documents.receipt_baseline)
    if acknowledge_id:
        chosen = next(view for view in result if view["id"] == acknowledge_id)
        activity = chosen["activity"]
        if activity["state"] == "ready" and cursor == activity["completion_cursor"]:
            documents.receipt_seen[(business, person, acknowledge_id)] = cursor
            activity["unread"] = False
    return result


def _project(views, states, baseline, drafts=None):
    output = []
    for view in views:
        row = states.get(view["id"], {})
        draft = row.get("draft") or {}
        completed = draft.get("updated_at")
        if isinstance(completed, str):
            completed = datetime.fromisoformat(completed.replace("Z", "+00:00"))
        canonical = (drafts or {}).get(view["id"], [])
        stamp = _stamp(draft, view)
        if (
            canonical
            and view["status"] in ("review_ready", "needs_attention")
            and not view.get("read_pending")
        ):
            stamp = str(draft["version"])
        if canonical and stamp is not None:
            stamp += ":" + ":".join(f"{row['id']}@{row['version']}" for row in canonical)
            completed = max([completed, *(row["updated_at"] for row in canonical)])
        activity = project_activity(
            view,
            completion=stamp,
            seen=row.get("completion_cursor"),
            baseline=baseline,
            completed_at=completed,
        )
        output.append({**view, "activity": activity.wire()})
    return output


def inbox(
    context,  # noqa: ANN001
    views: list[dict],
    emails: Sequence[str] | None = None,
) -> dict[str, int]:
    """The Bandeja's counts over these receipt views, the Business's saved
    notes awaiting review (the in-memory app keeps no notes) and the emails
    that are a row of their own; ``emails`` are their standings, read here
    when not given."""

    from argus.api.email_intake import email_standings

    store = context.service.imports.store
    notes = 0
    por_igualar = None
    if isinstance(store, GrantImportStore):
        from argus.domain.business.actions.captures import awaiting_notes

        with transaction(store.authority, store.context) as tx:
            notes = awaiting_notes(tx)
        from argus.domain.business.bank.service import bank_matching_on

        if bank_matching_on():
            from argus.domain.business.bank.movements_store import por_igualar_count

            por_igualar = por_igualar_count(store.authority.pool, store.context)
    if emails is None:
        emails = email_standings(str(context.scope.owner.space_id))
    return inbox_counts(views, notes, emails, por_igualar)


def counts(context, views: list[dict]) -> dict:  # noqa: ANN001
    """One answer for the sidebar badge, the Bandeja and the Resumen."""

    from argus.api.email_intake import email_standings

    emails = email_standings(str(context.scope.owner.space_id))
    return {
        **aggregate_activity(
            (ReceiptActivity(**view["activity"]) for view in views),
            reading_emails=emails.count("reading"),
        ),
        **inbox(context, views, emails),
    }
