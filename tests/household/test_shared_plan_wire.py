"""Shared money disclosure has a deliberately bounded typed wire."""

from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_contribution_distinguishes_recorded_amount_from_unknown_goal_credit():
    from argus.domain.household.planning_schemas import SharedContribution

    entry = SharedContribution.model_validate(
        dict(
            id=uuid4(),
            person=dict(membership_id=uuid4(), display_name="Member"),
            amount_minor="2000",
            currency="DOP",
            currency_fraction_digits=2,
            date="2026-10-02",
            status="needs_review",
            applied_minor=None,
            original=None,
            purpose="goal_saving",
            occurrence_id=None,
            can_correct=True,
            can_release=True,
        )
    )
    assert entry.amount_minor == "2000" and entry.applied_minor is None
    with pytest.raises(ValidationError):
        SharedContribution.model_validate(
            entry.model_dump() | {"source_account_id": uuid4()}
        )


def test_responsibility_requires_one_explicit_period_occurrence_or_agreed_date():
    from argus.domain.household.planning_schemas import ResponsibilityWrite

    with pytest.raises(ValidationError):
        ResponsibilityWrite(membership_id=uuid4(), amount="70")
    with pytest.raises(ValidationError):
        ResponsibilityWrite(
            membership_id=uuid4(), amount="70", period="2026-10", agreed_date="2026-10-02"
        )
    result = ResponsibilityWrite(membership_id=uuid4(), amount=None, period="2026-10")
    assert result.amount is None and result.period == "2026-10"
