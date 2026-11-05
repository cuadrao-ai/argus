from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from argus.domain.business.actions import plans
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import BoundDraft, ExistingDraft
from faker import Faker

fake = Faker()


@pytest.fixture
def target() -> BoundDraft:
    return BoundDraft(draft_id=UUID(fake.uuid4()), base_version=2)


def transaction(rows: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(
            actor=SimpleNamespace(
                space_id=UUID(fake.uuid4()), actor_id=UUID(fake.uuid4())
            )
        ),
        rows=lambda query, args: rows,
    )


def test_bound_reference_starts_at_captured_version(target: BoundDraft) -> None:
    assert plans.reference(transaction([]), target, "turn", 0) == ExistingDraft(
        draft_id=target.draft_id, version=2
    )


def test_bound_reference_uses_only_saved_outcome_versions(target: BoundDraft) -> None:
    rows = [
        {
            "outcome": {
                "outcome": "applied",
                "draft_id": str(target.draft_id),
                "version": 3,
            }
        },
        {
            "outcome": {
                "outcome": "replayed",
                "draft_id": str(target.draft_id),
                "version": 3,
            }
        },
        {
            "outcome": {
                "outcome": "applied",
                "draft_id": str(target.draft_id),
                "version": 4,
            }
        },
    ]
    assert plans.reference(transaction(rows), target, "turn", 3) == ExistingDraft(
        draft_id=target.draft_id, version=4
    )


@pytest.mark.parametrize(
    "outcome",
    [
        None,
        {"outcome": "outcome_unknown", "code": "interrupted"},
        {"outcome": "stale_version", "code": "stale_version"},
        {"outcome": "invalid_input", "code": "invalid_fact"},
        {"outcome": "applied"},
        {"outcome": "applied", "draft_id": "not-a-uuid", "version": 3},
        {"outcome": "applied", "draft_id": fake.uuid4(), "version": 3},
    ],
)
def test_bound_reference_refuses_unverified_prior_result(
    target: BoundDraft, outcome: dict | None
) -> None:
    with pytest.raises(ActionError, match="business_prior_action_not_applied"):
        plans.reference(transaction([{"outcome": outcome}]), target, "turn", 1)


def test_bound_reference_cannot_regress_saved_revision(target: BoundDraft) -> None:
    rows = [
        {
            "outcome": {
                "outcome": "applied",
                "draft_id": str(target.draft_id),
                "version": 3,
            }
        },
        {
            "outcome": {
                "outcome": "applied",
                "draft_id": str(target.draft_id),
                "version": 2,
            }
        },
    ]
    with pytest.raises(ActionError, match="business_prior_action_not_applied"):
        plans.reference(transaction(rows), target, "turn", 2)


@pytest.mark.parametrize("key,index", [(None, 0), ("turn", None), ("turn", -1)])
def test_bound_reference_requires_durable_action_identity(
    target: BoundDraft, key: str | None, index: int | None
) -> None:
    with pytest.raises(ActionError, match="business_draft_reference_invalid"):
        plans.reference(transaction([]), target, key, index)
