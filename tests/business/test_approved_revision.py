"""A recorded approval names the facts revision a person approved and when,
not the latest revision a later mark added."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from argus.domain.business.actions.dossier import approval_of
from argus.domain.business.contracts.dossier import DraftRevision
from argus.domain.business.contracts.facts import BusinessFacts

ACTOR = {
    "actor_id": uuid4(),
    "actor_kind": "member",
    "display_name": "Ana",
    "grant_id": uuid4(),
    "issuer_id": uuid4(),
    "issuer_display_name": "Ana",
}
APPROVED_AT = datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc)


def _revision(version: int) -> DraftRevision:
    return DraftRevision(
        draft_id=UUID(int=1),
        version=version,
        actor=ACTOR,
        before=None,
        after=BusinessFacts(),
        source_ids=(),
        created_at=APPROVED_AT,
    )


def _receipt(version: int, outcome: dict | None = None) -> dict:
    return {
        "actor": ACTOR,
        "command": {"action": "approve_expense", "request": {"version": version}},
        "outcome": outcome,
        "created_at": APPROVED_AT,
    }


def test_recorded_approval_keeps_the_approved_revision_after_later_marks() -> None:
    # Revision 2 approved at event version 3 (a settlement bumped it); the
    # approval took 4 and a Personal mark wrote revision 5.
    history = (_revision(1), _revision(2), _revision(5))
    activity = uuid4()

    result = approval_of(_receipt(3), activity, history)

    assert result is not None
    assert result.model_dump(mode="json", exclude={"actor"}) == {
        "status": "recorded",
        "activity_id": str(activity),
        "reviewed_version": 3,
        "approved_revision": 2,
        "approved_at": "2026-10-09T14:30:00Z",
    }


def test_unsettled_approval_reports_its_outcome_without_a_revision() -> None:
    result = approval_of(
        _receipt(2, {"outcome": "outcome_unknown", "code": "ledger_unreachable"}),
        None,
        (_revision(1), _revision(2)),
    )

    assert result is not None
    assert result.model_dump(mode="json") == {
        "status": "outcome_unknown",
        "code": "ledger_unreachable",
        "reviewed_version": 2,
    }
    assert approval_of(None, None, (_revision(1),)) is None
