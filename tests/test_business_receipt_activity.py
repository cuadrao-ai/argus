from datetime import datetime, timedelta, timezone

from argus.domain.business.receipt_activity import (
    acknowledge,
    aggregate_activity,
    inbox_counts,
    project_activity,
    ready_to_review,
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


def test_emails_that_are_a_row_of_their_own_add_to_the_bandeja_counts():
    views = [
        receipt(id="a", status="needs_attention"),
        receipt(id="b"),
        receipt(id="c", status="confirmed"),
        receipt(id="d", email_original=True, status="needs_attention"),
    ]
    assert inbox_counts(views) == {
        "pending_review_count": 2,
        "needs_attention_count": 1,
        "ready_to_review_count": 2,
        "por_igualar_count": None,
    }
    assert inbox_counts(views, notes=1, emails=["no_receipt", "no_receipt"]) == {
        "pending_review_count": 5,
        "needs_attention_count": 3,
        "ready_to_review_count": 3,
        "por_igualar_count": None,
    }
    assert inbox_counts(views, emails=["reading", "no_receipt", "reading"]) == {
        "pending_review_count": 5,
        "needs_attention_count": 2,
        "ready_to_review_count": 2,
        "por_igualar_count": None,
    }
    assert inbox_counts(views, por_igualar=7)["por_igualar_count"] == 7


def test_ready_to_review_matches_the_web_por_revisar_cases():
    """The cases of web/__tests__/business-review-count.test.ts, one for one."""

    def review(**changes):
        return receipt(**{"attention": None, **changes})

    views = [
        review(),
        review(status="needs_attention", attention="duplicate"),
        review(status="needs_attention", attention="several_purchases"),
        review(status="saved"),
        review(status="needs_attention", attention="unreadable"),
        review(status="queued", read_pending=True),
        review(status="preparing", activity={"state": "reading"}),
        review(status="review_ready", activity={"state": "reading"}),
        review(status="confirmed"),
        review(status="dismissed"),
        review(email_original=True, status="saved"),
    ]
    assert inbox_counts(views)["ready_to_review_count"] == 4
    assert inbox_counts([])["ready_to_review_count"] == 0
    assert not ready_to_review(
        review(status="queued", read_pending=True, attention="unreadable")
    )


def test_each_fact_alone_keeps_a_receipt_out_of_ready_to_review():
    assert ready_to_review(receipt(attention="duplicate"))
    for changes in (
        {"status": "queued"},
        {"status": "preparing"},
        {"read_pending": True},
        {"activity": {"state": "reading"}},
        {"attention": "unreadable"},
        {"status": "confirmed"},
        {"status": "dismissed"},
        {"email_original": True},
    ):
        assert not ready_to_review(receipt(**changes)), changes


def test_emails_being_read_count_as_reading_and_make_the_badge_work():
    unread = project_activity(receipt(status="saved"), completion="v1", seen=None)
    assert aggregate_activity([unread]) == {
        "reading_count": 0,
        "unread_count": 1,
        "presentation": "unread",
    }
    assert aggregate_activity([unread], reading_emails=2) == {
        "reading_count": 2,
        "unread_count": 1,
        "presentation": "working",
    }
    assert aggregate_activity([])["presentation"] == "none"
    assert aggregate_activity([], reading_emails=1)["presentation"] == "working"
