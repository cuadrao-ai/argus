"""A restored subtotal is read from each historical snapshot by the server."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.business.contracts.dossier import DraftRevision
from argus.domain.business.contracts.facts import BusinessFacts, Unknown

from tests.business.test_fiscal_links import read
from tests.business.test_venta import _actor


@pytest.mark.parametrize("total, expected", [("1180.00", "1000.00"), (None, None)])
def test_restored_subtotal_uses_historical_facts_without_rewriting_them(total, expected):
    facts = BusinessFacts.model_validate(read().model_dump() | {"net_amount": {"state": "known", "value": "900.00", "origin": "member_set", "source_ids": [uuid4()]}})
    if total is None:
        facts = facts.model_copy(update={"amount": Unknown()})
    after = facts.model_copy(update={"net_amount": Unknown(origin="member_set", source_ids=(uuid4(),))})
    actor = _actor().model_dump() | {"shown_as": "name", "issuer_shown_as": "name"}
    revision = DraftRevision(draft_id=str(uuid4()), version=3, actor=actor, before=facts, after=after, source_ids=(), created_at=datetime.now(timezone.utc))
    data = revision.model_dump(mode="json")
    assert data["before_net_amount"]["amount"] == "900"
    assert data["after_net_amount"]["amount"] == expected
    assert BusinessFacts.model_validate(data["after"]).net_amount.state == "unknown"
