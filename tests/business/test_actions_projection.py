from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from argus.domain.business.contracts.facts import BusinessFacts, BusinessResolution
from argus.domain.ingestion.reconcile.matching import event_facts
from argus.domain.ingestion.reconcile.model import ImportEvent, Observation
from argus.domain.ingestion.reconcile.render import proposed_kind


@pytest.mark.parametrize("typed", [True, False])
def test_explicit_business_unknown_masks_old_extraction(typed: bool) -> None:
    now = datetime.now(timezone.utc)
    event = ImportEvent(
        str(uuid4()),
        str(uuid4()),
        "open",
        "transaction",
        None,
        None,
        None,
        (),
        {},
        None,
        None,
        now,
        now,
        1,
    )
    observation = Observation(
        str(uuid4()),
        event.user_id,
        event.id,
        str(uuid4()),
        "statement",
        "purchase",
        "fingerprint",
        {
            "amount": "850",
            "currency": "USD",
            "direction": "outflow",
            "kind_hint": "expense",
            "occurred_on": "2026-10-01",
        },
        True,
        1,
        now,
        now,
    )
    if typed:
        event = replace(
            event,
            resolution={
                "business": BusinessResolution(facts=BusinessFacts()).model_dump(
                    mode="json"
                )
            },
        )
    facts = event_facts(event, [observation], {})
    assert facts.amount == (None if typed else Decimal("850"))
    assert facts.currency == (None if typed else "USD")
    assert proposed_kind(facts) == (None if typed else "expense")
    assert (facts.occurred_on is None) == typed
