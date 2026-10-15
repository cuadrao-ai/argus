"""On Postgres, the Bandeja counts each record awaiting review once: a note
added to a receipt's record is part of that receipt's row, a note no receipt
carries is its own row, and the Resumen reads the same numbers."""

from datetime import date

import pytest
from argus.api.business_drafts import overview_with_drafts, receipt_summaries
from argus.api.business_receipt_activity import counts
from argus.domain.business.contracts.actions import CaptureNote, ExistingDraft

from tests import test_business_receipt_activity_postgres as activity

actions = activity.actions
users = activity.users
pytestmark = activity.pytestmark


@pytest.mark.owner_acts
def test_a_note_on_a_receipt_record_is_part_of_its_row_and_counted_once(actions):
    service, context, _cid, draft_id, web = activity.ready(actions)
    assert counts(web, receipt_summaries(web, "inbox"))["pending_review_count"] == 1

    version = service.dossier(context, draft_id).version
    on_receipt = service.capture(
        context,
        CaptureNote(
            text="Pagado con la tarjeta del negocio",
            draft=ExistingDraft(draft_id=draft_id, version=version),
        ),
        "review-counts-note-on-receipt",
    )
    assert on_receipt.outcome == "applied", on_receipt
    standalone = service.capture(
        context, CaptureNote(text="Pagué 850 en la ferretería"), "review-counts-note"
    )
    assert standalone.outcome == "applied", standalone

    # Every saved note stays searchable; the Bandeja lists only the one no receipt carries.
    assert {str(row["draft_id"]) for row in service.captures(context)} == {
        str(draft_id),
        str(standalone.draft_id),
    }
    assert [str(row["draft_id"]) for row in service.captures(context, view="inbox")] == [
        str(standalone.draft_id)
    ]
    found = counts(web, receipt_summaries(web, "inbox"))
    assert (found["pending_review_count"], found["needs_attention_count"]) == (2, 0)
    overview = overview_with_drafts(web, date(2026, 10, 1), date(2026, 10, 31))
    assert (overview["awaiting_review"], overview["needs_attention"]) == (2, 0)
