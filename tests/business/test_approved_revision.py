"""A recorded approval names the facts revision a person approved and when,
as the approved-revision reader finds it for the version the approval
reviewed. Postgres tests prove the reader skips revisions later marks added."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from argus.domain.business.actions.dossier import approval_of

ACTOR = {
    "actor_id": uuid4(),
    "actor_kind": "member",
    "display_name": "Ana",
    "grant_id": uuid4(),
    "issuer_id": uuid4(),
    "issuer_display_name": "Ana",
}
APPROVED_AT = datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc)


def _receipt(version: int, outcome: dict | None = None) -> dict:
    return {
        "actor": ACTOR,
        "command": {"action": "approve_expense", "request": {"version": version}},
        "outcome": outcome,
        "created_at": APPROVED_AT,
    }


def test_recorded_approval_names_the_revision_approved_at_its_version() -> None:
    # Revision 2 approved at event version 3: a settlement bumped the version.
    activity = uuid4()
    asked = []

    def approved(version: int) -> int:
        asked.append(version)
        return 2

    result = approval_of(_receipt(3), activity, approved)

    assert result is not None
    assert result.model_dump(mode="json", exclude={"actor"}) == {
        "status": "recorded",
        "activity_id": str(activity),
        "reviewed_version": 3,
        "approved_revision": 2,
        "approved_at": "2026-10-09T14:30:00Z",
    }
    assert asked == [3]


def _unread(version: int) -> int:
    raise AssertionError("an unsettled approval names no revision")


def test_unsettled_approval_reports_its_outcome_without_a_revision() -> None:
    result = approval_of(
        _receipt(2, {"outcome": "outcome_unknown", "code": "ledger_unreachable"}),
        None,
        _unread,
    )

    assert result is not None
    assert result.model_dump(mode="json") == {
        "status": "outcome_unknown",
        "code": "ledger_unreachable",
        "reviewed_version": 2,
    }
    assert approval_of(None, None, _unread) is None
