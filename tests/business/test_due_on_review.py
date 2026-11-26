from __future__ import annotations

from datetime import date, timezone
from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import (
    ReviewCommand,
    ReviewDraft,
    canonical_input_hash,
)
from faker import Faker
from pydantic import ValidationError


def test_a_review_may_carry_only_a_due_date_set_or_cleared():
    dated = ReviewDraft.model_validate(
        {"version": 2, "due_on": {"state": "known", "value": "2026-11-04"}}
    )
    assert dated.due_on.value == date(2026, 11, 4)
    cleared = ReviewDraft.model_validate({"version": 2, "due_on": {"state": "unknown"}})
    assert cleared.due_on.value is None


@pytest.mark.parametrize(
    "due_on",
    [
        None,
        {"state": "owner_does_not_know"},
        {"state": "known", "value": "2026-02-30"},
        {"state": "known", "value": None},
    ],
)
def test_a_due_date_is_a_real_date_or_an_explicit_unknown(due_on) -> None:  # noqa: ANN001
    with pytest.raises(ValidationError):
        ReviewDraft.model_validate({"version": 2, "due_on": due_on})


def test_clearing_the_due_date_is_its_own_command_for_idempotency():
    draft_id = uuid4()

    def command(**request) -> str:  # noqa: ANN003
        review = ReviewDraft.model_validate(
            {"version": 2, "document_type": "recibo", **request}
        )
        return canonical_input_hash(ReviewCommand(draft_id=draft_id, request=review))

    hashes = {
        command(),
        command(due_on={"state": "unknown"}),
        command(due_on={"state": "known", "value": "2026-11-04"}),
    }
    assert len(hashes) == 3


def test_a_receipt_whose_own_event_is_the_draft_shows_the_draft_due_date():
    from argus.api.business_drafts import draft_overlay
    from argus.domain.business.contracts.facts import BusinessFacts, BusinessResolution

    draft_id = str(uuid4())
    drafts = [
        {
            "id": draft_id,
            "state": "open",
            "resolution": {
                "business": BusinessResolution(
                    facts=BusinessFacts(), due_on=date(2026, 11, 4)
                ).model_dump(mode="json")
            },
        }
    ]
    detail = {"id": "receipt", "draft_id": draft_id, "due_on": None, "title": "obsolete read title", "filename": "nota.pdf"}
    assert draft_overlay(detail, drafts) == {**detail, "title": "nota.pdf", "deleted": None, "due_on": date(2026, 11, 4)}
    summary = {"id": "receipt", "draft_id": draft_id, "status": "review_ready", "title": None}
    assert draft_overlay(summary, drafts) == {**summary, "deleted": None}


def test_own_draft_overlay_preserves_the_selected_receipt_fields(faker: Faker) -> None:
    from argus.api.business_drafts import draft_overlay
    from argus.domain.business.contracts.facts import (
        BusinessFacts,
        BusinessResolution,
        Known,
    )
    from argus.domain.business.record_origin import DraftArrival

    draft = uuid4()
    name = faker.company()
    source = uuid4()
    arrival = DraftArrival(faker.date_time(tzinfo=timezone.utc), source, None, None)
    counterparty = Known[str](value=name, origin="owner_stated", source_ids=(source,))
    resolution = BusinessResolution(facts=BusinessFacts(counterparty=counterparty))
    stored = {"id": draft, "state": "open", "arrival": arrival,
              "resolution": {"business": resolution.model_dump(mode="json")}}
    receipt = {"id": str(uuid4()), "draft_id": str(draft)}
    assert draft_overlay(receipt, [stored]) == {**receipt, "deleted": None}
    selected = dict.fromkeys(("merchant", "title", "received_at", "due_on"))
    assert draft_overlay({**receipt, **selected}, [stored]) == {
        **receipt, "deleted": None, "merchant": name, "title": name,
        "received_at": arrival.received_at, "due_on": None,
    }
