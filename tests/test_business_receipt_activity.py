from datetime import datetime, timedelta, timezone

from argus.domain.business.receipt_activity import (
    acknowledge,
    aggregate_activity,
    project_activity,
)

NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def receipt(**changes):
    return {
        "id": "receipt-one",
        "status": "review_ready",
        "read_pending": False,
        "email_original": False,
        "received_at": NOW,
        **changes,
    }


def test_saved_receipt_waiting_for_consent_is_unread_and_never_ready():
    result = project_activity(receipt(status="saved"), completion="v1", seen=None)
    assert result.state == "saved_unread"
    assert result.unread is True
    assert result.completion_cursor is None


def test_stale_acknowledgement_cannot_consume_a_new_completion():
    old = project_activity(receipt(), completion="v1", seen=None)
    current = project_activity(receipt(), completion="v2", seen=None)
    assert acknowledge(current, old.completion_cursor, None) is None
    assert (
        acknowledge(current, current.completion_cursor, None) == current.completion_cursor
    )


def test_reading_wins_aggregate_and_context_originals_are_excluded():
    ready = project_activity(receipt(), completion="v1", seen=None)
    reading = project_activity(receipt(read_pending=True), completion=None, seen=None)
    context = project_activity(receipt(email_original=True), completion="v1", seen=None)
    assert aggregate_activity([ready, reading, context]) == {
        "reading_count": 1,
        "unread_count": 1,
        "presentation": "working",
    }


def test_existing_receipts_start_read_but_new_completions_do_not():
    assert (
        project_activity(
            receipt(received_at=NOW - timedelta(days=1)),
            completion="v1",
            seen=None,
            baseline=NOW,
        ).unread
        is False
    )
    assert (
        project_activity(
            receipt(), completion="v1", seen=None, baseline=NOW - timedelta(days=1)
        ).unread
        is True
    )


def test_old_receipt_with_new_completion_is_unread():
    activity = project_activity(
        receipt(received_at=NOW - timedelta(days=2)),
        completion="new",
        seen=None,
        baseline=NOW - timedelta(days=1),
        completed_at=NOW,
    )
    assert activity.unread is True


def test_saved_unread_counts_but_failed_read_requires_recovery():
    saved = project_activity(receipt(status="saved"), completion=None, seen=None)
    failed = project_activity(
        receipt(status="needs_attention", preparable=True), completion=None, seen=None
    )
    assert failed.state == "read_failed"
    assert failed.completion_cursor is None
    assert aggregate_activity([saved, failed])["unread_count"] == 1
